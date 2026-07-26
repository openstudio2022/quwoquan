from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
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


if __name__ == "__main__":
    unittest.main()
