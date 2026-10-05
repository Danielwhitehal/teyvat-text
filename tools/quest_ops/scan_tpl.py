# -*- coding: utf-8 -*-
"""扫描任务文件对话里残留的 {{...}} BWIKI 模板（供手工精校）。"""
import glob
import json
import os
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


def walk(dl, out):
    for x in dl:
        t = x.get("text")
        if isinstance(t, str) and "{{" in t:
            out.append(t)
        if x.get("type") == "choice":
            for o in x.get("options", []):
                if isinstance(o, dict):
                    walk(o.get("dialogues") or [], out)


def main():
    for qid in sys.argv[1:]:
        for p in glob.glob(os.path.join(LOCAL, "*_%s_*.json" % qid)):
            data = json.load(open(p, encoding="utf-8"))
            for s in data.get("stories", []):
                out = []
                walk(s.get("dialogues", []), out)
                if out:
                    print(f"\n[{os.path.basename(p)}] story {s.get('title')!r}")
                    for t in out:
                        print("   -", t)


if __name__ == "__main__":
    main()
