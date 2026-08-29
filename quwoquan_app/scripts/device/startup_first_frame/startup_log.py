"""启动日志解析：sequence 事件、watchdog 证据与终态分类。"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_qwqstartup_log(raw: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for key in (
        "android_activity_on_create",
        "android_flutter_engine_configured",
        "android_flutter_first_frame",
        "android_flutter_ui_displayed",
        "ios_flutter_first_frame",
    ):
        match = re.search(rf"{re.escape(key)} elapsedMs=(\d+)", raw)
        if match:
            values[key] = int(match.group(1))
    displayed_match = re.search(
        r"Displayed com\.quwoquan\.quwoquan_app/\.MainActivity for user \d+: \+((?:(\d+)s)?(\d+)ms)",
        raw,
    )
    if displayed_match:
        seconds = int(displayed_match.group(2) or "0")
        milliseconds = int(displayed_match.group(3))
        values["android_activity_displayed_ms"] = seconds * 1000 + milliseconds
    return values


def parse_startup_sequence_log(raw: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        json_marker = "startup_event "
        if json_marker in line:
            payload = line.split(json_marker, 1)[1].strip()
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError:
                decoded = None
            if (
                isinstance(decoded, dict)
                and decoded.get("eventName") == "startup_welcome_sequence"
            ):
                events.append(decoded)
            continue
        marker = next(
            (
                candidate
                for candidate in ("startup_welcome_sequence ", "startup_probe ")
                if candidate in line
            ),
            None,
        )
        if marker is None:
            continue
        payload = line.split(marker, 1)[1]
        event: dict[str, Any] = {}
        for key, value in re.findall(r"([A-Za-z][A-Za-z0-9]*)=([^\s]+)", payload):
            if re.fullmatch(r"-?\d+", value):
                event[key] = int(value)
            elif value in ("true", "false"):
                event[key] = value == "true"
            else:
                event[key] = value
        if event:
            events.append(event)

    finished = next(
        (event for event in reversed(events) if event.get("phase") == "finished"),
        None,
    )
    shell = next(
        (
            event
            for event in reversed(events)
            if event.get("phase") == "main_shell_first_paint"
        ),
        None,
    )
    overlay_removed = next(
        (
            event
            for event in reversed(events)
            if event.get("phase") == "welcome_overlay_removed"
        ),
        None,
    )
    safe_recovery = next(
        (
            event
            for event in reversed(events)
            if event.get("phase") == "safe_recovery_shown"
        ),
        None,
    )
    return {
        "events": events,
        "motionSpec": next(
            (
                event.get("motionSpec")
                for event in reversed(events)
                if event.get("motionSpec") is not None
            ),
            None,
        ),
        "firstVisibleMs": next(
            (
                event.get("elapsedSinceProcessStartMs")
                for event in events
                if event.get("phase") == "nativeStatic"
            ),
            None,
        ),
        "welcomeExitMs": finished.get("welcomeExitMs") if finished else None,
        "exitReason": finished.get("exitReason") if finished else None,
        "replayCount": next(
            (
                event.get("replayCount")
                for event in reversed(events)
                if event.get("phase") == "finished"
                and event.get("replayCount") is not None
            ),
            None,
        ),
        "shellFirstPaintMs": shell.get("shellFirstPaintMs") if shell else None,
        "overlayRemovedMs": (
            overlay_removed.get("overlayRemovedMs") if overlay_removed else None
        ),
        "safeRecoveryShown": safe_recovery is not None,
    }


def _native_watchdog_timeout_logged(raw_log: str) -> bool:
    return (
        "android_native_first_frame_timeout" in raw_log
        or "ios_native_first_frame_timeout" in raw_log
        or "web_first_frame_timeout" in raw_log
    )


def _flutter_safe_terminal_confirmed(raw_log: str) -> bool:
    """Flutter 已到可操作终态时，原生 watchdog 不得覆盖已可见 Flutter UI。"""

    return (
        "android_startup_safe_terminal_race_dismissed" in raw_log
        or "ios_startup_safe_terminal_race_dismissed" in raw_log
        or "android_startup_safe_terminal surface=" in raw_log
        or "ios_startup_safe_terminal surface=" in raw_log
        or "android_startup_safe_terminal_rejected surface=" in raw_log
        or "ios_startup_safe_terminal_rejected surface=" in raw_log
        or '"eventName":"startup_safe_terminal"' in raw_log
        or '"eventName": "startup_safe_terminal"' in raw_log
    )


def extract_dart_startup_attempts(raw_log: str) -> list[dict[str, Any]]:
    """Extract one bounded record for each Dart isolate startup attempt."""

    attempts: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?:android|ios)_dart_startup_attempt "
        r"attemptId=(?P<attemptId>[A-Za-z0-9_-]+)"
        r"(?:\s+launchProvenance=(?P<launchProvenance>[A-Za-z0-9_-]+))?"
        r"(?:\s+runtimeConfigSupplyMode=(?P<runtimeConfigSupplyMode>[A-Za-z0-9_-]+))?"
        r"(?:\s+hotRestart=(?P<hotRestart>true|false))?"
        r"(?:\s+configurationState=(?P<configurationState>[A-Za-z0-9_-]+))?"
        r"(?:\s+effectiveLaunchManifestDigest="
        r"(?P<effectiveLaunchManifestDigest>sha256:[0-9a-f]{64}))?"
        r"(?:\s+missingDefineKeys=(?P<missingDefineKeys>[A-Z0-9_,]+))?"
    )
    for match in pattern.finditer(raw_log):
        attempts.append(
            {
                key: value
                for key, value in match.groupdict().items()
                if value is not None
            }
        )
    return attempts


def extract_startup_watchdog_evidence(raw_log: str) -> dict[str, Any]:
    """Emit the same attempt-level fields for Android and iOS probe evidence."""

    renderer = re.search(
        r"(?:android|ios)_flutter_first_frame elapsedMs=(\d+).*source=\S+",
        raw_log,
    )
    safe_terminal = re.search(
        r"(?:android|ios)_startup_safe_terminal "
        r"surface=(?P<surface>[a-z_]+) "
        r"(?:elapsedMs|reportedElapsedMs)=(?P<elapsedMs>\d+)",
        raw_log,
    )
    reported_safe_terminal = re.search(
        r"(?:android|ios)_startup_safe_terminal surface=[a-z_]+ "
        r"reportedElapsedMs=(\d+)",
        raw_log,
    )
    native_received_safe_terminal = re.search(
        r"(?:android|ios)_startup_safe_terminal .*?receivedMs=(\d+)",
        raw_log,
    )
    dart_attempt = re.search(
        r"(?:android|ios)_dart_startup_attempt "
        r"attemptId=(?P<attemptId>[A-Za-z0-9_-]+)"
        r"(?:\s+launchProvenance=(?P<launchProvenance>[A-Za-z0-9_-]+))?"
        r"(?:\s+runtimeConfigSupplyMode=(?P<runtimeConfigSupplyMode>[A-Za-z0-9_-]+))?"
        r"(?:\s+hotRestart=(?P<hotRestart>true|false))?"
        r"(?:\s+configurationState=(?P<configurationState>[A-Za-z0-9_-]+))?"
        r"(?:\s+effectiveLaunchManifestDigest="
        r"(?P<effectiveLaunchManifestDigest>sha256:[0-9a-f]{64}))?"
        r"(?:\s+missingDefineKeys=(?P<missingDefineKeys>[A-Z0-9_,]+))?",
        raw_log,
    )
    attempt = re.search(
        r'(?:attemptId=|"attemptId"\s*:\s*")([A-Za-z0-9_-]+)',
        raw_log,
    )
    failure_code = re.search(
        r'(?:failureCode=|"failureCode"\s*:\s*")([A-Za-z0-9_.-]+)',
        raw_log,
    )
    attempt_id = (
        dart_attempt.group("attemptId")
        if dart_attempt
        else attempt.group(1)
        if attempt
        else None
    )
    telemetry_acks = re.findall(
        r"startup_telemetry_ack "
        r"attemptId=([A-Za-z0-9_-]+) "
        r"acceptedCount=(\d+) duplicateCount=(\d+)",
        raw_log,
    )
    telemetry_acknowledged = any(
        acknowledged_attempt == attempt_id
        and int(accepted_count) + int(duplicate_count) > 0
        for acknowledged_attempt, accepted_count, duplicate_count in telemetry_acks
    )
    race_dismissed = "startup_safe_terminal_race_dismissed" in raw_log
    return {
        "rendererFirstFrameMs": int(renderer.group(1)) if renderer else None,
        "safeTerminalMs": (
            int(safe_terminal.group("elapsedMs")) if safe_terminal else None
        ),
        "safeTerminalSurface": (
            safe_terminal.group("surface") if safe_terminal else None
        ),
        "reportedSafeTerminalMs": (
            int(reported_safe_terminal.group(1))
            if reported_safe_terminal
            else int(safe_terminal.group("elapsedMs"))
            if safe_terminal
            else None
        ),
        "nativeReceivedSafeTerminalMs": (
            int(native_received_safe_terminal.group(1))
            if native_received_safe_terminal
            else None
        ),
        "watchdogOutcome": (
            "race_dismissed"
            if race_dismissed
            else "native_recovery"
            if _native_watchdog_timeout_logged(raw_log)
            else "not_triggered"
        ),
        "canonicalTerminal": None,
        "attemptId": attempt_id,
        "launchProvenance": (
            dart_attempt.group("launchProvenance") if dart_attempt else None
        ),
        "runtimeConfigSupplyMode": (
            dart_attempt.group("runtimeConfigSupplyMode") if dart_attempt else None
        ),
        "hotRestart": (
            dart_attempt.group("hotRestart") == "true"
            if dart_attempt and dart_attempt.group("hotRestart") is not None
            else None
        ),
        "runtimeConfigurationState": (
            dart_attempt.group("configurationState") if dart_attempt else None
        ),
        "effectiveLaunchManifestDigest": (
            dart_attempt.group("effectiveLaunchManifestDigest")
            if dart_attempt
            else None
        ),
        "missingDefineKeys": (
            dart_attempt.group("missingDefineKeys") if dart_attempt else None
        ),
        "failureCode": failure_code.group(1) if failure_code else "",
        "telemetryAcknowledged": telemetry_acknowledged,
    }


def _safe_terminal_within_deadline(
    evidence: dict[str, Any],
    deadline_ms: int,
) -> bool:
    reported = evidence.get("reportedSafeTerminalMs")
    received = evidence.get("nativeReceivedSafeTerminalMs")
    return (
        isinstance(reported, int)
        and reported <= deadline_ms
        and isinstance(received, int)
        and received <= deadline_ms
    )


def classify_startup_terminal(
    raw_log: str,
    sequence: dict[str, Any],
) -> str:
    """Return one of routerShell/safeRecovery/nativeRecovery/unresolved.

    A six-second sample is only meaningful when it reaches one of these
    explicit visual terminal surfaces. A static native branded background is
    never a terminal surface.
    """

    watchdog = extract_startup_watchdog_evidence(raw_log)
    terminal_surface = watchdog.get("safeTerminalSurface")
    native_surface_required = re.search(
        r"(?:android|ios)_(?:dart_startup_attempt|startup_safe_terminal)",
        raw_log,
    ) is not None
    if sequence.get("safeRecoveryShown") or terminal_surface in {
        "safe_recovery",
        "flutter_recovery",
    }:
        return "safeRecovery"
    if (
        (not native_surface_required or terminal_surface == "router_shell")
        and sequence.get("shellFirstPaintMs") is not None
        and sequence.get("overlayRemovedMs") is not None
    ):
        return "routerShell"
    # watchdog timeout 与 Flutter safe_terminal 可能差几毫秒；若 Flutter 已确认
    # 安全终态（或已撤销竞态恢复面），不得再把样本判成 nativeRecovery。
    if _native_watchdog_timeout_logged(raw_log) and not _flutter_safe_terminal_confirmed(
        raw_log
    ):
        return "nativeRecovery"
    return "unresolved"
