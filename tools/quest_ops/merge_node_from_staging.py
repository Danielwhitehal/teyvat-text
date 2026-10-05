# -*- coding: utf-8 -*-
r"""校验任务树某节点，并把其叶子对应、当前只在暂存区 `更新\quest\` 的任务合并进数据库。

用法：
  python merge_node_from_staging.py --tree eq_quest_tree.json --node 7.1 --dry
  python merge_node_from_staging.py --tree eq_quest_tree.json --node 7.1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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
STAGING = str(ROOT / "staging" / "quest")


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


def index_by_id(d):
    m = {}
    if not os.path.isdir(d):
        return m
    for f in os.listdir(d):
        if not f.endswith(".json"):
            continue
        parts = f[:-5].split("_")
        if len(parts) >= 2 and parts[-2].isdigit():
            m.setdefault(int(parts[-2]), f)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    root = json.load(open(os.path.join(TREE_DIR, args.tree), encoding="utf-8"))
    target = find_node(root, args.node)
    if not target:
        print(f"未找到节点: {args.node}")
        return
    lv = []
    leaves(target, lv)

    local = index_by_id(LOCAL)
    staging = index_by_id(STAGING)

    print(f"树 {args.tree} / 节点「{args.node}」叶子 {len(lv)} 个\n")
    bad = 0
    to_merge = []
    for k, leaf in enumerate(lv, 1):
        name = leaf.get("name", "")
        qid = leaf.get("id")
        m = re.search(r"\(ID:(\d+)\)", name)
        problems = []
        if qid is None:
            problems.append("缺 id")
        if not name:
            problems.append("缺 name")
        if m and qid is not None and int(m.group(1)) != qid:
            problems.append(f"(ID:{m.group(1)}) 与 id 不符")
        clean = re.sub(r"\s*\(ID:\d+\)\s*$", "", name)
        where = "本地" if (qid in local) else ("暂存区" if (qid in staging) else "缺失")
        if where == "缺失":
            problems.append("本地/暂存区均无文件")
        elif where == "暂存区":
            to_merge.append((qid, staging[qid]))
        status = "OK" if not problems else "!! " + "; ".join(problems)
        if problems:
            bad += 1
        print(f"[{k}/{len(lv)}] id={qid} 「{clean}」 -> {where}  {status}")

    print(f"\n结构问题: {bad} 个；需从暂存区合并: {len(to_merge)} 个")
    if args.dry:
        return
    for qid, fname in to_merge:
        shutil.copy2(os.path.join(STAGING, fname), os.path.join(LOCAL, fname))
        print(f"  合并 {qid} {fname}")
    print(f"已合并 {len(to_merge)} 个到数据库")


if __name__ == "__main__":
    main()
