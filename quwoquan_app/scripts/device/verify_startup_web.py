#!/usr/bin/env python3
"""20-run headless Web cold-start probe for the 3s/6s welcome contract."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
DEFAULT_OUTPUT_DIR = (
    ROOT / ".qwq_output/env/alpha/runs/startup_first_frame/web_probe"
)
DEFAULT_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


class CdpClient:
    """Minimal dependency-free WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, websocket_url: str) -> None:
        parsed = urlparse(websocket_url)
        if parsed.scheme != "ws" or parsed.hostname is None or parsed.port is None:
            raise ValueError(f"Unsupported CDP websocket URL: {websocket_url}")
        self._socket = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
        self._socket.settimeout(10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {parsed.path or '/'} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._socket.sendall(request.encode("ascii"))
        response = self._receive_until(b"\r\n\r\n")
        if not response.startswith(b"HTTP/1.1 101"):
            raise RuntimeError(f"CDP WebSocket upgrade failed: {response[:120]!r}")
        self._next_id = 1

    def close(self) -> None:
        self._socket.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send_text(
            json.dumps(
                {"id": request_id, "method": method, "params": params or {}},
                separators=(",", ":"),
            )
        )
        while True:
            message = json.loads(self._receive_text())
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})

    def _receive_until(self, marker: bytes) -> bytes:
        data = bytearray()
        while marker not in data:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise ConnectionError("CDP WebSocket closed during handshake")
            data.extend(chunk)
        return bytes(data)

    def _send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        length = len(payload)
        header = bytearray([0x81])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126])
            header.extend(length.to_bytes(2, "big"))
        else:
            header.extend([0x80 | 127])
            header.extend(length.to_bytes(8, "big"))
        header.extend(mask)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self._socket.sendall(header + masked)

    def _receive_text(self) -> str:
        fragments = bytearray()
        while True:
            first, second = self._receive_exact(2)
            final = bool(first & 0x80)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(self._receive_exact(2), "big")
            elif length == 127:
                length = int.from_bytes(self._receive_exact(8), "big")
            masked = bool(second & 0x80)
            mask = self._receive_exact(4) if masked else b""
            payload = self._receive_exact(length)
            if masked:
                payload = bytes(
                    value ^ mask[index % 4] for index, value in enumerate(payload)
                )
            if opcode == 0x8:
                raise ConnectionError("CDP WebSocket closed")
            if opcode == 0x9:
                self._send_control(0xA, payload)
                continue
            if opcode in (0x1, 0x0):
                fragments.extend(payload)
                if final:
                    return fragments.decode("utf-8")

    def _send_control(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self._socket.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + mask + masked)

    def _receive_exact(self, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = self._socket.recv(length - len(data))
            if not chunk:
                raise ConnectionError("CDP WebSocket closed")
            data.extend(chunk)
        return bytes(data)


def percentile(values: list[int], ratio: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * ratio)
    return ordered[max(0, min(index, len(ordered) - 1))]


def parse_startup_report(dom: str) -> list[dict[str, Any]]:
    match = re.search(r'data-qwq-startup-report="([^"]+)"', dom)
    if not match:
        return []
    encoded = html.unescape(match.group(1))
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        raw = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return raw if isinstance(raw, list) else []


def decode_startup_report(encoded: str | None) -> list[dict[str, Any]]:
    if not encoded:
        return []
    try:
        raw = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return raw if isinstance(raw, list) else []


def terminal_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(events)
            if event.get("eventName") == "startup_welcome_sequence"
            and event.get("phase") == "finished"
        ),
        None,
    )


def shell_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(events)
            if event.get("eventName") == "startup_welcome_sequence"
            and event.get("phase") == "main_shell_first_paint"
        ),
        None,
    )


def overlay_removed_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(events)
            if event.get("eventName") == "startup_welcome_sequence"
            and event.get("phase") == "welcome_overlay_removed"
        ),
        None,
    )


def first_frame_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in events
            if event.get("eventName") == "startup_welcome_sequence"
            and event.get("phase") == "nativeStatic"
        ),
        None,
    )


