"""Execute the canonical Android or iOS launch phase for app-content UAT."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    COCOAPODS_ENVIRONMENT_KEYS,
    cocoapods_environment,
    resolve_cocoapods_identity,
)

IOS_DIRECT_FLUTTER_TIMEOUT_BLOCKER = "APP.LAUNCH.receipt_timeout"
IOS_DIRECT_FLUTTER_TIMEOUT_CLASS = "flutter_process_timeout_before_native_launch"
IOS_DIRECT_FLUTTER_RECEIPT_BLOCKER = "APP.LAUNCH.receipt_invalid"


def _ios_direct_flutter_failure_projection(
    *,
    evidence: Mapping[str, Any],
    binding_issue: str,
) -> dict[str, Any]:
    """Retain literal runner evidence and assign one deterministic failure class."""

    flutter_exit_code = evidence.get("flutterRunExitCode")
    native_launch_count = evidence.get("nativeDidFinishLaunchingCount")
    runtime_snapshots = evidence.get("runtimeIdentitySnapshots")
    if (
        flutter_exit_code is None
        and native_launch_count == 0
        and runtime_snapshots == []
    ):
        first_blocker = IOS_DIRECT_FLUTTER_TIMEOUT_BLOCKER
        failure_class = IOS_DIRECT_FLUTTER_TIMEOUT_CLASS
    else:
        first_blocker = IOS_DIRECT_FLUTTER_RECEIPT_BLOCKER
        failure_class = (
            "launch_binding_invalid"
            if binding_issue
            else "literal_flutter_run_report_invalid"
        )
    raw_issues = evidence.get("issues")
    return {
        "firstBlocker": first_blocker,
        "failureClass": failure_class,
        "reportRef": str(evidence.get("reportPath") or ""),
        "flutterRunLogRef": str(evidence.get("flutterRunLog") or ""),
        "iosStartupLogRef": str(evidence.get("iosStartupLog") or ""),
        "flutterProcessGroupId": evidence.get("flutterProcessGroupId"),
        "flutterProcessGroupStoppedBySigint": evidence.get(
            "flutterProcessGroupStoppedBySigint"
        ),
        "flutterRunExitCode": flutter_exit_code,
        "nativeDidFinishLaunchingCount": native_launch_count,
        "runtimeIdentitySnapshots": runtime_snapshots,
        "issues": list(raw_issues) if isinstance(raw_issues, list) else [],
        "bindingIssue": binding_issue,
    }


def execute_canonical_platform_launch(
    *,
    args: Any,
    stackctl: Any,
    environment: str,
    target: str,
    device_id: str,
    launch_attempt_path: Path,
    launch_report_path: Path,
    launch_control: Mapping[str, Any],
    canonical_output_root: Path,
    launch_app_root: Path,
    runtime_binding: Mapping[str, Any],
    launch_projection: Mapping[str, Any],
    build_projection_policy_id: str,
    report_dir: Path,
    issues: list[str],
    runs: list[dict[str, Any]],
    launch_bindings: dict[str, dict[str, Any]],
    canonical_launch_command: Callable[..., tuple[list[str], dict[str, str]]],
    launch_binding_reader: Callable[..., dict[str, Any]],
    write_launch_control: Callable[..., dict[str, Any]],
) -> bool:
    if args.platform in {"android", "android-physical", "ios-physical"}:
        canonical_command, canonical_environment = (
            canonical_launch_command(
                environment=environment,
                target=target,
                device_id=device_id,
                attempt_path=launch_attempt_path,
                report_path=launch_report_path,
                output_root=canonical_output_root,
                app_root=launch_app_root,
                launch_control=launch_control,
            )
        )
        if bool(getattr(args, "dry_run", False)):
            runs.append(
                {
                    "target": target,
                    "suite": "canonical-launch",
                    "exitCode": 0,
                    "reportRef": "",
                    "status": "planned",
                    "launchProvenance": "canonical_launcher",
                }
            )
        else:
            canonical_execution_lock = None
            try:
                canonical_execution_lock = (
                    stackctl.acquire_patrol_execution_lock(
                        env_name=target,
                        target=f"canonical-launch:{device_id}",
                    )
                )
                canonical_result = stackctl.run(
                    canonical_command,
                    cwd=launch_app_root,
                    env=canonical_environment,
                )
            except RuntimeError as exc:
                issues.append(f"{target}: {exc}")
                return False
            finally:
                if canonical_execution_lock is not None:
                    canonical_execution_lock.close()
            canonical_binding: dict[str, str] = {}
            canonical_binding_issue = ""
            if canonical_result.returncode == 0:
                try:
                    canonical_binding = launch_binding_reader(
                        runtime_binding=runtime_binding,
                        report_ref=launch_report_path,
                        attempt_ref=launch_attempt_path,
                        platform=str(args.platform),
                        device_id=device_id,
                        launch_provenance="canonical_launcher",
                        launch_projection=launch_projection,
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    canonical_binding_issue = str(exc)
            runs.append(
                {
                    "target": target,
                    "suite": "canonical-launch",
                    "exitCode": (
                        1
                        if canonical_binding_issue
                        else canonical_result.returncode
                    ),
                    "reportRef": str(launch_report_path),
                    "launchProvenance": "canonical_launcher",
                    "launchBinding": canonical_binding,
                }
            )
            if canonical_result.returncode != 0 or canonical_binding_issue:
                detail = (
                    canonical_binding_issue
                    or canonical_result.stderr
                    or canonical_result.stdout
                ).strip()
                issues.append(
                    f"{target}: canonical {args.platform} launch failed: "
                    + (
                        detail[:800]
                        if detail
                        else f"exit={canonical_result.returncode}"
                    )
                )
                return False
            launch_bindings[target] = canonical_binding
    elif args.platform == "ios-simulator":
        direct_command = [
            sys.executable,
            str(
                launch_app_root
                / "scripts/device/verify_ios_hot_restart.py"
            ),
            "--env",
            environment,
            "--device-id",
            device_id,
            "--launch-provenance",
            "workspace_flutter_run",
            "--run-mode",
            "content-live",
            # app-content-uat covers dependency capsule
            # verification/projection, offline replay, and cold
            # compilation. The measured canonical path can exceed
            # 15 minutes, so this evidence run needs a private
            # ready-wait budget.
            "--ready-timeout-seconds",
            "1800",
            # Only the native observation of the cold terminal gets
            # this page-UAT allowance. Dart-reported cold and all hot
            # restart terminal budgets remain the canonical 6000ms.
            "--max-cold-native-safe-terminal-ms",
            "12000",
            "--output-dir",
            str(report_dir / target / "workspace-flutter-run"),
        ]
        if bool(getattr(args, "dry_run", False)):
            direct_command.append("--preflight-only")
        direct_environment = {
            "QWQ_OUTPUT_ROOT": str(canonical_output_root),
            "QWQ_CANONICAL_LAUNCH_ACTOR": "app-content-uat",
            "QWQ_APP_LAUNCH_RECEIPT": str(launch_attempt_path),
            "QWQ_APP_TEST_LIVE_REPORT": str(launch_report_path),
            "QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST": launch_control.get(
                "sourceCapsuleManifestRef", ""
            ),
            "QWQ_CANONICAL_LAUNCH_CONTROL": launch_control.get(
                "controlRef", ""
            ),
            "QWQ_CANONICAL_LAUNCH_CONTROL_DIGEST": launch_control.get(
                "controlDigest", ""
            ),
            "QWQ_APP_STARTUP_TERMINAL_RECEIPT": launch_control.get(
                "startupTerminalReceiptRef", ""
            ),
        }
        direct_execution_lock = None
        try:
            if not bool(getattr(args, "dry_run", False)):
                declared_cocoapods_environment = {
                    key: str(os.environ.get(key) or "").strip()
                    for key in COCOAPODS_ENVIRONMENT_KEYS
                }
                declared_cocoapods_keys = {
                    key
                    for key, value in declared_cocoapods_environment.items()
                    if value
                }
                if declared_cocoapods_keys and declared_cocoapods_keys != set(
                    COCOAPODS_ENVIRONMENT_KEYS
                ):
                    raise ValueError(
                        "APP.DEPENDENCY.cocoapods_mixed: parent CocoaPods "
                        "identity is incomplete"
                    )
                cocoapods_identity = resolve_cocoapods_identity(
                    declared_cocoapods_environment[
                        "QWQ_COCOAPODS_EXECUTABLE"
                    ],
                    search_path=str(os.environ.get("PATH") or ""),
                )
                if (
                    declared_cocoapods_keys
                    and cocoapods_identity.as_environment()
                    != declared_cocoapods_environment
                ):
                    raise ValueError(
                        "APP.DEPENDENCY.cocoapods_mixed: parent CocoaPods "
                        "identity differs from the resolved executable"
                    )
                resolved_cocoapods_environment = cocoapods_environment(
                    cocoapods_identity,
                    base=os.environ,
                )
                frozen_cocoapods_environment: Mapping[str, str] = (
                    MappingProxyType(
                        {
                            "PATH": resolved_cocoapods_environment["PATH"],
                            **{
                                key: resolved_cocoapods_environment[key]
                                for key in COCOAPODS_ENVIRONMENT_KEYS
                            },
                        }
                    )
                )
                direct_environment = {
                    **direct_environment,
                    **frozen_cocoapods_environment,
                }
                direct_execution_lock = stackctl.acquire_patrol_execution_lock(
                    env_name=target,
                    target=f"workspace-flutter-run:{device_id}",
                )
            direct_result = stackctl.run(
                direct_command,
                cwd=launch_app_root,
                env=direct_environment,
            )
            try:
                direct_evidence = json.loads(direct_result.stdout)
            except json.JSONDecodeError:
                direct_evidence = {}
            direct_retry_reports: list[str] = []
            if (
                direct_result.returncode != 0
                and isinstance(direct_evidence, dict)
                and stackctl._ios_direct_flutter_log_reader_retryable(
                    direct_evidence
                )
            ):
                direct_retry_reports.append(
                    str(direct_evidence.get("reportPath") or "")
                )
                first_launch_binding = launch_binding_reader(
                    runtime_binding=runtime_binding,
                    report_ref=launch_report_path,
                    attempt_ref=launch_attempt_path,
                    platform="ios-simulator",
                    device_id=device_id,
                    launch_provenance="workspace_flutter_run",
                    launch_projection=launch_projection,
                )
                launch_attempt_path = (
                    report_dir
                    / target
                    / "canonical-launch"
                    / "attempt-2"
                    / "attempt.json"
                )
                launch_report_path = launch_attempt_path.with_name(
                    "report.json"
                )
                launch_terminal_path = launch_attempt_path.with_name(
                    "startup-terminal.json"
                )
                launch_control = write_launch_control(
                    runtime_binding=runtime_binding,
                    projection=launch_projection,
                    output_root=canonical_output_root,
                    control_path=launch_attempt_path.with_name(
                        "control.json"
                    ),
                    attempt_path=launch_attempt_path,
                    report_path=launch_report_path,
                    terminal_receipt_path=launch_terminal_path,
                    platform=str(args.platform),
                    device_id=device_id,
                    build_projection_policy_id=(
                        build_projection_policy_id
                    ),
                    build_projection_seal_path=(
                        launch_attempt_path.with_name(
                            "build-projection-seal.json"
                        )
                    ),
                    expected_build_projection_digest=str(
                        first_launch_binding["buildProjectionSeal"][
                            "buildProjectionDigest"
                        ]
                    ),
                )
                direct_environment = {
                    **direct_environment,
                    "QWQ_APP_LAUNCH_RECEIPT": str(launch_attempt_path),
                    "QWQ_APP_TEST_LIVE_REPORT": str(launch_report_path),
                    "QWQ_CANONICAL_LAUNCH_CONTROL": launch_control[
                        "controlRef"
                    ],
                    "QWQ_CANONICAL_LAUNCH_CONTROL_DIGEST": (
                        launch_control["controlDigest"]
                    ),
                    "QWQ_APP_STARTUP_TERMINAL_RECEIPT": launch_control[
                        "startupTerminalReceiptRef"
                    ],
                }
                direct_result = stackctl.run(
                    direct_command,
                    cwd=launch_app_root,
                    env=direct_environment,
                )
                try:
                    direct_evidence = json.loads(direct_result.stdout)
                except json.JSONDecodeError:
                    direct_evidence = {}
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            issues.append(f"{target}: {exc}")
            return False
        finally:
            if direct_execution_lock is not None:
                direct_execution_lock.close()
        direct_binding: dict[str, str] = {}
        direct_binding_issue = ""
        if (
            direct_result.returncode == 0
            and not bool(getattr(args, "dry_run", False))
        ):
            try:
                direct_binding = launch_binding_reader(
                    runtime_binding=runtime_binding,
                    report_ref=launch_report_path,
                    attempt_ref=launch_attempt_path,
                    platform="ios-simulator",
                    device_id=device_id,
                    launch_provenance="workspace_flutter_run",
                    launch_projection=launch_projection,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                direct_binding_issue = str(exc)
            snapshots = direct_evidence.get("runtimeIdentitySnapshots")
            if not direct_binding_issue and (
                not isinstance(snapshots, list)
                or not snapshots
                or any(
                    not isinstance(snapshot, Mapping)
                    or snapshot.get("runtimeConfigDigest")
                    != direct_binding.get("runtimeConfigPackageDigest")
                    or snapshot.get("effectiveLaunchManifestDigest")
                    != direct_binding.get("effectiveLaunchManifestDigest")
                    for snapshot in snapshots
                )
            ):
                direct_binding_issue = (
                    "installed iOS runtime readback differs from launch attempt"
                )
        direct_passed = (
            direct_result.returncode == 0
            and isinstance(direct_evidence, dict)
            and direct_evidence.get("status") == "passed"
            and direct_evidence.get("launchProvenance")
            == "workspace_flutter_run"
            and direct_evidence.get("runtimeConfigSupplyMode")
            == "external_runtime_package"
            and stackctl._DATA_READINESS_DIGEST_RE.fullmatch(
                str(direct_evidence.get("consumerLeaseId") or "")
            )
            is not None
            and not direct_binding_issue
        )
        direct_failure_evidence = (
            {}
            if direct_passed
            else _ios_direct_flutter_failure_projection(
                evidence=direct_evidence,
                binding_issue=direct_binding_issue,
            )
        )
        run_payload = {
            "target": target,
            "suite": "workspace-flutter-run",
            "status": "passed" if direct_passed else "failed",
            "exitCode": (
                1 if direct_binding_issue else direct_result.returncode
            ),
            "reportRef": str(direct_evidence.get("reportPath") or ""),
            "launchProvenance": direct_evidence.get(
                "launchProvenance"
            ),
            "runtimeConfigSupplyMode": direct_evidence.get(
                "runtimeConfigSupplyMode"
            ),
            "consumerLeaseId": direct_evidence.get("consumerLeaseId"),
            "attempts": direct_evidence.get("attempts", []),
            "retryCount": len(direct_retry_reports),
            "supersededFailedReportRefs": direct_retry_reports,
            "launchBinding": direct_binding,
        }
        if direct_failure_evidence:
            run_payload.update(
                {
                    "firstBlocker": direct_failure_evidence["firstBlocker"],
                    "failureClass": direct_failure_evidence["failureClass"],
                    "failureEvidence": direct_failure_evidence,
                }
            )
        runs.append(run_payload)
        if not direct_passed:
            if direct_failure_evidence:
                detail = json.dumps(
                    direct_failure_evidence,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            else:
                detail = (
                    direct_binding_issue
                    or direct_result.stderr
                    or direct_result.stdout
                ).strip()
            issues.append(
                f"{target}: literal flutter run failed: "
                + (detail if detail else "typed report is incomplete")
            )
            return False
        if not bool(getattr(args, "dry_run", False)):
            launch_bindings[target] = direct_binding
    # Patrol uninstalls its credential-bearing test package by design;
    # the immediately adjacent launch above therefore owns the exact
    # compile/install/activation/AppArtifact identity, while Patrol owns
    # the release-bound page journeys that follow.
    return True
