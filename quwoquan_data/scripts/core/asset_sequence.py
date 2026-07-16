"""执行序号真相源：单调递增、文件锁保护。"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core.io import read_json, write_json
from core.paths import execution_sequence_lock_path, execution_sequence_path

EXECUTION_SEQUENCE_SCHEMA = "quwoquan_data.execution_sequence/1"


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


def read_latest_execution_sequence() -> int:
    path = execution_sequence_path()
    if not path.is_file():
        return 0
    data = read_json(path)
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get("latestSeq") or 0)
    except (TypeError, ValueError):
        return 0


def allocate_execution_sequence() -> int:
    """分配下一个执行序号（首次 1，幂等依赖运行状态复用）。"""
    path = execution_sequence_path()
    lock = execution_sequence_lock_path()
    with _locked(lock):
        latest = read_latest_execution_sequence()
        next_seq = latest + 1
        write_json(
            path,
            {
                "schemaVersion": EXECUTION_SEQUENCE_SCHEMA,
                "latestSeq": next_seq,
                "updatedAt": _now_iso(),
            },
        )
        return next_seq