def startup_event(
    events: list[dict[str, Any]],
    event_name: str,
) -> dict[str, Any] | None:
    return next(
        (
            event
            for event in reversed(events)
            if event.get("eventName") == event_name
        ),
        None,
    )


def run_once(
    *,
    chrome: Path,
    url: str,
    virtual_time_budget_ms: int,
    output_dir: Path,
    run_index: int,
) -> dict[str, Any]:
    screenshot = output_dir / f"web-run-{run_index:02d}.png"
    process: subprocess.Popen[str] | None = None
    cdp: CdpClient | None = None
    events: list[dict[str, Any]] = []
    chrome_exit_code: int | None = None
    with tempfile.TemporaryDirectory(prefix="qwq-web-startup-") as profile:
        profile_path = Path(profile)
        process = subprocess.Popen(
            [
                str(chrome),
                "--headless=new",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-cache",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                "--window-size=393,852",
                url,
            ],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            port = _wait_for_devtools_port(profile_path, process)
            target = _wait_for_page_target(port, url)
            cdp = CdpClient(target["webSocketDebuggerUrl"])
            deadline = time.monotonic() + max(8.0, virtual_time_budget_ms / 1000 + 2)
            while time.monotonic() < deadline:
                result = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": (
                            "document.documentElement.getAttribute("
                            "'data-qwq-startup-report') || ''"
                        ),
                        "returnByValue": True,
                    },
                )
                encoded = result.get("result", {}).get("value")
                events = decode_startup_report(encoded)
                if (
                    terminal_event(events) is not None
                    and shell_event(events) is not None
                    and overlay_removed_event(events) is not None
                ):
                    break
                time.sleep(0.05)
            capture = cdp.call("Page.captureScreenshot", {"format": "png"})
            screenshot.write_bytes(base64.b64decode(capture["data"]))
        finally:
            if cdp is not None:
                cdp.close()
            process.terminate()
            try:
                chrome_exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                chrome_exit_code = process.wait(timeout=5)

    events_path = output_dir / f"web-run-{run_index:02d}.json"
    events_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    first = first_frame_event(events)
    terminal = terminal_event(events)
    shell = shell_event(events)
    overlay_removed = overlay_removed_event(events)
    flutter_first_frame = startup_event(events, "flutter_first_frame")
    safe_terminal = startup_event(events, "startup_safe_terminal")
    dart_attempt = startup_event(events, "startup_attempt_started")
    race_dismissed = startup_event(
        events,
        "web_startup_safe_terminal_race_dismissed",
    )
    native_recovery = startup_event(events, "web_first_frame_timeout") or startup_event(
        events,
        "web_startup_safe_terminal_timeout",
    )
    failure_code = next(
        (
            str(event["failureCode"])
            for event in events
            if event.get("failureCode")
        ),
        "",
    )
    attempt_id = next(
        (
            str(event["attemptId"])
            for event in events
            if event.get("attemptId")
        ),
        None,
    )
    return {
        "run": run_index,
        "chromeExitCode": chrome_exit_code,
        "ttidMs": first.get("elapsedSinceProcessStartMs") if first else None,
        "welcomeExitMs": terminal.get("welcomeExitMs") if terminal else None,
        "shellFirstPaintMs": shell.get("shellFirstPaintMs") if shell else None,
        "overlayRemovedMs": (
            overlay_removed.get("overlayRemovedMs") if overlay_removed else None
        ),
        "replayCount": terminal.get("replayCount") if terminal else None,
        "exitReason": terminal.get("exitReason") if terminal else None,
        "motionSpec": terminal.get("motionSpec") if terminal else None,
        "eventCount": len(events),
        "attemptId": (
            str(dart_attempt["attemptId"])
            if dart_attempt and dart_attempt.get("attemptId")
            else attempt_id
        ),
        "launchMode": dart_attempt.get("launchMode") if dart_attempt else None,
        "hotRestart": dart_attempt.get("hotRestart") if dart_attempt else None,
        "runtimeConfigurationState": (
            dart_attempt.get("configurationState") if dart_attempt else None
        ),
        "missingDefineKeys": (
            dart_attempt.get("missingDefineKeys") if dart_attempt else None
        ),
        "failureCode": failure_code,
        "rendererFirstFrameMs": (
            flutter_first_frame.get("elapsedMs") if flutter_first_frame else None
        ),
        "safeTerminalMs": (
            safe_terminal.get("elapsedMs") if safe_terminal else None
        ),
        "reportedSafeTerminalMs": (
            safe_terminal.get("elapsedMs") if safe_terminal else None
        ),
        "nativeReceivedSafeTerminalMs": (
            safe_terminal.get("elapsedMs") if safe_terminal else None
        ),
        "watchdogOutcome": (
            "race_dismissed"
            if race_dismissed is not None
            else "native_recovery"
            if native_recovery is not None
            else "not_triggered"
        ),
        "canonicalTerminal": (
            "routerShell"
            if shell is not None and overlay_removed is not None
            else "nativeRecovery"
            if native_recovery is not None
            else "unresolved"
        ),
        "screenshot": str(screenshot),
        "events": str(events_path),
    }


