"""CLI 入口：main 编排（设备矩阵、证据采集、报告落盘）与 write_report。"""
from __future__ import annotations

import atexit
import base64
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.device_matrix.evidence import (
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)
from quwoquan_ops.cli.lib.local_controlled_edge_fault import (
    CONTROLLED_EDGE_SERVICES,
    ControlledEdgeFault,
    begin_controlled_edge_fault,
)
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    release_consumer_lease,
)
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    acquire_local_runtime_use_lock,
)
from quwoquan_ops.cli.lib.patrol_cli import resolve_patrol_cli

# PATROL_EXECUTION_LOCK 是原入口的历史 import，运行时无调用点；随包保留。
from quwoquan_ops.cli.lib.patrol_execution_lock import (
    PATROL_EXECUTION_LOCK,  # noqa: F401
)
from quwoquan_ops.cli.lib.patrol_execution_lock import (
    acquire_patrol_execution_lock as _acquire_patrol_execution_lock,
)

from . import artifact_binding_report, host_activation
from .cli_args import (
    _load_release_uat_cases_b64,
    _redact_command,
    parse_args,
)
from .constants import (
    CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX,
    PATROL_HOST_DIR,
    REPO_ROOT,
    RUNTIME_RECOVERY_EVIDENCE_FIELDS,
    utc_now,
)
from .device_runtime import (
    _acquire_patrol_consumer_lease,
    _bind_patrol_consumer_lease_to_handoff,
    _device_command_env,
    _local_tls_trust_evidence,
    _prepare_android_local_port_reverse,
    _reset_release_uat_device_state,
)
from .devices import (
    discover_devices,
    dry_run_devices,
    ensure_patrol_ios_products_bridge,
)
from .evidence import (
    _AppContentPageScreenshotCapture,
    _apply_feed_content_evidence_gate,
    _device_evidence_stream,
    _output_evidence_ref,
    _read_account_enforcement_evidence,
    _read_controlled_edge_fault_evidence,
    _read_feed_content_evidence,
    _read_runtime_recovery_evidence,
    _read_video_playback_evidence,
    _structured_evidence_log_path,
    _validate_account_enforcement_device_matrix,
    _validate_runtime_recovery_device_matrix,
    load_remote_api_evidence,
)
from .execution import (
    _first_typed_patrol_blocker,
    apply_patrol_test_execution_summary,
    run_command,
)
from .external_aut_entry import (
    decode_external_aut_request,
    external_aut_case_result,
    record_external_aut_journey,
    validate_external_aut_device_count,
)
from .handoff import (
    _apply_launcher_handoff_to_command_env,
    _provider_patrol_launcher_handoff,
    _validated_provider_patrol_runtime_identity,
)
from .report_state import finish_report, new_report, write_report
from .request_validation import static_request_issue
from .session import (
    TypedTestDataActor,
    TypedTestDataConversation,
    _account_enforcement_phase,
    _is_account_enforcement_target,
    _is_controlled_edge_fault_target,
    _is_local_target,
    _is_runtime_recovery_target,
    _local_target_for_environment_alias,
    _missing_required_args,
    _prepare_execution_session,
    _requires_typed_test_data_conversation,
    _requires_video_playback_canary,
    _resolved_owner_id,
    _resolved_persona_id,
    _runtime_env_for_alias,
    _typed_test_data_conversation_from_environment,
    _uses_persisted_device_session,
    _uses_runtime_anonymous_session,
    _validate_video_playback_canary_work_id,
)
from .wrapper import (
    _cleanup_patrol_target_wrapper,
    _create_patrol_secret_define_file,
    _create_patrol_target_wrapper,
    _patrol_bundler_target,
    _provider_uat_secret_values,
    _purge_typed_actor_credential_artifacts,
    patrol_command,
)


