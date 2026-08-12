"""Run a release-bound supply-chain drill through canonical public CLIs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from content.release.canonical.garbage_collection_contract import (
    write_create_once_json,
)
from content.release.canonical.supply_chain_drill_support import (
    DrillDependencies,
    ENVIRONMENTS,
    FormalCommand,
    FormalCommandResult,
    PLATFORMS,
    PROFILES,
    ReleaseIdentity,
    StageBlocked,
    SupplyChainDrillError,
    command_stage,
    data_command,
    default_dependencies,
    delivery_counts,
    fact_stage,
    previous_import_run_id,
    readiness_phase,
    relative_ref,
    release_identity,
    report_dir,
    run_required,
    runtime_restored,
    runtime_state,
    safe_segment,
    stack_command,
    stage_ref,
    verified_candidate,
)
from content.release.environment.activation_recovery import (
    previous_verified_release,
)
from core.schema import assert_valid


def _delivery(
    *,
    identity: ReleaseIdentity,
    environment: str,
    drill_id: str,
    run_ref: str,
    output_root: Path,
    dependencies: DrillDependencies,
    stages: list[dict[str, object]],
) -> dict[str, int | None]:
    apply_run = f"drill-{drill_id}-apply"
    verify_run = f"drill-{drill_id}-verify"
    result_root = f"env/{environment}/runs/data-release/{identity.release_id}"
    run_required(
        data_command(
            "ship-apply",
            f"{result_root}/{apply_run}/result.json",
            "ship",
            "apply",
            "--release-id",
            identity.release_id,
            "--env",
            environment,
            "--run-id",
            apply_run,
            "--import",
            "--full-sync",
        ),
        dependencies=dependencies,
        stages=stages,
    )
    run_required(
        data_command(
            "ship-verify",
            f"{result_root}/{verify_run}/release-readiness.json",
            "ship",
            "verify",
            "--release-id",
            identity.release_id,
            "--env",
            environment,
            "--import-run-id",
            apply_run,
            "--run-id",
            verify_run,
            "--readiness-phase",
            "research",
        ),
        dependencies=dependencies,
        stages=stages,
    )
    result = run_required(
        stack_command(
            "content-delivery",
            stage_ref(run_ref, "content-delivery"),
            "verify",
            "--env",
            environment,
            "--kind",
            "content-delivery",
            "--profile",
            "integration",
            "--data-release-id",
            identity.release_id,
            "--data-verify-run-id",
            verify_run,
            "--data-manifest-digest",
            identity.manifest_digest,
            "--report-dir",
            report_dir(output_root, run_ref, "content-delivery"),
        ),
        dependencies=dependencies,
        stages=stages,
    )
    return delivery_counts(identity.expected_posts, result)


def _verify_command(
    *,
    name: str,
    environment: str,
    release_id: str,
    import_run_id: str,
    verify_run_id: str,
    phase: str,
) -> FormalCommand:
    evidence = (
        f"env/{environment}/runs/data-release/{release_id}/"
        f"{verify_run_id}/release-readiness.json"
    )
    return data_command(
        name,
        evidence,
        "ship",
        "verify",
        "--release-id",
        release_id,
        "--env",
        environment,
        "--import-run-id",
        import_run_id,
        "--run-id",
        verify_run_id,
        "--readiness-phase",
        phase,
    )


def _exercise_release_history(
    *,
    identity: ReleaseIdentity,
    environment: str,
    drill_id: str,
    previous: Any,
    candidate_readiness: Path,
    dependencies: DrillDependencies,
    stages: list[dict[str, object]],
) -> None:
    rollback_run = f"drill-{drill_id}-rollback"
    rollback_verify = f"drill-{drill_id}-rollback-verify"
    rollback_root = f"env/{environment}/runs/data-release/{previous.release_id}"
    run_required(
        data_command(
            "rollback",
            f"{rollback_root}/{rollback_run}/result.json",
            "ship",
            "rollback",
            "--to-release",
            previous.release_id,
            "--from-release-id",
            identity.release_id,
            "--env",
            environment,
            "--run-id",
            rollback_run,
            "--import",
        ),
        dependencies=dependencies,
        stages=stages,
    )
    run_required(
        _verify_command(
            name="rollback-verify",
            environment=environment,
            release_id=previous.release_id,
            import_run_id=rollback_run,
            verify_run_id=rollback_verify,
            phase=readiness_phase(previous.readiness_path),
        ),
        dependencies=dependencies,
        stages=stages,
    )
    replay_run = f"drill-{drill_id}-replay"
    replay_verify = f"drill-{drill_id}-replay-verify"
    replay_root = f"env/{environment}/runs/data-release/{identity.release_id}"
    run_required(
        data_command(
            "replay",
            f"{replay_root}/{replay_run}/result.json",
            "ship",
            "apply",
            "--release-id",
            identity.release_id,
            "--env",
            environment,
            "--run-id",
            replay_run,
            "--import",
            "--full-sync",
        ),
        dependencies=dependencies,
        stages=stages,
    )
    run_required(
        _verify_command(
            name="replay-verify",
            environment=environment,
            release_id=identity.release_id,
            import_run_id=replay_run,
            verify_run_id=replay_verify,
            phase=readiness_phase(candidate_readiness),
        ),
        dependencies=dependencies,
        stages=stages,
    )


def _rehearsal(
    *,
    identity: ReleaseIdentity,
    environment: str,
    platform: str,
    device_id: str,
    drill_id: str,
    run_ref: str,
    output_root: Path,
    initial_runtime: Mapping[str, object] | None,
    dependencies: DrillDependencies,
    stages: list[dict[str, object]],
) -> None:
    if platform not in PLATFORMS or not device_id.strip():
        raise SupplyChainDrillError("DATA.SUPPLY_CHAIN_DRILL.DEVICE_REQUIRED")
    candidate = verified_candidate(
        output_root=output_root,
        environment=environment,
        identity=identity,
    )
    previous = previous_verified_release(
        output_root=output_root,
        environment=environment,
        import_report_path=candidate.import_report_path,
    )
    if previous is None or previous.release_id == identity.release_id:
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.PREVIOUS_VERIFIED_RELEASE_MISSING"
        )
    previous_identity = release_identity(
        output_root=output_root,
        release_id=previous.release_id,
        environment=environment,
    )
    if previous_identity.manifest_digest != previous.manifest_digest:
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.PREVIOUS_RELEASE_DIGEST_MISMATCH"
        )
    previous_import_run_id(previous)
    target = f"{environment}-local"
    initial_running, initial_workload = runtime_state(initial_runtime)
    if initial_running and initial_workload != "full":
        raise SupplyChainDrillError(
            "DATA.SUPPLY_CHAIN_DRILL.RUNTIME_STATE_UNSAFE"
        )
    if initial_running:
        run_required(
            stack_command(
                "runtime-pause",
                stage_ref(run_ref, "runtime-pause"),
                "down",
                "--target",
                target,
                "--workload",
                initial_workload,
                "--report-dir",
                report_dir(output_root, run_ref, "runtime-pause"),
            ),
            dependencies=dependencies,
            stages=stages,
        )
    run_required(
        stack_command(
            "package",
            stage_ref(run_ref, "package"),
            "package",
            "--env",
            environment,
            "--target",
            target,
            "--release-attestation",
            str(identity.attestation_path),
            "--rollback-release-attestation",
            str(previous_identity.attestation_path),
            "--report-dir",
            report_dir(output_root, run_ref, "package"),
        ),
        dependencies=dependencies,
        stages=stages,
    )
    run_required(
        stack_command(
            "up",
            stage_ref(run_ref, "up"),
            "up",
            "--env",
            environment,
            "--target",
            target,
            "--workload",
            "content-release",
            "--skip-app",
            "--report-dir",
            report_dir(output_root, run_ref, "up"),
        ),
        dependencies=dependencies,
        stages=stages,
    )
    run_required(
        stack_command(
            "app-content-uat",
            stage_ref(run_ref, "app-content-uat"),
            "app-content-uat",
            "--targets",
            target,
            "--platform",
            platform,
            "--device-id",
            device_id,
            "--report-dir",
            report_dir(output_root, run_ref, "app-content-uat"),
        ),
        dependencies=dependencies,
        stages=stages,
    )
    _exercise_release_history(
        identity=identity,
        environment=environment,
        drill_id=drill_id,
        previous=previous,
        candidate_readiness=candidate.readiness_path,
        dependencies=dependencies,
        stages=stages,
    )


def _restore_runtime(
    *,
    initial_runtime: Mapping[str, object] | None,
    target: str,
    environment: str,
    run_ref: str,
    output_root: Path,
    dependencies: DrillDependencies,
    stages: list[dict[str, object]],
) -> bool:
    down = stack_command(
        "down",
        stage_ref(run_ref, "down"),
        "down",
        "--target",
        target,
        "--workload",
        "content-release",
        "--report-dir",
        report_dir(output_root, run_ref, "down"),
    )
    down_stage, result = command_stage(down, dependencies=dependencies)
    stages.append(down_stage)
    if result.returncode:
        return False
    was_running, workload = runtime_state(initial_runtime)
    if was_running:
        restore = stack_command(
            "runtime-restore",
            stage_ref(run_ref, "runtime-restore"),
            "up",
            "--env",
            environment,
            "--target",
            target,
            "--workload",
            workload,
            "--report-dir",
            report_dir(output_root, run_ref, "runtime-restore"),
        )
        restore_stage, result = command_stage(restore, dependencies=dependencies)
        stages.append(restore_stage)
        if result.returncode:
            return False
    try:
        return runtime_restored(initial_runtime, dependencies.read_runtime(target))
    except (OSError, TypeError, ValueError):
        return False


def run_supply_chain_drill(
    *,
    release_id: str,
    environment: str,
    profile: str,
    output_root: Path,
    platform: str = "",
    device_id: str = "",
    dependencies: DrillDependencies | None = None,
) -> tuple[dict[str, object], Path]:
    """Run the requested profile and write one schema-bound summary receipt."""

    environment = str(environment or "").strip()
    profile = str(profile or "").strip()
    if environment not in ENVIRONMENTS or profile not in PROFILES:
        raise SupplyChainDrillError("DATA.SUPPLY_CHAIN_DRILL.INPUT_INVALID")
    release_id = safe_segment(release_id, label="releaseId")
    output_root = output_root.resolve()
    dependencies = dependencies or default_dependencies(output_root)
    started_at = dependencies.now()
    drill_id = safe_segment(
        f"{profile}-{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        label="drillId",
    )
    run_ref = f"env/{environment}/runs/supply-chain-drill/{release_id}/{drill_id}"
    receipt_path = output_root / run_ref / "receipt.json"
    stages: list[dict[str, object]] = []
    counts: dict[str, int | None] = dict.fromkeys(
        ("expected", "imported", "active", "searchable", "recommendable")
    )
    identity: ReleaseIdentity | None = None
    manifest_digest = ""
    blocked = False
    runtime_is_restored = True
    initial_runtime: Mapping[str, object] | None = None
    target = f"{environment}-local"
    try:
        identity = release_identity(
            output_root=output_root,
            release_id=release_id,
            environment=environment,
        )
        manifest_digest = identity.manifest_digest
        counts["expected"] = identity.expected_posts
        evidence_ref = relative_ref(
            identity.attestation_path, output_root=output_root
        )
        if profile == "inspect":
            stages.append(
                fact_stage(
                    "inspect",
                    passed=True,
                    blocker="",
                    evidence_ref=evidence_ref,
                    input={
                        "releaseId": release_id,
                        "environment": environment,
                        "manifestDigest": manifest_digest,
                    },
                )
            )
        elif environment == "prod":
            stages.append(
                fact_stage(
                    profile,
                    passed=False,
                    blocker="DATA.SUPPLY_CHAIN_DRILL.PROD_ACTIVATION_FORBIDDEN",
                    evidence_ref=evidence_ref,
                    input={"releaseId": release_id, "environment": environment},
                )
            )
            blocked = True
        elif profile == "delivery":
            counts = _delivery(
                identity=identity,
                environment=environment,
                drill_id=drill_id,
                run_ref=run_ref,
                output_root=output_root,
                dependencies=dependencies,
                stages=stages,
            )
        else:
            initial_runtime = dependencies.read_runtime(target)
            _rehearsal(
                identity=identity,
                environment=environment,
                platform=str(platform or ""),
                device_id=str(device_id or ""),
                drill_id=drill_id,
                run_ref=run_ref,
                output_root=output_root,
                initial_runtime=initial_runtime,
                dependencies=dependencies,
                stages=stages,
            )
    except (OSError, TypeError, ValueError, SupplyChainDrillError, StageBlocked) as exc:
        blocked = True
        if not stages or stages[-1].get("result") != "failed":
            blocker = str(exc).split(":", 1)[0] or (
                "DATA.SUPPLY_CHAIN_DRILL.UNEXPECTED_FAILURE"
            )
            stages.append(
                fact_stage(
                    "preflight",
                    passed=False,
                    blocker=blocker,
                    evidence_ref=(
                        relative_ref(identity.attestation_path, output_root=output_root)
                        if identity
                        else f"data/releases/{release_id}/attestations/release.json"
                    ),
                    input={"releaseId": release_id, "environment": environment},
                )
            )
    finally:
        runtime_started = any(
            stage.get("name") in {"up", "runtime-pause"}
            for stage in stages
        )
        if profile == "rehearsal" and runtime_started:
            runtime_is_restored = _restore_runtime(
                initial_runtime=initial_runtime,
                target=target,
                environment=environment,
                run_ref=run_ref,
                output_root=output_root,
                dependencies=dependencies,
                stages=stages,
            )
            if not runtime_is_restored:
                blocked = True
                stages.append(
                    fact_stage(
                        "runtime-restore-check",
                        passed=False,
                        blocker="DATA.SUPPLY_CHAIN_DRILL.RUNTIME_NOT_RESTORED",
                        evidence_ref=stage_ref(run_ref, "down"),
                    )
                )
    ended_at = dependencies.now()
    document: dict[str, object] = {
        "schema": "quwoquan_data.supply_chain_drill_receipt",
        "drillId": drill_id,
        "releaseId": release_id,
        "environment": environment,
        "profile": profile,
        "platform": str(platform or ""),
        "deviceId": str(device_id or ""),
        "manifestDigest": manifest_digest,
        "result": "blocked" if blocked else "ready",
        "startedAt": started_at.isoformat().replace("+00:00", "Z"),
        "endedAt": ended_at.isoformat().replace("+00:00", "Z"),
        "runtimeRestored": runtime_is_restored,
        "stages": stages,
        "counts": counts,
    }
    assert_valid(
        document,
        "release",
        "supply_chain_drill_receipt",
        label="supply-chain drill receipt",
    )
    if not write_create_once_json(receipt_path, document):
        raise SupplyChainDrillError("DATA.SUPPLY_CHAIN_DRILL.RECEIPT_CONFLICT")
    return document, receipt_path


__all__ = [
    "DrillDependencies",
    "FormalCommand",
    "FormalCommandResult",
    "SupplyChainDrillError",
    "run_supply_chain_drill",
]
