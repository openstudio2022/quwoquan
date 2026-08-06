"""travel-service -> Gathering 的 target-only 迁移证据控制面。

本模块只读取显式快照、canonical generated ContractGraph 与外部签名回执，只把
脱敏的证据/审批计划写入 ``QWQ_OUTPUT_ROOT``。它不包含数据库客户端、HTTP 写入口，
也不在本进程执行 cutover 或 rollback 环境写入。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import (
    artifact_run_dir,
    load_json_yaml,
    relpath,
    write_json,
)
from quwoquan_ops.cli.lib.output_paths import output_root

ROOT = Path(__file__).resolve().parents[3]
MIGRATION_ID = "travel-to-gathering"
COMMAND_NAME = "stackctl migration travel-to-gathering"
RECEIPT_SCHEMA = "qwq.travel_to_gathering.migration_receipt"
SOURCE_SNAPSHOT_SCHEMA = "qwq.travel_to_gathering.source_snapshot"
TARGET_SNAPSHOT_SCHEMA = "qwq.travel_to_gathering.target_snapshot"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
EVIDENCE_PHASES = ("inventory", "dry-run", "parity")
CONTROL_PHASES = ("cutover", "rollback")
PHASES = (*EVIDENCE_PHASES, *CONTROL_PHASES)
DISPOSITIONS = ("migrated", "archived", "quarantined", "not_applicable")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
TIMEZONE_RE = re.compile(r"^(?:UTC|[A-Za-z_]+/[A-Za-z0-9_+.-]+)$")
EMAIL_RE = re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:phone|email|contact|address|inlineText|exactMeetingPoint|"
    r"answerText|applicationAnswers|credential|token|secret)"
)
IDENTITY_KEY_RE = re.compile(r"(?i)(?:personaId|memberId|participantId)$")
SOURCE_STATUS_VALUES = frozenset(
    {
        "accepted",
        "active",
        "archived",
        "assigned",
        "cancelled",
        "completed",
        "deleted",
        "in_progress",
        "left",
        "planning",
        "removed",
        "revoked",
    }
)

SOURCE_OBJECT_TYPES = (
    "TripPlan",
    "TripPlanRevision",
    "TripMembership",
    "TripMoment",
    "TripPlanContentLink",
    "TripGuideAssignment",
    "TripPlanPlacement",
    "TripMapView",
    "TripTimelineView",
    "TripShareSnapshot",
    "TripPlanTemplate",
)

TARGET_OWNER_CONTRACT_FILENAMES = (
    "object.yaml",
    "fields.yaml",
    "operations.yaml",
    "storage.yaml",
    "events.yaml",
    "errors.yaml",
)
TARGET_CONTRACT_BINDINGS = (
    (
        "circle.gathering",
        "circle/circle_management/gathering",
        Path("quwoquan_service/services/circle-service/contracts")
        / "circle_management/gathering",
        TARGET_OWNER_CONTRACT_FILENAMES,
    ),
    (
        "circle.gathering_plan",
        "circle/circle_management/gathering_plan",
        Path("quwoquan_service/services/circle-service/contracts")
        / "circle_management/gathering_plan",
        TARGET_OWNER_CONTRACT_FILENAMES,
    ),
    (
        "circle.circle",
        "circle/circle_management/circle",
        Path("quwoquan_service/services/circle-service/contracts")
        / "circle_management/circle",
        ("object.yaml", "fields.yaml", "operations.yaml"),
    ),
    (
        "chat.conversation",
        "chat/chat/conversation",
        Path("quwoquan_service/services/chat-service/contracts")
        / "chat/conversation",
        ("object.yaml", "fields.yaml", "operations.yaml"),
    ),
    (
        "content.post",
        "content/content/post",
        Path("quwoquan_service/services/content-service/contracts")
        / "content/post",
        ("object.yaml", "fields.yaml", "operations.yaml"),
    ),
)
TARGET_GENERATED_MODELS = (
    (
        "circle.gathering",
        Path("quwoquan_service/services/circle-service/generated")
        / "circle_management/gathering/contract/model/gathering.go",
    ),
    (
        "circle.gathering_plan",
        Path("quwoquan_service/services/circle-service/generated")
        / "circle_management/gathering_plan/contract/model/gathering_plan.go",
    ),
)
TARGET_CONTRACT_GRAPH = Path("quwoquan_service/generated/contract_graph.json")
CROSSWALK_PATH = Path(__file__).with_name("crosswalk.json")

CANONICAL_TARGET_OBJECT_IDS = (
    "chat.conversation",
    "circle.circle",
    "circle.gathering",
    "circle.gathering_plan",
    "content.post",
)
REQUIRED_TARGET_OPERATION_IDS = (
    "chat.conversation.ProjectGatheringConversation",
    "circle.gathering.CreateGatheringDraft",
    "circle.gathering.UpdateGathering",
    "circle.gathering_plan.CommitGatheringPlanProposal",
    "circle.gathering_plan.CreateGatheringPlan",
    "circle.gathering_plan.ProposeGatheringPlan",
)
OPERATIONAL_EVIDENCE_SCHEMA = "qwq.travel_to_gathering.operational_evidence"
OPERATIONAL_EVIDENCE_TYPES = (
    "target_backup",
    "source_write_freeze",
    "target_command_import",
    "protected_environment_approval",
    "target_config_activation",
    "target_restore",
)
ROLLBACK_MODES = ("target_application_config", "target_snapshot")
SAFE_WRITE_PLANES = frozenset(
    {"target_application", "target_config", "target_snapshot"}
)
TARGET_WRITE_SERVICES = frozenset(
    {"chat-service", "circle-service", "content-service", "quwoquan-app"}
)


class MigrationControlError(RuntimeError):
    """可安全写入控制面回执的 fail-closed 错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TargetContractBinding:
    digest: str
    graph_digest: str
    generated_artifact_digest: str
    sources: tuple[dict[str, str], ...]
    fields_contract: dict[str, Any]
    plan_fields_contract: dict[str, Any]
    object_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]


@dataclass(frozen=True)
class MappingResult:
    documents: tuple[dict[str, Any], ...]
    records: tuple[dict[str, Any], ...]
    conflicts: dict[str, Any]
    blockers: tuple[dict[str, Any], ...]
    validation: dict[str, Any]


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _identity_digest(object_type: str, object_id: str) -> str:
    return canonical_digest({"objectType": object_type, "objectId": object_id})


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = load_json_yaml(path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise MigrationControlError(
            "INPUT_UNREADABLE",
            f"{label} is unreadable",
        ) from exc
    if not isinstance(value, dict):
        raise MigrationControlError("INPUT_INVALID", f"{label} must be an object")
    return value


def _require_digest(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if DIGEST_RE.fullmatch(text) is None:
        raise MigrationControlError(
            "DIGEST_INVALID",
            f"{label} must be a canonical sha256 digest",
        )
    return text


def _require_nonblank(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise MigrationControlError("INPUT_INVALID", f"{label} must be non-empty")
    return text


def _parse_timestamp(value: Any, *, label: str) -> str:
    text = _require_nonblank(value, label=label)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationControlError(
            "INPUT_INVALID",
            f"{label} must be an RFC3339 timestamp",
        ) from exc
    return text


def _assert_generated_model_matches_fields(
    generated_text: str,
    fields_contract: Mapping[str, Any],
) -> None:
    if not generated_text.startswith(
        "// Code generated by internal/metadata/codegen. DO NOT EDIT."
    ):
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISSING",
            "canonical generated Gathering model header is missing",
        )
    root_fields = fields_contract.get("fields")
    if not isinstance(root_fields, list) or not root_fields:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISSING",
            "canonical Gathering fields contract is empty",
        )
    missing: list[str] = []
    for field in root_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        if not name:
            continue
        bson_name = name
        if f'bson:"{bson_name}"' not in generated_text:
            missing.append(name)
    if missing:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISMATCH",
            "canonical generated Gathering model is stale for: "
            + ", ".join(sorted(missing)),
        )


