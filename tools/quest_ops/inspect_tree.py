# -*- coding: utf-8 -*-
"""查看某棵任务树的结构：顶层分组 + 各组叶数 + 样例叶名（只读）。"""
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
TREE_DIR = str(ROOT / "data" / "trees")


def leaves(node, acc):
    if isinstance(node, dict):
        if node.get("children"):
            for c in node["children"]:
                leaves(c, acc)
        elif node.get("id") is not None:
            acc.append(node.get("name"))


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "eq_quest_tree.json"
    root = json.load(open(os.path.join(TREE_DIR, name), encoding="utf-8"))
    kids = root.get("children", [])
    print(f"{name}: root={root.get('name')!r} 顶层分组={len(kids)}")
    total = 0
    for c in kids:
        acc = []
        leaves(c, acc)
        total += len(acc)
        print(f"  - {c.get('name')!r}: {len(acc)} 叶  例: {acc[:5]}")
    print(f"合计叶: {total}")


if __name__ == "__main__":
    main()
