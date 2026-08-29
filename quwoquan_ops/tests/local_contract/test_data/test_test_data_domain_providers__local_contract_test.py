"""Seven-domain acceptance Provider autonomy through public operations.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t2
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from threading import Lock
from unittest import mock

from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceActor,
    LocalAcceptanceSession,
)
from quwoquan_ops.cli.lib.test_data.api import (
    AssertionStatus,
    BusinessObjectRef,
    TestDataSession,
)
from quwoquan_ops.cli.lib.test_data.cases import (
    assistant_prompt_case,
    assistant_skill_subscription_case,
    chat_group_governance_case,
    chat_recall_case,
    circle_gathering_case,
    circle_gathering_plan_case,
    circle_membership_case,
    circle_pending_approval_case,
    content_comments_case,
    content_footprint_case,
    content_reaction_case,
    notification_delivery_case,
    rtc_completed_call_case,
    user_following_subject_case,
    user_greeting_inbox_case,
    user_relationship_case,
)
from quwoquan_ops.cli.lib.test_data.discovery import load_provider
from quwoquan_ops.cli.lib.test_data.model import (
    CandidateBinding,
    TestDataContext as DataContext,
)
from quwoquan_ops.cli.lib.test_data.operations import TestDataRuntime as DataRuntime
from quwoquan_ops.cli.lib.test_data.serialization import collect_request_graph


def _candidate() -> CandidateBinding:
    return CandidateBinding(
        environment="gamma",
        target="gamma-local",
        source_revision="a" * 40,
        baseline_id="sha256:" + "1" * 64,
        package_digest="sha256:" + "2" * 64,
        runtime_config_digest="sha256:" + "3" * 64,
        release_id="release-provider-contract",
        release_digest="sha256:" + "4" * 64,
        import_run_id="import-provider-contract",
        readiness_phase="research",
        readiness_receipt_digest="sha256:" + "5" * 64,
        release_posts=(BusinessObjectRef("Post", "post-release-1"),),
        release_creators=(BusinessObjectRef("Creator", "creator-release-1"),),
        release_entities=(BusinessObjectRef("Entity", "entity-release-1"),),
        release_homepages=(
            BusinessObjectRef("EntityHomepage", "entity-release-1"),
        ),
        release_tags=(BusinessObjectRef("Tag", "tag-release-1"),),
        release_media_assets=(BusinessObjectRef("MediaAsset", "media-release-1"),),
    )


class _PublicRemote:
    """Stateful contract double at the HTTP operation boundary, not a Provider."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.relationships: set[tuple[str, str]] = set()
        self.personas: set[str] = set()
        self.closed_accounts: set[str] = set()
        self.fail_reverse_follow = False
        self.comments: dict[str, list[str]] = {}
        self.circles: dict[str, dict[str, object]] = {}
        self.gatherings: dict[str, dict[str, object]] = {}
        self.gathering_plans: dict[str, dict[str, object]] = {}
        self.gathering_plan_proposal_override: dict[str, object] | None = None
        self.gathering_plan_commit_count = 0
        self.followed_subjects: set[tuple[str, str, str]] = set()
        self.post_likes: set[tuple[str, str]] = set()
        self.behavior_events: list[tuple[str, str, str]] = []
        self.skill_subscriptions: dict[str, dict[str, str]] = {}
        self.conversations: dict[str, list[str]] = {}
        self.group_homes: dict[str, dict[str, object]] = {}
        self.greetings: dict[str, dict[str, str]] = {}
        self.recalled_messages: set[str] = set()
        self.assistant_runs: set[str] = set()
        self.calls: dict[str, str] = {}
        self.operation_count = 0

    def actor(
        self,
        _base_url: str,
        *,
        actor_role: str,
        actor_index: int,
        test_data_instance_id: str,
        **_kwargs: object,
    ) -> LocalAcceptanceActor:
        suffix = test_data_instance_id.replace("-", "")[:8]
        actor = LocalAcceptanceActor(
            role=actor_role,
            session=LocalAcceptanceSession(
                owner_id=f"owner-{actor_role}-{actor_index}-{suffix}",
                persona_id=f"persona-{actor_role}-{actor_index}-{suffix}",
                access_token=f"opaque-{actor_role}-{suffix}",
                refresh_token=f"opaque-refresh-{actor_role}-{suffix}",
            ),
            challenge_id=f"challenge-{actor_role}-{suffix}",
            account_state="active",
            identity_origin="phone",
        )
        self.personas.add(actor.session.persona_id)
        return actor

    def request(
        self,
        _base_url: str,
        *,
        path: str,
        session: LocalAcceptanceSession,
        method: str = "GET",
        **_kwargs: object,
    ) -> dict[str, object]:
        clean_path = path.partition("?")[0]
        with self._lock:
            self.operation_count += 1
            if method == "GET" and clean_path == "/me":
                # PersonaProfileView deliberately has no owner mapping.
                return {"personaId": session.persona_id}
            if method == "GET" and clean_path == "/user/personas/active":
                return {
                    "ownerUserId": session.owner_id,
                    "personaId": session.persona_id,
                }
            if method == "POST" and clean_path == "/owner/account/close":
                self.closed_accounts.add(session.owner_id)
                return {"status": "closed"}

            subject_follow = re.fullmatch(
                r"/relationships/subjects/([^/]+)/([^/]+)/follow", clean_path
            )
            if subject_follow:
                subject_type, subject_id = subject_follow.groups()
                edge = (session.persona_id, subject_type, subject_id)
                if method == "POST":
                    self.followed_subjects.add(edge)
                    return {
                        "personaId": session.persona_id,
                        "subjectType": subject_type,
                        "subjectId": subject_id,
                        "state": "following",
                    }
                if method == "DELETE":
                    self.followed_subjects.discard(edge)
                    return {
                        "personaId": session.persona_id,
                        "subjectType": subject_type,
                        "subjectId": subject_id,
                        "state": "none",
                    }
            if method == "GET" and clean_path == "/user/following-subjects":
                return {
                    "items": [
                        {"subjectId": subject_id, "subjectType": subject_type}
                        for persona, subject_type, subject_id in sorted(
                            self.followed_subjects
                        )
                        if persona == session.persona_id
                    ]
                }

            relationship = re.fullmatch(
                r"/user/personas/([^/]+)/(follow|relationship)", clean_path
            )
            if relationship:
                target, action = relationship.groups()
                edge = (session.persona_id, target)
                if action == "follow" and method == "POST":
                    if self.fail_reverse_follow and (
                        target,
                        session.persona_id,
                    ) in self.relationships:
                        self.fail_reverse_follow = False
                        raise RuntimeError("reverse follow failed")
                    self.relationships.add(edge)
                    return {"state": "following"}
                if action == "follow" and method == "DELETE":
                    self.relationships.discard(edge)
                    return {"state": "none"}
                if action == "relationship" and method == "GET":
                    reverse = (target, session.persona_id)
                    return {
                        "relationState": (
                            "mutual"
                            if edge in self.relationships
                            and reverse in self.relationships
                            else "following"
                        )
                    }

            if clean_path == "/user/greeting-request" and method == "POST":
                body = _kwargs.get("body") or {}
                greeting_id = f"greeting-{len(self.greetings) + 1}"
                self.greetings[greeting_id] = {
                    "id": greeting_id,
                    "requesterPersonaId": session.persona_id,
                    "targetPersonaId": str(body.get("targetPersonaId") or ""),
                    "requestMessage": str(body.get("requestMessage") or ""),
                    "status": "pending",
                }
                return dict(self.greetings[greeting_id])
            if clean_path == "/user/greeting-request/inbox" and method == "GET":
                return {
                    "items": [
                        dict(record)
                        for _, record in sorted(self.greetings.items())
                        if record["targetPersonaId"] == session.persona_id
                        and record["status"] == "pending"
                    ],
                    "nextCursor": None,
                }
            greeting_ignore = re.fullmatch(
                r"/user/greeting-request/([^/]+)/ignore", clean_path
            )
            if greeting_ignore and method == "POST":
                record = self.greetings[greeting_ignore.group(1)]
                record["status"] = "ignored"
                return dict(record)

            like_path = re.fullmatch(r"/content/posts/([^/]+)/like", clean_path)
            if like_path:
                post_id = like_path.group(1)
                edge = (session.persona_id, post_id)
                if method == "POST":
                    self.post_likes.add(edge)
                    return {"postId": post_id, "liked": True, "changed": True}
                if method == "DELETE":
                    self.post_likes.discard(edge)
                    return {"postId": post_id, "liked": False, "changed": True}
            reaction_path = re.fullmatch(
                r"/content/posts/([^/]+)/reactions", clean_path
            )
            if reaction_path and method == "GET":
                post_id = reaction_path.group(1)
                liked = (session.persona_id, post_id) in self.post_likes
                return {"found": liked, "postId": post_id, "liked": liked}

            if clean_path == "/content/behaviors" and method == "POST":
                body = _kwargs.get("body") or {}
                events = body.get("events") or []
                for event in events:
                    if not str(event.get("clientEventId") or "").strip():
                        raise AssertionError("behavior event requires clientEventId")
                    self.behavior_events.append(
                        (
                            session.persona_id,
                            str(event.get("contentId") or ""),
                            str(event.get("action") or ""),
                        )
                    )
                return {"acceptedCount": len(events), "replayedCount": 0}
            if clean_path == "/content/footprint" and method == "GET":
                viewed_actions = {"click", "dwell", "content_depth", "play_progress"}
                return {
                    "items": [
                        {
                            "postId": content_id,
                            "action": action,
                            "occurredAt": "2026-08-13T00:00:00Z",
                        }
                        for persona_id, content_id, action in self.behavior_events
                        if persona_id == session.persona_id
                        and action in viewed_actions
                    ],
                    "nextCursor": None,
                }

            comment_path = re.fullmatch(
                r"/content/posts/([^/]+)/comments(?:/([^/]+))?", clean_path
            )
            if comment_path:
                post_id, comment_id = comment_path.groups()
                comments = self.comments.setdefault(post_id, [])
                if method == "POST" and comment_id is None:
                    created = f"comment-{post_id}-{len(comments) + 1}"
                    comments.append(created)
                    return {"commentId": created}
                if method == "GET" and comment_id is None:
                    return {"items": [{"commentId": item} for item in comments]}
                if method == "DELETE" and comment_id is not None:
                    if comment_id in comments:
                        comments.remove(comment_id)
                    return {"status": "deleted"}

            if clean_path == "/circles" and method == "POST":
                body = _kwargs.get("body") or {}
                circle_id = f"circle-{len(self.circles) + 1}"
                self.circles[circle_id] = {
                    "joinPolicy": str(body.get("joinPolicy") or "open"),
                    "ownerPersonaId": session.persona_id,
                    "pending": {},
                }
                return {"circleId": circle_id}
            circle_path = re.fullmatch(r"/circles/([^/]+)", clean_path)
            if circle_path:
                circle_id = circle_path.group(1)
                if method == "GET":
                    return {"circleId": circle_id}
                if method == "DELETE":
                    self.circles.pop(circle_id, None)
                    return {"status": "archived"}
            pending_path = re.fullmatch(
                r"/circles/([^/]+)/memberships/pending", clean_path
            )
            if pending_path and method == "GET":
                state = self.circles[pending_path.group(1)]
                return {
                    "items": [
                        {
                            "membershipId": membership_id,
                            "personaId": persona_id,
                            "role": "member",
                            "state": "pending",
                        }
                        for persona_id, membership_id in sorted(
                            state["pending"].items()
                        )
                    ],
                    "cursor": None,
                }
            membership_path = re.fullmatch(
                r"/circles/([^/]+)/memberships", clean_path
            )
            if membership_path and method == "POST":
                circle_id = membership_path.group(1)
                state = self.circles[circle_id]
                membership_id = f"membership-{circle_id}-{session.persona_id}"
                if (
                    str(state["joinPolicy"]) == "approval"
                    and session.persona_id != state["ownerPersonaId"]
                ):
                    state["pending"][session.persona_id] = membership_id
                    return {
                        "membershipId": membership_id,
                        "role": "member",
                        "state": "pending",
                    }
                return {
                    "membershipId": membership_id,
                    "role": "member",
                    "state": "active",
                }
            persona_circles = re.fullmatch(
                r"/personas/([^/]+)/circles", clean_path
            )
            if persona_circles and method == "GET":
                return {
                    "items": [
                        {"circleId": circle_id, "name": f"验收圈子 {circle_id}"}
                        for circle_id in sorted(self.circles)
                    ],
                    "cursor": None,
                }

            if clean_path == "/gatherings" and method == "POST":
                gathering_id = f"gathering-{len(self.gatherings) + 1}"
                self.gatherings[gathering_id] = {
                    "lifecycle": "draft",
                    "version": 1,
                    "participants": {},
                }
                return {
                    "gatheringId": gathering_id,
                    "aggregateVersion": 1,
                    "lifecycleStatus": "draft",
                    "roomBindingStatus": "provisioning",
                }
            gathering_action = re.fullmatch(
                r"/gatherings/([^/:]+):(publish|join-open|cancel)", clean_path
            )
            if gathering_action and method == "POST":
                gathering_id, action = gathering_action.groups()
                state = self.gatherings[gathering_id]
                state["version"] = int(state["version"]) + 1
                if action == "publish":
                    state["lifecycle"] = "published"
                elif action == "join-open":
                    state["participants"][session.persona_id] = "active"
                else:
                    state["lifecycle"] = "cancelled"
                return {
                    "gatheringId": gathering_id,
                    "aggregateVersion": state["version"],
                    "lifecycleStatus": state["lifecycle"],
                    "roomBindingStatus": "ready",
                    "participationState": state["participants"].get(
                        session.persona_id
                    ),
                }
            roster_path = re.fullmatch(r"/gatherings/([^/:]+)/roster", clean_path)
            if roster_path and method == "GET":
                state = self.gatherings[roster_path.group(1)]
                return {
                    "items": [
                        {"personaId": persona, "state": participation}
                        for persona, participation in sorted(
                            state["participants"].items()
                        )
                    ],
                    "hasMore": False,
                }
            gathering_plan_path = re.fullmatch(
                r"/gatherings/([^/:]+)/plan", clean_path
            )
            if gathering_plan_path:
                gathering_id = gathering_plan_path.group(1)
                if method == "POST":
                    plan_id = f"plan-{len(self.gathering_plans) + 1}"
                    revision_id = f"revision-{plan_id}-1"
                    revision_digest = f"digest-{revision_id}"
                    plan = {
                        "id": plan_id,
                        "gatheringId": gathering_id,
                        "version": 1,
                        "currentRevisionId": revision_id,
                        "currentRevisionNumber": 1,
                        "currentRevisionDigest": revision_digest,
                        "items": (_kwargs.get("body") or {}).get("items") or [],
                        "revisions": [
                            {
                                "revisionId": revision_id,
                                "revisionNumber": 1,
                                "revisionDigest": revision_digest,
                            }
                        ],
                    }
                    self.gathering_plans[gathering_id] = plan
                    return {
                        "planId": plan_id,
                        "gatheringId": gathering_id,
                        "planVersion": 1,
                        "currentRevisionId": revision_id,
                        "currentRevisionNumber": 1,
                        "currentRevisionDigest": revision_digest,
                        "replayed": False,
                    }
                if method == "GET":
                    return dict(self.gathering_plans[gathering_id])
            gathering_plan_action = re.fullmatch(
                r"/gathering-plans/([^/]+)/(proposals|commit)", clean_path
            )
            if gathering_plan_action and method == "POST":
                plan_id, action = gathering_plan_action.groups()
                state = next(
                    plan
                    for plan in self.gathering_plans.values()
                    if plan["id"] == plan_id
                )
                if action == "proposals":
                    proposal_id = f"proposal-{plan_id}-1"
                    proposal_digest = f"digest-{proposal_id}"
                    state["version"] = 2
                    state["proposalId"] = proposal_id
                    state["proposalDigest"] = proposal_digest
                    response = {
                        "planId": plan_id,
                        "gatheringId": state["gatheringId"],
                        "planVersion": 2,
                        "currentRevisionId": state["currentRevisionId"],
                        "currentRevisionNumber": 1,
                        "currentRevisionDigest": state["currentRevisionDigest"],
                        "proposalId": proposal_id,
                        "proposalDigest": proposal_digest,
                        "replayed": False,
                    }
                    if self.gathering_plan_proposal_override is not None:
                        response.update(self.gathering_plan_proposal_override)
                    return response
                self.gathering_plan_commit_count += 1
                revision_id = f"revision-{plan_id}-2"
                revision_digest = f"digest-{revision_id}"
                state["version"] = 3
                state["currentRevisionId"] = revision_id
                state["currentRevisionNumber"] = 2
                state["currentRevisionDigest"] = revision_digest
                state["revisions"].append(
                    {
                        "revisionId": revision_id,
                        "revisionNumber": 2,
                        "revisionDigest": revision_digest,
                    }
                )
                return {
                    "planId": plan_id,
                    "gatheringId": state["gatheringId"],
                    "planVersion": 3,
                    "currentRevisionId": revision_id,
                    "currentRevisionNumber": 2,
                    "currentRevisionDigest": revision_digest,
                    "replayed": False,
                }
            gathering_plan_revisions = re.fullmatch(
                r"/gathering-plans/([^/]+)/revisions", clean_path
            )
            if gathering_plan_revisions and method == "GET":
                plan_id = gathering_plan_revisions.group(1)
                state = next(
                    plan
                    for plan in self.gathering_plans.values()
                    if plan["id"] == plan_id
                )
                return {
                    "items": list(state["revisions"]),
                    "nextCursor": None,
                    "hasMore": False,
                }
            gathering_path = re.fullmatch(r"/gatherings/([^/:]+)", clean_path)
            if gathering_path and method == "GET":
                state = self.gatherings[gathering_path.group(1)]
                return {
                    "gatheringId": gathering_path.group(1),
                    "aggregateVersion": state["version"],
                    "lifecycleStatus": state["lifecycle"],
                    "roomBindingStatus": "ready",
                }

            if clean_path == "/chat/conversations" and method == "POST":
                body = _kwargs.get("body") or {}
                if str(body.get("type") or "") == "direct":
                    member_ids = tuple(body.get("initialMemberIds") or ())
                    if len(member_ids) != 1:
                        raise AssertionError("direct conversation requires one member")
                    target_persona = str(member_ids[0])
                    if target_persona not in self.personas:
                        raise AssertionError("direct conversation member is unknown")
                    forward = (session.persona_id, target_persona)
                    reverse = (target_persona, session.persona_id)
                    if (
                        forward not in self.relationships
                        or reverse not in self.relationships
                    ):
                        raise AssertionError(
                            "direct conversation requires mutual actor topology"
                        )
                conversation_id = f"conversation-{len(self.conversations) + 1}"
                self.conversations[conversation_id] = []
                if str(body.get("type") or "") == "group":
                    members: dict[str, str] = {session.owner_id: "owner"}
                    for member_id in body.get("initialMemberIds") or []:
                        members[str(member_id)] = "member"
                    self.group_homes[conversation_id] = {
                        "members": members,
                        "announcement": "",
                    }
                return {"conversationId": conversation_id}
            announcement_path = re.fullmatch(
                r"/chat/conversations/([^/]+)/announcement", clean_path
            )
            if announcement_path and method == "PATCH":
                body = _kwargs.get("body") or {}
                state = self.group_homes[announcement_path.group(1)]
                state["announcement"] = str(body.get("announcement") or "")
                return {
                    "conversationId": announcement_path.group(1),
                    "announcement": state["announcement"],
                }
            admins_path = re.fullmatch(
                r"/chat/conversations/([^/]+)/admins", clean_path
            )
            if admins_path and method == "PUT":
                body = _kwargs.get("body") or {}
                members = self.group_homes[admins_path.group(1)]["members"]
                for user_id, role in members.items():
                    if role == "admin":
                        members[user_id] = "member"
                for admin_id in body.get("adminIds") or []:
                    if members.get(str(admin_id)) == "member":
                        members[str(admin_id)] = "admin"
                return {"status": "updated"}
            members_path = re.fullmatch(
                r"/chat/conversations/([^/]+)/members", clean_path
            )
            if members_path and method == "GET":
                members = self.group_homes[members_path.group(1)]["members"]
                return {
                    "items": [
                        {"userId": user_id, "role": role}
                        for user_id, role in sorted(members.items())
                    ],
                    "nextCursor": None,
                }
            group_home_path = re.fullmatch(r"/chat/groups/([^/]+)/home", clean_path)
            if group_home_path and method == "GET":
                state = self.group_homes[group_home_path.group(1)]
                return {
                    "conversationId": group_home_path.group(1),
                    "announcement": state["announcement"],
                    "memberCount": len(state["members"]),
                }
            message_path = re.fullmatch(
                r"/chat/conversations/([^/]+)/messages(?:/([^/]+)/recall)?",
                clean_path,
            )
            if message_path:
                conversation_id, recalled_id = message_path.groups()
                messages = self.conversations.setdefault(conversation_id, [])
                if method == "POST" and recalled_id is None:
                    message_id = f"message-{conversation_id}-{len(messages) + 1}"
                    messages.append(message_id)
                    return {"messageId": message_id}
                if method == "POST" and recalled_id is not None:
                    self.recalled_messages.add(recalled_id)
                    return {"status": "recalled"}
                if method == "GET":
                    return {
                        "items": [
                            {
                                "messageId": item,
                                "status": (
                                    "recalled"
                                    if item in self.recalled_messages
                                    else "sent"
                                ),
                            }
                            for item in messages
                        ]
                    }
            conversation_path = re.fullmatch(
                r"/chat/conversations/([^/]+)", clean_path
            )
            if conversation_path and method == "DELETE":
                self.conversations.pop(conversation_path.group(1), None)
                self.group_homes.pop(conversation_path.group(1), None)
                return {"status": "dissolved"}

            if clean_path == "/assistant/sessions" and method == "POST":
                return {"sessionId": "assistant-session-1"}
            assistant_start = re.fullmatch(
                r"/assistant/sessions/([^/]+)/runs", clean_path
            )
            if assistant_start and method == "POST":
                run_id = f"assistant-run-{len(self.assistant_runs) + 1}"
                self.assistant_runs.add(run_id)
                return {"runId": run_id}
            assistant_run = re.fullmatch(r"/assistant/runs/([^/]+)", clean_path)
            if assistant_run and method == "GET":
                return {"runId": assistant_run.group(1)}

            if clean_path == "/assistant/skills" and method == "GET":
                return {
                    "items": [
                        {"skillId": "travel_companion", "domainId": "travel"}
                    ]
                }
            if clean_path == "/assistant/skill-subscriptions" and method == "POST":
                body = _kwargs.get("body") or {}
                headers = _kwargs.get("headers") or {}
                # skill_subscription 命令边界要求 body/header 命令身份一致。
                if str(body.get("clientRequestId") or "") != str(
                    headers.get("Idempotency-Key") or ""
                ):
                    raise AssertionError(
                        "clientRequestId must match the Idempotency-Key header"
                    )
                subscription_id = (
                    f"skill-subscription-{len(self.skill_subscriptions) + 1}"
                )
                self.skill_subscriptions[subscription_id] = {
                    "status": "active",
                    "skillId": str(body.get("skillId") or ""),
                }
                return {
                    "subscriptionId": subscription_id,
                    "status": "active",
                    "skillId": str(body.get("skillId") or ""),
                }
            subscription_status = re.fullmatch(
                r"/assistant/skill-subscriptions/([^/]+)/status", clean_path
            )
            if subscription_status and method == "PATCH":
                body = _kwargs.get("body") or {}
                headers = _kwargs.get("headers") or {}
                if str(body.get("clientRequestId") or "") != str(
                    headers.get("Idempotency-Key") or ""
                ):
                    raise AssertionError(
                        "clientRequestId must match the Idempotency-Key header"
                    )
                state = self.skill_subscriptions[subscription_status.group(1)]
                state["status"] = str(body.get("status") or "")
                return {
                    "subscriptionId": subscription_status.group(1),
                    "status": state["status"],
                    "skillId": state["skillId"],
                }
            subscription_path = re.fullmatch(
                r"/assistant/skill-subscriptions/([^/]+)", clean_path
            )
            if subscription_path and method == "GET":
                state = self.skill_subscriptions[subscription_path.group(1)]
                return {
                    "subscriptionId": subscription_path.group(1),
                    "status": state["status"],
                    "skillId": state["skillId"],
                }

            if clean_path == "/app-messages" and method == "GET":
                message_id = next(
                    (
                        messages[-1]
                        for messages in self.conversations.values()
                        if messages
                    ),
                    "",
                )
                return {
                    "items": [
                        {
                            "messageId": "app-message-1",
                            "messageType": "chat",
                            "source": "chat_message",
                            "sourceId": message_id,
                        }
                    ]
                }

            if clean_path == "/rtc/calls" and method == "POST":
                call_id = f"call-{len(self.calls) + 1}"
                self.calls[call_id] = "initiated"
                return {"callId": call_id}
            if clean_path == "/rtc/calls" and method == "GET":
                return {
                    "items": [
                        {"callId": call_id, "state": state}
                        for call_id, state in self.calls.items()
                    ]
                }
            call_action = re.fullmatch(
                r"/rtc/calls/([^/]+)/(connected|hangup)", clean_path
            )
            if call_action and method == "POST":
                call_id, action = call_action.groups()
                self.calls[call_id] = "ended" if action == "hangup" else "connected"
                return {"callId": call_id, "state": self.calls[call_id]}

        raise AssertionError(f"unhandled public operation: {method} {path}")