def resolve_target_contract(
    repository_root: Path = ROOT,
) -> TargetContractBinding:
    """解析并验证 Circle/Chat/Content canonical target contract 摘要。"""

    graph_path = repository_root / TARGET_CONTRACT_GRAPH
    if not graph_path.is_file():
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISSING",
            "canonical generated ContractGraph is missing",
        )
    graph = _load_object(graph_path, label="ContractGraph")
    sources = graph.get("sources")
    if not isinstance(sources, list):
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISSING",
            "ContractGraph has no canonical source digest set",
        )
    source_by_path: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        path = str(source.get("path") or "")
        digest = str(source.get("sha256") or "")
        if path and HEX_DIGEST_RE.fullmatch(digest):
            source_by_path[path] = digest

    selected_sources: list[dict[str, str]] = []
    contract_dirs: dict[str, Path] = {}
    for object_id, graph_prefix, contract_relative, filenames in (
        TARGET_CONTRACT_BINDINGS
    ):
        contract_dir = repository_root / contract_relative
        contract_dirs[object_id] = contract_dir
        for filename in filenames:
            graph_source = f"{graph_prefix}/{filename}"
            expected = source_by_path.get(graph_source)
            contract_path = contract_dir / filename
            if expected is None or not contract_path.is_file():
                raise MigrationControlError(
                    "TARGET_CONTRACT_DIGEST_MISSING",
                    f"canonical target source digest is missing: {graph_source}",
                )
            actual = hashlib.sha256(contract_path.read_bytes()).hexdigest()
            if actual != expected:
                raise MigrationControlError(
                    "TARGET_CONTRACT_DIGEST_MISMATCH",
                    f"canonical target source digest drift: {graph_source}",
                )
            selected_sources.append({"path": graph_source, "sha256": expected})

    objects = graph.get("objects")
    if not isinstance(objects, list):
        objects = []
    target_objects_by_id: dict[str, dict[str, Any]] = {}
    for object_id in CANONICAL_TARGET_OBJECT_IDS:
        matches = [
            value
            for value in objects
            if isinstance(value, dict) and value.get("id") == object_id
        ]
        if len(matches) != 1:
            raise MigrationControlError(
                "TARGET_CONTRACT_DIGEST_MISSING",
                f"ContractGraph must contain exactly one {object_id} object",
            )
        target_objects_by_id[object_id] = matches[0]
    if set(target_objects_by_id) != set(CANONICAL_TARGET_OBJECT_IDS):
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISSING",
            "ContractGraph canonical migration targets are incomplete",
        )
    operations = graph.get("operations")
    if not isinstance(operations, list):
        operations = []
    target_operations = sorted(
        (
            value
            for value in operations
            if isinstance(value, dict)
            and value.get("objectId") in CANONICAL_TARGET_OBJECT_IDS
        ),
        key=lambda value: str(value.get("id") or ""),
    )
    operation_ids = {
        str(value.get("id") or "")
        for value in target_operations
        if str(value.get("id") or "")
    }
    missing_operations = sorted(set(REQUIRED_TARGET_OPERATION_IDS) - operation_ids)
    if missing_operations:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISSING",
            "ContractGraph canonical migration operations are missing: "
            + ", ".join(missing_operations),
        )

    fields_contract = _load_object(
        contract_dirs["circle.gathering"] / "fields.yaml",
        label="Gathering fields contract",
    )
    plan_fields_contract = _load_object(
        contract_dirs["circle.gathering_plan"] / "fields.yaml",
        label="GatheringPlan fields contract",
    )
    fields_by_object = {
        "circle.gathering": fields_contract,
        "circle.gathering_plan": plan_fields_contract,
    }
    generated_artifacts: list[dict[str, str]] = []
    for object_id, relative_path in TARGET_GENERATED_MODELS:
        generated_path = repository_root / relative_path
        if not generated_path.is_file():
            raise MigrationControlError(
                "TARGET_CONTRACT_DIGEST_MISSING",
                f"canonical generated model is missing: {object_id}",
            )
        generated_text = generated_path.read_text(encoding="utf-8")
        _assert_generated_model_matches_fields(
            generated_text,
            fields_by_object[object_id],
        )
        generated_artifacts.append(
            {
                "objectId": object_id,
                "path": relative_path.as_posix(),
                "digest": _file_digest(generated_path),
            }
        )
    generated_artifact_digest = canonical_digest(generated_artifacts)
    projection = {
        "objects": [
            target_objects_by_id[object_id]
            for object_id in CANONICAL_TARGET_OBJECT_IDS
        ],
        "operations": target_operations,
        "sources": sorted(selected_sources, key=lambda value: value["path"]),
        "generatedArtifacts": generated_artifacts,
    }
    return TargetContractBinding(
        digest=canonical_digest(projection),
        graph_digest=_file_digest(graph_path),
        generated_artifact_digest=generated_artifact_digest,
        sources=tuple(sorted(selected_sources, key=lambda value: value["path"])),
        fields_contract=fields_contract,
        plan_fields_contract=plan_fields_contract,
        object_ids=tuple(CANONICAL_TARGET_OBJECT_IDS),
        operation_ids=tuple(sorted(operation_ids)),
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


def _new_conflicts() -> dict[str, Any]:
    return {
        category: {"count": 0, "collisionDigests": []}
        for category in (
            "objectIdentity",
            "conversationId",
            "host",
            "member",
            "capacity",
            "timezone",
            "disclosure",
            "reference",
        )
    }


def _record_conflict(
    conflicts: dict[str, Any],
    category: str,
    evidence: Mapping[str, Any],
) -> None:
    digest = canonical_digest(evidence)
    bucket = conflicts[category]
    if digest in bucket["collisionDigests"]:
        return
    bucket["collisionDigests"].append(digest)
    bucket["collisionDigests"].sort()
    bucket["count"] = len(bucket["collisionDigests"])


def _safe_blocker(
    code: str,
    *,
    object_type: str = "",
    object_id: str = "",
    reason: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "objectType": object_type,
        "objectIdentityDigest": (
            _identity_digest(object_type, object_id)
            if object_type and object_id
            else ""
        ),
        "reason": reason,
    }


def _dedupe_blockers(
    blockers: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    by_digest = {canonical_digest(blocker): blocker for blocker in blockers}
    return tuple(by_digest[key] for key in sorted(by_digest))


def _index_objects(
    snapshot: Mapping[str, Any],
    conflicts: dict[str, Any],
) -> dict[str, list[tuple[int, dict[str, Any], str]]]:
    indexed: dict[str, list[tuple[int, dict[str, Any], str]]] = {}
    for object_type in SOURCE_OBJECT_TYPES:
        seen: dict[str, int] = {}
        entries: list[tuple[int, dict[str, Any], str]] = []
        for index, value in enumerate(snapshot["objects"][object_type]):
            object_id = _source_object_id(object_type, value)
            entries.append((index, value, object_id))
            if not object_id:
                _record_conflict(
                    conflicts,
                    "objectIdentity",
                    {"objectType": object_type, "index": index, "reason": "missing"},
                )
                continue
            if object_id in seen:
                _record_conflict(
                    conflicts,
                    "objectIdentity",
                    {
                        "objectType": object_type,
                        "objectId": object_id,
                        "reason": "duplicate",
                    },
                )
            seen[object_id] = seen.get(object_id, 0) + 1
        indexed[object_type] = entries
    return indexed


def _binding_trip_id(binding: Mapping[str, Any]) -> str:
    return str(binding.get("gatheringId") or "").strip()


def _trip_binding_issues(
    plan: Mapping[str, Any],
    binding: Mapping[str, Any] | None,
    memberships: Sequence[Mapping[str, Any]],
    membership_bindings: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = []
    if not isinstance(binding, dict):
        return ["trip_binding_missing"]
    gathering_id = _binding_trip_id(binding)
    if not gathering_id:
        issues.append("gathering_identity_missing")
    for key in (
        "hostBinding",
        "purpose",
        "schedule",
        "place",
        "policySet",
        "admissionControl",
    ):
        if not isinstance(binding.get(key), dict):
            issues.append(f"{key}_missing")
    host = binding.get("hostBinding")
    if isinstance(host, dict):
        if not str(host.get("authorityEvidenceRef") or "").strip():
            issues.append("host_authority_evidence_missing")
        if not isinstance(host.get("authorityVersion"), int):
            issues.append("host_authority_version_missing")
    schedule = binding.get("schedule")
    timezone_name = (
        str(schedule.get("timezone") or "").strip()
        if isinstance(schedule, dict)
        else ""
    )
    if TIMEZONE_RE.fullmatch(timezone_name) is None:
        issues.append("timezone_missing_or_invalid")
    policy = binding.get("policySet")
    disclosure = policy.get("disclosurePolicy") if isinstance(policy, dict) else None
    if not isinstance(disclosure, dict) or any(
        not str(disclosure.get(key) or "").strip()
        for key in ("timeDisclosure", "placeDisclosure", "rosterDisclosure")
    ):
        issues.append("disclosure_policy_missing")
    capacity = policy.get("capacityPolicy") if isinstance(policy, dict) else None
    max_participants = (
        capacity.get("maxParticipants") if isinstance(capacity, dict) else None
    )
    if (
        isinstance(max_participants, bool)
        or not isinstance(max_participants, int)
        or max_participants < 1
    ):
        issues.append("capacity_missing_or_invalid")
    active_memberships = [
        value for value in memberships if value.get("state") == "active"
    ]
    if isinstance(max_participants, int) and len(active_memberships) > max_participants:
        issues.append("capacity_below_active_members")
    organizer_id = str(plan.get("organizerPersonaId") or "").strip()
    active_organizers = [
        value
        for value in active_memberships
        if value.get("role") == "organizer"
        and str(value.get("personaId") or "").strip() == organizer_id
    ]
    if len(active_organizers) != 1:
        issues.append("primary_organizer_membership_not_unique")
    for membership in memberships:
        membership_id = str(membership.get("_id") or "").strip()
        membership_binding = membership_bindings.get(membership_id)
        if not isinstance(membership_binding, dict):
            issues.append("membership_binding_missing")
            continue
        for key in (
            "admissionSource",
            "attemptNo",
            "attendance",
            "currentChangeAcknowledgement",
        ):
            if key not in membership_binding:
                issues.append(f"membership_{key}_missing")
        if membership.get("role") == "organizer" and not isinstance(
            membership_binding.get("organizerAssignment"),
            dict,
        ):
            issues.append("organizer_assignment_evidence_missing")
    if plan.get("status") == "completed":
        if not isinstance(binding.get("outcome"), dict):
            issues.append("completed_outcome_evidence_missing")
        if not str(binding.get("completedAt") or "").strip():
            issues.append("completed_at_missing")
    return sorted(set(issues))


def _map_lifecycle_status(source_status: Any) -> str:
    return {
        "planning": "draft",
        "active": "published",
        "completed": "completed",
    }.get(str(source_status or ""), "")


def _map_membership_closed_reason(source_state: Any) -> str | None:
    return {
        "left": "left",
        "revoked": "removed",
    }.get(str(source_state or ""))


def _target_revision_id(source_revision_id: str) -> str:
    return f"gathering-revision:{source_revision_id}"


def _target_plan_id(gathering_id: str) -> str:
    return f"gathering-plan:{gathering_id}"


def _canonical_object_ref(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    object_type = str(value.get("objectTypeRef") or "").strip()
    object_id = str(value.get("objectId") or "").strip()
    if not object_type or not object_id:
        return None
    return {"objectTypeRef": object_type, "objectId": object_id}


def _duration_minutes(start_at: Any, end_at: Any) -> int | None:
    if not isinstance(start_at, str) or not isinstance(end_at, str):
        return None
    try:
        start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    seconds = int((end - start).total_seconds())
    return max(0, seconds // 60)


def _map_plan_item(
    value: Mapping[str, Any],
    *,
    extra_source_refs: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    """把旧 activity item 收敛到 GatheringPlan 的 typed agenda item。"""

    source_refs: list[dict[str, str]] = []
    place_ref = _canonical_object_ref(value.get("placeRef"))
    if place_ref is not None:
        source_refs.append(place_ref)
    source_refs.extend(
        {
            "objectTypeRef": str(ref.get("objectTypeRef") or ""),
            "objectId": str(ref.get("objectId") or ""),
        }
        for ref in extra_source_refs
        if str(ref.get("objectTypeRef") or "").strip()
        and str(ref.get("objectId") or "").strip()
    )
    source_refs = [
        dict(value)
        for _, value in sorted(
            {
                canonical_digest(ref): ref
                for ref in source_refs
            }.items()
        )
    ]
    title = str(value.get("title") or "").strip()
    note = str(value.get("note") or "").strip()
    content = title or note
    return {
        "itemId": str(value.get("itemId") or ""),
        "kind": "agenda",
        "order": int(value.get("dayIndex") or 0) * 1000
        + int(value.get("orderInDay") or 0),
        "agenda": {
            "content": content,
            "startsAt": value.get("startAt"),
            "durationMinutes": _duration_minutes(
                value.get("startAt"),
                value.get("endAt"),
            ),
        },
        "sourceRefs": source_refs,
    }


def _constraints(field: Mapping[str, Any]) -> set[str]:
    value = field.get("constraints")
    return {str(item) for item in value} if isinstance(value, list) else set()


def _validate_scalar_type(
    value: Any,
    type_name: str,
    *,
    location: str,
    enums: Mapping[str, Any],
    enum_ref: str,
) -> list[str]:
    if type_name in {"string", "json"}:
        if type_name == "string" and not isinstance(value, str):
            return [f"{location} must be string"]
        return []
    if type_name in {"int", "int64"}:
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{location} must be integer"]
        return []
    if type_name == "bool":
        return [] if isinstance(value, bool) else [f"{location} must be bool"]
    if type_name == "timestamp":
        if not isinstance(value, str):
            return [f"{location} must be timestamp string"]
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return [f"{location} must be RFC3339 timestamp"]
        return []
    if type_name == "enum":
        definition = enums.get(enum_ref)
        allowed = definition.get("values") if isinstance(definition, dict) else None
        if not isinstance(allowed, list) or value not in allowed:
            return [f"{location} is not in {enum_ref}"]
        return []
    return []


def _validate_field_value(
    value: Any,
    field: Mapping[str, Any],
    *,
    location: str,
    types: Mapping[str, Any],
    enums: Mapping[str, Any],
) -> list[str]:
    constraints = _constraints(field)
    if value is None:
        return [] if "NULLABLE" in constraints else [f"{location} may not be null"]
    type_name = str(field.get("type") or "")
    if type_name.startswith("[]"):
        if not isinstance(value, list):
            return [f"{location} must be list"]
        errors: list[str] = []
        max_items = field.get("max_items")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{location} exceeds max_items")
        item_type = type_name[2:]
        item_field = {"type": item_type, "constraints": ["NOT_NULL"]}
        for index, item in enumerate(value):
            errors.extend(
                _validate_field_value(
                    item,
                    item_field,
                    location=f"{location}[{index}]",
                    types=types,
                    enums=enums,
                )
            )
        return errors
    if type_name == "object":
        type_name = str(field.get("object_ref") or "")
    if type_name in types:
        definition = types[type_name]
        if not isinstance(value, dict) or not isinstance(definition, dict):
            return [f"{location} must be {type_name} object"]
        nested_fields = definition.get("fields")
        if not isinstance(nested_fields, list):
            return [f"{location} has invalid contract definition"]
        expected = {
            str(item.get("name") or "")
            for item in nested_fields
            if isinstance(item, dict)
        }
        errors = []
        unknown = set(value) - expected
        if unknown:
            errors.append(f"{location} has unknown fields: {sorted(unknown)}")
        for nested in nested_fields:
            if not isinstance(nested, dict):
                continue
            name = str(nested.get("name") or "")
            if name not in value:
                if "NULLABLE" not in _constraints(nested):
                    errors.append(f"{location}.{name} is missing")
                continue
            errors.extend(
                _validate_field_value(
                    value[name],
                    nested,
                    location=f"{location}.{name}",
                    types=types,
                    enums=enums,
                )
            )
        return errors
    errors = _validate_scalar_type(
        value,
        type_name,
        location=location,
        enums=enums,
        enum_ref=str(field.get("enum_ref") or ""),
    )
    if "NOT_BLANK" in constraints and isinstance(value, str) and not value.strip():
        errors.append(f"{location} may not be blank")
    max_bytes = field.get("max_utf8_bytes")
    if (
        isinstance(max_bytes, int)
        and isinstance(value, str)
        and len(value.encode("utf-8")) > max_bytes
    ):
        errors.append(f"{location} exceeds max_utf8_bytes")
    return errors


def _validate_contract_document(
    document: Mapping[str, Any],
    fields_contract: Mapping[str, Any],
    *,
    object_name: str,
) -> list[str]:
    root_fields = fields_contract.get("fields")
    types = fields_contract.get("types")
    enums = fields_contract.get("enums")
    if (
        not isinstance(root_fields, list)
        or not isinstance(types, dict)
        or not isinstance(enums, dict)
    ):
        return [f"canonical {object_name} fields contract is incomplete"]
    expected = {
        str(field.get("name") or "") for field in root_fields if isinstance(field, dict)
    }
    errors: list[str] = []
    unknown = set(document) - expected
    if unknown:
        errors.append(f"{object_name} has unknown fields: {sorted(unknown)}")
    for field in root_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        if name not in document:
            if "NULLABLE" not in _constraints(field):
                errors.append(f"{object_name}.{name} is missing")
            continue
        errors.extend(
            _validate_field_value(
                document[name],
                field,
                location=f"{object_name}.{name}",
                types=types,
                enums=enums,
            )
        )
    return errors


def validate_gathering_document(
    document: Mapping[str, Any],
    fields_contract: Mapping[str, Any],
) -> list[str]:
    return _validate_contract_document(
        document,
        fields_contract,
        object_name="Gathering",
    )


def _mapping_record(
    object_type: str,
    object_id: str,
    value: Mapping[str, Any],
    *,
    disposition: str,
    reason: str,
    target_refs: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    if disposition not in DISPOSITIONS:
        raise ValueError(f"invalid disposition: {disposition}")
    return {
        "sourceObjectType": object_type,
        "sourceObjectIdentityDigest": (
            _identity_digest(object_type, object_id)
            if object_id
            else canonical_digest(
                {"objectType": object_type, "sourceDigest": canonical_digest(value)}
            )
        ),
        "sourceObjectDigest": canonical_digest(value),
        "disposition": disposition,
        "reason": reason,
        "targetRefs": [
            {
                "objectType": str(ref.get("objectType") or ""),
                "objectIdentityDigest": _identity_digest(
                    str(ref.get("objectType") or ""),
                    str(ref.get("objectId") or ""),
                ),
            }
            for ref in target_refs
        ],
    }


def build_mapping(
    snapshot: Mapping[str, Any],
    target_contract: TargetContractBinding,
) -> MappingResult:
    conflicts = _new_conflicts()
    indexed = _index_objects(snapshot, conflicts)
    blockers: list[dict[str, Any]] = []
    records_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    documents: list[dict[str, Any]] = []
    validation_errors: list[dict[str, Any]] = []
    plan_validation_errors: list[dict[str, Any]] = []

    plans_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    duplicate_plan_ids: set[str] = set()
    for index, plan, trip_id in indexed["TripPlan"]:
        if trip_id in plans_by_id:
            duplicate_plan_ids.add(trip_id)
        else:
            plans_by_id[trip_id] = (index, plan)
    revisions_by_trip: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, revision, _ in indexed["TripPlanRevision"]:
        trip_id = str(revision.get("tripId") or "").strip()
        revisions_by_trip.setdefault(trip_id, []).append((index, revision))
    memberships_by_trip: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    membership_identity_seen: set[tuple[str, str]] = set()
    duplicate_membership_indexes: set[int] = set()
    for index, membership, _ in indexed["TripMembership"]:
        trip_id = str(membership.get("tripId") or "").strip()
        persona_id = str(membership.get("personaId") or "").strip()
        identity = (trip_id, persona_id)
        if identity in membership_identity_seen:
            duplicate_membership_indexes.add(index)
            _record_conflict(
                conflicts,
                "member",
                {"tripId": trip_id, "personaId": persona_id},
            )
        membership_identity_seen.add(identity)
        memberships_by_trip.setdefault(trip_id, []).append((index, membership))

    trip_bindings = snapshot["bindings"]["tripBindings"]
    membership_bindings = snapshot["bindings"]["membershipBindings"]
    placement_route_ids = snapshot["bindings"]["placementRouteIds"]
    plan_item_source_refs: dict[
        tuple[str, int, str],
        list[dict[str, str]],
    ] = {}
    for _, moment, _ in indexed["TripMoment"]:
        content_ref = _canonical_object_ref(moment.get("contentRef"))
        if moment.get("status") == "active" and content_ref is not None:
            key = (
                str(moment.get("tripId") or ""),
                int(moment.get("revisionNumber") or 0),
                str(moment.get("itemId") or ""),
            )
            plan_item_source_refs.setdefault(key, []).append(content_ref)
    for _, link, _ in indexed["TripPlanContentLink"]:
        post_id = str(link.get("postId") or "").strip()
        if link.get("status") == "active" and post_id:
            key = (
                str(link.get("tripId") or ""),
                int(link.get("revisionNumber") or 0),
                str(link.get("itemId") or ""),
            )
            plan_item_source_refs.setdefault(key, []).append(
                {
                    "objectTypeRef": "content.Post",
                    "objectId": post_id,
                }
            )
    gathering_identity_seen: dict[str, str] = {}
    conversation_seen: dict[str, str] = {}
    mapped_trip_ids: dict[str, str] = {}

    for trip_id, (plan_index, plan) in sorted(plans_by_id.items()):
        if trip_id in duplicate_plan_ids:
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason="duplicate_source_identity",
            )
            blockers.append(
                _safe_blocker(
                    "SOURCE_IDENTITY_COLLISION",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason="duplicate TripPlan identity",
                )
            )
            continue
        if plan.get("status") == "archived":
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="archived",
                reason="source_plan_archived",
            )
            continue
        binding = trip_bindings.get(trip_id)
        memberships = [value for _, value in memberships_by_trip.get(trip_id, [])]
        issues = _trip_binding_issues(
            plan,
            binding if isinstance(binding, dict) else None,
            memberships,
            membership_bindings,
        )
        if isinstance(binding, dict):
            gathering_id = _binding_trip_id(binding)
            if gathering_id:
                previous_trip = gathering_identity_seen.get(gathering_id)
                if previous_trip and previous_trip != trip_id:
                    issues.append("target_gathering_identity_collision")
                    _record_conflict(
                        conflicts,
                        "objectIdentity",
                        {
                            "gatheringId": gathering_id,
                            "firstTripId": previous_trip,
                            "secondTripId": trip_id,
                        },
                    )
                gathering_identity_seen[gathering_id] = trip_id
            conversation_id = str(binding.get("conversationId") or "").strip()
            if conversation_id:
                previous_trip = conversation_seen.get(conversation_id)
                if previous_trip and previous_trip != trip_id:
                    issues.append("duplicate_conversation_id")
                    _record_conflict(
                        conflicts,
                        "conversationId",
                        {
                            "conversationId": conversation_id,
                            "firstTripId": previous_trip,
                            "secondTripId": trip_id,
                        },
                    )
                conversation_seen[conversation_id] = trip_id
        for issue in issues:
            category = (
                "host"
                if "host" in issue or "organizer" in issue
                else "capacity"
                if "capacity" in issue
                else "timezone"
                if "timezone" in issue
                else "disclosure"
                if "disclosure" in issue
                else "member"
                if issue.startswith("membership_")
                else "reference"
            )
            _record_conflict(
                conflicts,
                category,
                {"tripId": trip_id, "issue": issue},
            )
        revision_candidates = revisions_by_trip.get(trip_id, [])
        current_revision_id = str(plan.get("currentRevisionId") or "").strip()
        current_revision_number = plan.get("currentRevisionNumber")
        current_revisions = [
            value
            for _, value in revision_candidates
            if str(value.get("_id") or "").strip() == current_revision_id
            and value.get("revisionNumber") == current_revision_number
        ]
        if len(current_revisions) != 1:
            issues.append("current_revision_missing_or_ambiguous")
            _record_conflict(
                conflicts,
                "reference",
                {"tripId": trip_id, "reference": "currentRevision"},
            )
        if issues:
            reason = min(set(issues))
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason=reason,
            )
            blockers.append(
                _safe_blocker(
                    "TRIP_MAPPING_QUARANTINED",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason=reason,
                )
            )
            continue

        assert isinstance(binding, dict)
        gathering_id = _binding_trip_id(binding)
        purpose_binding = dict(binding["purpose"])
        source_ref = {
            "objectRef": {
                "objectTypeRef": "travel.TripPlan",
                "objectId": trip_id,
            },
            "routeId": str(binding.get("sourceRouteId") or ""),
            "sourceDigest": canonical_digest(plan),
        }
        purpose = {
            "title": plan.get("title"),
            "summary": purpose_binding.get("summary"),
            "coverRef": _canonical_object_ref(purpose_binding.get("coverRef")),
            "topicRefs": purpose_binding.get("topicRefs"),
            "requirementRefs": purpose_binding.get("requirementRefs"),
            "sourceObjectRefs": [source_ref],
            "costNotice": purpose_binding.get("costNotice"),
            "costDescription": purpose_binding.get("costDescription"),
        }
        schedule = {
            "timezone": binding["schedule"].get("timezone"),
            "startAt": plan.get("startAt"),
            "endAt": plan.get("endAt"),
            "admissionClosesAt": binding["schedule"].get("admissionClosesAt"),
        }
        place = dict(binding["place"])
        policy_set = dict(binding["policySet"])
        host_binding = dict(binding["hostBinding"])
        host_snapshot = {
            "hostSubjectKind": host_binding.get("hostSubjectKind"),
            "hostSubjectId": host_binding.get("hostSubjectId"),
            "authorityEvidenceRef": host_binding.get("authorityEvidenceRef"),
            "authorityVersion": host_binding.get("authorityVersion"),
            "hostDigest": canonical_digest(host_binding),
        }
        mapped_participations: list[dict[str, Any]] = []
        organizer_assignments: list[dict[str, Any]] = []
        membership_mapping_failed = False
        for membership_index, membership in memberships_by_trip.get(trip_id, []):
            membership_id = str(membership.get("_id") or "").strip()
            if membership_index in duplicate_membership_indexes:
                membership_mapping_failed = True
                continue
            membership_binding = membership_bindings[membership_id]
            target_state = "active" if membership.get("state") == "active" else "closed"
            participation = {
                "gatheringId": gathering_id,
                "personaId": membership.get("personaId"),
                "state": target_state,
                "admissionSource": membership_binding.get("admissionSource"),
                "closedReason": _map_membership_closed_reason(membership.get("state")),
                "attemptNo": membership_binding.get("attemptNo"),
                "seatHoldUntil": membership_binding.get("seatHoldUntil"),
                "joinedAt": membership.get("joinedAt"),
                "closedAt": (
                    membership.get("updatedAt") if target_state == "closed" else None
                ),
                "closedByPersonaId": membership_binding.get("closedByPersonaId"),
                "reasonRef": membership_binding.get("reasonRef"),
                "reviewExpectedBy": membership_binding.get("reviewExpectedBy"),
                "version": membership.get("version"),
                "applicationAnswers": membership_binding.get(
                    "applicationAnswers",
                    [],
                ),
                "attendance": membership_binding.get("attendance"),
                "currentChangeAcknowledgement": membership_binding.get(
                    "currentChangeAcknowledgement"
                ),
            }
            mapped_participations.append(participation)
            target_refs: list[dict[str, str]] = [
                {
                    "objectType": "circle.gathering",
                    "objectId": gathering_id,
                }
            ]
            if membership.get("role") == "organizer":
                assignment = dict(membership_binding["organizerAssignment"])
                organizer_assignments.append(assignment)
            records_by_key[("TripMembership", membership_index)] = _mapping_record(
                "TripMembership",
                membership_id,
                membership,
                disposition="migrated",
                reason="participation_and_authority_split",
                target_refs=target_refs,
            )
        if membership_mapping_failed:
            for membership_index, membership in memberships_by_trip.get(trip_id, []):
                records_by_key[("TripMembership", membership_index)] = _mapping_record(
                    "TripMembership",
                    str(membership.get("_id") or ""),
                    membership,
                    disposition="quarantined",
                    reason="duplicate_member_identity",
                )
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason="duplicate_member_identity",
            )
            blockers.append(
                _safe_blocker(
                    "TRIP_MAPPING_QUARANTINED",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason="duplicate member identity",
                )
            )
            continue

        current_revision = current_revisions[0]
        target_revision_id = _target_revision_id(current_revision_id)
        gathering_revision_stable = {
            "revisionId": target_revision_id,
            "revisionNumber": current_revision_number,
            "purpose": purpose,
            "schedule": schedule,
            "place": place,
            "policySet": policy_set,
            "hostSnapshot": host_snapshot,
            "materialChange": current_revision.get("severity") != "minor",
            "createdByPersonaId": current_revision.get("createdByPersonaId"),
            "createdAt": current_revision.get("createdAt"),
        }
        gathering_revision = {
            **gathering_revision_stable,
            "digest": canonical_digest(gathering_revision_stable),
        }
        lifecycle_status = _map_lifecycle_status(plan.get("status"))
        gathering = {
            "_id": gathering_id,
            "version": plan.get("version"),
            "createdByPersonaId": plan.get("organizerPersonaId"),
            "hostBinding": host_binding,
            "organizerAssignments": organizer_assignments,
            "purpose": purpose,
            "schedule": schedule,
            "place": place,
            "policySet": policy_set,
            "admissionControl": dict(binding["admissionControl"]),
            "lifecycleStatus": lifecycle_status,
            "outcome": binding.get("outcome"),
            "conversationId": binding.get("conversationId"),
            "roomBindingStatus": binding.get("roomBindingStatus"),
            "currentGatheringRevisionId": target_revision_id,
            "currentGatheringRevisionNumber": current_revision_number,
            "participations": mapped_participations,
            "revisions": [gathering_revision],
            "availabilityWatches": [],
            "createdAt": plan.get("createdAt"),
            "updatedAt": plan.get("updatedAt"),
            "cancelledAt": None,
            "completedAt": binding.get("completedAt"),
        }
        gathering_errors = validate_gathering_document(
            gathering,
            target_contract.fields_contract,
        )

        mapped_revisions: list[dict[str, Any]] = []
        for revision_index, revision in sorted(
            revision_candidates,
            key=lambda item: (
                int(item[1].get("revisionNumber") or 0),
                str(item[1].get("_id") or ""),
            ),
        ):
            source_revision_id = str(revision.get("_id") or "")
            revision_number = int(revision.get("revisionNumber") or 0)
            affected_persona_ids = sorted(
                {
                    str(persona_id).strip()
                    for persona_id in revision.get("affectedPersonaIds", [])
                    if str(persona_id).strip()
                }
            )
            plan_revision_stable: dict[str, Any] = {
                "revisionId": _target_revision_id(source_revision_id),
                "revisionNumber": revision_number,
                "baseRevisionId": (
                    _target_revision_id(str(revision.get("previousRevisionId")))
                    if revision.get("previousRevisionId")
                    else None
                ),
                "baseRevisionNumber": max(0, revision_number - 1),
                "baseRevisionDigest": (
                    mapped_revisions[-1]["revisionDigest"]
                    if mapped_revisions
                    else canonical_digest(
                        {
                            "migrationId": MIGRATION_ID,
                            "tripId": trip_id,
                            "baseRevision": None,
                        }
                    )
                ),
                "committedProposalId": None,
                "committedByPersonaId": revision.get("createdByPersonaId"),
                "items": [
                    _map_plan_item(
                        item,
                        extra_source_refs=plan_item_source_refs.get(
                            (
                                trip_id,
                                revision_number,
                                str(item.get("itemId") or ""),
                            ),
                            (),
                        ),
                    )
                    for item in revision.get("items", [])
                    if isinstance(item, dict)
                ],
                "acknowledgementPolicy": {
                    "mode": (
                        "affected_participations"
                        if affected_persona_ids
                        else "none"
                    ),
                    "deadlineAt": None,
                },
                "affectedParticipationRefs": [
                    {
                        "gatheringId": gathering_id,
                        "personaId": persona_id,
                    }
                    for persona_id in affected_persona_ids
                ],
                "committedAt": revision.get("createdAt"),
            }
            revision_digest = canonical_digest(plan_revision_stable)
            mapped_revisions.append(
                {
                    **plan_revision_stable,
                    "revisionDigest": revision_digest,
                }
            )
            records_by_key[("TripPlanRevision", revision_index)] = _mapping_record(
                "TripPlanRevision",
                source_revision_id,
                revision,
                disposition="migrated",
                reason="immutable_revision_identity_preserved",
                target_refs=[
                    {
                        "objectType": "circle.gathering_plan",
                        "objectId": _target_plan_id(gathering_id),
                    }
                ],
            )
        current_mapped_revisions = [
            revision
            for revision in mapped_revisions
            if revision["revisionId"] == target_revision_id
            and revision["revisionNumber"] == current_revision_number
        ]
        if len(current_mapped_revisions) != 1:
            candidate_errors = ["canonical current GatheringPlan revision is missing"]
            current_revision_digest = ""
        else:
            candidate_errors = []
            current_revision_digest = current_mapped_revisions[0]["revisionDigest"]
        plan_candidate = {
            "_id": _target_plan_id(gathering_id),
            "gatheringId": gathering_id,
            "version": plan.get("version"),
            "currentRevisionId": target_revision_id,
            "currentRevisionNumber": current_revision_number,
            "currentRevisionDigest": current_revision_digest,
            "revisions": mapped_revisions,
            "proposals": [],
            "acknowledgements": [],
            "createdAt": plan.get("createdAt"),
            "updatedAt": plan.get("updatedAt"),
        }
        candidate_errors.extend(
            _validate_contract_document(
                plan_candidate,
                target_contract.plan_fields_contract,
                object_name="GatheringPlan",
            )
        )
        if gathering_errors or candidate_errors:
            if gathering_errors:
                validation_errors.append(
                    {
                        "targetIdentityDigest": _identity_digest(
                            "circle.gathering",
                            gathering_id,
                        ),
                        "errorDigests": [
                            canonical_digest(error) for error in gathering_errors
                        ],
                    }
                )
            if candidate_errors:
                plan_validation_errors.append(
                    {
                        "targetIdentityDigest": _identity_digest(
                            "circle.gathering_plan",
                            plan_candidate["_id"],
                        ),
                        "errorDigests": [
                            canonical_digest(error) for error in candidate_errors
                        ],
                    }
                )
            for membership_index, membership in memberships_by_trip.get(trip_id, []):
                records_by_key[("TripMembership", membership_index)] = _mapping_record(
                    "TripMembership",
                    str(membership.get("_id") or ""),
                    membership,
                    disposition="quarantined",
                    reason="parent_target_schema_validation_failed",
                )
            for revision_index, revision in revision_candidates:
                records_by_key[("TripPlanRevision", revision_index)] = _mapping_record(
                    "TripPlanRevision",
                    str(revision.get("_id") or ""),
                    revision,
                    disposition="quarantined",
                    reason="parent_target_schema_validation_failed",
                )
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason="target_schema_validation_failed",
            )
            blockers.append(
                _safe_blocker(
                    "TARGET_SCHEMA_VALIDATION_FAILED",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason="mapped canonical Gathering/GatheringPlan is invalid",
                )
            )
            continue

        documents.extend(
            (
                {"kind": "circle.gathering", "document": gathering},
                {"kind": "circle.gathering_plan", "document": plan_candidate},
            )
        )
        mapped_trip_ids[trip_id] = gathering_id
        records_by_key[("TripPlan", plan_index)] = _mapping_record(
            "TripPlan",
            trip_id,
            plan,
            disposition="migrated",
            reason="canonical_gathering_and_plan_validated",
            target_refs=[
                {"objectType": "circle.gathering", "objectId": gathering_id},
                {
                    "objectType": "circle.gathering_plan",
                    "objectId": plan_candidate["_id"],
                },
                *[
                    {
                        "objectType": "content.post",
                        "objectId": post_id,
                    }
                    for post_id in sorted(
                        {
                            str(value).strip()
                            for value in plan.get("sourcePostIds", [])
                            if str(value).strip()
                        }
                    )
                ],
            ],
        )

    # Duplicate TripPlan entries not selected as the canonical first entry.
    for index, plan, trip_id in indexed["TripPlan"]:
        key = ("TripPlan", index)
        if key not in records_by_key:
            records_by_key[key] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason=(
                    "duplicate_source_identity"
                    if trip_id in duplicate_plan_ids
                    else "mapping_not_reached"
                ),
            )

    parent_bound_types = (
        "TripPlanRevision",
        "TripMembership",
        "TripMoment",
        "TripPlanContentLink",
        "TripGuideAssignment",
        "TripPlanPlacement",
        "TripMapView",
        "TripTimelineView",
        "TripShareSnapshot",
    )
    for object_type in parent_bound_types:
        for index, value, object_id in indexed[object_type]:
            key = (object_type, index)
            if key in records_by_key:
                continue
            trip_id = str(value.get("tripId") or "").strip()
            if trip_id not in plans_by_id:
                _record_conflict(
                    conflicts,
                    "reference",
                    {"objectType": object_type, "tripId": trip_id},
                )
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="quarantined",
                    reason="orphan_trip_reference",
                )
                blockers.append(
                    _safe_blocker(
                        "ORPHAN_SOURCE_REFERENCE",
                        object_type=object_type,
                        object_id=object_id,
                        reason="source object references a missing TripPlan",
                    )
                )
                continue
            gathering_id = mapped_trip_ids.get(trip_id)
            if not gathering_id:
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="quarantined",
                    reason="parent_trip_quarantined",
                )
                continue
            if object_type == "TripMoment":
                if value.get("status") == "deleted":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_moment_deleted",
                    )
                    continue
                content_ref = _canonical_object_ref(value.get("contentRef"))
                if content_ref is None:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="canonical_content_reference_missing",
                    )
                    blockers.append(
                        _safe_blocker(
                            "CONTENT_REFERENCE_MISSING",
                            object_type=object_type,
                            object_id=object_id,
                            reason="inline Moment content is not copied",
                        )
                    )
                    continue
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="migrated",
                    reason="canonical_content_reference_recirculated",
                    target_refs=[
                        {
                            "objectType": "circle.gathering_plan",
                            "objectId": _target_plan_id(gathering_id),
                        },
                        {
                            "objectType": "content.post",
                            "objectId": content_ref["objectId"],
                        },
                    ],
                )
                continue
            if object_type == "TripPlanContentLink":
                if value.get("status") == "removed":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_content_link_removed",
                    )
                    continue
                post_id = str(value.get("postId") or "").strip()
                if not post_id:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="canonical_post_reference_missing",
                    )
                    continue
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="migrated",
                    reason="content_owner_reference_recirculated",
                    target_refs=[
                        {
                            "objectType": "circle.gathering_plan",
                            "objectId": _target_plan_id(gathering_id),
                        },
                        {
                            "objectType": "content.post",
                            "objectId": post_id,
                        },
                    ],
                )
                continue
            if object_type == "TripGuideAssignment":
                if value.get("status") == "cancelled":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_guide_assignment_cancelled",
                    )
                    continue
                qualification_id = str(
                    value.get("publicQualificationPersonaId") or ""
                ).strip()
                if not qualification_id:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="public_authority_evidence_missing",
                    )
                    blockers.append(
                        _safe_blocker(
                            "HOST_AUTHORITY_EVIDENCE_MISSING",
                            object_type=object_type,
                            object_id=object_id,
                            reason="GuideAssignment cannot manufacture Host authority",
                        )
                    )
                    continue
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="not_applicable",
                    reason="canonical_target_guide_assignment_contract_unavailable",
                )
                continue
            if object_type == "TripPlanPlacement":
                if value.get("status") == "removed":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_placement_removed",
                    )
                    continue
                route_id = str(placement_route_ids.get(object_id) or "").strip()
                if not route_id:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="target_route_binding_missing",
                    )
                    continue
                target_kind = (
                    "chat.conversation"
                    if value.get("surfaceKind") == "conversation"
                    else "circle.circle"
                )
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="migrated",
                    reason="typed_target_placement_binding_preserved",
                    target_refs=[
                        {
                            "objectType": "circle.gathering_plan",
                            "objectId": _target_plan_id(gathering_id),
                        },
                        {
                            "objectType": target_kind,
                            "objectId": str(value.get("surfaceId") or ""),
                        },
                    ],
                )
                continue
            if object_type in {"TripMapView", "TripTimelineView"}:
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="not_applicable",
                    reason="derived_projection_rebuild_only",
                )
                continue
            if object_type == "TripShareSnapshot":
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="not_applicable",
                    reason="privacy_trimmed_snapshot_is_parity_input_only",
                )
                continue
            # Remaining parent-bound objects are revisions/memberships already
            # handled with their aggregate.
            records_by_key[key] = _mapping_record(
                object_type,
                object_id,
                value,
                disposition="quarantined",
                reason="parent_mapping_incomplete",
            )

    for index, template, template_id in indexed["TripPlanTemplate"]:
        if template.get("status") == "archived":
            disposition = "archived"
            reason = "source_template_archived"
        else:
            disposition = "not_applicable"
            reason = "canonical_target_plan_template_contract_unavailable"
        records_by_key[("TripPlanTemplate", index)] = _mapping_record(
            "TripPlanTemplate",
            template_id,
            template,
            disposition=disposition,
            reason=reason,
        )

    for object_type in SOURCE_OBJECT_TYPES:
        for index, value, object_id in indexed[object_type]:
            key = (object_type, index)
            if key not in records_by_key:
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="quarantined",
                    reason="unmapped_source_object",
                )
                blockers.append(
                    _safe_blocker(
                        "UNMAPPED_SOURCE_OBJECT",
                        object_type=object_type,
                        object_id=object_id,
                        reason="source object has no completed disposition rule",
                    )
                )

    records = tuple(
        records_by_key[key]
        for key in sorted(records_by_key, key=lambda item: (item[0], item[1]))
    )
    canonical_target_ids = set(target_contract.object_ids)
    for record in records:
        for target_ref in record["targetRefs"]:
            object_type = str(target_ref.get("objectType") or "")
            if object_type not in canonical_target_ids:
                blockers.append(
                    _safe_blocker(
                        "NON_CANONICAL_TARGET_KIND",
                        object_type=str(record["sourceObjectType"]),
                        reason=f"target ref {object_type!r} is absent from ContractGraph",
                    )
                )
    for wrapper in documents:
        object_type = str(wrapper.get("kind") or "")
        if object_type not in canonical_target_ids:
            blockers.append(
                _safe_blocker(
                    "NON_CANONICAL_TARGET_KIND",
                    reason=f"target document {object_type!r} is absent from ContractGraph",
                )
            )
    quarantined = [
        record for record in records if record["disposition"] == "quarantined"
    ]
    if quarantined:
        blockers.append(
            _safe_blocker(
                "QUARANTINED_SOURCE_OBJECTS",
                reason=f"{len(quarantined)} source objects are quarantined",
            )
        )
    for category, bucket in conflicts.items():
        if bucket["count"]:
            blockers.append(
                _safe_blocker(
                    "MIGRATION_COLLISION",
                    reason=f"{category} conflicts: {bucket['count']}",
                )
            )
    validation = {
        "gatheringSchema": {
            "contractDigest": target_contract.digest,
            "validatedDocumentCount": len(
                [
                    value
                    for value in documents
                    if value.get("kind") == "circle.gathering"
                ]
            ),
            "errorCount": len(validation_errors),
            "errors": validation_errors,
        },
        "gatheringPlanSchema": {
            "validatedDocumentCount": len(
                [
                    value
                    for value in documents
                    if value.get("kind") == "circle.gathering_plan"
                ]
            ),
            "errorCount": len(plan_validation_errors),
            "errors": plan_validation_errors,
            "targetContractStatus": "canonical_generated_contract",
        },
    }
    return MappingResult(
        documents=tuple(
            sorted(
                documents,
                key=lambda value: (
                    str(value.get("kind") or ""),
                    canonical_digest(value.get("document")),
                ),
            )
        ),
        records=records,
        conflicts=conflicts,
        blockers=_dedupe_blockers(blockers),
        validation=validation,
    )


