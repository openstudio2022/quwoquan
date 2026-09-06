# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-002
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.android_official_release import (
    package_android_official_release,
)
from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError,
    inspect_official_distribution,
)
from quwoquan_ops.tests.local_contract.release.test_android_official_release__supply_chain__local_contract_test import (
    _executable,
)
from quwoquan_ops.tests.local_contract.release.test_official_distribution_release__supply_chain__local_contract_test import (
    _android_package,
    _deploy,
    _official_graph,
    _web_package,
    _write_json,
)


class MinimumSupportedBuildIncreaseTest(unittest.TestCase):
    def test_packager_binds_policy_evidence_into_release_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "release.apk"
            apk.write_bytes(b"signed-apk-fixture")
            analyzer = _executable(
                root / "apkanalyzer",
                """#!/bin/sh
case "$2" in
  application-id) echo com.leadwise.quwoquan ;;
  version-name) echo 1.8.2 ;;
  version-code) echo 18201 ;;
  min-sdk) echo 26 ;;
esac
""",
            )
            signer = _executable(
                root / "apksigner",
                """#!/bin/sh
echo 'Signer #1 certificate SHA-256 digest: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
""",
            )
            evidence_path = root / "source-evidence.json"
            _write_json(evidence_path, _valid_evidence())

            release = package_android_official_release(
                apk_path=apk,
                package_root=root / "package",
                public_origin="https://quwoquan.com",
                download_origin="https://cdn.quwoquan.com",
                expected_package="com.leadwise.quwoquan",
                expected_signing_certificate_sha256="a" * 64,
                minimum_supported_version="1.8.0",
                minimum_supported_build="18000",
                minimum_supported_build_evidence_path=evidence_path,
                apkanalyzer=str(analyzer),
                apksigner=str(signer),
            )

            manifest_path = Path(str(release["manifestPath"]))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["minimumSupportedBuildIncreaseEvidence"],
                _valid_evidence(),
            )

    def test_valid_policy_evidence_allows_raise_and_updates_canonical_latest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distribution, web = _deploy_baseline(root)
            android = _android_candidate(
                root / "android-18301",
                build="18301",
                minimum_version="1.8.0",
                minimum_build="18000",
                evidence=_valid_evidence(),
            )
            web = _web_package(root / "web-18301", build="18301")
            authority = _official_graph(
                root / "candidate-2",
                web_manifest=web,
                android_manifest=android,
            )

            receipt = _deploy(
                "app-release",
                authority,
                distribution,
                expected_current="18201",
            )

            self.assertTrue(receipt["minimumSupportedBuildRaised"])
            latest = json.loads(
                (distribution / "download/android/latest.json").read_text()
            )
            self.assertEqual(latest["minimumSupportedVersion"], "1.8.0")
            self.assertEqual(latest["minimumSupportedBuild"], "18000")
            self.assertNotIn("minimumVersion", latest)
            self.assertNotIn("minimumBuild", latest)
            inspection = inspect_official_distribution(
                distribution_root=distribution
            )
            self.assertEqual(inspection["status"], "ready")
            self.assertEqual(inspection["android"]["minimumSupportedBuild"], "18000")

    def test_raise_fails_closed_for_every_policy_threshold(self) -> None:
        cases: list[tuple[str, Any, str]] = [
            (
                "missing evidence",
                None,
                "requires canonical evidence",
            ),
            (
                "29 day observation",
                _evidence_with(
                    ("wouldBlock", "observationStartedAt"),
                    "2026-07-12T00:00:01Z",
                ),
                "at least 30 days",
            ),
            (
                "share equals threshold",
                _evidence_with(
                    ("wouldBlock", "oldVersionActiveInstallShareBasisPoints"),
                    10,
                ),
                "below 0.1 percent",
            ),
            (
                "support below 12 months",
                _evidence_with(
                    ("normalSupport", "supportedSince"),
                    "2025-08-11T00:00:01Z",
                ),
                "at least 12 months",
            ),
            (
                "update channel unverified",
                _evidence_with(("channels", "update", "verified"), False),
                "update channel is not verified",
            ),
            (
                "recovery channel unverified",
                _evidence_with(("channels", "recovery", "verified"), False),
                "recovery channel is not verified",
            ),
        ]
        for label, evidence, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                distribution, web = _deploy_baseline(root)
                android = _android_candidate(
                    root / "android-18301",
                    build="18301",
                    minimum_version="1.8.0",
                    minimum_build="18000",
                    evidence=evidence,
                )
                web = _web_package(root / "web-18301", build="18301")
                authority = _official_graph(
                    root / "candidate-2",
                    web_manifest=web,
                    android_manifest=android,
                )

                with self.assertRaisesRegex(
                    OfficialDistributionReleaseError,
                    expected_error,
                ):
                    _deploy(
                        "app-release",
                        authority,
                        distribution,
                        expected_current="18201",
                    )
                latest = json.loads(
                    (distribution / "download/android/latest.json").read_text()
                )
                self.assertEqual(latest["buildNumber"], "18201")
                self.assertEqual(latest["minimumSupportedBuild"], "17000")

    def test_high_risk_exception_fails_closed_without_graph_approval_authority(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            distribution, web = _deploy_baseline(root)
            evidence = _valid_evidence()
            evidence["wouldBlock"] = None
            evidence["normalSupport"] = None
            evidence["securityException"] = {
                "risk": "high",
                "reason": "actively exploited remote code execution vulnerability",
                "approvalAuthority": "governance-receipt.json",
            }
            android = _android_candidate(
                root / "android-18301",
                build="18301",
                minimum_version="1.8.0",
                minimum_build="18000",
                evidence=evidence,
            )
            web = _web_package(root / "web-18301", build="18301")
            authority = _official_graph(
                root / "candidate-2",
                web_manifest=web,
                android_manifest=android,
            )
            governance_path = authority["graph_root"] / "governance-receipt.json"
            _write_json(
                governance_path,
                {
                    "schema": "prod-release-governance-receipt",
                    "approved": True,
                    "artifactDigest": "sha256:" + "a" * 64,
                },
            )

            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "no canonical security exception approval authority",
            ):
                _deploy(
                    "app-release",
                    authority,
                    distribution,
                    expected_current="18201",
                )
            latest = json.loads(
                (distribution / "download/android/latest.json").read_text()
            )
            self.assertEqual(latest["buildNumber"], "18201")
            self.assertEqual(latest["minimumSupportedBuild"], "17000")

    def test_unchanged_or_lower_minimum_does_not_require_raise_evidence(self) -> None:
        for minimum_build in ("17000", "16000"):
            with self.subTest(minimum_build=minimum_build), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                distribution, web = _deploy_baseline(root)
                android = _android_candidate(
                    root / "android-18301",
                    build="18301",
                    minimum_version="1.6.0" if minimum_build == "16000" else "1.7.0",
                    minimum_build=minimum_build,
                    evidence=None,
                )
                web = _web_package(root / "web-18301", build="18301")
                authority = _official_graph(
                    root / "candidate-2",
                    web_manifest=web,
                    android_manifest=android,
                )
                receipt = _deploy(
                    "app-release",
                    authority,
                    distribution,
                    expected_current="18201",
                )
                self.assertFalse(receipt["minimumSupportedBuildRaised"])


