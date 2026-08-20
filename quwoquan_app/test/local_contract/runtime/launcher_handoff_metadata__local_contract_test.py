# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

import build_launcher_handoff as launcher
from build_launcher_handoff import (
    effective_launch_manifest_digest,
)
from launcher_package_fixture import build_test_handoff
from launch_manifest_metadata import (
    LAUNCH_MANIFEST_METADATA,
    LaunchManifestContractError,
    load_launch_manifest_contract,
    validate_handoff_against_metadata,
)


def _build_handoff(
    environment: str,
    target: str,
    *extra_arguments: str,
    launch_mode: str = "metadata_contract_test",
) -> dict[str, object]:
    return build_test_handoff(
        launcher,
        environment,
        target,
        launch_mode=launch_mode,
        extra_arguments=tuple(extra_arguments),
    )


class LauncherHandoffMetadataContractTest(unittest.TestCase):
    def test_metadata_rejects_reintroduced_content_binding_contract(self) -> None:
        metadata = LAUNCH_MANIFEST_METADATA.read_text(encoding="utf-8") + (
            "\ncontent_binding_contract:\n"
            "  content_binding_modes: [unbound, run_bound]\n"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "app_launch_manifest.yaml"
            path.write_text(metadata, encoding="utf-8")
            with self.assertRaisesRegex(
                LaunchManifestContractError,
                "must not declare content binding",
            ):
                load_launch_manifest_contract(path)

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

    def test_direct_platform_builds_preflight_without_content_binding(
        self,
    ) -> None:
        ios = (APP_DIR / "scripts/ios/build_prepare_dart_defines.sh").read_text(
            encoding="utf-8"
        )
        ios_direct = ios[ios.index('if [[ -z "$LAUNCH_MODE"') : ios.index("fi\n\nif [[ -z \"$ENV_NAME\"")]
        self.assertLess(
            ios_direct.index("app-debug-preflight"),
            ios_direct.index("build_launcher_handoff.py"),
        )
        self.assertIn("--launch-policy test_live", ios_direct)
        self.assertIn(
            'app-debug-preflight --target "$DIRECT_TARGET" --runtime-mode test_live',
            ios_direct,
        )
        # 内容激活是运行时服务端事实，direct 构建不得把内容身份注入 handoff。
        self.assertNotIn("--content-release-id", ios)
        self.assertNotIn("CONTENT_BINDING_STATE", ios)
        self.assertNotIn("QWQ_CONTENT_RELEASE_ID", ios)

        android = (APP_DIR / "android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        android_direct = android[
            android.index("fun buildCanonicalDirectDebugHandoff") : android.index(
                "fun handoffString"
            )
        ]
        self.assertLess(
            android_direct.index('"app-debug-preflight"'),
            android_direct.index('"--launch-policy"'),
        )
        self.assertIn('"--runtime-mode"', android_direct)
        self.assertIn('"test_live"', android_direct)
        self.assertNotIn("--content-release-id", android)
        self.assertNotIn("CONTENT_BINDING_STATE", android)
        self.assertNotIn("QWQ_CONTENT_RELEASE_ID", android)
        self.assertNotIn("handoff[handoffKey]", android_direct)

    def test_all_test_live_launchers_use_one_explicit_preflight_policy(self) -> None:
        launcher = (APP_DIR / "run.sh").read_text(encoding="utf-8")
        app_instance = (
            APP_DIR / "scripts/device/run_app_instance.sh"
        ).read_text(encoding="utf-8")
        ios = (
            APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
        ).read_text(encoding="utf-8")
        android = (APP_DIR / "android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"',
            launcher,
        )
        self.assertIn('--target "$QWQ_LAUNCH_TARGET" --runtime-mode test_live', launcher)
        # test_live 的 preflight、启动策略与租约判据收敛给 run.sh 这一个 owner；
        # run_app_instance.sh 只做入参校验与转发，不再复制一份 preflight。判据因此
        # 钉在 owner 身上，再要求 adapter 不得自建第二次 preflight 或第二条 Flutter
        # 命令——「一套策略」被破坏只会以这两种形式出现。
        self.assertIn('payload.get("status") not in {"passed", "warning"}', launcher)
        self.assertIn("export QWQ_APP_LAUNCH_POLICY=test_live", launcher)
        self.assertIn("--launch-policy test_live", launcher)
        self.assertIn(
            "GATE_BLOCK: content-live requires a runtime consumer lease.",
            launcher,
        )
        self.assertIn('bash "$APP_DIR/run.sh"', app_instance)
        self.assertNotIn("app-debug-preflight", app_instance)
        self.assertNotIn("flutter run", app_instance)
        self.assertIn(
            'app-debug-preflight --target "$DIRECT_TARGET" --runtime-mode test_live',
            ios,
        )
        self.assertIn('"--runtime-mode"', android)
        self.assertIn('"test_live"', android)

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

    def test_launch_policies_never_carry_content_identity(self) -> None:
        test_live = _build_handoff(
            "alpha",
            "alpha-local",
            launch_mode="direct_flutter_run",
        )
        self.assertEqual(test_live["launchPolicy"], "test_live")
        self.assertNotIn("contentBindingState", test_live)
        self.assertNotIn("contentReleaseId", test_live)
        self.assertEqual(validate_handoff_against_metadata(test_live), [])

        prod = _build_handoff(
            "prod",
            "prod-hosted",
            launch_mode="canonical_launcher",
        )
        self.assertEqual(
            prod["launchPolicy"], launcher.PROD_RELEASE_LAUNCH_POLICY
        )
        self.assertNotIn("contentBindingState", prod)
        self.assertNotIn("contentReleaseId", prod)
        self.assertEqual(validate_handoff_against_metadata(prod), [])

    def test_builder_rejects_retired_content_binding_arguments(self) -> None:
        digest = "sha256:" + "a" * 64
        with self.assertRaises(SystemExit):
            _build_handoff(
                "alpha",
                "alpha-local",
                "--content-release-id",
                "release-alpha-run",
                "--content-manifest-digest",
                digest,
                "--content-readiness-receipt-digest",
                digest,
                launch_mode="canonical_launcher",
            )

    def test_validator_rejects_reintroduced_content_fields(self) -> None:
        handoff = _build_handoff("alpha", "alpha-local")
        handoff["contentBindingState"] = "bound"

        self.assertIn(
            "handoff.contentBindingState is not declared by metadata",
            validate_handoff_against_metadata(handoff),
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
        handoff["retiredLaunchIdentity"] = "forbidden"

        issues = validate_handoff_against_metadata(handoff, contract)
        self.assertIn("handoff.publicWebBaseUrl is required", issues)
        self.assertIn(
            "handoff.retiredLaunchIdentity is not declared by metadata",
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
        with self.assertRaisesRegex(
            ValueError,
            "transport evidence must be empty when transport.required=false",
        ):
            _build_handoff(
                "alpha",
                "alpha-local",
                "--reverse-expected-ports",
                "7443",
            )


if __name__ == "__main__":
    unittest.main()
