"""Named evidence current-workspace truth contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t2
"""

from __future__ import annotations

import copy
import json
import json
import shutil
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
        path = self.case_root / "owner-manifest.json"
        path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        self.manifest_ref = path.relative_to(ROOT).as_posix()
        return manifest

    def _plan(
        self,
        commands: list[tuple[str, bool, str]],
        *,
        changed_paths: list[str] | None = None,
    ) -> tuple[dict, dict]:
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        registry["evidence"] = {
            evidence_id: {
                "command": command,
                "segment": "POST",
                "required": required,
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
            with mock.patch.object(runner.subprocess, "run") as command, self.assertRaisesRegex(
                runner.EvidenceRunnerError, "TERMINAL_CONTRACT_INVALID|FINGERPRINT_CHANGED"
            ):
                self._run(mutated, registry)
            self.assertFalse(
                any(call.args and call.args[0][:2] == ["/bin/sh", "-c"] for call in command.call_args_list)
            )

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
        real_run = subprocess.run
        shell_calls: list[list[str]] = []

        def record(args, *positional, **kwargs):
            if args[:2] == ["/bin/sh", "-c"]:
                shell_calls.append(args)
            return real_run(args, *positional, **kwargs)

        with (
            mock.patch.object(runner.subprocess, "run", side_effect=record),
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
