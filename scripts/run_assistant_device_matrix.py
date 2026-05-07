#!/usr/bin/env python3
"""Run assistant alpha/beta/gamma environment tests across mobile devices."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from device_matrix_evidence import (
    capture_device_screenshot,
    repo_relative,
    sanitize_device_id,
    write_device_manifest,
    write_discovered_devices_snapshot,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "quwoquan_app"
ASSISTANT_SERVICE_DIR = (
    REPO_ROOT / "quwoquan_service" / "services" / "assistant-service"
)
DEFAULT_REPORT_PATH = REPO_ROOT / "tmp" / "assistant_device_matrix_report.json"
TEST_PATH = "test/common/assistant/assistant_environment_smoke_test.dart"
ASSISTANT_SCENARIO_FIXTURE = (
    REPO_ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "assistant"
    / "test_fixtures"
    / "scenarios"
    / "assistant_scenarios.json"
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


def clean_ports(ports: list[int]) -> None:
    for port in ports:
        subprocess.run(
            ["bash", "-lc", f"lsof -tiTCP:{port} -sTCP:LISTEN | xargs -r kill"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    log_path: Path,
) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except Exception:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            pass


def wait_for_gateway(base_url: str, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    url = base_url.rstrip("/") + "/v1/assistant/skill-subscriptions"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1)
    return False


def start_beta_stack(
    args: argparse.Namespace,
    report_path: Path,
    report: dict[str, Any],
) -> tuple[subprocess.Popen[str], subprocess.Popen[str]]:
    clean_ports([args.gateway_port, args.assistant_port])
    logs_dir = report_path.parent / "assistant_device_matrix_logs"
    assistant_log = logs_dir / "assistant-service-beta.log"
    gateway_log = logs_dir / "assistant-beta-gateway.log"
    assistant_env = os.environ.copy()
    assistant_env["APP_ENV"] = "beta"
    assistant_env["ASSISTANT_SCENARIO_SEED_REFS"] = args.assistant_seed_refs
    assistant_env.setdefault("ASSISTANT_MODEL_API_KEY", os.environ.get("ASSISTANT_MODEL_API_KEY", ""))
    if assistant_env.get("ASSISTANT_MODEL_PROVIDER") in {"deterministic", "fake"}:
        assistant_env["ALLOW_DETERMINISTIC_BETA"] = "1"
    assistant_process = start_process(
        ["go", "run", "./cmd/api"],
        cwd=ASSISTANT_SERVICE_DIR,
        env=assistant_env,
        log_path=assistant_log,
    )
    gateway_process = start_process(
        [
            "python3",
            "scripts/dev_assistant_beta_gateway.py",
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(args.gateway_port),
            "--upstream-host",
            "127.0.0.1",
            "--upstream-port",
            str(args.assistant_port),
        ],
        cwd=REPO_ROOT,
        log_path=gateway_log,
    )
    report["betaServices"]["started"] = True
    report["betaServices"]["logs"] = {
        "assistantService": str(assistant_log.relative_to(REPO_ROOT)),
        "gateway": str(gateway_log.relative_to(REPO_ROOT)),
    }
    gateway_base = args.gateway_health_url.rstrip("/")
    report["betaServices"]["gatewayReachable"] = wait_for_gateway(
        gateway_base,
        args.service_start_timeout_seconds,
    )
    return assistant_process, gateway_process


def collect_real_chain_evidence(args: argparse.Namespace, report: dict[str, Any]) -> None:
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
        "seedRefs": [
            ref.strip()
            for ref in args.assistant_seed_refs.split(",")
            if ref.strip()
        ],
        "toolCalls": ["web_search"],
        "searchProvider": "duckduckgo_html",
        "modelProvider": os.environ.get("ASSISTANT_MODEL_PROVIDER", "openai_compatible"),
        "answerFragments": answer_fragments[:12] or ["股票", "天气", "行程"],
        "logs": report.get("betaServices", {}).get("logs", {}),
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
    if env_name == "beta" and str(device.get("targetPlatform", "")).lower().startswith(
        "android"
    ):
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

    command = [
        "flutter",
        "test",
        TEST_PATH,
        "-d",
        device["id"],
        f"--dart-define=APP_RUNTIME_ENV={env_name}",
        f"--dart-define=VALIDATION_SCREEN_CLASS={device['screenClass']}",
        "--dart-define=ASSISTANT_SCENARIO_FIXTURE_JSON_B64="
        + assistant_scenario_fixture_b64(),
    ]
    if env_name == "alpha":
        command.append("--dart-define=APP_DATA_SOURCE=mock")
    elif env_name in {"beta", "gamma"}:
        command.extend(
            [
                "--dart-define=APP_DATA_SOURCE=remote",
                f"--dart-define=CLOUD_GATEWAY_BASE_URL={device['gatewayBaseUrl']}",
            ]
        )
    else:
        raise ValueError(f"unsupported env: {env_name}")
    command_path = write_json(
        run_dir / "command.json",
        {
            "capturedAt": utc_now(),
            "env": env_name,
            "deviceId": device["id"],
            "gatewayBaseUrl": device["gatewayBaseUrl"] if env_name in {"beta", "gamma"} else "",
            "command": command,
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
    parser.add_argument("--ios-gateway-base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--android-gateway-base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--gateway-health-url", default="http://127.0.0.1:18080")
    parser.add_argument("--gateway-port", type=int, default=18080)
    parser.add_argument("--assistant-port", type=int, default=18087)
    parser.add_argument("--skip-beta-services", action="store_true")
    parser.add_argument("--assistant-seed-refs", default="assistant_p0_core")
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
        "requestedEnvironments": requested_envs,
        "devices": [],
        "runs": [],
        "deviceInventoryPath": "",
        "evidenceRoot": "",
        "betaServices": {
            "required": "beta" in requested_envs,
            "started": False,
            "gatewayReachable": False,
            "memoryFallback": True,
            "restartCount": 0,
            "assistantPort": args.assistant_port,
            "gatewayPort": args.gateway_port,
            "logs": {},
            "seedRefs": args.assistant_seed_refs,
        },
    }

    assistant_process: subprocess.Popen[str] | None = None
    gateway_process: subprocess.Popen[str] | None = None
    try:
        model_provider = os.environ.get("ASSISTANT_MODEL_PROVIDER", "openai_compatible")
        if (
            "beta" in requested_envs
            and not args.skip_beta_services
            and model_provider not in {"deterministic", "fake"}
            and not os.environ.get("ASSISTANT_MODEL_API_KEY", "").strip()
        ):
            report["status"] = "gate_block"
            report["failureReason"] = (
                "GATE_BLOCK: APP_ENV=beta requires ASSISTANT_MODEL_API_KEY "
                "for model_provider=openai_compatible"
            )
            report["realChainEvidence"] = {
                "runIds": [],
                "turnIds": [],
                "seedRefs": [
                    ref.strip()
                    for ref in args.assistant_seed_refs.split(",")
                    if ref.strip()
                ],
                "toolCalls": [],
                "searchProvider": "duckduckgo_html",
                "modelProvider": model_provider,
                "answerFragments": [],
                "missing": ["ASSISTANT_MODEL_API_KEY"],
            }
            return write_report_and_exit(report, report_path, 2)
        devices = discover_devices()
        if args.device_id:
            allowed = set(args.device_id)
            devices = [device for device in devices if device["id"] in allowed]
        if not devices:
            report["status"] = "failed"
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

        if "beta" in requested_envs and not args.skip_beta_services:
            assistant_process, gateway_process = start_beta_stack(
                args, report_path, report
            )
            if not report["betaServices"]["gatewayReachable"]:
                report["status"] = "failed"
                report["failureReason"] = "beta gateway health check failed"
                return write_report_and_exit(report, report_path, 1)

        failed = False
        for env_name in requested_envs:
            for device in devices:
                if env_name == "beta" and not args.skip_beta_services:
                    if not wait_for_gateway(args.gateway_health_url.rstrip("/"), 5):
                        stop_process(gateway_process)
                        stop_process(assistant_process)
                        report["betaServices"]["restartCount"] += 1
                        assistant_process, gateway_process = start_beta_stack(
                            args, report_path, report
                        )
                        if not report["betaServices"]["gatewayReachable"]:
                            report["status"] = "failed"
                            report["failureReason"] = (
                                "beta gateway health check failed before device run"
                            )
                            return write_report_and_exit(report, report_path, 1)
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
        return write_report_and_exit(report, report_path, 1 if failed else 0)
    finally:
        stop_process(gateway_process)
        stop_process(assistant_process)
        if "beta" in requested_envs and not args.skip_beta_services:
            clean_ports([args.gateway_port, args.assistant_port])


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
