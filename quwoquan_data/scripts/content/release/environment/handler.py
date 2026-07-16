"""Release-first 环境执行：canonical 只读，所有运行证据 append-only。

环境证据根：`env/<env>/runs/data-release/<releaseId>/<runId>/`（"data-release" 生命周期类别）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.media_asset_url import is_cas_media_object_key
from core.media_library_sync import sync_media_library
from core.release_layout import payload_file
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from core.paths import (
    OUTPUT_ROOT,
    PUBLISH_ROOT,
    RELEASE_ROOT,
    REPO_ROOT,
    execution_root,
    env_data_release_run_root,
    release_ref,
)
from content.release.environment.consistency import report_to_text, scan_release_contract
from content.release.environment.gamma_homepage_api_verification import (
    GammaHomepageApiVerificationError,
    write_gamma_homepage_api_verification,
)
from content.release.environment.gamma_app_uat_cases import GammaAppUatCaseError, write_gamma_app_uat_case_manifest
from content.release.model import (
    DEPLOYMENT_ENVIRONMENTS,
    FULL_SYNC_MILESTONES,
    DeletePolicy,
    DeploymentEnvironment,
    EvidenceStatus,
    ImportMode,
    ReleaseRunKind,
    ReleaseRunStatus,
)

VALID_ENVS = frozenset(DEPLOYMENT_ENVIRONMENTS)
_IMPORT_REPORT_SCHEMAS = {
    "quwoquan.content_import_report.v1": "import_report",
    "quwoquan_service.homepage_import_report/3": "homepage_import_report",
}
_ENTITY_RELOAD_PATH = "/v1/homepages:reload"
_ENTITY_RELOAD_TIMEOUT_SECONDS = active_runtime_policy().entity_reload_timeout_seconds


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
    if contract.get("schemaVersion") != "quwoquan_data.release_desired_state/1":
        raise SystemExit("[ship] 拒绝 legacy release contract；禁止 v1/v2 dual-read")
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
            "schemaVersion": "quwoquan_data.environment_release_run/1",
            "environment": env,
            "releaseId": release_id,
            "runId": run_id,
            "kind": kind,
            "startedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    return run


def _assert_import_report_contract(
    report: Mapping[str, Any] | Path,
    *,
    source: Path | None = None,
    expected_release_id: str | None = None,
) -> dict[str, Any]:
    """按已登记 schemaVersion 验证 importer 回执，拒绝未知或漂移的文档。"""
    if isinstance(report, Path):
        source = report
        report = read_json(report)
    if not isinstance(report, Mapping):
        raise ValueError(f"import report 必须是对象：{source or '<memory>'}")
    payload = dict(report)
    schema_version = str(payload.get("schemaVersion") or "")
    schema_name = _IMPORT_REPORT_SCHEMAS.get(schema_version)
    if not schema_name:
        raise SystemExit(
            f"[ship] 未登记 Schema import report：{schema_version or '<missing>'} "
            f"({source or '<memory>'})"
        )
    assert_valid(
        payload,
        "release",
        schema_name,
        label=f"import_report:{source or '<memory>'}",
    )
    if expected_release_id is not None and str(payload.get("releaseId") or "") != expected_release_id:
        raise RuntimeError(
            f"import report releaseId 不一致：expected={expected_release_id} "
            f"actual={payload.get('releaseId')}"
        )
    return payload


def _trigger_entity_reload(
    reload_url: str,
    *,
    release_id: str,
    run: Path | None = None,
) -> Path:
    """触发 entity-service 的免停服主页重载，并将结果写入 append-only 环境证据。

    服务不可达不会否定已经完成的数据库导入，但失败绝不能静默：始终落报告并打印
    WARNING。正式 ship 调用传入当前 run；无 run 的直接调用也只会写入
    `.qwq_output/env/alpha/runs/data-release/`，不会污染 frozen canonical 或静态 release。
    """
    endpoint = f"{reload_url.rstrip('/')}{_ENTITY_RELOAD_PATH}"
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            "POST",
            "-o",
            "-",
            "-w",
            "\n%{http_code}",
            "--max-time",
            str(_ENTITY_RELOAD_TIMEOUT_SECONDS),
            endpoint,
        ],
        capture_output=True,
        check=False,
    )
    raw = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    body, _, code = raw.rpartition("\n")
    ok = proc.returncode == 0 and code == str(HTTPStatus.OK.value)
    report_path = (
        run
        if run is not None
        else OUTPUT_ROOT
        / "env"
        / DeploymentEnvironment.ALPHA
        / "runs"
        / "data-release"
        / release_id
        / f"reload-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    ) / "entity-reload.json"
    result = {
        "schemaVersion": "quwoquan_data.entity_reload_report/1",
        "releaseId": release_id,
        "endpoint": endpoint,
        "httpStatus": code or None,
        "ok": ok,
        "response": body[:2000],
        "triggeredAt": datetime.now(timezone.utc).isoformat(),
    }
    write_json(report_path, result)
    if ok:
        print(f"[ship] entity-service reload ok: {endpoint} -> {body[:200]}")
    else:
        print(
            f"[ship] WARNING: entity-service reload failed "
            f"({endpoint}, http={code or 'n/a'}); 服务重启后导入仍生效",
            file=sys.stderr,
        )
    return report_path


def _run_content_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    mongo_uri: str,
    dry_run: bool,
    mode: ImportMode = ImportMode.UPSERT,
    delete_policy: DeletePolicy = DeletePolicy.NONE,
) -> None:
    report_path = run / "import.json"
    cmd = [
        "go",
        "run",
        "./services/content-service/cmd/import",
        "--publish-root",
        str(PUBLISH_ROOT),
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--env",
        env,
        "--mode",
        mode,
        "--delete-policy",
        delete_policy,
        "--report",
        str(report_path),
    ]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, cwd=REPO_ROOT / "quwoquan_service", check=False)
    if result.returncode != 0:
        raise SystemExit(f"[ship] importer failed: exit={result.returncode}")
    _assert_import_report_contract(report_path, expected_release_id=release.name)


def _run_homepage_importer(
    *,
    release: Path,
    env: str,
    run: Path,
    mongo_uri: str,
    media_base_url: str,
    dry_run: bool,
    mode: ImportMode,
) -> dict[str, Any]:
    report_path = run / "homepage-import.json"
    cmd = [
        "go",
        "run",
        "./cmd/homepage-import",
        "--publish-root",
        str(PUBLISH_ROOT),
        "--release-root",
        str(release),
        "--mongo-uri",
        mongo_uri,
        "--media-base-url",
        media_base_url,
        "--env",
        env,
        "--mode",
        mode,
        "--report",
        str(report_path),
    ]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT / "quwoquan_service" / "services" / "entity-service",
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"[ship] homepage importer failed: exit={result.returncode}")
    report = _assert_import_report_contract(
        report_path,
        expected_release_id=release.name,
    )
    desired = read_json(payload_file(release, "desired_state.json"))
    expected = set(desired.get("desiredRefs", {}).get("entities", []))
    imported = set(report.get("entityRefToHomepageId", {}))
    missing = sorted(expected - imported) if not dry_run else []
    projected_mismatch = int(report.get("projected", -1)) != len(expected)
    if report.get("issues") or report.get("skipped") or missing:
        raise SystemExit(
            "[ship] homepage importer closure failed: "
            f"issues={len(report.get('issues', []))} "
            f"skipped={len(report.get('skipped', []))} missing={missing[:5]}"
        )
    if projected_mismatch:
        raise SystemExit(
            "[ship] homepage importer projection mismatch: "
            f"expected={len(expected)} projected={report.get('projected')}"
        )
    return report


def _release_media_object_keys(release: Path) -> list[str]:
    manifest = read_json(payload_file(release, "media_manifest.json"))
    if manifest.get("schemaVersion") != "quwoquan_data.release_media_manifest/1":
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
        PUBLISH_ROOT,
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
            "schemaVersion": "quwoquan_data.applied_release_ref/1",
            "environment": env,
            "releaseId": release_id,
            "releaseRef": release_ref(release_id),
            "evidenceRef": run.relative_to(OUTPUT_ROOT).as_posix(),
        },
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
        publish_root=PUBLISH_ROOT,
        release_root=release,
        phase="preflight",
    )
    print(report_to_text(preflight))
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] release consistency preflight failed")
    full_sync = bool(getattr(args, "full_sync", False))
    if _release_requires_full_sync(release) and not full_sync:
        raise SystemExit(
            "[ship] rollout baseline/canary/m1/m2/m3 release requires --full-sync"
        )
    for env in envs:
        run_id = str(args.run_id or f"apply-{_now_compact()}")
        run = _create_run(env, release_id, run_id, kind=ReleaseRunKind.APPLY)
        write_json(run / "consistency-preflight.json", preflight)
        if args.sync_media_root:
            _sync_media(release=release, destination=str(args.sync_media_root), run=run)
        app_uat_cases_ref = ""
        if args.import_to_db:
            if not args.mongo_uri:
                raise SystemExit("[ship] --import 需要 --mongo-uri")
            _run_content_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=str(args.mongo_uri),
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
                delete_policy=DeletePolicy.TOMBSTONE if full_sync else DeletePolicy.NONE,
            )
            homepage_import_report = _run_homepage_importer(
                release=release,
                env=env,
                run=run,
                mongo_uri=str(args.mongo_uri),
                media_base_url=str(getattr(args, "media_base_url", "") or ""),
                dry_run=bool(args.dry_run),
                mode=ImportMode.SYNC if full_sync else ImportMode.UPSERT,
            )
            expected_entities = contract.get("desiredRefs", {}).get("entities", [])
            if env == DeploymentEnvironment.GAMMA and not args.dry_run and expected_entities:
                try:
                    app_uat_cases = write_gamma_app_uat_case_manifest(
                        release_root=release,
                        run_root=run,
                        run_id=run_id,
                        importer_report=homepage_import_report,
                    )
                except GammaAppUatCaseError as exc:
                    raise SystemExit(f"[ship] Gamma App UAT case manifest failed: {exc}") from exc
                app_uat_cases_ref = app_uat_cases.relative_to(OUTPUT_ROOT).as_posix()
            reload_url = str(getattr(args, "entity_reload_url", "") or "").strip()
            if reload_url and not args.dry_run:
                reload_report = _trigger_entity_reload(
                    reload_url,
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
                "schemaVersion": "quwoquan_data.environment_release_result/1",
                "environment": env,
                "releaseId": release_id,
                "runId": run_id,
                "status": ReleaseRunStatus.DRY_RUN if args.dry_run else ReleaseRunStatus.COMPLETED,
                "appUatCasesRef": app_uat_cases_ref,
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
    if env == DeploymentEnvironment.PROD and not args.dry_run and not args.confirm_prod_apply:
        raise SystemExit("[ship] prod rollback 需要 --confirm-prod-apply")
    preflight = scan_release_contract(
        contract,
        publish_root=PUBLISH_ROOT,
        release_root=release,
        phase="preflight",
    )
    if preflight["status"] != EvidenceStatus.PASSED:
        raise SystemExit("[ship] rollback target release consistency failed")
    run_id = str(args.run_id or f"rollback-{_now_compact()}")
    run = _create_run(env, target_id, run_id, kind=ReleaseRunKind.ROLLBACK)
    write_json(
        run / "rollback_ref.json",
        {
            "schemaVersion": "quwoquan_data.rollback_release_ref/1",
            "rollbackTo": target_id,
            "rollbackFromReleaseId": source_id,
            "releaseRef": release_ref(target_id),
        },
    )
    write_json(run / "consistency-preflight.json", preflight)
    sync_media_root = str(getattr(args, "sync_media_root", "") or "").strip()
    if sync_media_root:
        _sync_media(release=release, destination=sync_media_root, run=run)
    if args.import_to_db:
        if not args.mongo_uri:
            raise SystemExit("[ship] rollback --import 需要 --mongo-uri")
        _run_content_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=str(args.mongo_uri),
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
            delete_policy=DeletePolicy.TOMBSTONE,
        )
        _run_homepage_importer(
            release=release,
            env=env,
            run=run,
            mongo_uri=str(args.mongo_uri),
            media_base_url=str(getattr(args, "media_base_url", "") or ""),
            dry_run=bool(args.dry_run),
            mode=ImportMode.SYNC,
        )
        reload_url = str(getattr(args, "entity_reload_url", "") or "").strip()
        if reload_url and not args.dry_run:
            reload_report = _trigger_entity_reload(
                reload_url,
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
            "schemaVersion": "quwoquan_data.environment_release_result/1",
            "environment": env,
            "releaseId": target_id,
            "runId": run_id,
            "status": ReleaseRunStatus.DRY_RUN if args.dry_run else ReleaseRunStatus.COMPLETED,
        },
    )
    print(f"[ship] rollback env={env} target={target_id} run={run_id}")


def _verify_gamma_homepages(args: argparse.Namespace) -> None:
    release_id = str(args.release_id).strip()
    release, _contract = _load_release(release_id)
    import_run = _run_root(
        DeploymentEnvironment.GAMMA,
        release_id,
        str(args.import_run_id).strip(),
    )
    case_manifest = import_run / "app_uat_cases.json"
    if not case_manifest.is_file():
        raise SystemExit(f"[ship] Gamma App UAT cases missing from import run: {case_manifest}")
    import_result = read_json(import_run / "result.json")
    if import_result.get("status") != ReleaseRunStatus.COMPLETED or import_result.get("appUatCasesRef") != case_manifest.relative_to(OUTPUT_ROOT).as_posix():
        raise SystemExit("[ship] Gamma import run does not prove a completed release-bound App UAT case manifest")
    run_id = str(args.run_id or f"homepage-api-{_now_compact()}")
    run = _create_run(
        DeploymentEnvironment.GAMMA,
        release_id,
        run_id,
        kind=ReleaseRunKind.HOMEPAGE_API_VERIFICATION,
    )
    try:
        report = write_gamma_homepage_api_verification(
            release_id=release.name,
            run_id=run_id,
            case_manifest_path=case_manifest,
            output_path=run / "homepage-api-verification.json",
            api_base_url=str(args.api_base_url).strip(),
            insecure_tls=bool(args.insecure_tls),
            resolve_host=str(args.resolve_host or "").strip(),
        )
    except GammaHomepageApiVerificationError as exc:
        raise SystemExit(f"[ship] Gamma homepage API verification failed: {exc}") from exc
    write_json(
        run / "result.json",
        {
            "schemaVersion": "quwoquan_data.environment_release_result/1",
            "environment": DeploymentEnvironment.GAMMA,
            "releaseId": release_id,
            "runId": run_id,
            "status": ReleaseRunStatus.COMPLETED,
            "homepageApiVerificationRef": report.relative_to(OUTPUT_ROOT).as_posix(),
        },
    )
    print(f"[ship] gamma homepage API release={release_id} run={run_id} evidence={run}")


def handle_ship(args: argparse.Namespace) -> None:
    if args.ship_command == ReleaseRunKind.APPLY:
        _apply_release(args)
    elif args.ship_command == ReleaseRunKind.ROLLBACK:
        _rollback_release(args)
    elif args.ship_command == "verify-homepages":
        _verify_gamma_homepages(args)
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
            "schemaVersion": "quwoquan_data.release_only_ship_report/2",
            "closureType": "release_only",
            "sourceReleaseId": release_id,
            "releaseRef": release_ref(release_id),
            "summary": dict(summary),
            "importRequested": False,
            "importReports": [],
        },
    )
    return output_path


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "ship",
        help="只读 immutable release 并写 append-only 环境执行证据",
    )
    commands = parser.add_subparsers(dest="ship_command", required=True)
    apply = commands.add_parser(ReleaseRunKind.APPLY, help="执行已存在 release；禁止 promote/index/sample/canonical 写入")
    apply.add_argument("--release-id", required=True)
    apply.add_argument("--env", required=True, help="alpha,beta,gamma,prod；生产仅 prod")
    apply.add_argument("--run-id", help="append-only run id（默认 UTC 时间）")
    apply.add_argument("--import", dest="import_to_db", action="store_true")
    apply.add_argument("--mongo-uri")
    apply.add_argument("--sync-media-root")
    apply.add_argument("--media-base-url", default="", help="部署配置中的环境媒体公开基址")
    apply.add_argument("--entity-reload-url", help="导入后触发 entity-service 主页状态重载")
    apply.add_argument(
        "--full-sync",
        action="store_true",
        help="按 release desired state tombstone 缺失对象；baseline/canary/M1/M2/M3 强制使用",
    )
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--confirm-prod-apply", action="store_true")
    apply.set_defaults(handler=handle_ship)

    rollback = commands.add_parser(ReleaseRunKind.ROLLBACK, help="按 immutable release desired state 重放回滚")
    rollback.add_argument("--to-release", required=True)
    rollback.add_argument("--from-release-id", required=True)
    rollback.add_argument("--env", required=True, choices=sorted(VALID_ENVS))
    rollback.add_argument("--run-id")
    rollback.add_argument("--import", dest="import_to_db", action="store_true")
    rollback.add_argument("--mongo-uri")
    rollback.add_argument("--sync-media-root")
    rollback.add_argument("--media-base-url", default="", help="部署配置中的环境媒体公开基址")
    rollback.add_argument("--entity-reload-url", help="回滚导入后触发 entity-service 主页状态重载")
    rollback.add_argument("--dry-run", action="store_true")
    rollback.add_argument("--confirm-prod-apply", action="store_true")
    rollback.set_defaults(handler=handle_ship)

    verify_homepages = commands.add_parser(
        "verify-homepages",
        help="从 Gamma 导入回执派生 App UAT cases，并逐主页验证 detail/introduction API",
    )
    verify_homepages.add_argument("--release-id", required=True)
    verify_homepages.add_argument("--import-run-id", required=True)
    verify_homepages.add_argument("--run-id")
    verify_homepages.add_argument("--api-base-url", required=True)
    verify_homepages.add_argument("--insecure-tls", action="store_true")
    verify_homepages.add_argument(
        "--resolve-host",
        default="",
        help="仅本地环境：连接此 IP，保留 --api-base-url 的主机与 TLS SNI",
    )
    verify_homepages.set_defaults(handler=handle_ship)
