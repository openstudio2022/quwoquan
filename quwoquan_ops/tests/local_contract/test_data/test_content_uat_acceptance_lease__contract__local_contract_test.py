"""stackctl delegates UAT lease writes to the canonical Data facade."""

from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from quwoquan_ops.cli import stackctl


def test_content_uat_acceptance_lease__calls_data_facade_with_explicit_binding() -> None:
    payload = {
        "schema": "quwoquan_data.release_acceptance_lease_event",
        "environment": "gamma",
        "releaseId": "pilot-002",
        "leaseId": "android-uat-001",
        "action": "acquire",
        "eventRef": "env/gamma/runs/release-acceptance/pilot-002/android-uat-001/acquire/event.json",
    }
    with mock.patch.object(
        stackctl,
        "run",
        return_value=subprocess.CompletedProcess([], 0, __import__("json").dumps(payload), ""),
    ) as run:
        result = stackctl._run_data_acceptance_lease(
            action="acquire",
            environment="gamma",
            release_id="pilot-002",
            import_run_id="apply-001",
            verify_run_id="verify-001",
            lease_id="android-uat-001",
        )

    assert result == payload
    argv = run.call_args.args[0]
    assert argv[:6] == [
        "python3",
        "-B",
        "quwoquan_data/scripts/cli.py",
        "release",
        "acceptance-lease",
        "acquire",
    ]
    assert argv[argv.index("--import-run-id") + 1] == "apply-001"
    assert argv[argv.index("--verify-run-id") + 1] == "verify-001"


def test_content_uat_acceptance_lease__rejects_identity_drift() -> None:
    payload = {
        "schema": "quwoquan_data.release_acceptance_lease_event",
        "environment": "gamma",
        "releaseId": "wrong-release",
        "leaseId": "android-uat-001",
        "action": "acquire",
        "eventRef": "env/gamma/event.json",
    }
    with mock.patch.object(
        stackctl,
        "run",
        return_value=subprocess.CompletedProcess([], 0, __import__("json").dumps(payload), ""),
    ):
        with pytest.raises(ValueError, match="identity-drifted"):
            stackctl._run_data_acceptance_lease(
                action="acquire",
                environment="gamma",
                release_id="pilot-002",
                import_run_id="apply-001",
                verify_run_id="verify-001",
                lease_id="android-uat-001",
            )
