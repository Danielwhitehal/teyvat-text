# -*- coding: utf-8 -*-
"""按 HTML 查看器的规则，校验某树节点下每个任务叶能否命中本地文件。"""
import argparse
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
TREE_DIR = str(ROOT / "data" / "trees")
LOCAL = str(ROOT / "data" / "quest")
TYPES = ["aq", "wq", "eq", "iq", "lq"]


def find_node(node, name):
    if isinstance(node, dict):
        if node.get("name") == name:
            return node
        for c in node.get("children", []) or []:
            r = find_node(c, name)
            if r:
                return r
    return None


def leaves(node, out):
    if isinstance(node, dict):
        if node.get("children"):
            for c in node["children"]:
                leaves(c, out)
        else:
            out.append(node)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--node", required=True)
    args = ap.parse_args()
    root = json.load(open(os.path.join(TREE_DIR, args.tree), encoding="utf-8"))
    lv = []
    leaves(find_node(root, args.node), lv)
    files = set(os.listdir(LOCAL))
    ok = bad = 0
    for leaf in lv:
        name, qid = leaf.get("name", ""), leaf.get("id")
        clean = re.sub(r"\s*\(ID:\d+\)\s*$", "", name)
        hit = next((f"{clean}_{qid}_{t}.json" for t in TYPES if f"{clean}_{qid}_{t}.json" in files), None)
        if hit:
            ok += 1
            print(f"OK  id={qid} {hit}")
        else:
            bad += 1
            print(f"!!  id={qid} 「{clean}」 未命中（本地无匹配文件名）")
    print(f"\n命中 {ok} / 未命中 {bad}")


if __name__ == "__main__":
    main()