def _dimension_projection(
    documents: Sequence[Mapping[str, Any]],
    dimension: str,
) -> Any:
    by_kind: dict[str, list[Mapping[str, Any]]] = {}
    for wrapper in documents:
        kind = str(wrapper.get("kind") or "")
        document = wrapper.get("document")
        if kind and isinstance(document, dict):
            by_kind.setdefault(kind, []).append(document)
    if dimension == "identity":
        return {
            kind: sorted(
                canonical_digest(
                    {
                        key: document.get(key)
                        for key in (
                            "_id",
                            "gatheringId",
                        )
                        if key in document
                    }
                )
                for document in values
            )
            for kind, values in sorted(by_kind.items())
        }
    if dimension == "count":
        return {kind: len(values) for kind, values in sorted(by_kind.items())}
    if dimension == "state":
        return sorted(
            (
                document.get("_id"),
                document.get("lifecycleStatus"),
                document.get("currentGatheringRevisionId"),
                document.get("currentGatheringRevisionNumber"),
            )
            for document in by_kind.get("circle.gathering", [])
        )
    if dimension == "host":
        return sorted(
            canonical_digest(
                {
                    "gatheringId": document.get("_id"),
                    "hostBinding": document.get("hostBinding"),
                    "organizerAssignments": document.get("organizerAssignments"),
                }
            )
            for document in by_kind.get("circle.gathering", [])
        )
    if dimension == "membership":
        return sorted(
            canonical_digest(
                {
                    "gatheringId": document.get("_id"),
                    "participations": document.get("participations"),
                }
            )
            for document in by_kind.get("circle.gathering", [])
        )
    if dimension == "plan":
        return sorted(
            canonical_digest(document)
            for document in by_kind.get("circle.gathering_plan", [])
        )
    if dimension == "contentRefs":
        refs: list[dict[str, str]] = []
        for plan in by_kind.get("circle.gathering_plan", []):
            for revision in plan.get("revisions", []):
                if not isinstance(revision, dict):
                    continue
                for item in revision.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    for ref in item.get("sourceRefs", []):
                        if (
                            isinstance(ref, dict)
                            and ref.get("objectTypeRef") == "content.Post"
                        ):
                            refs.append(
                                {
                                    "objectTypeRef": "content.Post",
                                    "objectId": str(ref.get("objectId") or ""),
                                }
                            )
        return sorted(canonical_digest(ref) for ref in refs)
    if dimension == "outcome":
        return sorted(
            canonical_digest(
                {
                    "gatheringId": document.get("_id"),
                    "outcome": document.get("outcome"),
                    "completedAt": document.get("completedAt"),
                }
            )
            for document in by_kind.get("circle.gathering", [])
        )
    raise ValueError(f"unsupported parity dimension: {dimension}")


