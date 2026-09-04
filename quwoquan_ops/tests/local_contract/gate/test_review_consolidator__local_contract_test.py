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

    def _result(self, role: str, *, status: str = "completed", findings=None):
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


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
