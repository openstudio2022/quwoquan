"""Immutable release 的 apply、rollback 与 consumer verification 操作。"""

from __future__ import annotations

import argparse

from content.release.environment._ship_operation_dependencies import (
    ShipOperationDependencies,
)
from content.release.environment.consistency import report_to_text, scan_release_contract
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
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import write_json
from core.paths import release_ref
from core.release_layout import payload_digest, payload_file
from core.io import read_json


def apply_release(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    release_id = str(args.release_id)
    release, contract = dependencies.load_release(release_id)
    header = read_json(payload_file(release, "release.json"))
    lifecycle_evidence = {
        "releaseClass": str(header.get("releaseClass") or ""),
        "productLifecycleState": str(
            header.get("productLifecycleState") or ""
        ),
        "containsUnverifiedAssets": bool(
            header.get("containsUnverifiedAssets")
        ),
        "manifestDigest": payload_digest(release),
    }
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
            readiness_phase = (
                ShipReadinessPhase.RESEARCH
                if lifecycle_evidence["releaseClass"] == "research"
                else ShipReadinessPhase.IMPORT
            )
            dependencies.require_environment_readiness(
                environment=target.environment,
                phase=readiness_phase,
                run=run,
                release_id=release_id,
                manifest_digest=lifecycle_evidence["manifestDigest"],
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
        coverage_receipt_ref = ""
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
                redis_addr=target.redis_addr,
                redis_database=target.redis_database,
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
            coverage_receipt = (
                dependencies.write_environment_coverage_receipt(
                    environment=target.environment,
                    release_id=release_id,
                    run_id=run_id,
                    release_root=release,
                    run_root=run,
                    importer_report=homepage_import_report,
                    api_base_url=target.api_base_url,
                )
            )
            coverage_receipt_ref = coverage_receipt.relative_to(
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
                "homepageVerificationCasesRef": verification_cases_ref,
                "tagImportReportRef": tag_import_ref,
                "creatorImportReportRef": creator_import_ref,
                "contentImportReportRef": content_import_ref,
                "homepageImportReportRef": homepage_import_ref,
                **(
                    {"coverageReceiptRef": coverage_receipt_ref}
                    if coverage_receipt_ref
                    else {}
                ),
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
    header = read_json(payload_file(release, "release.json"))
    lifecycle_evidence = {
        "releaseClass": str(header.get("releaseClass") or ""),
        "productLifecycleState": str(
            header.get("productLifecycleState") or ""
        ),
        "containsUnverifiedAssets": bool(
            header.get("containsUnverifiedAssets")
        ),
        "manifestDigest": payload_digest(release),
    }
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
        readiness_phase = (
            ShipReadinessPhase.RESEARCH
            if lifecycle_evidence["releaseClass"] == "research"
            else ShipReadinessPhase.IMPORT
        )
        dependencies.require_environment_readiness(
            environment=target.environment,
            phase=readiness_phase,
            run=run,
            release_id=target_id,
            manifest_digest=lifecycle_evidence["manifestDigest"],
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
    verification_cases_ref = ""
    tag_import_ref = ""
    creator_import_ref = ""
    content_import_ref = ""
    homepage_import_ref = ""
    coverage_receipt_ref = ""
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
            redis_addr=target.redis_addr,
            redis_database=target.redis_database,
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
        homepage_import_report = dependencies.run_homepage_importer(
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
        coverage_receipt = dependencies.write_environment_coverage_receipt(
            environment=target.environment,
            release_id=target_id,
            run_id=run_id,
            release_root=release,
            run_root=run,
            importer_report=homepage_import_report,
            api_base_url=target.api_base_url,
        )
        coverage_receipt_ref = coverage_receipt.relative_to(
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
            release_id=target_id,
        )
    dependencies.write_release_evidence(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": env,
            "releaseId": target_id,
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
            "homepageVerificationCasesRef": verification_cases_ref,
            "tagImportReportRef": tag_import_ref,
            "creatorImportReportRef": creator_import_ref,
            "contentImportReportRef": content_import_ref,
            "homepageImportReportRef": homepage_import_ref,
            **(
                {"coverageReceiptRef": coverage_receipt_ref}
                if coverage_receipt_ref
                else {}
            ),
        },
        "environment_release_result",
    )
    print(f"[ship] rollback env={env} target={target_id} run={run_id}")


def verify_release_consumers(
    args: argparse.Namespace,
    *,
    dependencies: ShipOperationDependencies,
) -> None:
    from content.release.environment._ship_consumer_verification import (
        verify_release_consumers as verify_consumers,
    )

    verify_consumers(args, dependencies=dependencies)
