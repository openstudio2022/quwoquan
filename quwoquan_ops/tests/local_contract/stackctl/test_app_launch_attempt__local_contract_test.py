from __future__ import annotations

import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli.lib.app_launch_attempt import (
    create_app_launch_attempt,
    read_app_launch_attempt,
    transition_app_launch_attempt,
    wait_for_app_launch_attempt,
)

ROOT = Path(__file__).resolve().parents[4]
SUPERVISOR = ROOT / "quwoquan_app/scripts/device/supervise_app_launch.py"
INSTANCE_LAUNCHER = ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"


def _load_supervisor_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("supervise_app_launch", SUPERVISOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _supervisor_argv(
    receipt: Path,
    child: str,
    *,
    environment: str = "alpha",
    timeout_seconds: float | None = None,
    log_ref: Path | None = None,
) -> list[str]:
    target = f"{environment}-local" if environment != "prod" else "prod-sim"
    argv = [
        sys.executable,
        str(SUPERVISOR),
        "--receipt",
        str(receipt),
        "--environment",
        environment,
        "--target",
        target,
        "--platform",
        "ios",
        "--build-mode",
        "debug",
        "--run-mode",
        "ui-only",
        "--device",
        "device-1",
    ]
    if timeout_seconds is not None:
        argv.extend(("--timeout-seconds", str(timeout_seconds)))
    if log_ref is not None:
        argv.extend(("--log-ref", str(log_ref)))
    return [*argv, "--", sys.executable, "-c", child]


def _run_supervisor(
    receipt: Path,
    child: str,
    *,
    environment: str = "alpha",
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _supervisor_argv(
            receipt,
            child,
            environment=environment,
            timeout_seconds=timeout_seconds,
        ),
        check=False,
        capture_output=True,
        text=True,
    )


def test_receipt_rejects_skipped_forward_state() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        create_app_launch_attempt(
            receipt,
            environment="alpha",
            target="alpha-local",
            platform="android",
            build_mode="debug",
            run_mode="content-live",
            device_id="emulator-5554",
        )
        with pytest.raises(ValueError, match="prepared -> launched"):
            transition_app_launch_attempt(receipt, "launched")


def test_compile_failure_after_old_pid_window_never_becomes_launched() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "import time; time.sleep(1.7); print('compiler failed', flush=True); raise SystemExit(7)",
        )
        payload = read_app_launch_attempt(receipt)
        assert result.returncode == 7
        assert payload["status"] == "failed"
        assert payload["firstBlocker"] == "APP.LAUNCH.compile_failed"
        assert "launched" not in [item["status"] for item in payload["transitions"]]


def test_prod_debug_is_rejected_before_child_process() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "raise SystemExit('child must not run')",
            environment="prod",
        )
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        assert result.returncode == 2
        assert payload["status"] == "failed"
        assert payload["firstBlocker"] == "APP.LAUNCH.prod_debug_forbidden"


def test_launch_error_does_not_invent_install_or_launched_transitions() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "print('Xcode build done.', flush=True); "
            "print('Error launching application on iPhone.', flush=True); "
            "raise SystemExit(1)",
        )
        payload = read_app_launch_attempt(receipt)
        assert result.returncode == 1
        assert payload["firstBlocker"] == "APP.LAUNCH.launch_failed"
        assert [item["status"] for item in payload["transitions"]] == [
            "prepared",
            "compiling",
            "compiled",
            "failed",
        ]


def test_bootstrap_failure_is_logged_as_runtime_degraded_warning() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        receipt = root / "attempt.json"
        log_ref = root / "logs" / "flutter.log"
        result = subprocess.run(
            _supervisor_argv(
                receipt,
                "print('Xcode build done.', flush=True); "
                "print('Syncing files to device iPhone...', flush=True); "
                "print('A Dart VM Service is available', flush=True); "
                "print('[bootstrap] source=bootstrap_failure exception=typed', flush=True)",
                log_ref=log_ref,
            ),
            check=False,
            capture_output=True,
            text=True,
        )
        payload = read_app_launch_attempt(receipt)
        assert result.returncode == 0
        assert payload["status"] == "stopped"
        assert "warning/runtime_degraded: bootstrap_failure" in payload["warnings"]
        assert "source=bootstrap_failure" in log_ref.read_text(encoding="utf-8")


