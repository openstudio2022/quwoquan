# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-003

from __future__ import annotations

import hashlib
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import startup_attempt_receipt
from quwoquan_app.scripts.gamma import verify_local_gamma_mirror


def _digest_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _runtime_oci(target: str) -> dict[str, object]:
    environment = target.removesuffix("-local")
    images = {
        "api-edge": {
            "ref": "quwoquan/api-edge:build",
            "imageDigest": "sha256:" + "1" * 64,
        },
        "provider-protocol-substitute": {
            "buildInputDigest": "sha256:" + "2" * 64,
            "ref": "quwoquan/provider-protocol-substitute:build",
            "imageDigest": "sha256:" + "3" * 64,
        },
        "sms-provider-substitute": {
            "buildInputDigest": "sha256:" + "4" * 64,
            "ref": "quwoquan/sms-provider-substitute:build",
            "imageDigest": "sha256:" + "5" * 64,
        },
    }
    return {
        "schema": "stackctl-package-oci-images",
        "environment": environment,
        "target": target,
        "configurationDigest": "sha256:" + "1" * 64,
        "buildInputDigest": "sha256:" + "6" * 64,
        "imageDigest": _digest_json(images),
        "images": images,
    }


def _canonical_running_attempt(
    target: str,
    workload: str,
) -> dict[str, object]:
    composition = startup_attempt_receipt.image_composition_from_candidate_oci(
        _runtime_oci(target),
        expected_environment=target.removesuffix("-local"),
        expected_target=target,
    )
    return {
        "schema": "stackctl-local-startup-attempt",
        "attemptId": f"attempt-{target}",
        "env": target.removesuffix("-local"),
        "target": target,
        "status": "running",
        "workload": workload,
        "composeProject": f"quwoquan_{target.removesuffix('-local')}_release_test",
        "candidateDigest": "sha256:" + "3" * 64,
        "configurationDigest": "sha256:" + "1" * 64,
        "providerRuntimeDigest": "sha256:" + "4" * 64,
        "observabilityLogSinkDigest": "sha256:" + "5" * 64,
        "imageTransportTag": composition["imageVersion"],
        "imageComposition": composition,
        "runRoot": "",
        "startedAt": "2026-08-05T00:00:00Z",
        "updatedAt": "2026-08-05T00:00:01Z",
        "failure": None,
        "cleanupFailure": None,
    }


