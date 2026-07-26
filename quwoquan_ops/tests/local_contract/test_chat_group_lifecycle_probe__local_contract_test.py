from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = (
    ROOT
    / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/smoke"
    / "run_chat_group_lifecycle_probe.py"
)
WORKFLOW_PATH = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
SPEC = importlib.util.spec_from_file_location("chat_group_lifecycle_probe", PROBE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load chat group lifecycle probe")
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class ChatGroupLifecycleProbeLocalContractTest(unittest.TestCase):
    def test_source_contract_rejects_cross_source_rows(self) -> None:
        PROBE._require_source_rows(
            [
                {
                    "conversationId": "private-group",
                    "circleId": "",
                    "friendMemberCount": 2,
                }
            ],
            source="group",
            expected_conversation_id="private-group",
            expected_circle_id="",
            require_nonempty=True,
        )
        PROBE._require_source_rows(
            [
                {
                    "conversationId": "circle-group",
                    "circleId": "circle-1",
                    "friendMemberCount": 1,
                }
            ],
            source="circle",
            expected_conversation_id="circle-group",
            expected_circle_id="circle-1",
            require_nonempty=True,
        )

        with self.assertRaisesRegex(PROBE.ProbeFailure, "circle-bound"):
            PROBE._require_source_rows(
                [
                    {
                        "conversationId": "circle-group",
                        "circleId": "circle-1",
                        "friendMemberCount": 1,
                    }
                ],
                source="group",
                expected_conversation_id="",
                expected_circle_id="",
                require_nonempty=True,
            )

    def test_evidence_hash_does_not_persist_raw_object_id(self) -> None:
        raw_id = "conversation-production-sensitive-id"
        evidence_id = PROBE._stable_hash(raw_id)
        self.assertEqual(len(evidence_id), 16)
        self.assertNotEqual(evidence_id, raw_id)
        self.assertNotIn(raw_id, evidence_id)

    def test_mentioned_message_round_trip_requires_canonical_target(self) -> None:
        items = [
            {
                "id": "message-mention",
                "mentions": ["fixture_user_friend"],
            }
        ]
        self.assertTrue(
            PROBE._mentioned_message_visible(
                items,
                message_id="message-mention",
                mentioned_user_id="fixture_user_friend",
            )
        )
        with self.assertRaisesRegex(PROBE.ProbeFailure, "not preserved"):
            PROBE._mentioned_message_visible(
                items,
                message_id="message-mention",
                mentioned_user_id="fixture_user_other",
            )
        self.assertFalse(
            PROBE._mentioned_message_visible(
                items,
                message_id="unknown-message",
                mentioned_user_id="fixture_user_friend",
            )
        )

    def test_release_profiles_register_group_lifecycle_probe(self) -> None:
        registry = json.loads(
            (ROOT / "quwoquan_ops/environments/gamma/validation_suites.json").read_text(
                encoding="utf-8"
            )
        )
        case = registry["smokeCases"]["chat_group_lifecycle_api_probe"]
        self.assertEqual(case["path"], str(PROBE_PATH.relative_to(ROOT)))
        self.assertTrue(PROBE_PATH.is_file())
        for profile_name in (
            "manual_full",
            "nightly_full",
            "release_candidate",
            "mainline_auto_prod",
        ):
            profile = registry["profiles"][profile_name]
            self.assertTrue(profile["smokeCasesBlocking"])
            self.assertIn("chat_group_lifecycle_api_probe", profile["smokeCases"])

    def test_hosted_probe_keeps_tls_validation_and_uses_standard_prod_token(self) -> None:
        source = PROBE_PATH.read_text(encoding="utf-8")
        self.assertIn('default="PROD_TEST_AUTH_TOKEN"', source)
        self.assertNotIn("_create_unverified_context", source)

    def test_mainline_beta_bootstrap_runs_stackctl_integration_profile(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        bootstrap_start = workflow.index("Bootstrap beta-local stack for mainline auto prod")
        bootstrap_end = workflow.index("      - id: run_matrix", bootstrap_start)
        bootstrap = workflow[bootstrap_start:bootstrap_end]

        self.assertIn(
            "stackctl.py verify --env beta --kind all --profile integration",
            bootstrap,
        )
        self.assertIn(
            'report-dir "$QWQ_OUTPUT_ROOT/env/beta/runs/mainline-verify"',
            bootstrap,
        )


if __name__ == "__main__":
    unittest.main()
