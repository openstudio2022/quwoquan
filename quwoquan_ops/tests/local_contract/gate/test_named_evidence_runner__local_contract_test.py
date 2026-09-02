"""Named evidence current-workspace truth contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t2
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import evidence_runner as runner  # noqa: E402
import review_dispatch as review  # noqa: E402
from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.feature_tree.commands import _context_manifest, discover_nodes  # noqa: E402
from lib.feature_tree.ownership import resolve_target_details  # noqa: E402

REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"
TEST_ROOT = ROOT / ".qwq_output/env/repo/local/named-evidence-tests"


class NamedEvidenceRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.case_root = TEST_ROOT / uuid.uuid4().hex
        self.case_root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.case_root, ignore_errors=True)

    def _manifest(self) -> dict:
        target = (
            "specs/feature-tree/runtime/development-workflow-governance/"
            "agent-skill-review-context-organization/spec.md"
        )
        nodes = discover_nodes()
        manifest = _context_manifest(
            target, resolve_target_details(target, nodes), nodes
        )
        manifest["evidence_fingerprint"] = review.embedded_fingerprint_binding(
            review.build_feature_context_fingerprint(manifest, repo_root=ROOT)
        )
        raw = canonical_json_bytes(manifest)
        manifest_root = ROOT / ".qwq_output/env/repo/runs/feature-tree/by-fingerprint"
        manifest_root.mkdir(parents=True, exist_ok=True)
        path = manifest_root / (hashlib.sha256(raw).hexdigest() + ".json")
        path.write_bytes(raw)
        self.manifest_ref = path.relative_to(ROOT).as_posix()
        return manifest

    def _plan(
        self,
        commands: list[tuple[str, bool, str]],
        *,
        changed_paths: list[str] | None = None,
        timeout_seconds: int = 300,
    ) -> tuple[dict, dict]:
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        registry["evidence"] = {
            evidence_id: {
                "command": command,
                "segment": "POST",
                "required": required,
                "timeout_seconds": timeout_seconds,
                "covers": [],
            }
            for evidence_id, required, command in commands
        }
        evidence_ids = [item[0] for item in commands]
        with mock.patch.object(
            review, "_checklist_evidence", return_value=evidence_ids
        ):
            plan = review.build_plan(
                registry,
                "dev",
                "POST",
                None,
                changed_paths or [],
                context_manifest=self._manifest(),
                context_manifest_ref=self.manifest_ref,
            )
        return plan, registry

    def _run(self, plan: dict, registry: dict, **kwargs: object) -> dict:
        ids = [item["id"] for item in plan["evidence"]]
        with mock.patch.object(review, "_checklist_evidence", return_value=ids):
            return runner.run_plan(plan, registry=registry, cwd=ROOT, **kwargs)

    def test_deduplicates_and_emits_real_workspace_receipt(self) -> None:
        relative = (self.case_root / "asset.txt").relative_to(ROOT).as_posix()
        (ROOT / relative).write_text("stable\n", encoding="utf-8")
        plan, registry = self._plan(
            [("same", True, "printf same")], changed_paths=[relative]
        )
        plan["evidence"].append(dict(plan["evidence"][0]))
        receipt = self._run(plan, registry)
        self.assertEqual(["same"], [item["id"] for item in receipt["evidence"]])
        self.assertEqual("PASS", receipt["terminal"]["status"])
        workspace = receipt["execution_fingerprint"]["digest_payload"]["workspace"]
        self.assertNotEqual(
            runner.canonical_digest([]), workspace["untracked_digest"]
        )
        self.assertEqual(
            workspace,
            receipt["result_fingerprint"]["digest_payload"]["workspace"],
        )


    def test_cancelled_and_nonready_plans_execute_zero_commands(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        for terminal in (
            {"status": "GATE_BLOCK", "codes": ["REVIEW.CANCELLED"], "failed_evidence": []},
            {"status": "PR_WARN", "codes": ["REVIEW.OPTIONAL_REVIEWER_INCOMPLETE"], "failed_evidence": []},
            {"status": "GATE_BLOCK", "codes": ["REVIEW.EVIDENCE_FAILED"], "failed_evidence": ["safe"]},
        ):
            mutated = copy.deepcopy(plan)
            mutated["terminal"] = terminal
            with mock.patch.object(runner, "run_command") as command, self.assertRaisesRegex(
                runner.EvidenceRunnerError, "TERMINAL_CONTRACT_INVALID|FINGERPRINT_CHANGED"
            ):
                self._run(mutated, registry)
            command.assert_not_called()

    def test_terminal_mutation_with_old_fingerprint_is_rejected(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        plan["terminal"]["status"] = "PASS"
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "TERMINAL_CONTRACT_INVALID|FINGERPRINT_CHANGED"
        ):
            self._run(plan, registry)

    def test_plan_change_is_rejected_before_first_shell_command(self) -> None:
        relative = (self.case_root / "asset.txt").relative_to(ROOT).as_posix()
        (ROOT / relative).write_text("before\n", encoding="utf-8")
        plan, registry = self._plan(
            [("safe", True, "printf safe")], changed_paths=[relative]
        )
        (ROOT / relative).write_text("after\n", encoding="utf-8")
        real_run = runner.run_command
        shell_calls: list[list[str]] = []

        def record(args, *positional, **kwargs):
            shell_calls.append(list(args))
            return real_run(args, *positional, **kwargs)

        with (
            mock.patch.object(runner, "run_command", side_effect=record),
            self.assertRaisesRegex(
                runner.EvidenceRunnerError, "REVIEW.FINGERPRINT_CHANGED"
            ),
        ):
            self._run(plan, registry)
        self.assertEqual([], shell_calls)

    def test_command_time_workspace_change_marks_result_stale(self) -> None:
        target = self.case_root / "asset.txt"
        relative = target.relative_to(ROOT).as_posix()
        target.write_text("before\n", encoding="utf-8")
        command = f"printf after >> {relative}"
        plan, registry = self._plan(
            [("mutates", True, command)], changed_paths=[relative]
        )
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "REVIEW.FINGERPRINT_CHANGED"
        ):
            self._run(plan, registry)

    def test_registry_command_drift_is_zero_command_blocker(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        registry["evidence"]["safe"]["command"] = "printf changed"
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "REVIEW.FINGERPRINT_CHANGED"
        ):
            self._run(plan, registry)

    def test_data_static_contract_declares_isolated_output_and_cleanup(self) -> None:
        registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        command = str(registry["evidence"]["data-static-contract"]["command"])

        self.assertIn(
            'isolated_output_root="$(mktemp -d '
            '"${TMPDIR:-/tmp}/qwq-data-static-contract.XXXXXX")"',
            command,
        )
        self.assertIn('QWQ_OUTPUT_ROOT="$isolated_output_root"', command)
        self.assertIn('rm -rf -- "$isolated_output_root"', command)
        self.assertIn("trap cleanup_data_static_contract_output EXIT", command)
        self.assertTrue(
            command.rstrip().endswith(
                "python3 -B quwoquan_data/scripts/cli.py verify all"
            )
        )
        self.assertNotIn(".qwq_output/data/tasks", command)

    def test_data_static_contract_actual_command_cleans_isolated_output(self) -> None:
        registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        command = str(registry["evidence"]["data-static-contract"]["command"])
        fake_bin = self.case_root / "bin"
        fake_bin.mkdir()
        fake_python = fake_bin / "python3"
        fake_python.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$QWQ_OUTPUT_ROOT\" \"$PWD\" \"$*\" > \"$QWQ_PROBE_RECEIPT\"\n"
            "mkdir -p \"$QWQ_OUTPUT_ROOT/data/tasks\"\n"
            "printf 'probe\\n' > \"$QWQ_OUTPUT_ROOT/data/tasks/probe\"\n"
            "exit \"$QWQ_PROBE_EXIT_CODE\"\n",
            encoding="utf-8",
        )
        fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

        for expected_exit_code in (0, 23):
            with self.subTest(exit_code=expected_exit_code):
                case_root = self.case_root / f"case-{expected_exit_code}"
                temp_parent = case_root / "temporary root [isolated]"
                temp_parent.mkdir(parents=True)
                shared_output_root = case_root / "shared output"
                shared_output_root.mkdir()
                shared_sentinel = shared_output_root / "must-survive.txt"
                shared_sentinel.write_text("user data\n", encoding="utf-8")
                receipt = case_root / "output-root.txt"
                environment = {
                    **os.environ,
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                    "TMPDIR": str(temp_parent),
                    "QWQ_OUTPUT_ROOT": str(shared_output_root),
                    "QWQ_PROBE_RECEIPT": str(receipt),
                    "QWQ_PROBE_EXIT_CODE": str(expected_exit_code),
                }

                completed = subprocess.run(
                    ["/bin/sh", "-c", command],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                self.assertEqual(expected_exit_code, completed.returncode)
                isolated_root_raw, command_cwd, command_args = receipt.read_text(
                    encoding="utf-8"
                ).splitlines()
                isolated_root = Path(isolated_root_raw)
                self.assertEqual(temp_parent, isolated_root.parent)
                self.assertNotEqual(shared_output_root, isolated_root)
                self.assertEqual(str(ROOT), command_cwd)
                self.assertEqual(
                    "-B quwoquan_data/scripts/cli.py verify all", command_args
                )
                self.assertFalse(isolated_root.exists())
                self.assertEqual([], list(temp_parent.iterdir()))
                self.assertEqual(
                    "user data\n", shared_sentinel.read_text(encoding="utf-8")
                )

    def test_timeout_terminates_evidence_process_group_and_emits_typed_result(self) -> None:
        child_pid = self.case_root / "child.pid"
        command = (
            "python3 -c \"import pathlib,subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
            f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid)); "
            "time.sleep(30)\""
        )
        plan, registry = self._plan(
            [("slow", True, command)], timeout_seconds=1
        )

        started = __import__("time").monotonic()
        receipt = self._run(plan, registry)
        elapsed = __import__("time").monotonic() - started

        self.assertLess(elapsed, 12)
        self.assertEqual("GATE_BLOCK", receipt["terminal"]["status"])
        self.assertEqual("REVIEW.EVIDENCE_TIMEOUT", receipt["terminal"]["code"])
        result = receipt["evidence"][0]
        self.assertEqual(124, result["exit_code"])
        self.assertEqual("timeout", result["outcome"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(1, result["timeout_seconds"])
        self.assertIn(result["termination_signal"], {"SIGTERM", "SIGKILL"})
        pid = int(child_pid.read_text(encoding="utf-8"))
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            __import__("time").sleep(0.02)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_timeout_declaration_must_match_registry_and_stay_bounded(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        plan["evidence"][0]["timeout_seconds"] = 301
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "FINGERPRINT_CHANGED|timeout_seconds"
        ):
            self._run(plan, registry)

        for invalid in (0, -1, 3601, True, None):
            with self.subTest(invalid=invalid):
                plan, registry = self._plan([("safe", True, "printf safe")])
                registry["evidence"]["safe"]["timeout_seconds"] = invalid
                with self.assertRaisesRegex(
                    runner.EvidenceRunnerError, "INVALID_EVIDENCE|timeout_seconds"
                ):
                    self._run(plan, registry)

    def test_required_failure_projects_real_exit_and_stops(self) -> None:
        plan, registry = self._plan(
            [("fail", True, "exit 7"), ("later", True, "printf later")]
        )
        receipt = self._run(plan, registry)
        self.assertEqual("GATE_BLOCK", receipt["terminal"]["status"])
        self.assertEqual("REVIEW.EVIDENCE_FAILED", receipt["terminal"]["code"])
        self.assertEqual(["fail"], [item["id"] for item in receipt["evidence"]])
        self.assertEqual(7, receipt["evidence"][0]["exit_code"])


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
