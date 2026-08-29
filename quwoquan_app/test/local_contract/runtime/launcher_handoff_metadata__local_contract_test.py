# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parents[3]
ROOT = APP_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

import build_launcher_handoff as launcher
from build_launcher_handoff import (
    effective_launch_manifest_digest,
)
from launcher_package_fixture import (
    build_test_handoff_fixture,
    shared_nonprod_launcher_authority,
)

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    LaunchManifestContractError,
    build_runtime_config_activation_request,
    load_launch_manifest_contract,
    runtime_config_activation_request_digest,
    runtime_config_package_digest,
    runtime_config_trust_envelope_digest,
    validate_handoff_against_metadata,
    validate_runtime_config_activation_receipt,
    validate_runtime_config_activation_request,
    validate_runtime_config_package,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import (
    TRUSTED_PUBLIC_KEYS_FILE_ENV,
)


class _HandoffFixture:
    def __init__(
        self,
        handoff: dict[str, object],
        runtime_config_trust_envelope: dict[str, object],
    ) -> None:
        self.handoff = handoff
        self.runtime_config_trust_envelope = runtime_config_trust_envelope

    def __getitem__(self, key: str) -> object:
        return self.handoff[key]

    def __setitem__(self, key: str, value: object) -> None:
        self.handoff[key] = value

    def __delitem__(self, key: str) -> None:
        del self.handoff[key]

    def __contains__(self, key: object) -> bool:
        return key in self.handoff


def _build_handoff(
    environment: str,
    target: str,
    *extra_arguments: str,
    launch_provenance: str = "canonical_launcher",
) -> _HandoffFixture:
    handoff, envelope = build_test_handoff_fixture(
        launcher,
        environment,
        target,
        launch_provenance=launch_provenance,
        extra_arguments=tuple(extra_arguments),
    )
    return _HandoffFixture(handoff, envelope)


def _envelope(handoff: _HandoffFixture) -> dict[str, object]:
    return handoff.runtime_config_trust_envelope


def _validate_handoff(
    handoff: _HandoffFixture,
    contract: dict[str, object] | None = None,
) -> list[str]:
    return validate_handoff_against_metadata(
        handoff.handoff,
        handoff.runtime_config_trust_envelope,
        contract,
    )


def _validate_package(
    package: dict[str, object],
    envelope: dict[str, object],
    *,
    contract: dict[str, object] | None = None,
    now: datetime | None = None,
) -> list[str]:
    return validate_runtime_config_package(
        package,
        envelope,
        contract,
        now=now,
    )