def test_fresh_install_probe_advances_to_launching_without_claiming_launched() -> None:
    supervisor = _load_supervisor_module()
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        create_app_launch_attempt(
            receipt,
            environment="alpha",
            target="alpha-local",
            platform="ios",
            build_mode="debug",
            run_mode="ui-only",
            device_id="ios-1",
        )
        transition_app_launch_attempt(receipt, "compiling")
        transition_app_launch_attempt(receipt, "compiled")
        with mock.patch.object(
            supervisor,
            "_installation_snapshot",
            return_value="new-container\0new-mtime",
        ):
            observed = supervisor._advance_fresh_install(
                receipt,
                before="old-container\0old-mtime",
                platform="ios",
                device="ios-1",
                application_id="com.example.app",
            )
        assert observed is True
        payload = read_app_launch_attempt(receipt)
        assert payload["status"] == "launching"
        assert "launched" not in [item["status"] for item in payload["transitions"]]


def test_timeout_is_typed_and_ctrl_c_is_stopped_without_compile_failure() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        timeout_receipt = root / "timeout.json"
        timeout_result = _run_supervisor(
            timeout_receipt,
            "import time; time.sleep(5)",
            timeout_seconds=0.2,
        )
        timeout_payload = read_app_launch_attempt(timeout_receipt)
        assert timeout_result.returncode == 124
        assert timeout_payload["status"] == "failed"
        assert timeout_payload["firstBlocker"] == "APP.LAUNCH.compile_failed"

        stopped_receipt = root / "stopped.json"
        process = subprocess.Popen(
            _supervisor_argv(
                stopped_receipt,
                "import time; print('compiling', flush=True); time.sleep(30)",
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if stopped_receipt.is_file():
                payload = read_app_launch_attempt(stopped_receipt)
                if payload["status"] == "compiling":
                    break
            time.sleep(0.05)
        process.send_signal(signal.SIGINT)
        process.communicate(timeout=5)
        stopped_payload = read_app_launch_attempt(stopped_receipt)
        assert process.returncode == 130
        assert stopped_payload["status"] == "stopped"
        assert stopped_payload["firstBlocker"] == ""


def test_wait_returns_only_machine_terminal_receipt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        create_app_launch_attempt(
            receipt,
            environment="beta",
            target="beta-local",
            platform="ios",
            build_mode="debug",
            run_mode="ui-only",
            device_id="ios-1",
        )
        transition_app_launch_attempt(receipt, "compiling")
        transition_app_launch_attempt(
            receipt,
            "failed",
            first_blocker="APP.LAUNCH.compile_failed",
        )
        observed = wait_for_app_launch_attempt(receipt, timeout_seconds=0.1)
        assert observed["status"] == "failed"


def test_prod_instance_paths_never_fall_back_to_flutter_run() -> None:
    source = INSTANCE_LAUNCHER.read_text(encoding="utf-8")
    assert "flutter run" not in source
    hosted = subprocess.run(
        [
            "bash",
            str(INSTANCE_LAUNCHER),
            "--env",
            "prod",
            "--target",
            "prod-hosted",
            "--device-id",
            "device-1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert hosted.returncode == 2
    assert "APP.LAUNCH.prod_hosted_flutter_forbidden" in hosted.stderr
    simulator = subprocess.run(
        [
            "bash",
            str(INSTANCE_LAUNCHER),
            "--env",
            "prod",
            "--target",
            "prod-sim",
            "--device-id",
            "device-1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert simulator.returncode == 2
    assert "APP.LAUNCH.prod_artifact_required" in simulator.stderr
