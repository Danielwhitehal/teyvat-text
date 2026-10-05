# -*- coding: utf-8 -*-
r"""把某棵任务树中、指定节点名下的所有叶子任务，用新 demo 重爬并【原地替换】文本。

用法：
  python replace_tree_node.py --tree wq_quest_tree.json --node 至冬 --dry
  python replace_tree_node.py --tree wq_quest_tree.json --node 至冬
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_quest import fetch_quest, build_quest  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
TREE_DIR = str(ROOT / "data" / "trees")
LOCAL = str(ROOT / "data" / "quest")


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
        elif node.get("id") is not None:
            out.append((str(node.get("id")), node.get("name", "")))


def local_by_id():
    m = {}
    for f in os.listdir(LOCAL):
        if not f.endswith(".json"):
            continue
        parts = f[:-5].split("_")
        if len(parts) >= 2 and parts[-2].isdigit():
            m.setdefault(parts[-2], []).append(f)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args()

    root = json.load(open(os.path.join(TREE_DIR, args.tree), encoding="utf-8"))
    target = find_node(root, args.node)
    if not target:
        print(f"未找到节点: {args.node}")
        return
    lv = []
    leaves(target, lv)
    print(f"树 {args.tree} / 节点「{args.node}」下叶子 {len(lv)} 个")

    loc = local_by_id()
    backup = os.path.join(HERE, "_backup", f"{args.node}_old")
    repl = empty = miss = 0
    for k, (qid, name) in enumerate(lv, 1):
        files = loc.get(qid)
        if not files:
            print(f"[{k}/{len(lv)}] {qid} {name}  本地无对应文件，跳过")
            miss += 1
            continue
        if args.dry:
            print(f"[{k}/{len(lv)}] {qid} {name} -> {files}")
            continue
        try:
            raw = fetch_quest(int(qid))
            result = build_quest(int(qid), raw)
        except Exception as e:  # noqa: BLE001
            print(f"[{k}/{len(lv)}] {qid} FETCH-FAIL {e}")
            continue
        if not result.get("stories"):
            print(f"[{k}/{len(lv)}] {qid} {name}  新提取为空，保留原样")
            empty += 1
            continue
        os.makedirs(backup, exist_ok=True)
        for fname in files:
            dst = os.path.join(LOCAL, fname)
            shutil.copy2(dst, os.path.join(backup, fname))
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        ndlg = sum(len(s["dialogues"]) for s in result["stories"])
        print(f"[{k}/{len(lv)}] {qid} {name} 替换 {files} stories={len(result['stories'])} dialogues={ndlg}")
        repl += 1
        time.sleep(args.sleep)

    if not args.dry:
        print(f"\n替换 {repl} / 空保留 {empty} / 本地缺失 {miss}  备份: {backup}")


if __name__ == "__main__":
    main()
