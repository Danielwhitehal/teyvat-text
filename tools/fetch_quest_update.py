# -*- coding: utf-8 -*-
r"""任务增量更新：从 Yatta/Ambr 拉取【新】任务 → 转成 travellog 格式 → 写 `更新\quest\`。

提取内核已修正（相对旧版）：
  1. MultiDialog 分支：每个选项的后续对话递归嵌套进该选项，分支合并点(join)之后的公共内容才放到 choice 之后
     （旧版只跟第一个选项的 next，会丢分支）。
  2. `step.title` → `{type:"subtitle"}` 副标题（跳过 `$HIDDEN` / `(test)` 故事与步骤）。
  3. 解析 Yatta 占位符（`#` 行上的 `{NICKNAME}` / `{M#..}{F#..}` / SEXPRO / RUBY / 颜色 / 图标 等），role `旅人`→`旅行者`。
  4. 输出 schema 对齐本地 travellog：choice.options = [{text, dialogues}]。
  5. 提取用 visited 集合防环，避免图收敛处体积爆炸。

用法：
  python fetch_quest_update.py            # 正式拉取新任务到 更新\quest\
  python fetch_quest_update.py --dry      # 只列出远端新增任务 ID，不抓取、不写文件
  python fetch_quest_update.py --limit 3  # 只拉前 3 个（调试）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

import aiohttp
import ambr

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
OUTPUT_DIR = str(ROOT / "staging" / "quest")
SOURCE_DIR = str(ROOT / "data" / "quest")

TASK_TYPES = ("resultDialogue", "needToFinish")
ROLE_MAP = {"旅人": "旅行者", "玩家": "旅行者"}
HIDDEN = ("$HIDDEN",)

# SEXPRO 性别代词键 → 中文（取男性，与项目既有校正口径一致）
SEXPRO = {
    "INFO_MALE_PRONOUN_BROTHER": "哥哥",
    "INFO_MALE_PRONOUN_SISTER": "姐姐",
    "INFO_MALE_PRONOUN_BIGBROTHER": "大哥哥",
    "INFO_MALE_PRONOUN_BIGSISTER": "大姐姐",
    "INFO_MALE_PRONOUN_BOYC": "小哥哥",
    "INFO_MALE_PRONOUN_GIRLC": "小小姐",
    "INFO_MALE_PRONOUN_HERO": "英雄",
    "INFO_MALE_PRONOUN_HEROINE": "女英雄",
    "INFO_MALE_PRONOUN_HE": "他",
    "INFO_MALE_PRONOUN_SHE": "她",
    "INFO_MALE_PRONOUN_CUTEBIGBROTHER": "可爱的大哥哥",
    "INFO_MALE_PRONOUN_CUTEBIGSISTER": "可爱的大姐姐",
}


# ---------------------------------------------------------------- 文本
def _pronoun(key: str) -> str:
    tail = key.split("_")[-1]
    return SEXPRO.get(key, SEXPRO.get("INFO_MALE_PRONOUN_" + tail, ""))


def _expand(t: str) -> str:
    for _ in range(8):
        before = t
        t = re.sub(r"\{颜色\|[^{}]*\|([^{}]*)\}", r"\1", t)
        t = re.sub(r"\{图标\|([^|{}]*)(?:\|[^{}]*)?\}", r"\1", t)
        t = re.sub(r"\{(?:下)?注音\|([^|{}]*)\|([^{}]*)\}", r"\1（\2）", t)
        t = re.sub(r"\{RUBY\|[^|{}]*\|?([^{}]*)\}", lambda m: re.sub(r"\[D\]", "", m.group(1)), t)
        t = re.sub(r"\{RUBY\|([^{}]*)\}", lambda m: re.sub(r"\[D\]", "", m.group(1)), t)
        t = re.sub(r"\{M#([^{}]*)\}\{F#[^{}]*\}", r"\1", t)
        t = re.sub(r"\{M#([^{}]*)\}", r"\1", t)
        t = re.sub(r"\{F#([^{}]*)\}", r"\1", t)

        def _sex(m):
            parts = m.group(1).split("|")
            for p in parts:
                if "FEMALE" not in p:
                    return _pronoun(p) or "他"
            return _pronoun(parts[-1]) or "他"

        t = re.sub(r"\{[A-Z]+AVATAR#SEXPRO\[([^{}]*)\]\}", _sex, t)
        t = t.replace("{NICKNAME}", "旅行者")
        t = re.sub(r"\{REALNAME\[[^{}]*\]\}", "旅行者", t)
        if t == before:
            break
    t = re.sub(r"\{[^{}]*\}", "", t)
    return t


def clean_text(t: str) -> str:
    if not t:
        return t
    t = _expand(t.lstrip("#"))
    return t.replace("\u00a0", " ")


def map_role(r) -> str:
    r = "" if r is None else str(r)
    return ROLE_MAP.get(r, r)


_KEEP = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def _same(a, b) -> bool:
    na = "".join(_KEEP.findall(a or ""))
    nb = "".join(_KEEP.findall(b or ""))
    return bool(na) and na == nb


# ---------------------------------------------------------------- 对话图
def resolve(key, items: dict):
    if key is None:
        return None
    s = str(key)
    if s == "finish":
        return None
    if s in items:
        return s
    if s + "-player" in items:
        return s + "-player"
    if s.endswith("-player") and s[: -len("-player")] in items:
        return s[: -len("-player")]
    return None


def edges(key: str, items: dict) -> list:
    node = items.get(key)
    if not node:
        return []
    out = []
    for seg in node.get("text", []):
        if isinstance(seg, dict) and seg.get("next") is not None:
            r = resolve(seg["next"], items)
            if r:
                out.append(r)
    return out


def bfs_dist(start, items: dict) -> dict:
    if start is None:
        return {}
    dist = {start: 0}
    queue = [start]
    while queue:
        nxt = []
        for n in queue:
            for m in edges(n, items):
                if m not in dist:
                    dist[m] = dist[n] + 1
                    nxt.append(m)
        queue = nxt
    return dist


def find_join(starts: list, items: dict):
    starts = [s for s in starts if s]
    if not starts:
        return None
    reaches = [bfs_dist(s, items) for s in starts]
    common = set(reaches[0])
    for r in reaches[1:]:
        common &= set(r)
    if not common:
        return None
    return min(common, key=lambda n: max(r[n] for r in reaches))


def build_entries(start, items: dict, stop: set, visited: set | None = None) -> list:
    if visited is None:
        visited = set()
    entries = []
    key = start
    guard = 0
    while key and key not in stop and key not in visited:
        guard += 1
        if guard > 100000:
            break
        visited.add(key)
        node = items.get(key)
        if not node:
            break
        ntype = node.get("type")

        if ntype == "SingleDialog":
            role = map_role(node.get("role"))
            nxt = None
            for seg in node.get("text", []):
                if not isinstance(seg, dict):
                    continue
                txt = seg.get("text", "")
                if txt:
                    entries.append({"role": role, "text": clean_text(txt)})
                if seg.get("next") is not None:
                    nxt = seg["next"]
            key = resolve(nxt, items)

        elif ntype == "MultiDialog":
            role = map_role(node.get("role"))
            raw = [s for s in node.get("text", []) if isinstance(s, dict)]
            starts = [resolve(s.get("next"), items) for s in raw]
            join = find_join(starts, items)
            stop2 = set(stop)
            if join:
                stop2.add(join)
            options = []
            for seg, sk in zip(raw, starts):
                opt_text = clean_text(seg.get("text", ""))
                subs = build_entries(sk, items, stop2, visited) if sk else []
                if subs and subs[0].get("type") is None and _same(subs[0].get("text", ""), opt_text):
                    subs = subs[1:]
                options.append({"text": opt_text, "dialogues": subs})
            entries.append({"type": "choice", "role": role, "options": options})
            key = join

        else:
            break
    return entries


# ---------------------------------------------------------------- 组装
def is_hidden(text) -> bool:
    t = "" if text is None else str(text)
    return any(h in t for h in HIDDEN) or t.startswith("(test)")


def clean_title(t) -> str:
    t = "" if t is None else str(t)
    for h in HIDDEN:
        t = t.replace(h, "")
    return t.replace("(test)", "").strip()


def build_story(story) -> dict:
    info = story.get("info", {})
    dialogues = []
    steps = story.get("story", {}) or {}
    for stk in sorted(steps, key=lambda x: int(x)):
        step = steps[stk]
        if is_hidden(step.get("title")):
            continue
        title = clean_title(step.get("title"))
        if title:
            dialogues.append({"type": "subtitle", "text": title})
        tasks = step.get("taskData")
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if task.get("taskType") not in TASK_TYPES:
                continue
            items = task.get("items")
            if not isinstance(items, dict) or not items:
                continue
            start = resolve(task.get("initDialog"), items)
            if start:
                dialogues.extend(build_entries(start, items, set()))
    return {
        "story_id": story.get("id"),
        "title": info.get("title"),
        "description": info.get("description", ""),
        "dialogues": dialogues,
    }


def build_quest(qid: int, raw: dict) -> dict:
    info = raw.get("info", {})
    stories = []
    for sk in sorted(raw.get("storyList", {}), key=lambda x: int(x)):
        story = raw["storyList"][sk]
        if is_hidden(story.get("info", {}).get("title")):
            continue
        stories.append(build_story(story))
    return {
        "quest_id": info.get("id", qid),
        "chapter_num": info.get("chapterNum"),
        "chapter_title": info.get("chapterTitle"),
        "type": info.get("type"),
        "route": info.get("route"),
        "stories": stories,
    }


def sanitize_filename(name: str) -> str:
    for c in '<>:"/\\|?*':
        name = name.replace(c, "_")
    return name.strip()


# ---------------------------------------------------------------- 本地比对
def extract_local_ids() -> set:
    ids = set()
    for f in os.listdir(SOURCE_DIR):
        if not f.endswith(".json"):
            continue
        parts = f.removesuffix(".json").split("_")
        # 约定：`..._{id}_{type}.json`（id=倒数第二段）或 `..._{id}.json`（无类型后缀，id=最后一段）
        if len(parts) >= 2 and parts[-2].isdigit():
            ids.add(int(parts[-2]))
        elif parts and parts[-1].isdigit():
            ids.add(int(parts[-1]))
    return ids


# ---------------------------------------------------------------- 抓取
async def fetch_quest_raw(quest_id: int, version: str, session) -> dict:
    url = f"https://gi.yatta.moe/api/v2/chs/quest/{quest_id}?vh={version}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://gi.yatta.moe/chs/archive/quest",
    }
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status}")
        data = await resp.json()
        if data.get("response") != 200:
            raise Exception(f"API error: {data.get('response')}")
        return data["data"]


async def main():
    sys.setrecursionlimit(20000)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只列出新增 ID，不抓取")
    ap.add_argument("--out", default=OUTPUT_DIR)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    async with ambr.AmbrAPI(lang=ambr.Language.CHS) as client:
        version = await client.fetch_latest_version()
        remote_quests = await client.fetch_quests()

    print(f"Remote quests: {len(remote_quests)}  Version: {version}")
    local_ids = extract_local_ids()
    print(f"Local IDs: {len(local_ids)}")

    remote_ids = {q.id for q in remote_quests}
    new_ids = sorted(remote_ids - local_ids)
    print(f"New quests: {len(new_ids)}")
    if args.dry:
        for qid in new_ids:
            print(f"  {qid}")
        return
    if not new_ids:
        return
    if args.limit:
        new_ids = new_ids[: args.limit]

    os.makedirs(args.out, exist_ok=True)
    quest_map = {q.id: q for q in remote_quests}

    saved = 0
    errors = []
    async with aiohttp.ClientSession() as session:
        for idx, qid in enumerate(new_ids, 1):
            meta = quest_map[qid]
            try:
                raw = await fetch_quest_raw(qid, version, session)
                result = build_quest(qid, raw)
            except Exception as e:  # noqa: BLE001
                print(f"[{idx}/{len(new_ids)}] {qid} ERROR: {e}")
                errors.append((qid, meta.chapter_title, str(e)))
                await asyncio.sleep(0.2)
                continue

            name = sanitize_filename(str(result.get("chapter_title") or f"quest_{qid}"))
            filename = f"{name}_{qid}_{result.get('type') or 'unknown'}.json"
            with open(os.path.join(args.out, filename), "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            saved += 1
            ndlg = sum(len(s["dialogues"]) for s in result["stories"])
            print(f"[{idx}/{len(new_ids)}] {meta.chapter_title} (ID:{qid}, {result.get('type')}) "
                  f"stories={len(result['stories'])} dialogues={ndlg} -> {filename}")
            await asyncio.sleep(0.2)

    print(f"\nSaved: {saved} files to {args.out}")
    if errors:
        print(f"Errors: {len(errors)}")
        for qid, name, err in errors:
            print(f"  ID:{qid} {name} - {err}")


if __name__ == "__main__":
    asyncio.run(main())
