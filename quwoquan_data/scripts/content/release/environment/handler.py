"""Release-first 环境执行：canonical 只读，所有运行证据 append-only。

环境证据根：`env/<env>/runs/data-release/<releaseId>/<runId>/`（"data-release" 生命周期类别）。
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.environment.baseline_api_verification import (
    BaselineApiVerificationError,
    write_baseline_api_verification,
)
from content.release.environment.consistency import (
    report_to_text,
    scan_release_contract,
)
from content.release.environment.homepage_api_verification import (
    HomepageApiVerificationError,
    write_homepage_api_verification,
)
from content.release.environment.homepage_verification_cases import (
    HomepageVerificationCaseError,
    write_homepage_verification_case_manifest,
)
from content.release.environment.importers import (
    run_content_importer as _run_content_importer,
)
from content.release.environment.importers import (
    run_creator_importer as _run_creator_importer,
)
from content.release.environment.importers import (
    run_homepage_importer as _run_homepage_importer,
)
from content.release.environment.importers import (
    run_tag_importer as _run_tag_importer,
)
from content.release.environment.post_api_verification import (
    PostApiVerificationError,
    write_post_api_verification,
)
from content.release.environment.readiness import require_environment_readiness
from content.release.environment.release_runtime import (
    assert_target_action_allowed as _assert_environment_action_allowed,
)
from content.release.environment.release_runtime import (
    load_release,
    release_has_posts,
    release_requires_full_sync,
    sync_media,
)
from content.release.environment.run_evidence import (
    create_run as _create_environment_run,
)
from content.release.environment.run_evidence import (
    write_applied_ref as _write_environment_applied_ref,
)
from content.release.environment.run_evidence import (
    write_release_evidence as _write_release_evidence,
)
from content.release.environment.run_evidence import (
    write_verification_result as _write_verification_result,
)
from content.release.environment.tag_consumer_verification import (
    write_tag_consumer_verification,
)
from content.release.environment.topology import (
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
    resolve_environment_release_target,
)
from content.release.model import (
    DEPLOYMENT_ENVIRONMENTS,
    DeletePolicy,
    DeploymentEnvironment,
    EvidenceStatus,
    ImportMode,
    ReleaseKind,
)
from core.control_types import ReleaseRunKind, ReleaseRunStatus
from core.io import read_json, write_json
from core.paths import (
    OUTPUT_ROOT,
    RELEASE_ROOT,
    env_data_release_run_root,
    execution_root,
    release_ref,
)
from core.release_layout import payload_file

VALID_ENVS = frozenset(DEPLOYMENT_ENVIRONMENTS)


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_tag_consumer_verification(
    *, environment: str, release_id: str, release_kind: ReleaseKind, run_id: str, release_contract: Mapping[str, Any], import_report_path: Path, output_path: Path
) -> Path:
    return write_tag_consumer_verification(
        output_root=OUTPUT_ROOT,
        environment=environment,
        release_id=release_id,
        release_kind=release_kind,
        run_id=run_id,
        release_contract=release_contract,
        import_report_path=import_report_path,
        output_path=output_path,
    )


def _run_root(env: str, release_id: str, run_id: str) -> Path:
    return env_data_release_run_root(env, release_id, run_id, output_root=OUTPUT_ROOT)


def _load_release(release_id: str) -> tuple[Path, dict[str, Any]]:
    return load_release(RELEASE_ROOT, release_id)


def _release_requires_full_sync(release: Path) -> bool:
    return release_requires_full_sync(release)


def _release_has_posts(contract: Mapping[str, Any]) -> bool:
    """Return whether this immutable release owns post consumers to verify."""
    return release_has_posts(contract)


def _create_run(env: str, release_id: str, run_id: str, *, kind: ReleaseRunKind) -> Path:
    return _create_environment_run(
        output_root=OUTPUT_ROOT,
        environment=env,
        release_id=release_id,
        run_id=run_id,
        kind=kind,
        valid_environments=VALID_ENVS,
    )


def _sync_media(*, release: Path, destination: str, run: Path) -> None:
    sync_media(release=release, destination=destination, run=run)


def _write_applied_ref(*, run: Path, env: str, release_id: str) -> None:
    _write_environment_applied_ref(
        output_root=OUTPUT_ROOT,
        run=run,
        environment=env,
        release_id=release_id,
        release_ref=release_ref(release_id),
    )


def _assert_target_action_allowed(
    *,
    target: EnvironmentReleaseTarget,
    import_to_db: bool,
    dry_run: bool,
    action: str,
) -> None:
    _assert_environment_action_allowed(
        target=target,
        import_to_db=import_to_db,
        dry_run=dry_run,
        action=action,
    )


def _apply_release(args: argparse.Namespace) -> None:
    release_id = str(args.release_id)
    release, contract = _load_release(release_id)
    envs = [item.strip() for item in str(args.env).split(",") if item.strip()]
    if not envs:
        raise SystemExit("[ship] apply 需要 --env")
    if DeploymentEnvironment.PROD in envs and args.import_to_db and not args.dry_run and not args.confirm_prod_apply:
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
    if _release_requires_full_sync(release) and not full_sync:
        raise SystemExit("[ship] immutable release requires --full-sync")
    for env in envs:
        target = resolve_environment_release_target(env)
        _assert_target_action_allowed(
            target=target,
            import_to_db=bool(args.import_to_db),
            dry_run=bool(args.dry_run),
            action="apply",
        )
        run_id = str(args.run_id or f"apply-{_now_compact()}")
        run = _create_run(env, release_id, run_id, kind=ReleaseRunKind.APPLY)
        if args.import_to_db and not args.dry_run:
            require_environment_readiness(
                environment=target.environment,
                consumer=False,
                run=run,
            )
        write_json(run / "consistency-preflight.json", preflight)
        if target.media_sync_root is not None and args.import_to_db and not args.dry_run:
            _sync_media(release=release, destination=str(target.media_sync_root), run=run)
        verification_cases_ref = ""
        tag_import_ref = ""
        creator_import_ref = ""
        content_import_ref = ""
        homepage_import_ref = ""
        if args.import_to_db:
            tag_receipt = _run_tag_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                dry_run=bool(args.dry_run),
            )
            tag_import_ref = tag_receipt.relative_to(OUTPUT_ROOT).as_posix()
            creator_receipt = _run_creator_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                postgres_dsn=target.user_postgres_dsn,
                media_avatar_base_url=target.media_avatar_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
            creator_import_ref = creator_receipt.relative_to(OUTPUT_ROOT).as_posix()
            _run_content_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                media_image_base_url=target.media_image_base_url,
                media_video_base_url=target.media_video_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
                delete_policy=DeletePolicy.TOMBSTONE if full_sync else DeletePolicy.NONE,
                creator_receipt=creator_receipt,
            )
            content_import_ref = (run / "import.json").relative_to(OUTPUT_ROOT).as_posix()
            homepage_import_report = _run_homepage_importer(
                release=release,
                env=env,
                run=run,
                run_id=run_id,
                mongo_uri=target.mongo_uri,
                media_image_base_url=target.media_image_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
            homepage_import_ref = (run / "homepage-import.json").relative_to(OUTPUT_ROOT).as_posix()
            expected_entities = contract.get("desiredRefs", {}).get("entities", [])
            if not args.dry_run and expected_entities:
                try:
                    verification_cases = write_homepage_verification_case_manifest(
                        environment=target.environment,
                        release_root=release,
                        run_root=run,
                        run_id=run_id,
                        importer_report=homepage_import_report,
                    )
                except HomepageVerificationCaseError as exc:
                    raise SystemExit(f"[ship] homepage verification case manifest failed: {exc}") from exc
                verification_cases_ref = verification_cases.relative_to(OUTPUT_ROOT).as_posix()
        if args.import_to_db and not args.dry_run:
            _write_applied_ref(run=run, env=env, release_id=release_id)
        _write_release_evidence(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                "runId": run_id,
                "status": (ReleaseRunStatus.DRY_RUN if args.dry_run else (ReleaseRunStatus.COMPLETED if args.import_to_db else ReleaseRunStatus.PREPARED)),
                "homepageVerificationCasesRef": verification_cases_ref,
                "tagImportReportRef": tag_import_ref,
                "creatorImportReportRef": creator_import_ref,
                "contentImportReportRef": content_import_ref,
                "homepageImportReportRef": homepage_import_ref,
            },
            "environment_release_result",
        )
        print(f"[ship] {env} release={release_id} run={run_id} evidence={run}")


def _rollback_release(args: argparse.Namespace) -> None:
    target_id = str(args.to_release)
    source_id = str(args.from_release_id).strip()
    if not source_id or source_id == target_id:
        raise SystemExit("[ship] rollback requires a distinct --from-release-id")
    release, contract = _load_release(target_id)
    env = str(args.env)
    target = resolve_environment_release_target(env)
    if env == DeploymentEnvironment.PROD and args.import_to_db and not args.dry_run and not args.confirm_prod_apply:
        raise SystemExit("[ship] prod rollback 需要 --confirm-prod-apply")
    preflight = scan_release_contract(
        contract,
        release_root=release,
        phase="preflight",
    )
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] rollback target release consistency failed")
    _assert_target_action_allowed(
        target=target,
        import_to_db=bool(args.import_to_db),
        dry_run=bool(args.dry_run),
        action="rollback",
    )
    run_id = str(args.run_id or f"rollback-{_now_compact()}")
    run = _create_run(env, target_id, run_id, kind=ReleaseRunKind.ROLLBACK)
    if args.import_to_db and not args.dry_run:
        require_environment_readiness(
            environment=target.environment,
            consumer=False,
            run=run,
        )
    _write_release_evidence(
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
    if target.media_sync_root is not None and args.import_to_db and not args.dry_run:
        _sync_media(release=release, destination=str(target.media_sync_root), run=run)
    tag_import_ref = ""
    creator_import_ref = ""
    content_import_ref = ""
    homepage_import_ref = ""
    if args.import_to_db:
        tag_receipt = _run_tag_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            dry_run=bool(args.dry_run),
        )
        tag_import_ref = tag_receipt.relative_to(OUTPUT_ROOT).as_posix()
        creator_receipt = _run_creator_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            postgres_dsn=target.user_postgres_dsn,
            media_avatar_base_url=target.media_avatar_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
        )
        creator_import_ref = creator_receipt.relative_to(OUTPUT_ROOT).as_posix()
        _run_content_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            media_image_base_url=target.media_image_base_url,
            media_video_base_url=target.media_video_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
            delete_policy=DeletePolicy.TOMBSTONE,
            creator_receipt=creator_receipt,
        )
        content_import_ref = (run / "import.json").relative_to(OUTPUT_ROOT).as_posix()
        _run_homepage_importer(
            release=release,
            env=env,
            run=run,
            run_id=run_id,
            mongo_uri=target.mongo_uri,
            media_image_base_url=target.media_image_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
        )
        homepage_import_ref = (run / "homepage-import.json").relative_to(OUTPUT_ROOT).as_posix()
    if args.import_to_db and not args.dry_run:
        _write_applied_ref(run=run, env=env, release_id=target_id)
    _write_release_evidence(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": env,
            "releaseId": target_id,
            "runId": run_id,
            "status": (ReleaseRunStatus.DRY_RUN if args.dry_run else (ReleaseRunStatus.COMPLETED if args.import_to_db else ReleaseRunStatus.PREPARED)),
            "tagImportReportRef": tag_import_ref,
            "creatorImportReportRef": creator_import_ref,
            "contentImportReportRef": content_import_ref,
            "homepageImportReportRef": homepage_import_ref,
        },
        "environment_release_result",
    )
    print(f"[ship] rollback env={env} target={target_id} run={run_id}")


def _verify_release_consumers(args: argparse.Namespace) -> None:
    release_id = str(args.release_id).strip()
    release, contract = _load_release(release_id)
    env = str(args.env).strip()
    target = resolve_environment_release_target(env)
    if target.mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        raise SystemExit(f"[ship] {env} is projection-only and has no imported homepage API to verify")
    if not target.api_base_url:
        raise SystemExit(f"[ship] {env} topology does not declare an API base URL")
    import_run = _run_root(
        env,
        release_id,
        str(args.import_run_id).strip(),
    )
    import_result = read_json(import_run / "result.json")
    if import_result.get("environment") != env or import_result.get("status") != ReleaseRunStatus.COMPLETED:
        raise SystemExit("[ship] import run is not a completed environment release")
    header = read_json(payload_file(release, "release.json"))
    try:
        release_kind = ReleaseKind(str(header.get("releaseKind") or ""))
    except ValueError as exc:
        raise SystemExit("[ship] releaseKind is invalid") from exc
    run_id = str(args.run_id or f"consumer-api-{_now_compact()}")
    run = _create_run(
        env,
        release_id,
        run_id,
        kind=ReleaseRunKind.VERIFY,
    )

    def record_failure(stage: str, error: Exception) -> None:
        _write_verification_result(
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
        tag_report = _write_tag_consumer_verification(
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
        raise SystemExit(f"[ship] {env} tag consumer verification failed: {exc}") from exc

    try:
        require_environment_readiness(
            environment=target.environment,
            consumer=True,
            run=run,
        )
    except SystemExit as exc:
        readiness_error = RuntimeError(str(exc))
        record_failure("environment_readiness", readiness_error)
        raise
    if release_kind is ReleaseKind.EMPTY_BASELINE:
        if import_result.get("homepageVerificationCasesRef"):
            raise SystemExit("[ship] empty baseline import must not bind positive homepage cases")
        try:
            report = write_baseline_api_verification(
                environment=target.environment,
                release_id=release_id,
                run_id=run_id,
                importer_report_path=import_run / "homepage-import.json",
                output_path=run / "baseline-api-verification.json",
                api_base_url=target.api_base_url,
                insecure_tls=target.api_insecure_tls,
                resolve_host=target.api_resolve_host,
            )
        except BaselineApiVerificationError as exc:
            record_failure("baseline_api_verification", exc)
            raise SystemExit(f"[ship] {env} baseline API verification failed: {exc}") from exc
        _write_verification_result(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                "runId": run_id,
                "importRunId": str(args.import_run_id).strip(),
                "status": ReleaseRunStatus.COMPLETED,
                "tagConsumerVerificationRef": tag_report.relative_to(OUTPUT_ROOT).as_posix(),
                "baselineApiVerificationRef": report.relative_to(OUTPUT_ROOT).as_posix(),
            },
        )
        print(f"[ship] {env} baseline API release={release_id} run={run_id} evidence={run}")
        return
    post_report: Path | None = None
    if _release_has_posts(contract):
        try:
            post_report = write_post_api_verification(
                environment=target.environment,
                release_id=release.name,
                run_id=run_id,
                release_root=release,
                importer_report_path=import_run / "import.json",
                creator_importer_report_path=import_run / "creator-import.json",
                output_path=run / "post-api-verification.json",
                api_base_url=target.api_base_url,
                insecure_tls=target.api_insecure_tls,
                resolve_host=target.api_resolve_host,
            )
        except PostApiVerificationError as exc:
            record_failure("post_api_verification", exc)
            raise SystemExit(f"[ship] {env} post API verification failed: {exc}") from exc
    case_manifest = import_run / "homepage_verification_cases.json"
    if not case_manifest.is_file():
        raise SystemExit(f"[ship] homepage verification cases missing from import run: {case_manifest}")
    if import_result.get("homepageVerificationCasesRef") != case_manifest.relative_to(OUTPUT_ROOT).as_posix():
        raise SystemExit("[ship] import run does not bind a completed homepage verification case manifest")
    try:
        homepage_report = write_homepage_api_verification(
            environment=target.environment,
            release_id=release.name,
            run_id=run_id,
            case_manifest_path=case_manifest,
            output_path=run / "homepage-api-verification.json",
            api_base_url=target.api_base_url,
            insecure_tls=target.api_insecure_tls,
            resolve_host=target.api_resolve_host,
        )
    except HomepageApiVerificationError as exc:
        record_failure("homepage_api_verification", exc)
        raise SystemExit(f"[ship] {env} homepage API verification failed: {exc}") from exc
    result = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": env,
        "releaseId": release_id,
        "runId": run_id,
        "importRunId": str(args.import_run_id).strip(),
        "status": ReleaseRunStatus.COMPLETED,
        "tagConsumerVerificationRef": tag_report.relative_to(OUTPUT_ROOT).as_posix(),
        "homepageApiVerificationRef": homepage_report.relative_to(OUTPUT_ROOT).as_posix(),
    }
    if post_report is not None:
        result["postApiVerificationRef"] = post_report.relative_to(OUTPUT_ROOT).as_posix()
    _write_verification_result(run / "result.json", result)
    print(f"[ship] {env} consumer API release={release_id} run={run_id} evidence={run}")


def handle_ship(args: argparse.Namespace) -> None:
    if args.ship_command == ReleaseRunKind.APPLY:
        _apply_release(args)
    elif args.ship_command == ReleaseRunKind.ROLLBACK:
        _rollback_release(args)
    elif args.ship_command == ReleaseRunKind.VERIFY:
        _verify_release_consumers(args)
    else:
        raise SystemExit("[ship] subcommand required")


def write_release_only_ship_report(
    *,
    execution_id: str | None = None,
    output_path: Path | None = None,
    release_id: str,
    summary: Mapping[str, Any],
) -> Path:
    """保留给 task release 编排器的纯输出报告；不写 canonical。"""
    if output_path is None:
        if not execution_id or not execution_id:
            raise ValueError("execution_id/execution_id or output_path required")
        output_path = execution_root(execution_id) / "_shared" / "ship_report.json"
    write_json(
        output_path,
        {
            "schema": "quwoquan_data.release_only_ship_report",
            "closureType": "release_only",
            "sourceReleaseId": release_id,
            "releaseRef": release_ref(release_id),
            "summary": dict(summary),
            "importRequested": False,
            "importReports": [],
        },
    )
    return output_path
