#!/usr/bin/env python3
"""Activate and launch one exact Android Release artifact on prod-sim."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
DEVICE_SCRIPTS = Path(__file__).resolve().parent
for import_root in (ROOT, DEVICE_SCRIPTS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from canonical_app_instance.activation import (
    CanonicalExecutorError,
    CanonicalLaunchExecutor,
)
from run_app_instance import AndroidPlatformDriver
from supervise_app_launch import (
    _SafeTerminalIdentityError as SafeTerminalIdentityError,
)
from supervise_app_launch import _SafeTerminalTracker as SafeTerminalTracker

from quwoquan_app.scripts.device.startup_terminal_receipt import (
    canonical_document_digest,
    read_startup_terminal_receipt,
)
from quwoquan_ops.cli.commands.package_app_artifact_helpers import (
    validate_dependency_projection_receipt,
)
from quwoquan_ops.cli.commands.package_app_artifact import (
    build_provenance_digest,
)
from quwoquan_ops.cli.lib.app_launch_attempt import (
    create_app_launch_attempt,
    read_app_launch_attempt,
    record_app_launch_attempt_observation,
    transition_app_launch_attempt,
)
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_activation_request,
)
from quwoquan_ops.cli.lib.app_launch_manifest_schema import (
    validate_schema_document,
)
from quwoquan_ops.cli.lib.generated.app_launch_contract import (
    APP_ARTIFACT_CONTRACT,
    APP_LAUNCH_MANIFEST,
)

IOS_SIMULATOR_RELEASE_BLOCKER = (
    "APP.LAUNCH.ios_release_simulator_unsupported: Flutter iOS simulator "
    "supports Debug only; use an iphoneos Release artifact on an authorized "
    "registered device instead"
)
INVALID_ARTIFACT = "APP.LAUNCH.prod_artifact_invalid"
EXPECTED_BUILD_PRODUCT_ID = "android-prod-apk"
EXPECTED_HANDOFF_IDENTITY = {
    "environment": "prod",
    "target": "prod-sim",
    "buildProfile": "prod",
    "entrypoint": "lib/main_prod.dart",
    "launchPolicy": "prod_release",
    "launchProvenance": "release_package",
    "runtimeConfigSupplyMode": "external_runtime_package",
}
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class _ReleaseLaunchInterrupted(BaseException):
    """Unwind every synchronous Release phase when the parent is signalled."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


@dataclass(frozen=True)
class ReleaseLaunchInputs:
    manifest: dict[str, Any]
    build_receipt: dict[str, Any]
    handoff: dict[str, Any]
    artifact: Path
    build_receipt_path: Path
    handoff_path: Path


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return seconds


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--launcher-handoff", required=True, type=Path)
    parser.add_argument("--device", required=True)
    parser.add_argument("--platform", required=True, choices=("android", "ios"))
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--log-ref", default="")
    parser.add_argument(
        "--activation-timeout-seconds", type=_positive_seconds, default=30.0
    )
    parser.add_argument(
        "--launch-timeout-seconds", type=_positive_seconds, default=30.0
    )
    return parser


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    elif path.is_dir():
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            relative = child.relative_to(path).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(child.stat().st_size.to_bytes(8, "big"))
            with child.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
    else:
        raise ValueError(f"artifact is missing: {path}")
    return "sha256:" + digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must be an object")  # noqa: TRY004
    return decoded


def _invalid(detail: str) -> ValueError:
    return ValueError(f"{INVALID_ARTIFACT}: {detail}")


def _validate_manifest(manifest: dict[str, Any], platform: str) -> None:
    schema = APP_ARTIFACT_CONTRACT["schemas"]["app_artifact_manifest"]
    issues = validate_schema_document(
        manifest,
        "app_artifact_manifest",
        contract=APP_ARTIFACT_CONTRACT,
        field_path="artifactManifest",
    )
    if issues:
        raise _invalid("artifact manifest schema invalid: " + "; ".join(issues))
    product = APP_ARTIFACT_CONTRACT["build_products"][EXPECTED_BUILD_PRODUCT_ID]
    expected = {
        "schema": schema["schema_value"],
        "buildProductId": EXPECTED_BUILD_PRODUCT_ID,
        "buildProfile": product["build_profile"],
        "platform": platform,
        "buildMode": product["build_mode"],
        "distributionClass": product["distribution_class"],
        "artifactFormat": product["artifact_format"],
        "applicationId": APP_ARTIFACT_CONTRACT["application_identity"][
            "base_application_ids"
        ][platform]["value"],
    }
    mismatches = [
        field for field, value in expected.items() if manifest.get(field) != value
    ]
    if mismatches or manifest.get("promotable") is not True:
        raise _invalid(
            "prod-sim requires the exact promotable android-prod-apk manifest; "
            f"mismatched={sorted(mismatches)}"
        )
    if _DIGEST.fullmatch(
        str(manifest.get("runtimeConfigTrustEnvelopeDigest") or "")
    ) is None:
        raise _invalid("artifact manifest runtimeConfigTrustEnvelopeDigest is invalid")


