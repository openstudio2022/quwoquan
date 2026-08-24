# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
SCRIPT = APP_DIR / "scripts/ios/build_prepare_dart_defines.sh"
APP_DELEGATE = APP_DIR / "ios/Runner/AppDelegate.swift"
STACKCTL_PYTHON_RESOLVER = APP_DIR / "scripts/ios/build_resolve_stackctl_python.sh"


def _encoded_define(key: str, value: str) -> str:
    return base64.b64encode(f"{key}={value}".encode()).decode()


def _trust_envelope(root: Path, *, build_profile: str = "nonprod") -> Path:
    trust = root / "runtime-config-trust.json"
    trust.write_text(
        json.dumps(
            {
                "schema": "app-runtime-config-trust",
                "buildProfile": build_profile,
                "signatureAlgorithm": "ed25519",
                "trustedPublicKeys": {
                    "test-key": base64.b64encode(bytes(range(32))).decode("ascii")
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return trust


class IosRuntimeConfigBuildPreparationContractTest(unittest.TestCase):
    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["QWQ_IOS_STACKCTL_PYTHON"] = sys.executable
        environment["CONFIGURATION"] = "Debug-nonprod"
        environment["QWQ_APP_BUILD_PROFILE"] = "nonprod"
        environment["DART_DEFINES"] = _encoded_define("FLUTTER_VERSION", "test")
        return environment

    def _materialization_environment(
        self,
        root: Path,
        trust: Path,
    ) -> dict[str, str]:
        environment = self._environment()
        environment.update(
            {
                "QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH": str(trust),
                "TARGET_BUILD_DIR": str(root / "build"),
                "UNLOCALIZED_RESOURCES_FOLDER_PATH": "Runner.app",
            }
        )
        return environment

    def test_script_uses_build_profile_and_has_no_runtime_package_dual_read(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for configuration in (
            "Debug-nonprod",
            "Profile-nonprod",
            "Release-nonprod",
            "Release-prod",
        ):
            self.assertIn(configuration, source)
        self.assertNotIn("QWQ_LAUNCH_HANDOFF_JSON", source)
        self.assertIn("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", source)
        self.assertNotIn("QWQ_APP_RUNTIME_CONFIG_TRUST_PATH", source)
        for retired in (
            "Debug-alpha",
            "Debug-beta",
            "Debug-gamma",
            "QWQNativeRuntime.plist",
            "runtimeDefines",
            "print_app_env_dart_defines.py",
            "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON or",
        ):
            self.assertNotIn(retired, source)
        self.assertIn("Debug-prod|Profile-prod", source)
        self.assertIn("target runtime package must be activated post-install", source)

    def test_generated_build_profile_identity_is_required(self) -> None:
        environment = self._environment()
        environment.pop("QWQ_APP_BUILD_PROFILE")
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("generated build-profile identity is missing", result.stderr)

    def test_compile_defines_preserve_non_runtime_values_and_add_no_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._materialization_environment(root, _trust_envelope(root))
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertIn("export FLUTTER_TARGET=lib/main_prod.dart", result.stdout)
        self.assertIn(environment["DART_DEFINES"], result.stdout)
        self.assertIn("compileRuntimeDefines=0", result.stderr)
        self.assertIn("embeddedRuntimePackage=0", result.stderr)
        for forbidden in (
            "api.alpha.quwoquan.com",
            "APP_RUNTIME_ENV=",
            "APP_LAUNCH_POLICY=",
            "QWQ_LAUNCH_TARGET=",
        ):
            self.assertNotIn(forbidden, result.stdout)

    def test_runtime_and_endpoint_defines_are_rejected(self) -> None:
        for key, value in (
            ("APP_RUNTIME_ENV", "alpha"),
            ("CLOUD_GATEWAY_BASE_URL", "https://api.alpha.example"),
            ("APP_LAUNCH_POLICY", "test_live"),
            ("QWQ_LAUNCH_TARGET", "alpha-local"),
        ):
            with self.subTest(key=key):
                environment = self._environment()
                environment["DART_DEFINES"] = _encoded_define(key, value)
                result = subprocess.run(
                    ["bash", str(SCRIPT)],
                    cwd=APP_DIR,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("compile inputs contain runtime configuration", result.stderr)

    def test_build_materializes_only_profile_trust_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust = _trust_envelope(root)
            environment = self._materialization_environment(root, trust)
            package = root / "runtime-config-package.json"
            package.write_text('{"target":"alpha-local"}', encoding="utf-8")
            subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            resource_root = root / "build/Runner.app/qwq_runtime"
            self.assertEqual(
                json.loads(
                    (resource_root / "runtime-config-trust.json").read_text(
                        encoding="utf-8"
                    )
                )["buildProfile"],
                "nonprod",
            )
            self.assertFalse((resource_root / "runtime-config-package.json").exists())

    def test_explicit_target_package_path_is_rejected_without_bundle_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust = _trust_envelope(root)
            environment = self._materialization_environment(root, trust)
            package = root / "runtime-config-package.json"
            package.write_text('{"target":"alpha-local"}', encoding="utf-8")
            environment["QWQ_IOS_RUNTIME_CONFIG_PACKAGE_PATH"] = str(package)
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("activated post-install", result.stderr)
            self.assertFalse(
                (root / "build/Runner.app/qwq_runtime/runtime-config-package.json").exists()
            )

    def test_missing_or_invalid_trust_envelope_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = self._environment()
            missing.update(
                {
                    "TARGET_BUILD_DIR": str(root / "build"),
                    "UNLOCALIZED_RESOURCES_FOLDER_PATH": "Runner.app",
                }
            )
            missing_result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=missing,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing_result.returncode, 2)
            self.assertIn("trust envelope is required", missing_result.stderr)

            trust = _trust_envelope(root)
            payload = json.loads(trust.read_text(encoding="utf-8"))
            payload["environment"] = "alpha"
            trust.write_text(json.dumps(payload), encoding="utf-8")
            invalid_result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=self._materialization_environment(root, trust),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(invalid_result.returncode, 0)
            self.assertIn("canonical schema", invalid_result.stderr)

    def test_manual_keyring_protocol_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._materialization_environment(root, _trust_envelope(root))
            environment["QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON"] = "{}"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("manual trusted-public-keys JSON is retired", result.stderr)

    def test_debug_prod_and_profile_prod_are_rejected(self) -> None:
        for configuration in ("Debug-prod", "Profile-prod"):
            with self.subTest(configuration=configuration):
                environment = self._environment()
                environment["CONFIGURATION"] = configuration
                environment["QWQ_APP_BUILD_PROFILE"] = "prod"
                result = subprocess.run(
                    ["bash", str(SCRIPT)],
                    cwd=APP_DIR,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("supports Release-prod only", result.stderr)

    def test_native_reader_and_cold_start_activation_contract_shape(self) -> None:
        source = APP_DELEGATE.read_text(encoding="utf-8")
        for required in (
            "enum NativeRuntimeConfigReadState",
            "case present(NativeRuntimeConfigActiveProjection)",
            "case absent(NativeRuntimeConfigTrustProjection)",
            "case failure(NativeRuntimeConfigReadError)",
            'case "readRuntimeConfig"',
            'case "readRuntimeConfigState"',
            "static func activate(",
            "package rawPackage: [String: Any]",
            "try validateRequest(decoded)",
            "NativeRuntimeConfigStore.activate(",
            "expectedPackageDigest: packageDigest",
            "expectedTrustEnvelopeDigest: trustDigest",
            "expectedActiveDigest: expectedActiveDigest",
            "Curve25519.Signing.PublicKey",
            "isValidSignature",
            "FileHandle(forWritingTo: temporary)",
            "try handle.synchronize()",
            "replaceItemAt",
            "fsync(directoryHandle)",
            "runtimePackageDestinationURL(createDirectory: true)",
            "let previousActivePackage = try readCurrentActivePackageData()",
            "try atomicallyActivate(packageData)",
            "restorePreviousActivePackage(previousActivePackage, originalError: error)",
            "activationReadbackFailed",
            "activationRollbackFailed",
            "let activatedState = loadActivePackage()",
            "activated.packageDigest == validated.packageDigest",
            'subdirectory: nativeRuntimeConfigDirectory',
        ):
            self.assertIn(required, source)
        self.assertNotIn('case "installRuntimeConfigPackage"', source)
        self.assertNotIn("installArgumentsInvalid", source)
        self.assertNotIn("Set(arguments.keys) == installFields", source)
        self.assertNotIn("Bundle.main.url(\n      forResource: nativeRuntimePackageFileName", source)
        self.assertNotIn("cachedTrustEnvelope", source)
        self.assertNotIn("readTrustEnvelope()", source)
        self.assertNotIn("dartDefinesDigest", source)
        self.assertNotIn("nativeRuntimeConfigDigest", source)
        self.assertIn("nativeActiveRuntimePackageDigest", source)
        info_plist = (APP_DIR / "ios/Runner/Info.plist").read_text(encoding="utf-8")
        for retired_key in (
            "QWQRecoveryBaseURL",
            "QWQPublicWebURL",
            "QWQAppDownloadBaseURL",
            "QWQRuntimeEnvironment",
        ):
            self.assertNotIn(retired_key, info_plist)
        podfile = (APP_DIR / "ios/Podfile").read_text(encoding="utf-8")
        self.assertIn("platform :ios, '16.0'", podfile)
        self.assertNotIn(
            "Bundle.main.url(\n      forResource: nativeRuntimePackageFileName",
            source,
        )

    def test_configuration_identity_is_build_profile_and_mode_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self._materialization_environment(root, _trust_envelope(root))
            environment["PRODUCT_BUNDLE_IDENTIFIER"] = "com.example.quwoquanApp.nonprod.debug"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            environment["PRODUCT_BUNDLE_IDENTIFIER"] = "com.example.quwoquanApp.alpha"
            blocked = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("does not match", blocked.stderr)

    def test_python_resolver_skips_incompatible_path_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_python = root / "bin/python3"
            invalid_python.parent.mkdir()
            invalid_python.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            invalid_python.chmod(0o755)
            compatible_python = root / "python-cache/quwoquan-data/bin/python3"
            compatible_python.parent.mkdir(parents=True)
            compatible_python.symlink_to(Path(sys.executable))
            environment = dict(os.environ)
            environment.pop("QWQ_IOS_STACKCTL_PYTHON", None)
            environment["PATH"] = str(invalid_python.parent) + os.pathsep + environment["PATH"]
            environment["QWQ_PYTHON_CACHE_ROOT"] = str(root / "python-cache")
            result = subprocess.run(
                ["bash", str(STACKCTL_PYTHON_RESOLVER)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()).resolve(), compatible_python.resolve())


if __name__ == "__main__":
    unittest.main()