def _deploy_baseline(root: Path) -> tuple[Path, Path]:
    web = _web_package(root / "web-package")
    android = _android_candidate(
        root / "android-18201",
        build="18201",
        minimum_version="1.7.0",
        minimum_build="17000",
        evidence=None,
    )
    authority = _official_graph(
        root / "candidate-1",
        web_manifest=web,
        android_manifest=android,
    )
    distribution = root / "origin"
    _deploy("web", authority, distribution)
    _deploy("app-release", authority, distribution)
    return distribution, web


def _android_candidate(
    root: Path,
    *,
    build: str,
    minimum_version: str,
    minimum_build: str,
    evidence: dict[str, Any] | None,
) -> Path:
    manifest_path = _android_package(root, build=build)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["minimumSupportedVersion"] = minimum_version
    manifest["minimumSupportedBuild"] = minimum_build
    if evidence is not None:
        manifest["minimumSupportedBuildIncreaseEvidence"] = evidence
    _write_json(manifest_path, manifest)
    return manifest_path


def _valid_evidence() -> dict[str, Any]:
    receipt = "sha256:" + ("e" * 64)
    return {
        "schema": "client-app.minimum-supported-build-increase-evidence",
        "platform": "android",
        "fromMinimumSupportedBuild": "17000",
        "toMinimumSupportedVersion": "1.8.0",
        "toMinimumSupportedBuild": "18000",
        "wouldBlock": {
            "observationStartedAt": "2026-07-12T00:00:00Z",
            "observationEndedAt": "2026-08-11T00:00:00Z",
            "oldVersionActiveInstallShareBasisPoints": 9,
            "receiptDigest": receipt,
        },
        "normalSupport": {
            "supportedSince": "2025-08-11T00:00:00Z",
            "evaluatedAt": "2026-08-11T00:00:00Z",
            "receiptDigest": receipt,
        },
        "channels": {
            channel: {
                "verified": True,
                "verifiedAt": "2026-08-11T00:00:00Z",
                "receiptDigest": receipt,
            }
            for channel in ("update", "recovery")
        },
        "securityException": None,
    }


def _evidence_with(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    evidence = copy.deepcopy(_valid_evidence())
    target: dict[str, Any] = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return evidence


if __name__ == "__main__":
    unittest.main()
