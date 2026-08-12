"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations

from collections.abc import Mapping

from core.control_types import ExecutionStage, QueueJobState, StageStatus

from content.execution.queue.reliabletask.attempt import latest_attempt_report_path
from content.execution.support import (
    AUTO,
    DataIssueCode,
    DataRecoveryAction,
    ExecutionContext,
    Path,
    StageResult,
    _is_homepage_only_execution,
    load_execution_state,
    save_execution_state,
    stage_issues,
)
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)


@canonical_publish_serialized
def publish_homepage_object(
    execution_id: str,
    object_ref: str,
    *,
    pool_delivery_intent: Mapping[str, object] | None = None,
) -> dict[str, str]:
    """Apply one reviewed homepage through the canonical object transaction."""
    import hashlib

    from core.io import read_json
    from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
    from core.tree_integrity import tree_integrity_stats

    from content.execution.workspace import execution_root
    from content.release.canonical.application import apply_object_transaction
    from content.release.canonical.canonical_inventory import (
        load_or_bootstrap_inventory,
    )
    from content.release.canonical.object_transaction import (
        build_entity_object_transaction_package,
    )
    from content.release.canonical.object_transaction_audit import (
        audit_object_transaction,
    )

    canonical_ref = str(object_ref or "").removeprefix("/entity/").strip("/")
    if len(canonical_ref.split("/")) < 3:
        raise ValueError(f"homepage objectRef 无效：{object_ref!r}")
    transaction_id = (
        f"{execution_id}--entity-"
        f"{hashlib.sha256(canonical_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    execution_dir = execution_root(execution_id)
    if pool_delivery_intent is None:
        from content.execution.closure.pool_delivery import (
            pool_delivery_intent_path,
        )

        intent_path = pool_delivery_intent_path(
            execution_id,
            carrier="homepage",
            object_ref=object_ref,
        )
        loaded_intent = read_json(intent_path)
        if not isinstance(loaded_intent, dict):
            raise ValueError("pool delivery homepage intent must be an object")
        pool_delivery_intent = loaded_intent
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
        pool_delivery_intent=pool_delivery_intent,
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
        before = load_or_bootstrap_inventory(PUBLISH_ROOT)["stats"]["merkleRoot"]
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
    text = text.removeprefix("entities/")
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

def _publishable_homepage_names(ctx: ExecutionContext) -> set[str]:
    """本次准出集合的对象名，与 source 资格判定共用同一口径。"""
    from core.entity_object import collect_execution_entity_objects
    names: set[str] = set()
    for row in collect_execution_entity_objects(
        ctx.execution_id,
        approved_only=True,
        enforce_type_consistency=True,
    ):
        entity_dir = Path(str(row.get("entityDir") or ""))
        if not (entity_dir / "page.md").is_file():
            continue
        if entity_dir.name:
            names.add(entity_dir.name)
    return names


def _assert_video_canonical_plan(
    execution_id: str,
    publish_refs: set[str],
) -> None:
    """Fail before publish job creation when reviewed video bytes already exist."""
    from collections.abc import Mapping

    from core.io import read_json
    from core.paths import PUBLISH_ROOT

    from content.execution.workspace import execution_root
    from content.release.canonical.canonical_inventory import (
        assert_canonical_video_unique,
    )
    from content.release.canonical.object_transaction_contract import (
        ObjectTransactionError,
    )

    root = execution_root(execution_id)
    for raw_ref in sorted(publish_refs):
        relative = str(raw_ref or "").strip().strip("/")
        if not relative.startswith("posts/"):
            raise ObjectTransactionError(
                f"publish plan post ref is not canonical: {raw_ref!r}"
            )
        manifest_path = root / relative / "manifest.json"
        manifest = read_json(manifest_path)
        if not isinstance(manifest, Mapping):
            raise ObjectTransactionError(
                f"publish plan manifest must be an object: {relative}"
            )
        if str(manifest.get("contentType") or "").strip() != "video":
            continue
        assert_canonical_video_unique(
            publish_root=PUBLISH_ROOT,
            manifest=manifest,
            excluded_manifest_path=f"{relative}/manifest.json",
        )

def _run_publish(ctx: ExecutionContext) -> StageResult:
    from core.publish_materialization import materialize_task_publish_inputs

    from content.execution.queue.runtime import reconcile_completed_refs
    from content.execution.recovery.post_recovery import _purge_stale_author_queue
    from content.post import object_index as content_object
    if _is_homepage_only_execution(ctx):
        from content.execution.planning.qualification import (
            finalize_execution_qualification,
        )

        try:
            qualification = finalize_execution_qualification(
                ctx.execution_id,
                publishable_names=_publishable_homepage_names(ctx),
            )
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
    homepage_only = _is_homepage_only_execution(ctx)
    qualified_post_refs: set[str] | None = None
    if not homepage_only:
        from content.execution.closure.post_review import (
            indexed_post_targets,
            load_post_review_closure,
        )

        try:
            post_closure = load_post_review_closure(
                ctx.execution_id,
                expected_object_targets=indexed_post_targets(ctx.execution_id),
                require_quota_milestone=False,
            )
        except (OSError, TypeError, ValueError) as exc:
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                f"post publish closure is invalid: {exc}",
                fallback_stage=ExecutionStage.POST_REVIEW,
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    [str(exc)],
                    code=DataIssueCode.CONTRACT_INVALID,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
        qualified_post_refs = set(post_closure.qualified_publish_refs)
    summary = materialize_task_publish_inputs(
        ctx.execution_id,
        qualified_post_refs=qualified_post_refs,
    )
    if qualified_post_refs is not None:
        try:
            _assert_video_canonical_plan(ctx.execution_id, qualified_post_refs)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            issue = (
                "canonical video identity plan rejected before publish: "
                f"{type(exc).__name__}: {exc}"
            )
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                issue,
                fallback_stage=ExecutionStage.POST_REVIEW,
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    [issue],
                    code=DataIssueCode.CONTRACT_INVALID,
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                ),
            )
    homepage_refs: set[str] = set()
    if homepage_only:
        from content.execution.controller.homepage_authoring import (
            homepage_quota_verdict,
        )

        # Publish closure must equal review qualified set (campaign receipt).
        # approved_only entity pages can still include typed-discarded objects.
        verdict = homepage_quota_verdict(ctx)
        homepage_refs = {
            f"/entity/{label}" if not str(label).startswith("/entity/") else str(label)
            for label in verdict.qualified_refs
        }
        if not homepage_refs:
            return StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "homepage-only publish 前无 qualified 实体主页可发布",
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
    from core.io import read_json

    from content.execution.queue.reliabletask.jobs import prepare_reliable_publish_jobs
    from content.execution.spec_contract import approved_quota
    reliable_jobs = prepare_reliable_publish_jobs(
        ctx,
        homepage_refs=homepage_refs if homepage_only else None,
    )
    if reliable_jobs:
        fleet_report_path = latest_attempt_report_path(ctx.execution_id, "publish")
        fleet_report = (
            read_json(fleet_report_path)
            if fleet_report_path is not None and fleet_report_path.is_file()
            else None
        )
        # Only lifecycle-accepted canonical transaction results satisfy publish
        # quota. Reviewed/finalized work-package files remain an observation.
        required = approved_quota(ctx.execution_id)
        fleet_canonical_accepted = (
            int((fleet_report or {}).get("researchAcceptedCount") or 0)
            + int((fleet_report or {}).get("commercialAcceptedCount") or 0)
            if isinstance(fleet_report, dict)
            else 0
        )
        fleet_quota_met = bool(
            isinstance(fleet_report, dict)
            and fleet_report.get("passed") is True
            and fleet_canonical_accepted >= required
        )
        terminal_failures = [
            job
            for job in reliable_jobs
            if job.state in {QueueJobState.DEAD, QueueJobState.BLOCKED}
        ]
        if terminal_failures and not fleet_quota_met:
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
            job
            for job in reliable_jobs
            if job.state
            not in {
                QueueJobState.SUCCEEDED,
                QueueJobState.DEAD,
                QueueJobState.BLOCKED,
            }
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
                if job.state is QueueJobState.SUCCEEDED
                or (
                    fleet_quota_met
                    and job.state in {QueueJobState.DEAD, QueueJobState.BLOCKED}
                )
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
        # release 统一由 `release campaign-aggregate` 从 frozen campaign 闭包构建；
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
        # Each object transaction already validates its immutable package and
        # applies only its fenced delta.  A global canonical closure is O(N) and
        # belongs to the single campaign->release aggregation boundary, not the
        # per-object hot path.
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
