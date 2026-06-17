"""qwq-data ship — 一键发布编排。

流程：
  (可选) promote task/release → publish 主线
  → 重建 publish lookup 索引
  → 按 content_sampling_manifest 对每个目标环境确定性采样，写 publish/sample_bundles/{env}.json
  → 更新 publish_meta.lastShip
  → 打印服务侧 importer 灌库命令（或 --import 直接灌入运行库）

sample bundle 是端云桥契约：服务侧 content/entity importer 消费它把 posts/entities 灌进运行库。

用法：
  qwq-data ship --task T --batch B --copy-entities            # 从 task 发布 + 全环境采样
  qwq-data ship --release-id R --env gamma,beta               # 从 release 发布 + 指定环境
  qwq-data ship --skip-promote --env alpha                    # 仅对现有 publish 主线重采样
  qwq-data ship --task T --batch B --import --mongo-uri mongodb://localhost:27017
"""
from __future__ import annotations


import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from _common.io import read_json, write_json
from _common.media_asset_url import materialize_release_media
from _common.paths import PUBLISH_ROOT, batch_shared_dir, now_iso, publish_meta_path, release_manifest
from ship.sampler import (
    build_sample_bundle,
    load_publish_records,
    load_sampling_manifest,
    write_sample_bundle,
)
from ship.consistency import report_to_text, scan_release_contract, write_consistency_report
from ship.release_contract import (
    DEFAULT_DELETE_POLICY,
    DEFAULT_MODE,
    DEFAULT_SOURCE_OWNER,
    build_release_contract,
    normalize_release_id,
    write_release_contract,
)


def _promote(args: argparse.Namespace) -> int:
    from publish_ops.promote_to_publish import (
        promote_release,
        promote_task_batch,
        promote_task_entities,
    )

    if args.release_id:
        count, skipped = promote_release(args.release_id, dry_run=False)
    else:
        count, skipped = promote_task_batch(args.task, args.batch, dry_run=False)
        if args.copy_entities:
            promote_task_entities(args.task, dry_run=False)
    print(f"[ship] promoted posts={count} skipped={skipped}")
    return count


def _rebuild_index() -> None:
    from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes

    counts = build_publish_lookup_indexes()
    print(f"[ship] indexes: entities={counts['entities']} posts={counts['posts']}")


def _resolve_envs(args_env: str | None, manifest: dict) -> list[str]:
    envs = list((manifest.get("environments") or {}).keys())
    if args_env:
        requested = [e.strip() for e in args_env.split(",") if e.strip()]
        unknown = [e for e in requested if e not in envs]
        if unknown:
            raise SystemExit(f"[ship] unknown env(s): {unknown}; known={envs}")
        return requested
    return envs


def _run_importer(
    mongo_uri: str,
    bundles: list[Path],
    *,
    release_id: str,
    mode: str,
    delete_policy: str,
    source_owner: str,
    dry_run: bool,
) -> list[Path]:
    """调用服务侧 content/entity importer 把 sample bundle 灌进运行库。"""
    service_root = PUBLISH_ROOT.parent.parent / "quwoquan_service"
    reports: list[Path] = []
    for bundle in bundles:
        env = bundle.stem
        report_path = PUBLISH_ROOT / "env_releases" / release_id / f"import-{env}.json"
        cmd = [
            "go", "run", "./services/content-service/cmd/import",
            "--publish-root", str(PUBLISH_ROOT),
            "--sample-bundle", str(bundle),
            "--mongo-uri", mongo_uri,
            "--env", env,
            "--release-id", release_id,
            "--mode", mode,
            "--delete-policy", delete_policy,
            "--source-owner", source_owner,
            "--report", str(report_path),
        ]
        if dry_run:
            cmd.append("--dry-run")
        print(f"[ship] importing {env}: {' '.join(cmd)}")
        subprocess.run(cmd, cwd=str(service_root), check=True)
        reports.append(report_path)
    return reports


def _source_batch_for_ship(args: argparse.Namespace) -> tuple[str, str] | None:
    if args.task and args.batch:
        return str(args.task), str(args.batch)
    release_id = str(getattr(args, "release_id", "") or "").strip()
    if not release_id:
        return None
    manifest_path = release_manifest(release_id)
    if not manifest_path.is_file():
        return None
    manifest = read_json(manifest_path)
    task_id = str(manifest.get("sourceTaskId") or "").strip()
    batch_id = str(manifest.get("sourceBatchId") or "").strip()
    if task_id and batch_id:
        return task_id, batch_id
    return None


