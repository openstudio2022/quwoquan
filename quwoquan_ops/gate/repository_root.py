#!/usr/bin/env python3
"""`quwoquan_ops/gate/**` 的 root discovery bootstrap。

推导算法只有一份，位于 `quwoquan_ops/cli/lib/repository_root.py`。本文件是极薄转发层：
在「还不知道仓库根、因此还不能 import 包」的前提下按物理路径找到那份实现并转发它的符号，
自身不复制任何判定逻辑。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CANONICAL_RELATIVE = Path("quwoquan_ops/cli/lib/repository_root.py")
_CANONICAL_MODULE = "quwoquan_repository_root"


def _load_canonical():
    cached = sys.modules.get(_CANONICAL_MODULE)
    if cached is not None:
        return cached
    here = Path(__file__).resolve()
    for candidate in here.parents:
        module_path = candidate / _CANONICAL_RELATIVE
        if not module_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(_CANONICAL_MODULE, module_path)
        if spec is None or spec.loader is None:
            break
        module = importlib.util.module_from_spec(spec)
        sys.modules[_CANONICAL_MODULE] = module
        spec.loader.exec_module(module)
        return module
    raise RuntimeError(
        f"从 {here} 向上找不到 {_CANONICAL_RELATIVE}；root discovery 无法自举"
    )


_canonical = _load_canonical()

REPOSITORY_MARKERS = _canonical.REPOSITORY_MARKERS
RepositoryRootNotFound = _canonical.RepositoryRootNotFound
ScanRootUnusable = _canonical.ScanRootUnusable
is_repository_root = _canonical.is_repository_root
find_repository_root = _canonical.find_repository_root
require_scan_root = _canonical.require_scan_root
require_nonempty = _canonical.require_nonempty


def repository_root() -> Path:
    """本脚本树所在仓库的根目录。"""
    return find_repository_root(__file__)


__all__ = [
    "REPOSITORY_MARKERS",
    "RepositoryRootNotFound",
    "ScanRootUnusable",
    "find_repository_root",
    "is_repository_root",
    "repository_root",
    "require_nonempty",
    "require_scan_root",
]
