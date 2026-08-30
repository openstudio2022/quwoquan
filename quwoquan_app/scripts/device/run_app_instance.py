#!/usr/bin/env python3
"""构建、安装、原生激活并附着一个 canonical Debug App 实例。"""

from __future__ import annotations

import json
import os
import queue
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
APP_DIR = ROOT / "quwoquan_app"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canonical_app_instance import ios_vm_service
from canonical_app_instance.activation import (
    ACTIVE_PACKAGE_FILE_NAME,
    ACTIVE_RECEIPT_FILE_NAME,
    FORBIDDEN_COMPILE_ENVIRONMENT_KEYS,  # noqa: F401 - compatibility observation
    RECEIPT_FILE_NAME,
    REQUEST_FILE_NAME,
    CanonicalExecutorError,
    CanonicalLaunchExecutor,
    canonical_json_bytes,  # noqa: F401 - compatibility observation
    compile_environment,
)
from canonical_app_instance.activation import (
    bounded_payload as _bounded_payload,
)
from canonical_app_instance.arguments import (
    build_parser as _parser,
    positive_finite_seconds as _positive_finite_seconds,
    sanitize_attach_arguments,
)
from canonical_app_instance.launch_io import (
    is_flutter_app_started_event as _is_flutter_app_started_event,
)
from canonical_app_instance.launch_io import (
    load_handoff as _load_handoff,
)
from canonical_app_instance.launch_io import (
    validated_vm_service_info_file as _validate_vm_service_info_file,
)

ANDROID_REQUEST_DIGEST_EXTRA = (
    "quwoquan.runtime_config.ACTIVATION_REQUEST_DIGEST"
)
IOS_REQUEST_DIGEST_ARGUMENT = "--qwq-runtime-config-activation-request-digest"
RUNTIME_STATE_DIRECTORY = "qwq_runtime"
IOS_RUNTIME_STATE_SUBDIRECTORY = "Library/Application Support/qwq_runtime"
ATTACH_SIGNAL_GRACE_SECONDS = 5.0


def _flutter_executable() -> str:
    """canonical launcher 贯穿的单轨真实 SDK；缺席时按 PATH 解析。"""
    return os.environ.get("QWQ_REAL_FLUTTER", "").strip() or "flutter"


