#!/usr/bin/env python3
"""Run a real Flutter/iOS Simulator cold-start and hot-restart smoke.

The smoke can exercise either the canonical launcher or literal ``flutter run``.
Both surfaces must retain one canonical runtime handoff across the resident
compiler's cold start and hot restart.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import pty
import re
import signal
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from hot_restart_resident_observation import (
    attempt_segments,
    daemon_resident_app_id,
    flutter_resident_uses_daemon_protocol,
    pump_pty,
    read_simulator_startup_log,
    wait_for_cold_startup,
    wait_for_hot_restart,
)
from hot_restart_resident_observation import (
    direct_consumer_lease_id as _direct_consumer_lease_id,
)
from hot_restart_resident_observation import redacted_command as _redacted_command
from verify_startup_first_frame import (
    classify_startup_terminal,
    extract_dart_startup_attempts,
    extract_startup_watchdog_evidence,
    parse_startup_sequence_log,
)

APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_app.scripts.device.startup_terminal_receipt import (
    build_startup_terminal_receipt,
    canonical_terminal_for_surface,
    marker_digest,
    read_startup_terminal_receipt,
    write_startup_terminal_receipt,
)
from quwoquan_ops.cli.lib.app_identity import application_id_for
from quwoquan_ops.cli.lib.app_launch_attempt import read_app_launch_attempt

LAUNCHER = APP_DIR / "run.sh"
ENVIRONMENTS = ("alpha", "beta", "gamma")
LAUNCH_PROVENANCES = ("canonical_launcher", "workspace_flutter_run")
RUNTIME_CONFIG_SUPPLY_MODE = "external_runtime_package"
SAFE_TERMINAL_HARD_LIMIT_MS = 6000


def _runtime_package_preflight(
    environment: str,
    launch_provenance: str,
) -> dict[str, str]:
    """确认 runtime package 材料可渲染；endpoint 不再进 DART_DEFINES。

    新契约（environment-topology-and-packaging REQ-004）下环境、endpoint 与
    runtime config 摘要由安装后 native activation 拥有，编译期不注入 define；
    本 preflight 只验证 package 材料源可用与环境一致性。
    """
    result = subprocess.run(
        [
            sys.executable,
            "scripts/env/print_app_env_dart_defines.py",
            "--env",
            environment,
            "--format",
            "json",
            "--launch-provenance",
            launch_provenance,
        ],
        cwd=APP_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    decoded = json.loads(result.stdout)
    if not isinstance(decoded, dict):
        raise RuntimeError("runtime package material source did not return an object")
    material = {str(key): str(value) for key, value in decoded.items()}
    if material.get("environment") != environment:
        raise RuntimeError(
            "runtime package material environment is "
            f"{material.get('environment')!r}, expected {environment!r}"
        )
    forbidden = sorted(
        key
        for key in material
        if key.upper() == key and ("URL" in key or key == "APP_RUNTIME_ENV")
    )
    if forbidden:
        raise RuntimeError(
            "endpoint defines must not re-enter compile inputs: "
            + ", ".join(forbidden)
        )
    return material


def _attach_controlling_terminal(slave_fd: int) -> None:
    """Give Flutter's resident runner a real single-character terminal."""

    os.setsid()
    fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)


