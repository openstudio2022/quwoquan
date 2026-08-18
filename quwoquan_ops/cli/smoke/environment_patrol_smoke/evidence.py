"""Patrol 运行证据的读取与设备矩阵校验（视频/feed/edge/恢复/账号处置 + 移动端证据流）。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge
from quwoquan_ops.ci.device_matrix.evidence import repo_relative
from quwoquan_ops.cli.lib.video_playback_evidence import (
    read_native_video_playback_evidence,
)

from .constants import (
    ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX,
    ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE,
    ANDROID_DEVICE_EVIDENCE_LOG_TAG,
    ANDROID_DEVICE_EVIDENCE_TOKENS,
    APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX,
    CONTROLLED_EDGE_FAULT_COPY_KEYS,
    CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX,
    CORE_READBACK_TARGET,
    FEED_CONTENT_EVIDENCE_PREFIX,
    FEED_LOAD_TARGET,
    IOS_DEVICE_EVIDENCE_TOKENS,
    MESSAGE_HOME_TARGET,
    PROFILE_JOURNEY_TARGET,
    REPO_ROOT,
    RUNTIME_RECOVERY_EVIDENCE_FIELDS,
    RUNTIME_RECOVERY_EVIDENCE_PREFIX,
    utc_now,
)
from .session import (
    _is_account_enforcement_target,
    _is_feed_load_target,
    _is_runtime_recovery_target,
)


def _read_video_playback_evidence(patrol_log: Path) -> dict[str, bool]:
    return read_native_video_playback_evidence(patrol_log)


def _read_feed_content_evidence(patrol_log: Path) -> dict[str, Any]:
    if not patrol_log.is_file():
        return {}
    for line in reversed(patrol_log.read_text(encoding="utf-8").splitlines()):
        marker = line.find(FEED_CONTENT_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[marker + len(FEED_CONTENT_EVIDENCE_PREFIX) :].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        environment = str(payload.get("environment") or "").strip()
        visible_keys = payload.get("visibleCardKeys")
        visible_count = payload.get("visibleCardCount")
        if (
            environment not in {"alpha", "beta", "gamma"}
            or not isinstance(visible_keys, list)
            or not visible_keys
            or any(not isinstance(item, str) or not item for item in visible_keys)
            or len(set(visible_keys)) != len(visible_keys)
            or visible_count != len(visible_keys)
        ):
            return {}
        return {
            "environment": environment,
            "visibleCardCount": visible_count,
            "visibleCardKeys": visible_keys,
        }
    return {}


_APP_CONTENT_PAGE_SCREENSHOT_EXPECTATIONS = (
    (
        FEED_LOAD_TARGET,
        "homepage-feed",
        "/",
        "",
        ("home-feed-card-", "dual-discovery-card-"),
    ),
    (
        CORE_READBACK_TARGET,
        "app-core-readback",
        "/",
        "works_immersive_pager",
        (),
    ),
    (
        MESSAGE_HOME_TARGET,
        "message-home",
        "/chat/",
        "chat_input_text_field",
        (),
    ),
    (
        PROFILE_JOURNEY_TARGET,
        "profile-journey",
        "/user/",
        "",
        ("profile-header-avatar", "profile-shell-summary-card"),
    ),
)


def _app_content_page_screenshot_expectation(
    args: argparse.Namespace,
) -> tuple[str, str, str, tuple[str, ...]] | None:
    target = str(getattr(args, "target", "") or "").replace("\\", "/")
    for suffix, suite, route, terminal_key, terminal_key_prefixes in (
        _APP_CONTENT_PAGE_SCREENSHOT_EXPECTATIONS
    ):
        if target.endswith(suffix):
            return suite, route, terminal_key, terminal_key_prefixes
    return None


def _parse_app_content_page_screenshot_marker(
    line: str,
    *,
    args: argparse.Namespace,
    runtime_env: str,
) -> dict[str, str] | None:
    marker = line.find(APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX)
    if marker < 0:
        return None
    expectation = _app_content_page_screenshot_expectation(args)
    if expectation is None:
        raise RuntimeError(
            "app-content page screenshot marker came from an unsupported target"
        )
    encoded = line[
        marker + len(APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX) :
    ].strip()
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "app-content page screenshot marker is not valid JSON"
        ) from error
    if not isinstance(payload, dict):
        raise RuntimeError("app-content page screenshot marker must be an object")
    environment = str(payload.get("environment") or "").strip()
    suite = str(payload.get("suite") or "").strip()
    route = str(payload.get("route") or "").strip()
    terminal_key = str(payload.get("terminalKey") or "").strip()
    expected_suite, expected_route, expected_key, expected_key_prefixes = expectation
    if environment != runtime_env or runtime_env not in {"alpha", "beta", "gamma"}:
        raise RuntimeError(
            "app-content page screenshot marker environment does not match runtime"
        )
    if suite != expected_suite:
        raise RuntimeError(
            "app-content page screenshot marker suite does not match target"
        )
    if expected_route == "/":
        route_matches = route == expected_route
    else:
        route_matches = route.startswith(expected_route) and route != expected_route
    if not route_matches:
        raise RuntimeError(
            "app-content page screenshot marker route does not match target"
        )
    if expected_key:
        key_matches = terminal_key == expected_key
    else:
        key_matches = any(
            terminal_key.startswith(prefix) for prefix in expected_key_prefixes
        )
    if not key_matches:
        raise RuntimeError(
            "app-content page screenshot marker terminalKey does not match target"
        )
    return {
        "environment": environment,
        "suite": suite,
        "route": route,
        "terminalKey": terminal_key,
    }


class _AppContentPageScreenshotCapture:
    """Capture one exact page frame while the four app-content UATs are alive."""

    def __init__(
        self,
        *,
        args: argparse.Namespace,
        runtime_env: str,
        capture: Callable[[], dict[str, Any]],
    ) -> None:
        self.args = args
        self.runtime_env = runtime_env
        self.capture = capture
        self.required = _app_content_page_screenshot_expectation(args) is not None
        self.marker_count = 0
        self.evidence: dict[str, Any] = {
            "status": "missing" if self.required else "not-required"
        }

    def handle_line(self, line: str) -> None:
        marker = _parse_app_content_page_screenshot_marker(
            line,
            args=self.args,
            runtime_env=self.runtime_env,
        )
        if marker is None:
            return
        self.marker_count += 1
        if self.marker_count != 1:
            raise RuntimeError(
                "app-content page screenshot marker must occur exactly once"
            )
        captured = self.capture()
        if captured.get("status") != "captured" or not str(
            captured.get("path") or ""
        ).strip():
            raise RuntimeError(
                "app-content page screenshot capture failed during Patrol"
            )
        self.evidence = {
            **captured,
            "capturedDuringPatrol": True,
            "marker": marker,
        }

    def apply_success_gate(self, result: dict[str, Any], *, dry_run: bool) -> None:
        if (
            not self.required
            or dry_run
            or int(result.get("exitCode", 1)) != 0
            or (
                self.marker_count == 1
                and self.evidence.get("status") == "captured"
                and self.evidence.get("capturedDuringPatrol") is True
            )
        ):
            return
        result["exitCode"] = 1
        result["outputSummary"] = (
            str(result.get("outputSummary") or "")
            + "\napp-content UAT passed without one in-run route/key screenshot"
        ).strip()


def _read_controlled_edge_fault_evidence(patrol_log: Path) -> dict[str, Any]:
    if not patrol_log.is_file():
        return {}
    for line in reversed(patrol_log.read_text(encoding="utf-8").splitlines()):
        marker = line.find(CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[
            marker + len(CONTROLLED_EDGE_FAULT_EVIDENCE_PREFIX) :
        ].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        environment = str(payload.get("environment") or "").strip()
        copy_key = str(payload.get("copyKey") or "").strip()
        recovered_count = payload.get("recoveredVisibleCardCount")
        if (
            environment not in {"alpha", "beta", "gamma"}
            or copy_key not in CONTROLLED_EDGE_FAULT_COPY_KEYS
            or payload.get("singlePrimaryAction") is not True
            or payload.get("forbiddenBrandAbsent") is not True
            or payload.get("technicalDetailsAbsent") is not True
            or payload.get("blockedRetryCount") != 5
            or payload.get("blockingErrorRetained") is not True
            or payload.get("sameInstallRecovery") is not True
            or not isinstance(recovered_count, int)
            or recovered_count <= 0
        ):
            return {}
        return {
            "environment": environment,
            "copyKey": copy_key,
            "singlePrimaryAction": True,
            "forbiddenBrandAbsent": True,
            "technicalDetailsAbsent": True,
            "blockedRetryCount": 5,
            "blockingErrorRetained": True,
            "sameInstallRecovery": True,
            "recoveredVisibleCardCount": recovered_count,
        }
    return {}


def _is_ios_device(device: dict[str, Any]) -> bool:
    return str(device.get("targetPlatform") or "").strip().lower() == "ios"


def _is_android_device(device: dict[str, Any]) -> bool:
    return (
        str(device.get("targetPlatform") or "")
        .strip()
        .lower()
        .startswith("android")
    )


def _android_device_evidence_commands(
    device_id: str,
    run_boundary: str,
    *,
    adb_path: str | None = None,
) -> tuple[list[str], list[str]]:
    exact_device_id = device_id.strip()
    exact_run_boundary = run_boundary.strip()
    if not exact_device_id:
        raise ValueError("Android device evidence requires one exact device id")
    if not exact_run_boundary:
        raise ValueError("Android device evidence requires one exact run boundary")
    executable = adb_path or resolve_android_debug_bridge()
    if not executable:
        raise RuntimeError(
            "GATE_BLOCK: adb is required for exact-device Android UAT evidence"
        )
    return (
        [
            executable,
            "-s",
            exact_device_id,
            "logcat",
            "-v",
            "raw",
            "-T",
            "1",
            "flutter:I",
            f"{ANDROID_DEVICE_EVIDENCE_LOG_TAG}:I",
            "*:S",
        ],
        [
            executable,
            "-s",
            exact_device_id,
            "shell",
            "log",
            "-p",
            "i",
            "-t",
            ANDROID_DEVICE_EVIDENCE_LOG_TAG,
            exact_run_boundary,
        ],
    )


def _ios_device_evidence_command(
    device_id: str,
    *,
    xcrun_path: str | None = None,
) -> list[str]:
    exact_device_id = device_id.strip()
    if not exact_device_id:
        raise ValueError("iOS device evidence requires one exact Simulator UDID")
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        raise RuntimeError(
            "GATE_BLOCK: xcrun is required for exact-device iOS UAT evidence"
        )
    predicate = 'process == "Runner" AND (' + " OR ".join(
        f'eventMessage CONTAINS "{token}"'
        for token in IOS_DEVICE_EVIDENCE_TOKENS
    ) + ")"
    return [
        executable,
        "simctl",
        "spawn",
        exact_device_id,
        "log",
        "stream",
        "--style",
        "compact",
        "--level",
        "debug",
        "--predicate",
        predicate,
    ]


def _is_ios_log_stream_predicate_banner(line: str) -> bool:
    """Identify the transport banner emitted by ``log stream`` itself."""

    return line.startswith('Filtering the log data using "')


class _IosDeviceEvidenceStream:
    """Capture whitelisted Flutter markers from one Simulator execution window."""

    def __init__(
        self,
        *,
        device_id: str,
        log_path: Path,
        output_line_handler: Callable[[str], None] | None = None,
        command: list[str] | None = None,
        evidence_tokens: tuple[str, ...] = IOS_DEVICE_EVIDENCE_TOKENS,
        run_boundary: str = "",
        run_boundary_command: list[str] | None = None,
    ) -> None:
        self.device_id = device_id.strip()
        self.log_path = log_path
        self.output_line_handler = output_line_handler
        self.command = command or _ios_device_evidence_command(self.device_id)
        self.evidence_tokens = evidence_tokens
        self.run_boundary = run_boundary.strip()
        self.run_boundary_command = run_boundary_command
        self.started_at = ""
        self.ended_at = ""
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._handler_error: Exception | None = None
        self._log_file: Any | None = None
        self._run_boundary_observed = threading.Event()

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("iOS device evidence stream already started")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_path.open("w", encoding="utf-8")
        self.started_at = utc_now()
        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=str(REPO_ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except BaseException:
            self._log_file.close()
            self._log_file = None
            raise

        def read_output() -> None:
            assert self._process is not None and self._process.stdout is not None
            assert self._log_file is not None
            try:
                for line in self._process.stdout:
                    if _is_ios_log_stream_predicate_banner(line):
                        continue
                    if (
                        self.run_boundary
                        and not self._run_boundary_observed.is_set()
                    ):
                        if self.run_boundary in line:
                            self._run_boundary_observed.set()
                        continue
                    if not any(token in line for token in self.evidence_tokens):
                        continue
                    self._log_file.write(line)
                    self._log_file.flush()
                    if self.output_line_handler is not None:
                        try:
                            self.output_line_handler(line)
                        except Exception as error:  # noqa: BLE001
                            self._handler_error = error
                            return
            finally:
                self._log_file.flush()

        self._reader = threading.Thread(target=read_output, daemon=True)
        self._reader.start()
        if self.run_boundary_command is not None:
            for boundary_attempt in range(3):
                try:
                    boundary_result = subprocess.run(
                        self.run_boundary_command,
                        cwd=str(REPO_ROOT),
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=10,
                    )
                except BaseException:
                    self.stop(grace_seconds=0)
                    raise
                if boundary_result.returncode != 0:
                    self.stop(grace_seconds=0)
                    raise RuntimeError(
                        "GATE_BLOCK: exact-device Android evidence boundary "
                        "could not be emitted: "
                        + boundary_result.stderr.strip()[-1000:]
                    )
                if self._run_boundary_observed.wait(
                    timeout=2 if boundary_attempt < 2 else 6
                ):
                    break
        elif self.run_boundary:
            self._run_boundary_observed.wait(timeout=10)
        if self.run_boundary and not self._run_boundary_observed.is_set():
            self.stop(grace_seconds=0)
            raise RuntimeError(
                "GATE_BLOCK: exact-device Android evidence stream did not "
                "observe its current-run boundary"
            )
        time.sleep(0.25)
        if self._process.poll() is not None:
            self.stop(grace_seconds=0)
            raise RuntimeError(
                "GATE_BLOCK: exact-device iOS evidence stream exited before Patrol"
            )

    def stop(self, *, grace_seconds: float = 1.0) -> dict[str, Any]:
        process = self._process
        if process is None:
            return {
                "status": "not-started",
                "deviceId": self.device_id,
            }
        if grace_seconds > 0 and process.poll() is None:
            time.sleep(grace_seconds)
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        if self._reader is not None:
            self._reader.join(timeout=10)
        if process.stdout is not None:
            process.stdout.close()
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None
        self.ended_at = utc_now()
        self._process = None
        if self._handler_error is not None:
            raise RuntimeError(
                f"iOS device evidence handler failed: {self._handler_error}"
            ) from self._handler_error
        return {
            "status": "captured",
            "deviceId": self.device_id,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "logPath": repo_relative(self.log_path),
            "runBoundaryObserved": (
                not self.run_boundary or self._run_boundary_observed.is_set()
            ),
        }


class _AndroidDeviceEvidenceStream(_IosDeviceEvidenceStream):
    """Capture marker-only logcat after an exact-device, current-run boundary."""

    def __init__(
        self,
        *,
        device_id: str,
        log_path: Path,
        output_line_handler: Callable[[str], None] | None = None,
        command: list[str] | None = None,
        run_boundary: str = "",
        run_boundary_command: list[str] | None = None,
    ) -> None:
        exact_boundary = run_boundary.strip() or (
            f"qwq-patrol-evidence-{os.getpid()}-{time.time_ns()}"
        )
        if command is None:
            command, run_boundary_command = _android_device_evidence_commands(
                device_id,
                exact_boundary,
            )
        super().__init__(
            device_id=device_id,
            log_path=log_path,
            output_line_handler=output_line_handler,
            command=command,
            evidence_tokens=ANDROID_DEVICE_EVIDENCE_TOKENS,
            run_boundary=exact_boundary,
            run_boundary_command=run_boundary_command,
        )


def _device_evidence_stream(
    device: dict[str, Any],
    *,
    log_path: Path,
    output_line_handler: Callable[[str], None] | None = None,
) -> _IosDeviceEvidenceStream | None:
    device_id = str(device.get("id") or "")
    if _is_ios_device(device):
        return _IosDeviceEvidenceStream(
            device_id=device_id,
            log_path=log_path,
            output_line_handler=output_line_handler,
        )
    if _is_android_device(device):
        return _AndroidDeviceEvidenceStream(
            device_id=device_id,
            log_path=log_path,
            output_line_handler=output_line_handler,
        )
    return None


def _structured_evidence_log_path(
    device: dict[str, Any],
    run_dir: Path,
) -> Path:
    device_log = run_dir / "device-evidence.log"
    if (
        (_is_ios_device(device) or _is_android_device(device))
        and device_log.is_file()
    ):
        return device_log
    return run_dir / "patrol.log"


def _apply_feed_content_evidence_gate(
    result: dict[str, Any],
    args: argparse.Namespace,
    feed_content_evidence: dict[str, Any],
) -> None:
    if (
        _is_feed_load_target(args)
        and not args.dry_run
        and not feed_content_evidence
    ):
        result["exitCode"] = 1
        result["outputSummary"] = (
            str(result.get("outputSummary") or "")
            + "\nfeed UAT did not emit a release-bound visible-card evidence marker"
        ).strip()


def _read_runtime_recovery_evidence(path: Path) -> dict[str, bool]:
    if not path.is_file():
        return {}
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        marker = line.find(RUNTIME_RECOVERY_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[marker + len(RUNTIME_RECOVERY_EVIDENCE_PREFIX) :].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if (
            not isinstance(payload, dict)
            or set(payload) != RUNTIME_RECOVERY_EVIDENCE_FIELDS
            or any(not isinstance(value, bool) for value in payload.values())
        ):
            return {}
        return {str(key): bool(value) for key, value in payload.items()}
    return {}


def _read_account_enforcement_evidence(
    path: Path,
    *,
    phase: str,
    candidate_digest: str,
) -> dict[str, Any]:
    if not path.is_file() or phase not in ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE:
        return {}
    expected = {
        **ACCOUNT_ENFORCEMENT_EXPECTED_EVIDENCE[phase],
        "candidateDigest": candidate_digest,
    }
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        marker = line.find(ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX)
        if marker < 0:
            continue
        encoded = line[
            marker + len(ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX) :
        ].strip()
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict) or payload != expected:
            return {}
        return payload
    return {}


def _validate_runtime_recovery_device_matrix(
    args: argparse.Namespace,
    devices: list[dict[str, Any]],
) -> None:
    if not _is_runtime_recovery_target(args) or args.dry_run:
        return
    physical_android = any(
        str(device.get("targetPlatform") or "").lower().startswith("android")
        and not bool(device.get("emulator"))
        for device in devices
    )
    physical_ios = any(
        str(device.get("targetPlatform") or "").lower() == "ios"
        and not bool(device.get("emulator"))
        for device in devices
    )
    platform = str(args.platform or "").strip().lower()
    missing_android = platform in {"all", "android"} and not physical_android
    missing_ios = platform in {"all", "ios"} and not physical_ios
    if missing_android or missing_ios:
        required = (
            "one physical Android device and one physical iPhone"
            if platform == "all"
            else f"one physical {platform} device"
        )
        raise RuntimeError(
            f"GATE_BLOCK: runtime recovery UAT requires {required} "
            "in the selected CaseResult"
        )


def _validate_account_enforcement_device_matrix(
    args: argparse.Namespace,
    devices: list[dict[str, Any]],
) -> None:
    if not _is_account_enforcement_target(args) or args.dry_run:
        return
    physical_android = any(
        str(device.get("targetPlatform") or "").lower().startswith("android")
        and not bool(device.get("emulator"))
        for device in devices
    )
    physical_ios = any(
        str(device.get("targetPlatform") or "").lower() == "ios"
        and not bool(device.get("emulator"))
        for device in devices
    )
    if not physical_android or not physical_ios:
        raise RuntimeError(
            "GATE_BLOCK: account-enforcement Gamma UAT requires one physical "
            "Android device and one physical iPhone in the same CaseResult matrix"
        )


def load_remote_api_evidence(path_value: str) -> dict[str, Any]:
    """Load only a passed search Remote UAT report; no raw query is accepted."""

    normalized = path_value.strip()
    if not normalized:
        return {}
    path = Path(normalized).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence = payload["cases"]["searchAndFeedbackRoundtrip"]["evidence"]
        tag_filter = payload["cases"]["tagFilterPositiveAndNegative"]["evidence"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            "remote API evidence report is unreadable or not a search Remote UAT report"
        ) from exc
    if (
        payload.get("schema") != "search-remote-api-uat-report"
        or payload.get("status") != "passed"
        or evidence.get("schema") != "search-remote-api-evidence"
        or evidence.get("status") != "passed"
        or not str(evidence.get("searchRequestId") or "").strip()
        or tag_filter.get("schema") != "search-tag-filter-remote-evidence"
        or tag_filter.get("status") != "passed"
        or tag_filter.get("positiveHitCount") != 1
        or tag_filter.get("negativeHitCount") != 0
    ):
        raise ValueError("remote API evidence report is not a passed search Remote UAT")
    events = evidence.get("events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict)
        or not str(event.get("requestId") or "").strip()
        or not str(event.get("traceId") or "").strip()
        or event.get("succeeded") is not True
        for event in events
    ):
        raise ValueError("remote API evidence report lacks successful requestId/traceId events")
    feedback_events = evidence.get("feedbackEvents")
    if not isinstance(feedback_events, list):
        raise ValueError("remote API evidence report lacks typed feedback events")
    click_events = [
        event
        for event in feedback_events
        if isinstance(event, dict) and event.get("eventType") == "click"
    ]
    dwell_events = [
        event
        for event in feedback_events
        if isinstance(event, dict) and event.get("eventType") == "dwell"
    ]
    if (
        len(click_events) != 1
        or not str(click_events[0].get("objectId") or "").strip()
        or not str(click_events[0].get("target") or "").strip()
        or not isinstance(click_events[0].get("rankPosition"), int)
        or click_events[0]["rankPosition"] <= 0
        or len(dwell_events) != 1
        or not str(dwell_events[0].get("objectId") or "").strip()
        or dwell_events[0].get("dwellMs") != 3000
    ):
        raise ValueError(
            "remote API evidence report must assert one ranked click and 3-second dwell"
        )
    return {
        "reportPath": _output_evidence_ref(path),
        "searchRequestId": evidence["searchRequestId"],
        "events": events,
        "feedbackEvents": feedback_events,
        "tagFilter": tag_filter,
    }


def _output_evidence_ref(path: Path) -> str:
    """Expose runtime output references relative to QWQ_OUTPUT_ROOT, not repo root."""
    relative = repo_relative(path)
    prefix = ".qwq_output/"
    return relative[len(prefix) :] if relative.startswith(prefix) else relative
