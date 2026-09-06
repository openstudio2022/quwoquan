"""Derive and validate canonical object identity from task-init documents."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)
from core.schema import assert_valid
from core.source_digest import SourceDigestError, content_source_revision

_SHA256_PREFIX = "sha256:"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_FIELDS = (
    "sourceRevision",
    "sourceDigest",
    "entityCatalogDigest",
)
_INIT_INPUT_NAMES = ("carrierDemand", "immutableCandidateBindings")
_REQUEST_REF = "0.plan/request.json"
_TARGET_SET_REF = "0.plan/target_set.json"


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def _canonical_file_digest(value: object) -> str:
    return _SHA256_PREFIX + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_digest(path: Path) -> str:
    try:
        return _SHA256_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_IDENTITY_INVALID: unreadable bound input: {path}"
        ) from exc


def _digest(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SHA256.fullmatch(normalized):
        raise ObjectTransactionError(f"DATA.POOL.SOURCE_IDENTITY_INVALID: {label}")
    return normalized


def _binding(
    value: object, *, label: str, expected_ref: str | None = None
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise ObjectTransactionError(f"DATA.POOL.SOURCE_IDENTITY_INVALID: {label}")
    ref = _safe_rel(str(value.get("ref") or ""), label=f"{label}.ref").as_posix()
    if expected_ref is not None and ref != expected_ref:
        raise ObjectTransactionError(f"DATA.POOL.SOURCE_IDENTITY_INVALID: {label}.ref")
    return {"ref": ref, "digest": _digest(value.get("digest"), label=f"{label}.digest")}


def _init_binding(value: object, *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"scope", "ref", "digest"}:
        raise ObjectTransactionError(f"DATA.POOL.SOURCE_IDENTITY_INVALID: {label}")
    if value.get("scope") != "output":
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_IDENTITY_INVALID: {label}.scope"
        )
    return {
        "scope": "output",
        "ref": _safe_rel(str(value.get("ref") or ""), label=f"{label}.ref").as_posix(),
        "digest": _digest(value.get("digest"), label=f"{label}.digest"),
    }


def source_identity_digest(identity: Mapping[str, Any]) -> str:
    values = {
        field: str(identity.get(field) or "").strip() for field in _IDENTITY_FIELDS
    }
    if any(not _SHA256.fullmatch(value) for value in values.values()):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
    return _canonical_digest(
        {"schema": "quwoquan_data.object_source_identity", **values}
    )


def freeze_execution_source_identity(
    *,
    execution_root: Path,
    execution_manifest: Mapping[str, Any],
    target_ref: str,
) -> dict[str, str]:
    """Validate exact task-init bytes and derive one downstream identity."""

    manifest_path = execution_root / "execution_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: manifest missing"
        )
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: manifest unreadable"
        ) from exc
    if manifest_bytes != _canonical_bytes(execution_manifest):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: manifest exact bytes"
        )
    expected_manifest_fields = {
        "schema",
        "executionId",
        "carrier",
        "familyRef",
        "initInputs",
        "submittedInputs",
        "request",
        "targetSet",
        "retryOf",
    }
    if (
        set(execution_manifest) != expected_manifest_fields
        or execution_manifest.get("schema")
        != "quwoquan_data.content_execution_manifest"
    ):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: execution manifest fields"
        )

    execution_id = str(execution_manifest.get("executionId") or "").strip()
    carrier = str(execution_manifest.get("carrier") or "").strip()
    if not execution_id or execution_root.name != execution_id:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT: executionId")

    family = _binding(
        execution_manifest.get("familyRef"), label="executionManifest.familyRef"
    )
    request_binding = _binding(
        execution_manifest.get("request"),
        label="executionManifest.request",
        expected_ref=_REQUEST_REF,
    )
    target_binding = _binding(
        execution_manifest.get("targetSet"),
        label="executionManifest.targetSet",
        expected_ref=_TARGET_SET_REF,
    )
    raw_init_inputs = execution_manifest.get("initInputs")
    raw_submitted_inputs = execution_manifest.get("submittedInputs")
    if (
        not isinstance(raw_init_inputs, Mapping)
        or set(raw_init_inputs) != set(_INIT_INPUT_NAMES)
        or not isinstance(raw_submitted_inputs, Mapping)
        or set(raw_submitted_inputs) != set(_INIT_INPUT_NAMES)
    ):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: executionManifest init inputs"
        )
    init_inputs = {
        name: _init_binding(
            raw_init_inputs.get(name),
            label=f"executionManifest.initInputs.{name}",
        )
        for name in _INIT_INPUT_NAMES
    }

    from core.paths import FAMILIES_ROOT

    family_path = FAMILIES_ROOT.resolve() / _safe_rel(
        family["ref"], label="executionManifest.familyRef.ref"
    ).with_suffix(".recipe.yaml")
    try:
        family_path.resolve().relative_to(FAMILIES_ROOT.resolve())
    except (OSError, ValueError) as exc:
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: familyRef escapes families root"
        ) from exc
    if family_path.is_symlink() or not family_path.is_file():
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: family missing"
        )
    if _file_digest(family_path) != family["digest"]:
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: familyRef.digest"
        )

    request_path = execution_root / request_binding["ref"]
    target_path = execution_root / target_binding["ref"]
    if request_path.is_symlink() or not request_path.is_file():
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: request missing"
        )
    if target_path.is_symlink() or not target_path.is_file():
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: target set missing"
        )
    if _file_digest(request_path) != request_binding["digest"]:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT: request.digest")
    if _file_digest(target_path) != target_binding["digest"]:
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: targetSet.digest"
        )
    request = _read_json(request_path)
    target_set = _read_json(target_path)
    if request_path.read_bytes() != _canonical_bytes(request):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: request exact bytes"
        )
    if target_path.read_bytes() != _canonical_bytes(target_set):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: target set exact bytes"
        )
    expected_request_fields = {
        "schema",
        "executionId",
        "carrier",
        "familyRef",
        "quota",
        "candidateCount",
        "carrierDemand",
        "immutableCandidateBindings",
        "submittedInputs",
        "retryOf",
    }
    if (
        set(request) != expected_request_fields
        or request.get("schema") != "quwoquan_data.task_init_request"
    ):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_INVALID: task init request fields"
        )
    try:
        assert_valid(
            target_set, "execution", "target_set", label="publish object target set"
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_IDENTITY_INVALID: {exc}"
        ) from exc
    expected_common = {"executionId": execution_id, "carrier": carrier}
    if any(request.get(key) != value for key, value in expected_common.items()):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT: request binding")
    if any(target_set.get(key) != value for key, value in expected_common.items()):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: target set binding"
        )
    if request.get("familyRef") != family["ref"]:
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: request familyRef"
        )
    request_submitted_inputs = request.get("submittedInputs")
    if not isinstance(request_submitted_inputs, Mapping) or dict(
        request_submitted_inputs
    ) != dict(raw_submitted_inputs):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT: submittedInputs")
    for name in _INIT_INPUT_NAMES:
        if request.get(name) != init_inputs[name]:
            raise ObjectTransactionError(
                f"DATA.POOL.SOURCE_IDENTITY_DRIFT: request.{name}"
            )
        submitted = raw_submitted_inputs.get(name)
        if (
            not isinstance(submitted, Mapping)
            or _canonical_file_digest(submitted) != init_inputs[name]["digest"]
        ):
            raise ObjectTransactionError(
                f"DATA.POOL.SOURCE_IDENTITY_DRIFT: submittedInputs.{name}.digest"
            )
        target_candidate = target_set.get("candidateBinding")
        if name == "immutableCandidateBindings" and (
            not isinstance(target_candidate, Mapping)
            or {key: target_candidate.get(key) for key in ("scope", "ref", "digest")}
            != init_inputs[name]
        ):
            raise ObjectTransactionError(
                "DATA.POOL.SOURCE_IDENTITY_DRIFT: targetSet.candidateBinding"
            )

    submitted_demand = raw_submitted_inputs["carrierDemand"]
    submitted_candidates = raw_submitted_inputs["immutableCandidateBindings"]
    if (
        submitted_demand.get("executionId") != execution_id
        or submitted_demand.get("carrier") != carrier
        or submitted_demand.get("familyRef") != family["ref"]
        or submitted_demand.get("quota") != request.get("quota")
        or submitted_demand.get("retryOf")
        != (
            request.get("retryOf", {}).get("executionId")
            if isinstance(request.get("retryOf"), Mapping)
            else request.get("retryOf")
        )
        or submitted_candidates.get("executionId") != execution_id
        or submitted_candidates.get("carrier") != carrier
        or submitted_candidates.get("entityCatalogDigest")
        != target_set.get("entityCatalogDigest")
        or submitted_candidates.get("candidateCount") != request.get("candidateCount")
        or submitted_candidates.get("targets") != target_set.get("targets")
    ):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: submitted input semantics"
        )

    refs = target_set.get("targetRefs")
    count = target_set.get("targetCount")
    targets = target_set.get("targets")
    candidate_count = request.get("candidateCount")
    target_candidate = target_set.get("candidateBinding")
    normalized_target = str(target_ref or "").strip().strip("/")
    if (
        not isinstance(refs, list)
        or not refs
        or not isinstance(targets, list)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or not isinstance(target_candidate, Mapping)
        or count != len(refs)
        or count != len(targets)
        or candidate_count != count
        or target_candidate.get("candidateCount") != count
        or len(refs) != len(set(refs))
        or normalized_target not in refs
    ):
        raise ObjectTransactionError(
            "DATA.POOL.SOURCE_IDENTITY_DRIFT: target membership"
        )

    entity_catalog_digest = _digest(
        target_set.get("entityCatalogDigest"),
        label="targetSet.entityCatalogDigest",
    )
    source_digest = _canonical_digest(
        {
            "schema": "quwoquan_data.task_init_source_identity",
            "executionId": execution_id,
            "familyDigest": family["digest"],
            "requestDigest": request_binding["digest"],
            "targetSetDigest": target_binding["digest"],
            "initInputDigests": {
                name: init_inputs[name]["digest"] for name in _INIT_INPUT_NAMES
            },
        }
    )
    try:
        source_revision = content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID") from exc
    identity = {
        "executionId": execution_id,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    identity["identityDigest"] = source_identity_digest(identity)
    return identity


def validate_object_source_identity(
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    raw = manifest.get("sourceIdentity")
    if not isinstance(raw, Mapping):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_MISSING")
    required = {*_IDENTITY_FIELDS, "executionId", "identityDigest"}
    if set(raw) != required:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
    identity = {field: str(raw.get(field) or "").strip() for field in required}
    if identity["executionId"] != str(manifest.get("executionId") or "").strip():
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT: executionId")
    try:
        expected_revision = content_source_revision(
            source_digest=identity["sourceDigest"],
            entity_catalog_digest=identity["entityCatalogDigest"],
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID") from exc
    if (
        expected_revision != identity["sourceRevision"]
        or source_identity_digest(identity) != identity["identityDigest"]
    ):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT")
    return identity


def source_identity_set(
    identities: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, object]], str]:
    executions: dict[str, str] = {}
    grouped: dict[tuple[str, ...], set[str]] = {}
    for raw in identities:
        identity_digest = source_identity_digest(raw)
        execution_id = str(raw.get("executionId") or "").strip()
        if not execution_id:
            raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
        previous = executions.get(execution_id)
        if previous is not None and previous != identity_digest:
            raise ObjectTransactionError(
                f"DATA.POOL.SOURCE_IDENTITY_DRIFT: executionId={execution_id}"
            )
        executions[execution_id] = identity_digest
        key = tuple(str(raw[field]) for field in _IDENTITY_FIELDS)
        grouped.setdefault(key, set()).add(execution_id)
    if not grouped:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_MISSING")
    rows: list[dict[str, object]] = []
    for key, execution_ids in sorted(grouped.items()):
        rows.append(
            {
                "sourceRevision": key[0],
                "sourceDigest": key[1],
                "entityCatalogDigest": key[2],
                "executionIds": sorted(execution_ids),
            }
        )
    set_digest = _canonical_digest(
        {"schema": "quwoquan_data.source_identity_set", "sourceIdentities": rows}
    )
    return rows, set_digest


__all__ = [
    "freeze_execution_source_identity",
    "source_identity_digest",
    "source_identity_set",
    "validate_object_source_identity",
]
