# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""ContractGraph 派生 work root 的回收契约。

每次派生都必须独占一个 work root —— 共享固定 view 会让两个 gate 互删 symlink 树 ——
但独占之后没有任何一方负责回收，实测积压到 39 个、8GB。回收必须在保证长期不膨胀的
同时，绝不删掉并行 gate 正在读的 view。
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.object_evidence_closure import graph_source  # noqa: E402


def make_work_root(parent: Path, name: str, *, age_minutes: float) -> Path:
    root = parent / name
    (root / "view").mkdir(parents=True)
    stamp = time.time() - age_minutes * 60
    os.utime(root, (stamp, stamp))
    return root


def test_stale_work_roots_beyond_both_windows_are_reclaimed(tmp_path: Path) -> None:
    stale = [
        make_work_root(tmp_path, f"{graph_source.WORK_ROOT_PREFIX}{index}", age_minutes=600 + index)
        for index in range(graph_source.RETAINED_WORK_ROOTS + 6)
    ]

    removed = graph_source.prune_stale_work_roots(tmp_path)

    assert len(removed) == 6
    assert sum(1 for path in stale if path.is_dir()) == graph_source.RETAINED_WORK_ROOTS


def test_recent_work_roots_survive_regardless_of_count(tmp_path: Path) -> None:
    """并行运行的另一个 gate 刚建好的 view 不能被删掉脚下。"""
    recent = [
        make_work_root(tmp_path, f"{graph_source.WORK_ROOT_PREFIX}{index}", age_minutes=1)
        for index in range(graph_source.RETAINED_WORK_ROOTS + 6)
    ]

    assert graph_source.prune_stale_work_roots(tmp_path) == []
    assert all(path.is_dir() for path in recent)


def test_foreign_directories_are_out_of_scope(tmp_path: Path) -> None:
    """回收只认自己写下的 derive- 前缀。"""
    for index in range(graph_source.RETAINED_WORK_ROOTS + 3):
        make_work_root(tmp_path, f"{graph_source.WORK_ROOT_PREFIX}{index}", age_minutes=900)
    foreign = make_work_root(tmp_path, "reports", age_minutes=900)

    graph_source.prune_stale_work_roots(tmp_path)

    assert foreign.is_dir()
