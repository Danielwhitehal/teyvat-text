import json
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
BWIKI_DIR = str(ROOT / "tools" / "correct" / "bwiki_data")
OUTPUT_DIR = str(ROOT / "data" / "quest")

def restore_from_bwiki(bwiki_file):
    """从bwiki文件恢复Yatta版本（使用local_dialogues）"""
    with open(bwiki_file, "r", encoding="utf-8") as f:
        bwiki = json.load(f)

    result = {
        "quest_id": bwiki["quest_id"],
        "chapter_num": bwiki["chapter_num"],
        "chapter_title": bwiki["chapter_title"],
        "type": bwiki["type"],
        "route": bwiki["route"],
        "stories": []
    }

    for bs in bwiki["bwiki_stories"]:
        story = {
            "story_id": bs["story_id"],
            "title": bs["title"],
            "description": bs.get("description", ""),
            "dialogues": bs.get("local_dialogues", [])
        }
        result["stories"].append(story)

    # 生成输出文件名（沿用原始文件名，去掉 _bwiki 后缀，兼容 aq/wq/eq/iq/lq）
    out_name = os.path.basename(bwiki_file).replace("_bwiki.json", ".json")
    out_path = os.path.join(OUTPUT_DIR, out_name)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(len(s["dialogues"]) for s in result["stories"])
    print(f"Restored: {out_name} - {len(result['stories'])} stories, {total} dialogues")

def main():
    if len(sys.argv) > 1:
        # 指定bwiki文件路径
        bwiki_file = sys.argv[1]
        if not os.path.exists(bwiki_file):
            # 可能是文件名，在所有子文件夹中查找
            for dirpath, dirnames, filenames in os.walk(BWIKI_DIR):
                if sys.argv[1] in filenames:
                    bwiki_file = os.path.join(dirpath, sys.argv[1])
                    break
        restore_from_bwiki(bwiki_file)
    else:
        # 恢复所有任务
        count = 0
        for dirpath, dirnames, filenames in os.walk(BWIKI_DIR):
            for f in filenames:
                if f.endswith("_bwiki.json"):
                    restore_from_bwiki(os.path.join(dirpath, f))
                    count += 1
        print(f"\nTotal restored: {count} tasks")

if __name__ == "__main__":
    main()