def _write_batch_ship_report(
    args: argparse.Namespace,
    *,
    data_release_id: str,
    envs: list[str],
    summary: list[dict],
    import_reports: list[Path],
) -> None:
    source = _source_batch_for_ship(args)
    if source is None:
        return
    task_id, batch_id = source
    shared = batch_shared_dir(task_id, batch_id)
    payload = {
        "schemaVersion": "quwoquan_data.ship_report/1",
        "taskId": task_id,
        "batchId": batch_id,
        "dataReleaseId": data_release_id,
        "sourceReleaseId": str(getattr(args, "release_id", "") or ""),
        "envs": envs,
        "importRequested": bool(getattr(args, "import_to_db", False)),
        "dryRun": bool(getattr(args, "dry_run", False)),
        "summary": summary,
        "importReports": [str(path) for path in import_reports],
        "writtenAt": now_iso(),
    }
    write_json(shared / "ship_report.json", payload)
    for report_path in import_reports:
        if not report_path.is_file():
            continue
        env = report_path.stem.replace("import-", "", 1)
        report = read_json(report_path)
        report["sourceReportPath"] = str(report_path)
        write_json(shared / f"{env}_import_report.json", report)


def write_release_only_ship_report(
    *,
    task_id: str,
    batch_id: str,
    release_id: str,
    summary: dict,
) -> Path:
    """Record release-only closure without claiming an environment import.

    Managed trial runs intentionally stop at an isolated release package.  The
    scale gate still needs durable evidence that release assembly completed and
    that no importer was requested, otherwise each review has to pass the
    release id manually.
    """
    shared = batch_shared_dir(task_id, batch_id)
    payload = {
        "schemaVersion": "quwoquan_data.ship_report/1",
        "closureType": "release_only",
        "taskId": task_id,
        "batchId": batch_id,
        "dataReleaseId": release_id,
        "sourceReleaseId": release_id,
        "envs": [],
        "importRequested": False,
        "dryRun": False,
        "summary": [dict(summary)],
        "importReports": [],
        "writtenAt": now_iso(),
    }
    path = shared / "ship_report.json"
    write_json(path, payload)
    return path


