"""Canonical handoff producer and consumer truth contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t2
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
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
import handoff_consumer  # noqa: E402
import handoff_manifest as producer  # noqa: E402
import review_dispatch  # noqa: E402
from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.candidate_evidence import build_candidate_evidence  # noqa: E402
from lib.feature_tree.content_addressed_writer import _write_content_addressed_bytes  # noqa: E402
from lib.feature_tree.commands import _context_manifest, discover_nodes  # noqa: E402
from lib.feature_tree.ownership import resolve_target_details  # noqa: E402

REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"
GATE_PATH = ROOT / "quwoquan_ops/gate/verify_handoff_manifest.py"
CASE_ROOT = ROOT / ".qwq_output/env/repo/local/handoff-producer-tests"
_spec = importlib.util.spec_from_file_location("_handoff_truth_gate", GATE_PATH)
assert _spec is not None and _spec.loader is not None
handoff_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(handoff_gate)


class HandoffManifestProducerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._created_content_refs: list[tuple[Path, bytes]] = []
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        target = (
            "specs/feature-tree/runtime/development-workflow-governance/"
            "agent-skill-review-context-organization/spec.md"
        )
        nodes = discover_nodes()
        manifest = _context_manifest(
            target, resolve_target_details(target, nodes), nodes
        )
        manifest["open_items"] = [
            {
                "path": target,
                "id": "OPEN-" + uuid.uuid4().hex[:8],
                "title": "fixture snapshot",
                "release_impact": "track",
            }
        ]
        manifest["evidence_fingerprint"] = review_dispatch.embedded_fingerprint_binding(
            review_dispatch.build_feature_context_fingerprint(manifest, repo_root=ROOT)
        )
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_root = ROOT / ".qwq_output/env/repo/runs/feature-tree/by-fingerprint"
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

        def execute(*_args, **_kwargs):
            return mock.Mock(
                returncode=0,
                stdout=b"fixture",
                stderr=b"",
                timed_out=False,
                termination_signal=None,
            )

        with mock.patch.object(evidence_runner, "run_command", side_effect=execute):
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
            receipt = evidence_runner.run_plan(
                plan,
                registry=registry,
                cwd=ROOT,
                plan_bytes=canonical_json_bytes(plan),
                plan_ref=".qwq_output/test-fixture-plan.json",
            )
        cls._registry_template = registry
        cls._manifest_template = manifest
        cls._manifest_ref = manifest_ref
        cls._plan_template = plan
        cls._receipt_template = receipt

    @classmethod
    def tearDownClass(cls) -> None:
        for path, expected in reversed(cls._created_content_refs):
            try:
                if path.is_file() and not path.is_symlink() and path.read_bytes() == expected:
                    path.unlink()
            except OSError:
                pass

    def setUp(self) -> None:
        self.case = CASE_ROOT / uuid.uuid4().hex
        self.case.mkdir(parents=True)
        self.run_id = "producer-test-" + uuid.uuid4().hex
        self._fixture_index = 0

    def tearDown(self) -> None:
        shutil.rmtree(self.case, ignore_errors=True)
        shutil.rmtree(producer.OUTPUT_ROOT / self.run_id, ignore_errors=True)

    def _fixture(self) -> tuple[dict, dict, Path, Path, Path]:
        self._fixture_index += 1
        fixture_root = self.case / f"fixture-{self._fixture_index}"
        fixture_root.mkdir()
        artifact = fixture_root / "artifact.txt"
        artifact.write_text("stable\n", encoding="utf-8")
        registry = copy.deepcopy(self._registry_template)
        plan = copy.deepcopy(self._plan_template)
        receipt = copy.deepcopy(self._receipt_template)

        plan_path = fixture_root / "plan.json"
        receipt_path = fixture_root / "receipt.json"
        plan_path.write_bytes(canonical_json_bytes(plan))
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        receipt_ref = receipt_path.relative_to(ROOT).as_posix()
        evidence_identity = handoff_consumer.named_evidence_identity(
            receipt_ref, receipt
        )
        role = plan["reviewers"][0]["role"]
        review_result = {
            "schema_version": producer.contract_schema_version("review_result"),
            "role": role,
            "status": "completed",
            "plan_fingerprint_ref": evidence_identity["plan_fingerprint_ref"],
            "plan_fingerprint_digest": evidence_identity["plan_fingerprint_digest"],
            "evidence_receipt_ref": evidence_identity["receipt_ref"],
            "evidence_receipt_canonical_bytes_sha256": evidence_identity["canonical_bytes_sha256"],
            "evidence_run_id": evidence_identity["run_id"],
            "evidence_generation_id": evidence_identity["generation_id"],
            "execution_fingerprint_ref": evidence_identity["execution_fingerprint_ref"],
            "execution_fingerprint_digest": evidence_identity["execution_fingerprint_digest"],
            "result_fingerprint_ref": evidence_identity["result_fingerprint_ref"],
            "result_fingerprint_digest": evidence_identity["result_fingerprint_digest"],
            "assembled_input_byte_count": 1024,
            "assembled_input_digest": "sha256:" + "a" * 64,
            "assembled_input_compression": {
                "mode": "full",
                "applied": False,
                "changes": [],
                "attempts": [],
            },
            "started_at": evidence_identity["finished_at"],
            "finished_at": evidence_identity["finished_at"],
            "findings": [],
        }
        result_path = fixture_root / "review-result.json"
        result_path.write_bytes(canonical_json_bytes(review_result))
        result_ref = result_path.relative_to(ROOT).as_posix()
        consolidation = __import__("review_consolidator").consolidate(
            plan,
            [(receipt_ref, receipt)],
            [(result_ref, review_result)],
            registry=registry,
            generated_at=evidence_identity["finished_at"],
            exact_bytes_by_ref={
                receipt_ref: receipt_path.read_bytes(),
                result_ref: result_path.read_bytes(),
            },
        )
        consolidation_path = fixture_root / "consolidation.json"
        consolidation_path.write_bytes(canonical_json_bytes(consolidation))
        data = {
            "run_id": self.run_id,
            "intent": "闭合 canonical handoff truth",
            "triggers": ["user_explicit_request"],
            "artifacts": [artifact.relative_to(ROOT).as_posix()],
            "pending_dispositions": [],
            "downstream": "plan-next",
            "owner_identity_ref": plan["owner_identity"]["ref"],
            "candidate_evidence_ref": plan["candidate_evidence_identity"]["ref"],
            "review_plan_ref": plan_path.relative_to(ROOT).as_posix(),
            "evidence_receipt_refs": [receipt_ref],
            "reviewer_result_refs": [result_ref],
            "review_consolidation_ref": consolidation_path.relative_to(ROOT).as_posix(),
            "recovery_token": "rerun_evidence_for_new_fingerprint",
        }
        return data, registry, artifact, plan_path, receipt_path

    def test_all_six_triggers_reject_feedback_only_workspace_evidence(self) -> None:
        data, _, _, _, _ = self._fixture()
        for trigger in producer.contract_section("handoff_manifest")["triggers"]:
            with self.subTest(trigger=trigger):
                data["triggers"] = [trigger]
                data["run_id"] = f"{self.run_id}-{trigger}"
                self.addCleanup(
                    shutil.rmtree,
                    producer.OUTPUT_ROOT / data["run_id"],
                    True,
                )
                with self.assertRaisesRegex(
                    producer.HandoffManifestError, "REVIEW.EVIDENCE_FEEDBACK_ONLY"
                ):
                    producer.produce(data)

    def test_ordinary_closed_step_does_not_persist(self) -> None:
        with mock.patch.object(producer.handoff_store, "publish") as publish:
            self.assertEqual(
                "no_persistent_handoff", producer.produce({"triggers": []})
            )
        publish.assert_not_called()
        self.assertFalse((producer.OUTPUT_ROOT / self.run_id).exists())

    def test_rejects_missing_nonpass_and_wrong_plan_receipts(self) -> None:
        data, _, _, _, receipt_path = self._fixture()
        data["evidence_receipt_refs"] = [
            (self.case / "missing.json").relative_to(ROOT).as_posix()
        ]
        with self.assertRaisesRegex(producer.HandoffManifestError, "不存在"):
            producer.produce(data)

        data, _, _, _, receipt_path = self._fixture()
        receipt = json.loads(receipt_path.read_text())
        receipt["terminal"] = {
            "status": "GATE_BLOCK",
            "code": "REVIEW.EVIDENCE_FAILED",
            "failed_evidence": "fixture",
        }
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(producer.HandoffManifestError, "EVIDENCE_FEEDBACK_ONLY|非 PASS"):
            producer.produce(data)

        data, _, _, _, receipt_path = self._fixture()
        receipt = json.loads(receipt_path.read_text())
        receipt["plan_fingerprint_digest"] = "sha256:" + "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(producer.HandoffManifestError, "plan identity"):
            producer.produce(data)

    def test_same_head_dirty_artifact_change_rejects_old_handoff(self) -> None:
        data, _, artifact, _, _ = self._fixture()
        with self.assertRaisesRegex(
            producer.HandoffManifestError, "REVIEW.EVIDENCE_FEEDBACK_ONLY"
        ):
            producer.produce(data)
        artifact.write_text("changed\n", encoding="utf-8")


    def test_rejects_evidence_ref_replacement_and_symlink_drift(self) -> None:
        data, _, _, _, receipt_path = self._fixture()
        original = receipt_path.read_text(encoding="utf-8")
        receipt_path.write_text(original + " ", encoding="utf-8")
        with self.assertRaises(producer.HandoffManifestError):
            producer.produce(data)

        data, _, _, _, receipt_path = self._fixture()
        target = self.case / "receipt-target.json"
        receipt_path.rename(target)
        receipt_path.symlink_to(target.name)
        with self.assertRaisesRegex(producer.HandoffManifestError, "symlink"):
            producer.produce(data)

    def test_rejects_review_result_or_consolidation_terminal_drift(self) -> None:
        data, _, _, _, _ = self._fixture()
        result_path = ROOT / data["reviewer_result_refs"][0]
        result = json.loads(result_path.read_text())
        result["evidence_run_id"] = "other-run"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaises(producer.HandoffManifestError):
            producer.produce(data)

        data, _, _, _, _ = self._fixture()
        consolidation_path = ROOT / data["review_consolidation_ref"]
        consolidation = json.loads(consolidation_path.read_text())
        consolidation["terminal"] = {"status": "PR_WARN", "codes": []}
        consolidation_path.write_text(json.dumps(consolidation), encoding="utf-8")
        with self.assertRaisesRegex(producer.HandoffManifestError, "EVIDENCE_FEEDBACK_ONLY|非 PASS"):
            producer.produce(data)


    def test_rejects_owner_plan_result_and_consolidation_ref_rename(self) -> None:
        for field in (
            "owner_identity_ref",
            "candidate_evidence_ref",
            "review_plan_ref",
            "reviewer_result_refs",
            "review_consolidation_ref",
        ):
            data, _, _, _, _ = self._fixture()
            raw = data[field][0] if isinstance(data[field], list) else data[field]
            path = ROOT / raw
            renamed = path.with_name(path.name + ".renamed")
            path.rename(renamed)
            try:
                with self.subTest(field=field), self.assertRaises(
                    producer.HandoffManifestError
                ):
                    producer.produce(data)
            finally:
                if renamed.exists() and not path.exists():
                    renamed.rename(path)

    def test_downstream_must_be_registered_workflow(self) -> None:
        data, _, _, _, _ = self._fixture()
        data["downstream"] = "made-up-workflow"
        with self.assertRaisesRegex(producer.HandoffManifestError, "registry"):
            producer.produce(data)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
