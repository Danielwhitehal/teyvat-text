# -*- coding: utf-8 -*-
"""仓库路径中枢：所有脚本的路径统一从这里取，禁止再硬编码绝对路径。"""
from pathlib import Path


def _find_root(start: Path) -> Path:
    for p in (start, *start.parents):
        if (p / "data").is_dir() and (p / "tools").is_dir():
            return p
    raise RuntimeError(f"找不到仓库根（需同时存在 data/ 与 tools/），起点: {start}")


ROOT = _find_root(Path(__file__).resolve().parent)
DATA = ROOT / "data"
TREES = DATA / "trees"
WEB = ROOT / "web"
STAGING = ROOT / "staging"
TOOLS = ROOT / "tools"
CORRECT = TOOLS / "correct"

BLOCK = {
    "quest": DATA / "quest",
    "artifact": DATA / "artifact",
    "book": DATA / "book",
    "character": DATA / "character",
    "material": DATA / "material",
    "weapon": DATA / "weapon",
}