def handle_ship(args: argparse.Namespace) -> None:
    PUBLISH_ROOT.mkdir(parents=True, exist_ok=True)

    if not args.skip_promote:
        if not (args.release_id or (args.task and args.batch)):
            print("[ship] ERROR: 需要 --release-id 或 --task/--batch（或 --skip-promote 仅重采样）", file=sys.stderr)
            raise SystemExit(2)
        promoted = _promote(args)
        if promoted == 0:
            print("[ship] nothing promoted; aborting", file=sys.stderr)
            raise SystemExit(1)

    if not args.skip_index:
        _rebuild_index()

    manifest = load_sampling_manifest()
    envs = _resolve_envs(args.env, manifest)
    posts, entities = load_publish_records()
    mode = getattr(args, "mode", DEFAULT_MODE)
    delete_policy = getattr(args, "delete_policy", DEFAULT_DELETE_POLICY)
    source_owner = getattr(args, "source_owner", DEFAULT_SOURCE_OWNER)
    approved_by = getattr(args, "approved_by", None)
    release_id = normalize_release_id(getattr(args, "data_release_id", None), env="-".join(envs))

    bundles: list[Path] = []
    summary: list[dict] = []
    for env in envs:
        bundle = build_sample_bundle(env, manifest, posts, entities)
        path = write_sample_bundle(bundle)
        media_manifest = materialize_release_media(
            env=env,
            release_id=release_id,
            post_refs=list(bundle.get("posts") or []),
            entity_refs=list(bundle.get("entities") or []),
            publish_root=PUBLISH_ROOT,
            source_owner=source_owner,
            image_cdn_base_url=os.environ.get("QWQ_MEDIA_IMAGE_CDN_BASE_URL", ""),
            video_cdn_base_url=os.environ.get("QWQ_MEDIA_VIDEO_CDN_BASE_URL", ""),
        )
        contract = build_release_contract(
            env=env,
            bundle=bundle,
            posts=posts,
            entities=entities,
            release_id=release_id,
            mode=mode,
            delete_policy=delete_policy,
            source_owner=source_owner,
            approved_by=approved_by,
            media_manifest=media_manifest,
        )
        release_path = write_release_contract(contract, publish_root=PUBLISH_ROOT)
        report = scan_release_contract(contract, publish_root=PUBLISH_ROOT, phase="preflight")
        report_path = release_path.parent / f"consistency-preflight-{env}.json"
        write_consistency_report(report, report_path)
        print(report_to_text(report))
        if report["status"] != "passed":
            raise SystemExit(f"[ship] consistency preflight failed for {env}: {report_path}")
        bundles.append(path)
        summary.append({
            "env": env,
            "releaseId": release_id,
            "posts": bundle["counts"]["posts"],
            "entities": bundle["counts"]["entities"],
            "releaseContract": str(release_path),
            "consistencyReport": str(report_path),
        })
        print(f"[ship] sampled {env}: posts={bundle['counts']['posts']} entities={bundle['counts']['entities']} -> {path}")
        print(f"[ship] release contract {env}: {release_path}")

    meta = read_json(publish_meta_path()) if publish_meta_path().exists() else {"schemaVersion": "quwoquan.publish.meta"}
    meta["lastShip"] = now_iso()
    meta["lastDataReleaseId"] = release_id
    meta["shipSummary"] = summary
    write_json(publish_meta_path(), meta)

    import_reports: list[Path] = []
    if args.import_to_db:
        if not args.mongo_uri:
            print("[ship] ERROR: --import 需要 --mongo-uri", file=sys.stderr)
            raise SystemExit(2)
        if "prod" in envs and not bool(getattr(args, "dry_run", False)) and not bool(getattr(args, "confirm_prod_apply", False)):
            print("[ship] ERROR: prod apply 需要 --confirm-prod-apply；请先执行 --dry-run 并归档一致性报告", file=sys.stderr)
            raise SystemExit(2)
        import_reports = _run_importer(
            args.mongo_uri,
            bundles,
            release_id=release_id,
            mode=mode,
            delete_policy=delete_policy,
            source_owner=source_owner,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
    else:
        print("[ship] 灌库（按需）：")
        print("       go run ./services/content-service/cmd/import \\")
        print(f"         --publish-root {PUBLISH_ROOT} --sample-bundle <bundle> --mongo-uri <uri> --env <env> \\")
        print(f"         --release-id {release_id} --mode {mode} --delete-policy {delete_policy}")
    _write_batch_ship_report(
        args,
        data_release_id=release_id,
        envs=envs,
        summary=summary,
        import_reports=import_reports,
    )


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("ship", help="一键发布：promote→索引→按环境采样→(可选)灌库")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--release-id", help="release/ 下的发布包 id")
    src.add_argument("--task", help="runtime/tasks 下的 task id")
    p.add_argument("--batch", help="batch id（与 --task 同用）")
    p.add_argument("--copy-entities", action="store_true", help="promote 时同时拷贝 task entities/")
    p.add_argument("--env", help="目标环境逗号分隔（默认采样 manifest 内全部）")
    p.add_argument("--skip-promote", action="store_true", help="跳过 promote，仅对现有 publish 主线重采样")
    p.add_argument("--skip-index", action="store_true", help="跳过 lookup 索引重建")
    p.add_argument("--import", dest="import_to_db", action="store_true", help="采样后直接调用服务侧 importer 灌库")
    p.add_argument("--mongo-uri", help="importer 目标 mongo uri（与 --import 同用）")
    p.add_argument("--data-release-id", help="环境数据发布 releaseId（默认按环境与时间生成）")
    p.add_argument("--mode", choices=["upsert", "sync", "reset-source"], default=DEFAULT_MODE, help="环境 apply 模式")
    p.add_argument("--delete-policy", choices=["none", "tombstone", "hard-delete"], default=DEFAULT_DELETE_POLICY, help="缺失对象处理策略")
    p.add_argument("--source-owner", default=DEFAULT_SOURCE_OWNER, help="本次发布管理的数据所有者")
    p.add_argument("--approved-by", help="生产硬删除审批人/审批 id")
    p.add_argument("--dry-run", action="store_true", help="生成 release artifact 并让 importer 只报告不写入")
    p.add_argument("--confirm-prod-apply", action="store_true", help="确认对 prod 执行真实写入（dry-run 不需要）")
    p.set_defaults(handler=handle_ship)
