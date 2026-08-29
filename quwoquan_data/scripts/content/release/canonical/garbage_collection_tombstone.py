"""Create-once tombstones for execution work packages the collector released.

「从未物化」与「曾物化后被回收」是两个不同事实，各有自己的证据通道：前者由 campaign
reconciliation receipt 证明（引用图落 ``absent_execution``），后者由本模块的墓碑证明
（引用图落 ``reclaimed_execution``）。两者不得合并成同一个「缺席」——合并之后，
「release 引用的 execution 曾经存在并产出过对象」这件事就再也读不出来了。

墓碑只声明「已回收 / 永久缺席」，绝不改写或伪造任何原始证据字节：它不复制 execution
产物，不重建 manifest，也不为已经消失的字节补摘要。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from content.release.canonical.garbage_collection_contract import (
    gc_workspace_root,
    json_digest,
    write_create_once_json,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_id,
)
from core.schema import assert_valid

GC_EXECUTION_TOMBSTONE_SCHEMA = "quwoquan_data.canonical_gc_execution_tombstone"

_TOMBSTONE_DIRNAME = "tombstones"
_TOMBSTONE_FILENAME = "tombstone.json"


class ExecutionReclaimReason(StrEnum):
    """回收原因闭集。取值本身即拓扑名，不需要二次翻译。

    ``UNKNOWN`` 是显式声明的未知成员，只承载「契约之外的入站取值」，不等价于任何
    放行态：引用图读到它一律判否，因此新增一个契约取值不会靠 default 分支静默放行。
    它不出现在 schema 的 enum 里，所以合法墓碑文件永远落不到这个成员上。
    """

    GC_QUARANTINE_RECLAIM = "gc_quarantine_reclaim"
    RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL = "reclaimed_before_tombstone_protocol"
    UNKNOWN = "unknown"


# 能把一条 `release -> task` 引用解析为合法终态的原因取值；UNKNOWN 刻意不在其中。
REFERENCE_RESOLVING_RECLAIM_REASONS = frozenset(
    {
        ExecutionReclaimReason.GC_QUARANTINE_RECLAIM,
        ExecutionReclaimReason.RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL,
    }
)

# 结论字段：重写同结论幂等，结论不同即判否。观测时刻与其摘要不属于结论——同一次
# 回收被重放时时间必然不同，把它算进结论会把幂等重放误判成冲突。
_CONCLUSION_KEYS = (
    "schema",
    "executionId",
    "reclaimReason",
    "planId",
    "planDigest",
    "backfillId",
    "quarantineRef",
    "merkleRoot",
    "fileCount",
    "bytes",
    "referencedBy",
)


def _typed(code: str, detail: str) -> ObjectTransactionError:
    return ObjectTransactionError(f"GATE_BLOCK DATA.GC.{code}: {detail}")


def execution_reclaim_reason(raw: object) -> ExecutionReclaimReason:
    """把入站取值映射到闭集成员；契约之外的取值一律落显式未知成员。"""

    text = str(raw or "").strip()
    for member in ExecutionReclaimReason:
        if member is ExecutionReclaimReason.UNKNOWN:
            continue
        if text == member.value:
            return member
    return ExecutionReclaimReason.UNKNOWN


@dataclass(frozen=True, slots=True)
class ExecutionTombstone:
    """一个已回收 execution 的不可变回执及其在输出根内的位置。"""

    execution_id: str
    reason: ExecutionReclaimReason
    ref: str
    path: Path
    document: dict[str, Any]


def execution_tombstones_root(output_root: Path) -> Path:
    return gc_workspace_root(output_root) / _TOMBSTONE_DIRNAME


def execution_tombstone_path(output_root: Path, execution_id: str) -> Path:
    """Return the one canonical tombstone path for an execution id."""

    return (
        execution_tombstones_root(output_root)
        / _safe_id(execution_id, label="tombstone.executionId")
        / _TOMBSTONE_FILENAME
    )


def _conclusion(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: document[key] for key in _CONCLUSION_KEYS if key in document}


def validate_execution_tombstone(
    document: Mapping[str, Any],
    *,
    execution_id: str,
) -> ExecutionReclaimReason:
    """Validate one tombstone against its contract and return its typed reason."""

    try:
        assert_valid(
            dict(document),
            "governance",
            "canonical_gc_execution_tombstone",
            label=f"canonical GC execution tombstone:{execution_id}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _typed("EXECUTION_TOMBSTONE_INVALID", str(exc)) from exc
    if document.get("executionId") != execution_id:
        raise _typed(
            "EXECUTION_TOMBSTONE_INVALID",
            f"tombstone path identity drift: {execution_id}",
        )
    if document.get("tombstoneDigest") != json_digest(
        document,
        excluded="tombstoneDigest",
    ):
        raise _typed(
            "EXECUTION_TOMBSTONE_INVALID",
            f"tombstone digest drift: {execution_id}",
        )
    reason = execution_reclaim_reason(document.get("reclaimReason"))
    if reason not in REFERENCE_RESOLVING_RECLAIM_REASONS:
        raise _typed(
            "EXECUTION_TOMBSTONE_INVALID",
            "reclaimReason is outside the declared closed set: "
            f"{document.get('reclaimReason')!r}",
        )
    return reason


def write_execution_tombstone(
    *,
    output_root: Path,
    execution_id: str,
    reason: ExecutionReclaimReason,
    reclaimed_at: str,
    referenced_by: tuple[Mapping[str, str], ...],
    plan_id: str | None = None,
    plan_digest: str | None = None,
    backfill_id: str | None = None,
    quarantine_ref: str | None = None,
    merkle_root: str | None = None,
    file_count: int | None = None,
    total_bytes: int | None = None,
) -> tuple[dict[str, Any], Path, bool]:
    """Create one tombstone exactly once; replaying the same conclusion is a no-op.

    永久缺席的字节没有 merkle/fileCount/bytes 可记，这些键因此整键缺席而不是补零或
    空字符串——补一个零字节摘要等于伪造一份从未观测到的字节事实。
    """

    if reason not in REFERENCE_RESOLVING_RECLAIM_REASONS:
        raise _typed(
            "EXECUTION_TOMBSTONE_INVALID",
            f"reclaimReason is outside the declared closed set: {reason!r}",
        )
    document: dict[str, Any] = {
        "schema": GC_EXECUTION_TOMBSTONE_SCHEMA,
        "executionId": execution_id,
        "reclaimReason": reason.value,
        "reclaimedAt": reclaimed_at,
        "referencedBy": [dict(row) for row in referenced_by],
    }
    if reason is ExecutionReclaimReason.GC_QUARANTINE_RECLAIM:
        document.update(
            {
                "planId": plan_id,
                "planDigest": plan_digest,
                "quarantineRef": quarantine_ref,
                "merkleRoot": merkle_root,
                "fileCount": file_count,
                "bytes": total_bytes,
            }
        )
    else:
        document["backfillId"] = backfill_id
    document["tombstoneDigest"] = json_digest(document, excluded="tombstoneDigest")
    validate_execution_tombstone(document, execution_id=execution_id)
    path = execution_tombstone_path(output_root, execution_id)
    if write_create_once_json(path, document):
        return document, path, True
    persisted = _read_json(path)
    validate_execution_tombstone(persisted, execution_id=execution_id)
    if _conclusion(persisted) != _conclusion(document):
        raise _typed(
            "EXECUTION_TOMBSTONE_CONFLICT",
            f"persisted tombstone states a different conclusion: {execution_id}",
        )
    return persisted, path, False


def load_execution_tombstones(output_root: Path) -> dict[str, ExecutionTombstone]:
    """Read every tombstone under one output root, fail-closed on any invalid one."""

    root = execution_tombstones_root(output_root)
    tombstones: dict[str, ExecutionTombstone] = {}
    if not root.exists():
        return tombstones
    if root.is_symlink() or not root.is_dir():
        raise _typed(
            "EXECUTION_TOMBSTONE_INVALID",
            f"tombstone root is invalid: {root}",
        )
    for directory in sorted(root.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            raise _typed(
                "EXECUTION_TOMBSTONE_INVALID",
                f"unknown tombstone entry: {directory}",
            )
        path = directory / _TOMBSTONE_FILENAME
        if path.is_symlink() or not path.is_file():
            raise _typed(
                "EXECUTION_TOMBSTONE_INVALID",
                f"tombstone is missing: {path}",
            )
        document = _read_json(path)
        reason = validate_execution_tombstone(document, execution_id=directory.name)
        tombstones[directory.name] = ExecutionTombstone(
            execution_id=directory.name,
            reason=reason,
            ref=path.resolve().relative_to(output_root.resolve()).as_posix(),
            path=path.resolve(),
            document=document,
        )
    return tombstones


__all__ = [
    "GC_EXECUTION_TOMBSTONE_SCHEMA",
    "REFERENCE_RESOLVING_RECLAIM_REASONS",
    "ExecutionReclaimReason",
    "ExecutionTombstone",
    "execution_reclaim_reason",
    "execution_tombstone_path",
    "execution_tombstones_root",
    "load_execution_tombstones",
    "validate_execution_tombstone",
    "write_execution_tombstone",
]
