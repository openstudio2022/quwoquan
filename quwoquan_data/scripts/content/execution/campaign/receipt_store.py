"""Create-once writes for campaign receipts and the evidence they reference."""

from __future__ import annotations

import fcntl
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.io import read_json, write_json

from content.execution.campaign.publish_binding import receipt_error


@contextmanager
def receipt_write_lock(path: Path) -> Iterator[None]:
    """串行化同一路径的 create-once 写入，让「已存在则比对」保持原子。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f".{path.name}.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_create_once_document(
    path: Path,
    payload: Mapping[str, Any],
    *,
    collision_detail: str,
) -> Path:
    """写一份不可变文档：不存在则落盘，已存在则必须逐字节等值。

    重放同一终态是幂等的，落到同一路径的**不同**内容是身份冲突，只能判否——回执与它
    引用的证据都不允许被后一次运行改写。
    """

    with receipt_write_lock(path):
        if path.is_symlink():
            raise receipt_error(
                "PATH_INVALID",
                f"{path.name} cannot be a symlink",
                evidence=path,
            )
        if path.is_file():
            if read_json(path) != payload:
                raise receipt_error(
                    "IMMUTABLE_COLLISION",
                    collision_detail,
                    evidence=path,
                )
            return path
        write_json(path, payload)
    return path
