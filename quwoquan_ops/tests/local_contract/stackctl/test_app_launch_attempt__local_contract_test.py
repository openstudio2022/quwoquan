from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.app_debug_preflight_handoff import (
    app_debug_preflight_purpose,
    read_reusable_app_debug_preflight,
    write_app_debug_preflight_receipt,
)
from quwoquan_ops.cli.lib.app_launch_attempt import (
    LAUNCH_BLOCKERS,
    create_app_launch_attempt,
    read_app_launch_attempt,
    transition_app_launch_attempt,
    wait_for_app_launch_attempt,
)
from quwoquan_ops.cli.lib.generated.app_launch_contract import APP_LAUNCH_MANIFEST
from quwoquan_ops.tests.support import app_launch_signal_test_support as signal_support

ROOT = Path(__file__).resolve().parents[4]
SUPERVISOR = ROOT / "quwoquan_app/scripts/device/supervise_app_launch.py"
INSTANCE_LAUNCHER = ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"
CANONICAL_LAUNCHER = ROOT / "quwoquan_app/run.sh"
DIGEST = "sha256:" + "a" * 64


def _launch_manifest() -> dict:
    return APP_LAUNCH_MANIFEST


def _attempt_identity(environment: str = "alpha") -> dict[str, object]:
    return {
        "build_profile": "prod" if environment == "prod" else "nonprod",
        "launch_provenance": "canonical_launcher",
        "runtime_config_supply_mode": "external_runtime_package",
        "runtime_config_trust_envelope_digest": DIGEST,
        "runtime_config_package_digest": DIGEST,
        "application_id": "com.quwoquan.fixture",
        "flutter_version": "3.47.0",
        "command_resolution_digest": DIGEST,
    }


def _new_receipt(receipt: Path) -> dict:
    return create_app_launch_attempt(
        receipt,
        environment="alpha",
        target="alpha-local",
        platform="android",
        build_mode="debug",
        run_mode="content-live",
        device_id="emulator-5554",
        **_attempt_identity(),
    )


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
    platform: str = "ios",
    timeout_seconds: float | None = None,
    log_ref: Path | None = None,
    artifact_path: Path | None = None,
    materialize_artifact: bool = True,
    exit_after_launch: bool = False,
    require_safe_terminal: bool = False,
    startup_terminal_receipt: Path | None = None,
    warning: str = "",
) -> list[str]:
    target = f"{environment}-local" if environment != "prod" else "prod-sim"
    if artifact_path is None:
        artifact_path = receipt.parent / (
            "app-nonprod-debug.apk" if platform == "android" else "Runner.app"
        )
    if materialize_artifact:
        if platform == "android":
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(b"canonical-debug-apk")
        else:
            artifact_path.mkdir(parents=True, exist_ok=True)
            (artifact_path / "Runner").write_bytes(b"canonical-debug-app")
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
        platform,
        "--build-mode",
        "debug",
        "--run-mode",
        "ui-only",
        "--device",
        "device-1",
        "--build-profile",
        "prod" if environment == "prod" else "nonprod",
        "--application-id",
        "com.quwoquan.fixture",
        "--launch-provenance",
        "canonical_launcher",
        "--runtime-config-supply-mode",
        "external_runtime_package",
        "--runtime-config-trust-envelope-digest",
        DIGEST,
        "--runtime-config-package-digest",
        DIGEST,
        "--flutter-version",
        "3.47.0",
        "--command-resolution-digest",
        DIGEST,
        "--artifact-path",
        str(artifact_path),
        "--launch-digest",
        DIGEST,
    ]
    if timeout_seconds is not None:
        argv.extend(("--timeout-seconds", str(timeout_seconds)))
    if log_ref is not None:
        argv.extend(("--log-ref", str(log_ref)))
    if exit_after_launch:
        argv.append("--exit-after-launch")
    if require_safe_terminal:
        terminal_path = startup_terminal_receipt or receipt.with_name(
            "startup-terminal.json"
        )
        argv.extend(
            (
                "--require-safe-terminal",
                "--startup-terminal-receipt",
                str(terminal_path),
            )
        )
    if warning:
        argv.extend(("--warning", warning))
    return [*argv, "--", sys.executable, "-c", child]


