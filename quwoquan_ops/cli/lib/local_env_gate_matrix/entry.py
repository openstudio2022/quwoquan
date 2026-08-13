"""公开入口：在进程级执行租约下运行门禁矩阵（自原单文件逐字搬移）。"""
from __future__ import annotations

from typing import Any

from quwoquan_ops.cli.lib.local_env_gate_matrix.data_phases import _data_cli_runner
from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    CANONICAL_TARGETS,
    DEVICE_PROFILE_FULL,
    DataRunner,
    EnvRunner,
    MatrixExecutionLeaseBusy,
    _matrix_execution_lease,
    _new_matrix_run_id,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.orchestrator import (
    _run_local_env_gate_matrix,
)


def run_local_env_gate_matrix(
    *,
    package_fn: EnvRunner,
    up_fn: EnvRunner,
    health_fn: EnvRunner,
    verify_fn: EnvRunner,
    down_fn: EnvRunner,
    telemetry_fn: EnvRunner | None = None,
    provider_fn: EnvRunner | None = None,
    app_uat_fn: EnvRunner | None = None,
    filter_catalog_fn: EnvRunner | None = None,
    targets: tuple[str, ...] = CANONICAL_TARGETS,
    include_l0: bool = True,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
    test_data_request: dict[str, str] | None = None,
    test_data_evidence: dict[str, str] | None = None,
    test_data_handoff: dict[str, str] | None = None,
    ios_simulator_device: str = "",
    android_emulator_device: str = "",
    android_physical_device: str = "",
    device_profile: str = DEVICE_PROFILE_FULL,
    data_fn: DataRunner = _data_cli_runner,
    execution_class: str = "live",
) -> dict[str, Any]:
    """Run the matrix under a process-bound lease for live execution only."""
    if execution_class not in {"live", "contract-simulation"}:
        raise ValueError("execution_class must be live or contract-simulation")
    matrix_run_id = _new_matrix_run_id()
    kwargs = {
        "package_fn": package_fn,
        "up_fn": up_fn,
        "health_fn": health_fn,
        "verify_fn": verify_fn,
        "down_fn": down_fn,
        "telemetry_fn": telemetry_fn,
        "provider_fn": provider_fn,
        "app_uat_fn": app_uat_fn,
        "filter_catalog_fn": filter_catalog_fn,
        "targets": targets,
        "include_l0": include_l0,
        "release_attestation": release_attestation,
        "rollback_release_attestation": rollback_release_attestation,
        "test_data_request": test_data_request,
        "test_data_evidence": test_data_evidence,
        "test_data_handoff": test_data_handoff,
        "ios_simulator_device": ios_simulator_device,
        "android_emulator_device": android_emulator_device,
        "android_physical_device": android_physical_device,
        "device_profile": device_profile,
        "data_fn": data_fn,
        "execution_class": execution_class,
        "matrix_run_id": matrix_run_id,
    }
    if execution_class == "contract-simulation":
        return _run_local_env_gate_matrix(**kwargs)
    try:
        with _matrix_execution_lease(matrix_run_id):
            return _run_local_env_gate_matrix(**kwargs)
    except MatrixExecutionLeaseBusy as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl live matrix execution lease is GATE_BLOCK",
            "details": [str(exc)],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
            "matrixRunId": matrix_run_id,
            "executionClass": execution_class,
        }
