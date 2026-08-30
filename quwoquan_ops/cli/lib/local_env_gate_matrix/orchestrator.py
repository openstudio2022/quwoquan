"""stackctl matrix：固定候选上的 Alpha → Beta → Gamma 串行门禁（主状态机，自原单文件逐字搬移）。"""

from __future__ import annotations

import time
from typing import Any

# 测试通过 mock.patch("...local_env_gate_matrix._run_commit_gate") 与
# mock.patch("...local_env_gate_matrix.probe_migration_drift") 打桩；
# 这里保持对包属性的延迟访问以兼容 monkeypatch（参考 feature_tree/gitio 模式）。
import quwoquan_ops.cli.lib.local_env_gate_matrix as _matrix_pkg
from quwoquan_ops.cli.lib.local_env_gate_matrix.data_phases import (
    _acceptance_lease_event,
    _data_cli_runner,
    _data_readiness_path,
    _data_run_ids,
    _homepage_release_evidence,
    _invoke_env,
    _lifecycle_exit_path,
    _record_phase,
    _run_data_phase,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.evidence import (
    _down_target,
    _live_matrix_evidence_errors,
    _provider_local_functional_errors,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    CANONICAL_TARGETS,
    DEVICE_PROFILE_FULL,
    DEVICE_PROFILES,
    TARGET_ENVIRONMENTS,
    DataRunner,
    EnvRunner,
    _evidence_path,
    _namespace,
    _repo_matrix_dir,
    _startup_attempt_matches_package_identity,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.input_validation import (
    ResearchLifecycleUnsupported,
    _resolve_matrix_inputs,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.preflight import (
    _device_uat_bindings,
    _docker_daemon_ready,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.reporting import _write_matrix_result
from quwoquan_ops.cli.lib.local_env_gate_timing import (
    PhaseTimer,
    load_local_env_matrix_budgets,
)
from quwoquan_ops.cli.lib.local_postgres_migration_drift import format_drift_gate_block
from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt


def _run_local_env_gate_matrix(
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
    matrix_run_id: str,
) -> dict[str, Any]:
    """Run one package-bound full integration state machine per local environment."""
    if execution_class not in {"live", "contract-simulation"}:
        raise ValueError("execution_class must be live or contract-simulation")
    if device_profile not in DEVICE_PROFILES:
        raise ValueError("device_profile must be one of " + ", ".join(DEVICE_PROFILES))
    if tuple(targets) != CANONICAL_TARGETS:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix target set is GATE_BLOCK",
            "details": [
                "--targets must be exactly alpha-local,beta-local,gamma-local in order"
            ],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
        }
    try:
        input_bindings = _resolve_matrix_inputs(
            release_attestation=release_attestation,
            rollback_release_attestation=rollback_release_attestation,
            test_data_request=test_data_request,
            test_data_evidence=test_data_evidence,
            test_data_handoff=test_data_handoff,
            telemetry_fn=telemetry_fn,
            provider_fn=provider_fn,
            app_uat_fn=app_uat_fn,
            ios_simulator_device=ios_simulator_device,
            android_emulator_device=android_emulator_device,
            android_physical_device=android_physical_device,
            device_profile=device_profile,
            execution_class=execution_class,
        )
    except ResearchLifecycleUnsupported as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix release lifecycle is GATE_BLOCK",
            "details": [str(exc)],
            "failureCategory": "research_lifecycle_unsupported",
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
        }
    except ValueError as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix release/data inputs are GATE_BLOCK",
            "details": [str(exc)],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
        }

    candidate_release = input_bindings.candidate_release
    rollback_release = input_bindings.rollback_release
    request_by_target = input_bindings.request_by_target
    evidence_by_target = input_bindings.evidence_by_target
    handoff_by_target = input_bindings.handoff_by_target
    compiled_provider_governance = input_bindings.compiled_provider_governance

    budgets = load_local_env_matrix_budgets()
    matrix_dir = _repo_matrix_dir(matrix_run_id)
    wall_started = time.monotonic()
    phases: list[dict[str, Any]] = []
    environments: dict[str, Any] = {}
    overall_exit = 0
    failure_category = ""
    matrix_release_train_id = ""
    package_baselines: dict[str, str] = {}

    docker_ok, docker_detail = _docker_daemon_ready()
    phases.append(
        PhaseTimer("docker_daemon_preflight").finish(
            status="passed" if docker_ok else "gate_block",
            details=[docker_detail],
        )
    )
    if not docker_ok:
        overall_exit = 2
        failure_category = "docker"

    if overall_exit == 0 and include_l0:
        l0 = _matrix_pkg._run_commit_gate()
        phases.append(
            PhaseTimer("L0_commit_gate").finish(
                status="passed" if l0["exitCode"] == 0 else "gate_block",
                details=[f"exit={l0['exitCode']}"],
                report_dir=l0.get("reportDir", ""),
            )
        )
        if l0["exitCode"] != 0:
            overall_exit = int(l0["exitCode"] or 2)
            failure_category = "l0"

    # Freeze all target identities before the first runtime start, Data, or Patrol.
    for target in targets:
        if overall_exit != 0:
            break

        env_name = TARGET_ENVIRONMENTS[target]
        block: dict[str, Any] = {
            "target": target,
            "environment": env_name,
            "workload": "full",
            "profile": "integration",
            "matrixRunId": matrix_run_id,
            "release": candidate_release,
            "rollbackRelease": rollback_release,
        }
        data_ids = _data_run_ids(matrix_run_id, env_name)
        block["dataRunIds"] = data_ids
        environments[target] = block

        # The local targets share resources. Normal down is the sole cleanup path.
        for other in CANONICAL_TARGETS:
            down_payload = _down_target(other, down_fn=down_fn)
            down_exit = _record_phase(
                phases,
                name=f"{target}_pre_down_{other}",
                payload=down_payload,
            )
            if down_exit != 0:
                block["preDown"] = down_payload
                overall_exit = down_exit
                failure_category = "down"
                break
        if overall_exit != 0:
            break

        package_payload = _invoke_env(
            package_fn,
            _namespace(
                command="package",
                kind="runtime",
                env=env_name,
                service="",
                include_services=True,
                target=target,
                output_format="json",
                report_dir="",
                apk_path="",
                verify_remote_apk=False,
                release_attestation=release_attestation,
                rollback_release_attestation=rollback_release_attestation,
            ),
            action=f"{target} package",
        )
        block["package"] = package_payload
        package_exit = _record_phase(
            phases,
            name=f"{target}_package",
            payload=package_payload,
        )
        if package_exit != 0:
            overall_exit = package_exit
            failure_category = "package"
            break
        try:
            active_candidate = _matrix_pkg.active_deployment_candidate_snapshot(target)
            package_identity = _matrix_pkg._package_candidate_release_identity(
                package_payload,
                active_candidate,
                target=target,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            overall_exit = 2
            failure_category = "package_identity"
            phases.append(
                PhaseTimer(f"{target}_package_identity").finish(
                    status="gate_block",
                    details=[str(exc)],
                )
            )
            break
        block["packageIdentity"] = package_identity
        try:
            matrix_release_train_id = _matrix_pkg._freeze_matrix_package_identity(
                package_identity,
                release_train_id=matrix_release_train_id,
                package_baselines=package_baselines,
            )
        except ValueError as exc:
            overall_exit = 2
            failure_category = "release_train_drift"
            phases.append(
                PhaseTimer(f"{target}_package_identity").finish(
                    status="gate_block",
                    details=[str(exc)],
                )
            )
            break
    for target in targets:
        if overall_exit != 0:
            break
        if time.monotonic() - wall_started > int(budgets["hardBudgetSeconds"]):
            overall_exit = 2
            failure_category = "budget"
            phases.append(
                PhaseTimer(f"{target}_budget").finish(
                    status="gate_block",
                    details=["hard budget exhausted before target execution"],
                )
            )
            break

        env_name = TARGET_ENVIRONMENTS[target]
        block = environments[target]
        data_ids = block["dataRunIds"]

        if target in {"alpha-local", "beta-local"}:
            drift = _matrix_pkg.probe_migration_drift(target)
            phases.append(
                PhaseTimer(f"{target}_migration_drift_probe").finish(
                    status="gate_block" if drift.has_drift else "passed",
                    details=[
                        format_drift_gate_block(drift)
                        if drift.has_drift
                        else drift.detail
                    ],
                )
            )
            if drift.has_drift:
                overall_exit = 2
                failure_category = "migration_drift"
                environments[target] = block
                break

        up_payload = _invoke_env(
            up_fn,
            _namespace(
                command="up",
                env=env_name,
                target="",
                workload="full",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                formal_release=False,
                release_manifest="",
                rollout_mode="",
                device_id="",
                output_format="json",
                report_dir="",
            ),
            action=f"{target} up",
        )
        block["up"] = up_payload
        up_exit = _record_phase(phases, name=f"{target}_up", payload=up_payload)
        if up_exit != 0:
            overall_exit = up_exit
            failure_category = "up"
            cleanup_payload = _down_target(target, down_fn=down_fn)
            block["failedUpCleanup"] = cleanup_payload
            cleanup_exit = _record_phase(
                phases,
                name=f"{target}_failed_up_cleanup",
                payload=cleanup_payload,
            )
            if cleanup_exit != 0:
                overall_exit = cleanup_exit
                failure_category = "down"
            environments[target] = block
            break

        if execution_class == "live":
            try:
                startup_attempt = load_startup_attempt(target)
            except ValueError as exc:
                startup_attempt = None
                startup_detail = str(exc)
            else:
                startup_detail = ""
            block["startupAttempt"] = startup_attempt
            startup_identity_ok = _startup_attempt_matches_package_identity(
                startup_attempt,
                target=target,
                environment=env_name,
                package_baseline=package_baselines[target],
            )
            phases.append(
                PhaseTimer(f"{target}_startup_attempt_identity").finish(
                    status="passed" if startup_identity_ok else "gate_block",
                    details=[
                        "running startup attempt identity verified"
                        if startup_identity_ok
                        else startup_detail
                        or "running startup attempt identity is missing or drifted"
                    ],
                )
            )
            if not startup_identity_ok:
                overall_exit = 2
                failure_category = "startup_identity"

        if overall_exit != 0:
            cleanup_payload = _down_target(target, down_fn=down_fn)
            block["startupIdentityCleanup"] = cleanup_payload
            cleanup_exit = _record_phase(
                phases,
                name=f"{target}_startup_identity_cleanup",
                payload=cleanup_payload,
            )
            if cleanup_exit != 0:
                overall_exit = cleanup_exit
                failure_category = "down"
            environments[target] = block
            break

        health_payload = _invoke_env(
            health_fn,
            _namespace(
                command="health",
                target=target,
                scope="full",
                output_format="json",
                report_dir="",
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
            ),
            action=f"{target} health",
        )
        block["health"] = health_payload
        health_exit = _record_phase(
            phases,
            name=f"{target}_health",
            payload=health_payload,
        )
        if health_exit != 0:
            overall_exit = health_exit
            failure_category = "health"

        if overall_exit == 0 and execution_class == "live":
            telemetry_payload = _invoke_env(
                telemetry_fn,
                _namespace(
                    command="product-telemetry-log-sink",
                    target=target,
                    action="all",
                    output_format="json",
                    report_dir=str(matrix_dir / target / "telemetry-before"),
                ),
                action=f"{target} Elasticsearch telemetry preflight",
            )
            block["telemetryBefore"] = telemetry_payload
            telemetry_exit = _record_phase(
                phases,
                name=f"{target}_elasticsearch_telemetry_before",
                payload=telemetry_payload,
            )
            if telemetry_exit != 0:
                overall_exit = telemetry_exit
                failure_category = "elasticsearch"

        if overall_exit == 0 and execution_class == "live":
            provider_payload = _invoke_env(
                provider_fn,
                _namespace(
                    command="provider-conformance",
                    adapter_id="",
                    capability_id="",
                    env=env_name,
                    layer="",
                    matrix=False,
                    environment_matrix=True,
                    execute=True,
                    image_digest="",
                    data_digest="",
                    output_format="json",
                    report_dir=str(matrix_dir / target / "provider-matrix"),
                ),
                action=f"{target} Provider environment matrix",
            )
            provider_contract_errors = _provider_local_functional_errors(
                provider_payload,
                environment=env_name,
                target=target,
                compiled_provider_governance=compiled_provider_governance,
            )
            if provider_contract_errors:
                provider_payload = {
                    **provider_payload,
                    "exitCode": 2,
                    "status": "gate_block",
                    "summary": "Provider local functional evidence is GATE_BLOCK",
                    "details": [
                        *list(provider_payload.get("details") or []),
                        *provider_contract_errors,
                    ],
                    "issues": [
                        *list(provider_payload.get("issues") or []),
                        *provider_contract_errors,
                    ],
                }
            block["providerMatrix"] = provider_payload
            provider_exit = _record_phase(
                phases,
                name=f"{target}_provider_matrix",
                payload=provider_payload,
            )
            if provider_exit != 0:
                overall_exit = provider_exit
                failure_category = "provider"

        if overall_exit == 0:
            data_root = ["python3", "quwoquan_data/scripts/cli.py"]
            original_readiness = _data_readiness_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["originalVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_candidate_apply",
                environment=env_name,
                action="candidate-apply",
                argv=[
                    *data_root,
                    "ship",
                    "apply",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["originalImport"],
                    "--import",
                    "--full-sync",
                ],
                report_path=(
                    original_readiness.parent.parent
                    / data_ids["originalImport"]
                    / "result.json"
                ),
                data_fn=data_fn,
            )
            block["candidateApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_candidate_apply"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_candidate_verify",
                environment=env_name,
                action="candidate-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["originalImport"],
                    "--run-id",
                    data_ids["originalVerify"],
                    "--readiness-phase",
                    "consumer",
                ],
                report_path=original_readiness,
                data_fn=data_fn,
            )
            block["candidateVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_candidate_verify"

        if overall_exit == 0:
            rollback_readiness = _data_readiness_path(
                env_name,
                rollback_release["releaseId"],
                data_ids["rollbackVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_rollback_apply",
                environment=env_name,
                action="rollback-apply",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "rollback",
                    "--to-release",
                    rollback_release["releaseId"],
                    "--from-release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["rollbackImport"],
                    "--import",
                ],
                report_path=(
                    rollback_readiness.parent.parent
                    / data_ids["rollbackImport"]
                    / "result.json"
                ),
                data_fn=data_fn,
            )
            block["rollbackApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_rollback"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_rollback_verify",
                environment=env_name,
                action="rollback-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    rollback_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["rollbackImport"],
                    "--run-id",
                    data_ids["rollbackVerify"],
                    "--readiness-phase",
                    "consumer",
                ],
                report_path=rollback_readiness,
                data_fn=data_fn,
            )
            block["rollbackVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_rollback_verify"

        if overall_exit == 0:
            replay_readiness = _data_readiness_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["replayVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_replay_apply",
                environment=env_name,
                action="replay-apply",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "apply",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["replayImport"],
                    "--import",
                    "--full-sync",
                ],
                report_path=(
                    replay_readiness.parent.parent
                    / data_ids["replayImport"]
                    / "result.json"
                ),
                data_fn=data_fn,
            )
            block["replayApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_replay"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_replay_verify",
                environment=env_name,
                action="replay-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["replayImport"],
                    "--run-id",
                    data_ids["replayVerify"],
                    "--readiness-phase",
                    "commercial",
                ],
                report_path=replay_readiness,
                data_fn=data_fn,
            )
            block["replayVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_replay_verify"

        if overall_exit == 0 and execution_class == "live":
            homepage_payload = _homepage_release_evidence(
                readiness_path=replay_readiness,
                environment=env_name,
                release_id=candidate_release["releaseId"],
            )
            block["homepageReleaseEvidence"] = homepage_payload
            homepage_exit = _record_phase(
                phases,
                name=f"{target}_homepage_release_evidence",
                payload=homepage_payload,
            )
            if homepage_exit != 0:
                overall_exit = homepage_exit
                failure_category = "homepage_release_evidence"

        if overall_exit == 0:
            lifecycle_path = _lifecycle_exit_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["lifecycleExit"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_lifecycle_exit",
                environment=env_name,
                action="lifecycle-exit",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "lifecycle-exit",
                    "--env",
                    env_name,
                    "--original-release-id",
                    candidate_release["releaseId"],
                    "--original-import-run-id",
                    data_ids["originalImport"],
                    "--original-verify-run-id",
                    data_ids["originalVerify"],
                    "--rollback-to-release-id",
                    rollback_release["releaseId"],
                    "--rollback-run-id",
                    data_ids["rollbackImport"],
                    "--rollback-verify-run-id",
                    data_ids["rollbackVerify"],
                    "--replay-import-run-id",
                    data_ids["replayImport"],
                    "--replay-verify-run-id",
                    data_ids["replayVerify"],
                    "--run-id",
                    data_ids["lifecycleExit"],
                ],
                report_path=lifecycle_path,
                data_fn=data_fn,
            )
            block["lifecycleExit"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_lifecycle_exit"

        if overall_exit == 0:
            integration_payload = _invoke_env(
                verify_fn,
                _namespace(
                    command="verify",
                    kind="all",
                    env=env_name,
                    target=target,
                    profile="integration",
                    service="",
                    output_format="json",
                    report_dir="",
                    backup_recovery_receipt="",
                    data_release_id=candidate_release["releaseId"],
                    data_verify_run_id=data_ids["replayVerify"],
                    data_manifest_digest=candidate_release["releaseDigest"],
                    test_data_request=str(request_by_target.get(target) or ""),
                    test_data_evidence=str(evidence_by_target.get(target) or ""),
                    test_data_handoff=str(handoff_by_target.get(target) or ""),
                    data_lifecycle_exit_ref=_evidence_path(lifecycle_path),
                    distribution_root="",
                    verify_hosted=False,
                ),
                action=f"{target} full integration verify",
            )
            block["verify"] = integration_payload
            integration_exit = _record_phase(
                phases,
                name=f"{target}_full_integration_verify",
                payload=integration_payload,
            )
            if integration_exit != 0:
                overall_exit = integration_exit
                failure_category = "integration_verify"

        lease_id = f"{matrix_run_id}-{env_name}-device-uat"
        lease_acquire_event: dict[str, Any] | None = None
        if overall_exit == 0:
            lease_exit, lease_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_acceptance_lease_acquire",
                environment=env_name,
                action="acceptance-lease-acquire",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "acceptance-lease",
                    "acquire",
                    "--env",
                    env_name,
                    "--release-id",
                    candidate_release["releaseId"],
                    "--lease-id",
                    lease_id,
                    "--import-run-id",
                    data_ids["replayImport"],
                    "--verify-run-id",
                    data_ids["replayVerify"],
                ],
                report_path=lifecycle_path.parent / "acceptance-lease-acquire.json",
                data_fn=data_fn,
            )
            block["acceptanceLeaseAcquire"] = lease_payload
            if lease_exit != 0:
                overall_exit = lease_exit
                failure_category = "acceptance_lease_acquire"
            else:
                try:
                    lease_acquire_event = _acceptance_lease_event(
                        lease_payload,
                        action="acquire",
                        environment=env_name,
                        release_id=candidate_release["releaseId"],
                        lease_id=lease_id,
                    )
                except ValueError as exc:
                    overall_exit = 2
                    failure_category = "acceptance_lease_acquire"
                    phases.append(
                        PhaseTimer(f"{target}_acceptance_lease_identity").finish(
                            status="gate_block",
                            details=[str(exc)],
                        )
                    )

        if lease_acquire_event is not None and execution_class == "live":
            for key, platform, device_id in _device_uat_bindings(
                device_profile=device_profile,
                ios_simulator_device=ios_simulator_device,
                android_emulator_device=android_emulator_device,
                android_physical_device=android_physical_device,
            ):
                uat_payload = _invoke_env(
                    app_uat_fn,
                    _namespace(
                        command="app-content-uat",
                        targets=target,
                        platform=platform,
                        device_id=device_id,
                        dry_run=False,
                        output_format="json",
                        report_dir=str(matrix_dir / target / "device-uat" / key),
                    ),
                    action=f"{target} {key}",
                )
                block[key] = uat_payload
                uat_exit = _record_phase(
                    phases,
                    name=f"{target}_{key}",
                    payload=uat_payload,
                )
                if uat_exit != 0:
                    if overall_exit == 0:
                        overall_exit = uat_exit
                        failure_category = "device_uat"
                    break

            telemetry_after = _invoke_env(
                telemetry_fn,
                _namespace(
                    command="product-telemetry-log-sink",
                    target=target,
                    action="all",
                    output_format="json",
                    report_dir=str(matrix_dir / target / "telemetry-after"),
                ),
                action=f"{target} Elasticsearch telemetry readback",
            )
            block["telemetryAfter"] = telemetry_after
            telemetry_after_exit = _record_phase(
                phases,
                name=f"{target}_elasticsearch_telemetry_after",
                payload=telemetry_after,
            )
            if telemetry_after_exit != 0 and overall_exit == 0:
                overall_exit = telemetry_after_exit
                failure_category = "elasticsearch_readback"

        if lease_acquire_event is not None:
            revoke_exit, revoke_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_acceptance_lease_revoke",
                environment=env_name,
                action="acceptance-lease-revoke",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "acceptance-lease",
                    "revoke",
                    "--env",
                    env_name,
                    "--release-id",
                    candidate_release["releaseId"],
                    "--lease-id",
                    lease_id,
                    "--acquire-event-ref",
                    str(lease_acquire_event["eventRef"]),
                ],
                report_path=lifecycle_path.parent / "acceptance-lease-revoke.json",
                data_fn=data_fn,
            )
            block["acceptanceLeaseRevoke"] = revoke_payload
            if revoke_exit == 0:
                try:
                    _acceptance_lease_event(
                        revoke_payload,
                        action="revoke",
                        environment=env_name,
                        release_id=candidate_release["releaseId"],
                        lease_id=lease_id,
                    )
                except ValueError as exc:
                    revoke_exit = 2
                    phases.append(
                        PhaseTimer(f"{target}_acceptance_lease_revoke_identity").finish(
                            status="gate_block",
                            details=[str(exc)],
                        )
                    )
            if revoke_exit != 0:
                overall_exit = revoke_exit
                failure_category = "acceptance_lease_revoke"

        down_payload = _down_target(target, down_fn=down_fn)
        block["down"] = down_payload
        down_exit = _record_phase(
            phases,
            name=f"{target}_down",
            payload=down_payload,
        )
        if down_exit != 0:
            overall_exit = down_exit
            failure_category = "down"

        environments[target] = block
        if overall_exit != 0:
            break

    if overall_exit == 0 and execution_class == "live":
        evidence_errors = _live_matrix_evidence_errors(
            environments,
            release_train_id=matrix_release_train_id,
            package_baselines=package_baselines,
            device_profile=device_profile,
        )
        phases.append(
            PhaseTimer("live_matrix_evidence_identity").finish(
                status="gate_block" if evidence_errors else "passed",
                details=evidence_errors
                or ["all live evidence identities are report-bound"],
            )
        )
        if evidence_errors:
            overall_exit = 2
            failure_category = "evidence_identity"

    wall_seconds = time.monotonic() - wall_started
    if wall_seconds > int(budgets["hardBudgetSeconds"]) and overall_exit == 0:
        overall_exit = 2
        failure_category = "budget"
    return _write_matrix_result(
        matrix_dir=matrix_dir,
        phases=phases,
        environments=environments,
        budgets=budgets,
        wall_seconds=wall_seconds,
        exit_code=overall_exit,
        failure_category=failure_category,
        release_train_id=matrix_release_train_id,
        package_baselines=package_baselines,
        release=candidate_release,
        matrix_run_id=matrix_run_id,
        execution_class=execution_class,
        device_profile=device_profile,
    )