class _AttachTerminationSignal(Exception):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def _terminate_attach_process_group(
    process: subprocess.Popen[str],
    *,
    initial_signal: int,
) -> None:
    if initial_signal == signal.SIGINT:
        signals = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)
    elif initial_signal == signal.SIGHUP:
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGKILL)
    else:
        signals = (signal.SIGTERM, signal.SIGKILL)
    for signum in signals:
        if process.poll() is not None:
            process.wait()
            return
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            process.wait()
            return
        if signum == signal.SIGKILL:
            process.wait()
            return
        try:
            process.wait(timeout=ATTACH_SIGNAL_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            continue


class CommandPlatformDriver:
    def __init__(
        self,
        *,
        device_id: str,
        application_id: str,
        entrypoint: str,
        activation_component: str = "",
        vm_service_info_file: Path | None = None,
        vm_service_info_allowed_root: Path | None = None,
    ) -> None:
        self.device_id = _required_value(device_id, "device id")
        self.application_id = _required_value(application_id, "application id")
        self.entrypoint = _required_value(entrypoint, "entrypoint")
        # UAT 壳与生产壳不同；activation FQCN 必须由调用方交出，不从 App ID 猜测。
        self.activation_component = activation_component.strip()
        self.vm_service_info_file = vm_service_info_file
        self.vm_service_info_allowed_root = vm_service_info_allowed_root

    def build_command(self) -> list[str]:
        raise NotImplementedError

    def artifact_path(self) -> Path:
        raise NotImplementedError

    def requires_cocoapods(self) -> bool:
        return False

    def child_environment(self, environment: Mapping[str, str]) -> dict[str, str]:
        return compile_environment(
            environment,
            require_cocoapods=self.requires_cocoapods(),
        )

    def build(self, environment: dict[str, str]) -> None:
        _run_checked(
            self.build_command(),
            environment=self.child_environment(environment),
        )
        artifact = self.artifact_path()
        if not artifact.exists():
            raise CanonicalExecutorError(
                f"compiled App artifact is missing: {artifact}"
            )

    def resolve_attach_debug_url(self, timeout_seconds: float) -> str | None:
        del timeout_seconds
        return None

    def startup_evidence_lines(self) -> tuple[str, ...]:
        return ()

    def validate_vm_service_info_file(self) -> Path | None:
        if self.vm_service_info_file is None:
            return None
        return _validated_vm_service_info_file(
            self.vm_service_info_file,
            self.vm_service_info_allowed_root,
        )

    def attach(
        self,
        attach_arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        on_attached: Callable[[], None],
    ) -> int:
        command = [
            _flutter_executable(),
            "attach",
            "--machine",
            "-d",
            self.device_id,
            "--app-id",
            self.application_id,
            "--target",
            self.entrypoint,
            "--host-vmservice-port=0",
            "--dds-port=0",
        ]
        debug_url = self.resolve_attach_debug_url(timeout_seconds)
        if debug_url is not None:
            command.append(f"--debug-url={debug_url}")
        vm_service_info_file = self.validate_vm_service_info_file()
        if vm_service_info_file is not None:
            command.append(f"--write-service-info={vm_service_info_file}")
        command.extend(_sanitize_attach_arguments(attach_arguments))
        try:
            process = subprocess.Popen(
                command,
                cwd=APP_DIR,
                env=self.child_environment(os.environ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as error:
            raise CanonicalExecutorError(
                f"unable to start flutter attach: {error}"
            ) from error
        assert process.stdout is not None
        output: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            try:
                for line in process.stdout:
                    output.put(line)
            finally:
                output.put(None)

        previous_signal_handlers: dict[int, signal.Handlers] = {}

        def handle_termination(signum: int, _frame: object) -> None:
            raise _AttachTerminationSignal(signum)

        try:
            for signum in (signal.SIGTERM, signal.SIGHUP):
                previous_signal_handlers[signum] = signal.signal(
                    signum, handle_termination
                )
            threading.Thread(target=read_output, daemon=True).start()
            deadline = time.monotonic() + timeout_seconds
            attached = False
            emitted_startup_evidence: set[str] = set()

            def emit_startup_evidence() -> None:
                for evidence_line in self.startup_evidence_lines():
                    if evidence_line not in emitted_startup_evidence:
                        emitted_startup_evidence.add(evidence_line)
                        print(evidence_line, flush=True)

            while True:
                if not attached and time.monotonic() >= deadline:
                    raise CanonicalExecutorError(
                        "flutter attach did not establish a VM service session "
                        f"within {timeout_seconds:g}s"
                    )
                try:
                    line = output.get(timeout=0.1)
                except queue.Empty:
                    if attached:
                        emit_startup_evidence()
                    continue
                if line is None:
                    break
                print(ios_vm_service.redact_vm_service_tokens(line), end="", flush=True)
                if not attached and _is_flutter_app_started_event(line):
                    self.validate_vm_service_info_file()
                    emit_startup_evidence()
                    attached = True
                    on_attached()
            exit_code = process.wait()
        except KeyboardInterrupt:
            _terminate_attach_process_group(
                process, initial_signal=signal.SIGINT
            )
            return 130
        except _AttachTerminationSignal as termination:
            _terminate_attach_process_group(
                process, initial_signal=termination.signum
            )
            return 128 + termination.signum
        except BaseException:
            if process.poll() is None:
                _terminate_attach_process_group(
                    process, initial_signal=signal.SIGTERM
                )
            else:
                process.wait()
            raise
        finally:
            for signum, previous_handler in previous_signal_handlers.items():
                signal.signal(signum, previous_handler)
        if not attached:
            self.validate_vm_service_info_file()
            raise CanonicalExecutorError(
                f"flutter attach exited before VM service attachment (code {exit_code})"
            )
        self.validate_vm_service_info_file()
        return exit_code


class AndroidPlatformDriver(CommandPlatformDriver):
    def build_command(self) -> list[str]:
        return [
            _flutter_executable(),
            "build",
            "apk",
            "--debug",
            "--no-pub",
            "--flavor",
            "nonprod",
            "--target",
            self.entrypoint,
        ]

    def artifact_path(self) -> Path:
        return APP_DIR / "build/app/outputs/flutter-apk/app-nonprod-debug.apk"

    def install(self) -> None:
        _run_checked(
            [
                "adb",
                "-s",
                self.device_id,
                "install",
                "-r",
                "-t",
                str(self.artifact_path()),
            ]
        )

    def read_runtime_file(self, file_name: str) -> bytes | None:
        _validate_runtime_file_name(file_name)
        relative_path = f"no_backup/{file_name}"
        script = (
            f"if [ ! -e {shlex.quote(relative_path)} ]; then exit 44; fi; "
            f"if [ ! -f {shlex.quote(relative_path)} ] || "
            f"[ -L {shlex.quote(relative_path)} ]; then exit 45; fi; "
            f"cat {shlex.quote(relative_path)}"
        )
        # 安装完成后的短窗口内 run-as 可能因包管理器状态未同步而失败
        # （unknown package）；有限重试吸收该暂态，耗尽后仍 fail closed。
        last_result = None
        for attempt in range(5):
            if attempt:
                time.sleep(1.0)
            # adb shell 把 argv 拼接后交设备端 shell 重新解析，script 必须
            # 整体加引号才能作为 sh -c 的单一参数到达。
            result = _run(
                [
                    "adb",
                    "-s",
                    self.device_id,
                    "shell",
                    "run-as",
                    self.application_id,
                    "sh",
                    "-c",
                    shlex.quote(script),
                ],
                capture_output=True,
            )
            if result.returncode == 44:
                return None
            if result.returncode == 0:
                return _bounded_payload(result.stdout, file_name)
            last_result = result
            if result.returncode == 45:
                break
        detail = ""
        if last_result is not None and last_result.stderr:
            stderr_text = last_result.stderr
            if isinstance(stderr_text, bytes):
                stderr_text = stderr_text.decode("utf-8", errors="replace")
            detail = f": {stderr_text.strip()[:200]}"
        raise CanonicalExecutorError(
            "unable to read Android private runtime configuration state "
            f"(code {last_result.returncode if last_result else 'unknown'})"
            f"{detail}"
        )

    def write_activation_request(self, payload: bytes) -> None:
        _bounded_payload(payload, REQUEST_FILE_NAME)
        destination = f"no_backup/{REQUEST_FILE_NAME}"
        script = (
            "set -e; umask 077; mkdir -p no_backup; "
            f"temporary=no_backup/.{REQUEST_FILE_NAME}.$$.tmp; "
            "trap 'rm -f \"$temporary\"' EXIT; "
            "cat > \"$temporary\"; chmod 600 \"$temporary\"; "
            f"mv -f \"$temporary\" {shlex.quote(destination)}; trap - EXIT"
        )
        result = _run(
            [
                "adb",
                "-s",
                self.device_id,
                "shell",
                "run-as",
                self.application_id,
                "sh",
                "-c",
                shlex.quote(script),
            ],
            input_payload=payload,
            capture_output=True,
        )
        if result.returncode != 0:
            detail = ""
            if result.stderr:
                stderr_text = result.stderr
                if isinstance(stderr_text, bytes):
                    stderr_text = stderr_text.decode("utf-8", errors="replace")
                detail = f": {stderr_text.strip()[:200]}"
            raise CanonicalExecutorError(
                "unable to write Android private activation request "
                f"(code {result.returncode})"
                f"{detail}"
            )

    def launch_activation(self, request_digest: str) -> None:
        _run_checked(
            [
                "adb",
                "-s",
                self.device_id,
                "shell",
                "am",
                "start",
                "-S",
                "-W",
                "-n",
                self._activation_component(),
                "--es",
                ANDROID_REQUEST_DIGEST_EXTRA,
                request_digest,
            ]
        )

    def launch_application(self) -> None:
        if os.environ.get("QWQ_APP_STARTUP_TERMINAL_RECEIPT", "").strip():
            _run_checked(["adb", "-s", self.device_id, "logcat", "-c"])
        _run_checked(
            [
                "adb",
                "-s",
                self.device_id,
                "shell",
                "am",
                "start",
                "-S",
                "-W",
                "-n",
                self._startup_component(),
            ]
        )

    def startup_evidence_lines(self) -> tuple[str, ...]:
        if not os.environ.get("QWQ_APP_STARTUP_TERMINAL_RECEIPT", "").strip():
            return ()
        result = _run(
            ["adb", "-s", self.device_id, "logcat", "-d", "-v", "brief"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ()
        markers = ("android_dart_startup_attempt ", "android_startup_safe_terminal ")
        return tuple(
            line.strip()
            for line in str(result.stdout).splitlines()
            if any(marker in line for marker in markers)
        )

    def _startup_component(self) -> str:
        return (
            f"{self.application_id}/"
            "com.quwoquan.quwoquan_app.StartupGateActivity"
        )

    def _activation_component(self) -> str:
        if self.activation_component:
            return f"{self.application_id}/{self.activation_component}"
        return self._startup_component()


class IOSSimulatorPlatformDriver(CommandPlatformDriver):
    def requires_cocoapods(self) -> bool:
        return True

    def build_command(self) -> list[str]:
        return [
            _flutter_executable(),
            "build",
            "ios",
            "--debug",
            "--simulator",
            "--no-pub",
            "--flavor",
            "nonprod",
            "--target",
            self.entrypoint,
        ]

    def artifact_path(self) -> Path:
        return APP_DIR / "build/ios/iphonesimulator/Runner.app"

    def install(self) -> None:
        _run_checked(
            [
                "xcrun",
                "simctl",
                "install",
                self.device_id,
                str(self.artifact_path()),
            ]
        )

    def read_runtime_file(self, file_name: str) -> bytes | None:
        path = self._runtime_state_root(create=False) / file_name
        if not path.exists():
            return None
        if not path.is_file() or path.is_symlink():
            raise CanonicalExecutorError(
                f"iOS Simulator private runtime path is invalid: {file_name}"
            )
        try:
            return _bounded_payload(path.read_bytes(), file_name)
        except OSError as error:
            raise CanonicalExecutorError(
                f"unable to read iOS Simulator private runtime state: {error}"
            ) from error

    def write_activation_request(self, payload: bytes) -> None:
        payload = _bounded_payload(payload, REQUEST_FILE_NAME)
        root = self._runtime_state_root(create=True)
        destination = root / REQUEST_FILE_NAME
        temporary = root / f".{REQUEST_FILE_NAME}.{os.getpid()}.tmp"
        try:
            temporary.write_bytes(payload)
            temporary.chmod(0o600)
            os.replace(temporary, destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise CanonicalExecutorError(
                f"unable to write iOS Simulator activation request: {error}"
            ) from error

    def launch_activation(self, request_digest: str) -> None:
        _run_checked(
            [
                "xcrun",
                "simctl",
                "launch",
                "--terminate-running-process",
                self.device_id,
                self.application_id,
                IOS_REQUEST_DIGEST_ARGUMENT,
                request_digest,
            ]
        )

    def launch_application(self) -> None:
        self._ios_launch = ios_vm_service.launch_selected_simulator_application(
            self.device_id,
            self.application_id,
        )

    def resolve_attach_debug_url(self, timeout_seconds: float) -> str:
        return ios_vm_service.resolve_ios_simulator_debug_url(
            self._ios_launch,
            timeout_seconds=timeout_seconds,
        )

    def startup_evidence_lines(self) -> tuple[str, ...]:
        return ios_vm_service.read_ios_simulator_startup_evidence(self._ios_launch)

    def _runtime_state_root(self, *, create: bool) -> Path:
        result = _run(
            [
                "xcrun",
                "simctl",
                "get_app_container",
                self.device_id,
                self.application_id,
                "data",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CanonicalExecutorError(
                "unable to resolve iOS Simulator App data container "
                f"(code {result.returncode})"
            )
        container = Path(str(result.stdout).strip()).resolve()
        if not container.is_dir():
            raise CanonicalExecutorError(
                "iOS Simulator App data container is unavailable"
            )
        root = (
            container
            / "Library"
            / "Application Support"
            / RUNTIME_STATE_DIRECTORY
        )
        if create:
            try:
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                root.chmod(0o700)
            except OSError as error:
                raise CanonicalExecutorError(
                    f"unable to create iOS Simulator runtime state root: {error}"
                ) from error
        return root


class IOSPhysicalPlatformDriver(CommandPlatformDriver):
    def requires_cocoapods(self) -> bool:
        return True

    def build_command(self) -> list[str]:
        return [
            _flutter_executable(),
            "build",
            "ios",
            "--debug",
            "--no-pub",
            "--flavor",
            "nonprod",
            "--target",
            self.entrypoint,
        ]

    def artifact_path(self) -> Path:
        return APP_DIR / "build/ios/iphoneos/Runner.app"

    def install(self) -> None:
        self._devicectl(
            [
                "device",
                "install",
                "app",
                "--device",
                self.device_id,
                str(self.artifact_path()),
            ]
        )

    def read_runtime_file(self, file_name: str) -> bytes | None:
        _validate_runtime_file_name(file_name)
        listing = self._devicectl(
            [
                "device",
                "info",
                "files",
                "--device",
                self.device_id,
                "--domain-type",
                "appDataContainer",
                "--domain-identifier",
                self.application_id,
                "--subdirectory",
                ".",
                "--recurse",
                "--filter",
                f"name == '{file_name}'",
            ]
        )
        result = listing.get("result")
        if not isinstance(result, dict):
            raise CanonicalExecutorError(
                "iPhone runtime receipt listing result is missing or invalid"
            )
        collection_keys = [key for key in ("items", "files") if key in result]
        if len(collection_keys) != 1:
            raise CanonicalExecutorError(
                "iPhone runtime receipt listing must contain exactly one files collection"
            )
        items = result[collection_keys[0]]
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise CanonicalExecutorError(
                "iPhone runtime receipt listing files collection is invalid"
            )
        listed_paths: list[str] = []
        for item in items:
            candidates = [
                item.get(key)
                for key in ("path", "filePath", "relativePath", "name")
                if key in item
            ]
            if not candidates or any(not isinstance(value, str) for value in candidates):
                raise CanonicalExecutorError(
                    "iPhone runtime receipt listing file entry is invalid"
                )
            listed_paths.extend(candidates)
        if not any(
            value == file_name or value.endswith("/" + file_name)
            for value in listed_paths
        ):
            return None
        cache_root = _cache_root()
        with tempfile.TemporaryDirectory(
            prefix="ios-runtime-read-",
            dir=cache_root,
        ) as temporary_directory:
            destination = Path(temporary_directory) / file_name
            self._devicectl(
                [
                    "device",
                    "copy",
                    "from",
                    "--device",
                    self.device_id,
                    "--source",
                    f"{IOS_RUNTIME_STATE_SUBDIRECTORY}/{file_name}",
                    "--destination",
                    str(destination),
                    "--domain-type",
                    "appDataContainer",
                    "--domain-identifier",
                    self.application_id,
                ]
            )
            candidates = [
                path
                for path in Path(temporary_directory).rglob(file_name)
                if path.is_file() and not path.is_symlink()
            ]
            if len(candidates) != 1:
                raise CanonicalExecutorError(
                    "iPhone runtime receipt readback did not yield one regular file"
                )
            try:
                return _bounded_payload(candidates[0].read_bytes(), file_name)
            except OSError as error:
                raise CanonicalExecutorError(
                    f"unable to read copied iPhone runtime state: {error}"
                ) from error

    def write_activation_request(self, payload: bytes) -> None:
        payload = _bounded_payload(payload, REQUEST_FILE_NAME)
        cache_root = _cache_root()
        with tempfile.TemporaryDirectory(
            prefix="ios-runtime-write-",
            dir=cache_root,
        ) as temporary_directory:
            source_root = Path(temporary_directory) / RUNTIME_STATE_DIRECTORY
            source_root.mkdir(mode=0o700)
            request = source_root / REQUEST_FILE_NAME
            request.write_bytes(payload)
            request.chmod(0o600)
            self._devicectl(
                [
                    "device",
                    "copy",
                    "to",
                    "--device",
                    self.device_id,
                    "--source",
                    str(source_root),
                    "--destination",
                    "Library/Application Support",
                    "--domain-type",
                    "appDataContainer",
                    "--domain-identifier",
                    self.application_id,
                ]
            )

    def launch_activation(self, request_digest: str) -> None:
        self._devicectl(
            [
                "device",
                "process",
                "launch",
                "--device",
                self.device_id,
                "--terminate-existing",
                self.application_id,
                IOS_REQUEST_DIGEST_ARGUMENT,
                request_digest,
            ]
        )

    def launch_application(self) -> None:
        self._devicectl(
            [
                "device",
                "process",
                "launch",
                "--device",
                self.device_id,
                "--terminate-existing",
                self.application_id,
            ]
        )

    def _devicectl(self, arguments: Sequence[str]) -> dict[str, object]:
        cache_root = _cache_root()
        descriptor, raw_path = tempfile.mkstemp(
            prefix="devicectl-",
            suffix=".json",
            dir=cache_root,
        )
        os.close(descriptor)
        output_path = Path(raw_path)
        output_path.unlink(missing_ok=True)
        command = [
            "xcrun",
            "devicectl",
            *arguments,
            "--json-output",
            str(output_path),
            "--quiet",
        ]
        try:
            result = _run(command)
            try:
                document = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise CanonicalExecutorError(
                    f"devicectl did not produce valid structured output: {error}"
                ) from error
        finally:
            output_path.unlink(missing_ok=True)
        if not isinstance(document, dict):
            raise CanonicalExecutorError("devicectl structured output is not an object")
        info = document.get("info")
        outcome = info.get("outcome") if isinstance(info, dict) else None
        error = document.get("error")
        if result.returncode != 0 or error is not None or outcome == "failed":
            domain = error.get("domain") if isinstance(error, dict) else "unknown"
            code = error.get("code") if isinstance(error, dict) else result.returncode
            raise CanonicalExecutorError(
                f"devicectl operation failed domain={domain} code={code}"
            )
        return document


def build_platform_driver(
    *,
    device_kind: str,
    device_id: str,
    application_id: str,
    entrypoint: str,
    activation_component: str = "",
    vm_service_info_file: Path | None = None,
    vm_service_info_allowed_root: Path | None = None,
) -> CommandPlatformDriver:
    arguments = {
        "device_id": device_id,
        "application_id": application_id,
        "entrypoint": entrypoint,
        "activation_component": activation_component,
        "vm_service_info_file": vm_service_info_file,
        "vm_service_info_allowed_root": vm_service_info_allowed_root,
    }
    if device_kind in {"android_physical", "android_emulator"}:
        return AndroidPlatformDriver(**arguments)
    if device_kind == "ios-simulator":
        return IOSSimulatorPlatformDriver(**arguments)
    if device_kind == "ios-physical":
        return IOSPhysicalPlatformDriver(**arguments)
    raise CanonicalExecutorError(
        f"unsupported canonical launch device kind: {device_kind}"
    )


def main() -> int:
    args = _parser().parse_args()
    attach_arguments = tuple(args.attach_arguments)
    if attach_arguments[:1] == ("--",):
        attach_arguments = attach_arguments[1:]
    try:
        attach_arguments = tuple(_sanitize_attach_arguments(attach_arguments))
        handoff = _load_handoff(args.handoff_file)
        vm_service_info_file = args.vm_service_info_file
        vm_service_info_allowed_root = args.vm_service_info_allowed_root
        if (vm_service_info_file is None) != (vm_service_info_allowed_root is None):
            raise CanonicalExecutorError(
                "IDE VM service file and original workspace allow-root must be paired"
            )
        if (
            vm_service_info_file is not None
            and handoff.get("launchProvenance") != "workspace_ide_debug"
        ):
            raise CanonicalExecutorError(
                "IDE VM service output requires workspace_ide_debug handoff"
            )
        driver = build_platform_driver(
            device_kind=args.device_kind,
            device_id=args.device,
            application_id=args.application_id,
            entrypoint=args.entrypoint,
            vm_service_info_file=vm_service_info_file,
            vm_service_info_allowed_root=vm_service_info_allowed_root,
        )
        executor = CanonicalLaunchExecutor(
            handoff=handoff,
            platform_driver=driver,
            inherited_environment=os.environ,
            attach_arguments=attach_arguments,
            activation_timeout_seconds=args.activation_timeout_seconds,
            attach_timeout_seconds=args.attach_timeout_seconds,
            emit=lambda line: print(line, flush=True),
        )
        return executor.execute()
    except (CanonicalExecutorError, ValueError, TypeError) as error:
        print(f"[canonical-executor] GATE_BLOCK: {error}", file=sys.stderr, flush=True)
        return 2


def _validated_vm_service_info_file(path: Path, allowed_root: Path | None) -> Path:
    if allowed_root is None:
        raise CanonicalExecutorError("IDE VM service original workspace root is missing")
    return _validate_vm_service_info_file(path, allowed_root=allowed_root)


# sanitizer 定义在叶子模块 canonical_app_instance.arguments，launcher 预检与
# executor 共用同一实现；此处保留模块级别名以维持既有契约观察点。
_sanitize_attach_arguments = sanitize_attach_arguments


def _run_checked(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> None:
    result = _run(command, environment=environment)
    if result.returncode != 0:
        raise CanonicalExecutorError(
            f"command failed with code {result.returncode}: {shlex.join(command)}"
        )


def _run(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    input_payload: bytes | None = None,
    capture_output: bool = False,
    text: bool = False,
) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=APP_DIR,
            env=dict(environment) if environment is not None else None,
            input=input_payload,
            capture_output=capture_output,
            text=text,
            check=False,
        )
    except OSError as error:
        raise CanonicalExecutorError(
            f"unable to execute {command[0]}: {error}"
        ) from error


def _validate_runtime_file_name(file_name: str) -> None:
    if file_name not in {
        REQUEST_FILE_NAME,
        RECEIPT_FILE_NAME,
        ACTIVE_RECEIPT_FILE_NAME,
        ACTIVE_PACKAGE_FILE_NAME,
    }:
        raise CanonicalExecutorError(
            f"unsupported private runtime file: {file_name}"
        )


def _required_value(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise CanonicalExecutorError(f"{label} is required")
    return normalized


def _cache_root() -> Path:
    root = ROOT / ".qwq_output/env/repo/local/cache/app-launch"
    root.mkdir(parents=True, exist_ok=True)
    return root


if __name__ == "__main__":
    raise SystemExit(main())
