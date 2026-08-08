"""Assistant, notification, and RTC candidate-bound acceptance recipe.

All mutations use public ContractGraph operations and real non-production
principals. Provider conformance is validated before any provider-backed call.

spec_ref: specs/feature-tree/spec.md#uat-007
spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import time
from typing import Any, Mapping, TYPE_CHECKING

from .nonprod_business_data import (
    NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC,
    NONPROD_REFERENCE_CIRCLE_CHAT,
    NONPROD_REFERENCE_IDENTITY,
    idempotency_key,
)
from .nonprod_data_provisioner import (
    PublicOperationExecutor,
    _canonical_hash,
    _items,
    _required_string,
)

if TYPE_CHECKING:
    from .nonprod_data_provisioner import NonprodDataProvisioner


def provision_assistant_notification_rtc(
    owner: "NonprodDataProvisioner",
) -> dict[str, Any]:
    recipe = NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC
    epoch = owner._epoch(recipe)
    existing = owner._load_candidate_receipt_for_provision(recipe, epoch)
    if existing is not None:
        return owner._verify_existing_receipt(existing, recipe, epoch)

    provider_evidence = _validated_provider_evidence(owner)
    identity_epoch = owner._epoch(NONPROD_REFERENCE_IDENTITY)
    identity_receipt = owner._load_receipt(
        NONPROD_REFERENCE_IDENTITY, identity_epoch
    )
    if identity_receipt is None:
        raise RuntimeError("GATE_BLOCK: reference identity receipt is required")
    owner._verify_existing_identity_receipt(
        identity_receipt, NONPROD_REFERENCE_IDENTITY, identity_epoch
    )
    circle_epoch = owner._epoch(NONPROD_REFERENCE_CIRCLE_CHAT)
    circle_receipt = owner._load_receipt(
        NONPROD_REFERENCE_CIRCLE_CHAT, circle_epoch
    )
    if circle_receipt is None:
        raise RuntimeError("GATE_BLOCK: reference circle/chat receipt is required")
    owner._verify_existing_receipt(
        circle_receipt, NONPROD_REFERENCE_CIRCLE_CHAT, circle_epoch
    )

    actors = owner._open_actors(NONPROD_REFERENCE_IDENTITY, identity_epoch)
    executor = owner._candidate_executor(
        recipe,
        epoch,
        actor_receipt_refs=[
            {
                "datasetId": NONPROD_REFERENCE_IDENTITY.dataset_id,
                "datasetEpoch": identity_epoch,
            }
        ],
    )

    subscription = executor.call(
        "assistant.skill_subscription.CreateSkillSubscription",
        actor=actors[0],
        step="assistant-subscription",
        body={
            "skillId": "travel_companion",
            "domainId": "travel",
            "tagRefs": ["travel", "weather", "traffic"],
            "searchQueryPlan": {
                "rawText": "出发前检查西湖天气、路况和景区拥堵",
                "queries": ["杭州 西湖 天气", "杭州 景区拥堵"],
            },
            "trigger": {"type": "cron", "cron": "0 7 * * *"},
            "destination": {
                "destinationType": "user",
                "destinationId": actors[0].session.owner_id,
            },
            "clientRequestId": f"{epoch[:24]}-subscription",
        },
        object_id_fields=("subscriptionId", "id"),
    )
    subscription_id = _required_string(subscription, "subscriptionId", "id")

    assistant_session = executor.call(
        "assistant.assistant_session.CreateAssistantSession",
        actor=actors[0],
        step="assistant-session",
        body={
            "summary": "西湖行程验收会话",
            "clientRequestId": f"{epoch[:24]}-session",
        },
        object_id_fields=("sessionId", "id"),
    )
    assistant_session_id = _required_string(
        assistant_session, "sessionId", "id"
    )
    turn_ids: list[str] = []
    for index, text in enumerate(
        (
            "西湖今天适合步行游览吗？",
            "给我一条雨天替代路线。",
            "怎样避开主要拥堵时段？",
            "请总结出发前需要确认的三件事。",
        )
    ):
        turn = executor.call(
            "assistant.assistant_run.StartAssistantRun",
            actor=actors[0],
            step=f"assistant-turn-{index:02d}",
            bindings={"sessionId": assistant_session_id},
            body={
                "turnType": "user",
                "skillId": "travel_companion",
                "domainId": "travel",
                "input": {"text": text},
                "trigger": {"type": "user"},
                "clientRequestId": f"{epoch[:20]}-turn-{index:02d}",
            },
            object_id_fields=("turnId", "id"),
        )
        turn_ids.append(_required_string(turn, "turnId", "id"))

    group = executor.call(
        "chat.conversation.CreateConversation",
        actor=actors[0],
        step="assistant-mention-conversation",
        body={
            "type": "group",
            "title": "西湖助手协作群",
            "maxGroupSize": 20,
            "initialMemberIds": [actors[1].session.owner_id],
        },
        object_id_fields=("conversationId", "id"),
    )
    mention_conversation_id = _required_string(
        group, "conversationId", "id"
    )
    executor.call(
        "chat.conversation_membership.InviteAssistant",
        actor=actors[0],
        step="assistant-invite",
        bindings={"conversationId": mention_conversation_id},
        body={"skillId": "travel_companion"},
    )
    mention = executor.call(
        "chat.message.SendMessage",
        actor=actors[0],
        step="assistant-mention",
        bindings={"conversationId": mention_conversation_id},
        body={
            "type": "text",
            "content": "小趣，请给出西湖出发前提醒。",
            "mentions": ["assistant"],
            "clientMsgId": f"{epoch[:24]}-assistant-mention",
        },
        object_id_fields=("messageId", "id"),
    )
    mention_message_id = _required_string(mention, "messageId", "id")

    completed_call = executor.call(
        "rtc.call_session.InitiateCall",
        actor=actors[0],
        step="rtc-completed-initiate",
        body={
            "callType": "audio",
            "inviteeIds": [actors[1].session.persona_id],
            "conversationId": mention_conversation_id,
            "maxParticipants": 2,
        },
        object_id_fields=("callId", "id"),
    )
    completed_call_id = _required_string(completed_call, "callId", "id")
    for index, actor in enumerate(actors[:2]):
        executor.call(
            "rtc.call_session.ReportMediaConnected",
            actor=actor,
            step=f"rtc-completed-connected-{index}",
            bindings={"callId": completed_call_id},
            body=None,
        )
    executor.call(
        "rtc.call_session.HangupCall",
        actor=actors[0],
        step="rtc-completed-hangup",
        bindings={"callId": completed_call_id},
        body=None,
    )

    cancelled_call = executor.call(
        "rtc.call_session.InitiateCall",
        actor=actors[0],
        step="rtc-cancelled-initiate",
        body={
            "callType": "video",
            "inviteeIds": [actors[1].session.persona_id],
            "conversationId": mention_conversation_id,
            "maxParticipants": 2,
        },
        object_id_fields=("callId", "id"),
    )
    cancelled_call_id = _required_string(cancelled_call, "callId", "id")
    executor.call(
        "rtc.call_session.CancelCall",
        actor=actors[0],
        step="rtc-cancelled-cancel",
        bindings={"callId": cancelled_call_id},
        body=None,
    )
    call_history = executor.call(
        "rtc.call_session.ListCalls",
        actor=actors[0],
        step="rtc-history-readback",
        query={"limit": 20},
        body=None,
    )
    history_ids = {
        str(item.get("callId") or item.get("id") or "").strip()
        for item in _items(call_history)
        if isinstance(item, dict)
    }
    if not {completed_call_id, cancelled_call_id}.issubset(history_ids):
        raise RuntimeError("RTC history does not contain both acceptance attempts")

    notification_signals = _wait_notification_signals(
        executor=executor,
        actors=actors,
        circle_receipt=circle_receipt,
    )
    receipt = owner._base_receipt(recipe, epoch)
    receipt.update(
        {
            "status": "passed",
            "actorReceiptRefs": [
                {
                    "datasetId": NONPROD_REFERENCE_IDENTITY.dataset_id,
                    "datasetEpoch": identity_epoch,
                }
            ],
            "operationReceipts": [row.to_json() for row in executor.receipts],
            "createdObjectIdsOrHashes": {
                "subscriptionId": subscription_id,
                "assistantSessionId": assistant_session_id,
                "assistantTurnIds": turn_ids,
                "assistantMentionConversationId": mention_conversation_id,
                "assistantMentionMessageId": mention_message_id,
                "rtcCallIds": [completed_call_id, cancelled_call_id],
            },
            "projectionWatermarks": {
                "providerConformance": provider_evidence,
                "notificationSignals": notification_signals,
            },
            "readbackResults": {
                "assistantSubscriptions": 1,
                "assistantSessions": 1,
                "assistantTurns": len(turn_ids),
                "assistantMentions": 1,
                "cancelledRtcAttempts": 1,
                "completedRtcAttempts": 1,
                "notificationKinds": len(notification_signals),
            },
            "mediaUploadReceipts": [],
            "cleanupState": "retained",
            "caseResultRefs": [
                row["caseResultRef"]
                for row in provider_evidence.values()
                if row["caseResultRef"]
            ],
        }
    )
    if receipt["readbackResults"] != dict(recipe.expected_counts):
        raise RuntimeError("assistant/notification/RTC cardinality drift")
    owner._write_receipt(recipe, epoch, receipt)
    return receipt


def _validated_provider_evidence(
    owner: "NonprodDataProvisioner",
) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for name in ("assistantModel", "rtcMedia"):
        raw = owner.provider_conformance_evidence.get(name)
        if not isinstance(raw, Mapping):
            raise RuntimeError(
                f"GATE_BLOCK: Provider conformance evidence is required: {name}"
            )
        attempt_id = str(raw.get("attemptId") or "").strip()
        if (
            raw.get("status") != "passed"
            or not attempt_id
            or attempt_id == "unknown"
            or raw.get("baselineId") != owner.candidate.baseline_id
            or raw.get("packageDigest") != owner.candidate.package_digest
        ):
            raise RuntimeError(
                f"GATE_BLOCK: Provider conformance evidence is invalid: {name}"
            )
        normalized[name] = {
            "status": "passed",
            "attemptId": attempt_id,
            "caseResultRef": str(raw.get("caseResultRef") or "").strip(),
            "receiptHash": _canonical_hash(dict(raw)),
        }
    return normalized


def _wait_notification_signals(
    *,
    executor: PublicOperationExecutor,
    actors: list[Any],
    circle_receipt: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Read event-derived AppMessage plus Chat inbox delivery signals.

    Chat message delivery is owned by ChatInbox, not Notification AppMessage.
    Keeping the sources explicit prevents a fabricated fifth AppMessage kind.
    """

    required_app_message_types = {
        "greeting",
        "comment",
        "comment_mention",
        "circle_member",
    }
    direct_ids = circle_receipt.get("createdObjectIdsOrHashes", {}).get(
        "directConversationIds", []
    )
    if not isinstance(direct_ids, list) or not direct_ids:
        raise RuntimeError("reference circle/chat receipt misses direct conversations")
    direct_id = str(direct_ids[0]).strip()
    deadline = time.monotonic() + 20.0
    observed: dict[str, dict[str, Any]] = {}
    attempt = 0
    while True:
        for actor_index, actor in enumerate(actors):
            response = executor.call(
                "notification.notification.ListAppMessages",
                actor=actor,
                step=f"notification-readback-{attempt:02d}-{actor_index:02d}",
                query={"limit": 100},
                body=None,
            )
            for item in _items(response):
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("messageType") or "").strip()
                if kind in required_app_message_types:
                    observed[kind] = {
                        "source": "notification.app_message",
                        "objectHash": _canonical_hash(item),
                    }
        inbox = executor.call(
            "chat.chat_inbox_view.ListInbox",
            actor=actors[1],
            step=f"chat-inbox-readback-{attempt:02d}",
            query={"limit": 100},
            body=None,
        )
        for item in _items(inbox):
            if not isinstance(item, dict):
                continue
            if str(item.get("conversationId") or item.get("id") or "").strip() != direct_id:
                continue
            unread = item.get("unreadCount")
            if isinstance(unread, int) and not isinstance(unread, bool) and unread > 0:
                observed["chat_message"] = {
                    "source": "chat.inbox",
                    "objectHash": _canonical_hash(item),
                }
        if required_app_message_types.issubset(observed) and "chat_message" in observed:
            return {name: observed[name] for name in sorted(observed)}
        if time.monotonic() >= deadline:
            missing = sorted(
                (required_app_message_types | {"chat_message"}) - observed.keys()
            )
            raise RuntimeError(
                "GATE_BLOCK: event-derived notification signals did not converge: "
                + ", ".join(missing)
            )
        attempt += 1
        time.sleep(0.25)