def build_parity(
    expected_documents: Sequence[Mapping[str, Any]],
    observed_documents: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    dimensions = (
        "identity",
        "count",
        "state",
        "host",
        "membership",
        "plan",
        "contentRefs",
        "outcome",
    )
    if observed_documents is None:
        return {
            "status": "not_executed",
            "percentage": 0,
            "dimensions": {
                dimension: {
                    "matched": False,
                    "expectedDigest": canonical_digest(
                        _dimension_projection(expected_documents, dimension)
                    ),
                    "observedDigest": "",
                }
                for dimension in dimensions
            },
        }
    result: dict[str, Any] = {}
    matched = 0
    for dimension in dimensions:
        expected = _dimension_projection(expected_documents, dimension)
        observed = _dimension_projection(observed_documents, dimension)
        is_match = expected == observed
        matched += int(is_match)
        result[dimension] = {
            "matched": is_match,
            "expectedDigest": canonical_digest(expected),
            "observedDigest": canonical_digest(observed),
        }
    percentage = (matched * 100) // len(dimensions)
    return {
        "status": "passed" if percentage == 100 else "GATE_BLOCK",
        "percentage": percentage,
        "dimensions": result,
    }


def _disposition_summary(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total = {disposition: 0 for disposition in DISPOSITIONS}
    by_type: dict[str, dict[str, int]] = {}
    for record in records:
        object_type = str(record["sourceObjectType"])
        disposition = str(record["disposition"])
        total[disposition] += 1
        by_type.setdefault(
            object_type,
            {candidate: 0 for candidate in DISPOSITIONS},
        )[disposition] += 1
    return {
        "counts": total,
        "bySourceObjectType": {key: by_type[key] for key in sorted(by_type)},
    }


def _availability_sections() -> tuple[dict[str, Any], dict[str, Any]]:
    cutover = {
        "status": "available",
        "gate": "external_approval_required",
        "requiredEvidence": [
            "passed inventory migration receipt",
            "passed 100% parity migration receipt",
            "signed target_backup evidence",
            "signed source_write_freeze evidence",
            "signed target_command_import evidence",
            "signed protected_environment_approval evidence",
            "configuration candidate digest",
        ],
        "bypassSupported": False,
        "environmentWritesExecutedByControlPlane": False,
        "sourceWriteRecoveryAllowed": False,
    }
    rollback = {
        "status": "available",
        "gate": "external_approval_required",
        "requiredEvidence": [
            "approved cutover migration receipt",
            "signed protected_environment_approval evidence",
            "signed target_restore evidence",
            "passed post-restore parity migration receipt",
            "rollback candidate digest",
        ],
        "bypassSupported": False,
        "environmentWritesExecutedByControlPlane": False,
        "sourceWriteRecoveryAllowed": False,
    }
    return cutover, rollback


def _validate_control_write_set(
    write_set: Any,
    *,
    phase: str,
) -> list[dict[str, Any]]:
    if not isinstance(write_set, list):
        raise MigrationControlError(
            "WRITE_SET_INVALID",
            "writeSet must be a list",
        )
    normalized: list[dict[str, Any]] = []
    expected_fields = {
        "stepId",
        "plane",
        "service",
        "operation",
        "candidateDigest",
        "executionMode",
    }
    for index, value in enumerate(write_set):
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise MigrationControlError(
                "WRITE_SET_INVALID",
                f"writeSet[{index}] fields are invalid",
            )
        plane = str(value.get("plane") or "")
        service = str(value.get("service") or "")
        operation = str(value.get("operation") or "")
        if plane not in SAFE_WRITE_PLANES:
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                f"writeSet[{index}] plane {plane!r} is forbidden",
            )
        if service == "travel-service" or "source" in plane:
            raise MigrationControlError(
                "SOURCE_WRITE_FORBIDDEN",
                "travel source writes and source write recovery are forbidden",
            )
        if service not in TARGET_WRITE_SERVICES:
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                f"writeSet[{index}] service {service!r} is not a target owner",
            )
        lowered = f"{plane} {service} {operation}".lower()
        if any(
            token in lowered
            for token in (
                "database",
                "direct_db",
                "mongo",
                "projection_write",
                "raw_sql",
                "dual_write",
            )
        ):
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                "direct target database/projection and dual writes are forbidden",
            )
        _require_nonblank(value.get("stepId"), label=f"writeSet[{index}].stepId")
        _require_nonblank(service, label=f"writeSet[{index}].service")
        _require_nonblank(operation, label=f"writeSet[{index}].operation")
        _require_digest(
            value.get("candidateDigest"),
            label=f"writeSet[{index}].candidateDigest",
        )
        execution_mode = str(value.get("executionMode") or "")
        if execution_mode not in {
            "external_approval_only",
            "externally_executed",
        }:
            raise MigrationControlError(
                "WRITE_SET_INVALID",
                f"writeSet[{index}].executionMode is invalid",
            )
        normalized.append(dict(value))
    if phase in EVIDENCE_PHASES and normalized:
        raise MigrationControlError(
            "WRITE_SET_INVALID",
            f"{phase} receipts may not contain environment writes",
        )
    if phase in CONTROL_PHASES and not normalized:
        raise MigrationControlError(
            "WRITE_SET_INVALID",
            f"{phase} receipt must declare its target-only writeSet",
        )
    return normalized


