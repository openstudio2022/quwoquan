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
from quwoquan_ops.cli.lib.test_data.api import AssertionStatus, TestDataSession
from quwoquan_ops.cli.lib.test_data.cases import (
    assistant_prompt_case,
    chat_recall_case,
    circle_membership_case,
    content_comments_case,
    notification_delivery_case,
    rtc_completed_call_case,
    user_relationship_case,
)
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
        baseline_id="sha256:" + "1" * 64,
        package_digest="sha256:" + "2" * 64,
        runtime_config_digest="sha256:" + "3" * 64,
        release_id="release-provider-contract",
        release_digest="sha256:" + "4" * 64,
        import_run_id="import-provider-contract",
        release_post_ids=("post-release-1",),
    )


class _PublicRemote:
    """Stateful contract double at the HTTP operation boundary, not a Provider."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.relationships: set[tuple[str, str]] = set()
        self.comments: dict[str, list[str]] = {}
        self.circles: set[str] = set()
        self.conversations: dict[str, list[str]] = {}
        self.recalled_messages: set[str] = set()
        self.assistant_runs: set[str] = set()
        self.calls: set[str] = set()
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
        return LocalAcceptanceActor(
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
                return {"status": "closed"}

            relationship = re.fullmatch(
                r"/user/personas/([^/]+)/(follow|relationship)", clean_path
            )
            if relationship:
                target, action = relationship.groups()
                edge = (session.persona_id, target)
                if action == "follow" and method == "POST":
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
                circle_id = f"circle-{len(self.circles) + 1}"
                self.circles.add(circle_id)
                return {"circleId": circle_id}
            circle_path = re.fullmatch(r"/circles/([^/]+)", clean_path)
            if circle_path:
                circle_id = circle_path.group(1)
                if method == "GET":
                    return {"circleId": circle_id}
                if method == "DELETE":
                    self.circles.discard(circle_id)
                    return {"status": "archived"}
            membership_path = re.fullmatch(
                r"/circles/([^/]+)/memberships", clean_path
            )
            if membership_path and method == "POST":
                return {
                    "membershipId": (
                        f"membership-{membership_path.group(1)}-{session.persona_id}"
                    )
                }

            if clean_path == "/chat/conversations" and method == "POST":
                conversation_id = f"conversation-{len(self.conversations) + 1}"
                self.conversations[conversation_id] = []
                return {"conversationId": conversation_id}
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
                    return {"items": [{"messageId": item} for item in messages]}
            conversation_path = re.fullmatch(
                r"/chat/conversations/([^/]+)", clean_path
            )
            if conversation_path and method == "DELETE":
                self.conversations.pop(conversation_path.group(1), None)
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
                self.calls.add(call_id)
                return {"callId": call_id}
            if clean_path == "/rtc/calls" and method == "GET":
                return {"items": [{"callId": call_id} for call_id in self.calls]}
            call_action = re.fullmatch(
                r"/rtc/calls/([^/]+)/(connected|hangup)", clean_path
            )
            if call_action and method == "POST":
                return {"callId": call_action.group(1), "state": call_action.group(2)}

        raise AssertionError(f"unhandled public operation: {method} {path}")


class TestDataDomainProvidersContractTest(unittest.TestCase):
    def test_every_domain_provider_executes_its_autonomous_closure(self) -> None:
        candidate = _candidate()
        cases = (
            user_relationship_case(),
            content_comments_case(),
            circle_membership_case(),
            chat_recall_case(),
            assistant_prompt_case(),
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


if __name__ == "__main__":
    unittest.main()
