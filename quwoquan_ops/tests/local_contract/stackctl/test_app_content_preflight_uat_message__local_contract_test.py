"""app-content-uat 消息 P0 typed handoff 与 receipt 关联合约。"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import app_preflight_uat_binding as binding
from quwoquan_ops.cli.lib.test_data.api import BusinessObjectRef
from quwoquan_ops.cli.lib.test_data.capabilities.chat_service import (
    DIRECT_CONVERSATION_WITH_MESSAGES,
    DirectConversationResult,
    MessageHandle,
    MessageStatus,
)
from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    AuthenticatedActorsParams,
    MutualActorRelationship,
)
from quwoquan_ops.cli.lib.test_data.operations import TestDataRuntime
from quwoquan_ops.cli.lib.test_data.serialization import collect_request_graph


class _Scope:
    def __init__(self, value: DirectConversationResult, receipt: object) -> None:
        self.value = value
        self.receipt = receipt
        self.exited = False

    def __enter__(self) -> object:
        return SimpleNamespace(value=self.value, receipt=self.receipt)

    def __exit__(self, *_args: object) -> bool:
        self.exited = True
        return False


class _Session:
    def __init__(self, scope: _Scope, captured: dict[str, object]) -> None:
        self.scope = scope
        self.captured = captured

    def provision(self, request: object) -> _Scope:
        self.captured["request"] = request
        return self.scope


class AppContentPreflightUatMessageTest(unittest.TestCase):
    def test_message_runner_hands_typed_handles_only_through_child_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = SimpleNamespace(
                path=root / "000001-provision.json",
                digest="sha256:" + "1" * 64,
            )
            result_value = DirectConversationResult(
                conversation=BusinessObjectRef("Conversation", "conversation-live"),
                messages=(
                    MessageHandle(
                        BusinessObjectRef("Message", "message-a"),
                        MessageStatus.SENT,
                    ),
                    MessageHandle(
                        BusinessObjectRef("Message", "message-b"),
                        MessageStatus.SENT,
                    ),
                ),
                delivery_source=BusinessObjectRef("Message", "message-b"),
            )
            captured: dict[str, object] = {}
            scope = _Scope(result_value, receipt)
            session = _Session(scope, captured)
            runtime = TestDataRuntime()
            actor = SimpleNamespace(
                session=SimpleNamespace(
                    access_token="receiver-access",
                    refresh_token="receiver-refresh",
                    owner_id="receiver-owner",
                    persona_id="receiver-persona",
                )
            )
            context = SimpleNamespace(runtime=runtime, output_root=root)

            def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                captured["argv"] = argv
                captured["env"] = kwargs["env"]
                return subprocess.CompletedProcess(argv, 0, "", "")

            def link(_command: object, linked_receipt: object) -> dict[str, object]:
                self.assertTrue(scope.exited, "receipt link must happen after cleanup")
                self.assertIs(linked_receipt, receipt)
                return {"status": "prepared-cleaned", "baselineEligible": False}

            with (
                mock.patch.object(binding, "replace", return_value=context),
                mock.patch.object(
                    stackctl.TestDataSession,
                    "for_case",
                    return_value=session,
                ),
                mock.patch.object(runtime, "actor_for", return_value=object()),
                mock.patch.object(runtime, "actor", return_value=actor),
                mock.patch.object(
                    stackctl,
                    "_verify_child_environment",
                    side_effect=lambda _target, extra: extra,
                ),
                mock.patch.object(stackctl, "run", side_effect=run),
                mock.patch.object(
                    stackctl,
                    "_link_profile_preparation_to_page_report",
                    side_effect=link,
                ),
            ):
                completed, evidence = (
                    stackctl._run_app_content_message_home_command(
                        {
                            "argv": ["python3", "message-runner.py"],
                            "cwd": root,
                            "reportPath": root / "page-report.json",
                        },
                        target_name="alpha-local",
                        actor_context=context,
                    )
                )

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(evidence["status"], "prepared-cleaned")
            request = captured["request"]
            self.assertEqual(request.capability, DIRECT_CONVERSATION_WITH_MESSAGES)
            graph = collect_request_graph((request,))
            self.assertEqual(len(graph), 2)
            actor_requests = tuple(
                item
                for item in graph.values()
                if item.capability == AUTHENTICATED_ACTORS
            )
            self.assertEqual(len(actor_requests), 1)
            actor_params = actor_requests[0].params
            self.assertIsInstance(actor_params, AuthenticatedActorsParams)
            self.assertEqual(
                actor_params.mutual_relationships,
                (
                    MutualActorRelationship(
                        source_role=ActorRole.SENDER,
                        target_role=ActorRole.RECEIVER,
                    ),
                ),
            )
            environment = captured["env"]
            self.assertEqual(environment["QWQ_TEST_DATA_CONVERSATION_ID"], "conversation-live")
            self.assertEqual(
                json.loads(environment["QWQ_TEST_DATA_MESSAGE_IDS_JSON"]),
                ["message-a", "message-b"],
            )
            command_text = " ".join(captured["argv"])
            for value in (
                "conversation-live",
                "message-a",
                "message-b",
                "receiver-access",
            ):
                self.assertNotIn(value, command_text)

    def test_preparation_receipts_link_without_becoming_page_case_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            instance_id = "instance-a"

            def write_receipt(sequence: int, kind: str, payload: object) -> Path:
                path = root / f"{sequence:06d}-{kind}.json"
                path.write_text(
                    json.dumps(
                        {
                            "kind": kind,
                            "testDataInstanceId": instance_id,
                            "payload": payload,
                            "receiptDigest": f"sha256:{sequence:064x}",
                        }
                    ),
                    encoding="utf-8",
                )
                return path

            provision = write_receipt(1, "provision", {})
            write_receipt(2, "readback", {"passed": True})
            write_receipt(3, "cleanup", {"state": "released"})
            write_receipt(
                4,
                "run-summary",
                {"status": "prepared", "baselineEligible": False},
            )
            report_path = root / "page-report.json"
            page_case_results = [{"caseId": "patrol:message", "status": "passed"}]
            report_path.write_text(
                json.dumps({"status": "passed", "caseResults": page_case_results}),
                encoding="utf-8",
            )
            receipt = SimpleNamespace(
                path=provision,
                digest="sha256:" + f"{1:064x}",
            )

            evidence = stackctl._link_profile_preparation_to_page_report(
                {"reportPath": report_path},
                receipt,
            )
            page_report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(page_report["caseResults"], page_case_results)
            self.assertEqual(evidence["status"], "prepared-cleaned")
            self.assertFalse(evidence["baselineEligible"])
            self.assertEqual(evidence["testDataInstanceId"], instance_id)
            self.assertEqual(
                evidence["pageCaseResult"]["reportRef"],
                stackctl.relpath(report_path),
            )
            self.assertNotIn(
                "pageCaseResult",
                page_report["testDataPreparation"],
            )


if __name__ == "__main__":
    unittest.main()
