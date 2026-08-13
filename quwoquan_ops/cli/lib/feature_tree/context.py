"""仓库根与输出根。测试通过 monkeypatch 本模块属性驱动 fixture 树。"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TREE_ROOT = REPO_ROOT / "specs" / "feature-tree"
OUTPUT_ROOT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "feature-tree"
