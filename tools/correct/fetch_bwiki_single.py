# -*- coding: utf-8 -*-
"""
单独抓取某个故事页面的「任务剧情」，输出可直接替换到 travellog JSON 的 dialogues 数组。

用法:
    python fetch_bwiki_single.py <故事标题> [输出文件.json]

默认输出到 bwiki_data/<故事标题>_dialogues.json
输出内容为 JSON 数组，可直接替换 travellog JSON 中对应故事的 "dialogues" 字段。
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_bwiki_v2 as fb


def _count(dialogues):
    n = 0
    for x in dialogues:
        if isinstance(x, dict) and x.get("type") == "choice":
            n += 1
            for o in x.get("options", []):
                if isinstance(o, dict):
                    n += _count(o.get("dialogues", []))
        else:
            n += 1
    return n


def fetch_story_dialogues(title: str):
    """返回 (description, dialogues)；失败返回 (None, None)"""
    candidates = [title, title + "（任务）"]
    for attempt in range(3):
        for page in candidates:
            wt = fb.fetch_wikitext(page)
            if not wt:
                continue
            section = fb.extract_dialogue_section(wt)
            if section:
                desc = fb.extract_description(wt)
                return desc, fb.parse_dialogues_from_section(section)
        wait = 60 * (attempt + 1)
        print(f"  未取得，{wait}s 后重试（第 {attempt + 1}/3 次）...")
        time.sleep(wait)
    return None, None


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_bwiki_single.py <故事标题> [输出文件.json]")
        return
    title = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(fb.OUTPUT_DIR, f"{title}_dialogues.json")

    print(f"抓取: {title}")
    desc, dialogues = fetch_story_dialogues(title)
    if dialogues is None:
        print("失败：多次重试仍未取得（可能仍被反爬或页面不存在）")
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dialogues, f, ensure_ascii=False, indent=2)

    print(f"OK: {len(dialogues)} 顶层项 / {_count(dialogues)} 条（含嵌套）")
    if desc:
        print(f"description: {desc[:70]}...")
    print(f"保存到: {out}")


if __name__ == "__main__":
    main()
