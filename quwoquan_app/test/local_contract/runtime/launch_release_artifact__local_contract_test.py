"""prod-sim exact Release 启动边界的 local_contract。"""

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-004

from __future__ import annotations

import importlib.util
import json
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_app/scripts/device/launch_release_artifact.py"
CANDIDATE_DIGEST = "sha256:" + "c" * 64


def _load_module():
    spec = importlib.util.spec_from_file_location("launch_release_artifact", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_inputs(module, root: Path):
    artifact = root / "android-prod-apk.apk"
    artifact.write_bytes(b"exact-release-artifact")
    artifact_digest = module._digest(artifact)
    source_capsule_digest = "sha256:" + "3" * 64
    signing_digest = "sha256:" + "2" * 64
    trust_digest = "sha256:" + "4" * 64
    provenance_digest = module.build_provenance_digest(
        build_product_id="android-prod-apk",
        source_git_sha="a" * 40,
        source_tree_digest="sha1:" + "b" * 40,
        source_capsule_digest=source_capsule_digest,
        artifact_digest=artifact_digest,
        signing_identity_digest=signing_digest,
    )
    manifest = {
        "schema": "app-artifact-manifest",
        "buildProductId": "android-prod-apk",
        "buildProfile": "prod",
        "platform": "android",
        "buildMode": "release",
        "distributionClass": "store",
        "artifactFormat": "apk",
        "applicationId": "com.leadwise.quwoquan",
        "displayVersion": "1.0.0",
        "buildNumber": "1",
        "signingIdentityDigest": signing_digest,
        "sourceGitSha": "a" * 40,
        "sourceTreeDigest": "sha1:" + "b" * 40,
        "buildProvenanceDigest": provenance_digest,
        "artifactDigest": artifact_digest,
        "promotable": True,
        "runtimeConfigTrustEnvelopeDigest": trust_digest,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    receipt = {
        "schema": "app-artifact-build-receipt",
        "attemptId": "build-attempt-1",
        "buildProductId": "android-prod-apk",
        "sourceCapsuleDigest": source_capsule_digest,
        "sourceStatusDigest": "sha256:" + "5" * 64,
        "manifestPath": str(manifest_path),
        "manifestDigest": module._digest(manifest_path),
        "artifactPath": str(artifact),
        "artifactDigest": artifact_digest,
        "buildProvenanceDigest": provenance_digest,
        "flutterVersion": "3.35.1",
        "commandResolutionDigest": "sha256:" + "6" * 64,
    }
    evidence_names = {
        "dependencyProjectionExpectationRef": (
            "dependency-projection-expectation.json"
        ),
        "dependencyProjectionPrebuildReadbackRef": (
            "dependency-projection-prebuild-readback.json"
        ),
        "dependencyProjectionPostbuildReadbackRef": (
            "dependency-projection-postbuild-readback.json"
        ),
    }
    for index, (field, name) in enumerate(evidence_names.items(), start=9):
        evidence_path = root / name
        evidence_path.write_text("{}", encoding="utf-8")
        evidence_path.chmod(0o600)
        receipt[field] = str(evidence_path)
        receipt[field.removesuffix("Ref") + "Digest"] = (
            "sha256:" + f"{index:x}" * 64
        )
    (root / "build-receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    handoff = {
        **module.EXPECTED_HANDOFF_IDENTITY,
        "runtimeConfigTrustEnvelopeDigest": trust_digest,
        "runtimeConfigPackageDigest": "sha256:" + "7" * 64,
        "effectiveLaunchManifestDigest": "sha256:" + "8" * 64,
    }
    handoff_path = root / "launcher-handoff.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    return manifest_path, handoff_path


def _load_exact_inputs(module, manifest_path: Path, handoff_path: Path):
    return module._load_inputs(
        manifest_path,
        "android",
        handoff_path,
        candidate_digest=CANDIDATE_DIGEST,
        artifact_manifest_digest=module._digest(manifest_path),
        launcher_handoff_digest=module._digest(handoff_path),
    )


def _new_launching_attempt(module, path: Path) -> dict[str, object]:
    attempt = module.create_app_launch_attempt(
        path,
        environment="prod",
        target="prod-sim",
        platform="android",
        build_profile="prod",
        build_mode="release",
        run_mode="release-artifact",
        launch_provenance="release_package",
        runtime_config_supply_mode="external_runtime_package",
        runtime_config_trust_envelope_digest="sha256:" + "4" * 64,
        runtime_config_package_digest="sha256:" + "7" * 64,
        application_id="com.leadwise.quwoquan",
        flutter_version="3.35.1",
        command_resolution_digest="sha256:" + "6" * 64,
        device_id="android-device-1",
        artifact_digest="sha256:" + "1" * 64,
        candidate_digest=CANDIDATE_DIGEST,
        artifact_manifest_digest="sha256:" + "d" * 64,
        launcher_handoff_digest="sha256:" + "e" * 64,
        launch_digest="sha256:" + "8" * 64,
        non_promotable=True,
    )
    for status in (
        "compiling",
        "compiled",
        "installing",
        "installed",
        "configuring",
        "configured",
        "launching",
    ):
        attempt = module.transition_app_launch_attempt(path, status)
    return attempt


def _release_driver(
    module,
    root: Path,
    attempt_path: Path,
    terminal_path: Path,
):
    return module.ReleaseAndroidPlatformDriver(
        device_id="android-device-1",
        application_id="com.leadwise.quwoquan",
        entrypoint="lib/main_prod.dart",
        artifact=root / "android-prod-apk.apk",
        artifact_digest="sha256:" + "1" * 64,
        launch_attempt_receipt=attempt_path,
        startup_terminal_receipt=terminal_path,
    )


def _android_production_startup_evidence(
    *,
    startup_attempt_id: str,
    effective_launch_manifest_digest: str | None,
) -> tuple[str, str]:
    digest_field = (
        ""
        if effective_launch_manifest_digest is None
        else " effectiveLaunchManifestDigest="
        + effective_launch_manifest_digest
    )
    return (
        (
            "android_dart_startup_attempt "
            f"attemptId={startup_attempt_id} "
            "launchProvenance=release_package "
            "runtimeConfigSupplyMode=external_runtime_package "
            "hotRestart=false configurationState=complete"
            f"{digest_field}"
        ),
        (
            "android_startup_safe_terminal surface=router_shell "
            "reportedElapsedMs=10 "
            f"attemptId={startup_attempt_id} "
            "launchProvenance=release_package "
            "runtimeConfigSupplyMode=external_runtime_package"
        ),
    )


class LaunchReleaseArtifactTest(unittest.TestCase):
    def test_ios_release_simulator_fails_before_manifest_consumption(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            missing_manifest = Path(directory) / "does-not-exist.json"
            with self.assertRaisesRegex(
                ValueError,
                "APP.LAUNCH.ios_release_simulator_unsupported",
            ):
                module._load_inputs(
                    missing_manifest,
                    "ios",
                    candidate_digest=CANDIDATE_DIGEST,
                    artifact_manifest_digest="sha256:" + "d" * 64,
                    launcher_handoff_digest="sha256:" + "e" * 64,
                )

    def test_exact_build_receipt_manifest_artifact_and_handoff_are_bound(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, handoff_path = _write_inputs(module, Path(directory))
            with mock.patch.object(
                module,
                "build_runtime_config_activation_request",
                return_value={},
            ), mock.patch.object(
                module, "validate_schema_document", return_value=[]
            ), mock.patch.object(
                module, "validate_dependency_projection_receipt"
            ) as dependency_validator:
                inputs = _load_exact_inputs(
                    module,
                    manifest_path,
                    handoff_path,
                )
            dependency_validator.assert_called_once_with(
                inputs.build_receipt,
                manifest_path.resolve().parent,
            )
            self.assertEqual(inputs.build_receipt["flutterVersion"], "3.35.1")
            self.assertEqual(
                inputs.build_receipt["commandResolutionDigest"],
                "sha256:" + "6" * 64,
            )
            self.assertEqual(
                inputs.handoff["launchProvenance"], "release_package"
            )
            self.assertEqual(
                inputs.handoff["runtimeConfigSupplyMode"],
                "external_runtime_package",
            )

    def test_build_receipt_requires_dependency_projection_triplet(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, handoff_path = _write_inputs(module, root)
            receipt_path = root / "build-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt.pop("dependencyProjectionPostbuildReadbackDigest")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with mock.patch.object(
                module, "validate_schema_document", return_value=[]
            ), self.assertRaisesRegex(
                ValueError,
                "dependencyProjectionPostbuildReadbackDigest",
            ):
                _load_exact_inputs(module, manifest_path, handoff_path)

    def test_build_receipt_rejects_tampered_dependency_projection(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, handoff_path = _write_inputs(module, Path(directory))
            with mock.patch.object(
                module, "validate_schema_document", return_value=[]
            ), mock.patch.object(
                module,
                "validate_dependency_projection_receipt",
                side_effect=ValueError("expectation evidence digest drifted"),
            ), self.assertRaisesRegex(
                ValueError,
                rf"{module.INVALID_ARTIFACT}: build receipt dependency "
                "projection invalid: expectation evidence digest drifted",
            ):
                _load_exact_inputs(module, manifest_path, handoff_path)

    def test_retired_artifact_environment_is_not_dual_read(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, handoff_path = _write_inputs(module, root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["environment"] = "prod"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError,
                module.INVALID_ARTIFACT,
            ):
                _load_exact_inputs(module, manifest_path, handoff_path)

    def test_release_launcher_cannot_skip_activation_or_accept_rollout(self) -> None:
        launcher = SCRIPT.read_text(encoding="utf-8")
        adapter = (
            ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("CanonicalLaunchExecutor", launcher)
        self.assertIn("build_runtime_config_activation_request", launcher)
        self.assertNotIn('"monkey"', launcher)
        self.assertIn('--launcher-handoff "$LAUNCHER_HANDOFF"', adapter)
        self.assertIn("does not execute rollout or canary", adapter)

    def test_release_attach_rejects_pid_without_safe_terminal_receipt(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt_path = root / "launch-attempt.json"
            terminal_path = root / "startup-terminal.json"
            _new_launching_attempt(module, attempt_path)
            driver = _release_driver(
                module,
                root,
                attempt_path,
                terminal_path,
            )
            attached = mock.Mock()
            pid_result = mock.Mock(
                returncode=0,
                stdout="1234\n",
                stderr="",
            )
            with mock.patch.object(
                module, "_run", return_value=pid_result
            ) as run_mock, \
                mock.patch.object(
                    driver,
                    "startup_evidence_lines",
                    return_value=(),
                ), self.assertRaisesRegex(
                    module.CanonicalExecutorError,
                    "startup safe-terminal",
                ):
                driver.attach(
                    (),
                    timeout_seconds=0.001,
                    on_attached=attached,
                )

            attached.assert_not_called()
            run_mock.assert_not_called()
            self.assertFalse(terminal_path.exists())
            current = module.read_app_launch_attempt(attempt_path)
            self.assertEqual(
                module._failure_blocker(str(current["status"])),
                "APP.LAUNCH.launch_failed",
            )
            self.assertNotIn(
                "launched",
                [
                    item["status"]
                    for item in current["transitions"]
                ],
            )

    def test_release_attach_binds_same_attempt_router_shell_receipt(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt_path = root / "launch-attempt.json"
            terminal_path = root / "startup-terminal.json"
            launch_attempt = _new_launching_attempt(module, attempt_path)
            driver = _release_driver(
                module,
                root,
                attempt_path,
                terminal_path,
            )
            startup_attempt_id = "cold-release-a1"
            evidence = _android_production_startup_evidence(
                startup_attempt_id=startup_attempt_id,
                effective_launch_manifest_digest=str(
                    launch_attempt["launchDigest"]
                ),
            )
            attached = mock.Mock()
            with mock.patch.object(
                driver,
                "startup_evidence_lines",
                return_value=evidence,
            ):
                exit_code = driver.attach(
                    (),
                    timeout_seconds=1,
                    on_attached=attached,
                )

            attached.assert_called_once_with()
            self.assertEqual(exit_code, 0)
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            observed_attempt = module.read_app_launch_attempt(attempt_path)
            expected_identity = {
                "launchAttemptId": launch_attempt["attemptId"],
                "artifactDigest": launch_attempt["artifactDigest"],
                "deviceId": launch_attempt["deviceId"],
                "applicationId": launch_attempt["applicationId"],
                "launchProvenance": launch_attempt["launchProvenance"],
                "runtimeConfigSupplyMode": launch_attempt[
                    "runtimeConfigSupplyMode"
                ],
                "effectiveLaunchManifestDigest": launch_attempt["launchDigest"],
                "surface": "router_shell",
                "hotRestart": False,
            }
            self.assertEqual(
                {field: terminal[field] for field in expected_identity},
                expected_identity,
            )
            self.assertEqual(
                observed_attempt["startupTerminalAttemptId"],
                startup_attempt_id,
            )
            self.assertEqual(
                observed_attempt["startupTerminalEvidenceRef"],
                str(terminal_path),
            )
            self.assertEqual(
                observed_attempt["startupTerminalEvidenceDigest"],
                module.canonical_document_digest(terminal),
            )
            module._phase_emitter(attempt_path)(
                "QWQ_APP_LAUNCH_PHASE status=launched"
            )
            launched_attempt = module.read_app_launch_attempt(attempt_path)
            self.assertEqual(launched_attempt["status"], "launched")
            self.assertEqual(
                launched_attempt["runtimeHealthStatus"],
                "healthy",
            )

    def test_release_attach_rejects_missing_or_mismatched_observed_digest(
        self,
    ) -> None:
        module = _load_module()
        observed_digests = {
            "missing": None,
            "mismatched": "sha256:" + "f" * 64,
        }
        for case, observed_digest in observed_digests.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                attempt_path = root / "launch-attempt.json"
                terminal_path = root / "startup-terminal.json"
                _new_launching_attempt(module, attempt_path)
                driver = _release_driver(
                    module,
                    root,
                    attempt_path,
                    terminal_path,
                )
                evidence = _android_production_startup_evidence(
                    startup_attempt_id="cold-release-a1",
                    effective_launch_manifest_digest=observed_digest,
                )
                attached = mock.Mock()

                with mock.patch.object(
                    driver,
                    "startup_evidence_lines",
                    return_value=evidence,
                ), self.assertRaisesRegex(
                    module.CanonicalExecutorError,
                    "effective manifest",
                ):
                    driver.attach(
                        (),
                        timeout_seconds=1,
                        on_attached=attached,
                    )

                attached.assert_not_called()
                self.assertFalse(terminal_path.exists())

    def test_android_attempt_marker_uses_verified_runtime_digest(self) -> None:
        android = (
            ROOT
            / "quwoquan_app/android/app/src/main/java/com/quwoquan/"
            "quwoquan_app/MainActivity.java"
        ).read_text(encoding="utf-8")

        self.assertIn("readVerifiedEffectiveLaunchManifestDigest()", android)
        self.assertIn("readEffectiveLaunchManifestDigest()", android)
        self.assertIn(' + " effectiveLaunchManifestDigest="', android)

    def test_release_attach_rejects_stale_or_tampered_terminal_identity(self) -> None:
        module = _load_module()
        mismatches = {
            "launchAttemptId": "old-launch-attempt",
            "artifactDigest": "sha256:" + "a" * 64,
            "deviceId": "another-device",
            "applicationId": "com.example.another",
            "launchProvenance": "canonical_launcher",
            "runtimeConfigSupplyMode": "compile_time_define",
            "effectiveLaunchManifestDigest": "sha256:" + "b" * 64,
        }
        for field, mismatched_value in mismatches.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                attempt_path = root / "launch-attempt.json"
                terminal_path = root / "startup-terminal.json"
                launch_attempt = _new_launching_attempt(module, attempt_path)
                terminal = {
                    "schema": "quwoquan_app.startup_safe_terminal.v1",
                    "launchAttemptId": launch_attempt["attemptId"],
                    "startupAttemptId": "cold-release-a1",
                    "platform": "android",
                    "deviceId": launch_attempt["deviceId"],
                    "applicationId": launch_attempt["applicationId"],
                    "launchProvenance": launch_attempt["launchProvenance"],
                    "runtimeConfigSupplyMode": launch_attempt[
                        "runtimeConfigSupplyMode"
                    ],
                    "effectiveLaunchManifestDigest": launch_attempt[
                        "launchDigest"
                    ],
                    "artifactDigest": launch_attempt["artifactDigest"],
                    "configurationState": "complete",
                    "surface": "router_shell",
                    "canonicalTerminal": "routerShell",
                    "hotRestart": False,
                    "observedMarkerDigest": "sha256:" + "c" * 64,
                }
                terminal[field] = mismatched_value
                terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
                driver = _release_driver(
                    module,
                    root,
                    attempt_path,
                    terminal_path,
                )
                attached = mock.Mock()

                with mock.patch.object(
                    driver,
                    "startup_evidence_lines",
                    return_value=(),
                ), self.assertRaisesRegex(
                    module.CanonicalExecutorError,
                    "identity mismatch",
                ):
                    driver.attach(
                        (),
                        timeout_seconds=1,
                        on_attached=attached,
                    )

                attached.assert_not_called()
                self.assertEqual(
                    module.read_app_launch_attempt(attempt_path)["status"],
                    "launching",
                )

    def test_launched_phase_rejects_missing_safe_terminal_binding(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            attempt_path = Path(directory) / "launch-attempt.json"
            _new_launching_attempt(module, attempt_path)

            with self.assertRaisesRegex(
                module.CanonicalExecutorError,
                "startup safe-terminal",
            ):
                module._phase_emitter(attempt_path)(
                    "QWQ_APP_LAUNCH_PHASE status=launched"
                )

            self.assertEqual(
                module.read_app_launch_attempt(attempt_path)["status"],
                "launching",
            )

    def test_install_revalidates_exact_artifact_after_adb_returns(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "android-prod-apk.apk"
            artifact.write_bytes(b"exact-release-artifact")
            driver = module.ReleaseAndroidPlatformDriver(
                device_id="android-device-1",
                application_id="com.leadwise.quwoquan",
                entrypoint="lib/main_prod.dart",
                artifact=artifact,
                artifact_digest=module._digest(artifact),
                launch_attempt_receipt=root / "attempt.json",
                startup_terminal_receipt=root / "startup-terminal.json",
            )

            def mutate_during_install(_command):
                artifact.write_bytes(b"mutated-during-adb-install")
                return mock.Mock(returncode=0, stdout="Success", stderr="")

            with mock.patch.object(
                module,
                "_run",
                side_effect=mutate_during_install,
            ), self.assertRaisesRegex(
                module.CanonicalExecutorError,
                "exact Release artifact changed",
            ):
                driver.install()

    def test_release_signal_handler_settles_prelaunch_attempt(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "attempt.json"
            handlers = {}

            def register(signum, handler):
                handlers[signum] = handler
                return signal.SIG_DFL

            def execute(args, _inputs):
                module.create_app_launch_attempt(
                    args.receipt,
                    environment="prod",
                    target="prod-sim",
                    platform="android",
                    build_profile="prod",
                    build_mode="release",
                    run_mode="release-artifact",
                    launch_provenance="release_package",
                    runtime_config_supply_mode="external_runtime_package",
                    runtime_config_trust_envelope_digest="sha256:" + "4" * 64,
                    runtime_config_package_digest="sha256:" + "7" * 64,
                    application_id="com.leadwise.quwoquan",
                    flutter_version="3.35.1",
                    command_resolution_digest="sha256:" + "6" * 64,
                    device_id="android-device-1",
                    artifact_digest="sha256:" + "1" * 64,
                    candidate_digest=CANDIDATE_DIGEST,
                    artifact_manifest_digest="sha256:" + "d" * 64,
                    launcher_handoff_digest="sha256:" + "e" * 64,
                    launch_digest="sha256:" + "8" * 64,
                    non_promotable=True,
                )
                module.transition_app_launch_attempt(args.receipt, "compiling")
                handlers[signal.SIGTERM](signal.SIGTERM, None)
                raise AssertionError("signal handler must unwind the executor")

            argv = [
                str(SCRIPT),
                "--manifest",
                str(root / "manifest.json"),
                "--launcher-handoff",
                str(root / "handoff.json"),
                "--device",
                "android-device-1",
                "--platform",
                "android",
                "--receipt",
                str(receipt),
                "--candidate-digest",
                CANDIDATE_DIGEST,
                "--artifact-manifest-digest",
                "sha256:" + "d" * 64,
                "--launcher-handoff-digest",
                "sha256:" + "e" * 64,
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                module,
                "_load_inputs",
                return_value=object(),
            ), mock.patch.object(
                module,
                "_execute_release_attempt",
                side_effect=execute,
            ), mock.patch.object(module.signal, "signal", side_effect=register):
                self.assertEqual(module.main(), 130)

            attempt = module.read_app_launch_attempt(receipt)
            self.assertEqual(attempt["status"], "failed")
            self.assertEqual(
                attempt["firstBlocker"],
                "APP.LAUNCH.compile_failed",
            )


if __name__ == "__main__":
    unittest.main()
