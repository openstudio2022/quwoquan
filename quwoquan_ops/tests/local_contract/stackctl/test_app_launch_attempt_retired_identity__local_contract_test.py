from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import subprocess
import tempfile
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.app_launch_attempt import (
    create_app_launch_attempt,
    read_app_launch_attempt,
    validate_app_launch_attempt,
)
from quwoquan_ops.tests.local_contract.stackctl.test_app_launch_attempt__local_contract_test import (
    CANONICAL_LAUNCHER,
    DIGEST,
    _attempt_identity,
    _new_receipt,
    _supervisor_argv,
)


def test_terminal_carrier_identity_is_retired_and_must_stay_empty() -> None:
    """carrier receipt 机制退役：字段保留 schema 形状但只允许空值。"""
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        created = _new_receipt(receipt)
        assert created["terminalCarrierReceiptDigest"] == ""
        assert created["terminalCarrierReceiptRef"] == ""
        for field in ("terminalCarrierReceiptDigest", "terminalCarrierReceiptRef"):
            tampered = {**created, field: DIGEST if "Digest" in field else "/tmp/x"}
            with pytest.raises(ValueError, match="retired"):
                validate_app_launch_attempt(tampered)


def test_workspace_flutter_run_provenance_is_retired() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        with pytest.raises(
            ValueError,
            match="launchProvenance is not an allowed value",
        ):
            create_app_launch_attempt(
                receipt,
                environment="alpha",
                target="alpha-local",
                platform="ios",
                build_mode="debug",
                run_mode="ui-only",
                device_id="ios-1",
                **{
                    **_attempt_identity(),
                    "launch_provenance": "workspace_flutter_run",
                },
            )


def test_two_supervisor_invocations_create_new_attempts_with_empty_carrier() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        attempts = []
        for index in range(2):
            receipt = root / f"attempt-{index}.json"
            result = subprocess.run(
                _supervisor_argv(
                    receipt,
                    "raise SystemExit(0)",
                ),
                check=False,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 1
            attempts.append(read_app_launch_attempt(receipt))
    assert attempts[0]["attemptId"] != attempts[1]["attemptId"]
    for attempt in attempts:
        assert attempt["terminalCarrierReceiptRef"] == ""
        assert attempt["terminalCarrierReceiptDigest"] == ""


def test_run_sh_retires_terminal_carrier_and_workspace_flutter_run() -> None:
    source = CANONICAL_LAUNCHER.read_text(encoding="utf-8")
    assert "workspace_flutter_run" not in source
    assert "TERMINAL_CARRIER" not in source
    assert "terminal-carrier" not in source
    assert (
        "supported provenance is canonical_launcher or workspace_ide_debug"
        in source
    )