def _read_flutter_pid(state_root: Path, environment: str, device_id: str) -> int | None:
    safe_device_id = re.sub(r"[^A-Za-z0-9._-]+", "_", device_id).strip("_")
    state_file = state_root / environment / f"{safe_device_id or 'device'}.json"
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0)
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _find_descendant_flutter_pid(root_pid: int) -> int | None:
    pending = [root_pid]
    visited: set[int] = set()
    while pending:
        parent_pid = pending.pop()
        if parent_pid in visited:
            continue
        visited.add(parent_pid)
        try:
            children = subprocess.run(
                ["pgrep", "-P", str(parent_pid)],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        for raw_pid in children.stdout.split():
            try:
                child_pid = int(raw_pid)
            except ValueError:
                continue
            try:
                command = subprocess.run(
                    ["ps", "-o", "command=", "-p", str(child_pid)],
                    check=False,
                    capture_output=True,
                    text=True,
                ).stdout
            except OSError:
                return None
            if "flutter_tools.snapshot run" in command or (
                "flutter_tools.snapshot attach" in command
            ):
                return child_pid
            pending.append(child_pid)
    return None


def _terminate_stale_device_runtime(device_id: str, bundle_id: str) -> dict[str, Any]:
    """Terminate only the target app; never sweep unrelated host processes.

    The outer app-content UAT operation lock serializes this runner.  Host-wide
    process discovery cannot prove ownership and previously allowed one iOS
    run to terminate Android or another Simulator's frontend server.  The
    resident process created below is instead owned through its Popen handle
    and is always reaped in ``finally``.
    """
    native = subprocess.run(
        ["xcrun", "simctl", "terminate", device_id, bundle_id],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "cleanupScope": "simulator_bundle_only",
        "terminatedFlutterResidentPids": [],
        "terminatedFrontendServerPids": [],
        "terminatedNativeApp": native.returncode == 0,
    }


def _read_installed_runtime_identity(
    device_id: str,
    bundle_id: str,
) -> dict[str, str]:
    """读取安装后激活的 runtime identity（active receipt 真相源）。

    App 产物不再内嵌 runtime identity；环境、target 与 runtime config 摘要由
    安装后 native activation 写入 Data 容器的 active receipt。
    """
    container = subprocess.run(
        ["xcrun", "simctl", "get_app_container", device_id, bundle_id, "data"],
        check=False,
        capture_output=True,
        text=True,
    )
    if container.returncode != 0:
        raise RuntimeError(
            container.stderr.strip()
            or container.stdout.strip()
            or "installed iOS app data container is unavailable"
        )
    receipt_path = (
        Path(container.stdout.strip())
        / "Library/Application Support/qwq_runtime"
        / "runtime-config-active-receipt.json"
    )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"iOS runtime activation receipt is unreadable: {error}"
        ) from error
    if not isinstance(receipt, dict):
        raise RuntimeError("iOS runtime activation receipt must be an object")
    if receipt.get("status") != "activated":
        raise RuntimeError(
            "iOS runtime activation receipt status is "
            f"{receipt.get('status')!r}, expected 'activated'"
        )
    identity = {
        "environment": str(receipt.get("environment") or "").strip(),
        "target": str(receipt.get("target") or "").strip(),
        "runtimeConfigDigest": str(
            receipt.get("activePackageDigest") or ""
        ).strip(),
        "effectiveLaunchManifestDigest": str(
            receipt.get("effectiveLaunchManifestDigest") or ""
        ).strip(),
    }
    if not identity["environment"] or not identity["target"]:
        raise RuntimeError("installed iOS runtime identity is incomplete")
    for key in ("runtimeConfigDigest", "effectiveLaunchManifestDigest"):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity[key]):
            raise RuntimeError(f"installed iOS {key} is invalid")
    return identity


def _runtime_identity_issues(
    snapshots: list[dict[str, str]],
    *,
    expected_environment: str,
) -> list[str]:
    if not snapshots:
        return ["no installed iOS runtime identity snapshots were captured"]
    issues: list[str] = []
    expected_target = f"{expected_environment}-local"
    baseline = snapshots[0]
    for index, snapshot in enumerate(snapshots):
        label = "cold" if index == 0 else f"hot_restart_{index}"
        if snapshot.get("environment") != expected_environment:
            issues.append(
                f"{label}: environment is {snapshot.get('environment')!r}, "
                f"expected {expected_environment!r}"
            )
        if snapshot.get("target") != expected_target:
            issues.append(
                f"{label}: target is {snapshot.get('target')!r}, "
                f"expected {expected_target!r}"
            )
        for key in (
            "environment",
            "target",
            "runtimeConfigDigest",
            "effectiveLaunchManifestDigest",
        ):
            if snapshot.get(key) != baseline.get(key):
                issues.append(
                    f"{label}: {key} drifted from the cold runtime identity"
                )
    return issues


