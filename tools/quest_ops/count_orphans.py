# -*- coding: utf-8 -*-
"""统计：本地 travellog 中「未进入 aq/eq/legend/wq 树」的任务数量（只读）。"""
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
LOCAL = str(ROOT / "data" / "quest")
TREES = ["aq_quest_tree.json", "eq_quest_tree.json", "legend_quest_tree.json", "wq_quest_tree.json"]
ALL_TREES = TREES + ["iq_quest_tree.json"]


def collect_ids(node, out):
    if isinstance(node, dict):
        if "id" in node and node.get("id") is not None and "children" not in node:
            out.add(str(node["id"]))
        for c in node.get("children", []) or []:
            collect_ids(c, out)


def main():
    per = {}
    for t in ALL_TREES:
        p = os.path.join(TREE_DIR, t)
        if not os.path.exists(p):
            print("MISSING tree", t)
            continue
        one = set()
        collect_ids(json.load(open(p, encoding="utf-8")), one)
        per[t] = one
        print(f"  {t}: {len(one)} ids")
    tree_ids = set().union(*per.values())
    four_ids = set().union(*(per[t] for t in TREES if t in per))
    iq_ids = per.get("iq_quest_tree.json", set())
    print(f"四树去重: {len(four_ids)}   五树去重: {len(tree_ids)}   iq树: {len(iq_ids)}")

    local = {}
    for f in os.listdir(LOCAL):
        if not f.endswith(".json"):
            continue
        parts = f[:-5].split("_")
        if len(parts) >= 2 and parts[-2].isdigit():
            local[int(parts[-2])] = f
    print(f"本地 travellog 文件 id 数: {len(local)}")

    orphan4 = {i: f for i, f in local.items() if str(i) not in four_ids}
    print(f"本地「未进 aq/eq/legend/wq 四树」任务数: {len(orphan4)}")
    in_iq = {i: f for i, f in orphan4.items() if str(i) in iq_ids}
    not_iq = {i: f for i, f in orphan4.items() if str(i) not in iq_ids}
    print(f"  —其中「进了 iq 树」的: {len(in_iq)}")
    print(f"  —其中「连 iq 树都没进」的: {len(not_iq)}")
    orphan5 = {i: f for i, f in local.items() if str(i) not in tree_ids}
    print(f"本地「五树全没进」任务数: {len(orphan5)}")
    clean = {i: f for i, f in orphan4.items() if not (f.startswith("(test)") or "$HIDDEN" in f or "UNRELEASED" in f)}
    print(f"  四树孤儿里排除 test/HIDDEN/UNRELEASED 后: {len(clean)}")
    from collections import Counter as _C

    print("  排除后类型分布:", dict(_C(f[:-5].rsplit("_", 1)[-1] for f in clean.values())))

    # 按类型后缀统计
    from collections import Counter

    def suf(f):
        return f[:-5].rsplit("_", 1)[-1]

    print("四树孤儿 类型分布:", dict(Counter(suf(f) for f in orphan4.values())))

    tree_not_local = sorted(int(x) for x in tree_ids if x.isdigit() and int(x) not in local)
    print(f"树上但本地没有的 id 数: {len(tree_not_local)}")
    print("样例(未进四树):", [orphan4[i] for i in list(orphan4)[:10]])


if __name__ == "__main__":
    main()
