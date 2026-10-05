# -*- coding: utf-8 -*-
r"""
角色【全量重爬】脚本（替代 Yatta 版）。
- 对远端所有角色重新抓 detail + fetter，覆盖本地 data\character\。
- 跑前先备份旧数据到 staging\character\_backup_<时间戳>\。
- 字段精简：只保留 id/name/element/title/constellation/story{title,text}/quotes{title,text}。
- 旅行者：14 个元素/性别变体共享故事与语音，只保留一个（输出 旅行者.json）；
  其 fetter 只挂在裸 id 上，走原始接口。
- 排除无意义角色：奇偶·男性 / 奇偶·女性。
- 若抓取有失败，则【不替换】本地，需重跑。
"""
import asyncio
import json
import os
import shutil
import sys
import time

import ambr

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
LOCAL_DATA_DIR = str(ROOT / "data" / "character")
OUTPUT_DIR = str(ROOT / "staging" / "character")

EXCLUDE_NAMES = {"奇偶·男性", "奇偶·女性"}
TRAVELER_NAME = "旅行者"


def brief(node):
    if isinstance(node, dict):
        return {"title": node.get("title"), "text": node.get("text")}
    return {"title": getattr(node, "title", None), "text": getattr(node, "text", None)}


async def fetch_story_quotes(client, c):
    """返回 (story_dict, quotes_dict)，键为字符串下标，值为 {title,text}。"""
    if c.name == TRAVELER_NAME:
        # 旅行者：fetter 只在裸 id（如 10000005 / 10000007）上，走原始接口
        base = str(c.id).split("-")[0]
        raw = await client._request(f"avatarFetter/{base}", use_cache=True)
        data = raw.get("data", raw) if isinstance(raw, dict) else raw
        story = {k: brief(v) for k, v in (data.get("story") or {}).items()}
        quotes = {k: brief(v) for k, v in (data.get("quotes") or {}).items()}
        return story, quotes

    fetter = await client.fetch_character_fetter(c.id)
    story = {str(i): brief(s) for i, s in enumerate(fetter.stories)}
    quotes = {str(i): brief(q) for i, q in enumerate(fetter.quotes)}
    return story, quotes


def convert_char(c, detail, story, quotes):
    return {
        "id": str(c.id),                         # 与本地一致：纯 id（旅行者为 10000005-pyro 这类）
        "name": c.name,
        "element": c.element.value,
        "title": detail.info.title,
        "constellation": detail.info.constellation,
        "story": story,
        "quotes": quotes,
    }


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # 清掉上次遗留的暂存 json（保留 _backup_* 子目录）
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    async with ambr.AmbrAPI(lang=ambr.Language.CHS) as client:
        chars = await client.fetch_characters()
        print(f"远程角色: {len(chars)}")

        saved, errors = 0, []
        seen_traveler = False
        for i, c in enumerate(chars, 1):
            if c.name in EXCLUDE_NAMES:
                print(f"[{i}/{len(chars)}] 跳过(排除): {c.name}")
                continue
            if c.name == TRAVELER_NAME:
                if seen_traveler:
                    continue
                seen_traveler = True
            try:
                detail = await client.fetch_character_detail(c.id)
                story, quotes = await fetch_story_quotes(client, c)
                data = convert_char(c, detail, story, quotes)
                with open(os.path.join(OUTPUT_DIR, f"{c.name}.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                saved += 1
                print(f"[{i}/{len(chars)}] {c.name}")
            except Exception as e:
                errors.append((c.name, str(e)))
                print(f"FAILED: {c.name}: {e}")
            await asyncio.sleep(0.2)

    print(f"\n抓取完成: 成功 {saved} / 失败 {len(errors)}")
    if errors:
        print("有失败，未替换本地。失败列表:")
        for name, err in errors:
            print(f"  {name} - {err}")
        print("请重跑本脚本。")
        return

    # 1) 备份旧数据 → 更新\character\_backup_<ts>\
    backup_dir = os.path.join(OUTPUT_DIR, "_backup_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(backup_dir, exist_ok=True)
    old_count = 0
    for f in os.listdir(LOCAL_DATA_DIR):
        if f.endswith(".json"):
            shutil.copy2(os.path.join(LOCAL_DATA_DIR, f), os.path.join(backup_dir, f))
            old_count += 1
    print(f"已备份旧数据 {old_count} 个 -> {backup_dir}")

    # 2) 替换本地：清空旧 json，再写入新数据
    for f in os.listdir(LOCAL_DATA_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(LOCAL_DATA_DIR, f))
    new_count = 0
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".json"):
            shutil.copy2(os.path.join(OUTPUT_DIR, f), os.path.join(LOCAL_DATA_DIR, f))
            new_count += 1
    print(f"已替换本地角色数据: {new_count} 个")


if __name__ == "__main__":
    asyncio.run(main())
