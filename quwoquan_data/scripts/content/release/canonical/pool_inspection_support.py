"""Shared canonical pool inspection projections and admission predicates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
)
from content.release.canonical.effective_admission import (
    EffectiveAdmission,
    resolve_effective_admission,
)
from content.release.canonical.environment_release_selection import (
    MILESTONE_TARGETS,
)
from content.release.canonical.environment_release_support import (
    pool_error_code,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from content.release.canonical.pool_object_retirement import (
    pool_object_retirement,
)

_SUPPLY_TYPES = ("homepage", "article", "image", "video")
M100_TARGETS = MILESTONE_TARGETS["M100"]
_USAGE_SCOPES = {"research", "commercial"}
_REASON_MESSAGES = {
    "DATA.POOL.EMPTY": "池中还没有可发布的 Homepage 或 Post",
    "DATA.POOL.EXPLICIT_ADMISSION_MISSING": "对象缺少显式准入记录，需要补录",
    "DATA.POOL.OBJECT_NOT_ADMITTED": "对象尚未完成生成、质量或授权准入",
    "DATA.POOL.AUTHOR_NOT_ADMITTED": "对象引用的作者尚未准入",
    "DATA.POOL.REFERENCE_MISSING": "对象缺少可交付引用",
    "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE": "对象缺少完整来源署名与权利归因",
    "DATA.POOL.RETIREMENT_RECEIPT_UNREADABLE": "对象的退役回执不可读",
    "DATA.POOL.RETIREMENT_RECEIPT_INVALID": "对象的退役回执缺必需字段",
    "DATA.POOL.RETIREMENT_REASON_INVALID": "对象的退役原因落在闭集之外",
    "DATA.POOL.RETIREMENT_PAYLOAD_DRIFT": "对象在退役后原始证据字节发生改写",
}


def _manifest_refs(root: Path) -> list[tuple[str, Path]]:
    if not root.is_dir():
        return []
    return [
        (path.parent.relative_to(root).as_posix(), path)
        for path in sorted(root.rglob("manifest.json"))
    ]


def _resolved_admission(
    object_root: Path,
    document: Mapping[str, Any],
    *,
    object_type: str,
) -> EffectiveAdmission:
    try:
        return resolve_effective_admission(
            object_root,
            object_type=object_type,
            document=document,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        # Malformed explicit or historical evidence stays one object-level
        # eligibility failure and is never hidden by a later admission error.
        # 占位 evidenceDigest 故意保持非 canonical 形态（无 sha256: 前缀），
        # 使 `_evidence_bound` 与 admitted 判定都无法把它当作合法证据。
        return EffectiveAdmission(
            record={
                "status": "active",
                "contentVersion": 0,
                "processResult": "failed",
                "qualityResult": "passed",
                "eligibilityResult": "failed",
                "usageScope": None,
                "evidenceRef": "invalid-pool-record",
                "evidenceDigest": "invalid-pool-record-digest",
            },
            source="invalid",
        )


def _admission_record(
    object_root: Path,
    document: Mapping[str, Any],
    *,
    object_type: str,
) -> Mapping[str, Any] | None:
    return _resolved_admission(
        object_root,
        document,
        object_type=object_type,
    ).record


def _active(record: Mapping[str, Any]) -> bool:
    return str(record.get("status") or "active").strip() == "active"


def _quality_passed(record: Mapping[str, Any]) -> bool:
    return record.get("qualityResult") == "passed"


def _valid_version(record: Mapping[str, Any]) -> bool:
    value = record.get("contentVersion")
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _evidence_bound(record: Mapping[str, Any]) -> bool:
    return bool(
        str(record.get("evidenceRef") or "").strip()
        and str(record.get("evidenceDigest") or "").startswith("sha256:")
    )


def _eligibility_passed(record: Mapping[str, Any]) -> bool:
    return record.get("eligibilityResult") == "passed"


def _author_admitted(record: Mapping[str, Any] | None) -> bool:
    return bool(
        is_pool_record_admitted(record)
        and isinstance(record, Mapping)
        and _active(record)
        and _valid_version(record)
        and _evidence_bound(record)
        and record.get("processResult") == "completed"
        and _quality_passed(record)
        and _eligibility_passed(record)
        and record.get("usageScope") in {None, ""}
    )


def _content_admitted(record: Mapping[str, Any] | None) -> bool:
    return bool(
        is_pool_record_admitted(record)
        and isinstance(record, Mapping)
        and _active(record)
        and _valid_version(record)
        and _evidence_bound(record)
        and record.get("processResult") == "completed"
        and _quality_passed(record)
        and _eligibility_passed(record)
        and record.get("usageScope") in _USAGE_SCOPES
    )


def _issue(
    issues: list[dict[str, str]],
    *,
    gate: str,
    code: str,
    ref: str,
) -> None:
    issues.append({"gate": gate, "code": code, "ref": ref})


def _not_admitted_issue(
    issues: list[dict[str, str]],
    *,
    record: Mapping[str, Any] | None,
    admission_missing: bool,
    ref: str,
) -> None:
    if admission_missing:
        _issue(
            issues,
            gate="eligibility",
            code="DATA.POOL.EXPLICIT_ADMISSION_MISSING",
            ref=ref,
        )
        return
    gate = (
        "quality"
        if isinstance(record, Mapping) and record.get("qualityResult") == "failed"
        else "eligibility"
    )
    _issue(
        issues,
        gate=gate,
        code="DATA.POOL.OBJECT_NOT_ADMITTED",
        ref=ref,
    )


def _retirement_reported(
    issues: list[dict[str, str]],
    retired: list[dict[str, str]],
    *,
    object_root: Path,
    object_type: str,
    object_ref: str,
) -> bool:
    """Report one retirement conclusion; True means it replaces the object issue.

    「已退役」与「未准入」是两个独立结论。回执缺席时返回 False，调用方照常产出
    原有的不可准入 issue。回执在场但不可读、缺字段、reason 越界或 payloadDigest
    漂移时，各自落一条自己的 typed issue 而不是静默恢复成原有结论，也不计入
    retired。
    """

    try:
        receipt = pool_object_retirement(object_root)
    except ObjectTransactionError as exc:
        _issue(
            issues,
            gate="eligibility",
            code=pool_error_code(exc),
            ref=object_ref,
        )
        return True
    if receipt is None:
        return False
    retired.append(
        {
            "objectType": object_type,
            "objectRef": object_ref,
            "reason": str(receipt["reason"]),
        }
    )
    return True


def _creator_refs(object_root: Path, document: Mapping[str, Any]) -> list[str]:
    path = object_root / "creator.refs.json"
    if path.is_file():
        raw = _read_json(path).get("creatorRefs")
        if isinstance(raw, list):
            return [str(value).strip() for value in raw if str(value).strip()]
    author_id = str(document.get("authorId") or "").strip()
    return [author_id] if author_id else []


def _author_closure_ready(
    *,
    object_root: Path,
    document: Mapping[str, Any],
    author_admission: Mapping[str, bool],
) -> bool:
    refs = _creator_refs(object_root, document)
    return bool(refs) and all(author_admission.get(ref, False) for ref in refs)


def _entity_closure_ready(
    *,
    publish_root: Path,
    raw_refs: Any,
) -> bool:
    if not isinstance(raw_refs, list) or not raw_refs:
        return False
    for raw_ref in raw_refs:
        value = str(raw_ref or "").strip()
        if not value.startswith("/entity/"):
            return False
        if not (
            publish_root / "entities" / value.removeprefix("/entity/") / "manifest.json"
        ).is_file():
            return False
    return True


def _reason_summary(issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    counts = Counter((row["gate"], row["code"]) for row in issues)
    return [
        {
            "gate": gate,
            "code": code,
            "count": count,
            "message": _REASON_MESSAGES.get(code, code),
        }
        for (gate, code), count in sorted(counts.items())
    ]


__all__ = [
    "M100_TARGETS",
    "_SUPPLY_TYPES",
    "_active",
    "_admission_record",
    "_author_admitted",
    "_author_closure_ready",
    "_content_admitted",
    "_creator_refs",
    "_eligibility_passed",
    "_entity_closure_ready",
    "_evidence_bound",
    "_issue",
    "_manifest_refs",
    "_not_admitted_issue",
    "_quality_passed",
    "_reason_summary",
    "_resolved_admission",
    "_retirement_reported",
    "_valid_version",
]
