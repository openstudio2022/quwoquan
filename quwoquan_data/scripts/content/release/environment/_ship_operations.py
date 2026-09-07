"""Immutable release 的 apply(stage)、activate、rollback 与 consumer verification。

三段编排（DEC-042 lean staging）：

- ``apply``：单环境 import-only。Content 只写 ``posts_candidate`` 与 additive 媒体
  归属；Creator/Homepage 只做 ``upsert``；Tag taxonomy importer 没有 upsert/sync
  之分，它在这里就写入按 releaseId 保留的 snapshot 并切换 taxonomy 自己的 active
  pointer（可重新 Activate previous，见 multi-carrier-release OPEN-022）。Content
  active pointer、``posts``、媒体文件与 Creator/Homepage 的删除/下线一律不动。
- ``verify``（候选态）：按 stage 回执的 ``candidateRevision`` 读回候选闭包。
- ``activate``：绑定 stage + verify 两个 run 的同一候选身份，在 Content 单事务内
  切换 pointer；只有成功之后才执行 Creator/Homepage ``sync`` 的删除/下线与显式
  媒体回收。
- ``rollback``：对目标 release 走 fresh stage → verify → activate，再由 consumer
  verify 做四入口读回。
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.environment._ship_operation_dependencies import (
    ShipOperationDependencies,
)
from content.release.environment.activation_recovery import (
    previous_active_release_identity,
)
from content.release.environment.consistency import (
    report_to_text,
    scan_release_contract,
)
from content.release.environment.homepage_verification_cases import (
    HomepageVerificationCaseError,
)
from content.release.environment.readiness import ShipReadinessPhase
from content.release.model import (
    DeletePolicy,
    DeploymentEnvironment,
    EvidenceStatus,
    ImportMode,
)
from core.control_types import ContentImportPhase, ReleaseRunKind, ReleaseRunStatus
from core.io import read_json, write_json
from core.paths import release_ref
from core.release_layout import payload_digest, payload_file

ROLLBACK_FAILED_CODE = "DATA.DELIVERY.ROLLBACK_FAILED"


def _lifecycle_evidence(release: Path) -> dict[str, Any]:
    header = read_json(payload_file(release, "release.json"))
    return {
        "releaseClass": str(header.get("releaseClass") or ""),
        "productLifecycleState": str(
            header.get("productLifecycleState") or ""
        ),
        "containsUnverifiedAssets": bool(
            header.get("containsUnverifiedAssets")
        ),
        "manifestDigest": payload_digest(release),
    }


def _single_environment(raw: object, *, command: str) -> str:
    envs = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    if len(envs) != 1:
        raise SystemExit(
            f"[ship] {command} 只接受单个 --env；候选与激活身份按环境逐一绑定"
        )
    return envs[0]


def _relative(dependencies: ShipOperationDependencies, path: Path) -> str:
    return path.relative_to(dependencies.output_root).as_posix()


def _run_reference_importers(
    *,
    dependencies: ShipOperationDependencies,
    release: Path,
    contract: Mapping[str, Any],
    env: str,
    run: Path,
    run_id: str,
    target: Any,
    dry_run: bool,
    destructive: bool,
) -> tuple[dict[str, str], Path]:
    """Tag/Creator/Homepage importer 与 coverage/case 证据。

    ``destructive=False`` 只允许 additive ``upsert``；``destructive=True`` 只在
    Content activate 成功后使用，才允许 Creator/Homepage ``sync`` 删除或下线。
    """
    reference_mode = ImportMode.SYNC if destructive else ImportMode.UPSERT
    refs: dict[str, str] = {}
    tag_receipt = dependencies.run_tag_importer(
        release=release, env=env, run=run, mongo_uri=target.mongo_uri, dry_run=dry_run,
    )
    refs["tagImportReportRef"] = _relative(dependencies, tag_receipt)
    creator_receipt = dependencies.run_creator_importer(
        release=release, env=env, run=run, mongo_uri=target.mongo_uri,
        postgres_dsn=target.user_postgres_dsn,
        media_avatar_base_url=target.media_delivery_base_url,
        dry_run=dry_run, mode=reference_mode,
    )
    refs["creatorImportReportRef"] = _relative(dependencies, creator_receipt)
    homepage_import_report = dependencies.run_homepage_importer(
        release=release, env=env, run=run, run_id=run_id, mongo_uri=target.mongo_uri,
        media_image_base_url=target.media_delivery_base_url,
        dry_run=dry_run, mode=reference_mode,
    )
    refs["homepageImportReportRef"] = _relative(
        dependencies, run / "homepage-import.json"
    )
    coverage_receipt = dependencies.write_environment_coverage_receipt(
        environment=target.environment, release_id=release.name, run_id=run_id,
        release_root=release, run_root=run, importer_report=homepage_import_report,
        api_base_url=target.api_base_url,
    )
    refs["coverageReceiptRef"] = _relative(dependencies, coverage_receipt)
    expected_entities = contract.get("desiredRefs", {}).get("entities", [])
    if not dry_run and expected_entities:
        try:
            verification_cases = dependencies.write_homepage_verification_case_manifest(
                environment=target.environment, release_root=release, run_root=run,
                run_id=run_id, importer_report=homepage_import_report,
            )
        except HomepageVerificationCaseError as exc:
            raise SystemExit(
                f"[ship] homepage verification case manifest failed: {exc}"
            ) from exc
        refs["homepageVerificationCasesRef"] = _relative(dependencies, verification_cases)
    return refs, creator_receipt


def apply_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    """Stage one immutable release into one environment without activating it."""

    release_id = str(args.release_id)
    release, contract = dependencies.load_release(release_id)
    lifecycle_evidence = _lifecycle_evidence(release)
    env = _single_environment(args.env, command="apply")
    if (
        env == DeploymentEnvironment.PROD
        and args.import_to_db
        and not args.dry_run
        and not args.confirm_prod_apply
    ):
        raise SystemExit("[ship] prod apply 需要 --confirm-prod-apply")
    preflight = scan_release_contract(contract, release_root=release, phase="preflight")
    print(report_to_text(preflight))
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] release consistency preflight failed")
    full_sync = bool(args.full_sync)
    if dependencies.release_requires_full_sync(release) and not full_sync:
        raise SystemExit("[ship] immutable release requires --full-sync")
    dependencies.assert_environment_release_policy(
        release=release, contract=contract, environment=env,
    )
    target = dependencies.resolve_environment_release_target(env)
    dependencies.assert_target_action_allowed(
        target=target, import_to_db=bool(args.import_to_db),
        dry_run=bool(args.dry_run), action="apply",
    )
    run_id = str(args.run_id or f"apply-{dependencies.now_compact()}")
    run = dependencies.create_run(env, release_id, run_id, kind=ReleaseRunKind.APPLY)
    if args.import_to_db and not args.dry_run:
        # Stage 只证明导入能力；lifecycle readback 归 verify/activate 之后。
        dependencies.require_environment_readiness(
            environment=target.environment, phase=ShipReadinessPhase.IMPORT,
            run=run, release_id=release_id,
            manifest_digest=lifecycle_evidence["manifestDigest"],
        )
    write_json(run / "consistency-preflight.json", preflight)
    if target.media_sync_root is not None and args.import_to_db and not args.dry_run:
        dependencies.sync_media(
            release=release, destination=str(target.media_sync_root), run=run,
        )
    refs: dict[str, Any] = {}
    candidate_revision: int | None = None
    if args.import_to_db:
        refs, creator_receipt = _run_reference_importers(
            dependencies=dependencies, release=release, contract=contract, env=env,
            run=run, run_id=run_id, target=target, dry_run=bool(args.dry_run),
            destructive=False,
        )
        stage_report = dependencies.run_content_importer(
            release=release, env=env, run=run, mongo_uri=target.mongo_uri,
            media_avatar_base_url=target.media_delivery_base_url,
            media_image_base_url=target.media_delivery_base_url,
            media_video_base_url=target.media_delivery_base_url,
            dry_run=bool(args.dry_run), creator_receipt=creator_receipt,
            phase=ContentImportPhase.STAGE,
            mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            delete_policy=DeletePolicy.TOMBSTONE if full_sync else DeletePolicy.NONE,
        )
        refs["contentImportReportRef"] = _relative(dependencies, run / "import.json")
        if not args.dry_run:
            candidate_revision = int(stage_report["candidateRevision"])
    dependencies.write_release_evidence(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": env,
            "releaseId": release_id,
            **lifecycle_evidence,
            "runId": run_id,
            "status": (
                ReleaseRunStatus.DRY_RUN
                if args.dry_run
                else (
                    ReleaseRunStatus.COMPLETED
                    if args.import_to_db
                    else ReleaseRunStatus.PREPARED
                )
            ),
            "contentPhase": ContentImportPhase.STAGE.value,
            "fullSync": full_sync,
            **({"candidateRevision": candidate_revision} if candidate_revision else {}),
            **refs,
        },
        "environment_release_result",
    )
    print(f"[ship] {env} staged release={release_id} run={run_id} evidence={run}")


def _load_completed_run(
    dependencies: ShipOperationDependencies,
    *,
    env: str,
    release_id: str,
    run_id: str,
    manifest_digest: str,
    content_phase: ContentImportPhase,
    label: str,
) -> dict[str, Any]:
    run = dependencies.run_root(env, release_id, run_id)
    result_path = run / "result.json"
    if not result_path.is_file():
        raise SystemExit(
            f"[ship] {label} run {run_id} has no result evidence for {release_id}; "
            f"a completed {content_phase.value} run is required"
        )
    result = read_json(result_path)
    if (
        result.get("environment") != env
        or result.get("releaseId") != release_id
        or result.get("manifestDigest") != manifest_digest
        or result.get("status") != ReleaseRunStatus.COMPLETED
        or result.get("contentPhase") != content_phase.value
        or int(result.get("candidateRevision") or 0) <= 0
    ):
        raise SystemExit(
            f"[ship] {label} run {run_id} is not a completed {content_phase.value} "
            f"run for {release_id}@{manifest_digest}"
        )
    return result


def activate_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    """Switch the active pointer to an exactly verified candidate, then clean up."""

    release_id = str(args.release_id)
    release, contract = dependencies.load_release(release_id)
    lifecycle_evidence = _lifecycle_evidence(release)
    env = _single_environment(args.env, command="activate")
    expected_revision = int(args.expected_revision)
    if expected_revision < 0:
        raise SystemExit("[ship] activate --expected-revision 必须为非负整数")
    if env == DeploymentEnvironment.PROD and not args.confirm_prod_apply:
        raise SystemExit("[ship] prod activate 需要 --confirm-prod-apply")
    manifest_digest = lifecycle_evidence["manifestDigest"]
    import_run_id = str(args.import_run_id).strip()
    verify_run_id = str(args.verify_run_id).strip()
    stage_result = _load_completed_run(
        dependencies, env=env, release_id=release_id, run_id=import_run_id,
        manifest_digest=manifest_digest, content_phase=ContentImportPhase.STAGE,
        label="import",
    )
    verify_result = _load_completed_run(
        dependencies, env=env, release_id=release_id, run_id=verify_run_id,
        manifest_digest=manifest_digest, content_phase=ContentImportPhase.VERIFY,
        label="verify",
    )
    candidate_revision = int(stage_result["candidateRevision"])
    if (
        int(verify_result["candidateRevision"]) != candidate_revision
        or verify_result.get("importRunId") != import_run_id
    ):
        raise SystemExit(
            "[ship] verify run does not bind the staged candidate identity: "
            f"stage={candidate_revision} verify={verify_result.get('candidateRevision')}"
        )
    full_sync = bool(stage_result.get("fullSync"))
    dependencies.assert_environment_release_policy(
        release=release, contract=contract, environment=env,
    )
    target = dependencies.resolve_environment_release_target(env)
    dependencies.assert_target_action_allowed(
        target=target, import_to_db=True, dry_run=False, action="activate",
    )
    run_id = str(args.run_id or f"activate-{dependencies.now_compact()}")
    run = dependencies.create_run(env, release_id, run_id, kind=ReleaseRunKind.ACTIVATE)
    dependencies.require_environment_readiness(
        environment=target.environment, phase=ShipReadinessPhase.IMPORT,
        run=run, release_id=release_id, manifest_digest=manifest_digest,
    )
    stage_run = dependencies.run_root(env, release_id, import_run_id)
    activation = dependencies.run_content_importer(
        release=release, env=env, run=run, mongo_uri=target.mongo_uri,
        media_avatar_base_url=target.media_delivery_base_url,
        media_image_base_url=target.media_delivery_base_url,
        media_video_base_url=target.media_delivery_base_url,
        dry_run=False,
        # Creator receipt 已在 stage run 由 additive upsert 验证，activate 绑定同一份。
        creator_receipt=stage_run / "creator-import.json",
        phase=ContentImportPhase.ACTIVATE, candidate_revision=candidate_revision,
        expected_revision=expected_revision,
        mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
        delete_policy=DeletePolicy.TOMBSTONE if full_sync else DeletePolicy.NONE,
    )
    activated_result: dict[str, Any] = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        **lifecycle_evidence,
        "runId": run_id,
        "importRunId": import_run_id,
        "verifyRunId": verify_run_id,
        "contentPhase": ContentImportPhase.ACTIVATE.value,
        "fullSync": full_sync,
        "candidateRevision": candidate_revision,
        "revision": int(activation["revision"]),
        "contentImportReportRef": _relative(dependencies, run / "import.json"),
    }
    # Pointer 已切换，以下收尾都在 Content 事务之外。任一步失败都必须留下带
    # revision 的 failed result：重跑 activate 会命中 CANDIDATE_ALREADY_ACTIVE，
    # 只有可观测的终态才能让 consumer verify / fresh rollback 接手。
    refs: dict[str, str] = {}
    try:
        # 引用型对象在这里再跑一遍：full-sync 时才允许 Creator/Homepage ``sync``
        # 删除/下线；否则只是幂等 upsert。activate run 因此持有 consumer verify
        # 需要的完整导入证据。
        refs, _ = _run_reference_importers(
            dependencies=dependencies, release=release, contract=contract, env=env,
            run=run, run_id=run_id, target=target, dry_run=False, destructive=full_sync,
        )
        if target.media_sync_root is not None and dependencies.prune_media is not None:
            dependencies.prune_media(
                release=release,
                previous_release=_previous_release_root(
                    dependencies, release=release, release_id=release_id,
                    stage_result=stage_result, activation=activation,
                ),
                destination=str(target.media_sync_root), run=run,
            )
            refs["mediaPruneRef"] = _relative(dependencies, run / "media-prune.json")
        dependencies.write_applied_ref(run=run, env=env, release_id=release_id)
    except (SystemExit, OSError, RuntimeError, ValueError, TypeError) as exc:
        if not refs:
            failed_stage = "post_activate_reference_sync"
        elif "mediaPruneRef" not in refs and target.media_sync_root is not None:
            failed_stage = "post_activate_media_prune"
        else:
            failed_stage = "applied_ref"
        dependencies.write_release_evidence(
            run / "result.json",
            {
                **activated_result,
                **refs,
                "status": ReleaseRunStatus.FAILED,
                "failedStage": failed_stage,
                "error": f"DATA.DELIVERY.POST_ACTIVATE_FAILED: {str(exc)[:900]}",
            },
            "environment_release_result",
        )
        raise SystemExit(
            f"[ship] DATA.DELIVERY.POST_ACTIVATE_FAILED: env={env} release={release_id} "
            f"revision={activation['revision']} failedStage={failed_stage}: {exc}"
        ) from exc
    dependencies.write_release_evidence(
        run / "result.json",
        {**activated_result, **refs, "status": ReleaseRunStatus.COMPLETED},
        "environment_release_result",
    )
    print(
        f"[ship] {env} activated release={release_id} revision={activation['revision']} "
        f"run={run_id} evidence={run}"
    )


def _previous_release_root(
    dependencies: ShipOperationDependencies,
    *,
    release: Path,
    release_id: str,
    stage_result: Mapping[str, Any],
    activation: Mapping[str, Any],
) -> Path | None:
    """Resolve the previous active release root for post-activate media prune.

    ``None`` means "this is the first activation, prune may keep only the new
    closure". A previous release that is known from stage/activate evidence but
    unavailable locally is returned as a non-existent path so ``prune_media``
    skips deletion instead of pruning the rollback window away.
    """

    previous_release_id = str(stage_result.get("previousReleaseId") or "").strip()
    if not previous_release_id:
        previous_release_id = previous_active_release_identity(activation)[0]
    if not previous_release_id or previous_release_id == release_id:
        return None
    try:
        previous_release, _ = dependencies.load_release(previous_release_id)
    except (SystemExit, OSError, ValueError, TypeError):
        return release.parent / previous_release_id
    return previous_release


def rollback_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    """Fresh stage → verify → activate of the rollback target release."""

    from content.release.environment._ship_consumer_verification import (
        verify_release_candidate,
    )

    target_id = str(args.to_release)
    source_id = str(args.from_release_id).strip()
    if not source_id or source_id == target_id:
        raise SystemExit("[ship] rollback requires a distinct --from-release-id")
    release, contract = dependencies.load_release(target_id)
    lifecycle_evidence = _lifecycle_evidence(release)
    env = _single_environment(args.env, command="rollback")
    dependencies.assert_environment_release_policy(
        release=release, contract=contract, environment=env,
    )
    expected_revision = int(args.expected_revision)
    if expected_revision < 0:
        raise SystemExit("[ship] rollback --expected-revision 必须为非负整数")
    target = dependencies.resolve_environment_release_target(env)
    if (
        env == DeploymentEnvironment.PROD
        and args.import_to_db
        and not args.dry_run
        and not args.confirm_prod_apply
    ):
        raise SystemExit("[ship] prod rollback 需要 --confirm-prod-apply")
    preflight = scan_release_contract(contract, release_root=release, phase="preflight")
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] rollback target release consistency failed")
    dependencies.assert_target_action_allowed(
        target=target, import_to_db=bool(args.import_to_db),
        dry_run=bool(args.dry_run), action="rollback",
    )
    run_id = str(args.run_id or f"rollback-{dependencies.now_compact()}")
    run = dependencies.create_run(env, target_id, run_id, kind=ReleaseRunKind.ROLLBACK)
    dependencies.write_release_evidence(
        run / "rollback_ref.json",
        {
            "schema": "quwoquan_data.rollback_release_ref",
            "rollbackTo": target_id,
            "rollbackFromReleaseId": source_id,
            "releaseRef": release_ref(target_id),
        },
        "rollback_release_ref",
    )
    write_json(run / "consistency-preflight.json", preflight)
    base_result: dict[str, Any] = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": target_id,
        **lifecycle_evidence,
        "runId": run_id,
    }
    if not args.import_to_db or args.dry_run:
        stage_run_id = f"{run_id}-stage"
        apply_release(
            argparse.Namespace(
                release_id=target_id, env=env, run_id=stage_run_id,
                import_to_db=bool(args.import_to_db), full_sync=True,
                dry_run=bool(args.dry_run), confirm_prod_apply=bool(args.confirm_prod_apply),
            ),
            dependencies=dependencies,
        )
        dependencies.write_release_evidence(
            run / "result.json",
            {
                **base_result,
                "status": ReleaseRunStatus.DRY_RUN if args.dry_run else ReleaseRunStatus.PREPARED,
                "stageRunId": stage_run_id,
            },
            "environment_release_result",
        )
        print(f"[ship] rollback env={env} target={target_id} run={run_id} (not activated)")
        return

    stage_run_id = f"{run_id}-stage"
    verify_run_id = f"{run_id}-verify"
    activate_run_id = f"{run_id}-activate"
    stage_names = (
        ("stage", stage_run_id),
        ("verify", verify_run_id),
        ("activate", activate_run_id),
    )
    completed: dict[str, str] = {}
    try:
        apply_release(
            argparse.Namespace(
                release_id=target_id, env=env, run_id=stage_run_id, import_to_db=True,
                full_sync=True, dry_run=False, confirm_prod_apply=bool(args.confirm_prod_apply),
            ),
            dependencies=dependencies,
        )
        completed["stageRunId"] = stage_run_id
        verify_release_candidate(
            argparse.Namespace(
                release_id=target_id, env=env, import_run_id=stage_run_id,
                run_id=verify_run_id,
            ),
            dependencies=dependencies,
        )
        completed["verifyRunId"] = verify_run_id
        activate_release(
            argparse.Namespace(
                release_id=target_id, env=env, import_run_id=stage_run_id,
                verify_run_id=verify_run_id, run_id=activate_run_id,
                expected_revision=expected_revision,
                confirm_prod_apply=bool(args.confirm_prod_apply),
            ),
            dependencies=dependencies,
        )
        completed["activateRunId"] = activate_run_id
        # pointer 切换发生在 activate 子 run；lifecycle 证据按该子 run 判定回滚身份。
        dependencies.write_release_evidence(
            dependencies.run_root(env, target_id, activate_run_id) / "rollback_ref.json",
            {
                "schema": "quwoquan_data.rollback_release_ref",
                "rollbackTo": target_id,
                "rollbackFromReleaseId": source_id,
                "releaseRef": release_ref(target_id),
            },
            "rollback_release_ref",
        )
    except (SystemExit, OSError, RuntimeError, ValueError, TypeError) as exc:
        # report 契约漂移抛 RuntimeError、schema 违反抛 ValueError、release 文件缺失
        # 抛 OSError；它们都必须收敛为同一 rollback_failed 终态，不能绕过。
        failed_stage = next(
            (name for name, sub_run in stage_names if f"{name}RunId" not in completed),
            "rollback_ref",
        )
        dependencies.write_release_evidence(
            run / "result.json",
            {
                **base_result,
                "status": ReleaseRunStatus.FAILED,
                "failedStage": failed_stage,
                "error": f"{ROLLBACK_FAILED_CODE}: {str(exc)[:900]}",
                **completed,
            },
            "environment_release_result",
        )
        raise SystemExit(
            f"[ship] {ROLLBACK_FAILED_CODE}: env={env} target={target_id} "
            f"failedStage={failed_stage}: {exc}"
        ) from exc
    activate_result = read_json(
        dependencies.run_root(env, target_id, activate_run_id) / "result.json"
    )
    dependencies.write_release_evidence(
        run / "result.json",
        {
            **base_result,
            "status": ReleaseRunStatus.COMPLETED,
            "contentPhase": ContentImportPhase.ACTIVATE.value,
            "fullSync": True,
            "candidateRevision": int(activate_result["candidateRevision"]),
            "revision": int(activate_result["revision"]),
            "contentImportReportRef": str(activate_result.get("contentImportReportRef") or ""),
            **completed,
        },
        "environment_release_result",
    )
    print(
        f"[ship] rollback env={env} target={target_id} run={run_id} "
        f"activateRun={activate_run_id}"
    )


def verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    from content.release.environment._ship_consumer_verification import (
        verify_release_consumers as verify_consumers,
    )

    verify_consumers(args, dependencies=dependencies)
