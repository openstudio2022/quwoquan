"""Typed, API-only acceptance dataset contracts for local environments.

The recipes are executable code, not a business-object manifest. Paths and
methods are resolved from the generated ContractGraph so this module cannot
become another wire-contract source.

spec_ref: specs/feature-tree/spec.md#uat-007
spec_ref: specs/feature-tree/spec.md#uat-009
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_GRAPH = ROOT / "quwoquan_service/generated/contract_graph.json"
NONPROD_TARGETS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
}
PRODUCTION_ENVIRONMENT = "prod"
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


class RetentionClass(StrEnum):
    RELEASE_BOUND = "release_bound"
    CANDIDATE_BOUND = "candidate_bound"
    RUN_BOUND = "run_bound"


@dataclass(frozen=True)
class DatasetRecipe:
    dataset_id: str
    retention_class: RetentionClass
    required_actor_count: int
    operation_ids: tuple[str, ...]
    expected_counts: tuple[tuple[str, int], ...]
    spec_refs: tuple[str, ...]

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "datasetId": self.dataset_id,
            "retentionClass": self.retention_class.value,
            "requiredActorCount": self.required_actor_count,
            "operationIds": list(self.operation_ids),
            "expectedCounts": dict(self.expected_counts),
            "specRefs": list(self.spec_refs),
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


CONTENT_RELEASE_FOUNDATION = DatasetRecipe(
    dataset_id="content_release_foundation",
    retention_class=RetentionClass.RELEASE_BOUND,
    required_actor_count=0,
    operation_ids=(),
    expected_counts=(
        ("creators", 4),
        ("entities", 1),
        ("posts", 3),
        ("tags", 21),
        ("mediaAssets", 38),
    ),
    spec_refs=("specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",),
)

NONPROD_REFERENCE_IDENTITY = DatasetRecipe(
    dataset_id="nonprod_reference_identity",
    retention_class=RetentionClass.CANDIDATE_BOUND,
    required_actor_count=6,
    operation_ids=(
        "user.authentication_challenge.SendOtp",
        "user.account_session.LoginWithPhone",
        "user.persona.CreatePersona",
        "user.persona_relationship.FollowUser",
        "user.greeting_request.SendGreetingRequest",
        "user.greeting_request.ReplyGreetingRequest",
        "user.greeting_request.IgnoreGreetingRequest",
        "user.persona_relationship.BlockUser",
        "user.persona_relationship.UnblockUser",
        "user.user_account.CloseAccount",
    ),
    expected_counts=(
        ("accounts", 6),
        ("personas", 7),
        ("followDirections", 8),
        ("mutualPairs", 1),
        ("greetingStates", 3),
        ("blockRecoveryScenarios", 1),
    ),
    spec_refs=(
        "specs/feature-tree/spec.md#uat-007",
        "specs/feature-tree/spec.md#uat-009",
    ),
)

NONPROD_REFERENCE_CONTENT_INTERACTION = DatasetRecipe(
    dataset_id="nonprod_reference_content_interaction",
    retention_class=RetentionClass.CANDIDATE_BOUND,
    required_actor_count=6,
    operation_ids=(
        "content.comment.CreateComment",
        "content.comment.DeleteComment",
        "content.comment.ListComments",
        "content.comment.ListCommentReplies",
        "content.comment.BindMediaAssetsToComment",
        "content.media_upload_session.InitMediaUpload",
        "content.media_upload_session.CompleteMediaUpload",
        "content.media_asset.GetMediaAsset",
        "content.content_reaction.LikePost",
        "content.content_reaction.UnlikePost",
        "content.content_reaction.ReactToComment",
        "content.outbound_share_fact.CreateOutboundShare",
    ),
    expected_counts=(
        ("activeComments", 34),
        ("postALevelOneComments", 21),
        ("postAReplies", 11),
        ("postBComments", 2),
        ("postCLegalEmptyComments", 0),
        ("postLikes", 8),
        ("commentReactions", 6),
        ("shares", 3),
        ("deletedCommentTombstones", 1),
    ),
    spec_refs=(
        "specs/feature-tree/spec.md#uat-009",
        "specs/feature-tree/discovery-content/spec.md#dom-001",
    ),
)

NONPROD_REFERENCE_CIRCLE_CHAT = DatasetRecipe(
    dataset_id="nonprod_reference_circle_chat",
    retention_class=RetentionClass.CANDIDATE_BOUND,
    required_actor_count=6,
    operation_ids=(
        "circle.circle.CreateCircle",
        "circle.circle.GetCircle",
        "circle.circle_membership.JoinCircle",
        "circle.circle_membership.ApproveCircleMember",
        "circle.circle_group.CreateCircleGroup",
        "circle.circle_group.GetCircleGroup",
        "circle.circle_group_membership.ApplyJoinCircleGroup",
        "circle.circle_group_membership.ApproveCircleGroupMember",
        "circle.circle_post_placement.PlacePostInCircle",
        "circle.circle_post_placement.PinCirclePost",
        "circle.circle_post_placement.FeatureCirclePost",
        "chat.conversation.CreateConversation",
        "chat.conversation.GetConversation",
        "chat.conversation_membership.AddMembers",
        "chat.message.SendMessage",
        "chat.message.RecallMessage",
        "chat.message.ListMessages",
        "chat.conversation_user_state.MarkAsRead",
        "chat.conversation_user_state.UpdateConversationSettings",
        "content.media_upload_session.InitMediaUpload",
        "content.media_upload_session.CompleteMediaUpload",
        "content.media_asset.GetMediaAsset",
    ),
    expected_counts=(
        ("circles", 3),
        ("circleGroups", 3),
        ("circleAndGroupMemberships", 9),
        ("releasePostPlacements", 3),
        ("directConversations", 2),
        ("circleGroupConversations", 3),
        ("messages", 30),
        ("recalledMessages", 1),
    ),
    spec_refs=(
        "specs/feature-tree/spec.md#uat-007",
        "specs/feature-tree/spec.md#uat-009",
    ),
)

NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC = DatasetRecipe(
    dataset_id="nonprod_reference_assistant_notification_rtc",
    retention_class=RetentionClass.CANDIDATE_BOUND,
    required_actor_count=2,
    operation_ids=(
        "assistant.skill_subscription.CreateSkillSubscription",
        "assistant.skill_subscription.GetSkillSubscription",
        "assistant.assistant_session.CreateAssistantSession",
        "assistant.assistant_session.GetAssistantSession",
        "assistant.assistant_run.StartAssistantRun",
        "chat.conversation.CreateConversation",
        "chat.conversation_membership.InviteAssistant",
        "chat.message.SendMessage",
        "chat.chat_inbox_view.ListInbox",
        "notification.notification.ListAppMessages",
        "rtc.call_session.InitiateCall",
        "rtc.call_session.CancelCall",
        "rtc.call_session.ReportMediaConnected",
        "rtc.call_session.HangupCall",
        "rtc.call_session.ListCalls",
    ),
    expected_counts=(
        ("assistantSubscriptions", 1),
        ("assistantSessions", 1),
        ("assistantTurns", 4),
        ("assistantMentions", 1),
        ("cancelledRtcAttempts", 1),
        ("completedRtcAttempts", 1),
        ("notificationKinds", 5),
    ),
    spec_refs=(
        "specs/feature-tree/spec.md#uat-007",
        "specs/feature-tree/spec.md#uat-009",
    ),
)

NONPROD_PAGING_BOUNDARY = DatasetRecipe(
    dataset_id="nonprod_paging_boundary",
    retention_class=RetentionClass.RUN_BOUND,
    required_actor_count=12,
    operation_ids=(
        "content.comment.CreateComment",
        "content.comment.ListComments",
        "content.comment.ListCommentReplies",
        "content.comment.DeleteComment",
        "chat.conversation.CreateConversation",
        "chat.message.SendMessage",
        "chat.message.ListMessages",
        "chat.conversation.DissolveConversation",
        "user.user_account.CloseAccount",
    ),
    expected_counts=(
        ("commentReplyBoundaries", 6),
        ("createdComments", 182),
        ("inboxConversations", 25),
        ("pagedConversationMessages", 41),
    ),
    spec_refs=("specs/feature-tree/spec.md#uat-009",),
)

NONPROD_RELIABILITY_RECOVERY = DatasetRecipe(
    dataset_id="nonprod_reliability_recovery",
    retention_class=RetentionClass.RUN_BOUND,
    required_actor_count=4,
    operation_ids=(
        "chat.conversation.CreateConversation",
        "chat.message.SendMessage",
        "chat.message.SyncMessages",
        "chat.message.ListMessages",
        "chat.message.RecallMessage",
        "content.comment.CreateComment",
        "content.comment.DeleteComment",
        "circle.circle.CreateCircle",
        "circle.circle.ArchiveCircle",
        "circle.circle_membership.JoinCircle",
        "chat.conversation.DissolveConversation",
        "user.user_account.CloseAccount",
    ),
    expected_counts=(
        ("syncBoundaryMessages", 501),
        ("duplicateClientMessageCases", 1),
        ("commandReplayCases", 2),
        ("authorizationFailureCases", 3),
        ("projectionDelayCases", 1),
        ("cleanupRecoveryCases", 1),
    ),
    spec_refs=("specs/feature-tree/spec.md#uat-009",),
)


def dataset_recipes() -> tuple[DatasetRecipe, ...]:
    return (
        CONTENT_RELEASE_FOUNDATION,
        NONPROD_REFERENCE_IDENTITY,
        NONPROD_REFERENCE_CONTENT_INTERACTION,
        NONPROD_REFERENCE_CIRCLE_CHAT,
        NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC,
        NONPROD_PAGING_BOUNDARY,
        NONPROD_RELIABILITY_RECOVERY,
    )


def compute_dataset_epoch(
    *,
    target: str,
    baseline_id: str,
    package_digest: str,
    release_digest: str,
    recipe_digest: str,
) -> str:
    if target not in NONPROD_TARGETS:
        raise ValueError("datasetEpoch is available only for Alpha/Beta/Gamma")
    for label, value in (
        ("baselineId", baseline_id),
        ("packageDigest", package_digest),
        ("releaseDigest", release_digest),
        ("recipeDigest", recipe_digest),
    ):
        if _SHA256.fullmatch(str(value or "")) is None:
            raise ValueError(f"{label} must be sha256")
    material = "\0".join(
        (target, baseline_id, package_digest, release_digest, recipe_digest)
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def idempotency_key(
    *,
    target: str,
    dataset_epoch: str,
    dataset_id: str,
    actor_role: str,
    operation: str,
    step: str,
) -> str:
    if target not in NONPROD_TARGETS or not re.fullmatch(r"[0-9a-f]{64}", dataset_epoch):
        raise ValueError("invalid nonprod dataset identity")
    parts = (target, dataset_epoch, dataset_id, actor_role, operation, step)
    if any(not str(part).strip() or "/" in str(part) for part in parts[2:]):
        raise ValueError("idempotency key segments must be non-empty and slash-free")
    return "/".join(str(part) for part in parts)


@dataclass(frozen=True)
class ContractOperation:
    operation_id: str
    method: str
    path_template: str
    request_entity: str

    def path(self, bindings: Mapping[str, str] | None = None) -> str:
        result = self.path_template
        supplied = dict(bindings or {})
        for name in re.findall(r"{([A-Za-z][A-Za-z0-9]*)}", result):
            value = str(supplied.pop(name, "")).strip()
            if not value:
                raise ValueError(f"operation {self.operation_id} missing path binding {name}")
            result = result.replace("{" + name + "}", quote(value, safe=""))
        if supplied:
            raise ValueError(
                f"operation {self.operation_id} received unknown path bindings {sorted(supplied)}"
            )
        return result


class ContractOperationCatalog:
    def __init__(self, graph_path: Path = CONTRACT_GRAPH) -> None:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        rows = payload.get("operations") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("generated ContractGraph operations are unavailable")
        self._operations: dict[str, ContractOperation] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            operation_id = str(row.get("id") or "")
            if operation_id:
                self._operations[operation_id] = ContractOperation(
                    operation_id=operation_id,
                    method=str(row.get("method") or ""),
                    path_template=str(row.get("pathTemplate") or ""),
                    request_entity=str(row.get("requestEntity") or ""),
                )

    def require(self, operation_id: str) -> ContractOperation:
        operation = self._operations.get(operation_id)
        if operation is None:
            raise ValueError(f"required ContractGraph operation is missing: {operation_id}")
        if not operation.method or not operation.path_template:
            raise ValueError(f"required ContractGraph operation is incomplete: {operation_id}")
        return operation

    def require_recipes(self, recipes: Iterable[DatasetRecipe]) -> None:
        for recipe in recipes:
            for operation_id in recipe.operation_ids:
                self.require(operation_id)