def _wait_for_devtools_port(profile: Path, process: subprocess.Popen[str]) -> int:
    active_port = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Chrome exited before CDP was ready: {process.returncode}")
        if active_port.exists():
            lines = active_port.read_text(encoding="utf-8").splitlines()
            if lines:
                return int(lines[0])
        time.sleep(0.05)
    raise TimeoutError("Chrome DevTools port was not ready within 8 seconds")


def _wait_for_page_target(port: int, expected_url: str) -> dict[str, Any]:
    endpoint = f"http://127.0.0.1:{port}/json/list"
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            with urlopen(endpoint, timeout=1) as response:
                targets = json.load(response)
        except (OSError, ValueError):
            time.sleep(0.05)
            continue
        pages = [target for target in targets if target.get("type") == "page"]
        exact = next((target for target in pages if target.get("url") == expected_url), None)
        if exact is not None:
            return exact
        if pages:
            return pages[0]
        time.sleep(0.05)
    raise TimeoutError("Chrome page target was not ready within 8 seconds")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--chrome", default=str(DEFAULT_CHROME))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--virtual-time-budget-ms", type=int, default=6500)
    parser.add_argument("--ttid-p95-ms", type=int, default=2000)
    parser.add_argument("--shell-p95-ms", type=int, default=3000)
    parser.add_argument("--welcome-exit-hard-ms", type=int, default=6000)
    parser.add_argument(
        "--runtime-env",
        choices=("alpha", "beta", "gamma", "prod"),
        default="",
    )
    parser.add_argument("--matrix-evidence-root", default="")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    chrome = Path(args.chrome)
    if not chrome.exists() and shutil.which(args.chrome) is None:
        raise FileNotFoundError(f"Chrome executable not found: {chrome}")
    if args.runs < 20:
        raise ValueError("Web commercial startup UAT requires at least 20 runs")

    output_dir = Path(args.output_dir) / time.strftime("%Y%m%dT%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = [
        run_once(
            chrome=chrome,
            url=args.url,
            virtual_time_budget_ms=args.virtual_time_budget_ms,
            output_dir=output_dir,
            run_index=index,
        )
        for index in range(1, args.runs + 1)
    ]

    ttid_values = [sample["ttidMs"] for sample in samples if sample["ttidMs"] is not None]
    shell_values = [
        sample["shellFirstPaintMs"]
        for sample in samples
        if sample["shellFirstPaintMs"] is not None
    ]
    overlay_values = [
        sample["overlayRemovedMs"]
        for sample in samples
        if sample["overlayRemovedMs"] is not None
    ]
    exits = [sample["welcomeExitMs"] for sample in samples]
    overlay_removals = [sample["overlayRemovedMs"] for sample in samples]
    motion_spec_current = all(
        sample.get("motionSpec") == "petal_bloom" for sample in samples
    )
    ttid_p50 = percentile(ttid_values, 0.5)
    ttid_p95 = percentile(ttid_values, 0.95)
    shell_p50 = percentile(shell_values, 0.5)
    shell_p95 = percentile(shell_values, 0.95)
    overlay_p50 = percentile(overlay_values, 0.5)
    overlay_p95 = percentile(overlay_values, 0.95)
    complete = (
        len(ttid_values) == args.runs
        and len(shell_values) == args.runs
        and len(overlay_values) == args.runs
    )
    hard_exit_passed = all(
        isinstance(value, int) and value <= args.welcome_exit_hard_ms
        for value in exits
    )
    overlay_removal_passed = all(
        isinstance(value, int) and value <= args.welcome_exit_hard_ms
        for value in overlay_removals
    )
    passed = (
        complete
        and ttid_p95 is not None
        and ttid_p95 <= args.ttid_p95_ms
        and shell_p95 is not None
        and shell_p95 <= args.shell_p95_ms
        and hard_exit_passed
        and overlay_removal_passed
        and motion_spec_current
    )
    report = {
        "schema": "startup-web-report",
        "platform": "web",
        "motionSpec": "petal_bloom",
        "motionSpecCurrent": motion_spec_current,
        "runs": args.runs,
        "passed": passed,
        "p50": {
            "ttidMs": ttid_p50,
            "shellFirstPaintMs": shell_p50,
            "overlayRemovedMs": overlay_p50,
        },
        "p95": {
            "ttidMs": ttid_p95,
            "shellFirstPaintMs": shell_p95,
            "overlayRemovedMs": overlay_p95,
        },
        "welcomeExitOverHardCount": sum(
            1
            for value in exits
            if not isinstance(value, int) or value > args.welcome_exit_hard_ms
        ),
        "overlayRemovalOverHardCount": sum(
            1
            for value in overlay_removals
            if not isinstance(value, int) or value > args.welcome_exit_hard_ms
        ),
        "samples": samples,
    }
    report_path = output_dir / "startup_web_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if args.matrix_evidence_root:
        if not args.runtime_env:
            raise ValueError("--runtime-env is required with --matrix-evidence-root")
        attempt_ids = [
            str(sample["attemptId"])
            for sample in samples
            if sample.get("attemptId")
        ]
        renderer_values = [
            int(sample["rendererFirstFrameMs"])
            for sample in samples
            if sample.get("rendererFirstFrameMs") is not None
        ]
        safe_values = [
            int(sample["safeTerminalMs"])
            for sample in samples
            if sample.get("safeTerminalMs") is not None
        ]
        evidence = {
            "runtimeEnv": args.runtime_env,
            "platform": "web",
            "attemptId": attempt_ids[0] if attempt_ids else None,
            "attemptIds": attempt_ids,
            "rendererFirstFrameMs": max(renderer_values) if renderer_values else None,
            "safeTerminalMs": max(safe_values) if safe_values else None,
            "reportedSafeTerminalMs": max(safe_values) if safe_values else None,
            "nativeReceivedSafeTerminalMs": max(safe_values) if safe_values else None,
            "launchMode": next(
                (
                    sample.get("launchMode")
                    for sample in samples
                    if sample.get("launchMode")
                ),
                None,
            ),
            "runtimeConfigurationState": next(
                (
                    sample.get("runtimeConfigurationState")
                    for sample in samples
                    if sample.get("runtimeConfigurationState")
                ),
                None,
            ),
            "missingDefineKeys": next(
                (
                    sample.get("missingDefineKeys")
                    for sample in samples
                    if sample.get("missingDefineKeys")
                ),
                None,
            ),
            "failureCode": next(
                (
                    sample.get("failureCode")
                    for sample in samples
                    if sample.get("failureCode")
                ),
                "",
            ),
            "watchdogOutcome": (
                "native_recovery"
                if any(
                    sample.get("watchdogOutcome") == "native_recovery"
                    for sample in samples
                )
                else "race_dismissed"
                if any(
                    sample.get("watchdogOutcome") == "race_dismissed"
                    for sample in samples
                )
                else "not_triggered"
            ),
            "canonicalTerminal": (
                "routerShell"
                if all(
                    sample.get("canonicalTerminal") == "routerShell"
                    for sample in samples
                )
                else "unresolved"
            ),
            "sourceReport": str(report_path),
        }
        matrix_dir = Path(args.matrix_evidence_root) / args.runtime_env
        matrix_dir.mkdir(parents=True, exist_ok=True)
        (matrix_dir / "web.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