def _load_migration_receipt(
    path: Path,
    *,
    environment: str,
    phase: str,
) -> dict[str, Any]:
    receipt = _load_object(path, label=f"{phase} migration receipt")
    validate_receipt(receipt)
    if receipt.get("environment") != environment:
        raise MigrationControlError(
            "RECEIPT_ENV_MISMATCH",
            f"{phase} receipt environment does not match --env",
        )
    if receipt.get("phase") != phase:
        raise MigrationControlError(
            "RECEIPT_PHASE_MISMATCH",
            f"expected {phase} migration receipt",
        )
    if receipt.get("status") != "passed":
        raise MigrationControlError(
            "UPSTREAM_RECEIPT_BLOCKED",
            f"{phase} migration receipt is not passed",
        )
    if receipt.get("blockers"):
        raise MigrationControlError(
            "UPSTREAM_RECEIPT_BLOCKED",
            f"{phase} migration receipt contains blockers",
        )
    conflicts = receipt.get("conflicts")
    if not isinstance(conflicts, dict) or conflicts.get("totalCount") != 0:
        raise MigrationControlError(
            "MIGRATION_COLLISION",
            f"{phase} migration receipt contains collisions",
        )
    dispositions = receipt.get("dispositions")
    counts = dispositions.get("counts") if isinstance(dispositions, dict) else None
    if not isinstance(counts, dict) or counts.get("quarantined") != 0:
        raise MigrationControlError(
            "QUARANTINED_SOURCE_OBJECTS",
            f"{phase} migration receipt contains quarantined objects",
        )
    if phase == "parity":
        parity = receipt.get("parity")
        if (
            not isinstance(parity, dict)
            or parity.get("status") != "passed"
            or parity.get("percentage") != 100
        ):
            raise MigrationControlError(
                "PARITY_NOT_100_PERCENT",
                "parity receipt must prove 100% parity",
            )
    return receipt


def _assert_receipt_chain(
    inventory_receipt: Mapping[str, Any],
    parity_receipt: Mapping[str, Any],
) -> None:
    comparisons = (
        ("source.snapshotDigest", inventory_receipt["source"], parity_receipt["source"]),
        (
            "target.generatedContractDigest",
            inventory_receipt["target"],
            parity_receipt["target"],
        ),
        ("mapping.targetDocumentDigest", inventory_receipt["mapping"], parity_receipt["mapping"]),
    )
    keys = {
        "source.snapshotDigest": "snapshotDigest",
        "target.generatedContractDigest": "generatedContractDigest",
        "mapping.targetDocumentDigest": "targetDocumentDigest",
    }
    for label, left, right in comparisons:
        key = keys[label]
        if left.get(key) != right.get(key):
            raise MigrationControlError(
                "RECEIPT_CHAIN_DIGEST_MISMATCH",
                f"{label} differs between inventory and parity receipts",
            )
    if inventory_receipt.get("crosswalkDigest") != parity_receipt.get(
        "crosswalkDigest"
    ):
        raise MigrationControlError(
            "RECEIPT_CHAIN_DIGEST_MISMATCH",
            "crosswalkDigest differs between inventory and parity receipts",
        )
    if canonical_digest(inventory_receipt.get("inventory")) != canonical_digest(
        parity_receipt.get("inventory")
    ):
        raise MigrationControlError(
            "RECEIPT_CHAIN_DIGEST_MISMATCH",
            "inventory evidence differs between inventory and parity receipts",
        )


