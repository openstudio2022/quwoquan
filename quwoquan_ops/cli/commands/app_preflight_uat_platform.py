"""Execute the canonical Android or iOS launch phase for app-content UAT."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


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
    android_launch_command: Callable[..., tuple[list[str], dict[str, str]]],
    launch_binding_reader: Callable[..., dict[str, Any]],
    write_launch_control: Callable[..., dict[str, Any]],
) -> bool:
    if args.platform == "android":
        android_command, android_environment = (
            android_launch_command(
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
            android_execution_lock = None
            try:
                android_execution_lock = (
                    stackctl.acquire_patrol_execution_lock(
                        env_name=target,
                        target=f"canonical-launch:{device_id}",
                    )
                )
                android_result = stackctl.run(
                    android_command,
                    cwd=launch_app_root,
                    env=android_environment,
                )
            except RuntimeError as exc:
                issues.append(f"{target}: {exc}")
                return False
            finally:
                if android_execution_lock is not None:
                    android_execution_lock.close()
            android_binding: dict[str, str] = {}
            android_binding_issue = ""
            if android_result.returncode == 0:
                try:
                    android_binding = launch_binding_reader(
                        runtime_binding=runtime_binding,
                        report_ref=launch_report_path,
                        attempt_ref=launch_attempt_path,
                        platform="android",
                        device_id=device_id,
                        launch_provenance="canonical_launcher",
                        launch_projection=launch_projection,
                    )
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    android_binding_issue = str(exc)
            runs.append(
                {
                    "target": target,
                    "suite": "canonical-launch",
                    "exitCode": (
                        1
                        if android_binding_issue
                        else android_result.returncode
                    ),
                    "reportRef": str(launch_report_path),
                    "launchProvenance": "canonical_launcher",
                    "launchBinding": android_binding,
                }
            )
            if android_result.returncode != 0 or android_binding_issue:
                detail = (
                    android_binding_issue
                    or android_result.stderr
                    or android_result.stdout
                ).strip()
                issues.append(
                    f"{target}: canonical Android launch failed: "
                    + (
                        detail[:800]
                        if detail
                        else f"exit={android_result.returncode}"
                    )
                )
                return False
            launch_bindings[target] = android_binding
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
            "--launch-surface",
            "workspace_flutter_run",
            # app-content-uat cold compile includes the current tree's
            # frontend and Xcode build; observed builds exceed seven
            # minutes, so this one evidence run needs a private budget.
            "--ready-timeout-seconds",
            "900",
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
                    "QWQ_OUTPUT_ROOT": str(canonical_output_root),
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
        runs.append(
            {
                "target": target,
                "suite": "workspace-flutter-run",
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
        )
        if not direct_passed:
            detail = (
                direct_binding_issue
                or direct_result.stderr
                or direct_result.stdout
            ).strip()
            issues.append(
                f"{target}: literal flutter run failed: "
                + (detail[:800] if detail else "typed report is incomplete")
            )
            return False
        if not bool(getattr(args, "dry_run", False)):
            launch_bindings[target] = direct_binding
    # Patrol uninstalls its credential-bearing test package by design;
    # the immediately adjacent launch above therefore owns the exact
    # compile/install/activation/AppArtifact identity, while Patrol owns
    # the release-bound page journeys that follow.
    return True