class LauncherHandoffMetadataContractTest(unittest.TestCase):
    def test_runtime_consumer_rejects_metadata_override(self) -> None:
        with self.assertRaisesRegex(
            LaunchManifestContractError,
            "runtime launch-manifest overrides are forbidden",
        ):
            load_launch_manifest_contract(
                {"content_binding_contract": {"content_binding_modes": ["bound"]}}
            )

    def test_metadata_loads_without_site_packages_for_xcode_builds(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-S",
                "-c",
                (
                    "import sys; sys.path.insert(0, '..'); "
                    "sys.modules['yaml'] = None; "
                    "from quwoquan_ops.cli.lib.app_launch_manifest_contract import "
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
        # 内容激活是运行时服务端事实，direct 构建不得把内容身份注入 handoff。
        self.assertNotIn("--content-release-id", ios)
        self.assertNotIn("CONTENT_BINDING_STATE", ios)
        self.assertNotIn("QWQ_CONTENT_RELEASE_ID", ios)

        android = (APP_DIR / "android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("--content-release-id", android)
        self.assertNotIn("CONTENT_BINDING_STATE", android)
        self.assertNotIn("QWQ_CONTENT_RELEASE_ID", android)
        self.assertNotIn("handoff[handoffKey]", android)

    def test_all_test_live_launchers_use_one_explicit_preflight_policy(self) -> None:
        launcher = (APP_DIR / "run.sh").read_text(encoding="utf-8")
        app_instance = (
            APP_DIR / "scripts/device/run_app_instance.sh"
        ).read_text(encoding="utf-8")
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
            '"runtime consumer lease is unavailable; test_live remains nonPromotable."',
            launcher,
        )
        self.assertIn("record_prelaunch_warning", launcher)
        self.assertIn('bash "$APP_DIR/run.sh"', app_instance)
        self.assertNotIn("app-debug-preflight", app_instance)
        self.assertNotIn("flutter run", app_instance)
    def test_each_metadata_target_builds_one_canonical_handoff(self) -> None:
        contract = load_launch_manifest_contract()
        for target, environment in contract["target_environment"].items():
            with self.subTest(target=target):
                handoff = _build_handoff(environment, target)
                self.assertEqual(handoff["target"], target)
                self.assertEqual(handoff["environment"], environment)
                self.assertEqual(
                    _validate_handoff(handoff, contract),
                    [],
                )
                self.assertEqual(
                    set(handoff.handoff),
                    set(
                        contract["schemas"]["app_launcher_handoff"][
                            "required_fields"
                        ]
                    ),
                )

    def test_nonprod_trust_envelope_is_profile_only_and_target_independent(self) -> None:
        with shared_nonprod_launcher_authority():
            handoffs = [
                _build_handoff(environment, f"{environment}-local")
                for environment in ("alpha", "beta", "gamma")
            ]
        envelopes = [_envelope(handoff) for handoff in handoffs]
        digests = [runtime_config_trust_envelope_digest(value) for value in envelopes]
        self.assertEqual(envelopes[0], envelopes[1])
        self.assertEqual(envelopes[1], envelopes[2])
        self.assertEqual(digests[0], digests[1])
        self.assertEqual(digests[1], digests[2])
        self.assertEqual(
            set(envelopes[0]),
            {
                "schema",
                "buildProfile",
                "signatureAlgorithm",
                "trustedPublicKeys",
            },
        )
        for forbidden in (
            "environment",
            "target",
            "endpoint",
            "package",
            "privateKey",
            "secret",
            "rollout",
            "channel",
            "content",
        ):
            self.assertNotIn(forbidden, envelopes[0])
        self.assertEqual(
            {handoff["runtimeConfigTrustEnvelopeDigest"] for handoff in handoffs},
            {digests[0]},
        )

    def test_runtime_package_schema_freezes_signed_external_configuration(self) -> None:
        contract = load_launch_manifest_contract()
        trust_schema = contract["schemas"]["runtime_config_trust_envelope"]
        self.assertFalse(trust_schema["additional_fields"])
        self.assertEqual(
            set(trust_schema["fields"]),
            {
                "schema",
                "buildProfile",
                "signatureAlgorithm",
                "trustedPublicKeys",
            },
        )
        runtime_schema = contract["schemas"]["runtime_config_package"]
        self.assertEqual(runtime_schema["schema_value"], "app-runtime-config-package")
        self.assertFalse(runtime_schema["additional_fields"])
        # schema 是唯一身份键；版本信封字段不得回到契约。
        self.assertNotIn("schemaVersion", runtime_schema["fields"])
        self.assertEqual(
            runtime_schema["fields"]["signatureAlgorithm"]["const"], "ed25519"
        )
        self.assertEqual(
            set(runtime_schema["fields"]["runtime"]["fields"]),
            set(contract["runtime_value_keys"]),
        )
        self.assertIn("trustedPublicKeys", runtime_schema["fields"])
        forbidden = {"contentReleaseId", "rolloutStage", "channelId", "secret"}
        self.assertTrue(
            forbidden.isdisjoint(runtime_schema["fields"]["runtime"]["fields"])
        )
        handoff_fields = contract["schemas"]["app_launcher_handoff"]["fields"]
        self.assertIn("runtimeConfigPackage", handoff_fields)
        self.assertIn("runtimeConfigPackageDigest", handoff_fields)
        self.assertIn("runtimeConfigTrustEnvelopeDigest", handoff_fields)
        self.assertNotIn("runtimeConfigTrustEnvelope", handoff_fields)
        self.assertNotIn("trustedPublicKeys", handoff_fields)
        self.assertNotIn("dartDefines", handoff_fields)
        self.assertNotIn("dartDefinesDigest", handoff_fields)

    def test_handoff_carries_package_without_endpoint_dart_defines(self) -> None:
        handoff = _build_handoff("alpha", "alpha-local")
        package = handoff["runtimeConfigPackage"]
        self.assertIsInstance(package, dict)
        self.assertEqual(package["buildProfile"], "nonprod")
        self.assertEqual(package["environment"], "alpha")
        self.assertEqual(package["target"], "alpha-local")
        self.assertEqual(package["launchPolicy"], "test_live")
        self.assertIn("trustedPublicKeys", package)
        self.assertIn("runtimeConfigTrustEnvelopeDigest", handoff)
        self.assertNotIn("runtimeConfigTrustEnvelope", handoff)
        self.assertNotIn("trustedPublicKeys", handoff)
        self.assertNotIn("dartDefines", handoff)
        self.assertNotIn("dartDefinesDigest", handoff)
        self.assertEqual(
            handoff["runtimeConfigPackageDigest"],
            runtime_config_package_digest(package),
        )
        envelope = _envelope(handoff)
        self.assertEqual(
            handoff["runtimeConfigTrustEnvelopeDigest"],
            runtime_config_trust_envelope_digest(envelope),
        )

    def test_cli_materializes_independent_profile_trust_atomically(self) -> None:
        source = (APP_DIR / "scripts/device/build_launcher_handoff.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("--runtime-config-trust-output", source)
        self.assertIn("materialize_runtime_config_trust_envelope", source)
        self.assertIn("os.chmod(temporary, 0o600)", source)
        self.assertIn("temporary.replace(output_path)", source)

        with tempfile.TemporaryDirectory(prefix="qwq-runtime-trust-") as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            output = root / "runtime-config-trust.json"
            handoff, envelope = build_test_handoff_fixture(
                launcher,
                "alpha",
                "alpha-local",
                launch_provenance="canonical_launcher",
                extra_arguments=("--runtime-config-trust-output", str(output)),
            )
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                launcher.json.dumps(
                    envelope,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                handoff["runtimeConfigTrustEnvelopeDigest"],
                runtime_config_trust_envelope_digest(envelope),
            )
            self.assertNotIn("runtimeConfigTrustEnvelope", handoff)

    def test_canonical_launcher_consumes_external_trust_without_runtime_defines(
        self,
    ) -> None:
        source = (APP_DIR / "run.sh").read_text(encoding="utf-8")
        self.assertIn("--runtime-config-trust-output", source)
        self.assertIn("QWQ_APP_RUNTIME_CONFIG_TRUST_PATH", source)
        self.assertIn("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT", source)
        self.assertIn("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", source)
        self.assertNotIn("verify_flutter_run_defines.py", source)
        self.assertNotIn("VERIFY_HANDOFF_CMD", source)
        self.assertNotIn("DEFINES_JSON", source)
        self.assertNotIn("DART_DEFINES_DIGEST", source)
        self.assertNotIn("RUNTIME_CONFIG_DIGEST", source)
        self.assertNotIn("DART_DEFINES=(", source)
        self.assertNotIn('"${DART_DEFINES[@]}"', source)
        self.assertNotIn("--dart-define=APP_RUNTIME_ENV", source)
        self.assertNotIn("--dart-define=CLOUD_GATEWAY_BASE_URL", source)
        self.assertIn('scripts/device/run_app_instance.py"', source)
        self.assertNotIn('"$QWQ_REAL_FLUTTER" run', source)
        self.assertIn("workspace literal `flutter run`", source)

    def test_android_debug_mounts_only_external_profile_trust_asset(self) -> None:
        # assets 准入校验落在共享脚本，生产 App 与 Patrol UAT test host 两个 Gradle 工程
        # apply 同一份；主脚本只负责把校验结果挂成 assets srcDir。
        shared_validation = (
            APP_DIR / "android/gradle/runtime-config-assets.gradle.kts"
        ).read_text(encoding="utf-8")
        for host_gradle in (
            APP_DIR / "android/app/build.gradle.kts",
            APP_DIR / "test_host/patrol/android/app/build.gradle.kts",
        ):
            with self.subTest(gradle=host_gradle.name):
                gradle = host_gradle.read_text(encoding="utf-8")
                self.assertIn("runtime-config-assets.gradle.kts", gradle)
                self.assertIn(
                    'sourceSets.getByName("main").assets.srcDir',
                    gradle,
                )
        self.assertIn("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT", shared_validation)
        self.assertIn("runtime-config-trust.json", shared_validation)
        self.assertIn("runtime-config-package.json", shared_validation)
        self.assertIn("must stay outside the source tree", shared_validation)
        self.assertIn(
            "target runtime package must not enter Android assets",
            shared_validation,
        )

    def test_ios_production_and_patrol_projects_are_cocoapods_only(self) -> None:
        forbidden_spm_tokens = (
            "FlutterGeneratedPluginSwiftPackage",
            "XCLocalSwiftPackageReference",
            "XCSwiftPackageProductDependency",
        )
        for project in (
            APP_DIR / "ios/Runner.xcodeproj/project.pbxproj",
            APP_DIR / "test_host/patrol/ios/Runner.xcodeproj/project.pbxproj",
        ):
            with self.subTest(project=project):
                source = project.read_text(encoding="utf-8")
                for token in forbidden_spm_tokens:
                    self.assertNotIn(token, source)

    def test_activation_request_and_receipt_bind_manifest_package_trust_and_cas(
        self,
    ) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff(
            "alpha",
            "alpha-local",
            launch_provenance="canonical_launcher",
        )
        previous_active_digest = "sha256:" + "0" * 64
        request = build_runtime_config_activation_request(
            handoff.handoff,
            expected_active_digest=previous_active_digest,
        )
        self.assertEqual(validate_runtime_config_activation_request(request), [])
        self.assertEqual(
            set(request),
            set(
                contract["schemas"]["runtime_config_activation_request"][
                    "required_fields"
                ]
            ),
        )
        self.assertEqual(request["package"], handoff["runtimeConfigPackage"])
        self.assertEqual(
            request["packageDigest"], handoff["runtimeConfigPackageDigest"]
        )
        self.assertEqual(
            request["trustEnvelopeDigest"],
            handoff["runtimeConfigTrustEnvelopeDigest"],
        )
        self.assertEqual(
            request["effectiveLaunchManifest"],
            handoff["effectiveLaunchManifest"],
        )
        self.assertEqual(
            request["effectiveLaunchManifestDigest"],
            handoff["effectiveLaunchManifestDigest"],
        )
        self.assertEqual(request["expectedActiveDigest"], previous_active_digest)
        request_digest = runtime_config_activation_request_digest(request)
        self.assertRegex(request_digest, r"^sha256:[0-9a-f]{64}$")

        receipt = {
            "schema": "app-runtime-config-activation-receipt",
            "status": "activated",
            "requestDigest": request_digest,
            "environment": "alpha",
            "buildProfile": "nonprod",
            "target": "alpha-local",
            "launchProvenance": handoff["launchProvenance"],
            "runtimeConfigSupplyMode": handoff["runtimeConfigSupplyMode"],
            "packageDigest": handoff["runtimeConfigPackageDigest"],
            "trustEnvelopeDigest": handoff["runtimeConfigTrustEnvelopeDigest"],
            "effectiveLaunchManifestDigest": handoff[
                "effectiveLaunchManifestDigest"
            ],
            "previousActiveDigest": previous_active_digest,
            "activePackageDigest": handoff["runtimeConfigPackageDigest"],
            "errorCode": "",
            "validationIssues": [],
        }
        self.assertEqual(
            validate_runtime_config_activation_receipt(receipt, request), []
        )
        failed_receipt = {
            **receipt,
            "status": "failed",
            "activePackageDigest": previous_active_digest,
            "errorCode": "runtime_config_active_digest_conflict",
            "validationIssues": ["runtime_config_active_digest_conflict"],
        }
        self.assertEqual(
            validate_runtime_config_activation_receipt(failed_receipt, request), []
        )
        tampered = deepcopy(receipt)
        tampered["effectiveLaunchManifestDigest"] = "sha256:" + "f" * 64
        self.assertIn(
            "activation receipt effectiveLaunchManifestDigest does not match request",
            validate_runtime_config_activation_receipt(tampered, request),
        )

    def test_native_activation_precedes_flutter_engine_on_both_platforms(self) -> None:
        android_gate = (
            APP_DIR
            / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupGateActivity.java"
        ).read_text(encoding="utf-8")
        # runtime config 供给面落在 runtimeConfigShared 源集：生产 App 与 Patrol UAT
        # test host 两个 Gradle 工程编译同一份，宿主读到的取值因此与生产同源。
        android_coordinator = (
            APP_DIR
            / "android/app/src/runtimeConfigShared/java/com/quwoquan/quwoquan_app"
            / "RuntimeConfigActivationCoordinator.java"
        ).read_text(encoding="utf-8")
        ios = (APP_DIR / "ios/Runner/AppDelegate.swift").read_text(encoding="utf-8")
        # iOS 侧的 runtime config 供给面同样共享给 test host 工程，回执落盘在供给面而非
        # AppDelegate。
        ios_runtime_config_supply = (
            APP_DIR / "ios/Runner/NativeRuntimeConfigSupply.swift"
        ).read_text(encoding="utf-8")
        activation = (
            APP_DIR
            / "scripts/device/canonical_app_instance/activation.py"
        ).read_text(encoding="utf-8")
        runner = (APP_DIR / "scripts/device/run_app_instance.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("consumePendingRequest", android_gate)
        self.assertLess(
            android_gate.index("consumePendingRequest"),
            android_gate.index("showNativeLaunchFrameThenStartFlutter"),
        )
        self.assertIn("effectiveLaunchManifestDigest", android_coordinator)
        self.assertIn("expectedActiveDigest", android_coordinator)
        self.assertIn("runtime-config-activation-receipt.json", android_coordinator)
        self.assertIn("consumePendingActivationRequest", ios)
        self.assertLess(
            ios.index("consumePendingActivationRequest"),
            ios.index("return super.application("),
        )
        self.assertIn(
            "runtime-config-activation-receipt.json",
            ios_runtime_config_supply,
        )
        self.assertIn('self._emit_phase("configuring")', activation)
        self.assertIn('self._emit_phase("configured")', activation)
        self.assertIn("flutter attach", runner)
        self.assertNotIn("flutter run", runner)

    def test_runtime_package_rejects_profile_target_policy_and_source_drift(self) -> None:
        handoff = _build_handoff("alpha", "alpha-local")
        package = handoff["runtimeConfigPackage"]
        envelope = _envelope(handoff)
        cases = {
            "build profile": ("buildProfile", "prod"),
            "target/environment": ("target", "beta-local"),
            "launch policy": (
                "launchPolicy",
                launcher.PROD_RELEASE_LAUNCH_POLICY,
            ),
            "source tree": ("sourceTreeDigest", "sha256:" + "f" * 64),
        }
        for label, (field, value) in cases.items():
            with self.subTest(label=label):
                tampered = deepcopy(package)
                tampered[field] = value
                self.assertNotEqual(
                    _validate_package(tampered, envelope),
                    [],
                )

    def test_source_capsule_identity_must_be_canonical_and_verified(self) -> None:
        script = APP_DIR / "scripts/env/print_app_env_dart_defines.py"
        with tempfile.TemporaryDirectory() as temporary_directory:
            capsule = Path(temporary_directory) / "manifest.json"
            capsule.write_text(
                (
                    '{"schema":"stackctl-package-input-capsule.v1","sourceRevision":"'
                    + "a" * 40
                    + '","deploymentInputDigest":"sha256:'
                    + "b" * 64
                    + '"}'
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--env",
                    "alpha",
                    "--target",
                    "alpha-local",
                    "--format",
                    "json",
                    "--source-capsule-manifest",
                    str(capsule),
                ],
                cwd=APP_DIR,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package input capsule", result.stderr + result.stdout)

    def test_runtime_package_requires_explicit_matching_trust_envelope(self) -> None:
        handoff = _build_handoff("alpha", "alpha-local")
        package = dict(handoff["runtimeConfigPackage"])
        envelope = _envelope(handoff)
        self.assertIn(
            "runtimeConfigTrustEnvelope is required",
            validate_runtime_config_package(package, None),  # type: ignore[arg-type]
        )
        wrong_profile = deepcopy(envelope)
        wrong_profile["buildProfile"] = "prod"
        self.assertIn(
            "runtimeConfigPackage buildProfile disagrees with runtimeConfigTrustEnvelope",
            validate_runtime_config_package(package, wrong_profile),
        )
        wrong_keyring = deepcopy(envelope)
        wrong_keyring["trustedPublicKeys"] = {
            next(iter(package["trustedPublicKeys"])): (
                "eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg="
            )
        }
        self.assertIn(
            "runtimeConfigPackage trustedPublicKeys disagrees with runtimeConfigTrustEnvelope",
            validate_runtime_config_package(package, wrong_keyring),
        )

    def test_launcher_trust_root_rejects_repository_paths_and_unsafe_modes(self) -> None:
        build_profile = "prod"
        with mock.patch.dict(
            os.environ,
            {TRUSTED_PUBLIC_KEYS_FILE_ENV: ""},
        ), self.assertRaisesRegex(ValueError, "Prod.*required"):
            launcher._runtime_config_trust_envelope(build_profile)
        repository_keyring = APP_DIR / "repository-trusted-keyring.json"
        with mock.patch.dict(
            os.environ,
            {TRUSTED_PUBLIC_KEYS_FILE_ENV: str(repository_keyring)},
        ), self.assertRaisesRegex(ValueError, "outside repository"):
            launcher._runtime_config_trust_envelope(build_profile)

        with tempfile.TemporaryDirectory(prefix="qwq-runtime-trust-") as temporary:
            external_keyring = Path(temporary) / "trusted-keyring.json"
            external_keyring.write_text("{}", encoding="utf-8")
            external_keyring.chmod(0o666)
            with mock.patch.dict(
                os.environ,
                {TRUSTED_PUBLIC_KEYS_FILE_ENV: str(external_keyring)},
            ), self.assertRaisesRegex(ValueError, "permissions are unsafe"):
                launcher._runtime_config_trust_envelope(build_profile)

    def test_explicit_source_identity_must_match_audited_git(self) -> None:
        script = APP_DIR / "scripts/env/print_app_env_dart_defines.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--env",
                "alpha",
                "--target",
                "alpha-local",
                "--format",
                "json",
                "--source-git-sha",
                "c" * 40,
                "--source-tree-digest",
                "sha256:" + "d" * 64,
            ],
            cwd=APP_DIR,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("disagrees with audited Git identity", result.stderr)

    def test_runtime_package_rejects_tampering_expiry_and_future_issue(self) -> None:
        handoff = _build_handoff("beta", "beta-local")
        package = handoff["runtimeConfigPackage"]
        envelope = _envelope(handoff)
        now = datetime.now(timezone.utc)

        tampered = deepcopy(package)
        tampered["runtime"]["gatewayBaseUrl"] = "https://tampered.example.test"
        self.assertTrue(
            any(
                "payloadDigest" in issue or "signature" in issue
                for issue in _validate_package(tampered, envelope, now=now)
            )
        )

        expired = deepcopy(package)
        expired["expiresAt"] = (now - timedelta(seconds=1)).isoformat().replace(
            "+00:00", "Z"
        )
        self.assertTrue(
            any(
                "expired" in issue
                for issue in _validate_package(expired, envelope, now=now)
            )
        )

        future = deepcopy(package)
        future["issuedAt"] = (now + timedelta(minutes=6)).isoformat().replace(
            "+00:00", "Z"
        )
        self.assertTrue(
            any(
                "future" in issue
                for issue in _validate_package(future, envelope, now=now)
            )
        )

        signature = deepcopy(package)
        signature["signature"] = "A" + str(signature["signature"])[1:]
        self.assertTrue(
            any(
                "signature" in issue
                for issue in _validate_package(signature, envelope, now=now)
            )
        )

    def test_runtime_package_rejects_undeclared_or_non_string_runtime_values(self) -> None:
        handoff = _build_handoff("gamma", "gamma-local")
        package = handoff["runtimeConfigPackage"]
        envelope = _envelope(handoff)
        undeclared = deepcopy(package)
        undeclared["runtime"]["contentReleaseId"] = "release-forbidden"
        self.assertIn(
            "runtimeConfigPackage.runtime.contentReleaseId is not declared by metadata",
            _validate_package(undeclared, envelope),
        )
        non_string = deepcopy(package)
        non_string["runtime"]["gatewayBaseUrl"] = {"secret": "forbidden"}
        self.assertIn(
            "runtimeConfigPackage.runtime.gatewayBaseUrl must be string",
            _validate_package(non_string, envelope),
        )

    def test_compatibility_command_blocks_legacy_dart_define_formats(self) -> None:
        script = APP_DIR / "scripts/env/print_app_env_dart_defines.py"
        for output_format in ("args", "shell"):
            with self.subTest(output_format=output_format):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--env",
                        "alpha",
                        "--target",
                        "alpha-local",
                        "--format",
                        output_format,
                    ],
                    cwd=APP_DIR,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("GATE_BLOCK", result.stderr + result.stdout)
                self.assertNotIn("--dart-define", result.stdout)
                self.assertNotIn("APP_RUNTIME_ENV", result.stdout)
                self.assertNotIn("CLOUD_GATEWAY_BASE_URL", result.stdout)

    def test_launch_policies_never_carry_content_identity(self) -> None:
        test_live = _build_handoff(
            "alpha",
            "alpha-local",
            launch_provenance="workspace_flutter_run",
        )
        self.assertEqual(test_live["launchPolicy"], "test_live")
        self.assertNotIn("contentBindingState", test_live)
        self.assertNotIn("contentReleaseId", test_live)
        self.assertEqual(_validate_handoff(test_live), [])

        prod = _build_handoff(
            "prod",
            "prod-hosted",
            launch_provenance="canonical_launcher",
        )
        self.assertEqual(
            prod["launchPolicy"], launcher.PROD_RELEASE_LAUNCH_POLICY
        )
        self.assertNotIn("contentBindingState", prod)
        self.assertNotIn("contentReleaseId", prod)
        self.assertEqual(_validate_handoff(prod), [])

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
                launch_provenance="canonical_launcher",
            )

    def test_validator_rejects_reintroduced_content_fields(self) -> None:
        handoff = _build_handoff("alpha", "alpha-local")
        handoff["contentBindingState"] = "bound"

        self.assertIn(
            "handoff.contentBindingState is not declared by metadata",
            _validate_handoff(handoff),
        )

    def test_metadata_is_the_only_target_environment_authority(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("alpha", "alpha-local")
        changed_contract = deepcopy(contract)
        changed_contract["target_environment"]["alpha-local"] = "beta"

        self.assertIn(
            "effective launch target/environment mapping is invalid",
            _validate_handoff(handoff, changed_contract),
        )

    def test_top_level_and_effective_identity_must_match(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        handoff["buildProfile"] = "nonprod"

        self.assertIn(
            "handoff.buildProfile disagrees with "
            "effectiveLaunchManifest.buildProfile",
            _validate_handoff(handoff, contract),
        )

    def test_required_and_additional_fields_fail_closed(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        del handoff["runtimeConfigPackageDigest"]
        handoff["retiredLaunchIdentity"] = "forbidden"

        issues = _validate_handoff(handoff, contract)
        self.assertIn("handoff.runtimeConfigPackageDigest is required", issues)
        self.assertIn(
            "handoff.retiredLaunchIdentity is not declared by metadata",
            issues,
        )

    def test_effective_digest_uses_metadata_canonical_json(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        effective = handoff["effectiveLaunchManifest"]
        self.assertIsInstance(effective, dict)
        effective["launchProvenance"] = "tampered"

        self.assertIn(
            "effectiveLaunchManifestDigest does not match canonical metadata",
            _validate_handoff(handoff, contract),
        )
        handoff["effectiveLaunchManifestDigest"] = (
            effective_launch_manifest_digest(effective)
        )
        self.assertNotIn(
            "effectiveLaunchManifestDigest does not match canonical metadata",
            _validate_handoff(handoff, contract),
        )

    def test_runtime_endpoint_tampering_fails_without_changing_handoff_digest(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        package = handoff["runtimeConfigPackage"]
        self.assertIsInstance(package, dict)
        package["runtime"]["gatewayBaseUrl"] = (
            "https://user:secret@quwoquan.com/path?token=secret"
        )

        issues = _validate_handoff(handoff, contract)
        self.assertTrue(
            any("payloadDigest" in issue or "signature" in issue for issue in issues)
        )
        self.assertIn(
            "runtimeConfigPackageDigest does not match canonical metadata",
            issues,
        )

    def test_app_download_url_allows_path_but_rejects_tampered_query(self) -> None:
        contract = load_launch_manifest_contract()
        handoff = _build_handoff("prod", "prod-hosted")
        package = handoff["runtimeConfigPackage"]
        self.assertIsInstance(package, dict)
        self.assertIn("/download", package["runtime"]["appDownloadBaseUrl"])
        package["runtime"]["appDownloadBaseUrl"] = (
            "https://cdn.quwoquan.com/download?token=secret"
        )

        issues = _validate_handoff(handoff, contract)
        self.assertTrue(any("payloadDigest" in issue for issue in issues))
        self.assertTrue(any("signature" in issue for issue in issues))

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
        self.assertEqual(_validate_handoff(handoff), [])

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
