"""Validate and read one append-only canonical pool record ledger."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.release.canonical.object_source_identity import source_identity_digest
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)

POOL_RECORD_SCHEMA = "quwoquan_data.pool_object_record"
POOL_OBJECT_TYPES = {"author", "homepage", "content"}
POOL_RESULT_VALUES = {"completed", "failed"}
POOL_QUALITY_VALUES = {"passed", "failed"}
POOL_ELIGIBILITY_VALUES = {"passed", "pending", "failed"}


@dataclass(frozen=True, slots=True)
class PoolRecordExclusion:
    """One historical record that is not part of effective pool truth."""

    record_ref: str
    record_sequence: int
    reason: str
    superseded_by: int | None


@dataclass(frozen=True, slots=True)
class PoolRecordHistory:
    """Validated records plus explicit exclusions from one append-only ledger."""

    records: tuple[dict[str, Any], ...]
    exclusions: tuple[PoolRecordExclusion, ...]


def pool_source_identity_digest(identity: Mapping[str, Any]) -> str:
    """Digest the execution-bound source identity tuple."""

    if not str(identity.get("executionId") or "").strip():
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
    return source_identity_digest(identity)


def _validated_pool_record(
    raw: Mapping[str, Any],
    *,
    object_type: str | None = None,
) -> dict[str, Any]:
    record = dict(raw)
    if record.get("schema") != POOL_RECORD_SCHEMA:
        raise ObjectTransactionError("DATA.POOL.RECORD_SCHEMA_INVALID")
    actual_type = str(record.get("objectType") or "").strip()
    if actual_type not in POOL_OBJECT_TYPES or (
        object_type is not None and actual_type != object_type
    ):
        raise ObjectTransactionError(
            f"DATA.POOL.RECORD_OBJECT_TYPE_INVALID: {actual_type!r}"
        )
    if "recordSequence" not in record and "contentVersion" not in record:
        raise ObjectTransactionError("DATA.POOL.RECORD_SEQUENCE_MISSING")
    record_sequence = record.get("recordSequence")
    content_version = record.get("contentVersion")
    if (
        not isinstance(record_sequence, int)
        or isinstance(record_sequence, bool)
        or record_sequence < 1
        or not isinstance(content_version, int)
        or isinstance(content_version, bool)
        or content_version < 1
    ):
        raise ObjectTransactionError("DATA.POOL.RECORD_VERSION_INVALID")
    for key in ("objectId", "objectRef", "evidenceRef"):
        if not str(record.get(key) or "").strip():
            raise ObjectTransactionError(f"DATA.POOL.RECORD_FIELD_MISSING: {key}")
    for key in ("evidenceDigest", "payloadDigest"):
        digest = str(record.get(key) or "")
        if len(digest) != 71 or not digest.startswith("sha256:"):
            raise ObjectTransactionError(
                f"DATA.POOL.RECORD_DIGEST_INVALID: {key}"
            )
    if record.get("processResult") not in POOL_RESULT_VALUES:
        raise ObjectTransactionError("DATA.POOL.RECORD_PROCESS_INVALID")
    if record.get("qualityResult") not in POOL_QUALITY_VALUES:
        raise ObjectTransactionError("DATA.POOL.RECORD_QUALITY_INVALID")
    if actual_type != "author":
        if record.get("rightsResult") != "passed":
            raise ObjectTransactionError("DATA.POOL.RECORD_RIGHTS_INVALID")
        if not str(record.get("rightsAuthorityRef") or "").strip():
            raise ObjectTransactionError("DATA.POOL.RECORD_RIGHTS_AUTHORITY_MISSING")
        rights_digest = str(record.get("rightsAuthorityDigest") or "")
        if len(rights_digest) != 71 or not rights_digest.startswith("sha256:"):
            raise ObjectTransactionError("DATA.POOL.RECORD_RIGHTS_AUTHORITY_DIGEST_INVALID")
    eligibility = record.get("eligibilityResult")
    if eligibility not in POOL_ELIGIBILITY_VALUES:
        raise ObjectTransactionError("DATA.POOL.RECORD_ELIGIBILITY_INVALID")
    usage_scope = record.get("usageScope")
    if actual_type == "author":
        if usage_scope is not None:
            raise ObjectTransactionError("DATA.POOL.AUTHOR_SCOPE_FORBIDDEN")
    elif eligibility == "passed":
        if usage_scope not in {"research", "commercial"}:
            raise ObjectTransactionError("DATA.POOL.RECORD_USAGE_SCOPE_INVALID")
    elif usage_scope is not None:
        raise ObjectTransactionError("DATA.POOL.PENDING_SCOPE_MUST_BE_NULL")
    if record.get("status") not in {"active", "retired", "deleted"}:
        raise ObjectTransactionError("DATA.POOL.RECORD_STATUS_INVALID")
    if actual_type in {"homepage", "content"}:
        source_identity = record.get("sourceIdentity")
        source_attribution = record.get("sourceAttribution")
        canonical_digest = str(record.get("canonicalObjectDigest") or "")
        expected_identity_fields = {
            "executionId",
            "sourceRevision",
            "sourceDigest",
            "entityCatalogDigest",
            "identityDigest",
        }
        if (
            not isinstance(source_identity, Mapping)
            or set(source_identity) != expected_identity_fields
            or pool_source_identity_digest(source_identity)
            != source_identity.get("identityDigest")
        ):
            raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
        if not source_attribution_complete(
            {"sourceAttribution": source_attribution}
        ):
            raise ObjectTransactionError(
                "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE"
            )
        if canonical_digest != record.get("payloadDigest"):
            raise ObjectTransactionError("DATA.POOL.CANONICAL_DIGEST_DRIFT")
    return record


def _record_error_code(exc: ObjectTransactionError) -> str:
    return str(exc).split(":", 1)[0]


_PRE_RIGHTS_RECORD_FIELDS = frozenset(
    {
        "schema",
        "objectType",
        "objectId",
        "objectRef",
        "recordSequence",
        "contentVersion",
        "status",
        "processResult",
        "qualityResult",
        "eligibilityResult",
        "usageScope",
        "evidenceRef",
        "evidenceDigest",
        "payloadDigest",
        "canonicalObjectDigest",
        "sourceIdentity",
        "sourceAttribution",
    }
)


def _is_pre_rights_pool_record(
    raw: Mapping[str, Any],
    *,
    object_type: str | None = None,
) -> bool:
    """Recognize the exact valid contract that predates rights fields.

    This classification is only for collision-identity reservation. It never
    turns the historical record into admission or supplies rights from a
    manifest.
    """

    actual_type = str(raw.get("objectType") or "").strip()
    rights_fields = (
        "rightsResult",
        "rightsAuthorityRef",
        "rightsAuthorityDigest",
    )
    if (
        actual_type not in {"homepage", "content"}
        or set(raw) != _PRE_RIGHTS_RECORD_FIELDS
        or any(field in raw for field in rights_fields)
    ):
        return False
    candidate = dict(raw)
    candidate.update(
        rightsResult="passed",
        rightsAuthorityRef="historical-rights-contract-validation",
        rightsAuthorityDigest="sha256:" + "0" * 64,
    )
    try:
        _validated_pool_record(candidate, object_type=object_type)
    except ObjectTransactionError:
        return False
    return True


def _physical_record_sequence(path: Path) -> int:
    raw = path.stem
    if not raw.isdigit() or raw.startswith("0"):
        raise ObjectTransactionError(
            f"DATA.POOL.RECORD_SEQUENCE_CONFLICT: {path.as_posix()}"
        )
    value = int(raw)
    if value < 1:
        raise ObjectTransactionError(
            f"DATA.POOL.RECORD_SEQUENCE_CONFLICT: {path.as_posix()}"
        )
    return value


def _is_explicit_retired_record(
    raw: Mapping[str, Any],
    *,
    physical_sequence: int,
    reason: str,
) -> bool:
    """Recognize only the retired, explicit ``version`` ledger contract."""

    version = raw.get("version")
    return bool(
        reason == "DATA.POOL.RECORD_SEQUENCE_MISSING"
        and "recordSequence" not in raw
        and "contentVersion" not in raw
        and isinstance(version, int)
        and not isinstance(version, bool)
        and version == physical_sequence
    )


def _validate_retired_supersession(
    *,
    raw: Mapping[str, Any],
    successor: Mapping[str, Any],
    physical_sequence: int,
) -> None:
    """Require a later record to be an exact field-contract repair."""

    identity_fields = ("schema", "objectType", "objectId", "objectRef")
    if any(raw.get(key) != successor.get(key) for key in identity_fields):
        raise ObjectTransactionError(
            "DATA.POOL.RECORD_IDENTITY_CONFLICT: "
            f"retiredSequence={physical_sequence}"
        )
    if successor.get("contentVersion") != raw.get("version"):
        raise ObjectTransactionError(
            "DATA.POOL.RECORD_VERSION_CONFLICT: "
            f"retiredSequence={physical_sequence}"
        )
    digest_fields = ("evidenceDigest", "payloadDigest")
    if any(raw.get(key) != successor.get(key) for key in digest_fields):
        raise ObjectTransactionError(
            "DATA.POOL.RECORD_DIGEST_CONFLICT: "
            f"retiredSequence={physical_sequence}"
        )
    retired_payload = {
        key: value for key, value in raw.items() if key != "version"
    }
    successor_payload = {
        key: value
        for key, value in successor.items()
        if key not in {"recordSequence", "contentVersion"}
    }
    if retired_payload != successor_payload:
        raise ObjectTransactionError(
            "DATA.POOL.RECORD_SUPERSESSION_CONFLICT: "
            f"retiredSequence={physical_sequence}"
        )


def read_pool_record_history(
    object_root: Path,
    *,
    object_type: str | None = None,
) -> PoolRecordHistory:
    """Read one ledger without allowing an invalid record to become admission.

    The retired explicit ``version`` shape can be superseded only by an exact
    metadata repair. A valid pre-rights contract is kept as a typed exclusion
    for collision-only consumers, but remains blocking here and in direct
    admission. Other malformed records and integrity conflicts also block.
    """

    versions_root = object_root / "_pool" / "versions"
    if not versions_root.is_dir():
        return PoolRecordHistory(records=(), exclusions=())
    paths = [
        path for path in versions_root.glob("*.json") if path.is_file()
    ]
    indexed_paths = sorted(
        ((_physical_record_sequence(path), path) for path in paths),
        key=lambda item: item[0],
    )
    records: list[dict[str, Any]] = []
    invalid: list[tuple[int, Path, dict[str, Any], str]] = []
    for physical_sequence, path in indexed_paths:
        raw = _read_json(path)
        try:
            record = _validated_pool_record(raw, object_type=object_type)
        except ObjectTransactionError as exc:
            invalid.append(
                (physical_sequence, path, raw, _record_error_code(exc))
            )
            continue
        if int(record["recordSequence"]) != physical_sequence:
            raise ObjectTransactionError(
                "DATA.POOL.RECORD_SEQUENCE_CONFLICT: "
                f"pathSequence={physical_sequence} "
                f"recordSequence={record['recordSequence']}"
            )
        records.append(record)
    records.sort(key=lambda item: int(item["recordSequence"]))
    exclusions: list[PoolRecordExclusion] = []
    for physical_sequence, path, raw, reason in invalid:
        successor = next(
            (
                record
                for record in records
                if int(record["recordSequence"]) > physical_sequence
            ),
            None,
        )
        if successor is not None and _is_explicit_retired_record(
            raw,
            physical_sequence=physical_sequence,
            reason=reason,
        ):
            _validate_retired_supersession(
                raw=raw,
                successor=successor,
                physical_sequence=physical_sequence,
            )
            superseded_by: int | None = int(successor["recordSequence"])
        else:
            superseded_by = None
        exclusions.append(
            PoolRecordExclusion(
                record_ref=path.relative_to(object_root).as_posix(),
                record_sequence=physical_sequence,
                reason=reason,
                superseded_by=superseded_by,
            )
        )
    return PoolRecordHistory(
        records=tuple(records),
        exclusions=tuple(exclusions),
    )


def iter_pool_records(
    object_root: Path,
    *,
    object_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return canonical records; never infer admission from excluded history."""

    history = read_pool_record_history(object_root, object_type=object_type)
    blocking = [
        exclusion
        for exclusion in history.exclusions
        if exclusion.superseded_by is None
    ]
    if blocking:
        raise ObjectTransactionError(
            f"{blocking[0].reason}: {blocking[0].record_ref}"
        )
    return list(history.records)


__all__ = [
    "POOL_RECORD_SCHEMA",
    "PoolRecordExclusion",
    "PoolRecordHistory",
    "iter_pool_records",
    "pool_source_identity_digest",
    "read_pool_record_history",
]
