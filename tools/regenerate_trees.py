# -*- coding: utf-8 -*-
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
BASE = str(ROOT / "data")
TREE_DIR = os.path.join(BASE, "trees")

# 通用扁平树：叶 = 文件名去 .json，name = 数据里的 name，type = 块名
configs = [
    ("artifact", "artifact_tree.json", "圣遗物", "artifact"),
    ("character", "character_tree.json", "角色", "character"),
    ("material", "material_tree.json", "材料", "material"),
    ("weapon", "weapon_tree.json", "武器", "weapon"),
]

for data_dir, tree_file, display_name, type_tag in configs:
    data_path = os.path.join(BASE, data_dir)
    if not os.path.exists(data_path):
        print(f"SKIP: {data_dir} not found")
        continue

    children = []
    for f in sorted(os.listdir(data_path)):
        if not f.endswith(".json"):
            continue
        file_id = f[:-5]  # remove .json
        filepath = os.path.join(data_path, f)
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            name = data.get("name", file_id)
        except Exception:
            name = file_id
        children.append({"name": name, "id": file_id, "type": type_tag})

    tree = {"name": display_name, "children": children}
    tree_path = os.path.join(TREE_DIR, tree_file)
    with open(tree_path, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, ensure_ascii=False, indent=2)

    print(f"{tree_file}: {len(children)} items")


# 书籍：自定义两层结构（故事书 / 地图可阅读物），并剔除废弃条目
BOOK_DIR = os.path.join(BASE, "book")
BOOK_TREE = os.path.join(TREE_DIR, "book_tree.json")
BOOK_ID_THRESHOLD = 10000  # id < 阈值 → 故事书；否则 → 地图可阅读物
BOOK_EXCLUDE = {"_100470.json", "(test)提纳里的来信_120260.json"}  # 废弃条目，见 quest_tree/_废弃书籍清单.md
def load_approved_map_ids():
    """自引导白名单：从现有 book_tree.json 读取"已被批准"的地图文本 id。
    文件不存在/无法解析 → 返回空集（地图文本需显式批准才会进树）。"""
    if not os.path.exists(BOOK_TREE):
        return set()
    try:
        with open(BOOK_TREE, encoding="utf-8") as fh:
            tree = json.load(fh)
    except Exception:
        return set()
    approved = set()

    def walk(node):
        for ch in node.get("children", []):
            if ch.get("children"):
                walk(ch)
            else:
                m = re.search(r"_(\d+)$", ch.get("id") or "")
                if m:
                    approved.add(int(m.group(1)))

    walk(tree)
    return approved


def build_book_tree():
    approved = load_approved_map_ids()
    story, mapping, dropped = [], [], 0
    for f in sorted(os.listdir(BOOK_DIR)):
        if not f.endswith(".json") or f in BOOK_EXCLUDE:
            continue
        with open(os.path.join(BOOK_DIR, f), encoding="utf-8") as fh:
            data = json.load(fh)
        leaf = {"name": data.get("name") or f[:-5], "id": f[:-5], "type": "book"}
        idv = data.get("id")
        if isinstance(idv, int) and idv < BOOK_ID_THRESHOLD:
            story.append((idv, leaf))            # 故事书：全收（放进数据目录即进树）
        elif idv in approved:
            mapping.append((idv, leaf))          # 地图文本：仅保留已批准的
        else:
            dropped += 1

    story.sort(key=lambda x: x[0])
    mapping.sort(key=lambda x: x[0])

    tree = {
        "name": "书籍",
        "children": [
            {"name": "书籍", "children": [leaf for _, leaf in story]},
            {"name": "地图可阅读物", "children": [leaf for _, leaf in mapping]},
        ],
    }
    with open(BOOK_TREE, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, ensure_ascii=False, indent=2)

    print(f"book_tree.json: 书籍 {len(story)} + 地图可阅读物 {len(mapping)} "
          f"(剔除废弃 {len(BOOK_EXCLUDE)} 个；未批准地图文本过滤掉 {dropped} 个)")


if os.path.exists(BOOK_DIR):
    build_book_tree()
else:
    print("SKIP: book data dir not found")
