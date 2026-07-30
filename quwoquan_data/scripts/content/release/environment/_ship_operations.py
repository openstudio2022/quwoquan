"""Immutable release 的 apply、rollback 与 consumer verification 操作。"""

from __future__ import annotations

import argparse
from pathlib import Path

from content.release.environment._ship_operation_dependencies import (
    ShipOperationDependencies,
)
from content.release.environment.baseline_api_verification import (
    BaselineApiVerificationError,
)
from content.release.environment.consistency import report_to_text, scan_release_contract
from content.release.environment.homepage_api_verification import (
    HomepageApiVerificationError,
)
from content.release.environment.homepage_verification_cases import (
    HomepageVerificationCaseError,
)
from content.release.environment.post_api_verification import PostApiVerificationError
from content.release.environment.release_readiness import (
    EnvironmentReleaseReadinessError,
)
from content.release.environment.topology import EnvironmentReleaseMode
from content.release.model import (
    DeletePolicy,
    DeploymentEnvironment,
    EvidenceStatus,
    ImportMode,
    ReleaseKind,
)
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import read_json, write_json
from core.paths import release_ref
from core.release_layout import payload_digest, payload_file


def apply_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    release_id = str(args.release_id)
    release, contract = dependencies.load_release(release_id)
    envs = [item.strip() for item in str(args.env).split(",") if item.strip()]
    if not envs:
        raise SystemExit("[ship] apply 需要 --env")
    if (
        DeploymentEnvironment.PROD in envs
        and args.import_to_db
        and not args.dry_run
        and not args.confirm_prod_apply
    ):
        raise SystemExit("[ship] prod apply 需要 --confirm-prod-apply")
    preflight = scan_release_contract(
        contract,
        release_root=release,
        phase="preflight",
    )
    print(report_to_text(preflight))
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] release consistency preflight failed")
    full_sync = bool(args.full_sync)
    if dependencies.release_requires_full_sync(release) and not full_sync:
        raise SystemExit("[ship] immutable release requires --full-sync")
    for env in envs:
        target = dependencies.resolve_environment_release_target(env)
        dependencies.assert_target_action_allowed(
            target=target,
            import_to_db=bool(args.import_to_db),
            dry_run=bool(args.dry_run),
            action="apply",
        )
        run_id = str(args.run_id or f"apply-{dependencies.now_compact()}")
        run = dependencies.create_run(
            env,
            release_id,
            run_id,
            kind=ReleaseRunKind.APPLY,
        )
        if args.import_to_db and not args.dry_run:
            dependencies.require_environment_readiness(
                environment=target.environment,
                consumer=False,
                run=run,
            )
        write_json(run / "consistency-preflight.json", preflight)
        if (
            target.media_sync_root is not None
            and args.import_to_db
            and not args.dry_run
        ):
            dependencies.sync_media(
                release=release,
                destination=str(target.media_sync_root),
                run=run,
            )
        verification_cases_ref = ""
        tag_import_ref = ""
        creator_import_ref = ""
        content_import_ref = ""
        homepage_import_ref = ""
        if args.import_to_db:
            tag_receipt = dependencies.run_tag_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                dry_run=bool(args.dry_run),
            )
            tag_import_ref = tag_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            creator_receipt = dependencies.run_creator_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                postgres_dsn=target.user_postgres_dsn,
                media_avatar_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
            creator_import_ref = creator_receipt.relative_to(
                dependencies.output_root
            ).as_posix()
            dependencies.run_content_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                media_image_base_url=target.media_delivery_base_url,
                media_video_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
                delete_policy=(
                    DeletePolicy.TOMBSTONE if full_sync else DeletePolicy.NONE
                ),
                creator_receipt=creator_receipt,
            )
            content_import_ref = (run / "import.json").relative_to(
                dependencies.output_root
            ).as_posix()
            homepage_import_report = dependencies.run_homepage_importer(
                release=release,
                env=env,
                run=run,
                run_id=run_id,
                mongo_uri=target.mongo_uri,
                media_image_base_url=target.media_delivery_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
            homepage_import_ref = (run / "homepage-import.json").relative_to(
                dependencies.output_root
            ).as_posix()
            expected_entities = contract.get("desiredRefs", {}).get("entities", [])
            if not args.dry_run and expected_entities:
                try:
                    verification_cases = (
                        dependencies.write_homepage_verification_case_manifest(
                            environment=target.environment,
                            release_root=release,
                            run_root=run,
                            run_id=run_id,
                            importer_report=homepage_import_report,
                        )
                    )
                except HomepageVerificationCaseError as exc:
                    raise SystemExit(
                        f"[ship] homepage verification case manifest failed: {exc}"
                    ) from exc
                verification_cases_ref = verification_cases.relative_to(
                    dependencies.output_root
                ).as_posix()
        if args.import_to_db and not args.dry_run:
            dependencies.write_applied_ref(
                run=run,
                env=env,
                release_id=release_id,
            )
        dependencies.write_release_evidence(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
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
                "homepageVerificationCasesRef": verification_cases_ref,
                "tagImportReportRef": tag_import_ref,
                "creatorImportReportRef": creator_import_ref,
                "contentImportReportRef": content_import_ref,
                "homepageImportReportRef": homepage_import_ref,
            },
            "environment_release_result",
        )
        print(f"[ship] {env} release={release_id} run={run_id} evidence={run}")


