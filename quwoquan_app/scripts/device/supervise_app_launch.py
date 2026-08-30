#!/usr/bin/env python3
"""Run Flutter once and project compile/install/launch milestones into a receipt."""

from __future__ import annotations

import argparse
import hashlib
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_app.scripts.device.startup_first_frame import (
    extract_dart_startup_attempts,
)
from quwoquan_app.scripts.device.startup_terminal_receipt import (
    build_startup_terminal_receipt,
    canonical_document_digest,
    canonical_terminal_for_surface,
    marker_digest,
    read_startup_terminal_receipt,
    write_startup_terminal_receipt,
)
from quwoquan_ops.cli.lib.app_launch_attempt import (
    CONFIGURATION_STATES,
    LAUNCH_BLOCKERS,
    create_app_launch_attempt,
    read_app_launch_attempt,
    record_app_launch_attempt_observation,
    record_app_launch_attempt_warning,
    transition_app_launch_attempt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    parser.add_argument("--build-profile", choices=("nonprod", "prod"), required=True)
    parser.add_argument("--build-mode", choices=("debug", "profile", "release"), required=True)
    parser.add_argument(
        "--run-mode",
        choices=("content-live", "ui-only", "release-artifact"),
        required=True,
    )
    parser.add_argument("--device", required=True)
    parser.add_argument("--application-id", default="")
    parser.add_argument("--launch-provenance", required=True)
    parser.add_argument("--runtime-config-supply-mode", required=True)
    parser.add_argument("--runtime-config-trust-envelope-digest", required=True)
    parser.add_argument("--runtime-config-package-digest", required=True)
    parser.add_argument("--flutter-version", required=True)
    parser.add_argument("--command-resolution-digest", required=True)
    parser.add_argument("--artifact-path", type=Path)
    parser.add_argument("--artifact-digest", default="")
    parser.add_argument("--launch-digest", default="")
    parser.add_argument("--log-ref", action="append", default=[])
    parser.add_argument("--warning", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--exit-after-launch", action="store_true")
    parser.add_argument("--require-safe-terminal", action="store_true")
    parser.add_argument("--startup-terminal-receipt", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


_PHASE_MARKER = re.compile(
    r"^QWQ_APP_LAUNCH_PHASE status="
    r"(compiled|installing|installed|configuring|configured|launching|launched)$"
)
_DEPENDENCY_BLOCKER_MARKER = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<code>APP\.DEPENDENCY\.[a-z_]+)(?![A-Za-z0-9_.])"
)


def _canonical_dependency_blocker_from(line: str) -> str:
    """Project only registered launch dependency blockers from child output."""

    for match in _DEPENDENCY_BLOCKER_MARKER.finditer(line):
        code = match.group("code")
        if code in LAUNCH_BLOCKERS:
            return code
    return ""


class _ArtifactIdentityError(RuntimeError):
    def __init__(self, blocker: str, detail: str) -> None:
        super().__init__(detail)
        self.blocker = blocker


class _SafeTerminalIdentityError(RuntimeError):
    pass


_SAFE_TERMINAL_MARKER = re.compile(
    r"(?P<platform>android|ios)_startup_safe_terminal "
    r"surface=(?P<surface>[a-z_]+) "
    r"(?:reportedElapsedMs|elapsedMs)=\d+.*?"
    r"attemptId=(?P<attemptId>[A-Za-z0-9_-]+).*?"
    r"launchProvenance=(?P<launchProvenance>[A-Za-z0-9_-]+).*?"
    r"runtimeConfigSupplyMode=(?P<runtimeConfigSupplyMode>[A-Za-z0-9_-]+)"
)
_SAFE_TERMINAL_PREFIX = re.compile(
    r"(?P<platform>android|ios)_startup_safe_terminal "
)
_REJECTED_SAFE_TERMINAL_MARKER = re.compile(
    r"(?P<platform>android|ios)_startup_safe_terminal_rejected "
    r"surface=(?P<surface>[a-z_]+).*?"
    r"attemptId=(?P<attemptId>[A-Za-z0-9_-]+).*?"
    r"launchProvenance=(?P<launchProvenance>[A-Za-z0-9_-]+).*?"
    r"runtimeConfigSupplyMode=(?P<runtimeConfigSupplyMode>[A-Za-z0-9_-]+)"
)


class _SafeTerminalTracker:
    def __init__(
        self,
        *,
        required: bool,
        receipt_path: Path | None,
        platform: str,
        launch_provenance: str,
        runtime_config_supply_mode: str,
        launch_digest: str,
    ) -> None:
        if required and receipt_path is None:
            raise _SafeTerminalIdentityError(
                "strict launch requires a safe-terminal receipt path"
            )
        self.required = required
        self.receipt_path = receipt_path
        self.platform = platform
        self.launch_provenance = launch_provenance
        self.runtime_config_supply_mode = runtime_config_supply_mode
        self.launch_digest = launch_digest
        self.dart_attempt: dict[str, str] | None = None
        self.dart_marker = ""

    def observe(self, line: str, launch_attempt: dict[str, object]) -> None:
        if not self.required:
            return
        for raw_attempt in extract_dart_startup_attempts(line):
            attempt = {key: str(value) for key, value in raw_attempt.items()}
            if attempt.get("hotRestart") == "true":
                continue
            expected = {
                "launchProvenance": self.launch_provenance,
                "runtimeConfigSupplyMode": self.runtime_config_supply_mode,
                "configurationState": "complete",
            }
            if any(attempt.get(field) != value for field, value in expected.items()):
                raise _SafeTerminalIdentityError(
                    "cold startup attempt identity/configuration mismatch"
                )
            observed_launch_digest = attempt.get(
                "effectiveLaunchManifestDigest", ""
            )
            if not observed_launch_digest:
                raise _SafeTerminalIdentityError(
                    "cold startup attempt effective manifest is missing"
                )
            if observed_launch_digest != self.launch_digest:
                raise _SafeTerminalIdentityError(
                    "cold startup attempt effective manifest mismatch"
                )
            self.dart_attempt = attempt
            self.dart_marker = line.strip()

        marker = _SAFE_TERMINAL_MARKER.search(line)
        rejected_marker = _REJECTED_SAFE_TERMINAL_MARKER.search(line)
        if rejected_marker is not None:
            self._validate_terminal_identity(rejected_marker.groupdict())
            raise _SafeTerminalIdentityError(
                "startup safe-terminal surface is "
                f"{rejected_marker.group('surface')!r}; expected router_shell"
            )
        if _SAFE_TERMINAL_PREFIX.search(line) is not None and marker is None:
            raise _SafeTerminalIdentityError(
                "startup safe-terminal surface is missing or invalid; "
                "expected router_shell"
            )
        if marker is None:
            return
        terminal_identity = marker.groupdict()
        if terminal_identity.get("surface") != "router_shell":
            raise _SafeTerminalIdentityError(
                "startup safe-terminal surface is "
                f"{terminal_identity.get('surface')!r}; expected router_shell"
            )
        expected = self._validate_terminal_identity(terminal_identity)
        assert self.receipt_path is not None
        if self.receipt_path.exists() or self.receipt_path.is_symlink():
            existing = read_startup_terminal_receipt(
                self.receipt_path,
                launch_attempt=launch_attempt,
            )
            if existing["startupAttemptId"] != expected["attemptId"]:
                raise _SafeTerminalIdentityError(
                    "startup safe-terminal attemptId drifted"
                )
            return
        raw_marker = self.dart_marker + "\n" + line.strip()
        surface = str(terminal_identity["surface"])
        observed_launch_attempt = dict(launch_attempt)
        observed_launch_attempt["launchDigest"] = self.dart_attempt[
            "effectiveLaunchManifestDigest"
        ]
        receipt = build_startup_terminal_receipt(
            launch_attempt=observed_launch_attempt,
            startup_attempt_id=str(expected["attemptId"] or ""),
            configuration_state="complete",
            surface=surface,
            canonical_terminal=canonical_terminal_for_surface(surface),
            hot_restart=False,
            observed_marker_digest=marker_digest(raw_marker),
        )
        write_startup_terminal_receipt(self.receipt_path, receipt)

    def _validate_terminal_identity(
        self,
        terminal_identity: dict[str, str],
    ) -> dict[str, str | None]:
        if self.dart_attempt is None:
            raise _SafeTerminalIdentityError(
                "startup safe-terminal was observed before its cold attempt"
            )
        expected = {
            "platform": self.platform,
            "attemptId": self.dart_attempt.get("attemptId"),
            "launchProvenance": self.launch_provenance,
            "runtimeConfigSupplyMode": self.runtime_config_supply_mode,
        }
        if any(terminal_identity.get(field) != value for field, value in expected.items()):
            raise _SafeTerminalIdentityError(
                "startup safe-terminal identity mismatch"
            )
        return expected

    def ready(
        self,
        launch_attempt: dict[str, object],
    ) -> tuple[str, str, str] | None:
        if not self.required:
            return None
        assert self.receipt_path is not None
        if not self.receipt_path.exists() and not self.receipt_path.is_symlink():
            return None
        receipt = read_startup_terminal_receipt(
            self.receipt_path,
            launch_attempt=launch_attempt,
        )
        return (
            str(receipt["startupAttemptId"]),
            canonical_document_digest(receipt),
            str(self.receipt_path),
        )


def _artifact_payload_digest(path: Path, platform: str) -> str:
    """Hash the exact canonical build payload without accepting proxy identity.

    文件与目录算法和 AppArtifact packager/readback 一致。额外的前后 stat
    snapshot 只用于检测摘要窗口内的并发改写，不进入 digest 本身。
    """

    if not path.is_absolute() or path.is_symlink():
        raise OSError("artifact path must be an absolute non-symlink path")
    if platform == "android":
        if path.suffix != ".apk" or not path.is_file():
            raise OSError("Android canonical build artifact is not a regular APK")
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if identity_before != identity_after:
            raise OSError("Android APK changed during artifact readback")
        return "sha256:" + digest.hexdigest()
    if platform != "ios" or path.suffix != ".app" or not path.is_dir():
        raise OSError("iOS canonical build artifact is not an App bundle")

    def snapshot() -> tuple[tuple[object, ...], ...]:
        entries: list[tuple[object, ...]] = []
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            stat = child.stat()
            entries.append(
                (
                    child.relative_to(path).as_posix(),
                    stat.st_dev,
                    stat.st_ino,
                    stat.st_size,
                    stat.st_mtime_ns,
                )
            )
        return tuple(entries)

    before = snapshot()
    if not before:
        raise OSError("iOS App bundle has no payload files")
    digest = hashlib.sha256()
    for relative, _device, _inode, size, _modified in before:
        encoded_relative = str(relative).encode("utf-8")
        digest.update(len(encoded_relative).to_bytes(8, "big"))
        digest.update(encoded_relative)
        digest.update(int(size).to_bytes(8, "big"))
        with (path / str(relative)).open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    if before != snapshot():
        raise OSError("iOS App bundle changed during artifact readback")
    return "sha256:" + digest.hexdigest()


class _ArtifactIdentityTracker:
    def __init__(
        self,
        *,
        artifact_path: Path | None,
        platform: str,
        declared_digest: str,
    ) -> None:
        self.artifact_path = artifact_path
        self.platform = platform
        self.declared_digest = declared_digest.strip()
        self.compiled_digest = ""

    def capture_compiled(self) -> str:
        if self.artifact_path is None:
            raise _ArtifactIdentityError(
                "APP.LAUNCH.compile_failed",
                "compiled artifact identity path is missing",
            )
        try:
            digest = _artifact_payload_digest(self.artifact_path, self.platform)
        except OSError as error:
            raise _ArtifactIdentityError(
                "APP.LAUNCH.compile_failed",
                f"compiled artifact identity is unavailable: {error}",
            ) from error
        if self.declared_digest and self.declared_digest != digest:
            raise _ArtifactIdentityError(
                "APP.LAUNCH.compile_failed",
                "declared artifact digest does not match compiled payload readback",
            )
        self.compiled_digest = digest
        return digest

    def verify_installed(self) -> None:
        if not self.compiled_digest or self.artifact_path is None:
            raise _ArtifactIdentityError(
                "APP.LAUNCH.install_failed",
                "install reached readback without compiled artifact identity",
            )
        try:
            installed_readback = _artifact_payload_digest(
                self.artifact_path,
                self.platform,
            )
        except OSError as error:
            raise _ArtifactIdentityError(
                "APP.LAUNCH.install_failed",
                f"installed artifact readback is unavailable: {error}",
            ) from error
        if installed_readback != self.compiled_digest:
            raise _ArtifactIdentityError(
                "APP.LAUNCH.install_failed",
                "installed artifact readback differs from compiled artifact digest",
            )


def _advance(
    receipt: Path,
    target: str,
    artifact_identity: _ArtifactIdentityTracker,
) -> None:
    current = str(read_app_launch_attempt(receipt)["status"])
    if current == target:
        return
    if target == "compiled":
        transition_app_launch_attempt(
            receipt,
            target,
            artifact_digest=artifact_identity.capture_compiled(),
        )
        return
    if target == "installed":
        artifact_identity.verify_installed()
    transition_app_launch_attempt(receipt, target)


def _observed_phase_from(line: str) -> str:
    match = _PHASE_MARKER.fullmatch(line.strip())
    return match.group(1) if match is not None else ""


def _failure_for(status: str) -> str:
    if status in {"prepared", "compiling"}:
        return "APP.LAUNCH.compile_failed"
    if status in {"compiled", "installing"}:
        return "APP.LAUNCH.install_failed"
    if status == "installed":
        return "APP.LAUNCH.runtime_config_missing"
    if status == "configuring":
        return "APP.LAUNCH.runtime_config_activation_failed"
    return "APP.LAUNCH.launch_failed"


def _settle_interrupted_attempt(receipt: Path) -> None:
    current = str(read_app_launch_attempt(receipt)["status"])
    if current in {"failed", "runtime_degraded", "stopped"}:
        return
    if current == "launched":
        transition_app_launch_attempt(receipt, "stopped")
        return
    transition_app_launch_attempt(
        receipt,
        "failed",
        first_blocker=_failure_for(current),
    )


def _configuration_state_from(line: str) -> str:
    """Read configurationState off the canonical dart startup attempt line.

    文法只有一处定义：`(android|ios)_dart_startup_attempt`。这里复用
    startup_log 的解析器，不为同一事实另立第二条 marker。
    """

    for attempt in extract_dart_startup_attempts(line):
        state = str(attempt.get("configurationState") or "")
        if state in CONFIGURATION_STATES:
            return state
    return ""


def _settle_runtime_health(receipt: Path) -> None:
    """Settle runtime health once, from what this attempt actually observed.

    运行时健康只有真的到达 launched 才可观测；未启动的 attempt 保持 unobserved，
    不得用编译或安装阶段的结论冒充运行时结论。
    """

    payload = read_app_launch_attempt(receipt)
    launched = any(
        str(item.get("status") or "") == "launched"
        for item in payload["transitions"]
        if isinstance(item, dict)
    )
    if not launched or payload["runtimeHealthStatus"] != "unobserved":
        return
    # A warning is an observed runtime/preflight deficit.  A strict UAT caller
    # must never receive a healthy receipt merely because the warning did not
    # use one particular human-readable prefix.
    degraded = bool(payload["warnings"]) or payload["status"] == "runtime_degraded"
    record_app_launch_attempt_observation(
        receipt,
        runtime_health_status="degraded" if degraded else "healthy",
    )


def main() -> int:
    args = _parser().parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise SystemExit("APP.LAUNCH.compile_failed: missing launch command")

    child: subprocess.Popen[str] | None = None
    log_handles: list[TextIO] = []
    interrupted = False
    timed_out = False
    observed_launch_error = False
    first_dependency_blocker = ""
    artifact_identity_error: _ArtifactIdentityError | None = None
    safe_terminal_error: _SafeTerminalIdentityError | None = None
    pending_launched = False
    completed_after_launch = False
    bounded_stop_failed = False

    def forward(signum: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = True
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    # Install handlers before materializing the prepared receipt. A signal in
    # that preflight window must settle the attempt instead of leaving a
    # permanently non-terminal prepared receipt behind.
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, forward)
    create_app_launch_attempt(
        args.receipt,
        environment=args.environment,
        target=args.target,
        platform=args.platform,
        build_profile=args.build_profile,
        build_mode=args.build_mode,
        run_mode=args.run_mode,
        launch_provenance=args.launch_provenance,
        runtime_config_supply_mode=args.runtime_config_supply_mode,
        runtime_config_trust_envelope_digest=(
            args.runtime_config_trust_envelope_digest
        ),
        runtime_config_package_digest=args.runtime_config_package_digest,
        application_id=args.application_id,
        flutter_version=args.flutter_version,
        command_resolution_digest=args.command_resolution_digest,
        device_id=args.device,
        artifact_digest=args.artifact_digest,
        launch_digest=args.launch_digest,
        warnings=args.warning,
        log_refs=args.log_ref,
    )
    if interrupted:
        _settle_interrupted_attempt(args.receipt)
        return 130
    artifact_identity = _ArtifactIdentityTracker(
        artifact_path=args.artifact_path,
        platform=args.platform,
        declared_digest=args.artifact_digest,
    )
    try:
        safe_terminal = _SafeTerminalTracker(
            required=args.require_safe_terminal,
            receipt_path=args.startup_terminal_receipt,
            platform=args.platform,
            launch_provenance=args.launch_provenance,
            runtime_config_supply_mode=args.runtime_config_supply_mode,
            launch_digest=args.launch_digest,
        )
    except _SafeTerminalIdentityError as error:
        if interrupted:
            _settle_interrupted_attempt(args.receipt)
            return 130
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker="APP.LAUNCH.launch_failed",
            warning=str(error),
        )
        return 2
    if interrupted:
        _settle_interrupted_attempt(args.receipt)
        return 130
    if args.environment == "prod" and args.build_mode != "release":
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker="APP.LAUNCH.prod_debug_forbidden",
        )
        return 2

    def bind_pending_safe_terminal() -> bool:
        """Advance launched only after the current safe-terminal receipt binds."""

        nonlocal completed_after_launch
        if not args.require_safe_terminal or not pending_launched:
            return False
        terminal = safe_terminal.ready(read_app_launch_attempt(args.receipt))
        if terminal is None:
            return False
        attempt_id, evidence_digest, evidence_ref = terminal
        record_app_launch_attempt_observation(
            args.receipt,
            configuration_state="complete",
            startup_terminal_attempt_id=attempt_id,
            startup_terminal_evidence_digest=evidence_digest,
            startup_terminal_evidence_ref=evidence_ref,
        )
        _advance(args.receipt, "launched", artifact_identity)
        if args.exit_after_launch:
            completed_after_launch = True
            if child is not None and child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        return True

    def settle_pending_interruption() -> bool:
        """Stop the child and settle the current receipt before more milestones."""

        if not interrupted:
            return False
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except OSError:
                # The original handler may already have reaped or detached the
                # process group; receipt settlement is still mandatory.
                pass
        _settle_interrupted_attempt(args.receipt)
        _settle_runtime_health(args.receipt)
        return True

    transition_app_launch_attempt(args.receipt, "compiling")
    if settle_pending_interruption():
        return 130
    try:
        for raw_path in args.log_ref:
            log_path = Path(raw_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handles.append(log_path.open("w", encoding="utf-8"))
        if settle_pending_interruption():
            return 130
        child = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        # A signal can arrive while Popen is creating the process group.  Do
        # not wait for output or consume a phase marker before settling it.
        if settle_pending_interruption():
            child.wait()
            return 130
        assert child.stdout is not None
        output: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert child is not None and child.stdout is not None
            for emitted_line in child.stdout:
                output.put(emitted_line)
            output.put(None)

        threading.Thread(target=read_output, daemon=True).start()
        deadline = time.monotonic() + args.timeout_seconds
        while True:
            if settle_pending_interruption():
                break
            current = read_app_launch_attempt(args.receipt)["status"]
            if current != "launched" and time.monotonic() >= deadline:
                timed_out = True
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                break
            try:
                line = output.get(timeout=0.25)
            except queue.Empty:
                if settle_pending_interruption():
                    break
                if args.require_safe_terminal and pending_launched:
                    try:
                        terminal_bound = bind_pending_safe_terminal()
                    except (OSError, ValueError) as error:
                        safe_terminal_error = _SafeTerminalIdentityError(str(error))
                        if child.poll() is None:
                            os.killpg(child.pid, signal.SIGTERM)
                        break
                    if terminal_bound and completed_after_launch:
                        break
                if child.poll() is not None:
                    continue
                continue
            if line is None:
                break
            # The queue wait is another signal boundary.  A pending signal
            # must win over every compile/install/configure/launch marker.
            if settle_pending_interruption():
                break
            print(line, end="", flush=True)
            for handle in log_handles:
                handle.write(line)
                handle.flush()
            lowered = line.lower()
            if not first_dependency_blocker:
                first_dependency_blocker = _canonical_dependency_blocker_from(line)
            observed_phase = _observed_phase_from(line)
            if observed_phase:
                if settle_pending_interruption():
                    break
                try:
                    if observed_phase == "launched" and args.require_safe_terminal:
                        pending_launched = True
                    else:
                        _advance(
                            args.receipt,
                            observed_phase,
                            artifact_identity,
                        )
                except _ArtifactIdentityError as error:
                    artifact_identity_error = error
                    if child.poll() is None:
                        try:
                            os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    break
                if (
                    observed_phase == "launched"
                    and not args.require_safe_terminal
                    and args.exit_after_launch
                ):
                    completed_after_launch = True
                    if child.poll() is None:
                        try:
                            os.killpg(child.pid, signal.SIGINT)
                        except ProcessLookupError:
                            pass
                    break
            if "error launching application" in lowered:
                observed_launch_error = True
            if "[bootstrap] source=bootstrap_failure" in lowered:
                record_app_launch_attempt_warning(
                    args.receipt,
                    "warning/runtime_degraded: bootstrap_failure",
                )
            configuration_state = _configuration_state_from(line)
            if configuration_state:
                if settle_pending_interruption():
                    break
                record_app_launch_attempt_observation(
                    args.receipt,
                    configuration_state=configuration_state,
                )
            if args.require_safe_terminal:
                if settle_pending_interruption():
                    break
                try:
                    safe_terminal.observe(
                        line,
                        read_app_launch_attempt(args.receipt),
                    )
                    terminal_bound = bind_pending_safe_terminal()
                except (OSError, ValueError, _SafeTerminalIdentityError) as error:
                    safe_terminal_error = _SafeTerminalIdentityError(str(error))
                    if child.poll() is None:
                        try:
                            os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    break
                if terminal_bound and completed_after_launch:
                    break
            # Flutter/Xcode 的人类可读文案会随工具版本变化，不能作为状态事实。
            # compile/install/configure/launch 只能由 executor 发出的规范 marker 推进。
        try:
            exit_code = child.wait(
                timeout=(
                    15
                    if completed_after_launch
                    else 5
                    if timed_out or artifact_identity_error or safe_terminal_error
                    else None
                )
            )
        except subprocess.TimeoutExpired:
            bounded_stop_failed = completed_after_launch
            os.killpg(child.pid, signal.SIGKILL)
            exit_code = child.wait()
    except OSError as error:
        current = read_app_launch_attempt(args.receipt)["status"]
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=_failure_for(current),
            warning=str(error),
        )
        _settle_runtime_health(args.receipt)
        return 1
    finally:
        for handle in log_handles:
            handle.close()

    current = read_app_launch_attempt(args.receipt)["status"]
    if artifact_identity_error is not None:
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=artifact_identity_error.blocker,
            warning=str(artifact_identity_error),
        )
        print(
            f"[supervisor] GATE_BLOCK: {artifact_identity_error.blocker}: "
            f"{artifact_identity_error}",
            file=sys.stderr,
            flush=True,
        )
        _settle_runtime_health(args.receipt)
        return 2
    if safe_terminal_error is not None:
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker="APP.LAUNCH.launch_failed",
            warning=str(safe_terminal_error),
        )
        print(
            "[supervisor] GATE_BLOCK: APP.LAUNCH.launch_failed: "
            f"{safe_terminal_error}",
            file=sys.stderr,
            flush=True,
        )
        _settle_runtime_health(args.receipt)
        return 2
    if interrupted:
        _settle_interrupted_attempt(args.receipt)
        _settle_runtime_health(args.receipt)
        return 130
    if completed_after_launch:
        current = read_app_launch_attempt(args.receipt)["status"]
        if bounded_stop_failed:
            transition_app_launch_attempt(
                args.receipt,
                "runtime_degraded",
                warning=(
                    "warning/runtime_degraded: bounded UAT launch process did not "
                    "stop after SIGINT"
                ),
            )
            _settle_runtime_health(args.receipt)
            return 1
        if current != "launched":
            transition_app_launch_attempt(
                args.receipt,
                "failed",
                first_blocker=_failure_for(str(current)),
            )
            _settle_runtime_health(args.receipt)
            return 1
        transition_app_launch_attempt(args.receipt, "stopped")
        _settle_runtime_health(args.receipt)
        return 0
    if timed_out:
        current = read_app_launch_attempt(args.receipt)["status"]
        timeout_detail = (
            "startup safe terminal was not observed for the current launch attempt "
            f"within {args.timeout_seconds:g}s"
            if args.require_safe_terminal and pending_launched
            else f"launch did not reach launched within {args.timeout_seconds:g}s"
        )
        transition_app_launch_attempt(
            args.receipt,
            "failed",
            first_blocker=_failure_for(current),
            warning=timeout_detail,
        )
        _settle_runtime_health(args.receipt)
        return 124
    if exit_code != 0:
        current = read_app_launch_attempt(args.receipt)["status"]
        if current == "launched":
            transition_app_launch_attempt(
                args.receipt,
                "runtime_degraded",
                warning=f"Flutter process exited after launch with code {exit_code}",
            )
        else:
            transition_app_launch_attempt(
                args.receipt,
                "failed",
                first_blocker=(
                    first_dependency_blocker
                    or (
                        "APP.LAUNCH.launch_failed"
                        if observed_launch_error
                        else _failure_for(current)
                    )
                ),
            )
        _settle_runtime_health(args.receipt)
        return exit_code
    if current == "launched":
        transition_app_launch_attempt(args.receipt, "stopped")
        _settle_runtime_health(args.receipt)
        return 0
    transition_app_launch_attempt(
        args.receipt,
        "failed",
        first_blocker=_failure_for(current),
        warning="launch command exited before a launched milestone",
    )
    _settle_runtime_health(args.receipt)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