def _run_supervisor(
    receipt: Path,
    child: str,
    *,
    environment: str = "alpha",
    platform: str = "ios",
    timeout_seconds: float | None = None,
    artifact_path: Path | None = None,
    materialize_artifact: bool = True,
    exit_after_launch: bool = False,
    require_safe_terminal: bool = False,
    startup_terminal_receipt: Path | None = None,
    warning: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _supervisor_argv(
            receipt,
            child,
            environment=environment,
            platform=platform,
            timeout_seconds=timeout_seconds,
            artifact_path=artifact_path,
            materialize_artifact=materialize_artifact,
            exit_after_launch=exit_after_launch,
            require_safe_terminal=require_safe_terminal,
            startup_terminal_receipt=startup_terminal_receipt,
            warning=warning,
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
            **_attempt_identity(),
        )
        with pytest.raises(ValueError, match="prepared -> launched"):
            transition_app_launch_attempt(receipt, "launched")


def test_compiled_transition_requires_an_exact_artifact_digest() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        transition_app_launch_attempt(receipt, "compiling")
        with pytest.raises(ValueError, match="compiled.*artifactDigest"):
            transition_app_launch_attempt(receipt, "compiled")


def test_supervisor_binds_android_apk_digest_before_install_and_launch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        receipt = root / "attempt.json"
        artifact = root / "app-nonprod-debug.apk"
        artifact_bytes = b"this exact apk is installed"
        artifact.write_bytes(artifact_bytes)
        result = _run_supervisor(
            receipt,
            "for phase in ('compiled','installing','installed','configuring',"
            "'configured','launching','launched'): "
            "print(f'QWQ_APP_LAUNCH_PHASE status={phase}', flush=True)",
            platform="android",
            artifact_path=artifact,
            materialize_artifact=False,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 0
    assert payload["status"] == "stopped"
    assert payload["artifactDigest"] == (
        "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    )
    assert "launched" in [item["status"] for item in payload["transitions"]]


def test_supervisor_binds_ios_app_payload_digest_before_launch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        receipt = root / "attempt.json"
        artifact = root / "Runner.app"
        payloads = {
            "Frameworks/App.framework/App": b"framework bytes",
            "Runner": b"executable bytes",
        }
        for relative, content in payloads.items():
            destination = artifact / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        expected = hashlib.sha256()
        for relative in sorted(payloads):
            encoded = relative.encode("utf-8")
            content = payloads[relative]
            expected.update(len(encoded).to_bytes(8, "big"))
            expected.update(encoded)
            expected.update(len(content).to_bytes(8, "big"))
            expected.update(content)
        result = _run_supervisor(
            receipt,
            "for phase in ('compiled','installing','installed','configuring',"
            "'configured','launching','launched'): "
            "print(f'QWQ_APP_LAUNCH_PHASE status={phase}', flush=True)",
            platform="ios",
            artifact_path=artifact,
            materialize_artifact=False,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 0
    assert payload["artifactDigest"] == "sha256:" + expected.hexdigest()
    assert payload["status"] == "stopped"


def test_bounded_uat_launch_stops_only_after_full_launched_receipt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "import time; "
            "[print(f'QWQ_APP_LAUNCH_PHASE status={phase}', flush=True) "
            "for phase in ('compiled','installing','installed','configuring',"
            "'configured','launching','launched')]; time.sleep(30)",
            platform="android",
            exit_after_launch=True,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 0
    assert payload["status"] == "stopped"
    assert payload["artifactDigest"].startswith("sha256:")
    assert [item["status"] for item in payload["transitions"]][-2:] == [
        "launched",
        "stopped",
    ]


def _safe_terminal_child(
    *,
    terminal_attempt_id: str = "cold-a1",
    platform: str = "android",
    surface: str | None = "router_shell",
) -> str:
    dart_attempt_id = "cold-a1"
    surface_marker = f"surface={surface} " if surface is not None else ""
    phases = (
        "compiled",
        "installing",
        "installed",
        "configuring",
        "configured",
        "launching",
        "launched",
    )
    return (
        "import time; "
        f"phases={phases!r}; "
        "[print(f'QWQ_APP_LAUNCH_PHASE status={phase}', flush=True) "
        "for phase in phases]; "
        "time.sleep(0.1); "
        f"print('android_dart_startup_attempt attemptId={dart_attempt_id} "
        "launchProvenance=canonical_launcher "
        "runtimeConfigSupplyMode=external_runtime_package hotRestart=false "
        f"configurationState=complete effectiveLaunchManifestDigest={DIGEST}', "
        "flush=True); "
        f"print('{platform}_startup_safe_terminal {surface_marker}reportedElapsedMs=10 "
        f"attemptId={terminal_attempt_id} launchProvenance=canonical_launcher "
        "runtimeConfigSupplyMode=external_runtime_package', flush=True); "
        "time.sleep(30)"
    )


def test_bounded_launch_waits_for_same_attempt_safe_terminal() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        receipt = root / "attempt.json"
        terminal = root / "startup-terminal.json"
        result = _run_supervisor(
            receipt,
            _safe_terminal_child(),
            platform="android",
            exit_after_launch=True,
            require_safe_terminal=True,
            startup_terminal_receipt=terminal,
        )
        payload = read_app_launch_attempt(receipt)
        terminal_payload = json.loads(terminal.read_text(encoding="utf-8"))

    assert result.returncode == 0
    assert payload["status"] == "stopped"
    assert payload["startupTerminalAttemptId"] == "cold-a1"
    assert payload["startupTerminalEvidenceRef"] == str(terminal)
    assert payload["startupTerminalEvidenceDigest"].startswith("sha256:")
    assert terminal_payload["launchAttemptId"] == payload["attemptId"]
    assert terminal_payload["artifactDigest"] == payload["artifactDigest"]
    assert terminal_payload["surface"] == "router_shell"


def test_vm_attach_without_safe_terminal_times_out_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        child = (
            "import time; "
            "[print(f'QWQ_APP_LAUNCH_PHASE status={phase}', flush=True) "
            "for phase in ('compiled','installing','installed','configuring',"
            "'configured','launching','launched')]; time.sleep(30)"
        )
        result = _run_supervisor(
            receipt,
            child,
            platform="android",
            timeout_seconds=0.2,
            require_safe_terminal=True,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 124
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.launch_failed"
    assert "safe terminal" in payload["warnings"][0]
    assert "launched" not in [item["status"] for item in payload["transitions"]]


def test_mismatched_safe_terminal_attempt_is_typed_launch_failure() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            _safe_terminal_child(terminal_attempt_id="other-attempt"),
            platform="android",
            require_safe_terminal=True,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.launch_failed"
    assert "safe-terminal identity mismatch" in payload["warnings"][0]
    assert "launched" not in [item["status"] for item in payload["transitions"]]


@pytest.mark.parametrize(
    ("platform", "surface"),
    (("android", "safe_recovery"), ("ios", "flutter_recovery")),
)
def test_recovery_surface_cannot_form_strict_safe_terminal(
    platform: str,
    surface: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            _safe_terminal_child(platform=platform, surface=surface),
            platform=platform,
            require_safe_terminal=True,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.launch_failed"
    assert "router_shell" in payload["warnings"][0]
    assert "launched" not in [item["status"] for item in payload["transitions"]]


@pytest.mark.parametrize("surface", (None, "unknown_surface"))
def test_missing_or_unknown_safe_terminal_surface_is_typed_failure(
    surface: str | None,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            _safe_terminal_child(surface=surface),
            platform="android",
            require_safe_terminal=True,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.launch_failed"
    assert "surface" in payload["warnings"][0]
    assert "launched" not in [item["status"] for item in payload["transitions"]]


def test_artifact_digest_is_immutable_after_compiled_transition() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        transition_app_launch_attempt(receipt, "compiling")
        transition_app_launch_attempt(receipt, "compiled", artifact_digest=DIGEST)
        with pytest.raises(ValueError, match="artifactDigest is immutable"):
            transition_app_launch_attempt(
                receipt,
                "installing",
                artifact_digest="sha256:" + "b" * 64,
            )


def test_run_sh_projects_platform_artifact_identity_into_receipts_and_report() -> None:
    source = CANONICAL_LAUNCHER.read_text(encoding="utf-8")
    assert "app-nonprod-debug.apk" in source
    assert "build/ios/iphonesimulator/Runner.app" in source
    assert "build/ios/iphoneos/Runner.app" in source
    assert '--artifact-path "$LAUNCH_ARTIFACT_PATH"' in source
    assert '"artifactDigest": artifact_digest' in source


def test_run_sh_requires_same_attempt_safe_terminal_for_every_test_live_launch() -> None:
    source = CANONICAL_LAUNCHER.read_text(encoding="utf-8")

    assert (
        'STARTUP_TERMINAL_RECEIPT="$(dirname "$LAUNCH_RECEIPT")/'
        'startup-terminal.json"' in source
    )
    assert "export QWQ_APP_STARTUP_TERMINAL_RECEIPT" in source
    assert (
        'SUPERVISOR_CMD+=(\n'
        '  --require-safe-terminal\n'
        '  --startup-terminal-receipt "$STARTUP_TERMINAL_RECEIPT"\n'
        ')' in source
    )


def test_run_sh_report_rejects_launched_without_safe_terminal_for_test_live() -> None:
    source = CANONICAL_LAUNCHER.read_text(encoding="utf-8")

    assert 'if "launched" in transition_states and (' in source
    assert 'if candidate_digest and "launched" in transition_states' not in source


def test_internal_uat_controls_are_not_public_or_env_forgeable() -> None:
    help_result = subprocess.run(
        ["bash", str(CANONICAL_LAUNCHER), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--exit-after-launch" not in help_result.stdout
    assert "--test-live-report" not in help_result.stdout

    forged = subprocess.run(
        [
            "bash",
            str(CANONICAL_LAUNCHER),
            "--test-live-report",
            "/tmp/forged-report.json",
            "-d",
            "forged-device",
        ],
        env={
            **os.environ,
            "QWQ_CANONICAL_LAUNCH_ACTOR": "app-content-uat",
            "QWQ_APP_LAUNCH_RECEIPT": "/tmp/forged-attempt.json",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert forged.returncode == 2
    assert "private canonical launch control" in forged.stderr


def test_supervisor_fails_closed_when_compiled_artifact_is_missing() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        receipt = root / "attempt.json"
        missing = root / "Runner.app"
        result = _run_supervisor(
            receipt,
            "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True)",
            artifact_path=missing,
            materialize_artifact=False,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.compile_failed"
    assert payload["artifactDigest"] == ""
    assert "compiled" not in [item["status"] for item in payload["transitions"]]


def test_supervisor_rejects_artifact_mutation_across_install() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        receipt = root / "attempt.json"
        artifact = root / "app-nonprod-debug.apk"
        artifact.write_bytes(b"compiled bytes")
        child = (
            "import json, pathlib, time; "
            f"receipt=pathlib.Path({str(receipt)!r}); "
            f"artifact=pathlib.Path({str(artifact)!r}); "
            "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True); "
            "deadline=time.monotonic()+10; "
            "\nwhile time.monotonic() < deadline:\n"
            "    try:\n"
            "        if json.loads(receipt.read_text()).get('artifactDigest'):\n"
            "            break\n"
            "    except (FileNotFoundError, json.JSONDecodeError):\n"
            "        pass\n"
            "    time.sleep(0.01)\n"
            "else:\n"
            "    raise SystemExit(91)\n"
            "artifact.write_bytes(b'mutated after compiled readback'); "
            "print('QWQ_APP_LAUNCH_PHASE status=installing', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=installed', flush=True); "
            "time.sleep(30)"
        )
        result = _run_supervisor(
            receipt,
            child,
            platform="android",
            artifact_path=artifact,
            materialize_artifact=False,
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.install_failed"
    assert payload["artifactDigest"] == (
        "sha256:" + hashlib.sha256(b"compiled bytes").hexdigest()
    )
    assert "installed" not in [item["status"] for item in payload["transitions"]]


def test_receipt_requires_activation_between_install_and_launch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        transition_app_launch_attempt(receipt, "compiling")
        transition_app_launch_attempt(receipt, "compiled", artifact_digest=DIGEST)
        for status in ("installing", "installed"):
            transition_app_launch_attempt(receipt, status)
        with pytest.raises(ValueError, match="installed -> launching"):
            transition_app_launch_attempt(receipt, "launching")
        for status in ("configuring", "configured", "launching", "launched"):
            transition_app_launch_attempt(receipt, status)
        assert [item["status"] for item in read_app_launch_attempt(receipt)["transitions"]] == [
            "prepared",
            "compiling",
            "compiled",
            "installing",
            "installed",
            "configuring",
            "configured",
            "launching",
            "launched",
        ]


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
            "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True); "
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
                "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True); "
                "print('QWQ_APP_LAUNCH_PHASE status=installing', flush=True); "
                "print('QWQ_APP_LAUNCH_PHASE status=installed', flush=True); "
                "print('QWQ_APP_LAUNCH_PHASE status=configuring', flush=True); "
                "print('QWQ_APP_LAUNCH_PHASE status=configured', flush=True); "
                "print('QWQ_APP_LAUNCH_PHASE status=launching', flush=True); "
                "print('QWQ_APP_LAUNCH_PHASE status=launched', flush=True); "
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


def test_install_state_requires_executor_phase_marker() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True)",
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode != 0
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.install_failed"
    assert [item["status"] for item in payload["transitions"]] == [
        "prepared",
        "compiling",
        "compiled",
        "failed",
    ]


def test_timeout_is_typed_compile_failure() -> None:
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


@pytest.mark.parametrize(
    ("phase", "first_blocker"), signal_support.SIGNAL_PHASE_CASES
)
@pytest.mark.parametrize("signum", signal_support.SUPPORTED_SIGNALS)
def test_signal_terminal_depends_on_reaching_launched(
    phase: str,
    first_blocker: str,
    signum: signal.Signals,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        returncode, payload = signal_support.signal_supervisor_at_phase(
            receipt,
            phase=phase,
            signum=signum,
            argv_factory=lambda path, child: _supervisor_argv(
                path, child, platform="android"
            ),
        )

    assert returncode == 130
    assert payload["status"] == ("stopped" if phase == "launched" else "failed")
    assert payload["firstBlocker"] == first_blocker


def test_interrupted_prepared_attempt_is_typed_compile_failure() -> None:
    module = _load_supervisor_module()
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        module._settle_interrupted_attempt(receipt)
        payload = read_app_launch_attempt(receipt)

    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.compile_failed"


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
            **_attempt_identity("beta"),
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


def test_launch_blockers_are_enumerated_by_metadata_not_by_free_text() -> None:
    declared = _launch_manifest()["launch_blockers"]
    assert set(declared) == set(LAUNCH_BLOCKERS)
    assert "APP.WEB.recovery_unavailable" in declared
    assert all(str(reason).strip() for reason in declared.values())
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        with pytest.raises(ValueError, match="firstBlocker.*allowed value"):
            transition_app_launch_attempt(
                receipt,
                "failed",
                first_blocker="APP.LAUNCH.compile_failed: gradle said no",
            )


def test_install_failure_is_typed_from_the_phase_it_died_in() -> None:
    """compiled/installing 阶段的死亡是安装失败，不得复用编译或启动的码。"""

    module = _load_supervisor_module()
    assert module._failure_for("compiled") == "APP.LAUNCH.install_failed"
    assert module._failure_for("installing") == "APP.LAUNCH.install_failed"
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "import sys; print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True); sys.exit(1)",
        )
        payload = read_app_launch_attempt(receipt)
        assert result.returncode != 0
        assert payload["status"] == "failed"
        assert payload["firstBlocker"] == "APP.LAUNCH.install_failed"


def test_waiting_past_the_deadline_is_a_typed_receipt_timeout() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        transition_app_launch_attempt(receipt, "compiling")
        with pytest.raises(TimeoutError, match="APP.LAUNCH.receipt_timeout"):
            wait_for_app_launch_attempt(
                receipt, timeout_seconds=0.05, poll_seconds=0.01
            )


def test_prod_sim_rejects_an_artifact_that_is_not_the_exact_release() -> None:
    """prod-sim 只接受 exact non-promotable simulator Release manifest。"""

    import importlib.util

    launcher_path = (
        ROOT / "quwoquan_app/scripts/device/launch_release_artifact.py"
    )
    spec = importlib.util.spec_from_file_location(
        "launch_release_artifact", launcher_path
    )
    assert spec is not None and spec.loader is not None
    launcher = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = launcher
    spec.loader.exec_module(launcher)

    with tempfile.TemporaryDirectory() as temporary:
        manifest_path = Path(temporary) / "app-artifact-manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": "app-artifact-manifest",
                    "environment": "prod",
                    "platform": "android",
                    "buildMode": "release",
                    "distributionClass": "simulator",
                    # promotable 制品不是 prod-sim 的可运行对象。
                    "promotable": True,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="APP.LAUNCH.prod_artifact_invalid"):
            launcher._load_inputs(manifest_path, "android")




def test_one_attempt_has_exactly_one_preflight_owner() -> None:
    # dev-session 是编排方，它执行唯一一次 preflight 并交出 exact receipt；
    # canonical launcher 只允许复用，不得为同一 attempt 再跑第二次。
    orchestrator = (
        ROOT / "quwoquan_ops/cli/commands/dev_session_domain.py"
    ).read_text(encoding="utf-8")
    launcher = (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")

    assert orchestrator.count("command_app_debug_preflight(") == 1
    assert "write_app_debug_preflight_receipt(" in orchestrator
    assert "QWQ_APP_DEBUG_PREFLIGHT_RECEIPT" in orchestrator

    # 只统计真实执行；恢复提示里的命令文本不是第二个 owner。
    execution = 'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"'
    assert launcher.count(execution) == 1
    assert "read_reusable_app_debug_preflight(" in launcher
    reuse = launcher.index("QWQ_APP_DEBUG_PREFLIGHT_RECEIPT")
    own = launcher.index(execution)
    assert reuse < own, "reuse must be attempted before the launcher owns preflight"
    # purpose 映射与 receipt 判定只有一份实现，launcher 不得内联复制。
    assert "PREFLIGHT_PURPOSE=content_live" not in launcher
    assert "PREFLIGHT_PURPOSE=runtime" not in launcher


def test_preflight_purpose_is_derived_from_the_declared_app_mode() -> None:
    assert app_debug_preflight_purpose("content-live") == "content_live"
    assert app_debug_preflight_purpose("ui-only") == "runtime"
    with pytest.raises(ValueError, match="APP.LAUNCH.app_mode_invalid"):
        app_debug_preflight_purpose("")
    with pytest.raises(ValueError, match="APP.LAUNCH.app_mode_invalid"):
        app_debug_preflight_purpose("content_live")


def test_preflight_receipt_is_reusable_only_for_the_exact_attempt() -> None:
    payload = {"purpose": "content_live", "status": "passed", "warnings": []}
    with tempfile.TemporaryDirectory() as temporary:
        receipt = write_app_debug_preflight_receipt(
            Path(temporary) / "preflight" / "app-debug-preflight.json",
            payload,
            purpose="content_live",
            target="alpha-local",
        )
        reused = read_reusable_app_debug_preflight(
            receipt,
            purpose="content_live",
            target="alpha-local",
        )
        assert json.loads(reused) == payload

        with pytest.raises(ValueError, match="APP.LAUNCH.preflight_receipt_invalid"):
            read_reusable_app_debug_preflight(
                receipt,
                purpose="runtime",
                target="alpha-local",
            )
        with pytest.raises(ValueError, match="APP.LAUNCH.preflight_receipt_invalid"):
            read_reusable_app_debug_preflight(
                receipt,
                purpose="content_live",
                target="beta-local",
            )
        missing = Path(temporary) / "absent.json"
        with pytest.raises(ValueError, match="APP.LAUNCH.preflight_receipt_invalid"):
            read_reusable_app_debug_preflight(
                missing,
                purpose="content_live",
                target="alpha-local",
            )
        foreign = Path(temporary) / "foreign.json"
        foreign.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="APP.LAUNCH.preflight_receipt_invalid"):
            read_reusable_app_debug_preflight(
                foreign,
                purpose="content_live",
                target="alpha-local",
            )