def _publish_canonical_launch_terminal(
    *,
    device_id: str,
    bundle_id: str,
    launch_provenance: str,
    runtime_identity: dict[str, str],
    simulator_log: str,
    excluded_attempt_ids: set[str] | frozenset[str],
    max_cold_native_safe_terminal_ms: int,
) -> bool:
    """Project the same validated iOS safe terminal into the launch receipt track."""

    raw_attempt_path = os.environ.get("QWQ_APP_LAUNCH_RECEIPT", "").strip()
    raw_terminal_path = os.environ.get(
        "QWQ_APP_STARTUP_TERMINAL_RECEIPT", ""
    ).strip()
    if not raw_attempt_path and not raw_terminal_path:
        return True
    if not raw_attempt_path or not raw_terminal_path:
        raise RuntimeError("canonical iOS launch terminal evidence paths are partial")
    attempt_path = Path(raw_attempt_path)
    terminal_path = Path(raw_terminal_path)
    if not attempt_path.is_absolute() or not terminal_path.is_absolute():
        raise RuntimeError("canonical iOS launch terminal evidence paths are not absolute")
    launch_attempt: dict[str, Any] | None = None
    launch_deadline = time.monotonic() + 5.0
    while time.monotonic() < launch_deadline:
        try:
            observed = read_app_launch_attempt(attempt_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            time.sleep(0.05)
            continue
        launch_attempt = observed
        if observed.get("status") in {"launching", "launched"}:
            break
        time.sleep(0.05)
    if launch_attempt is None:
        raise RuntimeError("canonical iOS launch attempt is unavailable")
    expected_launch = {
        "platform": "ios",
        "deviceId": device_id,
        "applicationId": bundle_id,
        "launchProvenance": launch_provenance,
        "runtimeConfigSupplyMode": RUNTIME_CONFIG_SUPPLY_MODE,
        "runtimeConfigPackageDigest": runtime_identity["runtimeConfigDigest"],
        "launchDigest": runtime_identity["effectiveLaunchManifestDigest"],
    }
    if any(
        launch_attempt.get(field) != expected
        for field, expected in expected_launch.items()
    ):
        raise RuntimeError("canonical iOS launch attempt/runtime identity drifted")
    if launch_attempt.get("status") not in {"launching", "launched"}:
        raise RuntimeError("canonical iOS launch attempt has not reached launching")

    cold_segments = [
        (attempt, segment)
        for attempt, segment in attempt_segments(
            simulator_log,
            excluded_attempt_ids=excluded_attempt_ids,
        )
        if attempt.get("hotRestart") == "false"
    ]
    if len(cold_segments) != 1:
        raise RuntimeError("canonical iOS launch requires exactly one cold attempt")
    dart_attempt, raw_segment = cold_segments[0]
    validated = _validate_attempt(dart_attempt, raw_segment)
    issues = _attempt_evidence_issues(
        "cold",
        validated,
        expected_launch_provenance=launch_provenance,
        is_cold=True,
        max_cold_native_safe_terminal_ms=max_cold_native_safe_terminal_ms,
    )
    if issues:
        raise RuntimeError("canonical iOS safe terminal is invalid: " + "; ".join(issues))
    observed_manifest = str(
        dart_attempt.get("effectiveLaunchManifestDigest") or ""
    )
    if observed_manifest and observed_manifest != launch_attempt.get("launchDigest"):
        raise RuntimeError("canonical iOS safe terminal manifest identity drifted")
    if terminal_path.exists() or terminal_path.is_symlink():
        existing = read_startup_terminal_receipt(
            terminal_path,
            launch_attempt=launch_attempt,
        )
        if existing.get("startupAttemptId") != validated.get("attemptId"):
            raise RuntimeError("canonical iOS safe terminal attemptId drifted")
        return True
    receipt = build_startup_terminal_receipt(
        launch_attempt=launch_attempt,
        startup_attempt_id=str(validated.get("attemptId") or ""),
        configuration_state=str(validated.get("configurationState") or ""),
        surface=str(validated.get("terminalSurface") or ""),
        canonical_terminal=canonical_terminal_for_surface(
            str(validated.get("terminalSurface") or "")
        ),
        hot_restart=bool(validated.get("hotRestart")),
        observed_marker_digest=marker_digest(raw_segment),
    )
    write_startup_terminal_receipt(terminal_path, receipt)
    return True


def _stop_original_process_group(
    process: subprocess.Popen[bytes],
    process_group_id: int,
    *,
    attempts: int = 3,
    wait_seconds: float = 5.0,
) -> bool:
    """Stop only the process group created for this Flutter session."""

    if process.poll() is not None:
        return True
    for _ in range(attempts):
        try:
            os.killpg(process_group_id, signal.SIGINT)
        except ProcessLookupError:
            return True
        except PermissionError:
            # macOS 上模拟器系统进程可能混入该进程组导致 killpg EPERM；
            # 降级为只向我们拥有的 Popen 直系进程发信号。
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=wait_seconds)
            return True
        except subprocess.TimeoutExpired:
            continue
    # canonical launcher 的 SIGINT 收尾包含 attach 优雅退出与 test_live
    # 报告落盘，可能超过信号重试窗口；最后一次完整等待避免误报未退出。
    try:
        process.wait(timeout=30.0)
        return True
    except subprocess.TimeoutExpired:
        return process.poll() is not None


