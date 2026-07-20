"""Release-first 环境执行：canonical 只读，所有运行证据 append-only。

环境证据根：`env/<env>/runs/data-release/<releaseId>/<runId>/`（"data-release" 生命周期类别）。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.media_asset_url import is_cas_media_object_key
from core.media_library_sync import sync_media_library
from core.release_layout import payload_file
from core.release_layout import payload_root
from core.paths import (
    OUTPUT_ROOT,
    RELEASE_ROOT,
    execution_root,
    env_data_release_run_root,
    release_ref,
)
from content.release.environment.consistency import report_to_text, scan_release_contract
from content.release.environment.homepage_api_verification import (
    HomepageApiVerificationError,
    write_homepage_api_verification,
)
from content.release.environment.baseline_api_verification import (
    BaselineApiVerificationError,
    write_baseline_api_verification,
)
from content.release.environment.homepage_verification_cases import (
    HomepageVerificationCaseError,
    write_homepage_verification_case_manifest,
)
from content.release.environment.importers import (
    run_content_importer as _run_content_importer,
    run_homepage_importer as _run_homepage_importer,
)
from content.release.environment.reload import (
    authorization_header_for_target as _authorization_header_for_target,
    trigger_entity_reload as _trigger_entity_reload,
)
from content.release.environment.readiness import require_environment_readiness
from content.release.environment.topology import (
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
    resolve_environment_release_target,
)
from content.release.model import (
    DEPLOYMENT_ENVIRONMENTS,
    FULL_SYNC_MILESTONES,
    DeletePolicy,
    DeploymentEnvironment,
    EvidenceStatus,
    ImportMode,
    ReleaseKind,
)
from core.control_types import ReleaseRunKind, ReleaseRunStatus
VALID_ENVS = frozenset(DEPLOYMENT_ENVIRONMENTS)


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_root(env: str, release_id: str, run_id: str) -> Path:
    return env_data_release_run_root(env, release_id, run_id, output_root=OUTPUT_ROOT)


def _load_release(release_id: str) -> tuple[Path, dict[str, Any]]:
    release = RELEASE_ROOT / release_id
    desired = payload_file(release, "desired_state.json")
    if not desired.is_file():
        raise SystemExit(f"[ship] immutable release desired_state 不存在：{desired}")
    contract = read_json(desired)
    if contract.get("schema") != "quwoquan_data.release_desired_state":
        raise SystemExit("[ship] 拒绝非权威 release contract；只允许当前单一合同")
    return release, contract


def _release_requires_full_sync(release: Path) -> bool:
    header = read_json(payload_file(release, "release.json"))
    return str(header.get("rolloutMilestone") or "") in FULL_SYNC_MILESTONES


def _create_run(
    env: str,
    release_id: str,
    run_id: str,
    *,
    kind: ReleaseRunKind,
) -> Path:
    if env not in VALID_ENVS:
        raise SystemExit(f"[ship] environment 非法：{env}")
    run = _run_root(env, release_id, run_id)
    if run.exists():
        raise SystemExit(f"[ship] append-only run 已存在：{run}")
    write_json(
        run / "run.json",
        {
            "schema": "quwoquan_data.environment_release_run",
            "environment": env,
            "releaseId": release_id,
            "runId": run_id,
            "kind": kind,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    return run


def _release_media_object_keys(release: Path) -> list[str]:
    manifest = read_json(payload_file(release, "media_manifest.json"))
    if manifest.get("schema") != "quwoquan_data.release_media_manifest":
        raise SystemExit("[ship] release media manifest schema 无效")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise SystemExit("[ship] release media manifest assets 必须为数组")
    keys: set[str] = set()
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping):
            raise SystemExit(f"[ship] release media manifest assets[{index}] 必须为对象")
        key = str(row.get("objectKey") or "")
        if not is_cas_media_object_key(key):
            raise SystemExit(f"[ship] release media manifest 含非法 CAS key: {key}")
        keys.add(key)
    return sorted(keys)


def _sync_media(*, release: Path, destination: str, run: Path) -> None:
    report = sync_media_library(
        payload_root(release),
        Path(destination),
        object_keys=_release_media_object_keys(release),
    )
    write_json(run / "media-sync.json", report)
    if report["failed"] or report["issues"]:
        raise SystemExit(f"[ship] media sync failed: {report['issues'][:5]}")


def _write_applied_ref(*, run: Path, env: str, release_id: str) -> None:
    write_json(
        run / "applied_ref.json",
        {
            "schema": "quwoquan_data.applied_release_ref",
            "environment": env,
            "releaseId": release_id,
            "releaseRef": release_ref(release_id),
            "evidenceRef": run.relative_to(OUTPUT_ROOT).as_posix(),
        },
    )


def _assert_target_action_allowed(
    *,
    target: EnvironmentReleaseTarget,
    import_to_db: bool,
    dry_run: bool,
    action: str,
) -> None:
    if not import_to_db:
        return
    if target.mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        raise SystemExit(
            f"[ship] {target.environment.value} is projection-only; "
            f"database {action} is not a valid environment action"
        )
    if target.missing_requirements and not dry_run:
        raise SystemExit(
            f"[ship] environment release target is not ready for {action}; "
            "missing secret inputs: " + ", ".join(target.missing_requirements)
        )


def _apply_release(args: argparse.Namespace) -> None:
    release_id = str(args.release_id)
    release, contract = _load_release(release_id)
    envs = [item.strip() for item in str(args.env).split(",") if item.strip()]
    if not envs:
        raise SystemExit("[ship] apply 需要 --env")
    if DeploymentEnvironment.PROD in envs and not args.dry_run and not args.confirm_prod_apply:
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
        raise SystemExit(
            "[ship] rollout baseline/canary/m1/m2/m3 release requires --full-sync"
        )
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
        if target.media_sync_root is not None and not args.dry_run:
            _sync_media(release=release, destination=str(target.media_sync_root), run=run)
        verification_cases_ref = ""
        if args.import_to_db:
            _run_content_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                media_base_url=target.media_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
                delete_policy=DeletePolicy.TOMBSTONE if full_sync else DeletePolicy.NONE,
            )
            homepage_import_report = _run_homepage_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=target.mongo_uri,
                media_base_url=target.media_base_url,
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
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
            reload_url = target.entity_reload_url
            if reload_url and not args.dry_run:
                reload_report = _trigger_entity_reload(
                    reload_url,
                    authorization_header=_authorization_header_for_target(target),
                    release_id=release_id,
                    run=run,
                )
                if not read_json(reload_report).get("ok"):
                    raise SystemExit("[ship] entity-service reload failed")
        if args.import_to_db and not args.dry_run:
            _write_applied_ref(run=run, env=env, release_id=release_id)
        write_json(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                "runId": run_id,
                "status": ReleaseRunStatus.DRY_RUN if args.dry_run else ReleaseRunStatus.COMPLETED,
                "homepageVerificationCasesRef": verification_cases_ref,
            },
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
    if env == DeploymentEnvironment.PROD and not args.dry_run and not args.confirm_prod_apply:
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
    write_json(
        run / "rollback_ref.json",
        {
            "schema": "quwoquan_data.rollback_release_ref",
            "rollbackTo": target_id,
            "rollbackFromReleaseId": source_id,
            "releaseRef": release_ref(target_id),
        },
    )
    write_json(run / "consistency-preflight.json", preflight)
    if target.media_sync_root is not None and not args.dry_run:
        _sync_media(release=release, destination=str(target.media_sync_root), run=run)
    if args.import_to_db:
        _run_content_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            media_base_url=target.media_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
            delete_policy=DeletePolicy.TOMBSTONE,
        )
        _run_homepage_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=target.mongo_uri,
            media_base_url=target.media_base_url,
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
        )
        reload_url = target.entity_reload_url
        if reload_url and not args.dry_run:
            reload_report = _trigger_entity_reload(
                reload_url,
                authorization_header=_authorization_header_for_target(target),
                release_id=target_id,
                run=run,
            )
            if not read_json(reload_report).get("ok"):
                raise SystemExit("[ship] entity-service reload failed")
    if args.import_to_db and not args.dry_run:
        _write_applied_ref(run=run, env=env, release_id=target_id)
    write_json(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": env,
            "releaseId": target_id,
            "runId": run_id,
            "status": ReleaseRunStatus.DRY_RUN if args.dry_run else ReleaseRunStatus.COMPLETED,
        },
    )
    print(f"[ship] rollback env={env} target={target_id} run={run_id}")


def _verify_homepages(args: argparse.Namespace) -> None:
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
    run_id = str(args.run_id or f"homepage-api-{_now_compact()}")
    run = _create_run(
        env,
        release_id,
        run_id,
        kind=ReleaseRunKind.VERIFY,
    )
    require_environment_readiness(
        environment=target.environment,
        consumer=True,
        run=run,
    )
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
            raise SystemExit(f"[ship] {env} baseline API verification failed: {exc}") from exc
        write_json(
            run / "result.json",
            {
                "schema": "quwoquan_data.environment_release_result",
                "environment": env,
                "releaseId": release_id,
                "runId": run_id,
                "status": ReleaseRunStatus.COMPLETED,
                "baselineApiVerificationRef": report.relative_to(OUTPUT_ROOT).as_posix(),
            },
        )
        print(f"[ship] {env} baseline API release={release_id} run={run_id} evidence={run}")
        return
    case_manifest = import_run / "homepage_verification_cases.json"
    if not case_manifest.is_file():
        raise SystemExit(f"[ship] homepage verification cases missing from import run: {case_manifest}")
    if (
        import_result.get("homepageVerificationCasesRef")
        != case_manifest.relative_to(OUTPUT_ROOT).as_posix()
    ):
        raise SystemExit("[ship] import run does not bind a completed homepage verification case manifest")
    try:
        report = write_homepage_api_verification(
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
        raise SystemExit(f"[ship] {env} homepage API verification failed: {exc}") from exc
    write_json(
        run / "result.json",
        {
            "schema": "quwoquan_data.environment_release_result",
            "environment": env,
            "releaseId": release_id,
            "runId": run_id,
            "status": ReleaseRunStatus.COMPLETED,
            "homepageApiVerificationRef": report.relative_to(OUTPUT_ROOT).as_posix(),
        },
    )
    print(f"[ship] {env} homepage API release={release_id} run={run_id} evidence={run}")


def handle_ship(args: argparse.Namespace) -> None:
    if args.ship_command == ReleaseRunKind.APPLY:
        _apply_release(args)
    elif args.ship_command == ReleaseRunKind.ROLLBACK:
        _rollback_release(args)
    elif args.ship_command == ReleaseRunKind.VERIFY:
        _verify_homepages(args)
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
