"""全局批次号真相源：单调递增、文件锁保护。"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from _common.io import read_json, write_json
from _common.paths import global_batch_seq_lock_path, global_batch_seq_path

GLOBAL_BATCH_SEQ_SCHEMA = "quwoquan_data.global_batch_seq/1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as fp:
        fcntl.flock(fp.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fp.fileno(), fcntl.LOCK_UN)


def read_latest_global_batch_seq() -> int:
    path = global_batch_seq_path()
    if not path.is_file():
        return 0
    data = read_json(path)
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get("latestSeq") or 0)
    except (TypeError, ValueError):
        return 0


def allocate_global_batch_seq() -> int:
    """分配下一个全局批次号（首次 1，幂等依赖调用方的 batch_manifest 复用）。"""
    path = global_batch_seq_path()
    lock = global_batch_seq_lock_path()
    with _locked(lock):
        latest = read_latest_global_batch_seq()
        next_seq = latest + 1
        write_json(
            path,
            {
                "schemaVersion": GLOBAL_BATCH_SEQ_SCHEMA,
                "latestSeq": next_seq,
                "updatedAt": _now_iso(),
            },
        )
        return next_seq
