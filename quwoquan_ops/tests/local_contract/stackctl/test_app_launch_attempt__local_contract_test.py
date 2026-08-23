from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

import yaml

from quwoquan_ops.cli.lib.app_debug_preflight_handoff import (
    app_debug_preflight_purpose,
    read_reusable_app_debug_preflight,
    write_app_debug_preflight_receipt,
)
from quwoquan_ops.cli.lib.app_launch_attempt import (
    CONFIGURATION_STATES,
    LAUNCH_BLOCKERS,
    RECOVERY_WEB_STATUSES,
    RUNTIME_HEALTH_STATUSES,
    create_app_launch_attempt,
    read_app_launch_attempt,
    record_app_launch_attempt_observation,
    transition_app_launch_attempt,
    wait_for_app_launch_attempt,
)

ROOT = Path(__file__).resolve().parents[4]
SUPERVISOR = ROOT / "quwoquan_app/scripts/device/supervise_app_launch.py"
INSTANCE_LAUNCHER = ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"
LAUNCH_MANIFEST = (
    ROOT / "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"
)


def _launch_manifest() -> dict:
    return yaml.safe_load(LAUNCH_MANIFEST.read_text(encoding="utf-8"))


def _new_receipt(receipt: Path) -> dict:
    return create_app_launch_attempt(
        receipt,
        environment="alpha",
        target="alpha-local",
        platform="android",
        build_mode="debug",
        run_mode="content-live",
        device_id="emulator-5554",
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


def test_receipt_requires_activation_between_install_and_launch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        for status in ("compiling", "compiled", "installing", "installed"):
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


def test_launch_blockers_are_enumerated_by_metadata_not_by_free_text() -> None:
    declared = _launch_manifest()["launch_blockers"]
    assert set(declared) == set(LAUNCH_BLOCKERS)
    assert "APP.WEB.recovery_unavailable" in declared
    assert all(str(reason).strip() for reason in declared.values())
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        with pytest.raises(ValueError, match="firstBlocker is invalid"):
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


def test_observation_states_are_enumerated_by_metadata_not_by_free_text() -> None:
    fields = _launch_manifest()["schemas"]["app_launch_attempt"]["fields"]
    for field, constant in (
        ("configurationState", CONFIGURATION_STATES),
        ("runtimeHealthStatus", RUNTIME_HEALTH_STATUSES),
        ("recoveryWebStatus", RECOVERY_WEB_STATUSES),
    ):
        assert set(fields[field]["allowed_values"]) == set(constant)


def test_new_receipt_starts_unobserved_for_configuration_and_runtime() -> None:
    manifest_fields = _launch_manifest()["schemas"]["app_launch_attempt"]
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        payload = _new_receipt(receipt)
        assert set(payload) == set(manifest_fields["required_fields"])
        assert payload["configurationState"] == "unobserved"
        assert payload["runtimeHealthStatus"] == "unobserved"
        assert payload["recoveryWebStatus"] == "unobserved"
        assert payload["recoveryWebEvidenceRef"] == ""


def test_runtime_health_cannot_be_claimed_without_reaching_launched() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        transition_app_launch_attempt(receipt, "compiling")
        with pytest.raises(ValueError, match="runtime health requires launched"):
            record_app_launch_attempt_observation(
                receipt,
                runtime_health_status="healthy",
            )


def test_recovery_web_status_requires_readable_evidence_reference() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _new_receipt(receipt)
        with pytest.raises(ValueError, match="recovery web evidence is missing"):
            record_app_launch_attempt_observation(
                receipt,
                recovery_web_status="unavailable",
            )
        settled = record_app_launch_attempt_observation(
            receipt,
            recovery_web_status="unavailable",
            recovery_web_evidence_ref=".qwq_output/env/repo/runs/web-cta/http.json",
            first_blocker="APP.WEB.recovery_unavailable",
        )
        assert settled["firstBlocker"] == "APP.WEB.recovery_unavailable"
        with pytest.raises(ValueError, match="recovery web evidence is unexpected"):
            record_app_launch_attempt_observation(
                receipt,
                recovery_web_status="not_applicable",
            )


def test_configuration_state_is_read_from_the_canonical_startup_attempt_line() -> None:
    """一个事实只有一条文法：supervisor 只认 (android|ios)_dart_startup_attempt。"""

    module = _load_supervisor_module()
    assert module._configuration_state_from(
        "I/QWQStartup: android_dart_startup_attempt attemptId=a1 "
        "launchMode=stackctl_alpha hotRestart=false configurationState=complete"
    ) == "complete"
    assert module._configuration_state_from(
        "QWQStartup ios_dart_startup_attempt attemptId=b2 "
        "configurationState=pending_native"
    ) == "pending_native"
    # 未登记的取值不得写进 receipt，宁可保持 unobserved。
    assert module._configuration_state_from(
        "android_dart_startup_attempt attemptId=a1 configurationState=content_missing"
    ) == ""
    assert module._configuration_state_from("unrelated output") == ""
    # 第二条文法一旦复活即为双真相源，这里显式钉死它不被接受。
    assert module._configuration_state_from(
        "[log] startup_configuration_state state=complete"
    ) == ""


def test_launched_attempt_settles_runtime_health_from_observed_warnings() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        healthy_receipt = root / "healthy.json"
        result = _run_supervisor(
            healthy_receipt,
            "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=installing', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=installed', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=configuring', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=configured', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=launching', flush=True); "
            "print('android_dart_startup_attempt attemptId=a1 ""configurationState=complete', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=launched', flush=True)",
        )
        healthy = read_app_launch_attempt(healthy_receipt)
        assert result.returncode == 0
        assert healthy["status"] == "stopped"
        assert healthy["configurationState"] == "complete"
        assert healthy["runtimeHealthStatus"] == "healthy"

        degraded_receipt = root / "degraded.json"
        _run_supervisor(
            degraded_receipt,
            "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=installing', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=installed', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=configuring', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=configured', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=launching', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=launched', flush=True); "
            "print('[bootstrap] source=bootstrap_failure exception=typed', flush=True)",
        )
        degraded = read_app_launch_attempt(degraded_receipt)
        assert degraded["runtimeHealthStatus"] == "degraded"


def test_failed_attempt_leaves_runtime_health_unobserved() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        _run_supervisor(
            receipt,
            "print('compiler failed', flush=True); raise SystemExit(7)",
        )
        payload = read_app_launch_attempt(receipt)
        assert payload["status"] == "failed"
        assert payload["runtimeHealthStatus"] == "unobserved"


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
