"""environment patrol smoke：App UAT case 报告写入契约。

由职责边界从 device discovery / execution 测试拆出；测试方法与断言保持不变。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolSmokeReportWriterTest(EnvironmentPatrolSmokeCaseBase):
    def test_report_writer_emits_only_explicit_app_uat_case_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_plan_ref = "data/releases/release-a/uat/sample_plan.json"
            binding_ref = "target-uat-bindings/binding.json"
            sample_plan_path = root / sample_plan_ref
            binding_path = root / binding_ref
            sample_plan_path.parent.mkdir(parents=True)
            binding_path.parent.mkdir(parents=True)
            sample_plan_path.write_bytes(b"sample-plan\n")
            binding_path.write_bytes(b"target-binding\n")
            page_ref = "env/alpha/runs/app-content/page-evidence.json"
            page_path = root / page_ref
            page_path.parent.mkdir(parents=True)
            page_path.write_bytes(b"page-evidence\n")
            marker = {
                "schema": smoke.APP_UAT_CASE_EVIDENCE_SCHEMA,
                "sampleId": "baseline-article-001",
                "entrySurface": "direct_or_object_route",
                "carrier": "article",
                "objectId": "article-001",
                "specRef": "spec.md#gwt-001",
                "runnerIdentity": "qwq.content_consumer.direct_or_object_route.article.v1",
                "status": "passed",
                "startedAt": "2026-08-30T00:00:00Z",
                "completedAt": "2026-08-30T00:01:00Z",
                "target": {"kind": "page", "id": "article-001"},
                "pageEvidence": {
                    "status": "present",
                    "ref": page_ref,
                    "sha256": "sha256:" + hashlib.sha256(page_path.read_bytes()).hexdigest(),
                },
            }
            report = {
                "status": "passed",
                "appUatAuthority": {
                    "samplePlanRef": sample_plan_ref,
                    "samplePlanSha256": "sha256:" + hashlib.sha256(sample_plan_path.read_bytes()).hexdigest(),
                    "targetUatBindingRef": binding_ref,
                    "targetUatBindingSha256": "sha256:" + hashlib.sha256(binding_path.read_bytes()).hexdigest(),
                    "targetUatBindingDigest": "sha256:" + "2" * 64,
                    "releaseId": "release-a",
                    "releaseDigest": "sha256:" + "3" * 64,
                    "sourceIdentitySetDigest": "sha256:" + "4" * 64,
                    "commitSha": "a" * 40,
                    "contractGraphSourceHash": "b" * 64,
                    "candidateManifestSha256": "c" * 64,
                    "provider": "first-party-https",
                },
                "runs": [
                    {
                        "exitCode": 0,
                        "patrolExitCode": 0,
                        "evidence": {
                            "structuredEvidenceLogPath": "runs/device/device-evidence.log"
                        },
                    }
                ],
            }
            log_path = root / "runs/device/device-evidence.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                smoke.APP_UAT_CASE_EVIDENCE_PREFIX + json.dumps(marker) + "\n",
                encoding="utf-8",
            )
            report_path = root / "env/alpha/runs/app-content/report.json"

            with mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}, clear=False):
                smoke.write_report(report_path, report)

            sources = report["appUatCaseExecutionReports"]
            self.assertEqual(len(sources), 1)
            receipt = json.loads((root / sources[0]["receiptRef"]).read_text())
            self.assertEqual(receipt["schema"], "quwoquan_ops.app_uat_case_execution.v1")
            self.assertEqual(receipt["sampleId"], "baseline-article-001")
            self.assertEqual(receipt["entrySurface"], "direct_or_object_route")
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["pageEvidence"]["ref"], page_ref)

    def test_report_writer_collects_16_markers_with_distinct_host_page_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_plan_ref = "data/releases/release-a/uat/sample_plan.json"
            binding_ref = "target-uat-bindings/binding.json"
            sample_plan_path = root / sample_plan_ref
            binding_path = root / binding_ref
            sample_plan_path.parent.mkdir(parents=True)
            binding_path.parent.mkdir(parents=True)
            sample_plan_path.write_bytes(b"sample-plan\n")
            binding_path.write_bytes(b"target-binding\n")
            entries = ("feed", "search", "recommendation", "direct_or_object_route")
            carriers = ("homepage", "article", "image", "video")
            evidence_by_capture: dict[str, dict[str, str]] = {}
            markers = []
            for entry in entries:
                for carrier in carriers:
                    sample_id = f"baseline-{carrier}-001"
                    capture_id = f"{sample_id}--{entry}--{carrier}"
                    page_ref = f"env/alpha/runs/app-content/page/{capture_id}.png"
                    page_path = root / page_ref
                    page_path.parent.mkdir(parents=True, exist_ok=True)
                    page_path.write_bytes(capture_id.encode())
                    evidence_by_capture[capture_id] = {
                        "status": "present",
                        "ref": page_ref,
                        "sha256": "sha256:" + hashlib.sha256(page_path.read_bytes()).hexdigest(),
                    }
                    markers.append(
                        {
                            "schema": smoke.APP_UAT_CASE_EVIDENCE_SCHEMA,
                            "sampleId": sample_id,
                            "entrySurface": entry,
                            "carrier": carrier,
                            "objectId": f"source-{carrier}",
                            "specRef": "spec.md#gwt-004",
                            "runnerIdentity": f"qwq.content_consumer.{entry}.{carrier}.v1",
                            "status": "passed",
                            "startedAt": "2026-08-30T00:00:00Z",
                            "completedAt": "2026-08-30T00:01:00Z",
                            "target": {"kind": "object" if carrier == "homepage" else "page", "id": f"runtime-{carrier}"},
                            "pageEvidence": {"status": "host_captured", "captureId": capture_id},
                        }
                    )
            log_ref = "runs/device/device-evidence.log"
            log_path = root / log_ref
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                "".join(smoke.APP_UAT_CASE_EVIDENCE_PREFIX + json.dumps(marker) + "\n" for marker in markers),
                encoding="utf-8",
            )
            report = {
                # Parent failure is deliberately independent from the 16 explicit
                # marker statuses; no case may infer or lose passed from it.
                "status": "failed",
                "appUatAuthority": {
                    "samplePlanRef": sample_plan_ref,
                    "samplePlanSha256": "sha256:" + hashlib.sha256(sample_plan_path.read_bytes()).hexdigest(),
                    "targetUatBindingRef": binding_ref,
                    "targetUatBindingSha256": "sha256:" + hashlib.sha256(binding_path.read_bytes()).hexdigest(),
                    "targetUatBindingDigest": "sha256:" + "2" * 64,
                    "releaseId": "release-a",
                    "releaseDigest": "sha256:" + "3" * 64,
                    "sourceIdentitySetDigest": "sha256:" + "4" * 64,
                    "commitSha": "a" * 40,
                    "contractGraphSourceHash": "b" * 64,
                    "candidateManifestSha256": "c" * 64,
                    "provider": "first-party-https",
                },
                "runs": [{"exitCode": 1, "patrolExitCode": 0, "evidence": {"structuredEvidenceLogPath": log_ref}}],
            }
            report_path = root / "env/alpha/runs/app-content/report.json"
            resolver = lambda marker: evidence_by_capture[marker["pageEvidence"]["captureId"]]
            with mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}, clear=False):
                smoke.write_report(
                    report_path,
                    report,
                    app_uat_page_evidence_resolver=resolver,
                )
            self.assertEqual(len(report["appUatCaseExecutionReports"]), 16)
            receipts = [json.loads((root / source["receiptRef"]).read_text()) for source in report["appUatCaseExecutionReports"]]
            self.assertEqual(len({receipt["pageEvidence"]["ref"] for receipt in receipts}), 16)
            self.assertEqual(len({receipt["pageEvidence"]["sha256"] for receipt in receipts}), 16)
            self.assertTrue(all(receipt["status"] == "passed" for receipt in receipts))

    def test_report_writer_blocks_authority_when_explicit_case_marker_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_plan_ref = "data/releases/release-a/uat/sample_plan.json"
            binding_ref = "target-uat-bindings/binding.json"
            sample_plan_path = root / sample_plan_ref
            binding_path = root / binding_ref
            sample_plan_path.parent.mkdir(parents=True)
            binding_path.parent.mkdir(parents=True)
            sample_plan_path.write_bytes(b"sample-plan\n")
            binding_path.write_bytes(b"target-binding\n")
            report = {
                "status": "passed",
                "appUatAuthority": {
                    "samplePlanRef": sample_plan_ref,
                    "samplePlanSha256": "sha256:" + hashlib.sha256(sample_plan_path.read_bytes()).hexdigest(),
                    "targetUatBindingRef": binding_ref,
                    "targetUatBindingSha256": "sha256:" + hashlib.sha256(binding_path.read_bytes()).hexdigest(),
                    "targetUatBindingDigest": "sha256:" + "2" * 64,
                    "releaseId": "release-a",
                    "releaseDigest": "sha256:" + "3" * 64,
                    "sourceIdentitySetDigest": "sha256:" + "4" * 64,
                    "commitSha": "a" * 40,
                    "contractGraphSourceHash": "b" * 64,
                    "candidateManifestSha256": "c" * 64,
                    "provider": "first-party-https",
                },
                "runs": [
                    {
                        "exitCode": 0,
                        "patrolExitCode": 0,
                        "evidence": {
                            "structuredEvidenceLogPath": "runs/device/device-evidence.log"
                        },
                    }
                ],
            }
            log_path = root / "runs/device/device-evidence.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("suite passed without per-case marker\n", encoding="utf-8")
            report_path = root / "env/alpha/runs/app-content/report.json"

            with mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}, clear=False):
                smoke.write_report(report_path, report)

            self.assertEqual(report["status"], "gate_block")
            self.assertEqual(report["appUatCaseExecutionReports"], [])
            self.assertEqual(report["failureReason"], smoke.APP_UAT_CASE_EVIDENCE_MISSING)
            persisted = json.loads(report_path.read_text())
            self.assertEqual(persisted["status"], "gate_block")
            self.assertNotIn("passed", json.dumps(persisted["appUatCaseExecutionReports"]))



if __name__ == "__main__":
    unittest.main()
