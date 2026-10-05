# -*- coding: utf-8 -*-
"""
书籍类文本分类统计：故事书(id<10000) vs 地图文本(id>=10000)
输出: 书籍分类_故事书vs地图文本.md
"""
import os, json, sys, collections

sys.stdout.reconfigure(encoding="utf-8")

import sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve().parent
while not (_p / "paths.py").exists() and _p.parent != _p:
    _p = _p.parent
_sys.path.insert(0, str(_p))
from paths import ROOT  # noqa: E402
BOOK_DIR = str(ROOT / "data" / "book")
OUT_MD = str(ROOT / "tools" / "correct" / "书籍分类_故事书vs地图文本.md")
THRESHOLD = 10000  # 断层在 1076~100181 之间，取 10000 稳妥

rows = []
problems = []
for f in sorted(os.listdir(BOOK_DIR)):
    if not f.endswith(".json"):
        continue
    p = os.path.join(BOOK_DIR, f)
    try:
        with open(p, encoding="utf-8") as fh:
            o = json.load(fh)
    except Exception as e:
        problems.append((f, "解析失败: %r" % e))
        continue
    idv = o.get("id")
    vols = o.get("volumes") or []
    rows.append({
        "id": idv, "name": o.get("name"), "vols": len(vols),
        "len": sum(len(v.get("full_text") or "") for v in vols),
        "file": f,
        "suffix_id": int(f[:-5].rsplit("_", 1)[1]) if len(f[:-5].rsplit("_", 1)) == 2 and f[:-5].rsplit("_", 1)[1].isdigit() else None,
    })

story = [r for r in rows if isinstance(r["id"], int) and r["id"] < THRESHOLD]
mapping = [r for r in rows if isinstance(r["id"], int) and r["id"] >= THRESHOLD]
no_id = [r for r in rows if not isinstance(r["id"], int)]
no_suffix = [r for r in rows if r["suffix_id"] is None]
mismatch = [r for r in rows if r["suffix_id"] is not None and r["suffix_id"] != r["id"]]
bad_name = [r for r in rows if not (r["name"] or "").strip()]
test_name = [r for r in rows if "test" in (r["name"] or "").lower()]

def fmt(r):
    return "| %s | %s | %d | %d | `%s` |" % (
        r["id"], (r["name"] or "").replace("|", "\\|"), r["vols"], r["len"], r["file"])

lines = []
lines.append("# 书籍类文本分类：故事书 vs 地图文本")
lines.append("")
lines.append("> 数据目录：`%s`" % BOOK_DIR)
lines.append("> 判定：JSON `id` 字段 **< %d → 故事书**；**>= %d → 地图文本**（两者之间有巨大断层，见下）。" % (THRESHOLD, THRESHOLD))
lines.append("> 由 `analyze_books.py` 自动生成。")
lines.append("")

lines.append("## 一、总览")
lines.append("")
lines.append("| 类别 | 数量 | 总卷数 | 总字数(full_text) | id 范围 |")
lines.append("|---|---|---|---|---|")
if story:
    lines.append("| 故事书 (id<%d) | %d | %d | %d | %d ~ %d |" % (
        THRESHOLD, len(story), sum(r["vols"] for r in story), sum(r["len"] for r in story),
        min(r["id"] for r in story), max(r["id"] for r in story)))
if mapping:
    lines.append("| 地图文本 (id>=%d) | %d | %d | %d | %d ~ %d |" % (
        THRESHOLD, len(mapping), sum(r["vols"] for r in mapping), sum(r["len"] for r in mapping),
        min(r["id"] for r in mapping), max(r["id"] for r in mapping)))
lines.append("| 合计 | %d | %d | %d | |" % (
    len(rows), sum(r["vols"] for r in rows), sum(r["len"] for r in rows)))
lines.append("")

lines.append("## 二、id 分布与断层")
lines.append("")
buckets = collections.Counter()
for r in rows:
    i = r["id"]
    if i < 1000: buckets["<1000"] += 1
    elif i < 10000: buckets["1000-9999"] += 1
    elif i < 100000: buckets["10000-99999"] += 1
    elif i < 200000: buckets["100000-199999"] += 1
    else: buckets[">=200000"] += 1
lines.append("| id 区间 | 数量 |")
lines.append("|---|---|")
for k in ["<1000", "1000-9999", "10000-99999", "100000-199999", ">=200000"]:
    lines.append("| %s | %d |" % (k, buckets.get(k, 0)))
lines.append("")
sids = sorted(r["id"] for r in story)
mids = sorted(r["id"] for r in mapping)
if sids and mids:
    lines.append("- 故事书最大 id：**%d**；地图文本最小 id：**%d**（断层约 %d）。" % (
        sids[-1], mids[0], mids[0] - sids[-1]))
lines.append("")

if problems:
    lines.append("## ⚠️ 解析失败")
    lines.append("")
    for f, e in problems:
        lines.append("- `%s` — %s" % (f, e))
    lines.append("")

lines.append("## 三、异常/边界")
lines.append("")
lines.append("- 无整数 id：%d 个" % len(no_id))
lines.append("- 名称为空：%d 个 %s" % (len(bad_name), [r["file"] for r in bad_name]))
lines.append("- 名称含 test：%d 个 %s" % (len(test_name), [r["file"] for r in test_name]))
lines.append("- 文件名无数字 ID 后缀：%d 个" % len(no_suffix))
lines.append("- 文件名后缀 id ≠ JSON id：%d 个 %s" % (len(mismatch), [r["file"] for r in mismatch]))
lines.append("")

lines.append("## 四、故事书列表（id < %d，共 %d 个）" % (THRESHOLD, len(story)))
lines.append("")
lines.append("| id | 名称 | 卷数 | 字数 | 文件名 |")
lines.append("|---|---|---|---|---|")
for r in sorted(story, key=lambda x: x["id"]):
    lines.append(fmt(r))
lines.append("")

lines.append("## 五、地图文本列表（id >= %d，共 %d 个）" % (THRESHOLD, len(mapping)))
lines.append("")
lines.append("| id | 名称 | 卷数 | 字数 | 文件名 |")
lines.append("|---|---|---|---|---|")
for r in sorted(mapping, key=lambda x: x["id"]):
    lines.append(fmt(r))
lines.append("")

with open(OUT_MD, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))

print("总数:", len(rows))
print("故事书 (id<%d): %d  [id %d~%d]" % (THRESHOLD, len(story), min(sids), max(sids)))
print("地图文本 (id>=%d): %d  [id %d~%d]" % (THRESHOLD, len(mapping), min(mids), max(mids)))
print("断层:", sids[-1], "->", mids[0])
print("名称为空:", [r["file"] for r in bad_name])
print("含 test:", [r["file"] for r in test_name])
print("已写出:", OUT_MD)
