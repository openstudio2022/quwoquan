from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import json
import tempfile
from pathlib import Path

from quwoquan_ops.cli.lib.app_launch_attempt import LAUNCH_BLOCKERS, read_app_launch_attempt
from quwoquan_ops.tests.local_contract.stackctl.test_app_launch_attempt__local_contract_test import _run_supervisor

def test_supervisor_preserves_first_canonical_dependency_blocker() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "print('APP.DEPENDENCY.cocoapods_missing: token=very-secret', flush=True); "
            "print('APP.DEPENDENCY.lock_drift: later', flush=True); "
            "raise SystemExit(2)",
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.DEPENDENCY.cocoapods_missing"
    assert payload["warnings"] == []
    assert "very-secret" not in json.dumps(payload, ensure_ascii=False)


def test_supervisor_unregistered_dependency_blocker_falls_back_to_generic() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        receipt = Path(temporary) / "attempt.json"
        result = _run_supervisor(
            receipt,
            "print('APP.DEPENDENCY.sync_failed: raw=secret', flush=True); "
            "raise SystemExit(2)",
        )
        payload = read_app_launch_attempt(receipt)

    assert result.returncode == 2
    assert payload["status"] == "failed"
    assert payload["firstBlocker"] == "APP.LAUNCH.compile_failed"
    assert payload["warnings"] == []
    assert "raw=secret" not in json.dumps(payload, ensure_ascii=False)



def test_dependency_launch_blockers_are_enumerated_by_metadata() -> None:
    assert {
        "APP.DEPENDENCY.cocoapods_missing",
        "APP.DEPENDENCY.cocoapods_mixed",
        "APP.DEPENDENCY.lock_drift",
        "APP.DEPENDENCY.projection_cas_drift",
    } <= LAUNCH_BLOCKERS