def _count_native_launches_since(raw_log: str, since: dt.datetime) -> int:
    count = 0
    for line in raw_log.splitlines():
        if "ios_did_finish_launching" not in line:
            continue
        try:
            timestamp = dt.datetime.strptime(
                line[:23],
                "%Y-%m-%d %H:%M:%S.%f",
            )
        except ValueError:
            continue
        if timestamp >= since:
            count += 1
    return count


def _validate_attempt(attempt: dict[str, Any], raw_segment: str) -> dict[str, Any]:
    sequence = parse_startup_sequence_log(raw_segment)
    terminal = classify_startup_terminal(raw_segment, sequence)
    watchdog = extract_startup_watchdog_evidence(raw_segment)
    failures = any(
        marker in raw_segment
        for marker in (
            "startup_bootstrap_failure",
            "ios_startup_bootstrap_failure",
            "android_startup_bootstrap_failure",
        )
    )
    return {
        "attemptId": attempt.get("attemptId"),
        "launchProvenance": attempt.get("launchProvenance"),
        "runtimeConfigSupplyMode": attempt.get("runtimeConfigSupplyMode"),
        "effectiveLaunchManifestDigest": attempt.get(
            "effectiveLaunchManifestDigest"
        ),
        "hotRestart": attempt.get("hotRestart") == "true",
        "configurationState": attempt.get("configurationState"),
        "missingDefineKeys": attempt.get("missingDefineKeys"),
        "failureCode": watchdog.get("failureCode", ""),
        "terminalSurface": watchdog.get("safeTerminalSurface"),
        "canonicalTerminal": terminal,
        "bootstrapFailure": failures,
        "terminalEventCount": len(
            re.findall(
                r"(?:ios|android)_startup_safe_terminal "
                r"surface=router_shell "
                r"(?:reportedElapsedMs|elapsedMs)=",
                raw_segment,
            )
        ),
        "reportedSafeTerminalMs": watchdog.get("reportedSafeTerminalMs"),
        "nativeReceivedSafeTerminalMs": watchdog.get(
            "nativeReceivedSafeTerminalMs"
        ),
    }


