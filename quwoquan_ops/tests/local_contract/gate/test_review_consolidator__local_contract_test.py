"""Deterministic Review consolidation contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t2
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import evidence_runner  # noqa: E402
import review_consolidator  # noqa: E402
import review_dispatch  # noqa: E402
import handoff_consumer  # noqa: E402
from lib.agent_governance_contract import canonical_bytes_sha256, contract_schema_version  # noqa: E402
from lib.evidence_fingerprint import canonical_json_bytes
from lib.candidate_evidence import build_candidate_evidence
from lib.feature_tree.content_addressed_writer import _write_content_addressed_bytes  # noqa: E402
from lib.feature_tree.commands import _context_manifest, discover_nodes  # noqa: E402
from lib.feature_tree.ownership import resolve_target_details  # noqa: E402
from lib.local_readiness.core import LocalReadinessError, _load_review_inputs  # noqa: E402

REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"
CASE_ROOT = ROOT / ".qwq_output/env/repo/local/review-consolidator-tests"


class ReviewConsolidatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._created_content_refs: list[tuple[Path, bytes]] = []
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        registry["workflows"]["dev"]["baseline_evidence"] = ""
        registry["evidence"] = {
            "fixture": {
                "command": "printf fixture",
                "segment": "POST",
                "required": True,
                "timeout_seconds": 300,
                "covers": [],
            }
        }
        target = (
            "specs/feature-tree/runtime/development-workflow-governance/"
            "agent-skill-review-context-organization/spec.md"
        )
        nodes = discover_nodes()
        manifest = _context_manifest(
            target, resolve_target_details(target, nodes), nodes
        )
        manifest["evidence_fingerprint"] = review_dispatch.embedded_fingerprint_binding(
            review_dispatch.build_feature_context_fingerprint(manifest, repo_root=ROOT)
        )
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_root = (
            ROOT / ".qwq_output/env/repo/runs/feature-tree/by-fingerprint"
        )
        manifest_root.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_root / (
            hashlib.sha256(manifest_bytes).hexdigest() + ".json"
        )
        manifest_existed = manifest_path.exists()
        manifest_path.write_bytes(manifest_bytes)
        if not manifest_existed:
            cls._created_content_refs.append((manifest_path, manifest_bytes))
        manifest_ref = manifest_path.relative_to(ROOT).as_posix()

        changed_paths = [target]
        candidate = build_candidate_evidence(
            manifest_ref, changed_paths, repo_root=ROOT
        )
        candidate_bytes = canonical_json_bytes(candidate)
        candidate_path = ROOT / (
            ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/"
            "candidates/by-fingerprint/"
            f"{hashlib.sha256(candidate_bytes).hexdigest()}.json"
        )
        candidate_existed = candidate_path.exists()
        candidate_path = _write_content_addressed_bytes(
            candidate_bytes, subdirectory="candidates/by-fingerprint"
        )
        if not candidate_existed:
            cls._created_content_refs.append((candidate_path, candidate_bytes))

        source = evidence_runner._workspace_source_classification(ROOT)
        source["repository_clean"] = True
        with (
            mock.patch.object(
                review_dispatch, "_checklist_evidence", return_value=["fixture"]
            ),
            mock.patch.object(
                evidence_runner,
                "run_command",
                side_effect=cls._execute_fixture,
            ),
            mock.patch.object(
                evidence_runner,
                "_workspace_source_classification",
                return_value=source,
            ),
        ):
            plan = review_dispatch.build_plan(
                registry,
                "dev",
                "POST",
                None,
                changed_paths,
                context_manifest=manifest,
                context_manifest_ref=manifest_ref,
                candidate_evidence_ref=candidate_path.relative_to(ROOT).as_posix(),
            )
            evidence = evidence_runner.run_plan(
                plan, registry=registry, cwd=ROOT, run_id="run-1",
                plan_bytes=canonical_json_bytes(plan),
                plan_ref=".qwq_output/test-fixture-plan.json",
            )
        cls._registry_template = registry
        cls._manifest_path = manifest_path
        cls._plan_template = plan
        cls._evidence_template = evidence

    @classmethod
    def tearDownClass(cls) -> None:
        for path, expected in reversed(cls._created_content_refs):
            try:
                if path.is_file() and not path.is_symlink() and path.read_bytes() == expected:
                    path.unlink()
            except OSError:
                pass

    @staticmethod
    def _execute_fixture(*_args, **_kwargs):
        return mock.Mock(
            returncode=0,
            stdout=b"fixture",
            stderr=b"",
            timed_out=False,
            termination_signal=None,
        )

    def setUp(self) -> None:
        self.case = CASE_ROOT / uuid.uuid4().hex
        self.case.mkdir(parents=True)
        self.artifact = self.case / "asset.txt"
        self.artifact.write_text("stable\n", encoding="utf-8")
        self.registry = copy.deepcopy(self._registry_template)
        self.manifest_path = self._manifest_path
        self.plan = copy.deepcopy(self._plan_template)
        self.evidence = copy.deepcopy(self._evidence_template)
        self.evidence_path = self.case / "evidence.json"
        self.evidence_path.write_bytes(canonical_json_bytes(self.evidence))

    def tearDown(self) -> None:
        shutil.rmtree(self.case, ignore_errors=True)

    def _result(self, role: str, *, status: str = "completed", findings=None, closure=None):
        evidence = handoff_consumer.named_evidence_identity(
            self.evidence_path.relative_to(ROOT).as_posix(), self.evidence
        )
        result = {
            "schema_version": contract_schema_version("review_result"),
            "role": role,
            "status": status,
            "plan_fingerprint_ref": evidence["plan_fingerprint_ref"],
            "plan_fingerprint_digest": evidence["plan_fingerprint_digest"],
            "evidence_receipt_ref": evidence["receipt_ref"],
            "evidence_receipt_canonical_bytes_sha256": evidence["canonical_bytes_sha256"],
            "evidence_run_id": evidence["run_id"],
            "evidence_generation_id": evidence["generation_id"],
            "execution_fingerprint_ref": evidence["execution_fingerprint_ref"],
            "execution_fingerprint_digest": evidence["execution_fingerprint_digest"],
            "result_fingerprint_ref": evidence["result_fingerprint_ref"],
            "result_fingerprint_digest": evidence["result_fingerprint_digest"],
            "assembled_input_byte_count": 1024,
            "assembled_input_digest": "sha256:" + "a" * 64,
            "assembled_input_compression": {"mode": "full", "applied": False, "changes": [], "attempts": []},
            "started_at": evidence["finished_at"],
            "finished_at": evidence["finished_at"],
            "findings": findings or [],
        }
        if closure is not None:
            result["candidate_closure"] = closure
        path = self.case / f"review-{role}-{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        return path.relative_to(ROOT).as_posix(), result

    def _consolidate(self, results):
        with mock.patch.object(
            review_dispatch, "_checklist_evidence", return_value=["fixture"]
        ):
            return review_consolidator.consolidate(
                self.plan,
                self.evidence,
                results,
                evidence_receipt_ref=self.evidence_path.relative_to(ROOT).as_posix(),
                registry=self.registry,
                generated_at=self.evidence["finished_at"],
            )

    def _replace_evidence(self, *, repository_clean: bool, run_id: str) -> None:
        source = evidence_runner._workspace_source_classification(ROOT)
        source["repository_clean"] = repository_clean
        with (
            mock.patch.object(
                review_dispatch, "_checklist_evidence", return_value=["fixture"]
            ),
            mock.patch.object(
                evidence_runner,
                "run_command",
                side_effect=self._execute_fixture,
            ),
            mock.patch.object(
                evidence_runner,
                "_workspace_source_classification",
                return_value=source,
            ),
        ):
            self.evidence = evidence_runner.run_plan(
                self.plan,
                registry=self.registry,
                cwd=ROOT,
                run_id=run_id,
                plan_bytes=canonical_json_bytes(self.plan),
                plan_ref=".qwq_output/test-fixture-plan.json",
            )
        self.evidence_path.write_bytes(canonical_json_bytes(self.evidence))

    @staticmethod
    def _finding(
        finding_id: str,
        severity: str,
        *,
        summary: str = "finding",
        owner: str = "developer",
    ) -> dict[str, str]:
        return {
            "id": finding_id,
            "owner": owner,
            "severity": severity,
            "path": "README.md",
            "summary": summary,
        }

    def _set_optional_reviewer(self, role: str = "optional") -> None:
        optional = copy.deepcopy(self.plan["reviewers"][0])
        optional.update({"role": role, "required": False})
        self.plan["reviewers"] = [optional]

    def test_completed_result_is_pass_and_findings_deduplicate(self) -> None:
        finding = {
            "id": "F-001",
            "owner": "developer",
            "severity": "advisory",
            "path": "README.md",
            "summary": "same",
        }
        result = self._consolidate(
            [self._result("developer", findings=[finding, dict(finding)])]
        )
        self.assertEqual("PASS", result["terminal"]["status"])
        self.assertEqual("reusable", result["evidence_identities"][0]["evidence_class"])
        self.assertIs(result["evidence_identities"][0]["admission_eligible"], True)
        self.assertEqual(["F-001"], [item["id"] for item in result["findings"]])

    def test_exact_result_carries_closure_and_recomputation_rejects_stale(self):
        candidate = self.plan["candidate_evidence_identity"]
        closure = {
            "candidate_fingerprint_ref": candidate["fingerprint_ref"],
            "candidate_fingerprint_digest": candidate["fingerprint_digest"],
            "health_dispositions": [], "replacements": [],
        }
        result = self._consolidate([self._result("developer", closure=closure)])
        self.assertEqual("PASS", result["terminal"]["status"])
        self.assertEqual(closure, result["reviewer_results"][0]["candidate_closure"])
        closure["candidate_fingerprint_digest"] = "stale"
        with self.assertRaisesRegex(ValueError, "candidate fingerprint stale"):
            self._consolidate([self._result("developer", closure=closure)])

    def test_external_exact_closure_recomputes_and_rejects_forged_partial_payload(self):
        reviewers = [self._result("developer")]
        consolidation = self._consolidate(reviewers)
        evidence_pairs = [(self.evidence_path.relative_to(ROOT).as_posix(), self.evidence)]
        with mock.patch.object(review_dispatch, "_checklist_evidence", return_value=["fixture"]):
            validated = review_consolidator.validate_exact_consolidation(
                consolidation, plan=self.plan, evidence_pairs=evidence_pairs,
                reviewer_pairs=reviewers, registry=self.registry,
            )
            self.assertEqual(consolidation, validated)
            with self.assertRaisesRegex(ValueError, "字段漂移"):
                review_consolidator.validate_exact_consolidation(
                    consolidation, plan={"workflow": "dev"}, evidence_pairs=evidence_pairs,
                    reviewer_pairs=reviewers, registry=self.registry,
                )
            forged = copy.deepcopy(reviewers[0][1])
            forged["findings"] = [self._finding("injected", "advisory")]
            with self.assertRaisesRegex(ValueError, "exact bytes 与 payload"):
                review_consolidator.validate_exact_consolidation(
                    consolidation, plan=self.plan, evidence_pairs=evidence_pairs,
                    reviewer_pairs=[(reviewers[0][0], forged)], registry=self.registry,
                )
            with self.assertRaisesRegex(ValueError, "字段漂移"):
                review_consolidator.validate_exact_consolidation(
                    {"terminal": {"status": "PASS"}}, plan=self.plan,
                    evidence_pairs=evidence_pairs, reviewer_pairs=reviewers, registry=self.registry,
                )

    def test_required_incomplete_is_gate_block(self) -> None:
        result = self._consolidate([])
        self.assertEqual("GATE_BLOCK", result["terminal"]["status"])
        self.assertEqual(
            ["REVIEW.REQUIRED_REVIEWER_INCOMPLETE"],
            result["terminal"]["codes"],
        )

    def test_optional_incomplete_is_pr_warn(self) -> None:
        self._set_optional_reviewer()
        result = self._consolidate([])
        self.assertEqual("PR_WARN", result["terminal"]["status"])
        self.assertEqual(
            ["REVIEW.OPTIONAL_REVIEWER_INCOMPLETE"],
            result["terminal"]["codes"],
        )

    def test_completed_required_gate_block_finding_blocks(self) -> None:
        result = self._consolidate(
            [
                self._result(
                    "developer",
                    findings=[self._finding("F-BLOCK-REQUIRED", "GATE_BLOCK")],
                )
            ]
        )
        self.assertEqual(
            {"status": "GATE_BLOCK", "codes": []}, result["terminal"]
        )

    def test_completed_optional_gate_block_finding_blocks(self) -> None:
        self._set_optional_reviewer()
        result = self._consolidate(
            [
                self._result(
                    "optional",
                    findings=[self._finding("F-BLOCK-OPTIONAL", "GATE_BLOCK")],
                )
            ]
        )
        self.assertEqual("GATE_BLOCK", result["terminal"]["status"])

    def test_pr_warn_finding_warns(self) -> None:
        result = self._consolidate(
            [
                self._result(
                    "developer",
                    findings=[self._finding("F-WARN", "PR_WARN")],
                )
            ]
        )
        self.assertEqual("PR_WARN", result["terminal"]["status"])

    def test_advisory_only_findings_pass(self) -> None:
        result = self._consolidate(
            [
                self._result(
                    "developer",
                    findings=[self._finding("F-ADVISORY", "advisory")],
                )
            ]
        )
        self.assertEqual("PASS", result["terminal"]["status"])

    def test_conflicting_duplicate_finding_ids_are_rejected(self) -> None:
        findings = [
            self._finding("F-CONFLICT", "PR_WARN", summary="first"),
            self._finding("F-CONFLICT", "PR_WARN", summary="second"),
        ]
        with self.assertRaisesRegex(ValueError, "finding id 冲突"):
            self._consolidate([self._result("developer", findings=findings)])

    def test_unknown_finding_severity_is_rejected(self) -> None:
        finding = self._finding("F-UNKNOWN", "UNKNOWN")
        with self.assertRaisesRegex(ValueError, "severity 非法"):
            self._consolidate([self._result("developer", findings=[finding])])

    def test_malformed_finding_is_rejected(self) -> None:
        finding = self._finding("", "GATE_BLOCK")
        with self.assertRaisesRegex(ValueError, "必须为非空字符串"):
            self._consolidate([self._result("developer", findings=[finding])])

    def test_consolidation_exact_shape_remains_consumer_compatible(self) -> None:
        result = self._consolidate([self._result("developer")])
        contract = review_consolidator.contract_section("review_consolidation")
        self.assertEqual(
            [
                "malformed_unknown_stale_or_required_incomplete",
                "gate_block_finding",
                "optional_incomplete_or_pr_warn_finding",
                "advisory_or_pass",
            ],
            contract["terminal_precedence"],
        )
        self.assertEqual(
            {
                "identity_field": "id",
                "exact_duplicate": "retain_once",
                "conflict": "reject",
            },
            contract["finding_deduplication"],
        )
        self.assertEqual(set(contract["required_fields"]), set(result))
        self.assertEqual({"status", "codes"}, set(result["terminal"]))
        self.assertEqual("developer", result["reviewer_results"][0]["role"])
        self.assertEqual(
            self.evidence["run_id"],
            result["reviewer_results"][0]["evidence_run_id"],
        )


    def test_local_readiness_rejects_feedback_only_consolidation_evidence(self) -> None:
        self._replace_evidence(
            repository_clean=False,
            run_id="run-feedback-only",
        )
        consolidation = self._consolidate([self._result("developer")])
        consolidation_path = self.case / "consolidation.json"
        consolidation_path.write_text(json.dumps(consolidation), encoding="utf-8")

        with self.assertRaisesRegex(
            LocalReadinessError, "REVIEW.EVIDENCE_FEEDBACK_ONLY"
        ):
            _load_review_inputs(
                consolidation_path,
                [self.evidence_path],
                repo_root=ROOT,
                required=True,
            )

    def test_local_readiness_rejects_drifted_consolidation_evidence_identity(self) -> None:
        self._replace_evidence(
            repository_clean=False,
            run_id="run-feedback-only-drifted",
        )
        consolidation = self._consolidate([self._result("developer")])
        consolidation["evidence_identities"][0]["result_fingerprint_digest"] = (
            "sha256:" + "0" * 64
        )
        consolidation_path = self.case / "consolidation-drifted.json"
        consolidation_path.write_text(json.dumps(consolidation), encoding="utf-8")

        with self.assertRaisesRegex(
            LocalReadinessError,
            "未绑定提供的 required evidence exact identities",
        ):
            _load_review_inputs(
                consolidation_path,
                [self.evidence_path],
                repo_root=ROOT,
                required=True,
            )


    def test_result_from_evidence_run_one_rejected_for_run_two(self) -> None:
        old_result = self._result("developer")
        with mock.patch.object(
            review_dispatch, "_checklist_evidence", return_value=["fixture"]
        ):
            second = evidence_runner.run_plan(
                self.plan, registry=self.registry, cwd=ROOT, run_id="run-2",
                plan_bytes=canonical_json_bytes(self.plan), plan_ref=".qwq_output/test-fixture-plan.json",
            )
        second_path = self.case / "evidence-run-2.json"
        second_path.write_text(json.dumps(second), encoding="utf-8")
        self.evidence = second
        self.evidence_path = second_path
        with self.assertRaisesRegex(ValueError, "run_id|generation|receipt ref|canonical"):
            self._consolidate([old_result])

    def test_result_missing_or_predating_evidence_is_rejected(self) -> None:
        ref, result = self._result("developer")
        result.pop("evidence_run_id")
        (ROOT / ref).write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaises(ValueError):
            self._consolidate([(ref, result)])

        ref, result = self._result("developer")
        result["started_at"] = "2000-01-01T00:00:00+00:00"
        (ROOT / ref).write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pre-evidence"):
            self._consolidate([(ref, result)])

    def test_result_ref_replacement_and_fingerprint_drift_are_rejected(self) -> None:
        ref, result = self._result("developer")
        for field in (
            "evidence_receipt_canonical_bytes_sha256",
            "execution_fingerprint_digest",
            "result_fingerprint_digest",
        ):
            drifted = copy.deepcopy(result)
            drifted[field] = "sha256:" + "0" * 64
            (ROOT / ref).write_text(json.dumps(drifted), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ValueError):
                self._consolidate([(ref, drifted)])

    def test_stale_reviewer_result_is_rejected(self) -> None:
        ref, result = self._result("developer")
        result["result_fingerprint_digest"] = "sha256:" + "0" * 64
        (ROOT / ref).write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaises(ValueError):
            self._consolidate([(ref, result)])


class CandidateClosureTest(unittest.TestCase):
    """# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007"""

    def setUp(self):
        self.case = CASE_ROOT / uuid.uuid4().hex
        self.case.mkdir(parents=True)
        self.owner = "specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md"
        self.path = "quwoquan_ops/cli/review_consolidator.py"
        self.candidate = {
            "ref": "candidate-exact", "canonical_bytes_sha256": "sha256:" + "a" * 64,
            "changed_paths_digest": "paths", "impact_plan_ref": "impact", "impact_plan_digest": "impact-digest",
            "fingerprint_ref": "fingerprint", "fingerprint_digest": "digest",
        }
        self.plan = {
            "workflow": "dev", "changed_paths": [self.path],
            "candidate_evidence_identity": self.candidate,
            "owner_identity": {"resolved_owner": self.owner},
            "contexts": [{"path": self.owner, "exists": True}],
            "reviewers": [{"role": "developer", "kind": "primary"}],
        }
        self.receipt = {"evidence": []}
        self.closure = {
            "candidate_fingerprint_ref": "fingerprint", "candidate_fingerprint_digest": "digest",
            "health_dispositions": [], "replacements": [],
        }
        self.results = {"developer": {"status": "completed", "candidate_closure": self.closure}}

    def tearDown(self):
        shutil.rmtree(self.case)

    def report(self, findings, *, evidence_id="health", terminal=None, minute=0):
        terminal = terminal or ("PR_WARN" if findings else "PASS")
        report = {
            "schema": "quwoquan.code-health-delta", "terminal": terminal,
            "baseSha": "base", "headSha": "head", "changedPathsDigest": "paths",
            "summary": {"findingCount": len(findings)}, "findings": findings,
            "evidenceFingerprint": {"ref": "report-fingerprint", "digest": "report-digest"},
        }
        raw = canonical_json_bytes(report)
        path = self.case / f"{evidence_id}.json"
        path.write_bytes(raw)
        artifact = {
            "kind": "code-health-report-v1", "ref": path.relative_to(ROOT).as_posix(),
            "canonical_bytes_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "schema": report["schema"], "terminal": terminal, "base_sha": "base", "head_sha": "head",
            "changed_paths_digest": "paths", "summary": report["summary"], "findings": findings,
            "evidence_fingerprint_ref": "report-fingerprint", "evidence_fingerprint_digest": "report-digest",
            "candidate_evidence_ref": "candidate-exact", "candidate_evidence_sha256": self.candidate["canonical_bytes_sha256"],
            "impact_plan_ref": "impact", "impact_plan_digest": "impact-digest",
        }
        entry = {
            "id": evidence_id, "exit_code": 0, "timed_out": False, "artifact": artifact,
            "started_at": f"2026-09-11T00:{minute:02}:00+00:00",
            "finished_at": f"2026-09-11T00:{minute:02}:01+00:00",
        }
        self.receipt["evidence"].append(entry)
        return entry

    def warning(self, *, path=None, terminal="PR_WARN", finding_id="F-1"):
        return {"findingId": finding_id, "path": path or self.path, "terminal": terminal,
                "code": "CODE_HEALTH.TEST", "message": "objective fixture"}

    def disposition(self, *, action="owner-open", finding_id="F-1"):
        value = {"finding_id": finding_id, "disposition": action, "reason": "named current evidence",
                 "evidence_ids": ["health"], "open_ref": f"{self.owner}#open-003" if action == "owner-open" else None}
        self.closure["health_dispositions"].append(value)
        return value

    def validate(self):
        review_consolidator.validate_candidate_closure(self.plan, self.receipt, self.results)

    def test_health_pass_without_replacement_needs_no_inventory(self):
        self.report([])
        self.validate()
        self.results["developer"].pop("candidate_closure")
        self.validate()

    def test_handwritten_dev_missing_health_rejected_other_workflow_preserved(self):
        with self.assertRaisesRegex(ValueError, "手写 dev"):
            self.validate()
        self.plan["workflow"] = "design"
        self.validate()
        self.plan["workflow"] = "dev"
        self.plan["changed_paths"] = [self.owner]
        self.validate()

    def test_current_lowest_owner_open_and_candidate_warning_pass(self):
        for path in (self.path, "<candidate>"):
            with self.subTest(path=path):
                self.receipt["evidence"] = []
                self.closure["health_dispositions"] = []
                self.report([self.warning(path=path)])
                self.disposition()
                self.validate()

    def test_missing_duplicate_extra_disposition_rejected(self):
        self.report([self.warning()])
        with self.assertRaisesRegex(ValueError, "漏项"):
            self.validate()
        disposition = self.disposition()
        self.closure["health_dispositions"].append(dict(disposition))
        with self.assertRaisesRegex(ValueError, "重复"):
            self.validate()
        self.closure["health_dispositions"][-1]["finding_id"] = "extra"
        with self.assertRaisesRegex(ValueError, "漏项或多项"):
            self.validate()

    def test_stale_fingerprint_and_artifact_identity_rejected(self):
        entry = self.report([])
        self.closure["candidate_fingerprint_digest"] = "old"
        with self.assertRaisesRegex(ValueError, "fingerprint stale"):
            self.validate()
        self.closure["candidate_fingerprint_digest"] = "digest"
        entry["artifact"]["candidate_evidence_ref"] = "old"
        with self.assertRaisesRegex(ValueError, "stale"):
            self.validate()

    def test_original_artifact_bytes_tampering_rejected(self):
        entry = self.report([])
        (ROOT / entry["artifact"]["ref"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "bytes digest"):
            self.validate()

    def test_original_warning_cannot_be_hidden_by_missing_closure(self):
        self.report([self.warning()])
        self.results["developer"].pop("candidate_closure")
        with self.assertRaisesRegex(ValueError, "缺 primary"):
            self.validate()

    def test_unknown_finding_id_duplicate_and_blocker_rejected(self):
        for findings in ([self.warning(), self.warning()], [{"path": self.path}], [self.warning(terminal="GATE_BLOCK")]):
            self.receipt["evidence"] = []
            self.report(findings)
            self.closure["health_dispositions"] = []
            self.disposition()
            with self.subTest(findings=findings), self.assertRaises(ValueError):
                self.validate()

    def test_open_absent_wrong_owner_and_blocking_open_rejected(self):
        self.report([self.warning()])
        disposition = self.disposition()
        for ref in (f"{self.owner}#open-999", f"{self.owner}#open-005", "specs/feature-tree/spec.md#open-003"):
            disposition["open_ref"] = ref
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                self.validate()
        disposition["open_ref"] = f"{self.owner}#open-003"
        self.plan["contexts"] = []
        with self.assertRaisesRegex(ValueError, "context"):
            self.validate()

    def test_fake_out_of_scope_path_or_owner_rejected(self):
        for path in (self.path, "quwoquan_ops/cli/review_dispatch.py", "<candidate>"):
            self.receipt["evidence"] = []
            self.closure["health_dispositions"] = []
            self.report([self.warning(path=path)])
            self.disposition(action="out-of-scope")
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.validate()

    def test_real_outside_owner_with_boundary_evidence_passes(self):
        self.report([self.warning(path="specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md")])
        self.disposition(action="out-of-scope")
        self.validate()

    def test_fix_now_needs_later_current_validation_without_original_warning(self):
        self.report([self.warning()])
        disposition = self.disposition(action="fix-now")
        with self.assertRaisesRegex(ValueError, "缺后续"):
            self.validate()
        self.report([], evidence_id="new-health", minute=1)
        disposition["evidence_ids"] = ["new-health"]
        self.validate()
        self.receipt["evidence"].pop()
        self.report([self.warning()], evidence_id="new-health", minute=1)
        with self.assertRaisesRegex(ValueError, "原有效 warning"):
            self.validate()

    def test_fix_now_uses_finding_identity_not_other_member_same_code_path(self):
        # 仅测试消费语义，不声称确定性 immutable producer 能产生此变化。
        original = self.report([self.warning()])
        latest = self.report([self.warning(finding_id="other-member")], evidence_id="new-health", minute=1)
        review_consolidator._fix_now(original, self.warning(), [latest],
                                    [(original, original["artifact"]), (latest, latest["artifact"])])

    def test_replacement_without_old_config_or_test_uses_null_not_applicable(self):
        self.report([])
        replacement = self.replacement()
        for item in replacement["cleanup"][1:]:
            item.update(path=None, action="not-applicable", reason="scan found no old artifacts of this kind")
        self.validate()
        replacement["cleanup"][1]["path"] = "invented.yaml"
        with self.assertRaisesRegex(ValueError, "path 必须 null"):
            self.validate()
        replacement["cleanup"][1]["path"] = None
        replacement["cleanup"].append({"path": self.path, "kind": "config", "action": "retained", "reason": "contradictory"})
        with self.assertRaisesRegex(ValueError, "不得与同 kind"):
            self.validate()

    def replacement(self):
        value = {
            "old_path": self.path, "old_symbols": ["old_entry"],
            "successor_path": self.path, "successor_symbols": ["validate_candidate_closure"],
            "consumers": [{"path": self.path, "status": "migrated", "reason": "same module caller migrated"}],
            "cleanup": [
                {"path": self.path, "kind": "implementation", "action": "retained", "reason": "other entry points still live"},
                {"path": "quwoquan_ops/policies/agent_governance_contract.yaml", "kind": "config", "action": "retained", "reason": "canonical contract still used"},
                {"path": "quwoquan_ops/tests/local_contract/gate/test_review_consolidator__local_contract_test.py", "kind": "test", "action": "retained", "reason": "regression tests retained"},
            ],
            "dynamic_entry_status": "resolved", "scan_evidence_ids": ["health"], "test_evidence_ids": ["health"],
        }
        self.closure["replacements"] = [value]
        return value

    def test_replacement_retention_complete_passes_unknown_is_not_deletion(self):
        self.report([])
        replacement = self.replacement()
        self.validate()
        replacement["dynamic_entry_status"] = "unknown"
        self.validate()
        replacement["cleanup"][0]["action"] = "removed"
        with self.assertRaisesRegex(ValueError, "unknown 不可自动删除"):
            self.validate()

    def test_replacement_missing_cleanup_scan_test_consumer_or_successor_rejected(self):
        self.report([])
        for field, value in (("cleanup", []), ("consumers", []), ("scan_evidence_ids", []),
                             ("test_evidence_ids", ["missing"]), ("successor_path", "missing.py"), ("old_symbols", [])):
            replacement = self.replacement()
            replacement[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate()
        replacement = self.replacement()
        replacement["cleanup"].pop()
        with self.assertRaisesRegex(ValueError, "config/test"):
            self.validate()

    def test_specialist_cannot_supply_primary_closure(self):
        self.report([])
        self.results["specialist"] = self.results.pop("developer")
        with self.assertRaisesRegex(ValueError, "completed primary"):
            self.validate()


class PortableReviewChainTest(unittest.TestCase):
    """# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007"""

    def test_real_clean_source_transport_warning_open_and_tampering(self):
        import os
        import subprocess
        import tempfile
        from lib import candidate_evidence as candidates
        from lib import feature_context_fingerprint as owner_fingerprint
        from lib.feature_tree import context

        CASE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=CASE_ROOT) as directory:
            source, transport = Path(directory) / "source", Path(directory) / "transport"
            source.mkdir(); transport.mkdir()
            for root_name in ("quwoquan_ops", "specs", ".agents"):
                for path in (ROOT / root_name).rglob("*"):
                    if path.is_file() and path.suffix in {".py", ".yaml", ".yml", ".json", ".md", ".sh"}:
                        destination = source / path.relative_to(ROOT)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(path, destination)
            shutil.copyfile(ROOT / "quwoquan_ops/policies/ci_test_ownership.json", source / "quwoquan_ops/policies/ci_test_ownership.json")
            self.assertTrue((source / "quwoquan_ops/policies/ci_test_ownership.json").is_file())
            (source / ".gitignore").write_text(".qwq_output/\n")
            script = source / "quwoquan_ops/cli/portable_health_fixture.py"
            script.write_text('''import os,json,hashlib
from pathlib import Path
from quwoquan_ops.ci.verify_code_health_delivery import verify_delivery
root=Path.cwd()
plan=json.loads(Path(os.environ["QWQ_REVIEW_BASELINE_PLAN_PATH"]).read_text())
candidate=plan["candidate_evidence_identity"]
report,path,identity=verify_delivery(root,base_sha=plan["merge_base_sha"],head_sha=plan["head_sha"],expected_path_digest=candidate["changed_paths_digest"],expected_impact_plan_digest=candidate["impact_plan_digest"])
raw=path.read_bytes()
artifact={"kind":"code-health-report-v1","ref":path.relative_to(root).as_posix(),"canonical_bytes_sha256":"sha256:"+hashlib.sha256(raw).hexdigest(),"schema":report["schema"],"terminal":report["terminal"],"report_identity":identity,"evidence_fingerprint_ref":report["evidenceFingerprint"]["ref"],"evidence_fingerprint_digest":report["evidenceFingerprint"]["digest"],"base_sha":report["baseSha"],"head_sha":report["headSha"],"changed_paths_digest":report["changedPathsDigest"],"impact_plan_ref":candidate["impact_plan_ref"],"impact_plan_digest":candidate["impact_plan_digest"],"candidate_evidence_ref":candidate["ref"],"candidate_evidence_sha256":candidate["canonical_bytes_sha256"],"plan_ref":os.environ["QWQ_REVIEW_BASELINE_PLAN_REF"],"plan_sha256":os.environ["QWQ_REVIEW_BASELINE_PLAN_SHA256"],"summary":report["summary"],"findings":report["findings"]}
Path(os.environ["QWQ_NAMED_EVIDENCE_RESULT_PATH"]).write_text(json.dumps(artifact))
''')
            registry = yaml.safe_load((source / ".agents/skills/review/references/registry.yaml").read_text())
            registry["workflows"]["dev"]["baseline_evidence"] = ""
            registry["profiles"] = {}
            registry["evidence"] = {"code-health-delta": {"command": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B quwoquan_ops/cli/portable_health_fixture.py", "segment": "POST", "required": True, "timeout_seconds": 300, "covers": [], "result_artifact": "code-health-report-v1"}}
            (source / ".agents/skills/review/references/registry.yaml").write_text(yaml.safe_dump(registry))
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=source, text=True).strip()
            git("init", "-b", "main"); git("config", "user.name", "Portable test"); git("config", "user.email", "test@example.invalid")
            git("add", "."); git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            target = "quwoquan_ops/cli/review_consolidator.py"
            with (source / target).open("a") as stream:
                stream.write("\ndef portable_warning(value):\n" + "".join(f"    if value == {number}:\n        return {number}\n" for number in range(24)) + "    return -1\n")
            git("checkout", "-b", "dev1.0"); git("add", target); git("commit", "-qm", "warning")
            head = git("rev-parse", "HEAD")
            git("branch", "lane/engineering", head); git("update-ref", "refs/remotes/origin/dev1.0", head)
            exact_range = {"base_sha": base, "head_sha": head, "head_tree": git("rev-parse", "HEAD^{tree}")}
            current = candidates._current_owner(target, repo_root=source)
            owner = {**current, "schema_version": 4, "canonical_contexts": [{"path": current["resolved_owner"], "anchor": None, "kind": "spec"}], "applicable_agents": ["AGENTS.md"], "open_items": []}
            owner["evidence_fingerprint"] = owner_fingerprint.embedded_fingerprint_binding(owner_fingerprint.build_feature_context_fingerprint(owner, repo_root=source))
            def publish(value, subdirectory=None):
                with context.source_repository(source):
                    return _write_content_addressed_bytes(canonical_json_bytes(value), subdirectory=subdirectory).relative_to(source).as_posix()
            owner_ref = publish(owner)
            candidate = candidates.build_candidate_evidence(owner_ref, [target], repo_root=source, source_identity={**exact_range, "producer_lane": "lane/engineering"})
            candidate_ref = publish(candidate, "candidates/by-fingerprint")
            plan = review_dispatch.build_plan(registry, "dev", "POST", None, [target], context_manifest=owner,
                context_manifest_ref=owner_ref, candidate_evidence_ref=candidate_ref, git_range=exact_range, source_repository=source)
            plan_ref = ".qwq_output/portable/plan.json"
            (source / plan_ref).parent.mkdir(parents=True)
            (source / plan_ref).write_bytes(canonical_json_bytes(plan))
            receipt = evidence_runner.run_plan(plan, cwd=source, registry=registry, plan_bytes=canonical_json_bytes(plan), plan_ref=plan_ref, source_repository=source)
            if receipt["terminal"]["status"] != "PASS":
                environment = dict(os.environ)
                environment.update({evidence_runner.BASELINE_PLAN_ENV: str(source / plan_ref), evidence_runner.BASELINE_PLAN_SHA_ENV: "sha256:" + hashlib.sha256(canonical_json_bytes(plan)).hexdigest(), evidence_runner.BASELINE_PLAN_REF_ENV: plan_ref, evidence_runner.RESULT_PATH_ENV: str(source / ".qwq_output/debug-descriptor.json")})
                debug = subprocess.run(["/bin/sh", "-c", registry["evidence"]["code-health-delta"]["command"]], cwd=source, env=environment, capture_output=True, text=True)
                self.fail(debug.stderr + debug.stdout)
            artifact = receipt["evidence"][0]["artifact"]
            self.assertEqual("PR_WARN", artifact["terminal"])
            receipt_ref = ".qwq_output/portable/evidence.json"
            receipt_bytes = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            (source / receipt_ref).write_bytes(receipt_bytes)
            identity = handoff_consumer.named_evidence_identity_from_raw(receipt_ref, receipt_bytes, receipt)
            result = {"schema_version": contract_schema_version("review_result"), "role": "developer", "status": "completed",
                "evidence_receipt_ref": receipt_ref, "evidence_receipt_canonical_bytes_sha256": identity["canonical_bytes_sha256"],
                "evidence_run_id": identity["run_id"], "evidence_generation_id": identity["generation_id"],
                "assembled_input_byte_count": 1024, "assembled_input_digest": "sha256:" + "a" * 64, "assembled_input_compression": {},
                "started_at": receipt["finished_at"], "finished_at": receipt["finished_at"], "findings": []}
            for field in ("plan_fingerprint_ref", "plan_fingerprint_digest", "execution_fingerprint_ref", "execution_fingerprint_digest", "result_fingerprint_ref", "result_fingerprint_digest"):
                result[field] = identity[field]
            result["candidate_closure"] = {"candidate_fingerprint_ref": plan["candidate_evidence_identity"]["fingerprint_ref"], "candidate_fingerprint_digest": plan["candidate_evidence_identity"]["fingerprint_digest"], "replacements": [],
                "health_dispositions": [{"finding_id": item["findingId"], "disposition": "owner-open", "reason": "current owner scope", "evidence_ids": ["code-health-delta"], "open_ref": current["resolved_owner"] + "#open-003"} for item in artifact["findings"] if item["terminal"] == "PR_WARN"]}
            result_ref = ".qwq_output/portable/review.json"
            (source / result_ref).write_bytes(canonical_json_bytes(result))
            consolidation = review_consolidator.consolidate(plan, [(receipt_ref, receipt)], [(result_ref, result)], registry=registry, source_repository=source)
            shutil.copytree(source / ".qwq_output", transport / ".qwq_output")
            def validate():
                return review_consolidator.validate_exact_consolidation(consolidation, plan=plan, evidence_pairs=[(receipt_ref, receipt)], reviewer_pairs=[(result_ref, result)], registry=registry, source_repository=source, dependency_root=transport)
            self.assertEqual("PASS", validate()["terminal"]["status"])
            path = transport / artifact["ref"]
            original = path.read_bytes(); path.write_text("{}")
            with self.assertRaises(ValueError): validate()
            path.write_bytes(original)
            owner_path = transport / owner_ref
            original_owner = owner_path.read_bytes(); owner_path.unlink()
            with self.assertRaises((ValueError, OSError)): validate()
            owner_path.symlink_to(source / owner_ref)
            with self.assertRaises((ValueError, OSError)): validate()
            owner_path.unlink(); owner_path.write_bytes(original_owner)
            transported_plan = transport / plan_ref
            original_plan = transported_plan.read_bytes(); transported_plan.write_text("{}")
            with self.assertRaises(ValueError): validate()
            transported_plan.write_bytes(original_plan)
            self.assertEqual(head, git("rev-parse", "HEAD"))
            self.assertEqual(head, git("merge-base", "HEAD", "origin/dev1.0"))
            self.assertEqual(base, git("merge-base", "HEAD", "main"))
            git("branch", "-f", "lane/engineering", base)
            with self.assertRaises(ValueError): validate()
            git("branch", "-f", "lane/engineering", head)
            git("commit", "--allow-empty", "-qm", "stale")
            with self.assertRaises(ValueError): validate()


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
