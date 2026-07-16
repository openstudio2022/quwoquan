"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage, StageStatus
from content.execution.support import AUTO, DataIssueCode, DataRecoveryAction, ExecutionContext, Path, StageResult, _is_homepage_only_workflow, save_workflow_state, stage_issues

def _workflow_release_id(execution_id: str) -> str:
    from content.execution.identity import validate_execution_id

    execution_id = validate_execution_id(execution_id)
    return execution_id

def _entity_ref_from_entity_rel(raw: object) -> str:
    text = str(raw or "").strip().strip("/")
    if not text:
        return ""
    if text.startswith("entities/"):
        text = text[len("entities/"):]
    parts = text.split("/")
    if len(parts) < 3:
        return ""
    return f"/entity/{parts[0]}/{parts[1]}/{'/'.join(parts[2:])}"

def _publishable_homepage_refs(ctx: ExecutionContext) -> set[str]:
    from core.entity_object import collect_execution_entity_objects
    refs: set[str] = set()
    for row in collect_execution_entity_objects(
        ctx.execution_id,
        approved_only=True,
        enforce_type_consistency=True,
    ):
        entity_dir = Path(str(row.get("entityDir") or ""))
        if not (entity_dir / "page.md").is_file():
            continue
        ref = _entity_ref_from_entity_rel(row.get("entityRel"))
        if ref:
            refs.add(ref)
    return refs

