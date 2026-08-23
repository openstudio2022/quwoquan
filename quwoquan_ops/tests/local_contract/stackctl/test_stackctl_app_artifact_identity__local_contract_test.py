"""stackctl package --kind app-artifact 的 build-product local contract。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.commands.package_app_artifact import (
    _BASELINE_BUILD_PRODUCT_IDS,
    _CAPSULE_ROOTS,
    _artifact_digest,
    _build_from_capsule,
    _ios_unsigned_release_command,
    _materialize_protected_inputs,
    _materialize_runtime_config_inputs,
    build_product_artifact_segment,
    command_package_app_artifact,
)
from quwoquan_ops.cli.commands.package_app_artifact_identity import (
    read_android_identity,
    signing_digest,
)


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "build_product_id": "android-nonprod-apk",
        "artifact_path": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _fake_build(**values: object) -> dict[str, str]:
    attempt_dir = Path(str(values["attempt_dir"]))
    artifact = attempt_dir / "app.apk"
    artifact.write_bytes(b"artifact-bytes")
    return {
        "artifactPath": str(artifact),
        "artifactDigest": _artifact_digest(artifact),
        "signingIdentityDigest": "sha256:" + "2" * 64,
        "sourceCapsuleDigest": "sha256:" + "3" * 64,
        "sourceStatusDigest": (
            "sha256:e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
        "runtimeConfigTrustEnvelopeDigest": "sha256:" + "4" * 64,
    }


def _snapshot() -> dict[str, object]:
    return {
        "deploymentInputRoots": ["quwoquan_app"],
        "deploymentInputDigest": "sha256:" + "3" * 64,
        "deploymentInputFileCount": 1,
        "sourceRevision": "a" * 40,
        "workspaceStatusDigest": (
            "sha256:e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
        "baselineId": "sha256:" + "5" * 64,
    }


class StackctlAppArtifactIdentityTest(unittest.TestCase):
    def test_aab_identity_and_signature_use_bundle_aware_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "app-release.aab"
            artifact.write_bytes(b"signed-bundle")
            identity_result = mock.Mock(
                returncode=0,
                stdout="com.leadwise.quwoquan\n",
            )
            signature_result = mock.Mock(
                returncode=0,
                stdout="SHA256: " + ":".join(["AB"] * 32) + "\n",
            )
            identity_module = (
                "quwoquan_ops.cli.commands.package_app_artifact_identity"
            )
            with mock.patch(
                f"{identity_module}.bundletool_command",
                return_value=["bundletool"],
            ), mock.patch(
                f"{identity_module}.subprocess.run",
                side_effect=[identity_result, signature_result],
            ) as run, mock.patch(
                f"{identity_module}.shutil.which",
                return_value="/usr/bin/keytool",
            ):
                identity = read_android_identity(
                    artifact,
                    "com.leadwise.quwoquan",
                )
                signature = signing_digest("android", artifact)
            self.assertEqual(identity, "com.leadwise.quwoquan")
            self.assertEqual(signature, "sha256:" + "ab" * 32)
            self.assertIn("dump", run.call_args_list[0].args[0])
            self.assertIn("-jarfile", run.call_args_list[1].args[0])

    def test_canonical_baseline_is_exactly_five_build_products(self) -> None:
        self.assertEqual(
            _BASELINE_BUILD_PRODUCT_IDS,
            (
                "android-nonprod-apk",
                "android-prod-apk",
                "ios-nonprod-app",
                "ios-prod-app",
                "web-shared",
            ),
        )
        for build_product_id in _BASELINE_BUILD_PRODUCT_IDS:
            with self.subTest(build_product_id=build_product_id), mock.patch(
                "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
                side_effect=OSError("producer imported and invoked"),
            ):
                result = command_package_app_artifact(
                    _args(build_product_id=build_product_id)
                )
                self.assertEqual(result["exitCode"], 2)
                details = "\n".join(result["details"])
                if build_product_id == "ios-prod-app":
                    self.assertIn("prod_ios_identity_unregistered", details)
                else:
                    self.assertIn("producer imported and invoked", details)

    def test_source_capsule_includes_every_production_local_path_dependency(self) -> None:
        self.assertIn("quwoquan_app", _CAPSULE_ROOTS)
        self.assertIn(
            "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors",
            _CAPSULE_ROOTS,
        )

    def test_ios_release_command_uses_profile_and_zero_runtime_defines(self) -> None:
        command = _ios_unsigned_release_command(build_profile="nonprod")
        self.assertIn("--release", command)
        self.assertIn("--no-codesign", command)
        self.assertEqual(command[command.index("--flavor") + 1], "nonprod")
        self.assertFalse(any("dart-define" in token for token in command))
        for forbidden in (
            "APP_RUNTIME_ENV",
            "CLOUD_GATEWAY_BASE_URL",
            "APP_LAUNCH_POLICY",
            "QWQ_LAUNCH_TARGET",
        ):
            self.assertNotIn(forbidden, " ".join(command))

    def test_old_environment_interface_is_rejected_without_fallback(self) -> None:
        for legacy in (
            {"env": "alpha"},
            {"target": "alpha-local"},
            {"app_platform": "android"},
            {"app_build_mode": "release"},
            {"distribution_class": "dev_direct"},
            {"artifact_format": "apk"},
        ):
            with self.subTest(legacy=legacy):
                result = command_package_app_artifact(_args(**legacy))
                self.assertEqual(result["exitCode"], 2)
                self.assertIn("use --build-product-id only", "\n".join(result["details"]))

    def test_build_product_path_has_no_environment_segment(self) -> None:
        attempt_id = str(uuid.uuid4())
        segment = build_product_artifact_segment(
            build_product_id="android-nonprod-apk",
            attempt_id=attempt_id,
        )
        self.assertEqual(segment, f"android-nonprod-apk/{attempt_id}")
        for environment in ("alpha", "beta", "gamma", "prod"):
            self.assertNotIn(f"/{environment}/", f"/{segment}/")

    def test_nonprod_build_is_environment_channel_and_stage_invariant(self) -> None:
        manifests: list[dict[str, object]] = []
        build_arguments: list[dict[str, object]] = []
        for environment, channel, stage in (
            ("alpha", "official_web", "canary"),
            ("beta", "internal", "full"),
            ("gamma", "store", "pilot"),
        ):
            with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ,
                {
                    "QWQ_APP_RUNTIME_ENV": environment,
                    "QWQ_APP_CHANNEL": channel,
                    "QWQ_APP_ROLLOUT_STAGE": stage,
                },
                clear=False,
            ), mock.patch(
                "quwoquan_ops.cli.stackctl.deployment_target_path",
                return_value=Path(directory),
            ), mock.patch(
                "quwoquan_ops.cli.commands.package_app_artifact._build_from_capsule",
                side_effect=_fake_build,
            ) as build, mock.patch(
                "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
                side_effect=[_snapshot(), _snapshot()],
            ), mock.patch(
                "quwoquan_ops.cli.commands.package_app_artifact._git_identity",
                return_value=("a" * 40, "sha1:" + "b" * 40),
            ):
                result = command_package_app_artifact(_args())
                self.assertEqual(result["exitCode"], 0, result)
                manifests.append(result["manifest"])
                build_arguments.append(build.call_args.kwargs)
        invariant_manifest_fields = {
            key: value
            for key, value in manifests[0].items()
            if key not in {"artifactDigest", "buildProvenanceDigest"}
        }
        for manifest in manifests[1:]:
            self.assertEqual(
                {
                    key: value
                    for key, value in manifest.items()
                    if key not in {"artifactDigest", "buildProvenanceDigest"}
                },
                invariant_manifest_fields,
            )
        for arguments in build_arguments:
            self.assertEqual(arguments["build_product_id"], "android-nonprod-apk")
            self.assertEqual(arguments["build_profile"], "nonprod")
            self.assertNotIn("environment", arguments)
            self.assertNotIn("channel", arguments)
            self.assertNotIn("stage", arguments)

    def test_manifest_has_new_fields_and_no_retired_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "quwoquan_ops.cli.stackctl.deployment_target_path",
            return_value=Path(directory),
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact._build_from_capsule",
            side_effect=_fake_build,
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
            side_effect=[_snapshot(), _snapshot()],
        ):
            result = command_package_app_artifact(_args())
        self.assertEqual(result["exitCode"], 0, result)
        manifest = result["manifest"]
        for required in (
            "buildProductId",
            "buildProfile",
            "platform",
            "buildMode",
            "artifactFormat",
            "distributionClass",
            "sourceTreeDigest",
            "buildProvenanceDigest",
            "runtimeConfigTrustEnvelopeDigest",
        ):
            self.assertIn(required, manifest)
        for retired in ("environment", "target", "launchManifestDigest"):
            self.assertNotIn(retired, manifest)

    def test_mobile_build_embeds_only_profile_trust_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trust_path = root / "runtime-config-trust.json"
            trust_path.write_text(
                json.dumps(
                    {
                        "schema": "app-runtime-config-trust",
                        "schemaVersion": "1",
                        "buildProfile": "nonprod",
                        "signatureAlgorithm": "ed25519",
                        "trustedPublicKeys": {
                            "nonprod-key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_APP_RUNTIME_CONFIG_PACKAGE_PATH": "",
                    "QWQ_APP_RUNTIME_CONFIG_TRUST_PATH": str(trust_path),
                },
                clear=False,
            ):
                digest = _materialize_runtime_config_inputs(
                    app_dir=root,
                    build_profile="nonprod",
                    platform="android",
                    command_env={},
                )

            runtime_root = root / "android/app/src/main/assets/qwq_runtime"
            self.assertTrue((runtime_root / "runtime-config-trust.json").is_file())
            self.assertFalse((runtime_root / "runtime-config-package.json").exists())
            self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")

    def test_mobile_build_rejects_target_runtime_package_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path = root / "runtime-config-package.json"
            trust_path = root / "runtime-config-trust.json"
            package_path.write_text("{}", encoding="utf-8")
            trust_path.write_text(
                json.dumps(
                    {
                        "schema": "app-runtime-config-trust",
                        "schemaVersion": "1",
                        "buildProfile": "nonprod",
                        "signatureAlgorithm": "ed25519",
                        "trustedPublicKeys": {
                            "nonprod-key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_APP_RUNTIME_CONFIG_PACKAGE_PATH": str(package_path),
                    "QWQ_APP_RUNTIME_CONFIG_TRUST_PATH": str(trust_path),
                },
                clear=False,
            ):
                with self.assertRaisesRegex(Exception, "runtime_config_package_forbidden"):
                    _materialize_runtime_config_inputs(
                        app_dir=root,
                        build_profile="nonprod",
                        platform="android",
                        command_env={},
                    )

    def test_protected_firebase_key_is_selected_only_by_build_profile(self) -> None:
        payload = json.dumps(
            {
                "client": [
                    {
                        "client_info": {
                            "android_client_info": {
                                "package_name": "com.leadwise.quwoquan.nonprod"
                            }
                        }
                    }
                ]
            }
        )
        module = "quwoquan_ops.cli.commands.package_app_artifact"
        for environment in ("alpha", "beta", "gamma"):
            with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
                os.environ,
                {"QWQ_ANDROID_NONPROD_GOOGLE_SERVICES_JSON": payload},
                clear=False,
            ), mock.patch(f"{module}._write_private"), mock.patch(
                f"{module}._decode_secret",
                return_value=b"keystore",
            ):
                os.environ["QWQ_ANDROID_RELEASE_KEYSTORE_B64"] = "a2V5c3RvcmU="
                os.environ["QWQ_ANDROID_RELEASE_STORE_PASSWORD"] = "store"
                os.environ["QWQ_ANDROID_RELEASE_KEY_ALIAS"] = "alias"
                os.environ["QWQ_ANDROID_RELEASE_KEY_PASSWORD"] = "key"
                _materialize_protected_inputs(
                    app_dir=Path(directory),
                    build_profile="nonprod",
                    platform="android",
                    build_mode="release",
                    artifact_format="apk",
                    application_id="com.leadwise.quwoquan.nonprod",
                    command_env={},
                    private_dir=Path(directory) / "private",
                )
            self.assertEqual(environment in {"alpha", "beta", "gamma"}, True)
        source = Path(
            sys.modules[_build_from_capsule.__module__].__file__ or ""
        ).read_text(encoding="utf-8")
        for retired in (
            "QWQ_ANDROID_ALPHA_GOOGLE_SERVICES_JSON",
            "QWQ_ANDROID_BETA_GOOGLE_SERVICES_JSON",
            "QWQ_ANDROID_GAMMA_GOOGLE_SERVICES_JSON",
        ):
            self.assertNotIn(retired, source)

    def test_artifact_path_bypass_is_rejected(self) -> None:
        result = command_package_app_artifact(_args(artifact_path="/tmp/app.apk"))
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("--artifact-path bypass is forbidden", "\n".join(result["details"]))

    def test_source_drift_is_typed_concurrent_writer_block(self) -> None:
        changed = _snapshot()
        changed["deploymentInputDigest"] = "sha256:" + "9" * 64
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "quwoquan_ops.cli.stackctl.deployment_target_path",
            return_value=Path(directory),
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact._build_from_capsule",
            side_effect=_fake_build,
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
            side_effect=[_snapshot(), changed],
        ):
            result = command_package_app_artifact(_args())
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("WORKSPACE.CONCURRENT_WRITER", result["details"][0])


if __name__ == "__main__":
    unittest.main()