class TestDataDomainProvidersContractTest(unittest.TestCase):
    def test_partial_mutual_follow_is_unwound_before_actor_accounts_close(self) -> None:
        candidate = _candidate()
        case = chat_recall_case()
        remote = _PublicRemote()
        remote.fail_reverse_follow = True
        runtime = DataRuntime()
        required_provider_capabilities = {
            provider_key.value
            for request in collect_request_graph((case.request,)).values()
            for provider_key in request.capability.required_provider_capabilities
        }
        provider_evidence = {
            capability_id: {
                "status": "passed",
                "candidateBindingDigest": candidate.digest,
            }
            for capability_id in required_provider_capabilities
        }
        with tempfile.TemporaryDirectory() as temporary:
            context = DataContext(
                candidate=candidate,
                base_url="https://gamma.local.quwoquan.invalid",
                output_root=Path(temporary),
                provider_evidence=provider_evidence,
                runtime=runtime,
            )
            with (
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data.providers.user_service."
                    "open_test_data_acceptance_session",
                    side_effect=remote.actor,
                ),
                mock.patch(
                    "quwoquan_ops.cli.lib.test_data.operations."
                    "request_local_environment_json",
                    side_effect=remote.request,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "capability provision failed",
                ):
                    TestDataSession.for_case(
                        case.case_id,
                        context=context,
                    ).execute(case)

        self.assertEqual(remote.relationships, set())
        self.assertEqual(len(remote.closed_accounts), 2)

    def test_gathering_plan_rejects_invalid_proposal_identity_before_commit(self) -> None:
        candidate = _candidate()
        case = circle_gathering_plan_case()
        required_provider_capabilities = {
            provider_key.value
            for request in collect_request_graph((case.request,)).values()
            for provider_key in request.capability.required_provider_capabilities
        }
        provider_evidence = {
            capability_id: {
                "status": "passed",
                "candidateBindingDigest": candidate.digest,
            }
            for capability_id in required_provider_capabilities
        }
        invalid_identities = (
            ({"proposalId": ""}, "proposalId"),
            ({"proposalDigest": ""}, "proposalDigest"),
            ({"planVersion": 0}, "planVersion"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for index, (override, expected_error) in enumerate(invalid_identities):
                with self.subTest(identity=expected_error):
                    remote = _PublicRemote()
                    remote.gathering_plan_proposal_override = override
                    runtime = DataRuntime()
                    context = DataContext(
                        candidate=candidate,
                        base_url="https://gamma.local.quwoquan.invalid",
                        output_root=Path(temporary) / str(index),
                        provider_evidence=provider_evidence,
                        runtime=runtime,
                    )
                    with (
                        mock.patch(
                            "quwoquan_ops.cli.lib.test_data.providers.user_service."
                            "open_test_data_acceptance_session",
                            side_effect=remote.actor,
                        ),
                        mock.patch(
                            "quwoquan_ops.cli.lib.test_data.operations."
                            "request_local_environment_json",
                            side_effect=remote.request,
                        ),
                        self.assertRaisesRegex(ValueError, expected_error),
                    ):
                        TestDataSession.for_case(
                            case.case_id,
                            context=context,
                        ).execute(case)
                    self.assertEqual(remote.gathering_plan_commit_count, 0)

    def test_every_domain_provider_executes_its_autonomous_closure(self) -> None:
        candidate = _candidate()
        cases = (
            user_relationship_case(),
            user_following_subject_case(),
            user_greeting_inbox_case(),
            content_comments_case(),
            content_reaction_case(),
            content_footprint_case(),
            circle_membership_case(),
            circle_gathering_case(),
            circle_gathering_plan_case(),
            circle_pending_approval_case(),
            chat_recall_case(),
            chat_group_governance_case(),
            assistant_prompt_case(),
            assistant_skill_subscription_case(),
            notification_delivery_case(),
            rtc_completed_call_case(),
        )
        required_provider_capabilities = {
            provider_key.value
            for case in cases
            for request in collect_request_graph((case.request,)).values()
            for provider_key in request.capability.required_provider_capabilities
        }
        provider_evidence = {
            capability_id: {
                "status": "passed",
                "candidateBindingDigest": candidate.digest,
            }
            for capability_id in required_provider_capabilities
        }
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            for case in cases:
                with self.subTest(case=case.case_id.value):
                    remote = _PublicRemote()
                    runtime = DataRuntime()
                    context = DataContext(
                        candidate=candidate,
                        base_url="https://gamma.local.quwoquan.invalid",
                        output_root=output_root / str(case.case_id.value),
                        provider_evidence=provider_evidence,
                        runtime=runtime,
                    )
                    with (
                        mock.patch(
                            "quwoquan_ops.cli.lib.test_data.providers.user_service."
                            "open_test_data_acceptance_session",
                            side_effect=remote.actor,
                        ),
                        mock.patch(
                            "quwoquan_ops.cli.lib.test_data.operations."
                            "request_local_environment_json",
                            side_effect=remote.request,
                        ),
                    ):
                        executed = TestDataSession.for_case(
                            case.case_id,
                            context=context,
                        ).execute(case)

                    self.assertEqual(executed.status, AssertionStatus.PASSED)
                    graph = collect_request_graph((case.request,))
                    expected_owners = sorted(
                        {
                            request.capability.owner_service
                            for request in graph.values()
                        }
                    )
                    summaries = tuple(
                        context.output_root.rglob("*-run-summary.json")
                    )
                    self.assertEqual(len(summaries), 1)
                    summary = json.loads(
                        summaries[0].read_text(encoding="utf-8")
                    )["payload"]
                    self.assertEqual(summary["loadedProviders"], expected_owners)
                    self.assertEqual(summary["requiredProviders"], expected_owners)
                    self.assertEqual(summary["executed"], 1)
                    self.assertEqual(summary["status"], "passed")
                    self.assertTrue(summary["baselineEligible"])
                    self.assertGreater(remote.operation_count, 0)
                    expected_operations = {
                        operation
                        for request in graph.values()
                        for definition in load_provider(
                            request.capability.owner_service,
                            context,
                        ).describe()
                        if definition.capability == request.capability
                        for operation in definition.operations
                    }
                    actual_operations = {
                        str(receipt["operationId"])
                        for receipt in runtime.operation_receipts
                    }
                    self.assertTrue(actual_operations)
                    self.assertTrue(actual_operations.issubset(expected_operations))


if __name__ == "__main__":
    unittest.main()
