from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/cli/prod/backup_recovery.py"
PLAN = ROOT / "quwoquan_ops/environments/prod/backup-recovery.yaml"


def _module():
    spec = importlib.util.spec_from_file_location("backup_recovery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BackupRecoveryReleaseGateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _module()
        self.plan = yaml.safe_load(PLAN.read_text(encoding="utf-8"))

    def _receipt(self) -> dict[str, object]:
        datasets = []
        for policy in self.plan["datasets"]:
            datasets.append(
                {
                    "id": policy["id"],
                    "contentDigest": "sha256:" + "a" * 64,
                    "kmsKeyVersion": "kms-prod-v7",
                    "encrypted": True,
                    "remoteCopyUri": f"oss://dr-prod/{policy['id']}/receipt",
                    "remoteCopyVerified": True,
                    "isolationTarget": f"isolated-{policy['id']}-restore",
                    "restoreVerified": True,
                    "rpoMinutes": policy["rpoMinutes"],
                    "restoreDurationMinutes": policy["rtoMinutes"],
                    "memberships": {
                        "resourceRef": policy["resourceRef"],
                        "namespaces": policy["namespaces"],
                        "indexPatterns": policy["indexPatterns"],
                        "snapshotPolicyRef": policy["snapshotPolicyRef"],
                    },
                    "readback": {
                        field: True for field in policy["readback"]
                    },
                }
            )
        return {
            "schema": "quwoquan-prod-backup-recovery-receipt",
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "planDigest": self.module._digest(self.plan),
            "datasets": datasets,
            "capacityCost": {
                "sourceUsagePercent": 60,
                "replicaUsagePercent": 61,
                "monthlyCostCny": 2000,
            },
        }

    def _run(self, receipt: dict[str, object]) -> tuple[int, dict[str, object]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt_path = root / "receipt.json"
            output = root / "report.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            result = subprocess.run(
                ["python3", str(SCRIPT), "--plan", str(PLAN), "--receipt", str(receipt_path), "--output", str(output)],
                check=False,
                text=True,
                capture_output=True,
            )
            return result.returncode, json.loads(output.read_text(encoding="utf-8"))

    def test_fresh_encrypted_isolated_receipt_is_accepted(self) -> None:
        code, report = self._run(self._receipt())
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "ok")

    def test_missing_or_tampered_evidence_blocks_release(self) -> None:
        missing = self._receipt()
        missing["datasets"] = missing["datasets"][:-1]
        code, report = self._run(missing)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("receipt dataset is missing" in issue for issue in report["issues"]))

        tampered = self._receipt()
        tampered["planDigest"] = "sha256:" + "b" * 64
        code, report = self._run(tampered)
        self.assertEqual(code, 2)
        self.assertIn("planDigest", " ".join(report["issues"]))

    def test_dataset_membership_must_be_exact(self) -> None:
        receipt = self._receipt()
        receipt["datasets"][0]["memberships"]["namespaces"] = []

        code, report = self._run(receipt)

        self.assertEqual(code, 2)
        self.assertTrue(
            any("memberships do not exactly match" in issue for issue in report["issues"]),
            report,
        )

    def test_wildcard_outside_membership_blocks_plan(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        search = next(item for item in plan["datasets"] if item["id"] == "search-objects")
        search["indexPatterns"] = ["quwoquan_objects-v2-*"]

        issues = self.module._validate_plan_datasets(plan)

        self.assertTrue(any("index pattern exceeds namespace membership" in issue for issue in issues), issues)

    def test_dataset_memberships_cannot_overlap_on_same_resource(self) -> None:
        plan = json.loads(json.dumps(self.plan))
        telemetry = next(
            item for item in plan["datasets"] if item["id"] == "product-telemetry"
        )
        telemetry["namespaces"].append("runtime-diagnostics-raw")

        issues = self.module._validate_plan_datasets(plan)

        self.assertTrue(
            any("backup membership overlaps" in issue for issue in issues),
            issues,
        )

    def test_false_readback_blocks_release(self) -> None:
        receipt = self._receipt()
        search = next(item for item in receipt["datasets"] if item["id"] == "search-objects")
        search["readback"]["canonicalDigest"] = False

        code, report = self._run(receipt)

        self.assertEqual(code, 2)
        self.assertIn(
            "search-objects: readback.canonicalDigest is not verified",
            report["issues"],
        )


if __name__ == "__main__":
    unittest.main()