def _attempt_evidence_issues(
    label: str,
    item: dict[str, Any],
    *,
    expected_launch_provenance: str,
    is_cold: bool,
    max_cold_native_safe_terminal_ms: int = SAFE_TERMINAL_HARD_LIMIT_MS,
) -> list[str]:
    issues: list[str] = []
    if item["launchProvenance"] != expected_launch_provenance:
        issues.append(
            f"{label}: launchProvenance is {item['launchProvenance']!r}, "
            f"expected {expected_launch_provenance!r}"
        )
    if item["runtimeConfigSupplyMode"] != RUNTIME_CONFIG_SUPPLY_MODE:
        issues.append(
            f"{label}: runtimeConfigSupplyMode is "
            f"{item['runtimeConfigSupplyMode']!r}, "
            f"expected {RUNTIME_CONFIG_SUPPLY_MODE!r}"
        )
    if item["bootstrapFailure"]:
        issues.append(f"{label}: startup_bootstrap_failure observed")
    if item["canonicalTerminal"] != "routerShell":
        issues.append(
            f"{label}: canonical terminal is {item['canonicalTerminal']!r}, "
            "expected routerShell"
        )
    if item.get("terminalSurface") != "router_shell":
        issues.append(
            f"{label}: startup safe-terminal surface is "
            f"{item.get('terminalSurface')!r}, expected 'router_shell'"
        )
    if item["configurationState"] != "complete":
        issues.append(f"{label}: runtime configuration was not complete")
    if item["missingDefineKeys"]:
        issues.append(f"{label}: missing define keys reported")
    if item["terminalEventCount"] != 1:
        issues.append(
            f"{label}: expected exactly one safe terminal event, "
            f"got {item['terminalEventCount']}"
        )

    reported_value = item.get("reportedSafeTerminalMs")
    if (
        not isinstance(reported_value, int)
        or reported_value > SAFE_TERMINAL_HARD_LIMIT_MS
    ):
        issues.append(
            f"{label}: reportedSafeTerminalMs is missing or exceeds "
            f"{SAFE_TERMINAL_HARD_LIMIT_MS}ms"
        )

    native_limit_ms = (
        max_cold_native_safe_terminal_ms
        if is_cold
        else SAFE_TERMINAL_HARD_LIMIT_MS
    )
    native_value = item.get("nativeReceivedSafeTerminalMs")
    if not isinstance(native_value, int) or native_value > native_limit_ms:
        issues.append(
            f"{label}: nativeReceivedSafeTerminalMs is missing or exceeds "
            f"{native_limit_ms}ms"
        )
    return issues


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    parser.add_argument("--device-id", required=True)
    # 默认按 环境 × Debug 派生 bundle id（本 smoke 为 flutter run/Debug 面）。
    parser.add_argument("--bundle", default="")
    parser.add_argument(
        "--launch-provenance",
        choices=LAUNCH_PROVENANCES,
        default="canonical_launcher",
    )
    parser.add_argument(
        "--run-mode",
        choices=("content-live", "ui-only"),
        default="content-live",
        help=(
            "canonical launcher 经 --mode 透传；workspace_flutter_run "
            "经 QWQ_RUN_MODE 环境变量透传给同一执行体。"
        ),
    )
    parser.add_argument("--output-dir", default="")
    # canonical launcher 冷路径包含 pod install 与 xcodebuild 增量构建，
    # 180s 在真实构建下必然超时；上限只约束等待，不影响通过速度。
    parser.add_argument("--ready-timeout-seconds", type=float, default=480)
    parser.add_argument(
        "--max-cold-native-safe-terminal-ms",
        type=int,
        default=SAFE_TERMINAL_HARD_LIMIT_MS,
        help=(
            "Maximum native receipt latency for the cold attempt only; "
            "reported and hot-restart terminals remain capped at 6000ms."
        ),
    )
    parser.add_argument("--restart-wait-seconds", type=float, default=20)
    parser.add_argument("--hot-restart-count", type=int, default=3)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.hot_restart_count < 1:
        print("--hot-restart-count must be at least 1", file=sys.stderr)
        return 2
    if args.max_cold_native_safe_terminal_ms < SAFE_TERMINAL_HARD_LIMIT_MS:
        print(
            "--max-cold-native-safe-terminal-ms must be at least 6000",
            file=sys.stderr,
        )
        return 2
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else ROOT / ".qwq_output/env/repo/runs/ios_hot_restart"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    run_dir = output_dir / f"{args.env}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if not str(args.bundle or "").strip():
        args.bundle = application_id_for("ios", args.env, "debug")

    try:
        package_material = _runtime_package_preflight(
            args.env,
            args.launch_provenance,
        )
    except (RuntimeError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.preflight_only:
        report_path = run_dir / "report.json"
        report = {
            "status": "passed",
            "environment": args.env,
            "deviceId": args.device_id,
            "verifiedPackageMaterialKeys": sorted(package_material),
            "launchProvenance": args.launch_provenance,
            "runtimeConfigSupplyMode": RUNTIME_CONFIG_SUPPLY_MODE,
            "consumerLeaseId": _direct_consumer_lease_id(
                args.env,
                args.device_id,
            ),
            "reportPath": str(report_path),
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    stale_runtime_cleanup = _terminate_stale_device_runtime(
        args.device_id,
        args.bundle,
    )
    # workspace surface 走字面 flutter run（工作区 facade 接管归一化）；环境仅由
    # QWQ_ENVIRONMENT 表达，facade 拒绝 --flavor/--mode 等启动配置参数。
    if args.launch_provenance == "canonical_launcher":
        command = [
            "bash",
            str(LAUNCHER),
            "--mode",
            args.run_mode,
            "-d",
            args.device_id,
        ]
    else:
        command = ["flutter", "run", "-d", args.device_id]
    baseline_captured_at = dt.datetime.now()
    baseline_simulator_log = read_simulator_startup_log(args.device_id)
    baseline_attempt_ids = frozenset(
        str(attempt.get("attemptId") or "")
        for attempt in extract_dart_startup_attempts(baseline_simulator_log)
    )
    instance_state_root = run_dir / "app-instance-state"
    environment = dict(os.environ)
    environment["QWQ_IOS_SIMULATOR_UDID"] = args.device_id
    if args.launch_provenance == "canonical_launcher":
        environment["QWQ_APP_RUNTIME_ENV"] = args.env
    else:
        # Workspace Flutter Debug is selected only by QWQ_ENVIRONMENT. A partial
        # QWQ_APP_* identity must continue to fail closed.
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_APP_LAUNCH_PROVENANCE",
            "QWQ_RUNTIME_CONFIG_SUPPLY_MODE",
            "QWQ_LAUNCH_TARGET",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
        ):
            environment.pop(key, None)
        environment["QWQ_ENVIRONMENT"] = args.env
        # mode 与环境同构经环境变量透传给同一 canonical 执行体。
        environment["QWQ_RUN_MODE"] = args.run_mode
        # workspace surface 的语义是「工作区 facade 终端里的字面 flutter run」：
        # facade bin 必须前置 PATH，否则解析到裸 SDK 会因缺 trust envelope
        # 在 Xcode build phase fail closed（那是负例路径，不是本 surface）。
        facade_bin = APP_DIR / "scripts/tools/flutter_facade/bin"
        environment["PATH"] = (
            f"{facade_bin}{os.pathsep}{environment.get('PATH', '')}"
        )
    environment["QWQ_APP_INSTANCE_PRESERVE_TTY"] = "1"
    environment["APP_INSTANCE_STATE_ROOT"] = str(instance_state_root)
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        command,
        cwd=APP_DIR,
        env=environment,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=lambda: _attach_controlling_terminal(slave_fd),
    )
    process_group_id = os.getpgid(process.pid)
    if process_group_id != process.pid:
        raise RuntimeError(
            "Flutter session did not retain its dedicated process group"
        )
    os.close(slave_fd)
    output = bytearray()
    hot_restart_triggers: list[str] = []
    runtime_identity_snapshots: list[dict[str, str]] = []
    runtime_identity_capture_issues: list[str] = []
    process_group_stopped = False
    try:
        cold_ready = wait_for_cold_startup(
            master_fd,
            process,
            args.device_id,
            output,
            excluded_attempt_ids=baseline_attempt_ids,
            timeout_seconds=args.ready_timeout_seconds,
        )
        observed_attempt_ids = set(baseline_attempt_ids)
        if cold_ready and process.poll() is None:
            canonical_terminal_published = False
            try:
                cold_runtime_identity = _read_installed_runtime_identity(
                    args.device_id,
                    args.bundle,
                )
                runtime_identity_snapshots.append(cold_runtime_identity)
                canonical_terminal_published = _publish_canonical_launch_terminal(
                    device_id=args.device_id,
                    bundle_id=args.bundle,
                    launch_provenance=args.launch_provenance,
                    runtime_identity=cold_runtime_identity,
                    simulator_log=read_simulator_startup_log(args.device_id),
                    excluded_attempt_ids=baseline_attempt_ids,
                    max_cold_native_safe_terminal_ms=(
                        args.max_cold_native_safe_terminal_ms
                    ),
                )
            except RuntimeError as error:
                runtime_identity_capture_issues.append(f"cold: {error}")
            observed_attempt_ids.update(
                str(item.get("attemptId") or "")
                for item in extract_dart_startup_attempts(
                    read_simulator_startup_log(args.device_id)
                )
            )
            daemon_protocol = flutter_resident_uses_daemon_protocol(output)
            restart_count = (
                args.hot_restart_count if canonical_terminal_published else 0
            )
            for restart_sequence in range(1, restart_count + 1):
                terminal_state = termios.tcgetattr(master_fd)
                trigger = "daemon_app_restart" if daemon_protocol else "R"
                try:
                    hot_grace_seconds = min(8.0, args.restart_wait_seconds)
                    if daemon_protocol:
                        # daemon 协议（flutter attach --machine）没有键盘命令
                        # 面；hot restart 走协议正门 app.restart JSON-RPC，
                        # 经 PTY stdin 送达 resident flutter attach。
                        app_id = daemon_resident_app_id(output)
                        if app_id is None:
                            trigger = "daemon_app_id_missing"
                        else:
                            request = (
                                json.dumps(
                                    [
                                        {
                                            "id": restart_sequence,
                                            "method": "app.restart",
                                            "params": {
                                                "appId": app_id,
                                                "fullRestart": True,
                                            },
                                        }
                                    ]
                                )
                                + "\n"
                            )
                            os.write(master_fd, request.encode("utf-8"))
                        hot_grace_seconds = 0.0
                    else:
                        # Flutter may not switch to single-character mode when
                        # the launcher is nested under a noninteractive shell.
                        # Set the PTY raw for the one command so R cannot
                        # remain line-buffered.
                        tty.setraw(master_fd)
                        hot_restart_output_offset = len(output)
                        os.write(master_fd, b"R")
                        hot_attempt_ready = wait_for_hot_restart(
                            master_fd,
                            process,
                            args.device_id,
                            output,
                            excluded_attempt_ids=observed_attempt_ids,
                            timeout_seconds=hot_grace_seconds,
                            require_safe_terminal=False,
                        )
                        hot_restart_cli_started = (
                            b"Performing hot restart"
                            in output[hot_restart_output_offset:]
                        )
                        if (
                            not hot_attempt_ready
                            and not hot_restart_cli_started
                            and process.poll() is None
                        ):
                            flutter_pid = _read_flutter_pid(
                                instance_state_root,
                                args.env,
                                args.device_id,
                            )
                            if flutter_pid is None:
                                flutter_pid = _find_descendant_flutter_pid(
                                    process.pid
                                )
                            if flutter_pid is not None:
                                try:
                                    os.kill(flutter_pid, signal.SIGUSR2)
                                    trigger = "SIGUSR2_fallback"
                                except OSError:
                                    trigger = "SIGUSR2_fallback_failed"
                    hot_safe_ready = wait_for_hot_restart(
                        master_fd,
                        process,
                        args.device_id,
                        output,
                        excluded_attempt_ids=observed_attempt_ids,
                        timeout_seconds=max(
                            0.0,
                            args.restart_wait_seconds - hot_grace_seconds,
                        ),
                        require_safe_terminal=True,
                    )
                    hot_restart_triggers.append(trigger)
                    if hot_safe_ready:
                        try:
                            runtime_identity_snapshots.append(
                                _read_installed_runtime_identity(
                                    args.device_id,
                                    args.bundle,
                                )
                            )
                        except RuntimeError as error:
                            runtime_identity_capture_issues.append(
                                f"hot_restart_{len(hot_restart_triggers)}: {error}"
                            )
                    observed_attempt_ids.update(
                        str(item.get("attemptId") or "")
                        for item in extract_dart_startup_attempts(
                            read_simulator_startup_log(args.device_id)
                        )
                    )
                finally:
                    termios.tcsetattr(master_fd, termios.TCSANOW, terminal_state)
    finally:
        process_group_stopped = _stop_original_process_group(
            process,
            process_group_id,
        )
        pump_pty(master_fd, process, output, timeout_seconds=1)
        os.close(master_fd)
        # 高负载下 launcher 的 SIGINT 收尾可能晚于等待窗口；只要进程
        # 在报告前已退出，就视为 scoped SIGINT 生效。
        process_group_stopped = process_group_stopped or (
            process.poll() is not None
        )

    flutter_output = output.decode("utf-8", errors="replace")
    (run_dir / "flutter-run.log").write_text(flutter_output, encoding="utf-8")
    simulator_log = read_simulator_startup_log(args.device_id)
    (run_dir / "ios-startup.log").write_text(simulator_log, encoding="utf-8")

    segments = attempt_segments(
        simulator_log,
        excluded_attempt_ids=baseline_attempt_ids,
    )
    attempt_reports = [_validate_attempt(attempt, segment) for attempt, segment in segments]
    cold = next(
        (item for item in attempt_reports if not item["hotRestart"]),
        None,
    )
    hot_restarts = [item for item in attempt_reports if item["hotRestart"]]
    native_did_finish_count = _count_native_launches_since(
        simulator_log,
        baseline_captured_at,
    )
    issues: list[str] = []
    issues.extend(runtime_identity_capture_issues)
    issues.extend(
        _runtime_identity_issues(
            runtime_identity_snapshots,
            expected_environment=args.env,
        )
    )
    if len(runtime_identity_snapshots) != args.hot_restart_count + 1:
        issues.append(
            "expected runtime identity readback for cold plus "
            f"{args.hot_restart_count} hot restarts, got "
            f"{len(runtime_identity_snapshots)}"
        )
    if not process_group_stopped:
        issues.append(
            "Flutter process group did not exit after scoped SIGINT requests"
        )
    if cold is None:
        issues.append("cold Dart startup attempt was not observed")
    if len(hot_restarts) != args.hot_restart_count:
        issues.append(
            "expected "
            f"{args.hot_restart_count} hot-restart Dart startup attempts, "
            f"got {len(hot_restarts)}"
        )
    labeled_attempts = [("cold", cold)] + [
        (f"hot_restart_{index}", item)
        for index, item in enumerate(hot_restarts, start=1)
    ]
    for label, item in labeled_attempts:
        if item is None:
            continue
        issues.extend(
            _attempt_evidence_issues(
                label,
                item,
                expected_launch_provenance=args.launch_provenance,
                is_cold=label == "cold",
                max_cold_native_safe_terminal_ms=(
                    args.max_cold_native_safe_terminal_ms
                ),
            )
        )
    if native_did_finish_count != 1:
        issues.append(
            "expected exactly one ios_did_finish_launching for the cold "
            f"process launch, got {native_did_finish_count}; "
            "native relaunch must not be mistaken for hot restart"
        )

    report_path = run_dir / "report.json"
    report = {
        "status": "passed" if not issues else "failed",
        "environment": args.env,
        "deviceId": args.device_id,
        "launchProvenance": args.launch_provenance,
        "runtimeConfigSupplyMode": RUNTIME_CONFIG_SUPPLY_MODE,
        "consumerLeaseId": _direct_consumer_lease_id(args.env, args.device_id),
        "hotRestartCount": args.hot_restart_count,
        "hotRestartTriggers": hot_restart_triggers,
        "staleRuntimeCleanup": stale_runtime_cleanup,
        "flutterProcessGroupId": process_group_id,
        "flutterProcessGroupStoppedBySigint": process_group_stopped,
        "flutterRunExitCode": process.returncode,
        "nativeDidFinishLaunchingCount": native_did_finish_count,
        "runtimeIdentitySnapshots": runtime_identity_snapshots,
        "safeTerminalBudgetsMs": {
            "reported": SAFE_TERMINAL_HARD_LIMIT_MS,
            "hotNativeReceived": SAFE_TERMINAL_HARD_LIMIT_MS,
            "coldNativeReceived": args.max_cold_native_safe_terminal_ms,
        },
        "attempts": attempt_reports,
        "issues": issues,
        "flutterRunLog": str(run_dir / "flutter-run.log"),
        "iosStartupLog": str(run_dir / "ios-startup.log"),
        "command": _redacted_command(command),
        "reportPath": str(report_path),
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