def _validate_build_receipt(
    *,
    receipt: dict[str, Any],
    receipt_path: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> Path:
    required = {
        "schema",
        "attemptId",
        "buildProductId",
        "sourceCapsuleDigest",
        "sourceStatusDigest",
        "manifestPath",
        "manifestDigest",
        "artifactPath",
        "artifactDigest",
        "buildProvenanceDigest",
        "flutterVersion",
        "commandResolutionDigest",
        "dependencyProjectionExpectationRef",
        "dependencyProjectionExpectationDigest",
        "dependencyProjectionPrebuildReadbackRef",
        "dependencyProjectionPrebuildReadbackDigest",
        "dependencyProjectionPostbuildReadbackRef",
        "dependencyProjectionPostbuildReadbackDigest",
    }
    if set(receipt) != required:
        raise _invalid(
            "build receipt fields mismatch; "
            f"missing={sorted(required - set(receipt))} "
            f"unexpected={sorted(set(receipt) - required)}"
        )
    if (
        receipt.get("schema") != "app-artifact-build-receipt"
        or receipt.get("buildProductId") != manifest["buildProductId"]
        or not str(receipt.get("attemptId") or "").strip()
        or Path(str(receipt.get("manifestPath") or "")).resolve()
        != manifest_path.resolve()
        or receipt.get("manifestDigest") != _digest(manifest_path)
        or receipt.get("artifactDigest") != manifest["artifactDigest"]
        or receipt.get("buildProvenanceDigest")
        != manifest["buildProvenanceDigest"]
        or not str(receipt.get("flutterVersion") or "").strip()
    ):
        raise _invalid(f"build receipt identity mismatch: {receipt_path}")
    for field in (
        "sourceCapsuleDigest",
        "sourceStatusDigest",
        "artifactDigest",
        "buildProvenanceDigest",
        "commandResolutionDigest",
    ):
        if _DIGEST.fullmatch(str(receipt.get(field) or "")) is None:
            raise _invalid(f"build receipt {field} is invalid")
    try:
        validate_dependency_projection_receipt(receipt, receipt_path.parent)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise _invalid(f"build receipt dependency projection invalid: {error}") from error
    expected_provenance = build_provenance_digest(
        build_product_id=str(manifest["buildProductId"]),
        source_git_sha=str(manifest["sourceGitSha"]),
        source_tree_digest=str(manifest["sourceTreeDigest"]),
        source_capsule_digest=str(receipt["sourceCapsuleDigest"]),
        artifact_digest=str(receipt["artifactDigest"]),
        signing_identity_digest=str(manifest["signingIdentityDigest"]),
    )
    if expected_provenance != manifest["buildProvenanceDigest"]:
        raise _invalid("build provenance does not bind the build receipt and artifact")
    artifact = Path(str(receipt.get("artifactPath") or "")).resolve()
    if _digest(artifact) != manifest["artifactDigest"]:
        raise _invalid("artifact digest mismatch")
    return artifact


def _validate_handoff(
    handoff: dict[str, Any], manifest: dict[str, Any]
) -> None:
    issues = validate_schema_document(
        handoff,
        "app_launcher_handoff",
        contract=APP_LAUNCH_MANIFEST,
        field_path="launcherHandoff",
    )
    if issues:
        raise _invalid("launcher handoff schema invalid: " + "; ".join(issues))
    mismatches = [
        field
        for field, value in EXPECTED_HANDOFF_IDENTITY.items()
        if handoff.get(field) != value
    ]
    if mismatches:
        raise _invalid(
            "launcher handoff is not prod/prod-sim release_package; "
            f"mismatched={sorted(mismatches)}"
        )
    if (
        handoff.get("runtimeConfigTrustEnvelopeDigest")
        != manifest["runtimeConfigTrustEnvelopeDigest"]
    ):
        raise _invalid("artifact and handoff trust envelope digests disagree")
    try:
        build_runtime_config_activation_request(handoff)
    except ValueError as error:
        raise _invalid(f"launcher handoff is invalid: {error}") from error


def _load_inputs(
    manifest_path: Path,
    platform: str,
    handoff_path: Path | None = None,
) -> ReleaseLaunchInputs:
    if platform == "ios":
        raise ValueError(IOS_SIMULATOR_RELEASE_BLOCKER)
    if handoff_path is None:
        raise _invalid("launcher handoff is required")
    manifest_path = manifest_path.resolve()
    handoff_path = handoff_path.resolve()
    manifest = _load_object(manifest_path, "artifact manifest")
    _validate_manifest(manifest, platform)
    build_receipt_path = manifest_path.with_name("build-receipt.json")
    build_receipt = _load_object(build_receipt_path, "build receipt")
    artifact = _validate_build_receipt(
        receipt=build_receipt,
        receipt_path=build_receipt_path,
        manifest=manifest,
        manifest_path=manifest_path,
    )
    handoff = _load_object(handoff_path, "launcher handoff")
    _validate_handoff(handoff, manifest)
    return ReleaseLaunchInputs(
        manifest=manifest,
        build_receipt=build_receipt,
        handoff=handoff,
        artifact=artifact,
        build_receipt_path=build_receipt_path,
        handoff_path=handoff_path,
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


class ReleaseAndroidPlatformDriver(AndroidPlatformDriver):
    """Reuse canonical native activation while consuming a prebuilt artifact."""

    def __init__(
        self,
        *,
        device_id: str,
        application_id: str,
        entrypoint: str,
        artifact: Path,
        artifact_digest: str,
        launch_attempt_receipt: Path,
        startup_terminal_receipt: Path | None,
    ) -> None:
        super().__init__(
            device_id=device_id,
            application_id=application_id,
            entrypoint=entrypoint,
        )
        self.release_artifact = artifact
        self.release_artifact_digest = artifact_digest
        self.launch_attempt_receipt = launch_attempt_receipt
        self.startup_terminal_receipt = startup_terminal_receipt

    def artifact_path(self) -> Path:
        return self.release_artifact

    def build(self, environment: dict[str, str]) -> None:
        del environment
        self._verify_artifact()

    def install(self) -> None:
        self._verify_artifact()
        result = _run(
            [
                "adb",
                "-s",
                self.device_id,
                "install",
                "-r",
                str(self.release_artifact),
            ]
        )
        if result.returncode != 0:
            raise CanonicalExecutorError(
                "unable to install exact Release artifact: "
                + (result.stderr.strip() or result.stdout.strip())[:300]
            )
        # The contract binds installed to a readback of the same payload path
        # after the real installer returns.  A pre-install check alone leaves
        # a mutation window while adb owns the artifact.
        self._verify_artifact()

    def attach(
        self,
        attach_arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        on_attached: Any,
    ) -> int:
        if attach_arguments:
            raise CanonicalExecutorError(
                "Release artifact launch does not accept Flutter attach arguments"
            )
        if (
            self.startup_terminal_receipt is None
            or not self.startup_terminal_receipt.is_absolute()
            or self.startup_terminal_receipt.name != "startup-terminal.json"
            or self.startup_terminal_receipt.parent
            != self.launch_attempt_receipt.absolute().parent
        ):
            raise CanonicalExecutorError(
                "Release launch requires the canonical startup safe-terminal "
                "receipt in the launch attempt directory"
            )
        launch_attempt = self._bound_launch_attempt()
        try:
            safe_terminal = SafeTerminalTracker(
                required=True,
                receipt_path=self.startup_terminal_receipt,
                platform="android",
                launch_provenance=str(launch_attempt["launchProvenance"]),
                runtime_config_supply_mode=str(
                    launch_attempt["runtimeConfigSupplyMode"]
                ),
                launch_digest=str(launch_attempt["launchDigest"]),
            )
        except SafeTerminalIdentityError as error:
            raise CanonicalExecutorError(str(error)) from error

        deadline = time.monotonic() + timeout_seconds
        observed_lines: set[str] = set()
        while time.monotonic() < deadline:
            launch_attempt = self._bound_launch_attempt()
            try:
                terminal = safe_terminal.ready(launch_attempt)
                for line in self.startup_evidence_lines():
                    if line in observed_lines:
                        continue
                    observed_lines.add(line)
                    safe_terminal.observe(line, launch_attempt)
                    terminal = safe_terminal.ready(
                        self._bound_launch_attempt()
                    )
                    if terminal is not None:
                        break
            except (OSError, ValueError, SafeTerminalIdentityError) as error:
                raise CanonicalExecutorError(
                    f"startup safe-terminal receipt is invalid: {error}"
                ) from error
            if terminal is not None:
                attempt_id, evidence_digest, evidence_ref = terminal
                record_app_launch_attempt_observation(
                    self.launch_attempt_receipt,
                    configuration_state="complete",
                    startup_terminal_attempt_id=attempt_id,
                    startup_terminal_evidence_digest=evidence_digest,
                    startup_terminal_evidence_ref=evidence_ref,
                )
                _require_bound_startup_terminal(
                    read_app_launch_attempt(self.launch_attempt_receipt)
                )
                on_attached()
                return 0
            time.sleep(0.2)
        raise CanonicalExecutorError(
            "Release application cold startup safe-terminal receipt was not "
            "observed after canonical startup"
        )

    def _bound_launch_attempt(self) -> dict[str, Any]:
        launch_attempt = read_app_launch_attempt(self.launch_attempt_receipt)
        expected = {
            "platform": "android",
            "deviceId": self.device_id,
            "applicationId": self.application_id,
            "artifactDigest": self.release_artifact_digest,
        }
        if any(
            launch_attempt.get(field) != value
            for field, value in expected.items()
        ):
            raise CanonicalExecutorError(
                "Release startup safe-terminal launch attempt identity mismatch"
            )
        return launch_attempt

    def _verify_artifact(self) -> None:
        if _digest(self.release_artifact) != self.release_artifact_digest:
            raise CanonicalExecutorError(
                "exact Release artifact changed after build receipt validation"
            )


def _require_bound_startup_terminal(
    launch_attempt: dict[str, Any],
) -> dict[str, Any]:
    attempt_id = str(launch_attempt.get("startupTerminalAttemptId") or "")
    evidence_digest = str(
        launch_attempt.get("startupTerminalEvidenceDigest") or ""
    )
    evidence_ref = str(launch_attempt.get("startupTerminalEvidenceRef") or "")
    if not attempt_id or not evidence_digest or not evidence_ref:
        raise CanonicalExecutorError(
            "Release launch requires a bound startup safe-terminal receipt"
        )
    try:
        terminal = read_startup_terminal_receipt(
            Path(evidence_ref),
            launch_attempt=launch_attempt,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise CanonicalExecutorError(
            f"Release startup safe-terminal receipt is invalid: {error}"
        ) from error
    if (
        terminal["startupAttemptId"] != attempt_id
        or canonical_document_digest(terminal) != evidence_digest
    ):
        raise CanonicalExecutorError(
            "Release startup safe-terminal receipt evidence identity mismatch"
        )
    return terminal


def _phase_emitter(receipt_path: Path):
    def emit(message: str) -> None:
        marker = "status="
        if marker not in message:
            return
        status = message.rsplit(marker, 1)[1].strip()
        if status == "launched":
            _require_bound_startup_terminal(
                read_app_launch_attempt(receipt_path)
            )
        transition_app_launch_attempt(receipt_path, status)
        if status == "configured":
            record_app_launch_attempt_observation(
                receipt_path,
                configuration_state="complete",
            )
        elif status == "launched":
            record_app_launch_attempt_observation(
                receipt_path,
                runtime_health_status="healthy",
                recovery_web_status="not_applicable",
            )

    return emit


def _failure_blocker(status: str) -> str:
    if status in {"prepared", "compiling"}:
        return "APP.LAUNCH.compile_failed"
    if status in {"compiled", "installing"}:
        return "APP.LAUNCH.install_failed"
    if status == "installed":
        return "APP.LAUNCH.runtime_config_missing"
    if status == "configuring":
        return "APP.LAUNCH.runtime_config_activation_failed"
    return "APP.LAUNCH.launch_failed"


def _settle_release_interruption(receipt: Path) -> None:
    if not receipt.is_file():
        return
    current = read_app_launch_attempt(receipt)
    status = str(current["status"])
    if status in {"failed", "runtime_degraded", "stopped"}:
        return
    if status == "launched":
        transition_app_launch_attempt(receipt, "stopped")
        return
    transition_app_launch_attempt(
        receipt,
        "failed",
        first_blocker=_failure_blocker(status),
    )


def _execute_release_attempt(
    args: argparse.Namespace,
    inputs: ReleaseLaunchInputs,
) -> int:

    identity_refs = [
        (
            f"app-artifact-build-receipt:{inputs.build_receipt_path}"
            f"#{_digest(inputs.build_receipt_path)}"
        ),
        (
            f"app-launcher-handoff:{inputs.handoff_path}"
            f"#{_digest(inputs.handoff_path)}"
        ),
    ]
    if args.log_ref:
        identity_refs.append(args.log_ref)
    create_app_launch_attempt(
        args.receipt,
        environment="prod",
        target="prod-sim",
        platform=args.platform,
        build_profile=str(inputs.manifest["buildProfile"]),
        build_mode=str(inputs.manifest["buildMode"]),
        run_mode="release-artifact",
        launch_provenance=str(inputs.handoff["launchProvenance"]),
        runtime_config_supply_mode=str(
            inputs.handoff["runtimeConfigSupplyMode"]
        ),
        runtime_config_trust_envelope_digest=str(
            inputs.handoff["runtimeConfigTrustEnvelopeDigest"]
        ),
        runtime_config_package_digest=str(
            inputs.handoff["runtimeConfigPackageDigest"]
        ),
        application_id=str(inputs.manifest["applicationId"]),
        flutter_version=str(inputs.build_receipt["flutterVersion"]),
        command_resolution_digest=str(
            inputs.build_receipt["commandResolutionDigest"]
        ),
        device_id=args.device,
        artifact_digest=str(inputs.manifest["artifactDigest"]),
        launch_digest=str(inputs.handoff["effectiveLaunchManifestDigest"]),
        log_refs=identity_refs,
        non_promotable=True,
    )
    transition_app_launch_attempt(args.receipt, "compiling")
    startup_terminal_value = os.environ.get(
        "QWQ_APP_STARTUP_TERMINAL_RECEIPT", ""
    ).strip()
    startup_terminal_receipt = (
        Path(startup_terminal_value)
        if startup_terminal_value
        else args.receipt.absolute().with_name("startup-terminal.json")
    )
    os.environ["QWQ_APP_STARTUP_TERMINAL_RECEIPT"] = str(
        startup_terminal_receipt
    )
    driver = ReleaseAndroidPlatformDriver(
        device_id=args.device,
        application_id=str(inputs.manifest["applicationId"]),
        entrypoint=str(inputs.handoff["entrypoint"]),
        artifact=inputs.artifact,
        artifact_digest=str(inputs.manifest["artifactDigest"]),
        launch_attempt_receipt=args.receipt,
        startup_terminal_receipt=startup_terminal_receipt,
    )
    executor = CanonicalLaunchExecutor(
        handoff=inputs.handoff,
        platform_driver=driver,
        inherited_environment=os.environ,
        attach_arguments=(),
        activation_timeout_seconds=args.activation_timeout_seconds,
        attach_timeout_seconds=args.launch_timeout_seconds,
        emit=_phase_emitter(args.receipt),
    )
    try:
        exit_code = executor.execute()
    except (CanonicalExecutorError, OSError, ValueError) as error:
        current = read_app_launch_attempt(args.receipt)
        blocker = _failure_blocker(str(current["status"]))
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=blocker,
        )
        print(f"{blocker}: {error}", file=sys.stderr)
        return 2
    if exit_code != 0:
        current = read_app_launch_attempt(args.receipt)
        blocker = _failure_blocker(str(current["status"]))
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=blocker,
        )
        return exit_code
    attempt = read_app_launch_attempt(args.receipt)
    print(
        json.dumps(
            {
                "attemptId": attempt["attemptId"],
                "receipt": str(args.receipt),
                "artifact": str(inputs.artifact),
                "artifactDigest": inputs.manifest["artifactDigest"],
                "buildAttemptId": inputs.build_receipt["attemptId"],
                "buildReceipt": str(inputs.build_receipt_path),
                "launcherHandoff": str(inputs.handoff_path),
                "launchDigest": inputs.handoff[
                    "effectiveLaunchManifestDigest"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    args = _parser().parse_args()
    try:
        inputs = _load_inputs(
            args.manifest,
            args.platform,
            args.launcher_handoff,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2

    handled_signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous_handlers: dict[int, Any] = {}

    def interrupt(signum: int, _frame: object) -> None:
        raise _ReleaseLaunchInterrupted(signum)

    for signum in handled_signals:
        previous_handlers[signum] = signal.signal(signum, interrupt)
    try:
        return _execute_release_attempt(args, inputs)
    except _ReleaseLaunchInterrupted as interrupted:
        try:
            _settle_release_interruption(args.receipt)
        except (OSError, ValueError) as error:
            print(
                "APP.LAUNCH.receipt_unreadable: Release interruption could not "
                f"settle the attempt: {error}",
                file=sys.stderr,
            )
            return 2
        print(
            "APP.LAUNCH.launch interrupted and receipt settled "
            f"(signal={interrupted.signum})",
            file=sys.stderr,
        )
        return 130
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)


if __name__ == "__main__":
    raise SystemExit(main())
