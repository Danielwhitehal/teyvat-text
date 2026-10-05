# -*- coding: utf-8 -*-
"""任务剧情提取器（正确版）。

相对旧 `fetch_quest_update.py` 的修复：
  1. 正确处理 MultiDialog 分支：每个选项的后续对话**递归嵌套**进该选项，
     分支合并点(join)之后的公共内容才放到 choice 之后（不再只走第一个选项）。
  2. `step.title` 转为 `{type:"subtitle"}` 副标题（跳过 `$HIDDEN` / `(test)` 步骤）。
  3. 输出 schema 对齐本地 travellog：choice.options = [{text, dialogues}]。
  4. 跳过隐藏/测试故事（标题含 `$HIDDEN` 或以 `(test)` 开头）。
  5. 解析 Yatta 占位符（`#` 行上的 `{NICKNAME}` / `{M#..}{F#..}` / SEXPRO / RUBY / 颜色 / 图标 等），
     role `旅人` → `旅行者`。

只读远端、输出仅写本专项目录（绝不写数据目录）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://gi.yatta.moe/api/v2/chs"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://gi.yatta.moe/chs/archive/quest",
}
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


# ---------------------------------------------------------------- fetch
def fetch_quest(qid: int, version: str | None = None, retries: int = 3) -> dict:
    url = f"{BASE}/quest/{qid}" + (f"?vh={version}" if version else "")
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("response") != 200:
                raise RuntimeError(f"API response={data.get('response')}")
            return data["data"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch {qid} failed: {last}")


# ---------------------------------------------------------------- text
def _pronoun(key: str) -> str:
    tail = key.split("_")[-1]
    return SEXPRO.get(key, SEXPRO.get("INFO_MALE_PRONOUN_" + tail, ""))


def _expand(t: str) -> str:
    """展开 `{...}` 模板（可含嵌套，最多迭代到稳定）。"""
    for _ in range(8):
        before = t

        # 颜色 / 图标：取正文
        t = re.sub(r"\{颜色\|[^{}]*\|([^{}]*)\}", r"\1", t)
        t = re.sub(r"\{图标\|([^|{}]*)(?:\|[^{}]*)?\}", r"\1", t)

        # 注音 / 下注音：文（注）
        t = re.sub(r"\{(?:下)?注音\|([^|{}]*)\|([^{}]*)\}", r"\1（\2）", t)

        # RUBY：取正文，去 [D] 前缀
        t = re.sub(r"\{RUBY\|[^|{}]*\|?([^{}]*)\}", lambda m: re.sub(r"\[D\]", "", m.group(1)), t)
        t = re.sub(r"\{RUBY\|([^{}]*)\}", lambda m: re.sub(r"\[D\]", "", m.group(1)), t)

        # 相邻 M/F 变体 → 取男
        t = re.sub(r"\{M#([^{}]*)\}\{F#[^{}]*\}", r"\1", t)
        t = re.sub(r"\{M#([^{}]*)\}", r"\1", t)
        t = re.sub(r"\{F#([^{}]*)\}", r"\1", t)

        # 玩家性别代词 SEXPRO
        def _sex(m):
            parts = m.group(1).split("|")
            for p in parts:
                if "FEMALE" not in p:
                    return _pronoun(p) or "他"
            return _pronoun(parts[-1]) or "他"

        t = re.sub(r"\{[A-Z]+AVATAR#SEXPRO\[([^{}]*)\]\}", _sex, t)

        # 名字
        t = t.replace("{NICKNAME}", "旅行者")
        t = re.sub(r"\{REALNAME\[[^{}]*\]\}", "旅行者", t)

        if t == before:
            break
    # 兜底：清掉残余模板
    t = re.sub(r"\{[^{}]*\}", "", t)
    return t


def clean_text(t: str) -> str:
    if not t:
        return t
    t = t.lstrip("#")
    t = _expand(t)
    t = t.replace("\u00a0", " ")
    return t


def map_role(r) -> str:
    r = "" if r is None else str(r)
    return ROLE_MAP.get(r, r)


_KEEP = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def _same(a, b) -> bool:
    na = "".join(_KEEP.findall(a or ""))
    nb = "".join(_KEEP.findall(b or ""))
    return bool(na) and na == nb


# ---------------------------------------------------------------- graph
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
    for suf in ("-player",):
        if s.endswith(suf) and s[: -len(suf)] in items:
            return s[: -len(suf)]
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
    """所有分支的最早公共后继（合并点）。"""
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
                # Yatta 分支首节点常是「玩家所选台词」的回显，与选项文本重复 → 去重
                if subs and subs[0].get("type") is None and _same(subs[0].get("text", ""), opt_text):
                    subs = subs[1:]
                options.append({"text": opt_text, "dialogues": subs})
            entries.append({"type": "choice", "role": role, "options": options})
            key = join

        else:
            break
    return entries


# ---------------------------------------------------------------- build
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


def sanitize(name: str) -> str:
    for c in '<>:"/\\|?*':
        name = name.replace(c, "_")
    return name.strip()


def main():
    sys.setrecursionlimit(20000)
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+", type=int)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "extracted"))
    ap.add_argument("--version", default=None)
    ap.add_argument("--print", action="store_true", dest="show")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    for qid in args.ids:
        try:
            raw = fetch_quest(qid, args.version)
            result = build_quest(qid, raw)
        except Exception as e:  # noqa: BLE001
            print(f"[{qid}] ERROR {e}")
            continue
        fname = f"{sanitize(str(result['chapter_title'] or 'quest_' + str(qid)))}_{qid}_{result['type']}.json"
        path = os.path.join(args.out, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        ndlg = sum(len(s["dialogues"]) for s in result["stories"])
        print(f"[{qid}] {result['chapter_title']} type={result['type']} stories={len(result['stories'])} top-dialogues={ndlg} -> {fname}")
        if args.show:
            print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    main()
