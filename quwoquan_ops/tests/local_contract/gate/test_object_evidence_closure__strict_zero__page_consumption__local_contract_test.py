"""verify_object_evidence_closure 的 App 页面/运行时消费真相与门禁接线合约。

由 test_object_evidence_closure__strict_zero__contract_graph__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：page command 绑定声明参与者、runtime
execution 拒绝 adapter-only 证据、未消费 clientContract 是结构缺口、gate_repo
与 Make 接线不回退。测试逐字搬移；共享 harness 见 tests/support。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import unittest
from unittest import mock


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.object_evidence_closure_test_support import (
    COMMITTED_GRAPH,
    GATE_REPO,
    MAKEFILE,
    ObjectEvidenceClosureStrictZeroSupport,
    closure,
    synthetic_graph,
)


class ObjectEvidenceClosureStrictZeroTest(ObjectEvidenceClosureStrictZeroSupport):
    # --- App page / runtime consumption truth ---------------------------

    def test_page_command_is_bound_to_its_declared_participant(self) -> None:
        page_contract = self.write_page_contract(
            {
                "pages": [
                    {
                        "page_id": "content.demo",
                        "object_ids": ["content.demo"],
                        "query_slices": [],
                        "command_operations": ["content.demo.WriteDemo"],
                    }
                ],
                "runtime_execution": [],
            }
        )
        graph = {
            "objects": [{"id": "content.demo"}],
            "operations": [
                {
                    "id": "content.demo.WriteDemo",
                    "objectId": "content.demo",
                    "kind": "command",
                    "clientContract": True,
                }
            ],
        }

        with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
            claimed, query, command, runtime = closure.page_claims_and_consumers(graph)

        self.assertEqual(claimed, {"content.demo"})
        self.assertEqual(query, {})
        self.assertEqual(command, {"content.demo": {"content.demo"}})
        self.assertEqual(runtime, {})

    def test_page_command_rejects_query_or_foreign_object(self) -> None:
        graph = {
            "objects": [{"id": "content.demo"}, {"id": "content.foreign"}],
            "operations": [
                {
                    "id": "content.demo.ReadDemo",
                    "objectId": "content.demo",
                    "kind": "query",
                    "clientContract": True,
                },
                {
                    "id": "content.foreign.WriteForeign",
                    "objectId": "content.foreign",
                    "kind": "command",
                    "clientContract": True,
                },
            ],
        }
        for operation_id in ("content.demo.ReadDemo", "content.foreign.WriteForeign"):
            with self.subTest(operation_id=operation_id):
                page_contract = self.write_page_contract(
                    {
                        "pages": [
                            {
                                "page_id": "content.demo",
                                "object_ids": ["content.demo"],
                                "query_slices": [],
                                "command_operations": [operation_id],
                            }
                        ],
                        "runtime_execution": [],
                    }
                )
                with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
                    with self.assertRaises(SystemExit):
                        closure.page_claims_and_consumers(graph)

    def test_runtime_execution_rejects_adapter_only_or_missing_symbol(self) -> None:
        graph = {
            "objects": [{"id": "realtime.connection"}],
            "operations": [
                {
                    "id": "realtime.connection.IssueConnectionTicket",
                    "objectId": "realtime.connection",
                    "kind": "session",
                    "clientContract": True,
                    "localId": "IssueConnectionTicket",
                    "requestEntity": "IssueConnectionTicketRequest",
                    "facadeMethod": "issueTicket",
                }
            ],
        }
        evidence = [
            {
                "path": "lib/service/realtime_gateway/realtime/connection/adapters/realtime_connection_operation_remote.dart",
                "symbols": ["IssueConnectionTicketRequest"],
            },
            {
                "path": "lib/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart",
                "symbols": ["realtimeConnectionWebSocketUpgrade"],
            },
        ]
        for mutated in (
            evidence,
            [evidence[0], {**evidence[1], "symbols": ["MissingProductionSymbol"]}],
        ):
            with self.subTest(evidence=mutated):
                page_contract = self.write_page_contract(
                    {
                        "pages": [],
                        "runtime_execution": [
                            {
                                "object_id": "realtime.connection",
                                "operation_ids": [
                                    "realtime.connection.IssueConnectionTicket"
                                ],
                                "production_evidence": mutated,
                            }
                        ],
                    }
                )
                with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
                    with self.assertRaises(SystemExit):
                        closure.page_claims_and_consumers(graph)

    def test_current_contract_keeps_exact_page_and_runtime_consumers(self) -> None:
        graph = json.loads(COMMITTED_GRAPH.read_text(encoding="utf-8"))
        claimed, query, command, runtime = closure.page_claims_and_consumers(graph)

        expected_query_pages = {
            "assistant.assistant_entry_view": {"content.home"},
            "assistant.assistant_task_view": {"assistant.skill_center"},
            "assistant.assistant_turn_view": {"assistant.personal_session"},
            "chat.message_receipt_fact": {"chat.detail"},
            "circle.circle_file": {"circle.detail"},
            "circle.circle_group": {"circle.detail", "circle.stats"},
            "circle.circle_group_membership": {"circle.detail"},
            "circle.circle_membership": {
                "circle.membership_approval",
                "circle.stats",
            },
            "entity.homepage_review": {"entity.detail"},
            "user.following_subject": {"content.home"},
        }
        expected_command_pages = {
            "assistant.assistant_learning_fact": {"assistant.personal_session"},
            "assistant.page_context": {"assistant.personal_session", "content.home"},
            "chat.conversation_user_state": {"chat.detail"},
            "circle.circle_behavior_fact": {"circle.detail"},
            "circle.circle_group_membership": {"circle.detail"},
            "circle.circle_post_placement": {
                "content.home",
                "content.media_viewer",
                "content.work_browser_entry",
            },
            "content.content_behavior_fact": {
                "assistant.personal_session",
                "circle.detail",
                "content.home",
                "content.media_viewer",
                "content.work_browser_entry",
                "entity.detail",
                "intersection.object_list",
                "user.my_footprint",
                "user.my_intersections",
                "user.my_profile",
                "user.other_profile",
            },
            "content.media_upload_session": {"chat.detail"},
            "rtc.call_session": {"chat.detail", "chat.settings"},
            "search.search_feedback_fact": {"search.network_results"},
            "tag.tag_feedback_fact": {"user.career_interest"},
            "user.followed_subject_visit_state": {"content.home"},
            "user.subject_follow": {"entity.detail"},
        }
        for object_id, pages in expected_query_pages.items():
            self.assertEqual(query.get(object_id), pages, object_id)
        for object_id, pages in expected_command_pages.items():
            self.assertTrue(pages.issubset(command.get(object_id) or set()), object_id)

        self.assertEqual(
            set(runtime),
            {
                "notification.notification_delivery_job",
                "ops.event_record",
                "ops.visit_record",
                "user.device_registration",
            },
        )
        for object_id in (
            "chat.message_receipt_fact",
            "circle.circle_group_membership",
        ):
            self.assertIn(object_id, claimed)
            self.assertIn(object_id, query)
            self.assertNotIn(object_id, runtime)

    def test_unconsumed_client_contract_is_a_structural_gap(self) -> None:
        page_contract = self.write_page_contract(
            {"pages": [], "runtime_execution": []}
        )
        graph = synthetic_graph(missing="")
        graph["objectReadiness"][0]["missing"] = []
        graph["operations"] = [
            {
                "id": "content.demo.ReadDemo",
                "objectId": "content.demo",
                "kind": "query",
                "clientContract": True,
            }
        ]
        with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
            gaps = closure.collect_gaps(graph)

        self.assertIn("app.unconsumed_contract", {gap.dimension for gap in gaps})
        self.assertEqual(
            closure.EVIDENCE_CLASS_BY_DIMENSION["app.unconsumed_contract"],
            closure.STRUCTURAL,
        )

    def test_gate_repo_runs_the_gate_and_this_contract(self) -> None:
        text = GATE_REPO.read_text(encoding="utf-8")
        self.assertIn("quwoquan_ops/gate/verify_object_evidence_closure.py", text)
        self.assertIn(Path(__file__).name, text)

    def test_make_commercial_target_requires_and_forwards_all_six_inputs(self) -> None:
        text = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("verify-object-evidence-commercial-closure:", text)
        expected = {
            "OBJECT_EVIDENCE_READINESS_BUNDLE": "--readiness-bundle",
            "OBJECT_EVIDENCE_SIGNED_CURRENT_SNAPSHOT": "--signed-current-snapshot",
            "OBJECT_EVIDENCE_SNAPSHOT_KEYRING": "--snapshot-keyring",
            "OBJECT_EVIDENCE_RUNNER_KEYRING": "--runner-keyring",
            "OBJECT_EVIDENCE_RECEIPT_ROOT": "--receipt-root",
            "OBJECT_EVIDENCE_EVIDENCE_ROOT": "--evidence-root",
        }
        for variable, option in expected.items():
            with self.subTest(variable=variable):
                self.assertIn(f'test -n "$(%s)"' % variable, text)
                self.assertIn(f'{option} "$(%s)"' % variable, text)
        self.assertNotIn("--update-baseline", text)


if __name__ == "__main__":
    unittest.main()
