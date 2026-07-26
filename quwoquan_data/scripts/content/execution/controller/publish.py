"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage, QueueJobState, StageStatus
from content.execution.support import AUTO, DataIssueCode, DataRecoveryAction, ExecutionContext, Path, StageResult, _is_homepage_only_execution, load_execution_state, save_execution_state, stage_issues
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)


@canonical_publish_serialized
def publish_homepage_object(execution_id: str, object_ref: str) -> dict[str, str]:
    """Apply one reviewed homepage through the canonical object transaction."""
    import hashlib

    from core.io import read_json
    from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
    from core.tree_integrity import tree_integrity_stats
    from content.execution.workspace import execution_root
    from content.release.canonical.application import apply_object_transaction
    from content.release.canonical.object_transaction import (
        build_entity_object_transaction_package,
    )
    from content.release.canonical.object_transaction_audit import (
        audit_object_transaction,
        validate_canonical_publish,
    )

    canonical_ref = str(object_ref or "").removeprefix("/entity/").strip("/")
    if len(canonical_ref.split("/")) < 3:
        raise ValueError(f"homepage objectRef 无效：{object_ref!r}")
    transaction_id = (
        f"{execution_id}--entity-"
        f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    execution_dir = execution_root(execution_id)
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
        object_ref=f"/entity/{canonical_ref}",
        transaction_id=transaction_id,
        package_root=package_root,
    )
    if apply_report.is_file() and (canonical_object / "manifest.json").is_file():
        if (
            tree_integrity_stats(canonical_object)["merkleRoot"]
            != tree_integrity_stats(package_root / "object")["merkleRoot"]
        ):
            raise RuntimeError(
                f"completed transaction canonical object drift: /entity/{canonical_ref}"
            )
        applied = read_json(apply_report)
    else:
        before = tree_integrity_stats(PUBLISH_ROOT)["merkleRoot"]
        audit = audit_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            expected_canonical_merkle=before,
        )
        applied = apply_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
        )
    closure = validate_canonical_publish(PUBLISH_ROOT)
    if closure["status"] != "passed":
        raise RuntimeError(f"canonical publish closure failed: {closure['issues'][:5]}")
    return {
        "transactionId": transaction_id,
        "applyReportRef": apply_report.relative_to(OUTPUT_ROOT).as_posix(),
        "canonicalObjectRef": f"entities/{canonical_ref}",
        "canonicalObjectSha256": str(
            tree_integrity_stats(canonical_object)["merkleRoot"]
        ),
        "objectClosureDigest": str(applied.get("objectClosureDigest") or ""),
    }

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
    from content.execution.recovery.post_recovery import _purge_stale_author_queue
    from content.post import object_index as content_object
    from core.publish_materialization import materialize_task_publish_inputs
    from content.execution.queue.runtime import reconcile_completed_refs
    if _is_homepage_only_execution(ctx):
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
    homepage_only = _is_homepage_only_execution(ctx)
    homepage_refs: set[str] = set()
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
    elif summary["postCount"] <= 0:
        return StageResult(
            ExecutionStage.PUBLISH,
            AUTO,
            StageStatus.FAILED,
            "publish 前未物化出可发布 post 输入",
            fallback_stage=ExecutionStage.POST_REVIEW,
        )
    from content.execution.reliabletask_jobs import prepare_reliable_publish_jobs

    reliable_jobs = prepare_reliable_publish_jobs(
        ctx,
        homepage_refs=homepage_refs if homepage_only else None,
    )
    if reliable_jobs:
        terminal_failures = [
            job
            for job in reliable_jobs
            if job.state in {QueueJobState.DEAD, QueueJobState.BLOCKED}
        ]
        if terminal_failures:
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "ReliableTask publish object transaction failed: "
                + ", ".join(job.ref for job in terminal_failures[:10]),
                fallback_stage=(
                    ExecutionStage.BUILD_VALIDATE
                    if homepage_only
                    else ExecutionStage.POST_REVIEW
                ),
            )
        pending_jobs = [
            job for job in reliable_jobs if job.state is not QueueJobState.SUCCEEDED
        ]
        if pending_jobs:
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.WAITING,
                f"等待 ReliableTask 完成 {len(pending_jobs)} 个 canonical object transaction",
                checkpoint_hint=(
                    "Mongo+Redis ReliableTask worker 正在执行对象事务；"
                    "全部 publish job 写入 applied evidence 后，以同一 executionId resume"
                ),
            )
        from content.execution.workspace import write_publish_ref

        if homepage_only:
            write_publish_ref(
                ctx.execution_id,
                entity_refs=[
                    ref.removeprefix("/entity/") for ref in homepage_refs
                ],
            )
        else:
            post_refs = [
                str(job.content_object_dir or "").removeprefix("posts/")
                for job in reliable_jobs
            ]
            write_publish_ref(ctx.execution_id, post_refs=post_refs)
    if homepage_only and not reliable_jobs:
        try:
            from content.execution.workspace import write_publish_ref

            for object_ref in sorted(homepage_refs):
                publish_homepage_object(ctx.execution_id, object_ref)
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
    if not homepage_only and not reliable_jobs:
        # 新发布模型：posts 经 object transaction 原子进入 canonical publish，
        # release 统一由 `release aggregate` 从 publish 闭包构建；
        # 旧的 per-execution assemble/gate 路径已退役。
        try:
            from content.release.canonical.post_promotion import promote_execution_posts

            promote_execution_posts(ctx.execution_id)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            issues = [f"canonical post promotion failed: {type(exc).__name__}: {exc}"]
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "canonical post promotion failed:\n  - " + "\n  - ".join(issues[:10]),
                fallback_stage=ExecutionStage.POST_REVIEW,
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    issues,
                    code=DataIssueCode.CONTRACT_INVALID,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
    if ctx.managed or ctx.release_only:
        from content.release.canonical.object_transaction_audit import validate_canonical_publish
        from core.paths import PUBLISH_ROOT

        closure = validate_canonical_publish(PUBLISH_ROOT)
        if closure["status"] != "passed":
            issues = [str(issue) for issue in closure["issues"]]
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "canonical publish closure failed:\n  - " + "\n  - ".join(issues[:10]),
                fallback_stage=(
                    ExecutionStage.BUILD_VALIDATE if homepage_only else ExecutionStage.POST_REVIEW
                ),
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    issues,
                    code=DataIssueCode.CONTRACT_INVALID,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
        state = load_execution_state(ctx.execution_id)
        save_execution_state(state)
    authored_refs = content_object.iter_content_refs(ctx.execution_id)
    reconciled = reconcile_completed_refs(
        ctx.execution_id,
        authored_refs,
        "author",
        reason="publish_succeeded",
    )
    _purge_stale_author_queue(ctx, reason="publish_succeeded")
    return StageResult(
        ExecutionStage.PUBLISH,
        AUTO,
        StageStatus.DONE,
        "canonical publish transaction gated "
        f"(entities={summary['entityCount']}, posts={summary['postCount']}, "
        f"tags={summary['tagCount']}, relations={summary['relationCount']}, "
        f"authorQueueReconciled={len(reconciled)})",
    )