def rollback_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    target_id = str(args.to_release)
    source_id = str(args.from_release_id).strip()
    if not source_id or source_id == target_id:
        raise SystemExit("[ship] rollback requires a distinct --from-release-id")
    release, contract = dependencies.load_release(target_id)
    env = str(args.env)
    target = dependencies.resolve_environment_release_target(env)
    if (
        env == DeploymentEnvironment.PROD
        and args.import_to_db
        and not args.dry_run
        and not args.confirm_prod_apply
    ):
        raise SystemExit("[ship] prod rollback 需要 --confirm-prod-apply")
    preflight = scan_release_contract(
        contract,
        release_root=release,
        phase="preflight",
    )
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] rollback target release consistency failed")
    dependencies.assert_target_action_allowed(
        target=target,
        import_to_db=bool(args.import_to_db),
        dry_run=bool(args.dry_run),
        action="rollback",
    )
    run_id = str(args.run_id or f"rollback-{dependencies.now_compact()}")
    run = dependencies.create_run(
        env,
        target_id,
        run_id,
        kind=ReleaseRunKind.ROLLBACK,
    )
    if args.import_to_db and not args.dry_run:
        dependencies.require_environment_readiness(
            environment=target.environment,
            consumer=False,
            run=run,
        )
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
    if (
        target.media_sync_root is not None
        and args.import_to_db
        and not args.dry_run
    ):
        dependencies.sync_media(
            release=release,
            destination=str(target.media_sync_root),
            run=run,
        )
    tag_import_ref = ""
    creator_import_ref = ""
    content_import_ref = ""
    homepage_import_ref = ""
    if args.import_to_db:
        tag_receipt = dependencies.run_tag_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            dry_run=bool(args.dry_run),
        )
        tag_import_ref = tag_receipt.relative_to(
            dependencies.output_root
        ).as_posix()
        creator_receipt = dependencies.run_creator_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            postgres_dsn=target.user_postgres_dsn,
            media_avatar_base_url=target.media_delivery_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
        )
        creator_import_ref = creator_receipt.relative_to(
            dependencies.output_root
        ).as_posix()
        dependencies.run_content_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            media_image_base_url=target.media_delivery_base_url,
            media_video_base_url=target.media_delivery_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
            delete_policy=DeletePolicy.TOMBSTONE,
            creator_receipt=creator_receipt,
        )
        content_import_ref = (run / "import.json").relative_to(
            dependencies.output_root
        ).as_posix()
        dependencies.run_homepage_importer(
            release=release,
            env=env,
            run=run,
            run_id=run_id,
            mongo_uri=target.mongo_uri,
            media_image_base_url=target.media_delivery_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
        )
        homepage_import_ref = (run / "homepage-import.json").relative_to(
            dependencies.output_root
        ).as_posix()
    if args.import_to_db and not args.dry_run:
        dependencies.write_applied_ref(
            run=run,
            env=env,
            release_id=target_id,
        )
    dependencies.write_release_evidence(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": env,
            "releaseId": target_id,
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
            "tagImportReportRef": tag_import_ref,
            "creatorImportReportRef": creator_import_ref,
            "contentImportReportRef": content_import_ref,
            "homepageImportReportRef": homepage_import_ref,
        },
        "environment_release_result",
    )
    print(f"[ship] rollback env={env} target={target_id} run={run_id}")


def verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    release_id = str(args.release_id).strip()
    release, contract = dependencies.load_release(release_id)
    env = str(args.env).strip()
    target = dependencies.resolve_environment_release_target(env)
    if target.mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        raise SystemExit(
            f"[ship] {env} is projection-only and has no imported homepage API to verify"
        )
    if not target.api_base_url:
        raise SystemExit(f"[ship] {env} topology does not declare an API base URL")
    import_run = dependencies.run_root(
        env,
        release_id,
        str(args.import_run_id).strip(),
    )
    import_result = read_json(import_run / "result.json")
    if (
        import_result.get("environment") != env
        or import_result.get("status") != ReleaseRunStatus.COMPLETED
    ):
        raise SystemExit("[ship] import run is not a completed environment release")
    header = read_json(payload_file(release, "release.json"))
    try:
        release_kind = ReleaseKind(str(header.get("releaseKind") or ""))
    except ValueError as exc:
        raise SystemExit("[ship] releaseKind is invalid") from exc
    run_id = str(args.run_id or f"consumer-api-{dependencies.now_compact()}")
    run = dependencies.create_run(
        env,
        release_id,
        run_id,
        kind=ReleaseRunKind.VERIFY,
    )

    def record_failure(stage: str, error: Exception) -> None:
        dependencies.write_verification_result(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                "runId": run_id,
                "importRunId": str(args.import_run_id).strip(),
                "status": ReleaseRunStatus.FAILED,
                "failedStage": stage,
                "error": str(error),
            },
        )

    try:
        tag_report = dependencies.write_tag_consumer_verification(
            environment=env,
            release_id=release_id,
            release_kind=release_kind,
            run_id=run_id,
            release_contract=contract,
            import_report_path=import_run / "tag-import.json",
            output_path=run / "tag-consumer-verification.json",
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        record_failure("tag_consumer_verification", exc)
        raise SystemExit(
            f"[ship] {env} tag consumer verification failed: {exc}"
        ) from exc

    if release_kind is ReleaseKind.EMPTY_BASELINE:
        if import_result.get("homepageVerificationCasesRef"):
            raise SystemExit(
                "[ship] empty baseline import must not bind positive homepage cases"
            )
        try:
            report = dependencies.write_baseline_api_verification(
                environment=target.environment,
                release_id=release_id,
                run_id=run_id,
                importer_report_path=import_run / "homepage-import.json",
                output_path=run / "baseline-api-verification.json",
                api_base_url=target.api_base_url,
            )
        except BaselineApiVerificationError as exc:
            record_failure("baseline_api_verification", exc)
            raise SystemExit(
                f"[ship] {env} baseline API verification failed: {exc}"
            ) from exc
        dependencies.write_verification_result(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                "runId": run_id,
                "importRunId": str(args.import_run_id).strip(),
                "status": ReleaseRunStatus.COMPLETED,
                "tagConsumerVerificationRef": tag_report.relative_to(
                    dependencies.output_root
                ).as_posix(),
                "baselineApiVerificationRef": report.relative_to(
                    dependencies.output_root
                ).as_posix(),
            },
        )
        print(
            f"[ship] {env} baseline API release={release_id} "
            f"run={run_id} evidence={run}"
        )
        return
    post_report: Path | None = None
    if dependencies.release_has_posts(contract):
        try:
            post_report = dependencies.write_post_api_verification(
                environment=target.environment,
                release_id=release.name,
                run_id=run_id,
                release_root=release,
                importer_report_path=import_run / "import.json",
                creator_importer_report_path=import_run / "creator-import.json",
                output_path=run / "post-api-verification.json",
                api_base_url=target.api_base_url,
                media_delivery_base_url=target.media_delivery_base_url,
            )
        except PostApiVerificationError as exc:
            record_failure("post_api_verification", exc)
            raise SystemExit(
                f"[ship] {env} post API verification failed: {exc}"
            ) from exc
    case_manifest = import_run / "homepage_verification_cases.json"
    if not case_manifest.is_file():
        raise SystemExit(
            f"[ship] homepage verification cases missing from import run: {case_manifest}"
        )
    if (
        import_result.get("homepageVerificationCasesRef")
        != case_manifest.relative_to(dependencies.output_root).as_posix()
    ):
        raise SystemExit(
            "[ship] import run does not bind a completed homepage verification "
            "case manifest"
        )
    try:
        homepage_report = dependencies.write_homepage_api_verification(
            environment=target.environment,
            release_id=release.name,
            run_id=run_id,
            case_manifest_path=case_manifest,
            output_path=run / "homepage-api-verification.json",
            api_base_url=target.api_base_url,
        )
    except HomepageApiVerificationError as exc:
        record_failure("homepage_api_verification", exc)
        raise SystemExit(
            f"[ship] {env} homepage API verification failed: {exc}"
        ) from exc
    readiness_report: Path | None = None
    if post_report is not None:
        try:
            readiness_report = dependencies.write_environment_release_readiness(
                environment=env,
                release_id=release_id,
                import_run_id=str(args.import_run_id).strip(),
                verify_run_id=run_id,
                release_root=release,
                import_report_path=import_run / "import.json",
                creator_import_report_path=import_run / "creator-import.json",
                tag_consumer_verification_path=tag_report,
                homepage_api_verification_path=homepage_report,
                post_api_verification_path=post_report,
                output_root=dependencies.output_root,
                output_path=run / "release-readiness.json",
            )
        except EnvironmentReleaseReadinessError as exc:
            record_failure("environment_release_readiness", exc)
            raise SystemExit(
                f"[ship] {env} environment release readiness failed: {exc}"
            ) from exc
    if readiness_report is not None:
        try:
            dependencies.require_environment_readiness(
                environment=target.environment,
                consumer=True,
                run=run,
                release_id=release_id,
                verify_run_id=run_id,
                manifest_digest=payload_digest(release),
            )
        except SystemExit as exc:
            readiness_error = RuntimeError(str(exc))
            record_failure("environment_readiness", readiness_error)
            raise
    result = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        "runId": run_id,
        "importRunId": str(args.import_run_id).strip(),
        "status": ReleaseRunStatus.COMPLETED,
        "tagConsumerVerificationRef": tag_report.relative_to(
            dependencies.output_root
        ).as_posix(),
        "homepageApiVerificationRef": homepage_report.relative_to(
            dependencies.output_root
        ).as_posix(),
    }
    if post_report is not None:
        result["postApiVerificationRef"] = post_report.relative_to(
            dependencies.output_root
        ).as_posix()
    if readiness_report is not None:
        result["releaseReadinessRef"] = readiness_report.relative_to(
            dependencies.output_root
        ).as_posix()
    dependencies.write_verification_result(run / "result.json", result)
    print(
        f"[ship] {env} consumer API release={release_id} "
        f"run={run_id} evidence={run}"
    )