def _validate_external_evidence_write_set(
    evidence: Mapping[str, Any],
    *,
    target_contract: TargetContractBinding,
) -> None:
    evidence_type = str(evidence.get("evidenceType") or "")
    write_set = evidence.get("writeSet")
    if not isinstance(write_set, list):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.writeSet must be a list",
        )
    if evidence_type not in {
        "target_command_import",
        "target_config_activation",
        "target_restore",
    }:
        if write_set:
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_INVALID",
                f"{evidence_type} evidence may not declare writes",
            )
        return
    if not write_set:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type} evidence must declare its externally executed writeSet",
        )
    canonical_objects = set(target_contract.object_ids)
    for index, value in enumerate(write_set):
        if not isinstance(value, dict):
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_INVALID",
                f"{evidence_type}.writeSet[{index}] must be an object",
            )
        plane = str(value.get("plane") or "")
        service = str(value.get("service") or "")
        operation_id = str(value.get("operationId") or "")
        target_object_id = str(value.get("targetObjectId") or "")
        lowered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).lower()
        if service == "travel-service" or plane.startswith("source"):
            raise MigrationControlError(
                "SOURCE_WRITE_FORBIDDEN",
                "external evidence contains a travel source write",
            )
        if service not in TARGET_WRITE_SERVICES:
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                f"external write service {service!r} is not a target owner",
            )
        if any(
            token in lowered
            for token in (
                "database",
                "direct_db",
                "mongo",
                "projection_write",
                "raw_sql",
                "dual_write",
            )
        ):
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                "external evidence contains direct database/projection or dual write",
            )
        if evidence_type == "target_command_import":
            if plane not in {"target_command", "target_import"}:
                raise MigrationControlError(
                    "DIRECT_TARGET_WRITE_FORBIDDEN",
                    "target data may only be applied through canonical command/import",
                )
            if target_object_id not in canonical_objects:
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_KIND",
                    f"external target kind {target_object_id!r} is not canonical",
                )
            expected_service = {
                "chat": "chat-service",
                "circle": "circle-service",
                "content": "content-service",
            }.get(target_object_id.partition(".")[0])
            if service != expected_service:
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_OPERATION",
                    "external target service does not own targetObjectId",
                )
            if plane == "target_command" and operation_id not in set(
                REQUIRED_TARGET_OPERATION_IDS
            ):
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_OPERATION",
                    f"external target operation {operation_id!r} is not canonical",
                )
        elif evidence_type == "target_config_activation":
            if plane != "target_config" or target_object_id not in canonical_objects:
                raise MigrationControlError(
                    "CONFIG_ACTIVATION_WRITE_SET_MISMATCH",
                    "config activation evidence must target canonical target config",
                )
        else:
            if plane not in SAFE_WRITE_PLANES:
                raise MigrationControlError(
                    "DIRECT_TARGET_WRITE_FORBIDDEN",
                    "rollback restore may only target app/config/snapshot planes",
                )
            if target_object_id and target_object_id not in canonical_objects:
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_KIND",
                    f"rollback target kind {target_object_id!r} is not canonical",
                )
        _require_nonblank(service, label=f"{evidence_type}.writeSet[{index}].service")
        _require_nonblank(
            operation_id,
            label=f"{evidence_type}.writeSet[{index}].operationId",
        )
        _require_digest(
            value.get("commandReceiptDigest"),
            label=f"{evidence_type}.writeSet[{index}].commandReceiptDigest",
        )


def _load_operational_evidence(
    path: Path,
    *,
    environment: str,
    evidence_type: str,
    expected_digests: Mapping[str, str],
    target_contract: TargetContractBinding,
) -> dict[str, Any]:
    evidence = _load_object(path, label=f"{evidence_type} operational evidence")
    required = {
        "schema",
        "migrationId",
        "environment",
        "evidenceType",
        "status",
        "issuedAt",
        "subjectDigests",
        "writeSet",
        "claims",
        "signature",
        "evidenceDigest",
    }
    if set(evidence) != required:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type} evidence fields are invalid",
        )
    if (
        evidence.get("schema") != OPERATIONAL_EVIDENCE_SCHEMA
        or evidence.get("migrationId") != MIGRATION_ID
        or evidence.get("environment") != environment
        or evidence.get("evidenceType") != evidence_type
        or evidence.get("status") != "passed"
    ):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type} evidence identity/status is invalid",
        )
    _parse_timestamp(evidence.get("issuedAt"), label=f"{evidence_type}.issuedAt")
    subject_digests = evidence.get("subjectDigests")
    if not isinstance(subject_digests, dict):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.subjectDigests must be an object",
        )
    for key, value in subject_digests.items():
        _require_digest(value, label=f"{evidence_type}.subjectDigests.{key}")
    for key, expected in expected_digests.items():
        if subject_digests.get(key) != expected:
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_DIGEST_MISMATCH",
                f"{evidence_type} evidence digest mismatch: {key}",
            )
    signature = evidence.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "algorithm",
        "keyId",
        "signatureDigest",
        "verificationReceiptDigest",
    }:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.signature is invalid",
        )
    if signature.get("algorithm") not in {
        "ed25519",
        "ecdsa_p256_sha256",
        "rsa_pss_sha256",
    }:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.signature algorithm is invalid",
        )
    _require_nonblank(signature.get("keyId"), label=f"{evidence_type}.signature.keyId")
    _require_digest(
        signature.get("signatureDigest"),
        label=f"{evidence_type}.signature.signatureDigest",
    )
    _require_digest(
        signature.get("verificationReceiptDigest"),
        label=f"{evidence_type}.signature.verificationReceiptDigest",
    )
    expected_evidence_digest = canonical_digest(
        {key: value for key, value in evidence.items() if key != "evidenceDigest"}
    )
    if evidence.get("evidenceDigest") != expected_evidence_digest:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_DIGEST_MISMATCH",
            f"{evidence_type} canonical evidence digest mismatch",
        )
    claims = evidence.get("claims")
    if not isinstance(claims, dict):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.claims must be an object",
        )
    required_claims: dict[str, Any] = {
        "target_backup": {
            "backupScope": "target_only",
            "restorable": True,
        },
        "source_write_freeze": {
            "sourceWriteState": "frozen_permanently",
            "sourceWriteRecoveryAllowed": False,
            "dualWriteEnabled": False,
        },
        "target_command_import": {
            "executionPath": {"canonical_commands", "canonical_importer"},
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
            "sourceWrite": False,
        },
        "protected_environment_approval": {
            "decision": "approved",
            "protectedEnvironmentWritesApproved": True,
        },
        "target_config_activation": {
            "targetActivated": True,
            "sourceRuntimeDecommissioned": True,
            "sourceTrafficMode": "disabled",
            "sourceFallbackEnabled": False,
            "sourceWriteRecoveryAllowed": False,
        },
        "target_restore": {
            "targetRestored": True,
            "sourceWrite": False,
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
        },
    }[evidence_type]
    for key, expected in required_claims.items():
        actual = claims.get(key)
        if isinstance(expected, set):
            matched = actual in expected
        else:
            matched = actual == expected
        if not matched:
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_INVALID",
                f"{evidence_type} claim is invalid: {key}",
            )
    _validate_external_evidence_write_set(
        evidence,
        target_contract=target_contract,
    )
    return evidence


def _evidence_ref(evidence: Mapping[str, Any]) -> dict[str, Any]:
    signature = evidence["signature"]
    return {
        "evidenceType": evidence["evidenceType"],
        "evidenceDigest": evidence["evidenceDigest"],
        "issuedAt": evidence["issuedAt"],
        "signatureDigest": signature["signatureDigest"],
        "verificationReceiptDigest": signature["verificationReceiptDigest"],
        "writeSetDigest": canonical_digest(evidence["writeSet"]),
    }


def _seal_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    stable = dict(payload)
    seed = canonical_digest(stable).removeprefix("sha256:")
    receipt_id = f"{MIGRATION_ID}:{stable['environment']}:{stable['phase']}:{seed}"
    with_id = {**stable, "receiptId": receipt_id}
    return {**with_id, "receiptDigest": canonical_digest(with_id)}


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "migrationId",
        "command",
        "environment",
        "phase",
        "status",
        "executionMode",
        "source",
        "target",
        "crosswalkDigest",
        "inventory",
        "mapping",
        "dispositions",
        "conflicts",
        "blockers",
        "piiRedaction",
        "validation",
        "parity",
        "writeSet",
        "cutover",
        "rollback",
        "receiptId",
        "receiptDigest",
    }
    if set(receipt) != required:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "migration receipt fields do not match canonical schema",
        )
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt schema mismatch"
        )
    if receipt.get("migrationId") != MIGRATION_ID:
        raise MigrationControlError("RECEIPT_INVALID", "migration receipt id mismatch")
    if receipt.get("environment") not in ENVIRONMENTS:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "migration receipt environment is invalid",
        )
    if receipt.get("phase") not in PHASES:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt phase is invalid"
        )
    if receipt.get("status") not in {"passed", "GATE_BLOCK"}:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt status is invalid"
        )
    execution_mode = receipt.get("executionMode")
    if execution_mode not in {
        "read_only",
        "zero_write",
        "approval_plan",
        "external_evidence_only",
    }:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "migration receipt executionMode is invalid",
        )
    _validate_control_write_set(
        receipt.get("writeSet"),
        phase=str(receipt["phase"]),
    )
    if receipt["phase"] in EVIDENCE_PHASES and execution_mode not in {
        "read_only",
        "zero_write",
    }:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "evidence receipt executionMode is invalid",
        )
    if receipt["phase"] in CONTROL_PHASES and execution_mode not in {
        "approval_plan",
        "external_evidence_only",
    }:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "control receipt executionMode is invalid",
        )
    expected_digest = canonical_digest(
        {key: value for key, value in receipt.items() if key != "receiptDigest"}
    )
    if receipt.get("receiptDigest") != expected_digest:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt digest mismatch"
        )


