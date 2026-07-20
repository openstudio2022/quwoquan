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

    def test_release_profiles_register_group_lifecycle_probe(self) -> None:
        registry = json.loads(
            (ROOT / "quwoquan_ops/environments/gamma_validation_suites.json").read_text(
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


if __name__ == "__main__":
    unittest.main()