def main() -> int:
    args = parse_args()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    execution_lock = None
    runtime_use_lock = None
    if not args.dry_run:
        try:
            execution_lock = _acquire_patrol_execution_lock(
                env_name=args.env_name,
                target=args.target,
            )
            atexit.register(execution_lock.close)
            if _is_local_target(args.env_name):
                runtime_use_lock = acquire_local_runtime_use_lock(
                    target=_local_target_for_environment_alias(args.env_name),
                    purpose="environment-patrol-smoke",
                )
                atexit.register(runtime_use_lock.close)
        except RuntimeError as exc:
            if runtime_use_lock is not None:
                runtime_use_lock.close()
            if execution_lock is not None:
                execution_lock.close()
            print(f"GATE_BLOCK: {exc}", file=sys.stderr)
            return 2

    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    api_contract_env = args.api_contract_env.strip() or runtime_env
    (
        external_aut_required,
        external_aut_canonical_binding,
        external_aut_decode_error,
    ) = decode_external_aut_request(args)
    report = new_report(
        args=args,
        runtime_env=runtime_env,
        api_contract_env=api_contract_env,
        external_aut_required=external_aut_required,
    )
    if external_aut_decode_error is not None:
        return finish_report(
            report_path,
            report,
            status="gate_block",
            reason=external_aut_decode_error,
            exit_code=2,
        )
    request_issue = static_request_issue(
        args,
        runtime_env=runtime_env,
        api_contract_env=api_contract_env,
        candidate_digest=report["candidateDigest"],
    )
    if request_issue:
        return finish_report(
            report_path,
            report,
            status="gate_block",
            reason=request_issue,
            exit_code=2,
        )
    try:
        report["remoteApiEvidence"] = load_remote_api_evidence(
            str(getattr(args, "remote_api_evidence_report", "") or "")
        )
    except ValueError as exc:
        return finish_report(
            report_path, report, status="gate_block", reason=exc, exit_code=2
        )
    typed_conversation: TypedTestDataConversation | None = None
    if not args.dry_run:
        try:
            report["sessionSource"] = _prepare_execution_session(args)
            typed_conversation = _typed_test_data_conversation_from_environment()
            conversation_required = _requires_typed_test_data_conversation(args)
            if conversation_required and typed_conversation is None:
                raise ValueError(
                    "typed message UAT requires a stackctl TestDataSession "
                    "conversation handoff"
                )
            if not conversation_required and typed_conversation is not None:
                raise ValueError(
                    "typed test-data conversation handoff is not valid for this target"
                )
        except Exception as exc:  # noqa: BLE001
            return finish_report(
                report_path, report, status="gate_block", reason=exc, exit_code=2
            )
        report["hasCurrentOwnerIdentity"] = bool(_resolved_owner_id(args))
        report["hasCurrentPersonaIdentity"] = bool(
            _resolved_persona_id(args)
        )
    else:
        report["sessionSource"] = "dry_run"
    patrol_resolution = resolve_patrol_cli()
    patrol_executable = patrol_resolution.executable or "patrol"
    report["patrolCli"] = patrol_resolution.as_report(required=not args.dry_run)

    if args.release_uat_cases:
        try:
            args.release_uat_cases_b64 = _load_release_uat_cases_b64(args.release_uat_cases)
        except ValueError as exc:
            return finish_report(
                report_path, report, status="gate_block", reason=exc, exit_code=2
            )
        report["releaseUatCasesPath"] = _output_evidence_ref(Path(args.release_uat_cases).expanduser())
    else:
        args.release_uat_cases_b64 = ""

    if not args.dry_run:
        if patrol_resolution.executable is None:
            return finish_report(
                report_path,
                report,
                status="gate_block",
                reason=patrol_resolution.error,
                exit_code=2,
            )
        missing = _missing_required_args(args)
        if missing:
            return finish_report(
                report_path,
                report,
                status="gate_block",
                reason=f"missing required args: {', '.join(missing)}",
                exit_code=2,
            )
        if _requires_video_playback_canary(args):
            try:
                args.video_playback_canary_work_id = (
                    _validate_video_playback_canary_work_id(args, runtime_env)
                )
            except ValueError as exc:
                return finish_report(
                    report_path,
                    report,
                    status="gate_block",
                    reason=exc,
                    exit_code=2,
                )
    try:
        devices = dry_run_devices(args) if args.dry_run else discover_devices(args.platform, args.device_id)
    except Exception as exc:  # noqa: BLE001
        return finish_report(
            report_path, report, status="failed", reason=exc, exit_code=1
        )

    if not devices:
        return finish_report(
            report_path,
            report,
            status="gate_block",
            reason="no mobile Flutter devices available on self-hosted Mac runner",
            exit_code=2,
        )
    try:
        validate_external_aut_device_count(
            required=external_aut_required, devices=devices
        )
        _validate_runtime_recovery_device_matrix(args, devices)
        _validate_account_enforcement_device_matrix(args, devices)
    except RuntimeError as exc:
        return finish_report(
            report_path,
            report,
            status="gate_block",
            reason=exc,
            exit_code=2,
            devices=devices,
        )

    report["devices"] = devices
    evidence_root = report_path.parent / "runs"
    report["evidenceRoot"] = repo_relative(evidence_root)
    report["deviceInventoryPath"] = write_discovered_devices_snapshot(
        report_path.parent / "discovered_devices.json",
        devices,
        suite="environment-page-smoke",
        requested_environments=[args.env_name],
        extra={
            "target": args.target,
            "runtimeEnv": runtime_env,
            "platform": args.platform,
            "reportPath": repo_relative(report_path),
        },
    )
    failed = False
    gate_blocked = False
    for device in devices:
        run_dir = evidence_root / sanitize_device_id(str(device.get("id", "")))
        run_dir.mkdir(parents=True, exist_ok=True)
        device_manifest_path = write_device_manifest(
            run_dir / "device.json",
            device,
            env_name=args.env_name,
            suite="environment-page-smoke",
            extra={"target": args.target, "runtimeEnv": runtime_env},
        )
        if (
            not args.dry_run
            and str(device.get("targetPlatform", "")).lower() == "ios"
        ):
            ensure_patrol_ios_products_bridge()
        tls_trust = _local_tls_trust_evidence(dry_run=args.dry_run)
        android_port_reverse = {"status": "skipped", "reason": "not-required"}
        if (
            not args.dry_run
            and str(device.get("targetPlatform", "")).lower().startswith("android")
        ):
            try:
                android_port_reverse = _prepare_android_local_port_reverse(
                    args,
                    device,
                )
            except RuntimeError as exc:
                android_port_reverse = {
                    "status": "failed",
                    "reason": str(exc),
                }
                report["runs"].append(
                    {
                        "device": device,
                        "exitCode": 2,
                        "timedOut": False,
                        "durationMs": 0,
                        "outputSummary": str(exc),
                        "preflightFailed": True,
                        "evidence": {
                            "runDirectory": repo_relative(run_dir),
                            "deviceManifestPath": device_manifest_path,
                            "localTlsTrust": tls_trust,
                            "androidPortReverse": android_port_reverse,
                        },
                    }
                )
                failed = True
                gate_blocked = True
                continue
        try:
            release_uat_state_reset = _reset_release_uat_device_state(args, device)
        except RuntimeError as exc:
            release_uat_state_reset = {"status": "failed", "reason": str(exc)}
            report["runs"].append(
                {
                    "device": device,
                    "exitCode": 2,
                    "timedOut": False,
                    "durationMs": 0,
                    "outputSummary": str(exc),
                    "preflightFailed": True,
                    "evidence": {
                        "runDirectory": repo_relative(run_dir),
                        "deviceManifestPath": device_manifest_path,
                        "localTlsTrust": tls_trust,
                        "androidPortReverse": android_port_reverse,
                        "releaseUatStateReset": release_uat_state_reset,
                    },
                }
            )
            failed = True
            gate_blocked = True
            continue
        credential_artifact_cleanup: dict[str, Any] = {
            "status": "not-required",
            "removedFiles": 0,
        }
        secret_define_path: Path | None = None
        typed_actor = getattr(args, "_typed_test_data_actor", None)
        if typed_actor is not None and not isinstance(
            typed_actor,
            TypedTestDataActor,
        ):
            raise TypeError("typed test-data actor handoff is invalid")
        if args.dry_run:
            secret_define_path = run_dir / "dry-run-patrol-secrets.json"
        elif not (
            _uses_runtime_anonymous_session(args)
            or _uses_persisted_device_session(args)
            or typed_actor is not None
        ):
            secret_define_path = _create_patrol_secret_define_file(args)
        consumer_lease: tuple[str, str, str, str] | None = None
        patrol_wrapper_cleanup: Callable[[], None] | None = None
        try:
            command_env = _device_command_env(args, device)
            provider_runtime_identity = (
                _validated_provider_patrol_runtime_identity(
                    args,
                    command_env,
                )
            )
            launcher_handoff: dict[str, Any] | None = None
            if not args.dry_run:
                consumer_lease = _acquire_patrol_consumer_lease(
                    args,
                    device,
                    android_port_reverse,
                    command_env,
                )
                if runtime_env in {"alpha", "beta", "gamma"}:
                    launcher_handoff = _provider_patrol_launcher_handoff(
                        args,
                        device,
                        command_env,
                        runtime_identity=provider_runtime_identity,
                    )
                    if launcher_handoff is not None:
                        _apply_launcher_handoff_to_command_env(
                            command_env,
                            launcher_handoff,
                        )
                        if consumer_lease is not None:
                            _bind_patrol_consumer_lease_to_handoff(
                                args,
                                device,
                                consumer_lease,
                                command_env,
                                launcher_handoff,
                            )
                        # 与生产同构的两阶段冷启动：宿主先激活 runtime config，patrol test
                        # 随后的正常启动才读得到真实后端配置。
                        host_activation.ensure_patrol_host_runtime_config(
                            args, device, launcher_handoff, command_env, run_dir, report
                        )
            patrol_target = _patrol_bundler_target(args.target)
            if not args.dry_run:
                _, patrol_target, patrol_wrapper_cleanup = (
                    _create_patrol_target_wrapper(
                        args.target,
                        typed_actor=typed_actor,
                        typed_conversation=typed_conversation,
                    )
                )
            command = patrol_command(
                device,
                args,
                patrol_executable,
                dart_define_file=secret_define_path,
                launcher_handoff=launcher_handoff,
                patrol_target=patrol_target,
                typed_test_data_session_handoff=typed_actor is not None,
            )
            command_path = write_json(
                run_dir / "command.json",
                {
                    "capturedAt": utc_now(),
                    "target": args.target,
                    "deviceId": device["id"],
                    "command": _redact_command(command),
                    "environment": {},
                    "androidPortReverse": android_port_reverse,
                    "releaseUatStateReset": release_uat_state_reset,
                },
            )
            before_screenshot = (
                {"status": "skipped", "reason": "dry-run"}
                if args.dry_run
                else capture_device_screenshot(device, run_dir / "before.png")
            )
            print(
                f"[environment-page-smoke] run {args.env_name} on "
                f"{device['name']} ({device['id']}, {device['targetPlatform']})",
                flush=True,
            )
        except BaseException as exc:
            _cleanup_patrol_target_wrapper(patrol_wrapper_cleanup)
            if consumer_lease is not None:
                release_consumer_lease(
                    target=consumer_lease[0],
                    device=consumer_lease[1],
                    consumer=consumer_lease[2],
                )
            if secret_define_path is not None and not args.dry_run:
                secret_define_path.unlink(missing_ok=True)
            if not isinstance(exc, host_activation.PatrolHostActivationError):
                raise
            host_activation.record_patrol_host_activation_gate_block(
                exc, report, device, device_manifest_path,
                tls_trust, android_port_reverse, release_uat_state_reset,
            )
            failed = True
            gate_blocked = True
            continue
        if args.dry_run:
            log_path = run_dir / "patrol.log"
            log_path.write_text("dry-run\n", encoding="utf-8")
            result = {
                "command": _redact_command(command),
                "cwd": str(PATROL_HOST_DIR),
                "exitCode": 0,
                "timedOut": False,
                "durationMs": 0,
                "outputSummary": "dry-run",
                "logPath": repo_relative(log_path),
            }
            if bool(getattr(args, "stackctl_controlled_edge_fault", False)):
                report["controlledEdgeFault"]["receipt"] = {
                    "status": "planned",
                    "target": _local_target_for_environment_alias(args.env_name),
                    "services": list(CONTROLLED_EDGE_SERVICES),
                }
        else:
            controlled_fault: ControlledEdgeFault | None = None
            restore_request_count = 0
            restore_error = ""
            device_evidence_error = ""
            device_evidence_capture: dict[str, Any] = {
                "status": "not-required",
            }
            device_evidence_stream = None
            credential_cleanup_error = ""
            page_screenshot_capture = _AppContentPageScreenshotCapture(
                args=args,
                runtime_env=runtime_env,
                capture=lambda _device=device, _run_dir=run_dir: capture_device_screenshot(
                    _device,
                    _run_dir / "after.png",
                ),
            )

            def handle_controlled_edge_output(line: str) -> None:
                nonlocal restore_request_count
                marker = line.find(CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX)
                if marker < 0:
                    return
                encoded = line[
                    marker + len(CONTROLLED_EDGE_RESTORE_REQUEST_PREFIX) :
                ].strip()
                try:
                    payload = json.loads(encoded)
                except json.JSONDecodeError as error:
                    raise RuntimeError(
                        "controlled edge restore request is not valid JSON"
                    ) from error
                if (
                    not isinstance(payload, dict)
                    or payload.get("environment") != runtime_env
                    or payload.get("observed") is not True
                    or payload.get("blockedRetryCount") != 5
                ):
                    raise RuntimeError(
                        "controlled edge restore request identity is invalid"
                    )
                restore_request_count += 1
                if restore_request_count != 1 or controlled_fault is None:  # noqa: B023
                    raise RuntimeError(
                        "controlled edge restore request must occur exactly once"
                    )
                report["controlledEdgeFault"]["receipt"] = (
                    controlled_fault.restore()  # noqa: B023
                )

            def handle_device_evidence_output(line: str) -> None:
                page_screenshot_capture.handle_line(line)  # noqa: B023
                if controlled_fault is not None:  # noqa: B023
                    handle_controlled_edge_output(line)

            try:
                if bool(getattr(args, "stackctl_controlled_edge_fault", False)):
                    controlled_fault = begin_controlled_edge_fault(
                        _local_target_for_environment_alias(args.env_name)
                    )
                    report["controlledEdgeFault"]["receipt"] = (
                        controlled_fault.receipt()
                    )
                try:
                    device_evidence_stream = _device_evidence_stream(
                        device,
                        log_path=run_dir / "device-evidence.log",
                        output_line_handler=handle_device_evidence_output,
                    )
                    if device_evidence_stream is not None:
                        device_evidence_stream.start()
                    result = run_command(
                        command,
                        cwd=PATROL_HOST_DIR,
                        env=command_env,
                        timeout_seconds=args.timeout_seconds,
                        log_path=run_dir / "patrol.log",
                        secret_values=(
                            args.test_auth_token.strip(),
                            args.test_refresh_token.strip(),
                            _resolved_owner_id(args),
                            _resolved_persona_id(args),
                            *(
                                typed_conversation.artifact_values()
                                if typed_conversation is not None
                                else ()
                            ),
                            *_provider_uat_secret_values(),
                        ),
                        output_line_handler=(
                            handle_device_evidence_output
                            if device_evidence_stream is None
                            else None
                        ),
                    )
                except Exception as error:  # noqa: BLE001
                    result = {
                        "command": _redact_command(command),
                        "cwd": str(PATROL_HOST_DIR),
                        "exitCode": 2,
                        "timedOut": False,
                        "durationMs": 0,
                        "outputSummary": f"controlled edge UAT failed: {error}",
                        "logPath": repo_relative(run_dir / "patrol.log"),
                    }
            except Exception as error:  # noqa: BLE001
                result = {
                    "command": _redact_command(command),
                    "cwd": str(PATROL_HOST_DIR),
                    "exitCode": 2,
                    "timedOut": False,
                    "durationMs": 0,
                    "outputSummary": f"controlled edge setup failed: {error}",
                    "logPath": repo_relative(run_dir / "patrol.log"),
                }
            finally:
                tested_app_artifact_binding, artifact_binding_blocker = artifact_binding_report.attach_tested_app_artifact_binding(report, result, device, command, command_env, False)
                if artifact_binding_blocker:
                    failed = gate_blocked = True
                if device_evidence_stream is not None:
                    try:
                        device_evidence_capture = device_evidence_stream.stop()
                    except Exception as error:  # noqa: BLE001
                        device_evidence_error = str(error)
                        device_evidence_capture = {
                            "status": "failed",
                            "deviceId": str(device.get("id") or ""),
                            "logPath": repo_relative(
                                run_dir / "device-evidence.log"
                            ),
                            "reason": device_evidence_error,
                        }
                if controlled_fault is not None and not controlled_fault.restored:
                    try:
                        report["controlledEdgeFault"]["receipt"] = (
                            controlled_fault.restore()
                        )
                    except Exception as error:  # noqa: BLE001
                        restore_error = str(error)
                if consumer_lease is not None:
                    release_consumer_lease(
                        target=consumer_lease[0],
                        device=consumer_lease[1],
                        consumer=consumer_lease[2],
                    )
                if secret_define_path is not None:
                    secret_define_path.unlink(missing_ok=True)
                _cleanup_patrol_target_wrapper(patrol_wrapper_cleanup)
                typed_handoff_values = (
                    *(
                        typed_actor.secret_values()
                        if typed_actor is not None
                        else ()
                    ),
                    *(
                        typed_conversation.artifact_values()
                        if typed_conversation is not None
                        else ()
                    ),
                )
                generated_secret_values = tuple(
                    dict.fromkeys(
                        (
                            *typed_handoff_values,
                            *(
                                base64.b64encode(value.encode("utf-8")).decode(
                                    "ascii"
                                )
                                for value in typed_handoff_values
                            ),
                            *_provider_uat_secret_values(),
                        )
                    )
                )
                if generated_secret_values:
                    try:
                        credential_artifact_cleanup = {
                            "status": "passed",
                            "removedFiles": (
                                _purge_typed_actor_credential_artifacts(
                                    generated_secret_values
                                )
                            ),
                        }
                    except RuntimeError as error:
                        credential_cleanup_error = str(error)
                        credential_artifact_cleanup = {
                            "status": "failed",
                            "removedFiles": 0,
                        }
            if restore_error:
                result["exitCode"] = 2
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\ncontrolled edge fail-safe restore failed: "
                    + restore_error
                ).strip()
            if device_evidence_error:
                result["exitCode"] = 2
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\nexact-device evidence stream failed: "
                    + device_evidence_error
                ).strip()
            if controlled_fault is not None and restore_request_count != 1:
                result["exitCode"] = 1
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\ncontrolled edge UAT did not emit exactly one restore request"
                ).strip()
            if credential_cleanup_error:
                result["exitCode"] = 2
                result["outputSummary"] = (
                    str(result.get("outputSummary") or "")
                    + "\nPatrol credential artifact cleanup failed: "
                    + credential_cleanup_error
                ).strip()
        raw_log_path = run_dir / "patrol.log"
        structured_evidence_log_path = _structured_evidence_log_path(
            device,
            run_dir,
        )
        raw_log = (
            raw_log_path.read_text(encoding="utf-8")
            if raw_log_path.is_file()
            else ""
        )
        apply_patrol_test_execution_summary(
            result,
            raw_log,
            dry_run=args.dry_run,
        )
        patrol_typed_blocker = (
            _first_typed_patrol_blocker(raw_log)
            if result.get("patrolExitCode") != 0 and not args.dry_run
            else {}
        )
        if args.dry_run:
            tested_app_artifact_binding, artifact_binding_blocker = artifact_binding_report.attach_tested_app_artifact_binding(report, result, device, command, command_env, True)
        (
            external_aut_journey,
            external_aut_driver_result,
            external_aut_screenshot,
            external_aut_blocker,
            external_aut_gate_blocked,
        ) = record_external_aut_journey(
            required=external_aut_required,
            args=args,
            device=device,
            run_dir=run_dir,
            patrol_output=raw_log,
            canonical_binding=external_aut_canonical_binding,
            runtime_env=runtime_env,
            command_env=command_env,
            tested_app_artifact_binding=tested_app_artifact_binding,
            report=report,
            result=result,
        )
        if external_aut_gate_blocked:
            failed = gate_blocked = True
        typed_blocker = (
            patrol_typed_blocker
            or artifact_binding_blocker
            or external_aut_blocker
        )
        if args.dry_run:
            after_screenshot = {"status": "skipped", "reason": "dry-run"}
        else:
            page_screenshot_capture.apply_success_gate(result, dry_run=False)
            if page_screenshot_capture.required:
                after_screenshot = page_screenshot_capture.evidence
            else:
                after_screenshot = (
                    capture_device_screenshot(device, run_dir / "after.png")
                    if result["exitCode"] == 0
                    else {"status": "skipped", "reason": "command failed"}
                )
        failure_screenshot = (
            capture_device_screenshot(device, run_dir / "failure.png")
            if result["exitCode"] != 0 and not args.dry_run
            else {"status": "skipped", "reason": "command passed"}
        )
        result["device"] = device
        runtime_recovery_evidence = _read_runtime_recovery_evidence(
            structured_evidence_log_path,
        )
        feed_content_evidence = _read_feed_content_evidence(
            structured_evidence_log_path
        )
        controlled_edge_fault_evidence = _read_controlled_edge_fault_evidence(
            structured_evidence_log_path
        )
        controlled_edge_log = (
            structured_evidence_log_path.read_text(encoding="utf-8")
            if structured_evidence_log_path.is_file()
            else ""
        )
        controlled_edge_runtime_errors = [
            token
            for token in (
                "[bootstrap] source=zone_guarded exception=",
                "feed recovery did not leave blocking error",
            )
            if token in controlled_edge_log
        ]
        account_enforcement_phase = _account_enforcement_phase(args)
        account_enforcement_evidence = _read_account_enforcement_evidence(
            structured_evidence_log_path,
            phase=account_enforcement_phase,
            candidate_digest=report["candidateDigest"],
        )
        if _is_runtime_recovery_target(args) and (
            set(runtime_recovery_evidence) != RUNTIME_RECOVERY_EVIDENCE_FIELDS
            or not all(runtime_recovery_evidence.values())
        ):
            result["exitCode"] = 1
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\nruntime recovery UAT did not emit a complete passed evidence marker"
            ).strip()
        _apply_feed_content_evidence_gate(
            result,
            args,
            feed_content_evidence,
        )
        if _is_account_enforcement_target(args) and not account_enforcement_evidence:
            result["exitCode"] = 1
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\naccount-enforcement UAT did not emit its exact passed evidence marker"
            ).strip()
        controlled_edge_receipt = report["controlledEdgeFault"].get("receipt")
        if (
            _is_controlled_edge_fault_target(args)
            and bool(getattr(args, "stackctl_controlled_edge_fault", False))
            and not args.dry_run
            and (
                not controlled_edge_fault_evidence
                or not isinstance(controlled_edge_receipt, dict)
                or controlled_edge_receipt.get("status") != "restored"
                or bool(controlled_edge_runtime_errors)
            )
        ):
            result["exitCode"] = 1
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\ncontrolled edge UAT lacks complete copy and same-install recovery evidence"
                + (
                    "; forbidden runtime errors="
                    + ",".join(controlled_edge_runtime_errors)
                    if controlled_edge_runtime_errors
                    else ""
                )
            ).strip()
        result["evidence"] = {
            "runDirectory": repo_relative(run_dir),
            "deviceManifestPath": device_manifest_path,
            "commandPath": command_path,
            "rawLogPath": result.get("logPath", ""),
            "structuredEvidenceLogPath": repo_relative(
                structured_evidence_log_path
            ),
            "deviceEvidenceCapture": (
                device_evidence_capture
                if not args.dry_run
                else {"status": "skipped", "reason": "dry-run"}
            ),
            "videoPlayback": _read_video_playback_evidence(
                structured_evidence_log_path,
            ),
            "feedContent": feed_content_evidence,
            "controlledEdgeFault": controlled_edge_fault_evidence,
            "controlledEdgeFaultReceipt": controlled_edge_receipt or {},
            "beforeScreenshot": before_screenshot,
            "afterScreenshot": after_screenshot,
            "failureScreenshot": failure_screenshot,
            "localTlsTrust": tls_trust,
            "androidPortReverse": android_port_reverse,
            "releaseUatStateReset": release_uat_state_reset,
            "consumerLease": (
                {
                    "target": consumer_lease[0],
                    "deviceId": consumer_lease[1],
                    "consumer": consumer_lease[2],
                    "leaseId": consumer_lease[3],
                    "releasedAfterRun": True,
                }
                if consumer_lease is not None
                else {"status": "not-required"}
            ),
            "runtimeRecovery": runtime_recovery_evidence,
            "accountEnforcement": account_enforcement_evidence,
            "credentialArtifactCleanup": credential_artifact_cleanup,
            "testedAppArtifactBinding": tested_app_artifact_binding,
            "externalProductionAutJourney": external_aut_journey,
            "externalProductionAutDriver": external_aut_driver_result,
            "externalProductionAutDriverArtifact": report.get(
                "externalProductionAutDriverArtifact", {}
            ),
            "externalProductionAutScreenshot": external_aut_screenshot,
            "artifactBindingBlocker": artifact_binding_blocker,
            "typedBlocker": typed_blocker,
        }
        report["runs"].append(result)
        external_case = external_aut_case_result(
            required=external_aut_required,
            dry_run=args.dry_run,
            device_id=sanitize_device_id(str(device.get("id", ""))),
            journey=external_aut_journey,
            driver_result=external_aut_driver_result,
            screenshot=external_aut_screenshot,
            blocker=external_aut_blocker,
        )
        if external_case is not None:
            report["caseResults"].append(external_case)
        report["caseResults"].append(
            {
                "caseId": (
                    f"patrol:{args.target}:{sanitize_device_id(str(device.get('id', '')))}"
                ),
                "status": (
                    "not_executed"
                    if args.dry_run
                    else ("passed" if result["exitCode"] == 0 else "failed")
                ),
                "deviceId": device.get("id", ""),
                "testExecution": result["testExecution"],
                **typed_blocker,
                "evidence": {
                    "commandPath": command_path,
                    "patrolLogPath": result.get("logPath", ""),
                    "remoteApi": report["remoteApiEvidence"],
                    "runtimeRecovery": runtime_recovery_evidence,
                    "accountEnforcement": account_enforcement_evidence,
                    "controlledEdgeFault": controlled_edge_fault_evidence,
                    "testedAppArtifactBinding": tested_app_artifact_binding,
                    "externalProductionAutJourney": external_aut_journey,
                },
            }
        )
        failed = failed or result["exitCode"] != 0

    report["status"] = (
        "gate_block"
        if gate_blocked
        else ("failed" if failed else ("dry_run" if args.dry_run else "passed"))
    )
    if failed:
        report["failureReason"] = (
            "local TLS preflight blocked one or more Patrol runs"
            if gate_blocked
            else "one or more Patrol runs failed"
        )
    report["endedAt"] = utc_now()
    write_report(report_path, report)
    return 2 if report["status"] == "gate_block" else (1 if failed else 0)