def _gamma_candidate(
    root: Path,
    startup: dict[str, object],
    *,
    provider_digest: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    candidate_root = root / "candidate"
    runtime_shared = candidate_root / "packages/runtime-shared"
    runtime_shared.mkdir(parents=True)
    oci = _runtime_oci("gamma-local")
    (runtime_shared / "oci-images.json").write_text(
        json.dumps(oci),
        encoding="utf-8",
    )
    candidate = {
        "baselineId": startup["candidateDigest"],
        "packageDigest": "sha256:" + "7" * 64,
        "configurationDigest": startup["configurationDigest"],
        "runtimeConfigDigest": "sha256:" + "8" * 64,
        "buildInputDigest": oci["buildInputDigest"],
        "imageDigest": oci["imageDigest"],
        "providerRuntime": {
            "composition": {
                "runtimeCompositionDigest": (
                    provider_digest or startup["providerRuntimeDigest"]
                )
            }
        },
        "observabilityLogSink": {
            "composeDigest": startup["observabilityLogSinkDigest"]
        },
    }
    active = {
        "baselineId": startup["candidateDigest"],
        "candidateDir": str(candidate_root),
    }
    return active, candidate


def _gamma_case(
    phase: str,
    startup: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": verify_local_gamma_mirror.CASE_RESULT_SCHEMA,
        "caseId": verify_local_gamma_mirror.CASE_IDS[phase],
        "status": "passed",
        "environment": "gamma",
        "target": "gamma-local",
        "baselineId": startup["candidateDigest"],
        "attemptId": startup["attemptId"],
        "packageDigest": candidate["packageDigest"],
        "configurationDigest": startup["configurationDigest"],
        "providerRuntimeDigest": startup["providerRuntimeDigest"],
        "observabilityLogSinkDigest": startup["observabilityLogSinkDigest"],
        "imageDigest": candidate["imageDigest"],
        "executed": 1,
        "skipped": 0,
        "failed": 0,
        "executedAt": "2026-08-05T00:00:02Z",
        "specRefs": list(verify_local_gamma_mirror.CASE_SPEC_REFS),
    }


class StackctlRuntimeReceiptSingleTrackContractTest(unittest.TestCase):
    def test_package_image_composition_carries_active_candidate_id(self) -> None:
        configuration_digest = "sha256:" + "1" * 64
        build_input_digest = "sha256:" + "2" * 64
        baseline_id = "sha256:" + "3" * 64
        build_refs = {
            service: f"localhost/quwoquan_service_{service.replace('-', '_')}:build"
            for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
        }
        build_refs["service-core"] = (
            "localhost/quwoquan_service_core:"
            + baseline_id.removeprefix("sha256:")
        )
        images: dict[str, dict[str, str]] = {}
        for index, (service, _) in enumerate(
            stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS,
            start=1,
        ):
            image_digest = "sha256:" + f"{index:064x}"
            images[service] = {
                "ref": build_refs[service],
                "imageDigest": image_digest,
            }
        provider_role = "provider-protocol-substitute"
        provider_descriptor = {
            "buildInputDigest": "sha256:" + "8" * 64,
            "ref": "quwoquan/provider-protocol-substitute:build",
            "imageDigest": "sha256:" + "9" * 64,
        }
        images[provider_role] = provider_descriptor
        image_set_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                images,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        manifest = {
            "schema": stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
            "environment": "alpha",
            "target": "alpha-local",
            "configurationDigest": configuration_digest,
            "buildInputDigest": build_input_digest,
            "imageDigest": image_set_digest,
            "images": images,
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            candidate_root = Path(temporary_dir) / "candidate"
            package_root = candidate_root / "packages/runtime-shared"
            package_root.mkdir(parents=True)
            manifest_path = package_root / "oci-images.json"
            manifest_path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "_packaged_service_source_image_ref",
                    side_effect=lambda _environment, service: build_refs[service],
                ),
                mock.patch.object(
                    stackctl,
                    "packaged_configuration_digest",
                    return_value=configuration_digest,
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": baseline_id},
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value={
                        "baselineId": baseline_id,
                        "imageDigest": image_set_digest,
                        "buildInputDigest": build_input_digest,
                        "configurationDigest": configuration_digest,
                        "runtimeConfigDigest": "sha256:" + "a" * 64,
                        "providerRuntime": {
                            "images": {provider_role: provider_descriptor}
                        },
                    },
                ),
            ):
                composition = stackctl._load_package_bound_local_image_composition(
                    "alpha",
                    "alpha-local",
                )

        self.assertEqual(composition["candidateId"], baseline_id)
        self.assertEqual(
            composition["startupImageCompositionFile"],
            str(manifest_path),
        )
        first_party_refs = {
            service: str(descriptor["imageDigest"])
            for service, descriptor in images.items()
            if service != provider_role
        }
        full_refs = {
            service: str(descriptor["imageDigest"])
            for service, descriptor in images.items()
        }
        self.assertEqual(
            composition["imageVersion"],
            stackctl.immutable_image_digest(first_party_refs),
        )
        self.assertEqual(
            composition["startupImageTransportTag"],
            stackctl.immutable_image_digest(full_refs),
        )
        self.assertNotEqual(
            composition["imageVersion"],
            composition["startupImageTransportTag"],
        )

    def test_health_scope_uses_canonical_current_startup_attempt(self) -> None:
        cases = (
            ("alpha-local", "content-release", "content-consumer"),
            ("beta-local", "content-commercial", "content-commercial"),
            ("gamma-local", "full", "full"),
        )
        for target, workload, expected_scope in cases:
            with self.subTest(target=target, workload=workload):
                attempt = _canonical_running_attempt(target, workload)
                with mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ):
                    actual_scope = stackctl._current_runtime_health_scope(target)

                self.assertEqual(actual_scope, expected_scope)

    def test_health_scope_ignores_retired_environment_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir)
            run_root = process_dir / "old-run"
            run_root.mkdir()
            (process_dir / "stack.state").write_text(
                "workload=content-commercial\n",
                encoding="utf-8",
            )
            (process_dir / "stack_status.json").write_text(
                '{"status":"passed","workload":"content-commercial"}',
                encoding="utf-8",
            )
            (process_dir / "content-release.json").write_text(
                '{"workload":"content-release"}',
                encoding="utf-8",
            )
            (process_dir / "local_run.json").write_text(
                json.dumps({"runRoot": str(run_root)}),
                encoding="utf-8",
            )
            (run_root / "report.json").write_text(
                json.dumps(
                    {
                        "command": "up",
                        "resolvedTarget": "alpha-local",
                        "workload": "content-commercial",
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "target_process_dir",
                    return_value=process_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=None,
                ),
            ):
                actual_scope = stackctl._current_runtime_health_scope("alpha-local")

        self.assertEqual(actual_scope, "full")

    def test_stopped_or_drifted_current_attempt_fails_closed(self) -> None:
        stopped = _canonical_running_attempt("gamma-local", "content-commercial")
        stopped["status"] = "stopped"
        drifted = _canonical_running_attempt("gamma-local", "content-commercial")
        drifted["target"] = "beta-local"
        malformed = _canonical_running_attempt("gamma-local", "content-commercial")
        malformed["configurationDigest"] = "not-a-digest"

        for attempt in (stopped, drifted, malformed):
            with self.subTest(attempt=attempt):
                with mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ):
                    actual_scope = stackctl._current_runtime_health_scope(
                        "gamma-local"
                    )

                self.assertEqual(actual_scope, "full")

    def test_control_consumers_contain_no_retired_receipt_identity(self) -> None:
        sources = (
            inspect.getsource(stackctl._current_runtime_health_scope),
            inspect.getsource(stackctl._load_gamma_runtime_image_composition),
        )

        for source in sources:
            for retired_identity in (
                "stack.state",
                "stack_status.json",
                "content-release.json",
                "local_run.json",
                "report.json",
                "runtimeEnv",
                "startup_attempt_path",
            ):
                self.assertNotIn(retired_identity, source)

    def test_gamma_verifier_consumes_canonical_startup_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            report_path = root / "report.json"
            startup_path = root / "startup_attempt.json"
            t3_path = root / "release_consumer.json"
            t4_path = root / "device_uat.json"
            configuration_digest = "sha256:" + "1" * 64
            startup = _canonical_running_attempt(
                "gamma-local",
                "full",
            )
            startup["configurationDigest"] = configuration_digest
            active, candidate = _gamma_candidate(root, startup)
            startup_path.write_text(json.dumps(startup), encoding="utf-8")
            t3_path.write_text(
                json.dumps(_gamma_case("release_consumer", startup, candidate)),
                encoding="utf-8",
            )
            t4_path.write_text(
                json.dumps(_gamma_case("device_uat", startup, candidate)),
                encoding="utf-8",
            )
            argv = [
                "verify_local_gamma_mirror.py",
                "--report",
                str(report_path),
                "--startup-receipt",
                str(startup_path),
                "--release-consumer-report",
                str(t3_path),
                "--device-uat-report",
                str(t4_path),
                "--configuration-digest",
                configuration_digest,
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    verify_local_gamma_mirror,
                    "active_deployment_candidate",
                    return_value=active,
                ),
                mock.patch.object(
                    verify_local_gamma_mirror,
                    "load_candidate_manifest",
                    return_value=candidate,
                ),
            ):
                exit_code = verify_local_gamma_mirror.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["startupAttempt"]["target"], "gamma-local")
        self.assertNotIn("stack", report)

    def test_gamma_verifier_rejects_provider_runtime_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            startup = _canonical_running_attempt("gamma-local", "full")
            active, candidate = _gamma_candidate(
                root,
                startup,
                provider_digest="sha256:" + "9" * 64,
            )
            startup_path = root / "startup.json"
            startup_path.write_text(json.dumps(startup), encoding="utf-8")
            for phase, name in (("release_consumer", "release_consumer.json"), ("device_uat", "device_uat.json")):
                (root / name).write_text(
                    json.dumps(_gamma_case(phase, startup, candidate)),
                    encoding="utf-8",
                )
            argv = [
                "verify_local_gamma_mirror.py",
                "--report",
                str(root / "report.json"),
                "--startup-receipt",
                str(startup_path),
                "--release-consumer-report",
                str(root / "release_consumer.json"),
                "--device-uat-report",
                str(root / "device_uat.json"),
                "--configuration-digest",
                str(startup["configurationDigest"]),
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    verify_local_gamma_mirror,
                    "active_deployment_candidate",
                    return_value=active,
                ),
                mock.patch.object(
                    verify_local_gamma_mirror,
                    "load_candidate_manifest",
                    return_value=candidate,
                ),
            ):
                exit_code = verify_local_gamma_mirror.main()
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "gate_block")
        self.assertIn("Provider runtime differs", report["startupIssue"])

    def test_gamma_verifier_rejects_bounded_startup_for_green(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            startup = _canonical_running_attempt("gamma-local", "content-release")
            active, candidate = _gamma_candidate(root, startup)
            startup_path = root / "startup.json"
            startup_path.write_text(json.dumps(startup), encoding="utf-8")
            for phase, name in (("release_consumer", "release_consumer.json"), ("device_uat", "device_uat.json")):
                (root / name).write_text(
                    json.dumps(_gamma_case(phase, startup, candidate)),
                    encoding="utf-8",
                )
            argv = [
                "verify_local_gamma_mirror.py",
                "--report",
                str(root / "report.json"),
                "--startup-receipt",
                str(startup_path),
                "--release-consumer-report",
                str(root / "release_consumer.json"),
                "--device-uat-report",
                str(root / "device_uat.json"),
                "--configuration-digest",
                str(startup["configurationDigest"]),
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    verify_local_gamma_mirror,
                    "active_deployment_candidate",
                    return_value=active,
                ),
                mock.patch.object(
                    verify_local_gamma_mirror,
                    "load_candidate_manifest",
                    return_value=candidate,
                ),
            ):
                exit_code = verify_local_gamma_mirror.main()
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "gate_block")
        self.assertIn("workload=full", report["startupIssue"])

    def test_gamma_case_result_requires_bound_non_skipped_execution(self) -> None:
        startup = _canonical_running_attempt("gamma-local", "full")
        candidate = {
            "packageDigest": "sha256:" + "7" * 64,
            "imageDigest": "sha256:" + "8" * 64,
        }
        identity = {
            field: str(value)
            for field, value in _gamma_case("release_consumer", startup, candidate).items()
            if field
            in {
                "environment",
                "target",
                "baselineId",
                "attemptId",
                "packageDigest",
                "configurationDigest",
                "providerRuntimeDigest",
                "observabilityLogSinkDigest",
                "imageDigest",
            }
        }
        baseline = _gamma_case("release_consumer", startup, candidate)
        self.assertEqual(
            verify_local_gamma_mirror.validate_gamma_case_result(
                baseline,
                phase="release_consumer",
                identity=identity,
            ),
            baseline,
        )

        mutations = {
            "baselineId": "sha256:" + "9" * 64,
            "attemptId": "other-attempt",
            "packageDigest": "sha256:" + "9" * 64,
            "configurationDigest": "sha256:" + "9" * 64,
            "providerRuntimeDigest": "sha256:" + "9" * 64,
            "observabilityLogSinkDigest": "sha256:" + "9" * 64,
            "imageDigest": "sha256:" + "9" * 64,
            "executed": 0,
            "skipped": 1,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                forged = dict(baseline)
                forged[field] = value
                with self.assertRaises(ValueError):
                    verify_local_gamma_mirror.validate_gamma_case_result(
                        forged,
                        phase="release_consumer",
                        identity=identity,
                    )

    def test_gamma_dry_run_is_contract_only_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_path = Path(temporary_dir) / "report.json"
            argv = [
                "verify_local_gamma_mirror.py",
                "--report",
                str(report_path),
                "--configuration-digest",
                "sha256:" + "1" * 64,
                "--dry-run",
            ]
            with mock.patch.object(sys, "argv", argv):
                exit_code = verify_local_gamma_mirror.main()
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "gate_block")
        self.assertTrue(report["contractOnly"])
        self.assertNotIn(
            "passed",
            {section["status"] for section in report["tests"].values()},
        )

    def test_gamma_runtime_sources_contain_no_retired_receipt_identity(self) -> None:
        root = Path(__file__).resolve().parents[4]
        sources = (
            root
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
            root
            / "quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py",
            root / "quwoquan_ops/cli/stackctl.py",
        )

        for source_path in sources:
            source = source_path.read_text(encoding="utf-8")
            for retired_identity in (
                "LOCAL_GAMMA_STACK_STATUS_REPORT",
                "stack_status.json",
                "--stack-report",
            ):
                self.assertNotIn(retired_identity, source)


if __name__ == "__main__":
    unittest.main()
