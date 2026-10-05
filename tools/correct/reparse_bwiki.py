# -*- coding: utf-8 -*-
"""
离线重解析：用已保存的 {stem}_wikitext.json 重新生成 {stem}_bwiki.json。
用于修正解析器后，无需重新联网爬取即可更新结果。

用法:
    python reparse_bwiki.py "任务文件_bwiki.json"     # 也可传 "任务文件.json"
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_bwiki_v2 as fb

BWIKI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bwiki_data")


def main():
    if len(sys.argv) < 2:
        print("用法: python reparse_bwiki.py <任务文件_bwiki.json>")
        return
    arg = sys.argv[1]
    stem = arg[:-5] if arg.endswith(".json") else arg
    if stem.endswith("_bwiki"):
        stem = stem[:-6]

    bw_files = glob.glob(os.path.join(BWIKI_DIR, "*", stem + "_bwiki.json"))
    wt_files = glob.glob(os.path.join(BWIKI_DIR, "*", stem + "_wikitext.json"))
    if not bw_files:
        print(f"找不到: {stem}_bwiki.json")
        return
    if not wt_files:
        print(f"找不到 {stem}_wikitext.json（该任务未保存原文，无法离线重解析）")
        return

    with open(bw_files[0], encoding="utf-8") as f:
        bw = json.load(f)
    with open(wt_files[0], encoding="utf-8") as f:
        wt_map = json.load(f)

    changed = 0
    for s in bw.get("bwiki_stories", []):
        title = s["title"]
        if "(test)" in title or "$HIDDEN" in title:
            continue
        wt = wt_map.get(title)
        if not wt:
            continue
        section = fb.extract_dialogue_section(wt)
        if not section:
            s["bwiki_dialogues"] = []
            s["status"] = "not_found"
            continue
        desc = fb.extract_description(wt)
        if desc:
            s["description"] = desc
        new_dlg = fb.parse_dialogues_from_section(section)
        if new_dlg != s.get("bwiki_dialogues"):
            changed += 1
            print(f"  变化: [{s['story_id']}] {title}")
        s["bwiki_dialogues"] = new_dlg
        s["status"] = "fetched"

    with open(bw_files[0], "w", encoding="utf-8") as f:
        json.dump(bw, f, ensure_ascii=False, indent=2)
    print(f"重解析完成: {bw_files[0]}")
    print(f"有变化的故事: {changed}")


if __name__ == "__main__":
    main()
