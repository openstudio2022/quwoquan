from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import tempfile
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.app_launch_attempt import (
    CONFIGURATION_STATES,
    RECOVERY_WEB_STATUSES,
    RUNTIME_HEALTH_STATUSES,
    read_app_launch_attempt,
    record_app_launch_attempt_observation,
    transition_app_launch_attempt,
)
from quwoquan_ops.tests.local_contract.stackctl.test_app_launch_attempt__local_contract_test import (
    _launch_manifest,
    _load_supervisor_module,
    _new_receipt,
    _run_supervisor,
)


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


def test_configuration_state_is_read_from_canonical_startup_attempt_line() -> None:
    module = _load_supervisor_module()
    assert module._configuration_state_from(
        "I/QWQStartup: android_dart_startup_attempt attemptId=a1 "
        "launchProvenance=canonical_launcher hotRestart=false "
        "configurationState=complete"
    ) == "complete"
    assert module._configuration_state_from(
        "QWQStartup ios_dart_startup_attempt attemptId=b2 "
        "configurationState=pending_native"
    ) == "pending_native"
    assert module._configuration_state_from(
        "android_dart_startup_attempt attemptId=a1 "
        "configurationState=content_missing"
    ) == ""
    assert module._configuration_state_from("unrelated output") == ""
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
            "print('android_dart_startup_attempt attemptId=a1 "
            "configurationState=complete', flush=True); "
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

        warning_receipt = root / "readiness-warning.json"
        _run_supervisor(
            warning_receipt,
            "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=installing', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=installed', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=configuring', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=configured', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=launching', flush=True); "
            "print('QWQ_APP_LAUNCH_PHASE status=launched', flush=True)",
            warning="CONTENT.SYSTEM.required_dependency_unavailable",
        )
        warning = read_app_launch_attempt(warning_receipt)
        assert warning["runtimeHealthStatus"] == "degraded"


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
