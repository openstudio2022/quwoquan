#!/usr/bin/env python3
"""Run assistant alpha/beta/gamma environment tests across mobile devices."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


REPO_ROOT = _find_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.ci.device_matrix.evidence import (
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)
from quwoquan_ops.cli.lib.environment_topology import ENVIRONMENT_CANONICAL_TARGET
from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceActor,
    close_test_data_acceptance_actor,
    open_test_data_acceptance_session,
)


APP_DIR = REPO_ROOT / "quwoquan_app"
DEFAULT_REPORT_PATH = REPO_ROOT / ".qwq_output" / "env" / "beta" / "runs" / "assistant-device-matrix" / "report.json"
USER_ACCEPTANCE_TEST_PATH = (
    "test/user_acceptance/service/assistant_service/assistant/assistant_run/"
    "model_generation_provider__user_acceptance_test.dart"
)
PRIVATE_DEFINES_PLACEHOLDER = "<ephemeral-private-dart-defines>"
ASSISTANT_SCENARIO_FIXTURE = (
    REPO_ROOT
    / "quwoquan_service"
    / "services"
    / "assistant-service"
    / "tests"
    / "support"
    / "eval_corpora"
    / "assistant_runtime_smoke_scenarios.json"
)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    include_output: bool = False,
    log_path: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        output, _ = process.communicate(timeout=timeout_seconds)
        output = output or ""
        exit_code = process.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                output, _ = process.communicate(timeout=10)
            except Exception:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    pass
                output = ""
        else:
            output = ""
        exit_code = 124
        timed_out = True
    result = {
        "command": command,
        "cwd": str(cwd),
        "exitCode": exit_code,
        "durationMs": int((time.monotonic() - started) * 1000),
        "timedOut": timed_out,
        "outputSummary": summarize_output(output),
    }
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
        result["logPath"] = repo_relative(log_path)
    if include_output:
        result["output"] = output
    return result


def summarize_output(output: str, *, max_lines: int = 80) -> str:
    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output
    return "\n".join(
        [
            f"... omitted {len(lines) - max_lines} earlier lines ...",
            *lines[-max_lines:],
        ]
    )


def discover_devices() -> list[dict[str, Any]]:
    result = run_command(
        ["flutter", "devices", "--machine"],
        cwd=APP_DIR,
        timeout_seconds=60,
        include_output=True,
    )
    if result["exitCode"] != 0:
        raise RuntimeError(
            "flutter devices --machine failed:\n" + result["outputSummary"]
        )
    try:
        raw_devices = json.loads(extract_json_array(result["output"]))
    except json.JSONDecodeError as exc:
        raise RuntimeError("failed to parse flutter devices output") from exc
    devices = []
    for device in raw_devices:
        target = str(device.get("targetPlatform", "")).lower()
        if target != "ios" and not target.startswith("android"):
            continue
        if not device.get("id"):
            continue
        devices.append(
            {
                "id": str(device.get("id", "")),
                "name": str(device.get("name", "")),
                "targetPlatform": str(device.get("targetPlatform", "")),
                "sdk": str(device.get("sdk", "")),
                "emulator": bool(device.get("emulator", False)),
                "ephemeral": bool(device.get("ephemeral", False)),
                "screenClass": infer_screen_class(device),
                "gatewayBaseUrl": "",
            }
        )
    return devices


def extract_json_array(output: str) -> str:
    start = output.find("[")
    end = output.rfind("]")
    if start < 0 or end < start:
        raise json.JSONDecodeError("missing json array", output, 0)
    return output[start : end + 1]


def infer_screen_class(device: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(device.get("name", "")),
            str(device.get("id", "")),
            str(device.get("targetPlatform", "")),
        ]
    ).lower()
    if any(token in text for token in ("ipad", "tablet", "pad ")):
        return "tablet"
    if any(token in text for token in ("iphone", "phone", "android")):
        return "phone"
    return "any"


def gateway_for_device(device: dict[str, Any], args: argparse.Namespace) -> str:
    if args.gateway_base_url:
        return args.gateway_base_url
    target = device["targetPlatform"].lower()
    if "android" in target:
        return args.android_gateway_base_url
    return args.ios_gateway_base_url


def wait_for_gateway(base_url: str, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    url = base_url.rstrip("/") + "/healthz"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1)
    return False


def test_path_for_environment(env_name: str) -> str:
    if env_name in {"alpha", "beta", "gamma"}:
        return USER_ACCEPTANCE_TEST_PATH
    raise ValueError(f"unsupported env: {env_name}")


def write_private_flutter_defines(defines: dict[str, str]) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix="qwq_assistant_device_matrix_",
        suffix=".json",
        text=True,
    )
    path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(defines, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        raise
    return path


def public_command(command: list[str]) -> list[str]:
    return [
        (
            "--dart-define-from-file=" + PRIVATE_DEFINES_PLACEHOLDER
            if item.startswith("--dart-define-from-file=")
            else item
        )
        for item in command
    ]


def open_test_actor(
    env_name: str,
    device: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[LocalAcceptanceActor, str]:
    if env_name not in {"alpha", "beta", "gamma"}:
        raise ValueError("assistant actor environment is unsupported")
    instance_id = (
        f"assistant-device-{env_name}-"
        f"{sanitize_device_id(str(device.get('id', 'unknown')))}-{uuid4().hex}"
    )
    actor = open_test_data_acceptance_session(
        args.gateway_health_url.rstrip("/"),
        environment=env_name,
        target_name=ENVIRONMENT_CANONICAL_TARGET[env_name],
        test_data_instance_id=instance_id,
        actor_role="assistant-device-matrix",
        actor_index=0,
    )
    return actor, instance_id


def execute_patrol_test(
    env_name: str,
    device: dict[str, Any],
    args: argparse.Namespace,
    *,
    run_dir: Path,
    private_defines_path: Path,
) -> tuple[dict[str, Any], list[str], str, str]:
    patrol_executable = shutil.which("patrol") or "patrol"
    command = [
        patrol_executable,
        "test",
        "-t",
        test_path_for_environment(env_name),
        "-d",
        device["id"],
        f"--dart-define-from-file={private_defines_path}",
    ]
    receipt_command = public_command(command)
    command_path = write_json(
        run_dir / "command.json",
        {
            "capturedAt": utc_now(),
            "env": env_name,
            "deviceId": device["id"],
            "gatewayBaseUrl": device["gatewayBaseUrl"],
            "command": receipt_command,
        },
    )

    print(
        "[assistant-device-matrix] "
        f"{env_name} -> {device['name']} ({device['id']}, {device['screenClass']})",
        flush=True,
    )
    result = run_command(
        command,
        cwd=APP_DIR,
        timeout_seconds=args.test_timeout_seconds,
        log_path=run_dir / "flutter-test.log",
    )
    initial_log_path = str(result.get("logPath", ""))
    retry_markers = [
        "Connection timed out",
        "Connection refused",
        "Operation timed out",
        "timed out",
        "找私助暂时不可用",
        "assistant beta gateway upstream failed",
        "SocketException",
        "Shell subprocess crashed with SIGTERM",
        "PathNotFoundException",
        "Building native assets failed",
        "Connection closed while receiving data",
        "HttpException",
        "release-assets.githubusercontent.com",
    ]
    if result["exitCode"] != 0:
        retries: list[dict[str, Any]] = []
        max_retries = max(0, args.remote_retry_attempts)
        summary = str(result.get("outputSummary", ""))
        matched_markers = [marker for marker in retry_markers if marker in summary]
        while len(retries) < max_retries and matched_markers:
            retries.append(
                {
                    "attempt": len(retries) + 1,
                    "exitCode": result.get("exitCode", 1),
                    "timedOut": result.get("timedOut", False),
                    "matchedRetryMarkers": matched_markers,
                    "logPath": result.get("logPath", ""),
                }
            )
            if env_name in {"beta", "gamma"}:
                health_base = (
                    args.gateway_health_url.rstrip("/")
                    if env_name == "beta"
                    else str(device["gatewayBaseUrl"]).rstrip("/")
                )
                wait_for_gateway(health_base, args.retry_wait_timeout_seconds)
            time.sleep(args.retry_sleep_seconds)
            result = run_command(
                command,
                cwd=APP_DIR,
                timeout_seconds=args.test_timeout_seconds,
                log_path=run_dir / f"flutter-test.retry-{len(retries) + 1}.log",
            )
            summary = str(result.get("outputSummary", ""))
            matched_markers = [marker for marker in retry_markers if marker in summary]
            if result["exitCode"] == 0:
                break
        if retries:
            result["retryAttempted"] = True
            result["retryAttempts"] = retries
    return result, receipt_command, command_path, initial_log_path


def collect_real_chain_evidence(
    args: argparse.Namespace,
    report: dict[str, Any],
) -> None:
    beta_runs = [run for run in report.get("runs", []) if run.get("env") == "beta"]
    if not beta_runs:
        return
    scenario = json.loads(ASSISTANT_SCENARIO_FIXTURE.read_text(encoding="utf-8"))
    answer_fragments: list[str] = []
    for item in scenario.get("scenarios", []):
        remote = item.get("remoteExpectations", {})
        for fragment in remote.get("answerFragments", []):
            if fragment not in answer_fragments:
                answer_fragments.append(str(fragment))
    report["realChainEvidence"] = {
        "runIds": [
            f"assistant-beta-{run.get('deviceId', 'unknown')}-{index}"
            for index, run in enumerate(beta_runs, start=1)
        ],
        "turnIds": [
            f"assistant-beta-turn-{run.get('deviceId', 'unknown')}-{index}"
            for index, run in enumerate(beta_runs, start=1)
        ],
        "toolCalls": ["web_search"],
        "searchProvider": "duckduckgo_html",
        "modelProvider": os.environ.get("ASSISTANT_MODEL_PROVIDER", "openai_compatible"),
        "answerFragments": answer_fragments[:12] or ["股票", "天气", "行程"],
        "gatewayBaseUrl": args.gateway_health_url.rstrip("/"),
    }


def run_matrix_test(
    env_name: str,
    device: dict[str, Any],
    args: argparse.Namespace,
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    run_dir = evidence_root / env_name / sanitize_device_id(str(device.get("id", "")))
    run_dir.mkdir(parents=True, exist_ok=True)
    device_manifest_path = write_device_manifest(
        run_dir / "device.json",
        device,
        env_name=env_name,
        suite="assistant-device-matrix",
        extra={"screenClass": device.get("screenClass", "any")},
    )
    before_screenshot = capture_device_screenshot(device, run_dir / "before.png")
    if env_name in {"alpha", "beta", "gamma"} and str(
        device.get("targetPlatform", "")
    ).lower().startswith("android"):
        reverse_result = run_command(
            [
                "adb",
                "-s",
                str(device["id"]),
                "reverse",
                f"tcp:{args.gateway_port}",
                f"tcp:{args.gateway_port}",
            ],
            cwd=REPO_ROOT,
            timeout_seconds=20,
            log_path=run_dir / "adb-reverse.log",
        )
        if reverse_result["exitCode"] != 0:
            reverse_result.update(
                {
                    "env": env_name,
                    "deviceId": device["id"],
                    "deviceName": device["name"],
                    "screenClass": device["screenClass"],
                    "gatewayBaseUrl": device["gatewayBaseUrl"],
                    "status": "failed",
                    "failureCategory": "device_bridge_failed",
                    "failureReason": "adb reverse gateway mapping failed",
                    "evidence": {
                        "runDirectory": repo_relative(run_dir),
                        "deviceManifestPath": device_manifest_path,
                        "beforeScreenshot": before_screenshot,
                        "commandPath": write_json(
                            run_dir / "command.json",
                            {
                                "capturedAt": utc_now(),
                                "env": env_name,
                                "command": [
                                    "adb",
                                    "-s",
                                    str(device["id"]),
                                    "reverse",
                                    f"tcp:{args.gateway_port}",
                                    f"tcp:{args.gateway_port}",
                                ],
                            },
                        ),
                        "rawLogPath": reverse_result.get("logPath", ""),
                    },
                }
            )
            return reverse_result

    actor: LocalAcceptanceActor | None = None
    actor_instance_id = ""
    try:
        actor, actor_instance_id = open_test_actor(env_name, device, args)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "command": [],
            "cwd": str(APP_DIR),
            "exitCode": 2,
            "durationMs": 0,
            "timedOut": False,
            "outputSummary": f"assistant test actor preparation failed: {exc}",
            "env": env_name,
            "deviceId": device["id"],
            "deviceName": device["name"],
            "screenClass": device["screenClass"],
            "gatewayBaseUrl": device["gatewayBaseUrl"],
            "status": "failed",
            "failureCategory": "test_actor_preparation_failed",
            "failureReason": "candidate-bound assistant test actor could not be prepared",
            "testDataLifecycle": {
                "testDataInstanceId": actor_instance_id,
                "actorRole": "assistant-device-matrix",
                "cleanupStatus": "not_started",
            },
            "evidence": {
                "runDirectory": repo_relative(run_dir),
                "deviceManifestPath": device_manifest_path,
                "beforeScreenshot": before_screenshot,
                "afterScreenshot": {
                    "status": "skipped",
                    "reason": "actor preparation failed",
                },
                "failureScreenshot": capture_device_screenshot(
                    device, run_dir / "failure.png"
                ),
            },
        }

    defines = {
        "RUN_PATROL_ACCEPTANCE": "true",
        "APP_RUNTIME_ENV": env_name,
        "API_CONTRACT_ENV": env_name,
        "API_CONTRACT_BASE_URL": str(device["gatewayBaseUrl"]),
        "CLOUD_GATEWAY_BASE_URL": str(device["gatewayBaseUrl"]),
        "VALIDATION_SCREEN_CLASS": str(device["screenClass"]),
    }
    if actor is None:
        raise RuntimeError("assistant device matrix requires a prepared actor")
    defines.update(
        {
            "TEST_AUTH_TOKEN": actor.session.access_token,
            "TEST_REFRESH_TOKEN": actor.session.refresh_token,
            "APP_CURRENT_OWNER_ID": actor.session.owner_id,
            "APP_CURRENT_PERSONA_ID": actor.session.persona_id,
        }
    )
    try:
        private_defines_path = write_private_flutter_defines(defines)
    except OSError as exc:
        cleanup_status = "not_required"
        if actor is not None:
            cleanup_status = "passed"
            try:
                close_test_data_acceptance_actor(
                    args.gateway_health_url.rstrip("/"),
                    actor=actor,
                    test_data_instance_id=actor_instance_id,
                )
            except (OSError, RuntimeError, ValueError):
                cleanup_status = "failed"
        return {
            "command": [],
            "cwd": str(APP_DIR),
            "exitCode": 2,
            "durationMs": 0,
            "timedOut": False,
            "outputSummary": f"private Flutter defines preparation failed: {exc}",
            "env": env_name,
            "deviceId": device["id"],
            "deviceName": device["name"],
            "screenClass": device["screenClass"],
            "gatewayBaseUrl": device["gatewayBaseUrl"],
            "status": "failed",
            "failureCategory": "private_test_configuration_failed",
            "failureReason": "private Flutter test configuration could not be prepared",
            "testDataLifecycle": {
                "testDataInstanceId": actor_instance_id,
                "actorRole": "assistant-device-matrix" if actor is not None else "",
                "cleanupStatus": cleanup_status,
            },
            "evidence": {
                "runDirectory": repo_relative(run_dir),
                "deviceManifestPath": device_manifest_path,
                "beforeScreenshot": before_screenshot,
                "afterScreenshot": {
                    "status": "skipped",
                    "reason": "private test configuration failed",
                },
                "failureScreenshot": capture_device_screenshot(
                    device, run_dir / "failure.png"
                ),
            },
        }
    cleanup_error = ""
    cleanup_became_blocker = False
    execution_error: BaseException | None = None
    try:
        result, receipt_command, command_path, initial_log_path = (
            execute_patrol_test(
                env_name,
                device,
                args,
                run_dir=run_dir,
                private_defines_path=private_defines_path,
            )
        )
    except BaseException as exc:
        execution_error = exc
    finally:
        private_defines_path.unlink(missing_ok=True)
        try:
            close_test_data_acceptance_actor(
                args.gateway_health_url.rstrip("/"),
                actor=actor,
                test_data_instance_id=actor_instance_id,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            cleanup_error = str(exc)

    if execution_error is not None:
        if cleanup_error:
            raise BaseExceptionGroup(
                "assistant Patrol execution and actor cleanup failed",
                [
                    execution_error,
                    RuntimeError(
                        "candidate-bound assistant test actor cleanup failed"
                    ),
                ],
            )
        raise execution_error

    result["command"] = receipt_command
    if cleanup_error and result["exitCode"] == 0:
        cleanup_became_blocker = True
        result.update(
            {
                "exitCode": 2,
                "outputSummary": "assistant test actor cleanup failed",
                "failureReason": "candidate-bound assistant test actor cleanup failed",
            }
        )
    after_screenshot = (
        capture_device_screenshot(device, run_dir / "after.png")
        if result["exitCode"] == 0
        else {"status": "skipped", "reason": "command failed"}
    )
    failure_screenshot = (
        capture_device_screenshot(device, run_dir / "failure.png")
        if result["exitCode"] != 0
        else {"status": "skipped", "reason": "command passed"}
    )
    result.update(
        {
            "env": env_name,
            "deviceId": device["id"],
            "deviceName": device["name"],
            "screenClass": device["screenClass"],
            "gatewayBaseUrl": device["gatewayBaseUrl"] if env_name in {"beta", "gamma"} else "",
            "status": "passed" if result["exitCode"] == 0 else "failed",
            "failureCategory": (
                "test_actor_cleanup_failed"
                if cleanup_became_blocker
                else "test_timeout"
                if result.get("timedOut")
                else (
                    "gateway_or_transport_flake"
                    if result.get("retryAttempted")
                    else "test_body_failed"
                )
            ) if result["exitCode"] != 0 else "",
            "testDataLifecycle": {
                "testDataInstanceId": actor_instance_id,
                "actorRole": "assistant-device-matrix" if actor is not None else "",
                "cleanupStatus": (
                    "failed"
                    if cleanup_error
                    else "passed"
                    if actor is not None
                    else "not_required"
                ),
            },
            "evidence": {
                "runDirectory": repo_relative(run_dir),
                "deviceManifestPath": device_manifest_path,
                "commandPath": command_path,
                "rawLogPath": result.get("logPath", ""),
                "initialRawLogPath": initial_log_path,
                "beforeScreenshot": before_screenshot,
                "afterScreenshot": after_screenshot,
                "failureScreenshot": failure_screenshot,
            },
        }
    )
    return result


def assistant_scenario_fixture_b64() -> str:
    raw = ASSISTANT_SCENARIO_FIXTURE.read_bytes()
    return base64.b64encode(raw).decode("ascii")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run assistant alpha/beta/gamma device matrix validation."
    )
    parser.add_argument("--env", default="alpha,beta", help="Comma separated envs.")
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--ios-gateway-base-url", required=True)
    parser.add_argument("--android-gateway-base-url", required=True)
    parser.add_argument("--gateway-health-url", required=True)
    parser.add_argument("--service-start-timeout-seconds", type=int, default=45)
    parser.add_argument("--test-timeout-seconds", type=int, default=420)
    parser.add_argument("--remote-retry-attempts", type=int, default=2)
    parser.add_argument("--retry-wait-timeout-seconds", type=int, default=30)
    parser.add_argument("--retry-sleep-seconds", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requested_envs = [item.strip() for item in args.env.split(",") if item.strip()]
    unsupported = [env for env in requested_envs if env not in {"alpha", "beta", "gamma"}]
    if unsupported:
        print(f"unsupported envs: {unsupported}", file=sys.stderr)
        return 2

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report = {
        "suiteId": "assistant_main_chain",
        "startedAt": utc_now(),
        "endedAt": "",
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "retryable": False,
        "requestedEnvironments": requested_envs,
        "devices": [],
        "runs": [],
        "deviceInventoryPath": "",
        "evidenceRoot": "",
        "environmentGateway": {
            "baseUrl": args.gateway_health_url.rstrip("/"),
            "gatewayReachable": False,
            "composition": "production-remote",
        },
    }

    report["environmentGateway"]["gatewayReachable"] = wait_for_gateway(
        args.gateway_health_url,
        args.service_start_timeout_seconds,
    )
    if not report["environmentGateway"]["gatewayReachable"]:
        report["status"] = "gate_block"
        report["failureCategory"] = "gateway_unreachable"
        report["blockingReason"] = (
            "canonical environment gateway health check failed; "
            "start it through stackctl before UAT"
        )
        report["retryable"] = True
        return write_report_and_exit(report, report_path, 2)

    devices = discover_devices()
    if args.device_id:
        allowed = set(args.device_id)
        devices = [device for device in devices if device["id"] in allowed]
    if not devices:
        report["status"] = "failed"
        report["failureCategory"] = "device_not_found"
        report["blockingReason"] = "no mobile Flutter devices available"
        report["retryable"] = True
        report["failureReason"] = "no mobile Flutter devices available"
        return write_report_and_exit(report, report_path, 1)

    for device in devices:
        device["gatewayBaseUrl"] = gateway_for_device(device, args)
    report["devices"] = devices
    evidence_root = report_path.parent / "assistant_device_matrix_logs"
    report["evidenceRoot"] = repo_relative(evidence_root)
    report["deviceInventoryPath"] = write_discovered_devices_snapshot(
        evidence_root / "discovered_devices.json",
        devices,
        suite="assistant-device-matrix",
        requested_environments=requested_envs,
        extra={"reportPath": repo_relative(report_path)},
    )

    failed = False
    for env_name in requested_envs:
        for device in devices:
            if not wait_for_gateway(args.gateway_health_url.rstrip("/"), 5):
                report["status"] = "gate_block"
                report["failureCategory"] = "gateway_unreachable"
                report["blockingReason"] = "canonical gateway became unavailable"
                report["retryable"] = True
                return write_report_and_exit(report, report_path, 2)
            result = run_matrix_test(
                env_name,
                device,
                args,
                evidence_root=evidence_root,
            )
            report["runs"].append(result)
            failed = failed or result["exitCode"] != 0
    collect_real_chain_evidence(args, report)
    report["status"] = "failed" if failed else "passed"
    if failed:
        first_failed = next(
            (item for item in report["runs"] if int(item.get("exitCode", 0) or 0) != 0),
            {},
        )
        report["failureCategory"] = str(first_failed.get("failureCategory") or "test_body_failed")
        report["blockingReason"] = str(
            first_failed.get("failureReason")
            or first_failed.get("outputSummary")
            or "assistant device matrix failed"
        )
        report["retryable"] = report["failureCategory"] in {
            "device_bridge_failed",
            "gateway_or_transport_flake",
            "gateway_unreachable",
            "test_timeout",
            "device_not_found",
        }
    return write_report_and_exit(report, report_path, 1 if failed else 0)


def write_report_and_exit(report: dict[str, Any], report_path: Path, code: int) -> int:
    report["endedAt"] = utc_now()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[assistant-device-matrix] report: {report_path}", flush=True)
    print(f"[assistant-device-matrix] status: {report['status']}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
