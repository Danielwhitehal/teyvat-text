# -*- coding: utf-8 -*-
"""对比「新提取器输出」与「本地已校正 travellog」的差异（只读、只打印）。"""
from __future__ import annotations

import difflib
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
EXTRACT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extracted")

KEEP = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def norm(t) -> str:
    if not isinstance(t, str):
        return ""
    return "".join(KEEP.findall(t))


def find(root, qid):
    for f in os.listdir(root):
        stem = f[:-5]
        parts = stem.split("_")
        if len(parts) >= 2 and parts[-2].isdigit() and int(parts[-2]) == qid:
            return os.path.join(root, f)
    return None


def stats(data):
    stories = data.get("stories", [])
    top, choices, opts, subs, depth = 0, 0, 0, 0, 0

    def walk(dl, d):
        nonlocal top, choices, opts, subs, depth
        depth = max(depth, d)
        for x in dl:
            top += 1
            if x.get("type") == "choice":
                choices += 1
                for o in x.get("options", []):
                    opts += 1
                    if isinstance(o, dict):
                        walk(o.get("dialogues") or [], d + 1)
            elif x.get("type") == "subtitle":
                subs += 1

    for s in stories:
        walk(s.get("dialogues", []), 0)
    return {
        "stories": len(stories),
        "items": top,
        "choices": choices,
        "options": opts,
        "subtitles": subs,
        "max_opt_depth": depth,
    }


def seq_of(data):
    out = []
    for s in data.get("stories", []):
        for x in s.get("dialogues", []):
            _collect(x, out)
    return out


def _collect(x, out):
    if x.get("type") == "choice":
        out.append("CHOICE:" + norm(x.get("role")))
        for o in x.get("options", []):
            if isinstance(o, str):
                out.append("OPT:" + norm(o))
            else:
                out.append("OPT:" + norm(o.get("text")))
                for y in o.get("dialogues") or []:
                    _collect(y, out)
    elif x.get("type") == "subtitle":
        out.append("SUB:" + norm(x.get("text")))
    else:
        out.append(norm(x.get("text")))


def compare(qid):
    lp = find(LOCAL, qid)
    ep = find(EXTRACT, qid)
    print(f"\n{'='*80}\nQuest {qid}")
    if not lp or not ep:
        print(f"  missing: local={bool(lp)} extract={bool(ep)}")
        return
    print(f"  local  : {os.path.basename(lp)}")
    print(f"  extract: {os.path.basename(ep)}")
    L = json.load(open(lp, encoding="utf-8"))
    E = json.load(open(ep, encoding="utf-8"))
    sl, se = stats(L), stats(E)
    for k in sl:
        flag = "" if sl[k] == se[k] else "  <-- diff"
        print(f"  {k:15s} local={sl[k]:5d}  extract={se[k]:5d}{flag}")

    a = seq_of(L)
    b = seq_of(E)
    from collections import Counter

    la = Counter(a)
    lb = Counter(b)
    inter = sum((la & lb).values())
    cov_e_in_l = inter / max(1, len(b))
    cov_l_in_e = inter / max(1, len(a))
    print(f"  coverage : ours-in-local={cov_e_in_l:.3f}  local-in-ours={cov_l_in_e:.3f}")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    print(f"  sequence: local={len(a)} extract={len(b)} similarity={sm.ratio():.3f}")

    # 副标题集合差异
    lsub = [x for x in a if x.startswith("SUB:")]
    esub = [x for x in b if x.startswith("SUB:")]
    only_l = [s for s in lsub if s not in esub]
    only_e = [s for s in esub if s not in lsub]
    print(f"  subtitles only-local   ({len(only_l)}): {[s[4:][:14] for s in only_l[:12]]}")
    print(f"  subtitles only-extract ({len(only_e)}): {[s[4:][:14] for s in only_e[:12]]}")

    # 前若干差异块
    shown = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        shown += 1
        if shown > 6:
            print("  ... (more diff blocks)")
            break
        la = " | ".join(a[i1:i2][:6])
        lb = " | ".join(b[j1:j2][:6])
        print(f"  [{tag}] local: {la[:110]}")
        print(f"          ours : {lb[:110]}")


def main():
    ids = [int(x) for x in sys.argv[1:]]
    for q in ids:
        compare(q)


if __name__ == "__main__":
    main()
