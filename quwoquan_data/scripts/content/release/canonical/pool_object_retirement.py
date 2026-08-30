"""Create-once retirement receipts for pool objects that predate the receipt protocol.

这些对象没有入池事务回执，唯一的逆向入口 `release object-transaction rollback`
因此不可用。本模块只写一份独立的退役回执，声明「此对象退出可选集」这一件事：
manifest、`generator` 与各类审核回执既不作为入参也不被写入，所以退役不能用来
伪造溯源；退役请求又必须先观测到 discovery 层已经给出的 typed 不可准入结论，
所以它也不能绕过审核把合格对象下架。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import pool_payload_digest
from content.release.canonical.environment_release_selection import (
    discover_pool_candidates,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
    _write_json,
)
from core.control_types import PoolObjectRetirementReason
from core.schema import assert_valid

POOL_OBJECT_RETIREMENT_SCHEMA = "quwoquan_data.pool_object_retirement_receipt"
# 与既有 `_pool/versions/*.json` 同级。`pool_payload_digest` 排除整个 `_pool`
# 目录，所以写回执不改变对象的 payloadDigest——「只表达退出可选集、不改写原始
# 证据字节」因此是结构成立的，不靠调用方自律。
RETIREMENT_RECEIPT_RELATIVE_PATH = "_pool/retirement.json"
_RETIREMENT_REASONS = frozenset(
    member.value for member in PoolObjectRetirementReason
)


@dataclass(frozen=True, slots=True)
class _RetirementCriterion:
    """One reason bound to the discovery-layer verdict that must be observed."""

    object_type: str
    object_root_name: str
    object_id_field: str
    inadmissibility_code: str


_REASON_CRITERIA: dict[PoolObjectRetirementReason, _RetirementCriterion] = {
    PoolObjectRetirementReason.HISTORICAL_GENERATOR_NOT_AGENT: _RetirementCriterion(
        object_type="content",
        object_root_name="posts",
        object_id_field="contentId",
        inadmissibility_code="DATA.POOL.GENERATOR_PROVENANCE_INVALID",
    ),
}


def _receipt_path(object_root: Path) -> Path:
    return object_root / RETIREMENT_RECEIPT_RELATIVE_PATH


def pool_object_retirement(object_root: Path) -> dict[str, Any] | None:
    """Read one object's retirement conclusion; absence is not a failure.

    ``None`` 只表示「本对象没有退役回执」。回执在场但不可读、缺必需字段、reason
    落在闭集外，或 payloadDigest 与当前对象字节不符时，各自抛出独立 typed 结论：
    既不塌陷为「未退役」而静默恢复成原有的不可准入结论，也不默认判为已退役。
    """

    path = _receipt_path(object_root)
    if path.is_symlink():
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_RECEIPT_UNREADABLE: {path.as_posix()} is a symlink"
        )
    if not path.exists():
        return None
    if not path.is_file():
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_RECEIPT_UNREADABLE: {path.as_posix()}"
        )
    try:
        document = _read_json(path)
    except ObjectTransactionError as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_RECEIPT_UNREADABLE: {path.as_posix()}: {exc}"
        ) from exc
    if "reason" in document and document["reason"] not in _RETIREMENT_REASONS:
        raise ObjectTransactionError(
            "DATA.POOL.RETIREMENT_REASON_INVALID: "
            f"{path.as_posix()} reason={document['reason']!r}"
        )
    try:
        assert_valid(
            document,
            "release",
            "pool_object_retirement_receipt",
            label="pool retirement receipt",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_RECEIPT_INVALID: {path.as_posix()}: {exc}"
        ) from exc
    payload_digest = pool_payload_digest(object_root)
    if document["payloadDigest"] != payload_digest:
        raise ObjectTransactionError(
            "DATA.POOL.RETIREMENT_PAYLOAD_DRIFT: "
            f"{path.as_posix()} frozen={document['payloadDigest']} "
            f"actual={payload_digest}"
        )
    return document


def _observed_inadmissibility(
    *,
    publish_root: Path,
    object_ref: str,
    criterion: _RetirementCriterion,
) -> dict[str, str]:
    """Require the discovery layer to already refuse this object.

    判据不由本模块自算：`discover_pool_candidates` 是逐对象准入的唯一判定面，
    退役只在它已经给出所声明的那条 typed 结论时成立。对象仍可选、判定没有结论、
    结论是另一条 typed 原因，三者各自判否且零写入。
    """

    candidates, excluded = discover_pool_candidates(
        publish_root=publish_root,
        post_refs=(object_ref,),
        strict_admission=True,
    )
    if candidates:
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_OBJECT_ADMISSIBLE: {object_ref}"
        )
    if not excluded:
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_ADMISSION_UNDECIDED: {object_ref}"
        )
    row = excluded[0]
    if row.code != criterion.inadmissibility_code:
        raise ObjectTransactionError(
            "DATA.POOL.RETIREMENT_REASON_MISMATCH: "
            f"{object_ref} declared={criterion.inadmissibility_code} "
            f"observed={row.code}"
        )
    return {"gate": row.gate, "code": row.code}


def _report(
    *,
    result: str,
    document: Mapping[str, Any],
    target: Path,
    publish_root: Path,
) -> dict[str, Any]:
    return {
        "result": result,
        "receiptRef": target.relative_to(publish_root).as_posix(),
        "receipt": dict(document),
    }


def retire_pool_object(
    *,
    publish_root: Path,
    object_type: str,
    object_ref: str,
    reason: str,
    retired_at: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Write one create-once retirement receipt for an inadmissible pool object.

    `retiredAt` 由调用方显式给出而不是读进程时钟：回执是 create-once 文档，重入
    必须逐字节复算出同一份，读时钟会让同参数重入变成一次伪冲突。
    """

    if reason not in _RETIREMENT_REASONS:
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_REASON_INVALID: reason={reason!r}"
        )
    criterion = _REASON_CRITERIA[PoolObjectRetirementReason(reason)]
    if object_type != criterion.object_type:
        raise ObjectTransactionError(
            "DATA.POOL.RETIREMENT_REASON_OBJECT_TYPE_MISMATCH: "
            f"reason={reason} requested={object_type!r} "
            f"criterion={criterion.object_type!r}"
        )
    relative = _safe_rel(object_ref, label="retirement.objectRef")
    object_root = publish_root / criterion.object_root_name / relative
    manifest_path = object_root / "manifest.json"
    if not manifest_path.is_file():
        raise ObjectTransactionError(
            f"DATA.POOL.RETIREMENT_OBJECT_ABSENT: {relative.as_posix()}"
        )
    object_id = str(
        _read_json(manifest_path).get(criterion.object_id_field) or ""
    ).strip()
    if not object_id:
        raise ObjectTransactionError(
            "DATA.POOL.IDENTITY_INVALID: "
            f"{relative.as_posix()} lacks manifest.{criterion.object_id_field}"
        )
    inadmissibility = _observed_inadmissibility(
        publish_root=publish_root,
        object_ref=relative.as_posix(),
        criterion=criterion,
    )
    payload_digest = pool_payload_digest(object_root)
    document: dict[str, Any] = {
        "schema": POOL_OBJECT_RETIREMENT_SCHEMA,
        "objectType": criterion.object_type,
        "objectRef": relative.as_posix(),
        "objectId": object_id,
        "reason": reason,
        "retiredAt": retired_at,
        "payloadDigest": payload_digest,
        "inadmissibility": inadmissibility,
    }
    assert_valid(
        document,
        "release",
        "pool_object_retirement_receipt",
        label="pool retirement receipt",
    )
    target = _receipt_path(object_root)
    if target.exists():
        if pool_object_retirement(object_root) != document:
            raise ObjectTransactionError(
                "DATA.POOL.RETIREMENT_RECEIPT_CONFLICT: "
                f"{target.relative_to(publish_root).as_posix()}"
            )
        return _report(
            result="replayed",
            document=document,
            target=target,
            publish_root=publish_root,
        )
    if not apply:
        return _report(
            result="planned",
            document=document,
            target=target,
            publish_root=publish_root,
        )
    _write_json(target, document)
    written_digest = pool_payload_digest(object_root)
    if written_digest != payload_digest:
        raise ObjectTransactionError(
            "DATA.POOL.RETIREMENT_PAYLOAD_DRIFT: "
            f"{relative.as_posix()} frozen={payload_digest} actual={written_digest}"
        )
    return _report(
        result="retired",
        document=document,
        target=target,
        publish_root=publish_root,
    )


__all__ = [
    "POOL_OBJECT_RETIREMENT_SCHEMA",
    "RETIREMENT_RECEIPT_RELATIVE_PATH",
    "pool_object_retirement",
    "retire_pool_object",
]
