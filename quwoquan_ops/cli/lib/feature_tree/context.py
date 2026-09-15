"""仓库根与输出根。测试通过 monkeypatch 本模块属性驱动 fixture 树。"""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar

REPO_ROOT = Path(__file__).resolve().parents[4]
TREE_ROOT = REPO_ROOT / "specs" / "feature-tree"
OUTPUT_ROOT = REPO_ROOT / ".qwq_output" / "env" / "repo" / "runs" / "feature-tree"
_SOURCE: ContextVar[Path | None] = ContextVar("feature_tree_source", default=None)


def repository_root() -> Path:
    return _SOURCE.get() or REPO_ROOT


def tree_root() -> Path:
    source = _SOURCE.get()
    return source / "specs/feature-tree" if source is not None else TREE_ROOT


def output_root() -> Path:
    source = _SOURCE.get()
    return source / ".qwq_output/env/repo/runs/feature-tree" if source is not None else OUTPUT_ROOT


@contextmanager
def source_repository(root: Path):
    """每个调用上下文独立的 source reader，不修改全局 ROOT 常量。"""
    token = _SOURCE.set(root.resolve())
    try:
        yield
    finally:
        _SOURCE.reset(token)