def build_receipt(
    *,
    environment: str,
    phase: str,
    snapshot: Mapping[str, Any],
    target_contract: TargetContractBinding,
    mapping: MappingResult,
    target_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    crosswalk = _load_object(CROSSWALK_PATH, label="travel-to-gathering crosswalk")
    inventory = build_inventory(snapshot)
    parity = build_parity(
        mapping.documents,
        (
            target_snapshot.get("documents")
            if isinstance(target_snapshot, dict)
            else None
        ),
    )
    blockers = list(mapping.blockers)
    if phase == "parity" and parity["percentage"] != 100:
        blockers.append(
            _safe_blocker(
                "PARITY_NOT_100_PERCENT",
                reason="all identity/count/state/host/membership/plan/contentRefs/outcome dimensions must match",
            )
        )
    quarantined_count = sum(
        1 for record in mapping.records if record["disposition"] == "quarantined"
    )
    gate_blocked = bool(blockers) or quarantined_count > 0
    if phase == "parity" and parity["percentage"] != 100:
        gate_blocked = True
    cutover, rollback = _availability_sections()
    source = snapshot["source"]
    stable = {
        "schema": RECEIPT_SCHEMA,
        "migrationId": MIGRATION_ID,
        "command": COMMAND_NAME,
        "environment": environment,
        "phase": phase,
        "status": "GATE_BLOCK" if gate_blocked else "passed",
        "executionMode": "read_only"
        if phase in {"inventory", "parity"}
        else "zero_write",
        "source": {
            "service": source["service"],
            "releaseId": source["releaseId"],
            "serviceImageDigest": source["serviceImageDigest"],
            "configDigest": source["configDigest"],
            "snapshotDigest": snapshot["snapshotDigest"],
            "capturedAt": snapshot["capturedAt"],
        },
        "target": {
            "services": [
                "chat-service",
                "circle-service",
                "content-service",
            ],
            "objectIds": list(target_contract.object_ids),
            "generatedContractDigest": target_contract.digest,
            "contractGraphDigest": target_contract.graph_digest,
            "generatedArtifactDigest": target_contract.generated_artifact_digest,
            "contractSources": list(target_contract.sources),
            "snapshotDigest": (
                target_snapshot.get("snapshotDigest")
                if isinstance(target_snapshot, dict)
                else ""
            ),
        },
        "crosswalkDigest": canonical_digest(crosswalk),
        "inventory": inventory,
        "mapping": {
            "recordCount": len(mapping.records),
            "records": list(mapping.records),
            "targetDocumentCount": len(mapping.documents),
            "targetDocumentDigest": canonical_digest(mapping.documents),
            "targetDocumentsEmitted": False,
        },
        "dispositions": _disposition_summary(mapping.records),
        "conflicts": {
            "totalCount": sum(value["count"] for value in mapping.conflicts.values()),
            "categories": mapping.conflicts,
        },
        "blockers": list(_dedupe_blockers(blockers)),
        "piiRedaction": _pii_redaction_report(snapshot),
        "validation": mapping.validation,
        "parity": parity,
        "writeSet": [],
        "cutover": cutover,
        "rollback": rollback,
    }
    receipt = _seal_receipt(stable)
    validate_receipt(receipt)
    return receipt


def _control_receipt_base(
    upstream: Mapping[str, Any],
    *,
    phase: str,
    status: str,
    blockers: Sequence[Mapping[str, Any]],
    write_set: Sequence[Mapping[str, Any]],
    cutover: Mapping[str, Any],
    rollback: Mapping[str, Any],
) -> dict[str, Any]:
    stable = {
        "schema": RECEIPT_SCHEMA,
        "migrationId": MIGRATION_ID,
        "command": COMMAND_NAME,
        "environment": upstream["environment"],
        "phase": phase,
        "status": status,
        "executionMode": (
            "approval_plan" if status == "GATE_BLOCK" else "external_evidence_only"
        ),
        "source": upstream["source"],
        "target": upstream["target"],
        "crosswalkDigest": upstream["crosswalkDigest"],
        "inventory": upstream["inventory"],
        "mapping": upstream["mapping"],
        "dispositions": upstream["dispositions"],
        "conflicts": upstream["conflicts"],
        "blockers": list(_dedupe_blockers(dict(value) for value in blockers)),
        "piiRedaction": upstream["piiRedaction"],
        "validation": upstream["validation"],
        "parity": upstream["parity"],
        "writeSet": [dict(value) for value in write_set],
        "cutover": dict(cutover),
        "rollback": dict(rollback),
    }
    receipt = _seal_receipt(stable)
    validate_receipt(receipt)
    return receipt


def build_cutover_receipt(
    *,
    environment: str,
    inventory_receipt: Mapping[str, Any],
    parity_receipt: Mapping[str, Any],
    target_contract: TargetContractBinding,
    target_backup_evidence: Mapping[str, Any],
    source_freeze_evidence: Mapping[str, Any],
    target_command_evidence: Mapping[str, Any],
    config_candidate_digest: str,
    approval_evidence: Mapping[str, Any] | None,
    activation_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if (
        inventory_receipt.get("environment") != environment
        or parity_receipt.get("environment") != environment
        or any(
            evidence.get("environment") != environment
            for evidence in (
                target_backup_evidence,
                source_freeze_evidence,
                target_command_evidence,
            )
        )
        or (
            approval_evidence is not None
            and approval_evidence.get("environment") != environment
        )
        or (
            activation_evidence is not None
            and activation_evidence.get("environment") != environment
        )
    ):
        raise MigrationControlError(
            "RECEIPT_ENV_MISMATCH",
            "cutover receipt/evidence environments must match",
        )
    _assert_receipt_chain(inventory_receipt, parity_receipt)
    if parity_receipt["target"].get("generatedContractDigest") != target_contract.digest:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISMATCH",
            "parity target contract differs from current canonical contracts",
        )
    config_candidate_digest = _require_digest(
        config_candidate_digest,
        label="config candidate digest",
    )
    write_set = [
        {
            "stepId": "cutover.activate-target-only-config",
            "plane": "target_config",
            "service": "circle-service",
            "operation": "activate_target_only_candidate",
            "candidateDigest": config_candidate_digest,
            "executionMode": "external_approval_only",
        }
    ]
    write_set_digest = canonical_digest(write_set)
    blockers: list[dict[str, Any]] = []
    approval_ref: dict[str, Any] | None = None
    activation_ref: dict[str, Any] | None = None
    if approval_evidence is None:
        blockers.append(
            _safe_blocker(
                "PROTECTED_ENVIRONMENT_APPROVAL_REQUIRED",
                reason="target config activation requires signed external approval",
            )
        )
    else:
        approval_ref = _evidence_ref(approval_evidence)
    if activation_evidence is None:
        blockers.append(
            _safe_blocker(
                "TARGET_CONFIG_ACTIVATION_EVIDENCE_REQUIRED",
                reason="control plane never executes protected target config writes",
            )
        )
    else:
        activation_ref = _evidence_ref(activation_evidence)
    cutover = {
        "status": (
            "externally_executed"
            if not blockers
            else "external_execution_required"
        ),
        "targetOnly": True,
        "sourceWriteState": "frozen_permanently",
        "sourceWriteRecoveryAllowed": False,
        "sourceFallbackAllowed": False,
        "sourceTrafficMode": "disabled",
        "sourceRuntimeRecoveryAllowed": False,
        "dualReadAllowed": False,
        "dualWriteAllowed": False,
        "targetDataApplication": _evidence_ref(target_command_evidence),
        "evidence": {
            "inventoryReceiptDigest": inventory_receipt["receiptDigest"],
            "parityReceiptDigest": parity_receipt["receiptDigest"],
            "targetBackup": _evidence_ref(target_backup_evidence),
            "sourceWriteFreeze": _evidence_ref(source_freeze_evidence),
            "protectedEnvironmentApproval": approval_ref,
            "targetConfigActivation": activation_ref,
        },
        "configActivationPlan": {
            "candidateDigest": config_candidate_digest,
            "writeSetDigest": write_set_digest,
            "activateTargetReads": True,
            "decommissionSourceRuntime": True,
            "sourceTrafficMode": "disabled",
            "sourceFallbackAllowed": False,
            "sourceWriteRecoveryAllowed": False,
            "executedByControlPlane": False,
        },
        "approvalRequirement": {
            "required": True,
            "status": "approved" if approval_ref else "missing",
            "writeSetDigest": write_set_digest,
            "bypassSupported": False,
        },
    }
    _, rollback = _availability_sections()
    return _control_receipt_base(
        parity_receipt,
        phase="cutover",
        status="GATE_BLOCK" if blockers else "passed",
        blockers=blockers,
        write_set=write_set,
        cutover=cutover,
        rollback=rollback,
    )


def build_rollback_receipt(
    *,
    cutover_receipt: Mapping[str, Any],
    post_restore_parity_receipt: Mapping[str, Any],
    target_contract: TargetContractBinding,
    rollback_mode: str,
    rollback_candidate_digest: str,
    approval_evidence: Mapping[str, Any],
    restore_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if rollback_mode not in ROLLBACK_MODES:
        raise MigrationControlError(
            "ROLLBACK_MODE_INVALID",
            f"rollback mode must be one of {ROLLBACK_MODES}",
        )
    if (
        cutover_receipt.get("status") != "passed"
        or cutover_receipt.get("cutover", {}).get("status")
        != "externally_executed"
    ):
        raise MigrationControlError(
            "CUTOVER_RECEIPT_NOT_EXECUTED",
            "rollback requires a passed externally-executed cutover receipt",
        )
    if (
        post_restore_parity_receipt["source"].get("snapshotDigest")
        != cutover_receipt["source"].get("snapshotDigest")
        or post_restore_parity_receipt["target"].get("generatedContractDigest")
        != cutover_receipt["target"].get("generatedContractDigest")
        or post_restore_parity_receipt.get("crosswalkDigest")
        != cutover_receipt.get("crosswalkDigest")
        or post_restore_parity_receipt["mapping"].get("targetDocumentDigest")
        != cutover_receipt["mapping"].get("targetDocumentDigest")
    ):
        raise MigrationControlError(
            "POST_RESTORE_PARITY_DIGEST_MISMATCH",
            "post-restore parity does not reconcile the approved cutover data set",
        )
    if cutover_receipt["target"].get("generatedContractDigest") != target_contract.digest:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISMATCH",
            "rollback target contract differs from current canonical contracts",
        )
    rollback_candidate_digest = _require_digest(
        rollback_candidate_digest,
        label="rollback candidate digest",
    )
    if rollback_mode == "target_application_config":
        plane = "target_config"
        operation = "restore_target_application_config"
    else:
        plane = "target_snapshot"
        operation = "restore_target_snapshot"
    write_set = [
        {
            "stepId": f"rollback.{rollback_mode}",
            "plane": plane,
            "service": "circle-service",
            "operation": operation,
            "candidateDigest": rollback_candidate_digest,
            "executionMode": "externally_executed",
        }
    ]
    write_set_digest = canonical_digest(
        [
            {
                **write_set[0],
                "executionMode": "external_approval_only",
            }
        ]
    )
    cutover, _ = _availability_sections()
    rollback = {
        "status": "externally_restored_and_parity_passed",
        "mode": rollback_mode,
        "targetOnly": True,
        "sourceWriteRecoveryAllowed": False,
        "sourceRuntimeRecoveryAllowed": False,
        "sourceFallbackAllowed": False,
        "restorePlan": {
            "candidateDigest": rollback_candidate_digest,
            "writeSetDigest": write_set_digest,
            "executedByControlPlane": False,
        },
        "approvalRequirement": {
            "required": True,
            "status": "approved",
            "writeSetDigest": write_set_digest,
            "bypassSupported": False,
        },
        "evidence": {
            "cutoverReceiptDigest": cutover_receipt["receiptDigest"],
            "protectedEnvironmentApproval": _evidence_ref(approval_evidence),
            "targetRestore": _evidence_ref(restore_evidence),
            "postRestoreParityReceiptDigest": post_restore_parity_receipt[
                "receiptDigest"
            ],
            "postRestoreTargetSnapshotDigest": post_restore_parity_receipt[
                "target"
            ].get("snapshotDigest"),
        },
    }
    return _control_receipt_base(
        post_restore_parity_receipt,
        phase="rollback",
        status="passed",
        blockers=(),
        write_set=write_set,
        cutover=cutover,
        rollback=rollback,
    )


def _ensure_output_path(path: Path) -> Path:
    root = output_root().expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise MigrationControlError(
            "OUTPUT_PATH_FORBIDDEN",
            "migration receipts may only be written under QWQ_OUTPUT_ROOT",
        ) from exc
    return resolved


def _report_dir(args: argparse.Namespace) -> Path:
    explicit = str(getattr(args, "report_dir", "") or "").strip()
    if explicit:
        return _ensure_output_path(Path(explicit))
    generated = artifact_run_dir(
        str(args.env),
        f"migration-{MIGRATION_ID}-{args.phase}",
        target="control-plane",
    )
    return _ensure_output_path(generated)


def _required_cli_path(
    args: argparse.Namespace,
    attribute: str,
    flag: str,
) -> Path:
    value = str(getattr(args, attribute, "") or "").strip()
    if not value:
        raise MigrationControlError(
            "REQUIRED_RECEIPT_MISSING",
            f"{flag} is required",
        )
    return Path(value)


def execute(
    args: argparse.Namespace,
    *,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    phase = str(args.phase)
    environment = str(args.env)
    report_dir: Path | None = None
    try:
        report_dir = _report_dir(args)
        if environment == "prod" and phase == "dry-run":
            raise MigrationControlError(
                "PROD_PHASE_FORBIDDEN",
                "prod permits read-only inventory/parity only; dry-run is GATE_BLOCK",
            )
        if phase in EVIDENCE_PHASES:
            source_snapshot_path = str(
                getattr(args, "source_snapshot", "") or ""
            ).strip()
            if not source_snapshot_path:
                raise MigrationControlError(
                    "SOURCE_SNAPSHOT_REQUIRED",
                    "--source-snapshot is required for inventory/dry-run/parity",
                )
            target_contract = resolve_target_contract(repository_root)
            snapshot = load_source_snapshot(
                Path(source_snapshot_path),
                environment=environment,
                target_contract_digest=target_contract.digest,
            )
            mapping = build_mapping(snapshot, target_contract)
            target_snapshot: dict[str, Any] | None = None
            if phase == "parity":
                target_snapshot_path = str(
                    getattr(args, "target_snapshot", "") or ""
                ).strip()
                if not target_snapshot_path:
                    raise MigrationControlError(
                        "TARGET_SNAPSHOT_REQUIRED",
                        "--target-snapshot is required for parity",
                    )
                target_snapshot = load_target_snapshot(
                    Path(target_snapshot_path),
                    environment=environment,
                    target_contract_digest=target_contract.digest,
                )
            receipt = build_receipt(
                environment=environment,
                phase=phase,
                snapshot=snapshot,
                target_contract=target_contract,
                mapping=mapping,
                target_snapshot=target_snapshot,
            )
        elif phase == "cutover":
            target_contract = resolve_target_contract(repository_root)
            inventory_receipt = _load_migration_receipt(
                _required_cli_path(
                    args,
                    "inventory_receipt",
                    "--inventory-receipt",
                ),
                environment=environment,
                phase="inventory",
            )
            parity_receipt = _load_migration_receipt(
                _required_cli_path(args, "parity_receipt", "--parity-receipt"),
                environment=environment,
                phase="parity",
            )
            _assert_receipt_chain(inventory_receipt, parity_receipt)
            common_digests = {
                "inventoryReceiptDigest": inventory_receipt["receiptDigest"],
                "parityReceiptDigest": parity_receipt["receiptDigest"],
                "sourceSnapshotDigest": parity_receipt["source"]["snapshotDigest"],
                "targetContractDigest": target_contract.digest,
                "crosswalkDigest": parity_receipt["crosswalkDigest"],
                "mappingDigest": parity_receipt["mapping"][
                    "targetDocumentDigest"
                ],
            }
            target_backup = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "target_backup_receipt",
                    "--target-backup-receipt",
                ),
                environment=environment,
                evidence_type="target_backup",
                expected_digests=common_digests,
                target_contract=target_contract,
            )
            source_freeze = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "source_freeze_receipt",
                    "--source-freeze-receipt",
                ),
                environment=environment,
                evidence_type="source_write_freeze",
                expected_digests=common_digests,
                target_contract=target_contract,
            )
            target_command = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "target_command_receipt",
                    "--target-command-receipt",
                ),
                environment=environment,
                evidence_type="target_command_import",
                expected_digests={
                    **common_digests,
                    "targetBackupEvidenceDigest": target_backup["evidenceDigest"],
                    "sourceFreezeEvidenceDigest": source_freeze["evidenceDigest"],
                },
                target_contract=target_contract,
            )
            _require_digest(
                target_command["subjectDigests"].get(
                    "protectedWriteApprovalDigest"
                ),
                label=(
                    "target_command_import.subjectDigests."
                    "protectedWriteApprovalDigest"
                ),
            )
            config_candidate_digest = _require_digest(
                getattr(args, "config_candidate_digest", ""),
                label="--config-candidate-digest",
            )
            planned_write_set = [
                {
                    "stepId": "cutover.activate-target-only-config",
                    "plane": "target_config",
                    "service": "circle-service",
                    "operation": "activate_target_only_candidate",
                    "candidateDigest": config_candidate_digest,
                    "executionMode": "external_approval_only",
                }
            ]
            planned_write_set_digest = canonical_digest(planned_write_set)
            approval_path = str(
                getattr(args, "approval_receipt", "") or ""
            ).strip()
            approval: dict[str, Any] | None = None
            if approval_path:
                approval = _load_operational_evidence(
                    Path(approval_path),
                    environment=environment,
                    evidence_type="protected_environment_approval",
                    expected_digests={
                        **common_digests,
                        "targetCommandEvidenceDigest": target_command[
                            "evidenceDigest"
                        ],
                        "configCandidateDigest": config_candidate_digest,
                        "writeSetDigest": planned_write_set_digest,
                    },
                    target_contract=target_contract,
                )
            activation_path = str(
                getattr(args, "config_activation_receipt", "") or ""
            ).strip()
            activation: dict[str, Any] | None = None
            if activation_path:
                if approval is None:
                    raise MigrationControlError(
                        "PROTECTED_ENVIRONMENT_APPROVAL_REQUIRED",
                        "config activation evidence requires prior approval evidence",
                    )
                activation = _load_operational_evidence(
                    Path(activation_path),
                    environment=environment,
                    evidence_type="target_config_activation",
                    expected_digests={
                        **common_digests,
                        "configCandidateDigest": config_candidate_digest,
                        "plannedWriteSetDigest": planned_write_set_digest,
                        "approvalEvidenceDigest": approval["evidenceDigest"],
                    },
                    target_contract=target_contract,
                )
            receipt = build_cutover_receipt(
                environment=environment,
                inventory_receipt=inventory_receipt,
                parity_receipt=parity_receipt,
                target_contract=target_contract,
                target_backup_evidence=target_backup,
                source_freeze_evidence=source_freeze,
                target_command_evidence=target_command,
                config_candidate_digest=config_candidate_digest,
                approval_evidence=approval,
                activation_evidence=activation,
            )
        elif phase == "rollback":
            target_contract = resolve_target_contract(repository_root)
            cutover_receipt = _load_migration_receipt(
                _required_cli_path(args, "cutover_receipt", "--cutover-receipt"),
                environment=environment,
                phase="cutover",
            )
            post_restore_parity = _load_migration_receipt(
                _required_cli_path(
                    args,
                    "post_restore_parity_receipt",
                    "--post-restore-parity-receipt",
                ),
                environment=environment,
                phase="parity",
            )
            rollback_mode = str(getattr(args, "rollback_mode", "") or "")
            if rollback_mode not in ROLLBACK_MODES:
                raise MigrationControlError(
                    "ROLLBACK_MODE_INVALID",
                    "--rollback-mode is required for rollback",
                )
            rollback_candidate_digest = _require_digest(
                getattr(args, "rollback_candidate_digest", ""),
                label="--rollback-candidate-digest",
            )
            planned_plane = (
                "target_config"
                if rollback_mode == "target_application_config"
                else "target_snapshot"
            )
            planned_operation = (
                "restore_target_application_config"
                if rollback_mode == "target_application_config"
                else "restore_target_snapshot"
            )
            planned_write_set_digest = canonical_digest(
                [
                    {
                        "stepId": f"rollback.{rollback_mode}",
                        "plane": planned_plane,
                        "service": "circle-service",
                        "operation": planned_operation,
                        "candidateDigest": rollback_candidate_digest,
                        "executionMode": "external_approval_only",
                    }
                ]
            )
            rollback_digests = {
                "cutoverReceiptDigest": cutover_receipt["receiptDigest"],
                "targetContractDigest": target_contract.digest,
                "crosswalkDigest": cutover_receipt["crosswalkDigest"],
                "sourceSnapshotDigest": cutover_receipt["source"][
                    "snapshotDigest"
                ],
                "rollbackCandidateDigest": rollback_candidate_digest,
                "plannedWriteSetDigest": planned_write_set_digest,
            }
            approval = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "approval_receipt",
                    "--approval-receipt",
                ),
                environment=environment,
                evidence_type="protected_environment_approval",
                expected_digests=rollback_digests,
                target_contract=target_contract,
            )
            restore = _load_operational_evidence(
                _required_cli_path(
                    args,
                    "target_restore_receipt",
                    "--target-restore-receipt",
                ),
                environment=environment,
                evidence_type="target_restore",
                expected_digests={
                    **rollback_digests,
                    "approvalEvidenceDigest": approval["evidenceDigest"],
                    "restoredTargetSnapshotDigest": post_restore_parity[
                        "target"
                    ]["snapshotDigest"],
                },
                target_contract=target_contract,
            )
            restore_planes = {
                str(value.get("plane") or "")
                for value in restore["writeSet"]
                if isinstance(value, dict)
            }
            if restore_planes != {planned_plane}:
                raise MigrationControlError(
                    "ROLLBACK_WRITE_SET_MISMATCH",
                    "target restore evidence does not match rollback mode",
                )
            receipt = build_rollback_receipt(
                cutover_receipt=cutover_receipt,
                post_restore_parity_receipt=post_restore_parity,
                target_contract=target_contract,
                rollback_mode=rollback_mode,
                rollback_candidate_digest=rollback_candidate_digest,
                approval_evidence=approval,
                restore_evidence=restore,
            )
        else:
            raise MigrationControlError(
                "MIGRATION_PHASE_INVALID",
                f"unsupported migration phase: {phase}",
            )
        receipt_path = report_dir / "receipt.json"
        write_json(receipt_path, receipt)
        write_json(
            report_dir / "report.json",
            {
                "schema": RECEIPT_SCHEMA,
                "migrationId": MIGRATION_ID,
                "environment": environment,
                "phase": phase,
                "status": receipt["status"],
                "receiptRef": relpath(receipt_path),
                "receiptDigest": receipt["receiptDigest"],
                "writeSet": receipt["writeSet"],
            },
        )
        blocked = receipt["status"] == "GATE_BLOCK"
        return {
            "exitCode": 2 if blocked else 0,
            "summary": (
                f"stackctl migration {MIGRATION_ID} {phase} is GATE_BLOCK"
                if blocked
                else f"stackctl migration {MIGRATION_ID} {phase} passed"
            ),
            "details": [
                f"receipt: {relpath(receipt_path)}",
                f"receiptDigest: {receipt['receiptDigest']}",
                "environment writes executed by control plane: 0",
                f"declared writeSet steps: {len(receipt['writeSet'])}",
            ],
            "reportDir": relpath(report_dir),
            "receiptRef": relpath(receipt_path),
            "receiptDigest": receipt["receiptDigest"],
        }
    except MigrationControlError as exc:
        if report_dir is not None:
            failure_path = report_dir / "report.json"
            write_json(
                failure_path,
                {
                    "schema": RECEIPT_SCHEMA,
                    "migrationId": MIGRATION_ID,
                    "environment": environment,
                    "phase": phase,
                    "status": "GATE_BLOCK",
                    "errorCode": exc.code,
                    "details": [str(exc)],
                    "writeSet": [],
                },
            )
        result = {
            "exitCode": 2,
            "summary": (f"stackctl migration {MIGRATION_ID} {phase} is GATE_BLOCK"),
            "details": [f"{exc.code}: {exc}", "environment writes: 0"],
        }
        if report_dir is not None:
            result["reportDir"] = relpath(report_dir)
        return result


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    migration = subparsers.add_parser(
        "migration",
        help="受控跨服务 target-only 迁移证据控制面",
    )
    migration_commands = migration.add_subparsers(
        dest="migration_command",
        required=True,
    )
    travel = migration_commands.add_parser(
        MIGRATION_ID,
        help="travel-service 到 Gathering 的 target-only 迁移控制面",
    )
    travel.add_argument("--report-dir", default=argparse.SUPPRESS)
    travel.add_argument("--env", choices=ENVIRONMENTS, required=True)
    travel.add_argument("--phase", choices=PHASES, required=True)
    travel.add_argument(
        "--source-snapshot",
        default="",
        help="显式只读 travel source snapshot；inventory/dry-run/parity 必需",
    )
    travel.add_argument(
        "--target-snapshot",
        default="",
        help="显式只读 Gathering target snapshot；parity 必需",
    )
    travel.add_argument(
        "--inventory-receipt",
        default="",
        help="已通过且摘要封存的 inventory migration receipt；cutover 必需",
    )
    travel.add_argument(
        "--parity-receipt",
        default="",
        help="100% parity migration receipt；cutover 必需",
    )
    travel.add_argument(
        "--target-backup-receipt",
        default="",
        help="签名 target-only 备份 evidence；cutover 必需",
    )
    travel.add_argument(
        "--source-freeze-receipt",
        default="",
        help="签名且不允许恢复源写的 source freeze evidence；cutover 必需",
    )
    travel.add_argument(
        "--target-command-receipt",
        default="",
        help="签名 canonical target command/import evidence；cutover 必需",
    )
    travel.add_argument(
        "--config-candidate-digest",
        default="",
        help="待激活 target-only 配置候选摘要；cutover 必需",
    )
    travel.add_argument(
        "--approval-receipt",
        default="",
        help="保护环境写入的外部签名审批 evidence；cutover/rollback 必需",
    )
    travel.add_argument(
        "--config-activation-receipt",
        default="",
        help="外部执行 target config activation 的签名 evidence；cutover 完成必需",
    )
    travel.add_argument(
        "--cutover-receipt",
        default="",
        help="已通过且外部执行完成的 cutover receipt；rollback 必需",
    )
    travel.add_argument(
        "--rollback-mode",
        choices=ROLLBACK_MODES,
        default="",
        help="仅允许 target app/config 或 target snapshot rollback",
    )
    travel.add_argument(
        "--rollback-candidate-digest",
        default="",
        help="rollback app/config 或 snapshot 候选摘要",
    )
    travel.add_argument(
        "--target-restore-receipt",
        default="",
        help="外部审批后执行 target restore 的签名 evidence",
    )
    travel.add_argument(
        "--post-restore-parity-receipt",
        default="",
        help="restore 后 100% parity migration receipt",
    )


def command(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "migration_command", "") != MIGRATION_ID:
        return {
            "exitCode": 2,
            "summary": "stackctl migration command is GATE_BLOCK",
            "details": ["unknown migration command", "environment writes: 0"],
        }
    return execute(args)


__all__ = [
    "COMMAND_NAME",
    "DISPOSITIONS",
    "ENVIRONMENTS",
    "MIGRATION_ID",
    "SOURCE_OBJECT_TYPES",
    "SOURCE_SNAPSHOT_SCHEMA",
    "TARGET_SNAPSHOT_SCHEMA",
    "MigrationControlError",
    "TargetContractBinding",
    "build_cutover_receipt",
    "build_inventory",
    "build_mapping",
    "build_parity",
    "build_receipt",
    "build_rollback_receipt",
    "canonical_digest",
    "command",
    "execute",
    "load_source_snapshot",
    "load_target_snapshot",
    "register_parser",
    "resolve_target_contract",
    "validate_gathering_document",
    "validate_receipt",
]
