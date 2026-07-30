# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))

from build_launcher_handoff import (
    effective_launch_manifest_digest,
)
from launch_manifest_metadata import (
    LAUNCH_MANIFEST_METADATA,
    load_launch_manifest_contract,
    validate_handoff_against_metadata,
)


HANDOFF_BUILDER = APP_DIR / "scripts/device/build_launcher_handoff.py"


def _build_handoff(
    environment: str,
    target: str,
    *extra_arguments: str,
) -> dict[str, object]:
    result = subprocess.run(
        [
            "python3",
            str(HANDOFF_BUILDER),
            "--env",
            environment,
            "--target",
            target,
            "--launch-mode",
            "metadata_contract_test",
            *extra_arguments,
        ],
        cwd=APP_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class LauncherHandoffMetadataContractTest(unittest.TestCase):
    def test_metadata_loads_without_site_packages_for_xcode_builds(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-S",
                "-c",
                (
                    "import sys; "
                    "sys.path.insert(0, 'scripts/device'); "
                    "from launch_manifest_metadata import "
                    "load_launch_manifest_contract; "
                    "print(load_launch_manifest_contract()['schema_id'])"
                ),
            ],
            cwd=APP_DIR,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "app_launch_manifest")

    def test_each_metadata_target_builds_one_canonical_handoff(self) -> None:
        contract = load_launch_manifest_contract()
        for target, environment in contract["target_environment"].items():
            with self.subTest(target=target):
                handoff = _build_handoff(environment, target)
                self.assertEqual(handoff["target"], target)
                self.assertEqual(handoff["environment"], environment)
                self.assertEqual(
                    validate_handoff_against_metadata(handoff, contract),
                    [],
                )
                self.assertEqual(
                    set(handoff),
                    set(
                        contract["schemas"]["app_launcher_handoff"][
                            "required_fields"
                        ]
                    ),
                )

    def test_metadata_is_the_only_target_environment_authority(self) -> None:
        contract = load_launch_manifest_contract(LAUNCH_MANIFEST_METADATA)
        handoff = _build_handoff("alpha", "alpha-local")
        changed_contract = deepcopy(contract)
        changed_contract["target_environment"]["alpha-local"] = "beta"

        self.assertIn(
            "effective launch target/environment mapping is invalid",
            validate_handoff_against_metadata(handoff, changed_contract),
        )

    def test_top_level_and_effective_identity_must_match(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        handoff["publicWebBaseUrl"] = "https://different.quwoquan.com"

        self.assertIn(
            "handoff.publicWebBaseUrl disagrees with "
            "effectiveLaunchManifest.publicWebBaseUrl",
            validate_handoff_against_metadata(handoff, contract),
        )

    def test_required_and_additional_fields_fail_closed(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        del handoff["publicWebBaseUrl"]
        handoff["legacyLaunchIdentity"] = "forbidden"

        issues = validate_handoff_against_metadata(handoff, contract)
        self.assertIn("handoff.publicWebBaseUrl is required", issues)
        self.assertIn(
            "handoff.legacyLaunchIdentity is not declared by metadata",
            issues,
        )

    def test_effective_digest_uses_metadata_canonical_json(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        effective = handoff["effectiveLaunchManifest"]
        self.assertIsInstance(effective, dict)
        effective["launchMode"] = "tampered"

        self.assertIn(
            "effectiveLaunchManifestDigest does not match canonical metadata",
            validate_handoff_against_metadata(handoff, contract),
        )
        handoff["effectiveLaunchManifestDigest"] = (
            effective_launch_manifest_digest(effective)
        )
        self.assertNotIn(
            "effectiveLaunchManifestDigest does not match canonical metadata",
            validate_handoff_against_metadata(handoff, contract),
        )

    def test_urls_fail_closed_without_changing_the_digest(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        effective = handoff["effectiveLaunchManifest"]
        self.assertIsInstance(effective, dict)
        invalid_url = "https://user:secret@quwoquan.com/path?token=secret"
        effective["recoveryBaseUrl"] = invalid_url
        handoff["recoveryBaseUrl"] = invalid_url
        handoff["effectiveLaunchManifestDigest"] = (
            effective_launch_manifest_digest(effective)
        )

        issues = validate_handoff_against_metadata(handoff, contract)
        self.assertIn(
            "handoff.effectiveLaunchManifest.recoveryBaseUrl must satisfy "
            "https_origin",
            issues,
        )

    def test_app_download_url_allows_path_but_rejects_query(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        effective = handoff["effectiveLaunchManifest"]
        self.assertIsInstance(effective, dict)
        self.assertEqual(validate_handoff_against_metadata(handoff, contract), [])
        invalid_url = "https://cdn.quwoquan.com/download?token=secret"
        effective["appDownloadBaseUrl"] = invalid_url
        handoff["appDownloadBaseUrl"] = invalid_url
        handoff["effectiveLaunchManifestDigest"] = (
            effective_launch_manifest_digest(effective)
        )

        self.assertIn(
            "handoff.effectiveLaunchManifest.appDownloadBaseUrl must satisfy "
            "https_url_no_query_fragment_credentials",
            validate_handoff_against_metadata(handoff, contract),
        )

    def test_local_transport_receipt_is_complete_and_canonical(self) -> None:
        digest = "sha256:" + "a" * 64
        handoff = _build_handoff(
            "beta",
            "beta-local",
            "--transport-required",
            "--reverse-expected-ports",
            "7444,7443",
            "--reverse-actual-ports",
            "7443,7444",
            "--reverse-receipt-digest",
            digest,
            "--consumer-lease-id",
            digest,
        )
        self.assertEqual(handoff["transport"]["reverseExpectedPorts"], "7443,7444")
        self.assertEqual(validate_handoff_against_metadata(handoff), [])

    def test_transport_values_without_required_flag_are_gate_blocked(self) -> None:
        result = subprocess.run(
            [
                "python3",
                str(HANDOFF_BUILDER),
                "--env",
                "alpha",
                "--target",
                "alpha-local",
                "--launch-mode",
                "metadata_contract_test",
                "--reverse-expected-ports",
                "7443",
            ],
            cwd=APP_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE_BLOCK", result.stdout)
        self.assertIn(
            "transport evidence must be empty when transport.required=false",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
