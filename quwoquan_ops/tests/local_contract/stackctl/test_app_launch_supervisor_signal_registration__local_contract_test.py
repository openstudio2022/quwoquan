import importlib.util
import signal
import sys
import tempfile
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.app_launch_attempt import read_app_launch_attempt


ROOT = Path(__file__).resolve().parents[4]
SUPERVISOR = ROOT / "quwoquan_app/scripts/device/supervise_app_launch.py"


def test_signal_handlers_precede_prepared_receipt_materialization() -> None:
    source = SUPERVISOR.read_text(encoding="utf-8")
    main = source[source.index("def main() -> int:") :]

    assert main.index("signal.signal(signum, forward)") < main.index(
        "create_app_launch_attempt("
    )
    assert main.index("if interrupted:") > main.index("create_app_launch_attempt(")


def _load_supervisor():
    spec = importlib.util.spec_from_file_location(
        "supervise_signal_boundary_under_test",
        SUPERVISOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_signal_during_popen_settles_before_any_phase_marker() -> None:
    module = _load_supervisor()
    handlers = {}

    class Process:
        pid = 4242
        stdout = None

        def __init__(self) -> None:
            self.returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            del timeout
            self.returncode = 0
            return 0

    def register(signum, handler):
        handlers[signum] = handler
        return signal.SIG_DFL

    def popen(*_args, **_kwargs):
        process = Process()
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        return process

    with tempfile.TemporaryDirectory() as directory:
        receipt = Path(directory) / "attempt.json"
        argv = [
            str(SUPERVISOR),
            "--receipt",
            str(receipt),
            "--environment",
            "alpha",
            "--target",
            "alpha-local",
            "--platform",
            "android",
            "--build-profile",
            "nonprod",
            "--build-mode",
            "debug",
            "--run-mode",
            "ui-only",
            "--device",
            "emulator-5554",
            "--application-id",
            "com.leadwise.quwoquan.nonprod.debug",
            "--launch-provenance",
            "canonical_launcher",
            "--runtime-config-supply-mode",
            "external_runtime_package",
            "--runtime-config-trust-envelope-digest",
            "sha256:" + "1" * 64,
            "--runtime-config-package-digest",
            "sha256:" + "2" * 64,
            "--flutter-version",
            "3.35.1",
            "--command-resolution-digest",
            "sha256:" + "3" * 64,
            "--launch-digest",
            "sha256:" + "4" * 64,
            "--",
            "ignored-child",
        ]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            module.signal,
            "signal",
            side_effect=register,
        ), mock.patch.object(
            module.subprocess,
            "Popen",
            side_effect=popen,
        ), mock.patch.object(module.os, "killpg") as killpg:
            assert module.main() == 130

        payload = read_app_launch_attempt(receipt)

    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.compile_failed"
    assert [item["status"] for item in payload["transitions"]] == [
        "prepared",
        "compiling",
        "failed",
    ]
    killpg.assert_called_once_with(4242, signal.SIGTERM)
