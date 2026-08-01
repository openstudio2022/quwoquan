"""local_contract: real receipt assembly for nonprod data provisioning.

spec_ref: specs/feature-tree/spec.md#uat-009
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import nonprod_data_evidence as evidence


class NonprodDataEvidenceContractTest(unittest.TestCase):
    def test_assembler_only_accepts_explicit_candidate_bound_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "target": "alpha-local",
                "environment": "alpha",
                "baselineId": "sha256:" + "1" * 64,
                "packageDigest": "sha256:" + "2" * 64,
                "sourceRevision": "a" * 40,
                "imageDigest": "sha256:" + "3" * 64,
                "release": {
                    "candidate": {"releaseDigest": "sha256:" + "4" * 64}
                },
            }

            def write_case(
                name: str,
                *,
                schema: str,
                case_id: str,
                provider_receipt_id: str = "",
            ) -> str:
                payload = {
                    "schema": schema,
                    "caseId": case_id,
                    "status": "passed",
                    "executed": 1,
                    "skipped": 0,
                    "target": "alpha-local",
                    "baselineId": manifest["baselineId"],
                    "packageDigest": manifest["packageDigest"],
                    "releaseDigest": manifest["release"]["candidate"][
                        "releaseDigest"
                    ],
                    "attemptId": f"attempt-{name}",
                    "networkBoundary": "user_journey",
                    "specRefs": ["specs/feature-tree/spec.md#uat-009"],
                    "telemetryReceipt": f"receipt:telemetry:{name}",
                }
                if provider_receipt_id:
                    payload["providerReceiptId"] = provider_receipt_id
                path = root / f"{name}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                return str(path)

            shares = [
                write_case(
                    f"share-{index}",
                    schema=evidence.SHARE_CASE_SCHEMA,
                    case_id="nonprod-outbound-share-delivery",
                    provider_receipt_id=f"provider-share-{index}",
                )
                for index in range(3)
            ]
            reliability = {
                name: write_case(
                    name,
                    schema=evidence.RELIABILITY_CASE_SCHEMA,
                    case_id=case_id,
                )
                for name, case_id in evidence.RELIABILITY_CASE_IDS.items()
            }
            provider = {
                name: str(root / f"provider-{name}.json")
                for name in evidence.PROVIDER_CAPABILITIES
            }
            for path in provider.values():
                Path(path).write_text("{}", encoding="utf-8")

            def provider_result(reference: str, **kwargs):
                name = str(kwargs["name"])
                return {
                    "status": "passed",
                    "attemptId": f"attempt-{name}",
                    "baselineId": manifest["baselineId"],
                    "packageDigest": manifest["packageDigest"],
                    "caseResultRef": reference,
                    "adapterId": f"ext.provider.{name.lower()}",
                    "implementationStatus": "sandbox",
                    "networkBoundary": "user_journey",
                    "sourceRef": reference,
                }

            output = root / "assembled" / "gate-evidence.json"
            with mock.patch.object(
                evidence,
                "_load_provider_receipt",
                side_effect=provider_result,
            ):
                payload = evidence.assemble_nonprod_gate_evidence(
                    target="alpha-local",
                    environment="alpha",
                    candidate_manifest=manifest,
                    share_receipt_refs=shares,
                    provider_receipt_refs=provider,
                    reliability_receipt_refs=reliability,
                    evidence_root=root,
                    output_path=output,
                )

        self.assertEqual(payload["shareProviderReceiptIds"], [
            "provider-share-0",
            "provider-share-1",
            "provider-share-2",
        ])
        self.assertEqual(set(payload["providerConformance"]), set(provider))
        self.assertEqual(set(payload["reliabilityEvidence"]), set(reliability))

    def test_cli_requires_each_named_receipt_exactly_once(self) -> None:
        parser = stackctl.build_parser()
        args = parser.parse_args(
            [
                "nonprod-data-evidence",
                "--target",
                "alpha-local",
                "--share-receipt",
                "one.json",
                "--provider-receipt",
                "identityOtp=otp.json",
                "--reliability-receipt",
                "expiredSession=expired.json",
            ]
        )
        with self.assertRaisesRegex(ValueError, "must bind exactly"):
            stackctl._explicit_evidence_mappings(
                list(args.provider_receipt),
                allowed=set(evidence.PROVIDER_CAPABILITIES),
                option="--provider-receipt",
            )


if __name__ == "__main__":
    unittest.main()
