"""Governed SourceAttribution repair from one physical source-ready pool."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    append_pool_record,
    iter_pool_records,
    pool_payload_digest,
)
from content.release.canonical.object_source_identity import (
    validate_object_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _read_json,
    _safe_rel,
)
from content.release.canonical.pool_backfill_canonical import (
    build_pool_record,
    object_evidence,
    rights_rows,
    usage_scope,
)
from content.source.research.scale_source_pool import (
    validate_scale_source_pool_evidence,
)
from core.schema import assert_valid
from core.source_attribution import canonical_source_attribution

_CARRIERS_BY_OBJECT_TYPE = {
    "homepage": {"homepage"},
    "content": {"article", "image", "video"},
}


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _exact_output_path(output_root: Path, raw_ref: object, *, label: str) -> Path:
    relative = Path(str(raw_ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ObjectTransactionError(f"{label} must be one exact output ref")
    root = output_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ObjectTransactionError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
    if any(
        (root / Path(*relative.parts[:index])).is_symlink()
        for index in range(1, len(relative.parts) + 1)
    ):
        raise ObjectTransactionError(f"{label} contains a symlink")
    return path


def _validate_bindings(path: Path) -> list[dict[str, Any]]:
    document = _read_json(path)
    try:
        assert_valid(
            document,
            "release",
            "pool_attribution_repair_bindings",
            label="pool attribution repair bindings",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    expected = _digest_json(
        {key: value for key, value in document.items() if key != "bindingsDigest"}
    )
    if document.get("bindingsDigest") != expected:
        raise ObjectTransactionError("DATA.POOL.REPAIR_BINDINGS_DIGEST_DRIFT")
    return [dict(row) for row in document["items"]]


def _pool_candidates(
    *,
    output_root: Path,
    source_pool_ref: str,
    evidence_root_ref: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    pool_path = _exact_output_path(
        output_root, source_pool_ref, label="sourcePoolRef"
    )
    evidence_root = _exact_output_path(
        output_root, evidence_root_ref, label="sourcePoolEvidenceRootRef"
    )
    if not pool_path.is_file() or not evidence_root.is_dir():
        raise ObjectTransactionError("DATA.POOL.REPAIR_SOURCE_POOL_MISSING")
    plan = _read_json(pool_path)
    try:
        validation = validate_scale_source_pool_evidence(
            plan,
            evidence_root=evidence_root,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.REPAIR_SOURCE_POOL_INVALID: {exc}"
        ) from exc
    rows = [dict(row) for row in plan.get("candidates") or []]
    by_id = {str(row.get("candidateId") or ""): row for row in rows}
    if "" in by_id or len(by_id) != len(rows):
        raise ObjectTransactionError("DATA.POOL.REPAIR_CANDIDATE_ID_CONFLICT")
    return by_id, {
        "sourcePoolRef": Path(source_pool_ref).as_posix(),
        "sourcePoolFileSha256": _digest_file(pool_path),
        "sourcePoolDigest": str(plan.get("planDigest") or ""),
        "sourcePoolEvidenceRootRef": Path(evidence_root_ref).as_posix(),
        "evidenceBindingCount": str(validation["evidenceBindingCount"]),
    }


def _object_root(
    publish_root: Path, *, object_type: str, object_ref: str
) -> Path:
    relative = _safe_rel(object_ref, label="repair.objectRef")
    kind = "entities" if object_type == "homepage" else "posts"
    root = publish_root / kind / relative
    if root.is_symlink() or not (root / "manifest.json").is_file():
        raise ObjectTransactionError("DATA.POOL.REPAIR_OBJECT_MISSING")
    return root


def _repair_item(
    *,
    publish_root: Path,
    binding: Mapping[str, Any],
    candidate: Mapping[str, Any],
    source_binding: Mapping[str, str],
) -> dict[str, Any]:
    object_type = str(binding["objectType"])
    object_ref = str(binding["objectRef"])
    if str(candidate.get("carrier") or "") not in _CARRIERS_BY_OBJECT_TYPE[object_type]:
        raise ObjectTransactionError("DATA.POOL.REPAIR_CARRIER_MISMATCH")
    kind = "entities" if object_type == "homepage" else "posts"
    if str(candidate.get("objectRef") or "").strip("/") != f"{kind}/{object_ref}":
        raise ObjectTransactionError("DATA.POOL.REPAIR_OBJECT_BINDING_DRIFT")
    root = _object_root(
        publish_root, object_type=object_type, object_ref=object_ref
    )
    payload_digest = pool_payload_digest(root)
    if payload_digest != binding.get("canonicalObjectDigest"):
        raise ObjectTransactionError("DATA.POOL.REPAIR_OBJECT_DIGEST_DRIFT")
    attribution = canonical_source_attribution(candidate.get("sourceAttribution"))
    manifest = _read_json(root / "manifest.json")
    old_records = iter_pool_records(root, object_type=object_type)
    latest = old_records[-1] if old_records else None
    identity_key = "entityId" if object_type == "homepage" else "contentId"
    object_id = str(
        manifest.get(identity_key) or (latest or {}).get("objectId") or ""
    ).strip()
    content_version = manifest.get("version") or (latest or {}).get(
        "contentVersion"
    )
    if (
        not object_id
        or not isinstance(content_version, int)
        or isinstance(content_version, bool)
        or content_version < 1
    ):
        raise ObjectTransactionError("DATA.POOL.IDENTITY_INVALID")
    passed, evidence_path = object_evidence(root)
    if not passed or evidence_path is None:
        raise ObjectTransactionError("DATA.POOL.QUALITY_EVIDENCE_FAILED")
    eligibility, selected_scope, reason = usage_scope(manifest, rights_rows(root))
    if eligibility != "passed":
        raise ObjectTransactionError(
            reason or "DATA.POOL.ELIGIBILITY_EVIDENCE_PENDING"
        )
    evidence_digest = _digest_file(evidence_path)
    identity = validate_object_source_identity(manifest)
    sequence = int(latest["recordSequence"]) + 1 if latest else 1
    record = build_pool_record(
        object_type=object_type,
        object_id=object_id,
        object_ref=object_ref,
        record_sequence=sequence,
        content_version=content_version,
        process_result="completed",
        quality_result="passed",
        eligibility_result="passed",
        usage_scope=selected_scope,
        evidence_ref=evidence_path.relative_to(root).as_posix(),
        evidence_digest=evidence_digest,
        payload_digest=payload_digest,
        source_identity=identity,
        source_attribution=attribution,
    )
    if latest is not None:
        replay = {**record, "recordSequence": latest["recordSequence"]}
        if dict(latest) != replay:
            raise ObjectTransactionError("DATA.POOL.REPAIR_MIGRATION_COLLISION")
        record = replay
    repair_evidence = {
        **source_binding,
        "candidateId": str(candidate["candidateId"]),
        "candidateDigest": _digest_json(candidate),
        "canonicalObjectDigest": payload_digest,
    }
    return {
        "itemId": f"repair:{object_type}:{object_id}:{content_version}",
        "record": record,
        "repairEvidence": repair_evidence,
    }


def repair_pool_attribution(
    *,
    publish_root: Path,
    output_root: Path,
    bindings_path: Path,
    source_pool_ref: str,
    evidence_root_ref: str,
    apply: bool = False,
) -> dict[str, Any]:
    """Plan or append exact repairs; never derive attribution at read time."""

    bindings = _validate_bindings(bindings_path)
    candidates, source_binding = _pool_candidates(
        output_root=output_root,
        source_pool_ref=source_pool_ref,
        evidence_root_ref=evidence_root_ref,
    )
    items: list[dict[str, Any]] = []
    for binding in bindings:
        candidate_id = str(binding["candidateId"])
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise ObjectTransactionError("DATA.POOL.REPAIR_CANDIDATE_MISSING")
        items.append(
            _repair_item(
                publish_root=publish_root,
                binding=binding,
                candidate=candidate,
                source_binding=source_binding,
            )
        )
    results: list[dict[str, Any]] = []
    for item in items:
        record = item["record"]
        root = _object_root(
            publish_root,
            object_type=str(record["objectType"]),
            object_ref=str(record["objectRef"]),
        )
        status = "ready"
        if apply:
            status, _path = append_pool_record(object_root=root, record=record)
        results.append(
            {
                "itemId": item["itemId"],
                "objectId": record["objectId"],
                "contentVersion": record["contentVersion"],
                "recordSequence": record["recordSequence"],
                "status": status,
            }
        )
    batch = {
        "schema": "quwoquan_data.pool_attribution_repair_batch",
        "sourceBinding": source_binding,
        "items": items,
    }
    batch["batchDigest"] = _digest_json(batch)
    return {
        "schema": "quwoquan_data.pool_attribution_repair_result",
        "mode": "apply" if apply else "plan",
        "result": "ready",
        "count": len(items),
        "batch": batch,
        "items": results,
    }


__all__ = ["repair_pool_attribution"]
