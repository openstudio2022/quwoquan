#!/usr/bin/env python3
"""仓库根发现与扫描根校验的唯一实现。

门禁脚本一旦用 `Path(__file__).resolve().parents[N]` 推导仓库根，脚本被移动或多包一层
目录，`N` 就会静默失配：推导出的根依然是一个真实存在的目录，于是 `glob` / `rglob`
扫描出 0 个对象，门禁反而报告通过。本模块把「什么是仓库根」收敛成一份实现，并要求
调用方显式声明扫描根，让空扫描在 verifier 内部就无法被当成通过。

两棵脚本树（`quwoquan_ops/gate/**` 与 `quwoquan_service/scripts/verify/**`）各自持有一份
极薄的 bootstrap（`repository_root.py`），它们只负责按物理路径找到本文件并转发，
不重复实现推导算法。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

#: 仓库根的判据：三个标记必须同时存在。任何一个单独出现都不足以确定根，
#: 因为 `quwoquan_service/quwoquan_service` 这类错位路径同样能命中单个标记。
REPOSITORY_MARKERS: tuple[str, ...] = ("quwoquan_app", "quwoquan_service", ".git")


class RepositoryRootNotFound(RuntimeError):
    """从给定起点向上找不到同时满足全部标记的仓库根。"""


class ScanRootUnusable(RuntimeError):
    """扫描根缺失、不是目录，或没有命中任何真实对象。"""


def is_repository_root(candidate: Path) -> bool:
    """`candidate` 是否同时具备全部仓库根标记。"""
    return candidate.is_dir() and all(
        (candidate / marker).exists() for marker in REPOSITORY_MARKERS
    )


def find_repository_root(start: Path | str) -> Path:
    """从 `start`（文件或目录）向上定位仓库根。

    找不到时抛 `RepositoryRootNotFound`，绝不退化成「返回某个存在的目录」——
    那正是空扫描假绿的来源。
    """
    origin = Path(start).resolve()
    for candidate in (origin, *origin.parents):
        if is_repository_root(candidate):
            return candidate
    raise RepositoryRootNotFound(
        f"从 {origin} 向上找不到同时包含 {', '.join(REPOSITORY_MARKERS)} 的仓库根"
    )


def require_scan_root(root: Path, description: str) -> Path:
    """断言扫描根真实存在，返回它本身以便链式使用。"""
    if not root.is_dir():
        raise ScanRootUnusable(
            f"{description} 扫描根不存在: {root}；"
            "扫描根缺失时门禁必须阻断，不得按空集报告通过"
        )
    return root


def require_nonempty(
    matches: Iterable[Path],
    description: str,
    *,
    root: Path | None = None,
) -> list[Path]:
    """断言扫描命中至少一个对象，返回物化后的列表。

    空集意味着门禁本轮什么都没校验，等价于没有门禁，因此必须阻断而不是通过。
    """
    materialized = list(matches)
    if not materialized:
        location = f"（扫描根 {root}）" if root is not None else ""
        raise ScanRootUnusable(
            f"{description} 扫描到 0 个对象{location}；"
            "空扫描不构成通过证据，先修复扫描根或对象归属"
        )
    return materialized
