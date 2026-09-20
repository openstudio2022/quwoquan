"""脏工作树与 candidate range 的重叠判定；只比较路径字节，不移动 ref。"""
from __future__ import annotations

from collections.abc import Sequence


def parse_porcelain_z(output: str) -> tuple[str, ...]:
    """解析 `git status --porcelain -z`，rename/copy 保留两端路径。"""
    paths: list[str] = []
    entries = iter(output.split("\0"))
    for entry in entries:
        if not entry:
            continue
        # porcelain v1 是「两位 XY + 空格 + path」；调用方不得 strip() 前导空格。
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            paths.append(next(entries, ""))
    return tuple(path for path in paths if path)


def parse_name_only_z(output: str) -> tuple[str, ...]:
    return tuple(name for name in output.split("\0") if name)


def overlapping_dirty_paths(dirty: Sequence[str], touched: Sequence[str]) -> tuple[str, ...]:
    """同一 path、父子目录替换均视为重叠；保留原始路径字节。"""
    return tuple(sorted({
        name for name in dirty
        if any(
            name == changed or name.startswith(f"{changed}/") or changed.startswith(f"{name}/")
            for changed in touched
        )
    }))
