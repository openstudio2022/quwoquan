"""travel-to-gathering 迁移控制面的常量、错误类型与不可变数据结构。

内容逐字来自原 ``control_plane.py`` 顶部常量区；唯一差异是 ``ROOT`` 与
``CROSSWALK_PATH`` 的路径锚点按本文件在 ``control_plane_lib/`` 子包内的
物理位置重新推导，指向的真实路径保持不变。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
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
CROSSWALK_PATH = Path(__file__).resolve().parents[1] / "crosswalk.json"

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
