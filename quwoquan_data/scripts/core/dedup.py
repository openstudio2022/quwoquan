"""跨批次去重账本（completedEntities/Topics/downloadedSources）。

落 ``task/_shared/dedup_ledger.json``；与 ``execution_manifest_path.json``（任务定义快照，§14.1）
分离，避免两类语义共用同一文件名。账本只写 data local cache 唯一路径。

并发契约（多省并行前置，WP4）：mark_* 为 read-modify-write，多 worker 共用同一
全国维度账本时必须互斥，否则丢更新 → 跨批重复生产。写路径统一经
``_ledger_lock``（flock 排他锁，`dedup_ledger.json.lock` 哨兵文件），锁内重读最新
账本再合并写回；只读路径不加锁（append-only 语义下读到旧值最多多选一次，
promote 幂等兜底）。
"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from typing import Iterator

from .io import read_json, write_json

LEDGER_SCHEMA = "quwoquan_data.dedup_ledger/1"


def _ledger_path() -> "Path":
    from pathlib import Path
    from . import paths

    return Path(paths.DATA_LOCAL_ROOT) / "cache" / "coverage_dedup.json"


@contextmanager
def _ledger_lock(execution_id: str) -> Iterator[None]:
    del execution_id
    lock_path = _ledger_path().with_suffix(".json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def load_manifest(execution_id: str) -> dict:
    path = _ledger_path()
    if path.exists():
        return read_json(path)
    return {
        "schemaVersion": LEDGER_SCHEMA,
        "executionId": execution_id,
        "completedEntities": [],
        "completedTopics": [],
        "downloadedSources": [],
    }


def save_manifest(execution_id: str, manifest: dict) -> None:
    manifest.setdefault("schemaVersion", LEDGER_SCHEMA)
    write_json(_ledger_path(), manifest)


def _mark(execution_id: str, field: str, value: str) -> None:
    with _ledger_lock(execution_id):
        manifest = load_manifest(execution_id)
        entries = manifest.setdefault(field, [])
        if value not in entries:
            entries.append(value)
            save_manifest(execution_id, manifest)


def is_entity_done(execution_id: str, entity_id: str) -> bool:
    m = load_manifest(execution_id)
    return entity_id in m.get("completedEntities", [])


def mark_entity_done(execution_id: str, entity_id: str) -> None:
    _mark(execution_id, "completedEntities", entity_id)


def is_topic_done(execution_id: str, topic_id: str) -> bool:
    m = load_manifest(execution_id)
    return topic_id in m.get("completedTopics", [])


def mark_topic_done(execution_id: str, topic_id: str) -> None:
    _mark(execution_id, "completedTopics", topic_id)


def is_source_downloaded(execution_id: str, source_key: str) -> bool:
    m = load_manifest(execution_id)
    return source_key in m.get("downloadedSources", [])


def mark_source_downloaded(execution_id: str, source_key: str) -> None:
    _mark(execution_id, "downloadedSources", source_key)
