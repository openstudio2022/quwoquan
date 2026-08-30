"""Single typed query for the effective identity of one canonical object."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import pool_payload_digest
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_bytes,
    _digest_file,
    _json_bytes,
    _read_json,
    _safe_rel,
)
from content.release.canonical.pool_record_history import read_pool_record_history
from core.schema import assert_valid

_PROJECTION_SCHEMA = "quwoquan_data.canonical_identity_state_projection"


def _error_code(exc: BaseException) -> str:
    code = str(exc).split(":", 1)[0].strip()
    return code if code.startswith("DATA.") else "DATA.POOL.IDENTITY_INVALID"


def _canonical_location(
    *, publish_root: Path, object_type: str, object_ref: str
) -> tuple[str, Path]:
    if object_type not in {"homepage", "content"}:
        raise ObjectTransactionError("DATA.POOL.RECORD_OBJECT_TYPE_INVALID")
    prefix = "entities" if object_type == "homepage" else "posts"
    raw_ref = str(object_ref or "").strip().strip("/")
    if raw_ref == prefix or raw_ref.startswith(f"{prefix}/"):
        raw_ref = raw_ref.removeprefix(f"{prefix}/")
    relative = _safe_rel(raw_ref, label="canonicalIdentity.objectRef")
    canonical_ref = f"{prefix}/{relative.as_posix()}"
    return canonical_ref, publish_root / prefix / relative


def _snapshot_token(object_root: Path, *, canonical_ref: str) -> str:
    rows: list[dict[str, Any]] = []
    if object_root.exists():
        if object_root.is_symlink() or not object_root.is_dir():
            raise ObjectTransactionError("DATA.POOL.IDENTITY_STORAGE_INVALID")
        for path in sorted(object_root.rglob("*")):
            if path.is_symlink():
                raise ObjectTransactionError("DATA.POOL.IDENTITY_STORAGE_INVALID")
            if path.is_file():
                rows.append(
                    {
                        "ref": path.relative_to(object_root).as_posix(),
                        "sha256": _digest_file(path),
                        "bytes": path.stat().st_size,
                    }
                )
    return _digest_bytes(
        _json_bytes(
            {
                "canonicalRef": canonical_ref,
                "objectPresent": object_root.is_dir(),
                "files": rows,
            }
        )
    )


def _latest_terminal_fact(object_root: Path) -> tuple[dict[str, Any], str] | None:
    terminal_root = object_root / "_pool/terminal"
    if not terminal_root.is_dir():
        return None
    indexed: list[tuple[int, Path]] = []
    for path in terminal_root.glob("*.json"):
        if not path.is_file() or not path.stem.isdigit() or path.stem.startswith("0"):
            raise ObjectTransactionError("DATA.POOL.TERMINAL_SEQUENCE_CONFLICT")
        indexed.append((int(path.stem), path))
    if not indexed:
        return None
    sequence, path = max(indexed, key=lambda row: row[0])
    fact = _read_json(path)
    assert_valid(
        fact,
        "release",
        "canonical_identity_terminal_fact",
        label="canonical identity terminal fact",
    )
    if fact.get("recordSequence") != sequence:
        raise ObjectTransactionError("DATA.POOL.TERMINAL_SEQUENCE_CONFLICT")
    return fact, path.relative_to(object_root).as_posix()


def _manifest_identity(
    manifest: Mapping[str, Any], *, object_type: str
) -> tuple[str | None, int | None]:
    key = "entityId" if object_type == "homepage" else "contentId"
    object_id = str(manifest.get(key) or "").strip() or None
    version = manifest.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        version = None
    return object_id, version


def _latest_physical_record_sequence(object_root: Path) -> int | None:
    versions_root = object_root / "_pool/versions"
    if not versions_root.is_dir():
        return None
    sequences = [
        int(path.stem)
        for path in versions_root.glob("*.json")
        if path.is_file() and path.stem.isdigit() and not path.stem.startswith("0")
    ]
    return max(sequences) if sequences else None


def _evidence_is_current(object_root: Path, record: Mapping[str, Any]) -> bool:
    try:
        evidence = object_root / _safe_rel(
            str(record.get("evidenceRef") or ""),
            label="canonicalIdentity.evidenceRef",
        )
    except ObjectTransactionError:
        return False
    return bool(
        not evidence.is_symlink()
        and evidence.is_file()
        and _digest_file(evidence) == record.get("evidenceDigest")
    )


def _payload_rebuild_evidence_is_current(
    object_root: Path, manifest: Mapping[str, Any]
) -> bool:
    admission = manifest.get("admission")
    if not isinstance(admission, Mapping) or not _evidence_is_current(
        object_root, admission
    ):
        return False
    rights_ref = str(manifest.get("rightsRef") or "").strip()
    creator_refs_ref = str(manifest.get("creatorRefsRef") or "").strip()
    try:
        rights = object_root / _safe_rel(
            rights_ref, label="canonicalIdentity.rightsRef"
        )
        creators = object_root / _safe_rel(
            creator_refs_ref, label="canonicalIdentity.creatorRefsRef"
        )
    except ObjectTransactionError:
        return False
    return bool(
        rights.is_file()
        and not rights.is_symlink()
        and creators.is_file()
        and not creators.is_symlink()
    )


def _invalid_state(
    *,
    object_root: Path,
    manifest: Mapping[str, Any],
    record: Mapping[str, Any],
    error: str,
) -> tuple[str, str]:
    _object_id, manifest_version = _manifest_identity(
        manifest,
        object_type=str(record["objectType"]),
    )
    record_version = int(record["contentVersion"])
    if (
        error == "DATA.POOL.PAYLOAD_DIGEST_DRIFT"
        and manifest_version == record_version
        and _evidence_is_current(object_root, record)
    ):
        return "invalid_record_repairable", "record_repair"
    if (
        error == "DATA.POOL.PAYLOAD_DIGEST_DRIFT"
        and manifest_version == record_version + 1
        and _payload_rebuild_evidence_is_current(object_root, manifest)
    ):
        return "invalid_payload_rebuildable", "payload_rebuild"
    return "invalid_unrepairable", "terminate"


class CanonicalIdentityStateQuery:
    """Read the only canonical identity state projection without mutation."""

    def __init__(self, *, publish_root: Path) -> None:
        self._publish_root = publish_root.resolve()

    def get(self, *, object_type: str, object_ref: str) -> dict[str, Any]:
        canonical_ref, object_root = _canonical_location(
            publish_root=self._publish_root,
            object_type=object_type,
            object_ref=object_ref,
        )
        snapshot_token = _snapshot_token(
            object_root,
            canonical_ref=canonical_ref,
        )
        manifest_path = object_root / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            return self._validated(
                object_type=object_type,
                object_ref=canonical_ref,
                object_id=None,
                state="absent",
                deepest_error=None,
                recovery_action=None,
                snapshot_token=snapshot_token,
                content_version=None,
                record_sequence=None,
                terminal_fact=None,
            )
        manifest = _read_json(manifest_path)
        object_id, manifest_version = _manifest_identity(
            manifest,
            object_type=object_type,
        )
        terminal = _latest_terminal_fact(object_root)
        if terminal is not None:
            fact, terminal_ref = terminal
            if (
                fact.get("objectType") != object_type
                or fact.get("objectRef") != canonical_ref
                or fact.get("objectId") != object_id
            ):
                raise ObjectTransactionError("DATA.POOL.TERMINAL_IDENTITY_DRIFT")
            return self._validated(
                object_type=object_type,
                object_ref=canonical_ref,
                object_id=object_id,
                state="terminated",
                deepest_error="DATA.POOL.IDENTITY_TERMINATED",
                recovery_action=None,
                snapshot_token=snapshot_token,
                content_version=int(fact["contentVersion"]),
                record_sequence=int(fact["recordSequence"]),
                terminal_fact={
                    "ref": terminal_ref,
                    "terminalReason": str(fact["terminalReason"]),
                    "nextAction": str(fact["nextAction"]),
                },
            )
        try:
            history = read_pool_record_history(
                object_root,
                object_type=object_type,
            )
        except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
            raise ObjectTransactionError(_error_code(exc)) from exc
        blocking = [
            row for row in history.exclusions if row.superseded_by is None
        ]
        if blocking:
            record_sequence = _latest_physical_record_sequence(object_root)
            if (
                object_id is not None
                and manifest_version is not None
                and record_sequence is not None
            ):
                return self._validated(
                    object_type=object_type,
                    object_ref=canonical_ref,
                    object_id=object_id,
                    state="invalid_unrepairable",
                    deepest_error=blocking[0].reason,
                    recovery_action={
                        "command": "resolve_invalid_canonical_identity",
                        "action": "terminate",
                    },
                    snapshot_token=snapshot_token,
                    content_version=manifest_version,
                    record_sequence=record_sequence,
                    terminal_fact=None,
                )
            raise ObjectTransactionError(blocking[0].reason)
        if not history.records:
            if (
                object_id is not None
                and manifest_version is not None
                and isinstance(manifest.get("admission"), Mapping)
                and _evidence_is_current(object_root, manifest["admission"])
            ):
                return self._validated(
                    object_type=object_type,
                    object_ref=canonical_ref,
                    object_id=object_id,
                    state="invalid_record_repairable",
                    deepest_error="DATA.POOL.EXPLICIT_ADMISSION_MISSING",
                    recovery_action={
                        "command": "resolve_invalid_canonical_identity",
                        "action": "record_repair",
                    },
                    snapshot_token=snapshot_token,
                    content_version=manifest_version,
                    record_sequence=1,
                    terminal_fact=None,
                )
            return self._validated(
                object_type=object_type,
                object_ref=canonical_ref,
                object_id=None,
                state="absent",
                deepest_error=None,
                recovery_action=None,
                snapshot_token=snapshot_token,
                content_version=None,
                record_sequence=None,
                terminal_fact=None,
            )
        record = history.records[-1]
        deepest_error: str | None = None
        if (
            not object_id
            or record.get("objectId") != object_id
            or record.get("objectRef") != canonical_ref.split("/", 1)[1]
        ):
            deepest_error = "DATA.POOL.IDENTITY_INVALID"
        elif record.get("payloadDigest") != pool_payload_digest(object_root):
            deepest_error = "DATA.POOL.PAYLOAD_DIGEST_DRIFT"
        elif not _evidence_is_current(object_root, record):
            deepest_error = "DATA.POOL.EVIDENCE_DIGEST_DRIFT"
        if deepest_error is None:
            return self._validated(
                object_type=object_type,
                object_ref=canonical_ref,
                object_id=object_id,
                state="admitted_current",
                deepest_error=None,
                recovery_action=None,
                snapshot_token=snapshot_token,
                content_version=int(record["contentVersion"]),
                record_sequence=int(record["recordSequence"]),
                terminal_fact=None,
            )
        state, action = _invalid_state(
            object_root=object_root,
            manifest=manifest,
            record=record,
            error=deepest_error,
        )
        return self._validated(
            object_type=object_type,
            object_ref=canonical_ref,
            object_id=object_id or str(record["objectId"]),
            state=state,
            deepest_error=deepest_error,
            recovery_action={
                "command": "resolve_invalid_canonical_identity",
                "action": action,
            },
            snapshot_token=snapshot_token,
            content_version=int(record["contentVersion"]),
            record_sequence=int(record["recordSequence"]),
            terminal_fact=None,
        )

    @staticmethod
    def _validated(
        *,
        object_type: str,
        object_ref: str,
        object_id: str | None,
        state: str,
        deepest_error: str | None,
        recovery_action: Mapping[str, Any] | None,
        snapshot_token: str,
        content_version: int | None,
        record_sequence: int | None,
        terminal_fact: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        projection = {
            "schema": _PROJECTION_SCHEMA,
            "objectType": object_type,
            "objectId": object_id,
            "objectRef": object_ref,
            "state": state,
            "deepestError": deepest_error,
            "recoveryAction": (
                dict(recovery_action) if recovery_action is not None else None
            ),
            "optimisticSnapshotToken": snapshot_token,
            "contentVersion": content_version,
            "recordSequence": record_sequence,
            "terminalFact": dict(terminal_fact) if terminal_fact is not None else None,
        }
        assert_valid(
            projection,
            "release",
            "canonical_identity_state_projection",
            label="canonical identity state projection",
        )
        return projection


def query_canonical_identity_state(
    *, publish_root: Path, object_type: str, object_ref: str
) -> dict[str, Any]:
    return CanonicalIdentityStateQuery(publish_root=publish_root).get(
        object_type=object_type,
        object_ref=object_ref,
    )


def canonical_identity_is_consumed(state: Mapping[str, Any]) -> bool:
    """Only current admission and explicit termination leave source backlog."""

    value = str(state.get("state") or "")
    if value not in {
        "absent",
        "admitted_current",
        "invalid_record_repairable",
        "invalid_payload_rebuildable",
        "invalid_unrepairable",
        "terminated",
    }:
        raise ObjectTransactionError("DATA.POOL.IDENTITY_STATE_INVALID")
    return value in {"admitted_current", "terminated"}


__all__ = [
    "CanonicalIdentityStateQuery",
    "canonical_identity_is_consumed",
    "query_canonical_identity_state",
]
