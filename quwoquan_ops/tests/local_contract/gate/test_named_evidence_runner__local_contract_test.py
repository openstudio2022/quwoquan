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
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import evidence_runner as runner  # noqa: E402
import review_dispatch as review  # noqa: E402
from lib.evidence_fingerprint import canonical_json_bytes
from lib.candidate_evidence import build_candidate_evidence
from lib.feature_tree.content_addressed_writer import _write_content_addressed_bytes  # noqa: E402
from lib.feature_tree.commands import _context_manifest, discover_nodes  # noqa: E402
from lib.feature_tree.ownership import resolve_target_details  # noqa: E402

REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"
TEST_ROOT = ROOT / "quwoquan_ops/cli/lib/.named-evidence-tests"


class NamedEvidenceRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._discovered_nodes = tuple(discover_nodes())

    def setUp(self) -> None:
        self.case_root = TEST_ROOT / uuid.uuid4().hex
        self.case_root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.case_root, ignore_errors=True)

    def _manifest(self, target: str) -> dict:
        nodes = self._discovered_nodes
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
        registry["workflows"]["dev"]["baseline_evidence"] = ""
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
            paths = changed_paths or [
                "specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md"
            ]
            manifest = self._manifest(paths[0])
            candidate = build_candidate_evidence(self.manifest_ref, paths, repo_root=ROOT)
            candidate_path = _write_content_addressed_bytes(
                canonical_json_bytes(candidate), subdirectory="candidates/by-fingerprint"
            )
            plan = review.build_plan(
                registry, "dev", "POST", None, paths,
                context_manifest=manifest, context_manifest_ref=self.manifest_ref,
                candidate_evidence_ref=candidate_path.relative_to(ROOT).as_posix(),
            )
        return plan, registry

    def _run(self, plan: dict, registry: dict, **kwargs: object) -> dict:
        ids = [item["id"] for item in plan["evidence"]]
        with mock.patch.object(review, "_checklist_evidence", return_value=ids):
            kwargs.setdefault("plan_bytes", canonical_json_bytes(plan))
            kwargs.setdefault("plan_ref", "test-fixture:exact-plan")
            return runner.run_plan(plan, registry=registry, cwd=ROOT, **kwargs)

    def test_deduplicates_and_emits_real_workspace_receipt(self) -> None:
        relative = "quwoquan_ops/tests/local_contract/gate/fixtures/named_evidence_workspace_receipt.txt"
        untracked = self.case_root / "workspace-untracked.txt"
        untracked.write_text("workspace evidence\n", encoding="utf-8")
        untracked_relative = untracked.relative_to(ROOT).as_posix()
        plan, registry = self._plan(
            [("same", True, "printf same")],
            changed_paths=[relative, untracked_relative],
        )
        plan["evidence"].append(dict(plan["evidence"][0]))
        receipt = self._run(plan, registry)
        self.assertEqual(["same"], [item["id"] for item in receipt["evidence"]])
        self.assertEqual("PASS", receipt["terminal"]["status"])
        self.assertEqual("feedback_only", receipt["evidence_class"])
        self.assertIs(receipt["admission_eligible"], False)
        self.assertEqual("workspace", receipt["source"]["mode"])
        self.assertIs(receipt["source"]["repository_clean"], False)
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
        relative = "quwoquan_ops/tests/local_contract/gate/fixtures/named_evidence_preflight_drift.txt"
        target = ROOT / relative
        original = target.read_text(encoding="utf-8")
        target.write_text("before\n", encoding="utf-8")
        self.addCleanup(target.write_text, original, encoding="utf-8")
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
                runner.EvidenceRunnerError, "CANDIDATE.STALE|REVIEW.FINGERPRINT_CHANGED"
            ),
        ):
            self._run(plan, registry)
        self.assertEqual([], shell_calls)

    def test_real_temp_repo_classifies_only_clean_exact_sha_as_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(
                [
                    "git", "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "clean exact sha",
                ],
                cwd=repo, check=True,
            )
            clean = runner._workspace_source_classification(repo)
            self.assertEqual(("reusable", True), runner._evidence_classification(clean))
            self.assertTrue(clean["repository_clean"])
            self.assertRegex(clean["head_sha"], r"^[0-9a-f]{40,64}$")

            (repo / "unrelated.txt").write_text("dirty\n", encoding="utf-8")
            dirty = runner._workspace_source_classification(repo)
            self.assertEqual(
                ("feedback_only", False), runner._evidence_classification(dirty)
            )
            self.assertFalse(dirty["repository_clean"])

    def test_clean_exact_sha_workspace_receipt_is_admission_eligible(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        clean_source = {
            "mode": "workspace",
            "head_sha": plan["head_sha"],
            "merge_base_sha": plan["merge_base_sha"],
            "repository_clean": True,
            "immutable": False,
        }
        with mock.patch.object(
            runner, "_workspace_source_classification", return_value=clean_source
        ), mock.patch.object(runner, "_assert_source_head"):
            receipt = self._run(plan, registry)
        self.assertEqual("reusable", receipt["evidence_class"])
        self.assertIs(receipt["admission_eligible"], True)
        self.assertIs(runner.require_admission_eligible(receipt), receipt)

    def test_legacy_receipt_without_evidence_class_requires_migration(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        receipt = self._run(plan, registry)
        for field in ("source", "evidence_class", "admission_eligible"):
            receipt.pop(field)
        receipt["schema_version"] -= 1
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "字段漂移|schema_version"
        ):
            runner.validate_named_evidence_receipt(receipt)

    def test_first_command_managed_drift_stops_second_marker(self) -> None:
        relative = "quwoquan_ops/tests/local_contract/gate/fixtures/named_evidence_runtime_drift.txt"
        target = ROOT / relative
        original = target.read_text(encoding="utf-8")
        marker = self.case_root / "second-command-must-not-run.txt"
        target.write_text("before\n", encoding="utf-8")
        self.addCleanup(target.write_text, original, encoding="utf-8")
        first = f"printf drift >> {relative}"
        second = f"printf ran > {marker}"
        plan, registry = self._plan(
            [("mutates", True, first), ("later", True, second)],
            changed_paths=[relative],
        )
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "FINGERPRINT_CHANGED"
        ):
            self._run(plan, registry)
        self.assertFalse(marker.exists())

    def test_command_time_workspace_change_marks_result_stale(self) -> None:
        relative = "quwoquan_ops/tests/local_contract/gate/fixtures/named_evidence_runtime_drift.txt"
        target = ROOT / relative
        original = target.read_text(encoding="utf-8")
        target.write_text("before\n", encoding="utf-8")
        self.addCleanup(target.write_text, original, encoding="utf-8")
        command = f"printf after >> {relative}"
        plan, registry = self._plan(
            [("mutates", True, command)], changed_paths=[relative]
        )
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "CANDIDATE.STALE|REVIEW.FINGERPRINT_CHANGED"
        ):
            self._run(plan, registry)

    def test_registry_command_drift_is_zero_command_blocker(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        registry["evidence"]["safe"]["command"] = "printf changed"
        with self.assertRaisesRegex(
            runner.EvidenceRunnerError, "CANDIDATE.STALE|REVIEW.FINGERPRINT_CHANGED"
        ):
            self._run(plan, registry)


    def test_review_baseline_receives_only_runner_exact_plan_identity(self) -> None:
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        command = str(registry["evidence"]["review-baseline"]["command"])
        self.assertIn("verify_review_baseline.py", command)
        self.assertNotIn("pytest", command)
        self.assertNotIn("make verify-review-dispatch", command)
        paths = [
            "specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md"
        ]
        manifest = self._manifest(paths[0])
        candidate = build_candidate_evidence(self.manifest_ref, paths, repo_root=ROOT)
        candidate_path = _write_content_addressed_bytes(
            canonical_json_bytes(candidate), subdirectory="candidates/by-fingerprint"
        )
        plan = review.build_plan(
            registry, "dev", "POST", None, paths,
            context_manifest=manifest, context_manifest_ref=self.manifest_ref,
            candidate_evidence_ref=candidate_path.relative_to(ROOT).as_posix(),
        )
        captured: dict[str, object] = {}
        real_run = runner.run_command

        def inspect(args, *positional, **kwargs):
            env = kwargs["env"]
            exact_path = Path(env[runner.BASELINE_PLAN_ENV])
            raw = exact_path.read_bytes()
            captured.update({
                "path": exact_path,
                "raw": raw,
                "sha": env[runner.BASELINE_PLAN_SHA_ENV],
                "ref": env[runner.BASELINE_PLAN_REF_ENV],
            })
            if "verify_review_baseline.py" in args[2]:
                result = real_run(args, *positional, **kwargs)
                captured["stderr"] = result.stderr.decode("utf-8", errors="replace")
                return result
            descriptor_raw = env.get(runner.RESULT_PATH_ENV)
            if descriptor_raw:
                descriptor = Path(descriptor_raw)
                candidate_identity = plan["candidate_evidence_identity"]
                report = {
                    "schema": "quwoquan.code-health-delta",
                    "terminal": "PASS",
                    "baseSha": plan["merge_base_sha"],
                    "headSha": plan["head_sha"],
                    "changedPathsDigest": candidate_identity["changed_paths_digest"],
                    "summary": {"changedFiles": len(plan["changed_paths"])},
                    "findings": [],
                    "evidenceFingerprint": {
                        "ref": "evidence-fingerprint-v1:sha256:" + "c" * 64,
                        "digest": "sha256:" + "c" * 64,
                    },
                }
                report_path = self.case_root / "baseline-code-health-report.json"
                report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
                descriptor.write_text(json.dumps({
                    "kind": "code-health-report-v1",
                    "ref": report_path.relative_to(ROOT).as_posix(),
                    "canonical_bytes_sha256": "sha256:" + hashlib.sha256(report_path.read_bytes()).hexdigest(),
                    "schema": report["schema"], "terminal": report["terminal"],
                    "report_identity": "sha256:" + "d" * 64,
                    "evidence_fingerprint_ref": report["evidenceFingerprint"]["ref"],
                    "evidence_fingerprint_digest": report["evidenceFingerprint"]["digest"],
                    "base_sha": plan["merge_base_sha"], "head_sha": plan["head_sha"],
                    "changed_paths_digest": candidate_identity["changed_paths_digest"],
                    "impact_plan_ref": candidate_identity["impact_plan_ref"],
                    "impact_plan_digest": candidate_identity["impact_plan_digest"],
                    "candidate_evidence_ref": candidate_identity["ref"],
                    "candidate_evidence_sha256": candidate_identity["canonical_bytes_sha256"],
                    "plan_ref": env[runner.BASELINE_PLAN_REF_ENV],
                    "plan_sha256": env[runner.BASELINE_PLAN_SHA_ENV],
                    "summary": report["summary"], "findings": report["findings"],
                }, sort_keys=True), encoding="utf-8")
            return type("Completed", (), {"returncode": 0, "timed_out": False, "termination_signal": None, "stdout": b"", "stderr": b""})()

        hostile = {
            runner.BASELINE_PLAN_ENV: "/tmp/forged-plan.json",
            runner.BASELINE_PLAN_SHA_ENV: "sha256:" + "0" * 64,
            runner.BASELINE_PLAN_REF_ENV: "forged",
        }
        source_plan = self.case_root / "exact-plan.json"
        source_plan.write_bytes(canonical_json_bytes(plan))
        source_ref = source_plan.relative_to(ROOT).as_posix()
        with mock.patch.dict(os.environ, hostile), mock.patch.object(
            runner, "run_command", side_effect=inspect
        ):
            receipt = self._run(
                plan, registry,
                plan_bytes=source_plan.read_bytes(),
                plan_ref=source_ref,
            )
        self.assertEqual(
            "PASS", receipt["terminal"]["status"],
            captured.get("stderr") or (receipt["evidence"][0] if receipt["evidence"] else receipt),
        )
        self.assertEqual(canonical_json_bytes(plan), captured["raw"])
        self.assertEqual(
            "sha256:" + hashlib.sha256(captured["raw"]).hexdigest(), captured["sha"]
        )
        self.assertEqual(source_ref, captured["ref"])
        self.assertFalse(captured["path"].exists())

    def test_declared_artifact_is_runner_bound_and_projected_to_reviewer(self) -> None:
        plan, registry = self._plan([("artifact", True, "printf artifact")])
        registry["evidence"]["artifact"]["result_artifact"] = "code-health-report-v1"
        artifact_path = self.case_root / "report.json"
        report = {
            "schema": "quwoquan.code-health-delta",
            "terminal": "PR_WARN",
            "baseSha": plan["merge_base_sha"],
            "headSha": plan["head_sha"],
            "changedPathsDigest": plan["candidate_evidence_identity"]["changed_paths_digest"],
            "summary": {
                "changedFiles": len(plan["changed_paths"]),
                "duplicationPercent": 1.043,
            },
            "findings": [{"code": "CODE_HEALTH.CHANGE_SIZE_ADVISORY", "path": "<candidate>", "terminal": "PR_WARN", "message": "large"}],
            "evidenceFingerprint": {"ref": "evidence-fingerprint-v1:sha256:" + "c" * 64, "digest": "sha256:" + "c" * 64},
        }
        artifact_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        artifact_ref = artifact_path.relative_to(ROOT).as_posix()

        def emit(_args, *positional, **kwargs):
            descriptor = Path(kwargs["env"][runner.RESULT_PATH_ENV])
            payload = {
                "kind": "code-health-report-v1",
                "ref": artifact_ref,
                "canonical_bytes_sha256": "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                "schema": report["schema"],
                "terminal": report["terminal"],
                "report_identity": "sha256:" + "d" * 64,
                "evidence_fingerprint_ref": report["evidenceFingerprint"]["ref"],
                "evidence_fingerprint_digest": report["evidenceFingerprint"]["digest"],
                "base_sha": plan["merge_base_sha"],
                "head_sha": plan["head_sha"],
                "changed_paths_digest": plan["candidate_evidence_identity"]["changed_paths_digest"],
                "impact_plan_ref": plan["candidate_evidence_identity"]["impact_plan_ref"],
                "impact_plan_digest": plan["candidate_evidence_identity"]["impact_plan_digest"],
                "candidate_evidence_ref": plan["candidate_evidence_identity"]["ref"],
                "candidate_evidence_sha256": plan["candidate_evidence_identity"]["canonical_bytes_sha256"],
                "plan_ref": "test-fixture:exact-plan",
                "plan_sha256": "sha256:" + hashlib.sha256(canonical_json_bytes(plan)).hexdigest(),
                "summary": report["summary"],
                "findings": report["findings"],
            }
            descriptor.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            return type("Completed", (), {"returncode": 0, "timed_out": False, "termination_signal": None, "stdout": b"", "stderr": b""})()

        source = {"mode": "workspace", "head_sha": plan["head_sha"], "merge_base_sha": plan["merge_base_sha"], "repository_clean": True, "immutable": False}
        with mock.patch.object(runner, "run_command", side_effect=emit), mock.patch.object(
            runner, "_workspace_source_classification", return_value=source
        ), mock.patch.object(runner, "_assert_source_head"):
            receipt = self._run(plan, registry)
        artifact = receipt["evidence"][0]["artifact"]
        self.assertEqual("code-health-report-v1", artifact["kind"])
        self.assertEqual(report["summary"], artifact["summary"])
        self.assertEqual(report["findings"], artifact["findings"])
        runner.validate_named_evidence_receipt(receipt)
        reviewer = review.build_reviewer_input(
            plan,
            {"receipt_ref": "receipt.json", "canonical_bytes_sha256": "sha256:" + "e" * 64},
            evidence_summary=receipt,
            reviewer_role=plan["reviewers"][0]["role"],
        )
        projected = reviewer["assembled_input"]["evidence_summary"]["results"][0]["artifact"]
        self.assertEqual(artifact, projected)

    def test_declared_artifact_identity_drift_and_missing_descriptor_fail_closed(self) -> None:
        plan, registry = self._plan([("artifact", True, "printf artifact")])
        registry["evidence"]["artifact"]["result_artifact"] = "code-health-report-v1"
        source = {"mode": "workspace", "head_sha": plan["head_sha"], "merge_base_sha": plan["merge_base_sha"], "repository_clean": True, "immutable": False}
        completed = type("Completed", (), {"returncode": 0, "timed_out": False, "termination_signal": None, "stdout": b"", "stderr": b""})()
        with mock.patch.object(runner, "run_command", return_value=completed), mock.patch.object(
            runner, "_workspace_source_classification", return_value=source
        ), mock.patch.object(runner, "_assert_source_head"), self.assertRaisesRegex(
            runner.EvidenceRunnerError, "descriptor"
        ):
            self._run(plan, registry)

        report_path = self.case_root / "drift-report.json"
        report = {"schema": "quwoquan.code-health-delta", "terminal": "PASS", "baseSha": plan["merge_base_sha"], "headSha": plan["head_sha"], "changedPathsDigest": plan["candidate_evidence_identity"]["changed_paths_digest"], "summary": {}, "findings": [], "evidenceFingerprint": {"ref": "evidence-fingerprint-v1:sha256:" + "c" * 64, "digest": "sha256:" + "c" * 64}}
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")

        for field in ("plan_ref", "candidate_evidence_ref", "changed_paths_digest", "impact_plan_digest"):
            with self.subTest(field=field):
                def emit(_args, *positional, **kwargs):
                    candidate = plan["candidate_evidence_identity"]
                    payload = {
                        "kind": "code-health-report-v1", "ref": report_path.relative_to(ROOT).as_posix(),
                        "canonical_bytes_sha256": "sha256:" + hashlib.sha256(report_path.read_bytes()).hexdigest(),
                        "schema": report["schema"], "terminal": report["terminal"], "report_identity": "sha256:" + "d" * 64,
                        "evidence_fingerprint_ref": report["evidenceFingerprint"]["ref"], "evidence_fingerprint_digest": report["evidenceFingerprint"]["digest"],
                        "base_sha": plan["merge_base_sha"], "head_sha": plan["head_sha"], "changed_paths_digest": candidate["changed_paths_digest"],
                        "impact_plan_ref": candidate["impact_plan_ref"], "impact_plan_digest": candidate["impact_plan_digest"],
                        "candidate_evidence_ref": candidate["ref"], "candidate_evidence_sha256": candidate["canonical_bytes_sha256"],
                        "plan_ref": "test-fixture:exact-plan", "plan_sha256": "sha256:" + hashlib.sha256(canonical_json_bytes(plan)).hexdigest(),
                        "summary": report["summary"], "findings": report["findings"],
                    }
                    payload[field] = "sha256:" + "0" * 64 if field.endswith("digest") else "forged"
                    Path(kwargs["env"][runner.RESULT_PATH_ENV]).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
                    return completed
                with mock.patch.object(runner, "run_command", side_effect=emit), mock.patch.object(
                    runner, "_workspace_source_classification", return_value=source
                ), mock.patch.object(runner, "_assert_source_head"), self.assertRaisesRegex(
                    runner.EvidenceRunnerError, "identity 漂移"
                ):
                    self._run(plan, registry)

    def test_declared_artifact_digest_drift_fails_closed(self) -> None:
        plan, registry = self._plan([("artifact", True, "printf artifact")])
        registry["evidence"]["artifact"]["result_artifact"] = "code-health-report-v1"

        def emit(_args, *positional, **kwargs):
            descriptor = Path(kwargs["env"][runner.RESULT_PATH_ENV])
            candidate = plan["candidate_evidence_identity"]
            descriptor.write_text(json.dumps({
                "kind": "code-health-report-v1", "ref": "README.md",
                "canonical_bytes_sha256": "sha256:" + "0" * 64,
                "schema": "quwoquan.code-health-delta", "terminal": "PASS",
                "report_identity": "sha256:" + "d" * 64,
                "evidence_fingerprint_ref": "evidence-fingerprint-v1:sha256:" + "c" * 64,
                "evidence_fingerprint_digest": "sha256:" + "c" * 64,
                "base_sha": plan["merge_base_sha"], "head_sha": plan["head_sha"],
                "changed_paths_digest": candidate["changed_paths_digest"],
                "impact_plan_ref": candidate["impact_plan_ref"],
                "impact_plan_digest": candidate["impact_plan_digest"],
                "candidate_evidence_ref": candidate["ref"],
                "candidate_evidence_sha256": candidate["canonical_bytes_sha256"],
                "plan_ref": "test-fixture:exact-plan",
                "plan_sha256": "sha256:" + hashlib.sha256(canonical_json_bytes(plan)).hexdigest(),
                "summary": {}, "findings": [],
            }, sort_keys=True), encoding="utf-8")
            return type("Completed", (), {"returncode": 0, "timed_out": False, "termination_signal": None, "stdout": b"", "stderr": b""})()

        source = {"mode": "workspace", "head_sha": plan["head_sha"], "merge_base_sha": plan["merge_base_sha"], "repository_clean": True, "immutable": False}
        with mock.patch.object(runner, "run_command", side_effect=emit), mock.patch.object(
            runner, "_workspace_source_classification", return_value=source
        ), mock.patch.object(runner, "_assert_source_head"), self.assertRaisesRegex(
            runner.EvidenceRunnerError, "bytes digest"
        ):
            self._run(plan, registry)

    def test_runner_refuses_missing_exact_plan_channel(self) -> None:
        plan, registry = self._plan([("safe", True, "printf safe")])
        ids = [item["id"] for item in plan["evidence"]]
        with mock.patch.object(review, "_checklist_evidence", return_value=ids), self.assertRaisesRegex(
            runner.EvidenceRunnerError, "exact plan bytes/ref"
        ):
            runner.run_plan(plan, registry=registry, cwd=ROOT)

    def test_review_baseline_rejects_plan_bytes_ref_candidate_paths_and_registry_drift(self) -> None:
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        command = str(registry["evidence"]["review-baseline"]["command"])
        paths = [
            "specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md"
        ]
        manifest = self._manifest(paths[0])
        candidate = build_candidate_evidence(self.manifest_ref, paths, repo_root=ROOT)
        candidate_path = _write_content_addressed_bytes(
            canonical_json_bytes(candidate), subdirectory="candidates/by-fingerprint"
        )
        plan = review.build_plan(
            registry, "dev", "POST", None, paths,
            context_manifest=manifest, context_manifest_ref=self.manifest_ref,
            candidate_evidence_ref=candidate_path.relative_to(ROOT).as_posix(),
        )
        wrong_bytes = canonical_json_bytes({**plan, "scope": "forged"})
        with self.assertRaisesRegex(runner.EvidenceRunnerError, "exact plan bytes"):
            self._run(plan, registry, plan_bytes=wrong_bytes)

        cases = [
            ("candidate", lambda value: value["candidate_evidence_identity"].__setitem__("ref", value["owner_identity"]["ref"])),
            ("changed_paths", lambda value: value.__setitem__("changed_paths", ["README.md"])),
            ("evidence_registry", lambda value: value["evidence"][0].__setitem__("command", "printf forged")),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                changed = copy.deepcopy(plan)
                mutate(changed)
                with self.assertRaisesRegex(
                    runner.EvidenceRunnerError,
                    "CANDIDATE|IDENTITY|FINGERPRINT_CHANGED|command 与 registry|identity",
                ):
                    self._run(changed, registry, plan_bytes=canonical_json_bytes(changed))

        source_plan = self.case_root / "source-plan.json"
        source_plan.write_bytes(canonical_json_bytes(plan))
        with tempfile.TemporaryDirectory(prefix="qwq-review-evidence-plan-") as directory:
            injected = Path(directory) / "exact-plan.json"
            injected.write_bytes(canonical_json_bytes(plan))
            source_plan.write_bytes(canonical_json_bytes({**plan, "generated_at": "drift"}))
            completed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "quwoquan_ops/gate/verify_review_baseline.py")],
                cwd=ROOT,
                env={
                    **os.environ,
                    runner.BASELINE_PLAN_ENV: str(injected),
                    runner.BASELINE_PLAN_SHA_ENV: "sha256:" + hashlib.sha256(injected.read_bytes()).hexdigest(),
                    runner.BASELINE_PLAN_REF_ENV: source_plan.relative_to(ROOT).as_posix(),
                },
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(2, completed.returncode)
        self.assertIn("ref bytes", completed.stderr)

        outside = self.case_root / "outside-plan.json"
        outside.write_bytes(canonical_json_bytes(plan))
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "quwoquan_ops/gate/verify_review_baseline.py")],
            cwd=ROOT,
            env={
                **os.environ,
                runner.BASELINE_PLAN_ENV: str(outside),
                runner.BASELINE_PLAN_SHA_ENV: "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest(),
                runner.BASELINE_PLAN_REF_ENV: "forged",
            },
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(2, completed.returncode)

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
        child_pid = Path(
            self.enterContext(
                tempfile.TemporaryDirectory(prefix="qwq-evidence-child-pid-")
            )
        ) / "child.pid"
        self.assertFalse(child_pid.is_relative_to(ROOT))
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

    def test_create_once_receipt_is_idempotent_and_conflicts_on_same_run_id(self) -> None:
        first = {"run_id": "same", "terminal": {"status": "PASS"}}
        path = runner._write_receipt_create_once("same", first)
        self.addCleanup(lambda: shutil.rmtree(path.parent, ignore_errors=True))
        self.assertEqual(path, runner._write_receipt_create_once("same", dict(first)))
        with self.assertRaisesRegex(runner.EvidenceRunnerError, "create-once conflict"):
            runner._write_receipt_create_once(
                "same", {"run_id": "same", "terminal": {"status": "GATE_BLOCK"}}
            )

    def test_zero_evidence_plan_is_rejected(self) -> None:
        plan, registry = self._plan([])
        with self.assertRaisesRegex(runner.EvidenceRunnerError, "不得为空"):
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
