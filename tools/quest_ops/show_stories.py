# -*- coding: utf-8 -*-
"""打印若干任务文件的 story 标题/描述/对话数，用于对照 BWIKI 页名。"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
LOCAL = str(ROOT / "data" / "quest")
STAGING = str(ROOT / "staging" / "quest")


def find(ids):
    out = {}
    for d in (LOCAL, STAGING):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".json"):
                continue
            parts = f[:-5].split("_")
            if len(parts) >= 2 and parts[-2].isdigit() and int(parts[-2]) in ids:
                out.setdefault(int(parts[-2]), (d, f))
    return out


def main():
    ids = {int(x) for x in sys.argv[1:]}
    for qid, (d, f) in sorted(find(ids).items()):
        data = json.load(open(os.path.join(d, f), encoding="utf-8"))
        loc = "本地" if d == LOCAL else "暂存"
        print(f"\n=== ID {qid} [{loc}] {f}  type={data.get('type')} chapter={data.get('chapter_title')!r}")
        for s in data.get("stories", []):
            print(f"   story_id={s.get('story_id')} title={s.get('title')!r} ndlg={len(s.get('dialogues', []))} desc={(s.get('description') or '')[:40]!r}")


if __name__ == "__main__":
    main()