def _run_publish(ctx: ExecutionContext) -> StageResult:
    from content.execution.recovery.post_recovery import _purge_author_queue_for_stale_workflow
    from content.post import object_index as content_object
    from core.publish_materialization import materialize_task_publish_inputs
    from content.release.canonical.assemble import assemble_release
    from content.release.canonical.gate import gate_publish
    from content.release.environment.handler import write_release_only_ship_report
    from content.execution.queue.runtime import reconcile_completed_refs
    if _is_homepage_only_workflow(ctx):
        from content.execution.qualification import finalize_execution_qualification

        try:
            qualification = finalize_execution_qualification(ctx.execution_id)
        except (OSError, TypeError, ValueError) as exc:
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                f"execution source qualification could not be verified: {exc}",
                fallback_stage=ExecutionStage.BUILD_VALIDATE,
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    [str(exc)],
                    code=DataIssueCode.CONTRACT_INVALID,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
        if not qualification.passed:
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "execution source qualification blocked canonical publish",
                fallback_stage=ExecutionStage.BUILD_VALIDATE,
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    qualification.issues,
                    code=DataIssueCode.QUALITY_FAILED,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
    summary = materialize_task_publish_inputs(ctx.execution_id)
    homepage_only = _is_homepage_only_workflow(ctx)
    if homepage_only:
        homepage_refs = _publishable_homepage_refs(ctx)
        if not homepage_refs:
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "homepage-only publish 前无 approved 实体主页可发布",
                fallback_stage=ExecutionStage.BUILD_VALIDATE,
            )
        try:
            import hashlib

            from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, RELEASE_ROOT
            from core.tree_integrity import tree_integrity_stats
            from content.execution.workspace import execution_root, write_publish_ref
            from content.release.canonical.application import apply_object_transaction
            from content.release.canonical.object_transaction import (
                audit_object_transaction,
                build_entity_object_transaction_package,
                validate_canonical_publish,
            )

            execution_dir = execution_root(ctx.execution_id)
            for object_ref in sorted(homepage_refs):
                canonical_ref = object_ref.removeprefix("/entity/")
                transaction_id = (
                    f"{ctx.execution_id}--entity-"
                    f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
                )
                package_root = execution_dir / "evidence/object-transactions" / transaction_id
                apply_report = (
                    OUTPUT_ROOT
                    / "data/local/workspace/object-transactions"
                    / transaction_id
                    / "apply_report.json"
                )
                canonical_object = PUBLISH_ROOT / "entities" / canonical_ref
                build_entity_object_transaction_package(
                    execution_root=execution_dir,
                    object_ref=object_ref,
                    transaction_id=transaction_id,
                    package_root=package_root,
                )
                if apply_report.is_file() and (canonical_object / "manifest.json").is_file():
                    if (
                        tree_integrity_stats(canonical_object)["merkleRoot"]
                        != tree_integrity_stats(package_root / "object")["merkleRoot"]
                    ):
                        raise RuntimeError(f"completed transaction canonical object drift: {object_ref}")
                    continue
                before = tree_integrity_stats(PUBLISH_ROOT)["merkleRoot"]
                audit = audit_object_transaction(
                    publish_root=PUBLISH_ROOT,
                    output_root=OUTPUT_ROOT,
                    package_root=package_root,
                    transaction_id=transaction_id,
                    expected_canonical_merkle=before,
                )
                apply_object_transaction(
                    publish_root=PUBLISH_ROOT,
                    output_root=OUTPUT_ROOT,
                    package_root=package_root,
                    transaction_id=transaction_id,
                    dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
                )
            closure = validate_canonical_publish(PUBLISH_ROOT)
            if closure["status"] != "passed":
                raise RuntimeError(f"canonical publish closure failed: {closure['issues'][:5]}")
            write_publish_ref(
                ctx.execution_id,
                entity_refs=[ref.removeprefix("/entity/") for ref in homepage_refs],
            )
        except Exception as exc:  # noqa: BLE001
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                f"canonical object transaction failed: {type(exc).__name__}: {exc}",
                fallback_stage=ExecutionStage.BUILD_VALIDATE,
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    [str(exc)],
                    code=DataIssueCode.CONTRACT_INVALID,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
    elif summary["postCount"] <= 0:
        return StageResult(
            ExecutionStage.PUBLISH,
            AUTO,
            StageStatus.FAILED,
            "publish 前未物化出可发布 post 输入",
            fallback_stage=ExecutionStage.POST_REVIEW,
        )
    if not homepage_only:
        try:
            release_id = _workflow_release_id(ctx.execution_id)
            assemble_release(ctx.execution_id, release_id)
            gate_issues = gate_publish(release_id)
            if gate_issues:
                raise RuntimeError("; ".join(gate_issues))
        except (FileExistsError, RuntimeError, ValueError) as exc:
            release_id = _workflow_release_id(ctx.execution_id)
            gate_issues = gate_publish(release_id)
            issues = gate_issues or [f"release package assemble/gate failed: {exc}"]
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "release package assemble/gate failed:\n  - " + "\n  - ".join(issues[:10]),
                fallback_stage=ExecutionStage.POST_REVIEW,
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    issues,
                    code=DataIssueCode.CONTRACT_INVALID,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
    if ctx.managed or ctx.release_only:
        if homepage_only:
            from content.release.canonical.object_transaction import validate_canonical_publish
            from core.paths import PUBLISH_ROOT

            closure = validate_canonical_publish(PUBLISH_ROOT)
            if closure["status"] != "passed":
                issues = [str(issue) for issue in closure["issues"]]
                return StageResult(
                    ExecutionStage.PUBLISH,
                    AUTO,
                    StageStatus.FAILED,
                    "canonical publish closure failed:\n  - " + "\n  - ".join(issues[:10]),
                    fallback_stage=ExecutionStage.BUILD_VALIDATE,
                    issue_records=stage_issues(
                        ExecutionStage.PUBLISH,
                        issues,
                        code=DataIssueCode.CONTRACT_INVALID,
                        recovery=DataRecoveryAction.REWIND_COMPOSE,
                    ),
                )
            state = load_workflow_state(ctx.execution_id)
            for key in ("releaseId", "releaseEvidencePath", "shipReportPath"):
                state.pop(key, None)
            save_workflow_state(state)
        else:
            from verify.gate import gate_verify

            release_id = _workflow_release_id(ctx.execution_id)
            _roots, verify_issues = gate_verify(release=release_id)
            if verify_issues:
                return StageResult(
                    ExecutionStage.PUBLISH,
                    AUTO,
                    StageStatus.FAILED,
                    "release verify failed:\n  - " + "\n  - ".join(verify_issues[:10]),
                    fallback_stage=ExecutionStage.POST_REVIEW,
                    issue_records=stage_issues(
                        ExecutionStage.PUBLISH,
                        verify_issues,
                        code=DataIssueCode.CONTRACT_INVALID,
                        recovery=DataRecoveryAction.REWIND_COMPOSE,
                    ),
                )
            write_release_only_ship_report(
                execution_id=ctx.execution_id,
                release_id=release_id,
                summary=summary,
            )
            state = load_workflow_state(ctx.execution_id)
            for key in ("releaseId", "releaseEvidencePath", "shipReportPath"):
                state.pop(key, None)
            save_workflow_state(state)
    authored_refs = content_object.iter_content_refs(ctx.execution_id)
    reconciled = reconcile_completed_refs(
        ctx.execution_id,
        authored_refs,
        "author",
        reason="publish_succeeded",
    )
    _purge_author_queue_for_stale_workflow(ctx, reason="publish_succeeded")
    return StageResult(
        ExecutionStage.PUBLISH,
        AUTO,
        StageStatus.DONE,
        "canonical publish transaction gated "
        f"(entities={summary['entityCount']}, posts={summary['postCount']}, "
        f"tags={summary['tagCount']}, relations={summary['relationCount']}, "
        f"authorQueueReconciled={len(reconciled)})",
    )
