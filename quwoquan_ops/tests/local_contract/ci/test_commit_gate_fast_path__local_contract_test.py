"""Contracts for L0 commit_gate: no double-run, no scope=all, impacted cap, budgets."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PRE_COMMIT = ROOT / "quwoquan_ops" / "hooks" / "pre-commit"
COMMIT_GATE = ROOT / "quwoquan_ops" / "gate" / "commit_gate.sh"
COMMIT_SELECT = ROOT / "quwoquan_ops" / "gate" / "commit_gate_select.py"
MAKEFILE = ROOT / "Makefile"
BUDGETS = ROOT / "quwoquan_ops" / "environments" / "pr_gate_timing_budgets.json"
BASELINE = ROOT / "quwoquan_ops" / "environments" / "commit_gate_timing_baseline.json"
FLUTTER_GUARD = ROOT / "quwoquan_app" / "scripts" / "env" / "run_flutter_test_guarded.py"
DELIVERY_GATE = ROOT / ".github" / "workflows" / "delivery-gate.yml"


class CommitGateFastPathTest(unittest.TestCase):
    def test_pre_commit_uses_commit_gate_not_make_gate(self) -> None:
        source = PRE_COMMIT.read_text(encoding="utf-8")
        self.assertIn("commit_gate.sh", source)
        self.assertNotRegex(source, r"(?m)^\s*make gate\b")
        self.assertNotIn("gate_repo.sh --scope", source)

    def test_makefile_gate_does_not_embed_test_local_contract(self) -> None:
        source = MAKEFILE.read_text(encoding="utf-8")
        gate_idx = source.index("\ngate:\n")
        next_target = source.index("\ngate-local-gamma:", gate_idx)
        gate_block = source[gate_idx:next_target]
        self.assertNotRegex(gate_block, r"(?m)^\s*@?\$\(MAKE\)\s+test-local-contract\b")
        self.assertIn("gate_repo.sh", gate_block)

    def test_local_gamma_defaults_to_skip_nested_gate(self) -> None:
        source = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn('LOCAL_GAMMA_SKIP_GATE:-1}', source)

    def test_budgets_declare_ten_minute_soft_fifteen_hard(self) -> None:
        data = json.loads(BUDGETS.read_text(encoding="utf-8"))
        gate = data["gates"]["00.local_commit_gate"]
        self.assertEqual(gate["budgetSeconds"], 600)
        self.assertEqual(gate["hardFailSeconds"], 900)
        self.assertEqual(gate["phaseBudgetsSeconds"]["L0_static_parallel"], 120)
        self.assertEqual(gate["phaseBudgetsSeconds"]["L0_impacted_tests_parallel"], 420)

    def test_baseline_artifact_exists(self) -> None:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertIn("cross_area_pre_commit", data["profiles"])
        self.assertEqual(data["targetAfterOptimization"]["local_commit_gate"]["p95Seconds"], 600)

    def test_selector_caps_flutter_and_defers_rest(self) -> None:
        proc = subprocess.run(
            [
                "python3",
                str(COMMIT_SELECT),
                "--changed-file",
                "quwoquan_app/lib/service/chat_service/chat/chat_message/presentation/chat_page.dart",
                "--flutter-cap",
                "5",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        plan = json.loads(proc.stdout)
        self.assertLessEqual(len(plan["flutter_tests"]), 5)
        self.assertGreaterEqual(len(plan["flutter_tests"]) + len(plan["deferred_to_ci"]), 5)
        self.assertIn("make gate", plan["forbidden"])
        self.assertIn("gate_repo --scope all", plan["forbidden"])
        # Cap must defer when the mapped suite is larger than flutter-cap.
        if len(plan["flutter_tests"]) + len(plan["deferred_to_ci"]) > 5:
            self.assertGreater(len(plan["deferred_to_ci"]), 0)

    def test_selector_skips_deleted_pytest_paths(self) -> None:
        existing = "quwoquan_ops/tests/local_contract/ci/test_commit_gate_fast_path__local_contract_test.py"
        deleted = "quwoquan_ops/tests/local_contract/test_removed_by_this_commit__local_contract_test.py"
        self.assertFalse((ROOT / deleted).exists())
        proc = subprocess.run(
            [
                "python3",
                str(COMMIT_SELECT),
                "--changed-file",
                existing,
                "--changed-file",
                deleted,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        plan = json.loads(proc.stdout)
        self.assertIn(existing, plan["pytest_paths"])
        self.assertNotIn(deleted, plan["pytest_paths"])

    def test_selector_maps_service_and_forbids_full_suite_symbols(self) -> None:
        proc = subprocess.run(
            [
                "python3",
                str(COMMIT_SELECT),
                "--changed-file",
                "quwoquan_service/services/user-service/internal/foo.go",
                "--changed-file",
                "quwoquan_app/lib/cloud/user/bar.dart",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        plan = json.loads(proc.stdout)
        self.assertTrue(plan["flags"]["has_service"])
        self.assertTrue(plan["flags"]["has_app"])
        self.assertIn("user-service", plan["go_services"])
        self.assertIn("service_architecture", plan["static_checks"])
        self.assertIn("python_script_governance", plan["static_checks"])
        self.assertIn("entrypoint_script_paths", plan["static_checks"])

    def test_flutter_guard_no_longer_forces_concurrency_one(self) -> None:
        source = FLUTTER_GUARD.read_text(encoding="utf-8")
        self.assertNotIn("_needs_serial_local_contract_run", source)
        self.assertIn("_with_concurrency", source)
        self.assertIn("_with_shard_flags", source)
        self.assertIn("FLUTTER_TEST_SERIAL_MODE", source)

    def test_delivery_gate_shards_app_tests(self) -> None:
        source = DELIVERY_GATE.read_text(encoding="utf-8")
        self.assertIn("quwoquan_app_tests:", source)
        self.assertIn("quwoquan_app_serial:", source)
        self.assertIn("quwoquan_app_static:", source)
        self.assertIn("FLUTTER_TEST_TOTAL_SHARDS: \"4\"", source)
        self.assertIn("FLUTTER_TEST_CONCURRENCY: \"8\"", source)
        self.assertIn("GATE_APP_PHASE: tests", source)

    def test_commit_gate_script_has_fingerprint_and_budgets(self) -> None:
        source = COMMIT_GATE.read_text(encoding="utf-8")
        self.assertIn("fingerprint", source.lower())
        self.assertIn("HARD_BUDGET", source)
        self.assertIn("SOFT_BUDGET", source)
        self.assertIn("entrypoint_script_paths", source)
        self.assertNotRegex(source, r"(?m)^\s*make gate\b")
        self.assertNotIn("gate_repo.sh --scope all", source)

    def test_commit_gate_resolves_a_real_pytest_runtime_and_redirects_cache(self) -> None:
        source = COMMIT_GATE.read_text(encoding="utf-8")

        self.assertIn("resolve_pytest_runtime", source)
        self.assertIn("QWQ_PYTHON_CACHE_ROOT", source)
        self.assertIn("import pytest", source)
        self.assertIn("PYTEST_ADDOPTS", source)
        self.assertIn("cache_dir=$QWQ_OUTPUT_ROOT/env/repo/local/tests/cache/pytest", source)


if __name__ == "__main__":
    unittest.main()
