"""快照加载与快照派生证据：source/target snapshot、inventory、PII 报告。

内容逐字来自原 ``control_plane.py``。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _load_object,
    _parse_timestamp,
    _require_digest,
    _require_nonblank,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    EMAIL_RE,
    IDENTITY_KEY_RE,
    PHONE_RE,
    SENSITIVE_KEY_RE,
    SOURCE_OBJECT_TYPES,
    SOURCE_SNAPSHOT_SCHEMA,
    SOURCE_STATUS_VALUES,
    TARGET_SNAPSHOT_SCHEMA,
    MigrationControlError,
)


def _snapshot_digest(payload: Mapping[str, Any]) -> str:
    stable = dict(payload)
    stable.pop("snapshotDigest", None)
    return canonical_digest(stable)


def load_source_snapshot(
    path: Path,
    *,
    environment: str,
    target_contract_digest: str,
) -> dict[str, Any]:
    payload = _load_object(path, label="travel source snapshot")
    required = {
        "schema",
        "environment",
        "capturedAt",
        "source",
        "targetContractDigest",
        "objects",
        "bindings",
        "snapshotDigest",
    }
    if set(payload) != required:
        raise MigrationControlError(
            "SOURCE_SNAPSHOT_INVALID",
            "travel source snapshot fields must be exactly: "
            + ", ".join(sorted(required)),
        )
    if payload.get("schema") != SOURCE_SNAPSHOT_SCHEMA:
        raise MigrationControlError(
            "SOURCE_SNAPSHOT_INVALID",
            f"travel source snapshot schema must be {SOURCE_SNAPSHOT_SCHEMA}",
        )
    if payload.get("environment") != environment:
        raise MigrationControlError(
            "SOURCE_SNAPSHOT_ENV_MISMATCH",
            "travel source snapshot environment does not match --env",
        )
    _parse_timestamp(payload.get("capturedAt"), label="capturedAt")
    declared_target_digest = _require_digest(
        payload.get("targetContractDigest"),
        label="targetContractDigest",
    )
    if declared_target_digest != target_contract_digest:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISMATCH",
            "source snapshot targetContractDigest does not match canonical generated Gathering contract",
        )
    declared_snapshot_digest = _require_digest(
        payload.get("snapshotDigest"),
        label="snapshotDigest",
    )
    if declared_snapshot_digest != _snapshot_digest(payload):
        raise MigrationControlError(
            "SOURCE_SNAPSHOT_DIGEST_MISMATCH",
            "travel source snapshot digest does not match its canonical content",
        )
    source = payload.get("source")
    if not isinstance(source, dict) or set(source) != {
        "service",
        "releaseId",
        "serviceImageDigest",
        "configDigest",
    }:
        raise MigrationControlError(
            "SOURCE_IDENTITY_INVALID",
            "source identity must contain exactly service/releaseId/serviceImageDigest/configDigest",
        )
    if source.get("service") != "travel-service":
        raise MigrationControlError(
            "SOURCE_IDENTITY_INVALID",
            "source service must be travel-service",
        )
    _require_nonblank(source.get("releaseId"), label="source.releaseId")
    _require_digest(
        source.get("serviceImageDigest"),
        label="source.serviceImageDigest",
    )
    _require_digest(source.get("configDigest"), label="source.configDigest")
    objects = payload.get("objects")
    if not isinstance(objects, dict) or set(objects) != set(SOURCE_OBJECT_TYPES):
        raise MigrationControlError(
            "SOURCE_INVENTORY_INCOMPLETE",
            "source objects must enumerate every canonical travel object collection",
        )
    for object_type in SOURCE_OBJECT_TYPES:
        values = objects.get(object_type)
        if not isinstance(values, list) or any(
            not isinstance(value, dict) for value in values
        ):
            raise MigrationControlError(
                "SOURCE_SNAPSHOT_INVALID",
                f"objects.{object_type} must be a list of objects",
            )
    bindings = payload.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != {
        "tripBindings",
        "membershipBindings",
        "placementRouteIds",
    }:
        raise MigrationControlError(
            "SOURCE_BINDINGS_INVALID",
            "bindings must contain exactly tripBindings/membershipBindings/placementRouteIds",
        )
    if any(not isinstance(bindings[key], dict) for key in bindings):
        raise MigrationControlError(
            "SOURCE_BINDINGS_INVALID",
            "all migration binding groups must be objects",
        )
    return payload


def load_target_snapshot(
    path: Path,
    *,
    environment: str,
    target_contract_digest: str,
) -> dict[str, Any]:
    payload = _load_object(path, label="Gathering target snapshot")
    required = {
        "schema",
        "environment",
        "capturedAt",
        "targetContractDigest",
        "documents",
        "snapshotDigest",
    }
    if set(payload) != required:
        raise MigrationControlError(
            "TARGET_SNAPSHOT_INVALID",
            "Gathering target snapshot fields must be exactly: "
            + ", ".join(sorted(required)),
        )
    if payload.get("schema") != TARGET_SNAPSHOT_SCHEMA:
        raise MigrationControlError(
            "TARGET_SNAPSHOT_INVALID",
            f"Gathering target snapshot schema must be {TARGET_SNAPSHOT_SCHEMA}",
        )
    if payload.get("environment") != environment:
        raise MigrationControlError(
            "TARGET_SNAPSHOT_ENV_MISMATCH",
            "Gathering target snapshot environment does not match --env",
        )
    _parse_timestamp(payload.get("capturedAt"), label="target.capturedAt")
    digest = _require_digest(
        payload.get("targetContractDigest"),
        label="target.targetContractDigest",
    )
    if digest != target_contract_digest:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISMATCH",
            "target snapshot contract digest does not match canonical generated Gathering contract",
        )
    if payload.get("snapshotDigest") != _snapshot_digest(payload):
        raise MigrationControlError(
            "TARGET_SNAPSHOT_DIGEST_MISMATCH",
            "Gathering target snapshot digest does not match its canonical content",
        )
    documents = payload.get("documents")
    if not isinstance(documents, list) or any(
        not isinstance(value, dict) for value in documents
    ):
        raise MigrationControlError(
            "TARGET_SNAPSHOT_INVALID",
            "target documents must be a list of objects",
        )
    return payload


def _source_object_id(object_type: str, value: Mapping[str, Any]) -> str:
    candidates = {
        "TripMapView": ("tripId",),
        "TripTimelineView": ("tripId",),
    }.get(object_type, ("_id",))
    for candidate in candidates:
        text = str(value.get(candidate) or "").strip()
        if text:
            return text
    return ""


def _status_key(value: Mapping[str, Any]) -> str:
    for key in ("status", "state", "assignmentStatus"):
        candidate = value.get(key)
        if candidate is not None and str(candidate).strip():
            status = str(candidate)
            return status if status in SOURCE_STATUS_VALUES else "unknown"
    return "not_applicable"


def _count_references(value: Any, *, key: str = "") -> int:
    if isinstance(value, dict):
        return sum(
            _count_references(child, key=str(child_key))
            for child_key, child in value.items()
        )
    if isinstance(value, list):
        if key.endswith(("Ids", "Refs")):
            return len([child for child in value if child not in (None, "")])
        return sum(_count_references(child, key=key) for child in value)
    if key != "_id" and key.endswith(("Id", "Ref")) and value not in (None, ""):
        return 1
    return 0


def build_inventory(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    objects = snapshot["objects"]
    result: dict[str, Any] = {}
    total_objects = 0
    total_references = 0
    for object_type in SOURCE_OBJECT_TYPES:
        values = objects[object_type]
        status_counts: dict[str, int] = {}
        reference_count = 0
        for value in values:
            status = _status_key(value)
            status_counts[status] = status_counts.get(status, 0) + 1
            reference_count += _count_references(value)
        object_digest = canonical_digest(values)
        result[object_type] = {
            "count": len(values),
            "statusCounts": dict(sorted(status_counts.items())),
            "referenceCount": reference_count,
            "objectDigest": object_digest,
        }
        total_objects += len(values)
        total_references += reference_count
    return {
        "objectTypes": result,
        "totalObjectCount": total_objects,
        "totalReferenceCount": total_references,
    }


def _pii_redaction_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    sensitive_counts: dict[str, int] = {}
    identity_count = 0
    pattern_matches = {"email": 0, "phone": 0}

    def sensitive_category(key: str) -> str:
        lowered = key.lower()
        if "phone" in lowered or "email" in lowered or "contact" in lowered:
            return "contact"
        if "address" in lowered or "meetingpoint" in lowered:
            return "location"
        if "answer" in lowered:
            return "application_answer"
        if "inlinetext" in lowered:
            return "inline_text"
        return "credential_or_secret"

    def scan(value: Any, *, key: str = "") -> None:
        nonlocal identity_count
        if isinstance(value, dict):
            for child_key, child in value.items():
                child_key_text = str(child_key)
                if SENSITIVE_KEY_RE.search(child_key_text):
                    category = sensitive_category(child_key_text)
                    sensitive_counts[category] = sensitive_counts.get(category, 0) + 1
                if IDENTITY_KEY_RE.search(child_key_text):
                    identity_count += 1
                scan(child, key=child_key_text)
            return
        if isinstance(value, list):
            for child in value:
                scan(child, key=key)
            return
        if isinstance(value, str):
            if EMAIL_RE.search(value):
                pattern_matches["email"] += 1
            if PHONE_RE.search(value):
                pattern_matches["phone"] += 1

    scan(snapshot)
    return {
        "policy": "hash-identities-count-sensitive-values-never-emit-source-text",
        "rawValuesEmitted": False,
        "identityFieldsHashed": identity_count,
        "sensitiveFieldOccurrences": dict(sorted(sensitive_counts.items())),
        "detectedValuePatterns": pattern_matches,
    }
