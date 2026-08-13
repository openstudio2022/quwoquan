# spec_ref: specs/feature-tree/runtime/runtime-testinfra/performance-load-harness/spec.md#gwt-001
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib import loadtest_orchestration as loadtest


class LoadtestSelectorContractTest(unittest.TestCase):
    def test_parse_selector_accepts_canonical_form(self) -> None:
        parsed = loadtest.parse_operation_selector(
            "chat-service/chat/conversation#ListConversations"
        )
        self.assertEqual(
            parsed,
            {
                "service": "chat-service",
                "context": "chat",
                "object": "conversation",
                "operation": "ListConversations",
            },
        )

    def test_parse_selector_rejects_malformed_forms(self) -> None:
        for selector in (
            "chat-service/chat#ListConversations",
            "chat-service/chat/conversation",
            "#ListConversations",
            "a/b/c#",
        ):
            with self.assertRaises(ValueError):
                loadtest.parse_operation_selector(selector)


class LoadtestContractDerivationTest(unittest.TestCase):
    def test_profile_is_derived_from_operations_contract(self) -> None:
        entry = loadtest.derive_operation_profile(
            "chat-service/chat/conversation#ListConversations"
        )
        self.assertEqual(entry["method"], "GET")
        self.assertEqual(entry["path"], "/chat/conversations")
        self.assertEqual(entry["sloLatencyP95Ms"], 500)
        self.assertAlmostEqual(entry["sloAvailabilityPercent"], 99.9)

    def test_parameterized_paths_are_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            loadtest.derive_operation_profile(
                "chat-service/chat/conversation#GetConversation"
            )
        self.assertIn("parameterized path", str(ctx.exception))

    def test_unknown_operation_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            loadtest.derive_operation_profile(
                "chat-service/chat/conversation#NoSuchOperation"
            )

    def test_profile_refuses_non_readonly_operations(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            loadtest.build_load_profile(
                base_url="http://127.0.0.1:1",
                operation_selectors=["chat-service/chat/conversation#CreateConversation"],
                concurrency=2,
                requests_per_operation=5,
                timeout_seconds=2.0,
            )
        self.assertIn("read-only", str(ctx.exception))


class LoadtestExecutionContractTest(unittest.TestCase):
    def test_prod_targets_are_refused_before_any_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                loadtest.run_loadtest(
                    env_name="prod",
                    target_name="prod-hosted",
                    operation_selectors=["chat-service/chat/conversation#ListConversations"],
                    concurrency=2,
                    requests_per_operation=5,
                    timeout_seconds=2.0,
                    report_dir=Path(tmp),
                )

    def test_report_binds_loadgen_verdict_and_is_persisted(self) -> None:
        loadgen_report = {
            "schema": "quwoquan.loadgen.report",
            "verdict": "pass",
            "operations": [
                {
                    "operationId": "chat-service/chat/conversation#ListConversations",
                    "verdict": "pass",
                    "p95Ms": 42.0,
                    "availabilityPercent": 100.0,
                    "samples": 5,
                }
            ],
        }

        def fake_runner(command):  # noqa: ANN001
            self.assertEqual(command[:3], ["go", "run", "./tools/loadgen"])
            return subprocess.CompletedProcess(
                args=list(command),
                returncode=0,
                stdout=json.dumps(loadgen_report),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            payload = loadtest.run_loadtest(
                env_name="gamma",
                target_name="gamma-local",
                operation_selectors=["chat-service/chat/conversation#ListConversations"],
                concurrency=2,
                requests_per_operation=5,
                timeout_seconds=2.0,
                report_dir=report_dir,
                runner=fake_runner,
                base_url_override="http://127.0.0.1:18079",
            )
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["verdict"], "pass")
            persisted = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["loadgen"]["verdict"], "pass")
            profile = json.loads((report_dir / "profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["schema"], loadtest.PROFILE_SCHEMA)
            self.assertFalse(profile["allowMutations"])
            self.assertEqual(profile["operations"][0]["sloLatencyP95Ms"], 500)

    def test_failed_verdict_is_not_masked_as_success(self) -> None:
        loadgen_report = {
            "schema": "quwoquan.loadgen.report",
            "verdict": "fail",
            "operations": [],
        }

        def fake_runner(command):  # noqa: ANN001
            return subprocess.CompletedProcess(
                args=list(command),
                returncode=1,
                stdout=json.dumps(loadgen_report),
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp:
            payload = loadtest.run_loadtest(
                env_name="gamma",
                target_name="gamma-local",
                operation_selectors=["chat-service/chat/conversation#ListConversations"],
                concurrency=2,
                requests_per_operation=5,
                timeout_seconds=2.0,
                report_dir=Path(tmp),
                runner=fake_runner,
                base_url_override="http://127.0.0.1:18079",
            )
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["verdict"], "fail")


if __name__ == "__main__":
    unittest.main()
