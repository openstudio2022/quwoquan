"""Canonical handoff producer and consumer truth contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t2
"""

from __future__ import annotations

import copy
import json
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
    def setUp(self) -> None:
        self.case = CASE_ROOT / uuid.uuid4().hex
        self.case.mkdir(parents=True)
        self.run_id = "producer-test-" + uuid.uuid4().hex

    def tearDown(self) -> None:
        shutil.rmtree(self.case, ignore_errors=True)
        shutil.rmtree(producer.OUTPUT_ROOT / self.run_id, ignore_errors=True)

    def _manifest(self) -> dict:
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
        path = self.case / "owner-manifest.json"
        path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        self.manifest_ref = path.relative_to(ROOT).as_posix()
        return manifest

    def _fixture(self) -> tuple[dict, dict, Path, Path, Path]:
        artifact = self.case / "artifact.txt"
        artifact.write_text("stable\n", encoding="utf-8")
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        plan = review_dispatch.build_plan(
            registry,
            "dev",
            "POST",
            None,
            ["quwoquan_ops/gate/verify_agent_context_budget.py"],
            context_manifest=self._manifest(),
            context_manifest_ref=self.manifest_ref,
        )
        real_run = evidence_runner.subprocess.run

        def execute(args, *positional, **kwargs):
            if args[:2] == ["/bin/sh", "-c"]:
                return mock.Mock(returncode=0, stdout=b"fixture", stderr=b"")
            return real_run(args, *positional, **kwargs)

        with mock.patch.object(evidence_runner.subprocess, "run", side_effect=execute):
            receipt = evidence_runner.run_plan(plan, registry=registry, cwd=ROOT)
        plan_path = self.case / "plan.json"
        receipt_path = self.case / "receipt.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        evidence_identity = handoff_consumer.named_evidence_identity(
            receipt_path.relative_to(ROOT).as_posix(), receipt
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
            "started_at": evidence_identity["finished_at"],
            "finished_at": evidence_identity["finished_at"],
            "findings": [],
        }
        result_path = self.case / "review-result.json"
        result_path.write_text(json.dumps(review_result), encoding="utf-8")
        result_identity = {
            "result_ref": result_path.relative_to(ROOT).as_posix(),
            "canonical_bytes_sha256": "sha256:" + __import__("hashlib").sha256(
                result_path.read_bytes()
            ).hexdigest(),
            "role": role,
        }
        consolidation = {
            "schema_version": producer.contract_schema_version("review_consolidation"),
            "plan_fingerprint_ref": plan["fingerprint_receipt"]["ref"],
            "plan_fingerprint_digest": plan["fingerprint_receipt"]["digest"],
            "evidence_identities": [evidence_identity],
            "reviewer_result_identities": [result_identity],
            "reviewer_results": [review_result],
            "findings": [],
            "incomplete_roles": [],
            "terminal": {"status": "PASS", "codes": []},
            "generated_at": evidence_identity["finished_at"],
        }
        consolidation_path = self.case / "consolidation.json"
        consolidation_path.write_text(json.dumps(consolidation), encoding="utf-8")
        data = {
            "run_id": self.run_id,
            "intent": "闭合 canonical handoff truth",
            "triggers": ["user_explicit_request"],
            "artifacts": [artifact.relative_to(ROOT).as_posix()],
            "pending_dispositions": [],
            "downstream": "plan-next",
            "owner_manifest_ref": plan["owner_manifest_identity"]["ref"],
            "review_plan_ref": plan_path.relative_to(ROOT).as_posix(),
            "evidence_receipt_refs": [receipt_path.relative_to(ROOT).as_posix()],
            "reviewer_result_refs": [result_path.relative_to(ROOT).as_posix()],
            "review_consolidation_ref": consolidation_path.relative_to(ROOT).as_posix(),
            "recovery_token": "rerun_evidence_for_new_fingerprint",
        }
        return data, registry, artifact, plan_path, receipt_path

    def test_all_six_triggers_persist_current_canonical_payload(self) -> None:
        data, _, _, _, _ = self._fixture()
        for trigger in producer.contract_section("handoff_manifest")["triggers"]:
            with self.subTest(trigger=trigger):
                data["triggers"] = [trigger]
                path = producer.produce(data)
                self.assertIsInstance(path, Path)
                payload = json.loads((path.parent / "payload.json").read_text())
                handoff_consumer.validate_handoff_payload(payload)
                text = path.read_text(encoding="utf-8")
                self.assertEqual([], handoff_gate.validate(text, str(path)))
                self.assertIn("exit=0", text)
                self.assertIn("make verify-agent-context-budget", text)
                self.assertIn("receipt=", text)

    def test_ordinary_closed_step_does_not_persist(self) -> None:
        data, _, _, _, _ = self._fixture()
        data["triggers"] = []
        self.assertEqual("no_persistent_handoff", producer.produce(data))
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
        with self.assertRaisesRegex(producer.HandoffManifestError, "非 PASS"):
            producer.produce(data)

        data, _, _, _, receipt_path = self._fixture()
        receipt = json.loads(receipt_path.read_text())
        receipt["plan_fingerprint_digest"] = "sha256:" + "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(producer.HandoffManifestError, "plan identity"):
            producer.produce(data)

    def test_same_head_dirty_artifact_change_rejects_old_handoff(self) -> None:
        data, _, artifact, _, _ = self._fixture()
        path = producer.produce(data)
        payload_path = path.parent / "payload.json"
        artifact.write_text("changed\n", encoding="utf-8")
        payload = json.loads(payload_path.read_text())
        with self.assertRaisesRegex(
            handoff_consumer.HandoffConsumerError, "FINGERPRINT_CHANGED"
        ):
            handoff_consumer.validate_handoff_payload(payload)


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
        with self.assertRaisesRegex(producer.HandoffManifestError, "非 PASS"):
            producer.produce(data)


    def test_rejects_owner_plan_result_and_consolidation_ref_rename(self) -> None:
        for field in (
            "owner_manifest_ref",
            "review_plan_ref",
            "reviewer_result_refs",
            "review_consolidation_ref",
        ):
            data, _, _, _, _ = self._fixture()
            raw = data[field][0] if isinstance(data[field], list) else data[field]
            path = ROOT / raw
            path.rename(path.with_name(path.name + ".renamed"))
            with self.subTest(field=field), self.assertRaises(
                producer.HandoffManifestError
            ):
                producer.produce(data)

    def test_downstream_must_be_registered_workflow(self) -> None:
        data, _, _, _, _ = self._fixture()
        data["downstream"] = "made-up-workflow"
        with self.assertRaisesRegex(producer.HandoffManifestError, "registry"):
            producer.produce(data)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
