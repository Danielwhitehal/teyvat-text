# -*- coding: utf-8 -*-
r"""按 ID 列表逐个校正（复用 run_task_simpler 的 _process_one）。
用于"查漏补缺"：你在树里补好缺漏任务后，把它们的 ID 交给本脚本即可。

用法：
    python 校正\run_ids.py 1105 2031 2050            # 逐个处理
    python 校正\run_ids.py --file=ids.txt           # 从文本里提取所有数字作为 ID
    python 校正\run_ids.py 1105 --dry               # 只看会不会处理（不抓取/不写）
    python 校正\run_ids.py 1105 --force             # 强制重做（覆盖，有 _yatta 备份）

行为：
  - 逐个调 _process_one：定位 travellog → 备份 _yatta → 抓 BWIKI → 选源 → §1 替换 → 折叠边界 → 写回 → 校验。
  - 已处理过（任务目录下有 _bwiki.json）的 ID 会被 **skip**，除非 --force。
  - 与树/后缀无关：只按 ID 定位（后缀 aq/wq/lq 只是开发分类，归属以树为准）。
"""
import sys
import os
import re
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import run_task_simpler as R  # noqa: E402


def name_of(qid):
    fs = glob.glob(os.path.join(R.SOURCE_DIR, "*_%s_*.json" % qid))
    if not fs:
        return ""
    b = os.path.basename(fs[0])
    return re.sub(r"_\d+_[A-Za-z]+\.json$", "", b)


def existing_bwiki(qid):
    fs = glob.glob(os.path.join(R.SOURCE_DIR, "*_%s_*.json" % qid))
    if not fs:
        return None, None
    fname = os.path.basename(fs[0])
    try:
        chapter_title = __import__("json").load(open(fs[0], encoding="utf-8")).get("chapter_title", "")
    except Exception:
        chapter_title = ""
    task_dir = os.path.join(R.OUTPUT_DIR, "%s_%s" % (chapter_title, qid))
    return task_dir, os.path.join(task_dir, fname.replace(".json", "_bwiki.json"))


def main():
    raw = sys.argv[1:]
    force = "--force" in raw
    dry = "--dry" in raw
    ids = [a for a in raw if a.isdigit()]
    for a in raw:
        if a.startswith("--file="):
            p = a.split("=", 1)[1]
            ids += re.findall(r"\d{3,}", open(p, encoding="utf-8").read())
    ids = list(dict.fromkeys(ids))
    if not ids:
        print(__doc__)
        return

    todo, skipped = [], []
    for qid in ids:
        _, eb = existing_bwiki(qid)
        (skipped if (eb and os.path.exists(eb) and not force) else todo).append(qid)

    print("共 %d 个 ID：待处理 %d，已处理(将跳过) %d" % (len(ids), len(todo), len(skipped)))
    for qid in skipped:
        print("  [skip] %s (ID:%s)" % (name_of(qid) or "?", qid))
    if dry:
        for qid in todo:
            print("  [will] %s (ID:%s)" % (name_of(qid) or "?", qid))
        print("--dry：未抓取、未写回。")
        return

    results = []
    for qid in todo:
        nm = name_of(qid) or ("ID%s" % qid)
        st, msg, notes = R._process_one(nm, qid, force)
        results.append((qid, nm, st, notes))
    print("\n===== 汇总 =====")
    from collections import Counter
    c = Counter(r[2] for r in results)
    print("结果:", dict(c), "| 跳过:", len(skipped))
    for qid, nm, st, notes in results:
        if st != "ok":
            print("  %s %s (ID:%s) %s" % (st, nm, qid, "; ".join(notes)))
    R._report_notes(["%s (ID:%s): %s" % (nm, qid, x) for qid, nm, st, ns in results for x in ns], "指定ID")


if __name__ == "__main__":
    main()
