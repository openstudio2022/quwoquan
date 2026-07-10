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
from _common.media_asset_url import materialize_release_media, resolve_media_cdn_bases
from _common.media_library_sync import sync_media_library
from _common.paths import PUBLISH_ROOT, REPO_ROOT, batch_root, batch_shared_dir, now_iso, publish_meta_path, release_manifest
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
        count, skipped, entity_count = promote_release(args.release_id, dry_run=False)
        print(f"[ship] promoted posts={count} entities={entity_count} skipped={skipped}")
        # homepage-only release 包没有 posts，仅实体主页晋升也算 promote 有效。
        return count + entity_count
    count, skipped = promote_task_batch(args.task, args.batch, dry_run=False)
    entity_count = 0
    if args.copy_entities:
        entity_count = promote_task_entities(args.task, dry_run=False)
    print(f"[ship] promoted posts={count} entities={entity_count} skipped={skipped}")
    # homepage-only 批次没有 posts 产物，仅实体主页进入 publish 主线；
    # 只要有任一类对象晋升即视为 promote 有效，不得误判中止。
    return count + entity_count


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


def _media_cdn_bases_for_env(env: str) -> tuple[str, str]:
    """解析目标环境 (image, video) CDN base：env var 显式覆盖优先，否则读 topology。

    prod 最终值为空或 `media.quwoquan.invalid` 占位一律阻断（topology 缺失时由
    resolve_media_cdn_bases 内部阻断）。
    """
    image = os.environ.get("QWQ_MEDIA_IMAGE_CDN_BASE_URL", "").strip()
    video = os.environ.get("QWQ_MEDIA_VIDEO_CDN_BASE_URL", "").strip()
    if not image:
        topo_image, topo_video = resolve_media_cdn_bases(env)
        image = topo_image
        video = video or topo_video
    elif env == "prod" and "quwoquan.invalid" in image:
        raise SystemExit(
            "[ship] FAIL: prod image CDN base override 是 media.quwoquan.invalid 占位；"
            "请修正 QWQ_MEDIA_IMAGE_CDN_BASE_URL 或改用 topology manifest 解析"
        )
    return image, video


def _sync_media_to_root(dest_root: str, *, release_id: str) -> Path:
    """CAS 媒体库 → 环境媒体根增量同步（sha256 校验），失败即阻断发布。"""
    library = PUBLISH_ROOT / "media" / "library"
    report = sync_media_library(library, Path(dest_root))
    report_path = PUBLISH_ROOT / "env_releases" / release_id / "media-sync.json"
    write_json(report_path, report)
    print(
        f"[ship] media sync -> {dest_root}: copied={report['copied']} "
        f"skipped={report['skipped']} repaired={report['repaired']} failed={report['failed']}"
    )
    if report["failed"] or report["issues"]:
        raise SystemExit(f"[ship] media sync failed: {report_path}")
    return report_path


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
    """调用服务侧 content/entity importer 把 sample bundle 灌进运行库。

    两段式同通道：content importer 灌 posts/entities 运行库；homepage importer
    把实体 page.md 三件套投影进 homepage_state（introductionMarkdown/
    introductionAssets），media base 与 materialize 阶段同源（per-env topology 解析）。
    """
    service_root = _service_root()
    reports: list[Path] = []
    for bundle in bundles:
        # rollback bundle 命名为 rollback-bundle-{env}.json，env 以 bundle 内容为准。
        bundle_doc = read_json(bundle)
        env = str(bundle_doc.get("environment") or bundle.stem)
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

        homepage_report_path = PUBLISH_ROOT / "env_releases" / release_id / f"import-homepage-{env}.json"
        media_base, _ = _media_cdn_bases_for_env(env)
        # entity-service 是独立 go module：须在其 module 根内运行。
        homepage_cmd = [
            "go", "run", "./cmd/homepage-import",
            "--publish-root", str(PUBLISH_ROOT),
            "--sample-bundle", str(bundle),
            "--mongo-uri", mongo_uri,
            "--env", env,
            "--report", str(homepage_report_path),
        ]
        if media_base:
            homepage_cmd.extend(["--media-base-url", media_base])
        metrics_dir = os.environ.get("QWQ_IMPORT_METRICS_TEXTFILE_DIR", "").strip()
        if metrics_dir:
            homepage_cmd.extend([
                "--metrics-textfile",
                str(Path(metrics_dir) / f"homepage_import_{env}.prom"),
            ])
        if dry_run:
            homepage_cmd.append("--dry-run")
        print(f"[ship] importing homepage projections {env}: {' '.join(homepage_cmd)}")
        subprocess.run(homepage_cmd, cwd=str(service_root / "services" / "entity-service"), check=True)
        reports.append(homepage_report_path)
    return reports


def _trigger_entity_reload(reload_url: str, *, release_id: str) -> Path | None:
    """importer 直写运行库后触发 entity-service 免停服重载。

    契约：POST {base}/v1/homepages:reload（metadata operation: ReloadHomepageState）。
    失败不阻断 ship（服务可能未运行，导入结果已在库中，重启后仍生效），但必须
    显式打印并把结果落审计报告，禁止静默吞掉重载失败。
    """
    base = reload_url.rstrip("/")
    endpoint = f"{base}/v1/homepages:reload"
    proc = subprocess.run(
        ["curl", "-sS", "-X", "POST", "-o", "-", "-w", "\n%{http_code}", "--max-time", "30", endpoint],
        capture_output=True,
        check=False,
    )
    raw = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    body, _, code = raw.rpartition("\n")
    ok = proc.returncode == 0 and code == "200"
    result: dict = {
        "schemaVersion": "quwoquan_data.entity_reload_report/1",
        "endpoint": endpoint,
        "httpStatus": code or None,
        "ok": ok,
        "response": body[:2000],
        "triggeredAt": now_iso(),
    }
    report_path = PUBLISH_ROOT / "env_releases" / release_id / "entity-reload.json"
    write_json(report_path, result)
    if ok:
        print(f"[ship] entity-service reload ok: {endpoint} -> {body[:200]}")
    else:
        print(f"[ship] WARNING: entity-service reload failed ({endpoint}, http={code or 'n/a'}); 服务重启后导入仍生效", file=sys.stderr)
    return report_path


def _service_root() -> Path:
    """Resolve the code-anchored service repo root for importer execution.

    Runtime publish roots are often isolated under /tmp for scale trials; service
    code remains part of the checked-out workspace and must not be inferred from
    the publish root location.
    """
    override = os.environ.get("QWQ_SERVICE_ROOT")
    if override:
        return Path(override)
    return REPO_ROOT / "quwoquan_service"


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


def _current_batch_post_refs(task_id: str, batch_id: str) -> list[str]:
    index_path = batch_shared_dir(task_id, batch_id) / "content_object_index.json"
    if not index_path.is_file():
        # homepage-only 批次（如 H100 全国景区主页）只有 entities/ 产物，
        # 没有 posts 与 content_object_index.json；此时 posts 强制清单为空，
        # force sample 只作用于实体 refs。纯 posts 批次缺索引仍必须阻断。
        if (batch_root(task_id, batch_id) / "entities").is_dir():
            return []
        raise SystemExit(f"[ship] --force-current-batch-sample requires content_object_index: {index_path}")
    index = read_json(index_path)
    refs = index.get("refs") if isinstance(index.get("refs"), dict) else {}
    state_path = batch_shared_dir(task_id, batch_id) / "task_workflow_state.json"
    abandoned_refs: set[str] = set()
    if state_path.is_file():
        state = read_json(state_path)
        for item in state.get("abandonedContentObjects") or []:
            if isinstance(item, dict) and str(item.get("status") or "abandoned") == "abandoned":
                ref = str(item.get("ref") or "").strip()
                if ref:
                    abandoned_refs.add(ref)
    post_refs: list[str] = []
    root = batch_root(task_id, batch_id)
    for ref, row in refs.items():
        if not isinstance(row, dict):
            continue
        if str(ref or "").strip() in abandoned_refs:
            continue
        content_type = str(row.get("contentType") or "").strip()
        angle = str(row.get("angle") or "").strip()
        title = str(row.get("title") or "").strip()
        seq = str(row.get("seq") or "").strip()
        if content_type and angle and title and seq:
            post_ref = f"posts/{content_type}/{angle}/{title}/{seq}"
            if (root / post_ref / "manifest.json").is_file():
                post_refs.append(post_ref)
    unique = sorted(set(post_refs))
    if not unique:
        raise SystemExit(f"[ship] --force-current-batch-sample found no post refs in {index_path}")
    return unique


def _current_batch_entity_refs(task_id: str, batch_id: str) -> list[str]:
    root = batch_root(task_id, batch_id) / "entities"
    if not root.is_dir():
        return []
    refs: set[str] = set()
    for entity_file in sorted(root.rglob("_entity.json")):
        try:
            rel = entity_file.parent.relative_to(root)
        except ValueError:
            continue
        parts = [part for part in rel.parts if part]
        if len(parts) >= 3:
            refs.add("/".join(parts[:3]))
    return sorted(refs)


def _split_refs(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _refs_from_file(path_value: str | None) -> list[str]:
    path_text = str(path_value or "").strip()
    if not path_text:
        return []
    path = Path(path_text)
    if not path.is_file():
        raise SystemExit(f"[ship] force post refs file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _assert_forced_posts_in_publish_index(
    forced_post_refs: list[str],
    posts: list[dict],
) -> None:
    if not forced_post_refs:
        return
    known_posts = {str(p.get("postRef") or "").strip() for p in posts if str(p.get("postRef") or "").strip()}
    missing = [ref for ref in forced_post_refs if ref not in known_posts]
    if missing:
        preview = ", ".join(missing[:8])
        raise SystemExit(
            "[ship] forced post refs missing from publish index: "
            f"{preview}. Run ship without --skip-promote, promote the release first, "
            "or remove non-materialized/abandoned refs before importing."
        )


def _assert_forced_entities_in_publish_index(
    forced_entity_refs: list[str],
    entities: list[dict],
) -> None:
    """显式阻断不在 publish index 的强制实体 ref（sampler 会静默过滤，此处保证诚实失败）。"""
    if not forced_entity_refs:
        return
    from ship.sampler import _normalize_entity_ref

    known = {
        _normalize_entity_ref(e.get("entityRef"))
        for e in entities
        if _normalize_entity_ref(e.get("entityRef"))
    }
    missing = [ref for ref in forced_entity_refs if _normalize_entity_ref(ref) not in known]
    if missing:
        preview = ", ".join(missing[:8])
        raise SystemExit(
            "[ship] forced entity refs missing from publish index: "
            f"{preview}. Promote the entities into publish mainline first."
        )


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


def build_rollback_plan(
    to_release_id: str,
    env: str,
    *,
    posts: list[dict],
    entities: list[dict],
    publish_root: Path | None = None,
) -> dict:
    """从历史 release contract 重建目标环境的回滚 bundle。

    回滚前提：desiredRefs 仍全部存在于 publish 主线索引。publish 主线是
    append-only 的内容真相源，refs 缺失说明主线被破坏，此时回滚不可幂等重放，
    必须阻断并人工介入，禁止静默丢内容。
    """
    root = publish_root or PUBLISH_ROOT
    contract_path = root / "env_releases" / to_release_id / f"{env}.json"
    if not contract_path.is_file():
        raise SystemExit(f"[ship] rollback: release contract not found: {contract_path}")
    source_contract = read_json(contract_path)
    if str(source_contract.get("schemaVersion") or "") != "quwoquan.data_env_release.v1":
        raise SystemExit(f"[ship] rollback: unsupported contract schema in {contract_path}")

    desired = source_contract.get("desiredRefs") or {}
    desired_posts = [str(r) for r in (desired.get("posts") or [])]
    desired_entities = [str(r) for r in (desired.get("entities") or [])]

    known_posts = {str(p.get("postRef") or "").strip() for p in posts}
    known_entities = {str(e.get("entityRef") or "").strip() for e in entities}
    missing_posts = [r for r in desired_posts if r not in known_posts]
    missing_entities = [r for r in desired_entities if r not in known_entities]
    if missing_posts or missing_entities:
        preview = ", ".join((missing_posts + missing_entities)[:8])
        raise SystemExit(
            f"[ship] rollback: {len(missing_posts) + len(missing_entities)} refs missing from publish index: "
            f"{preview}. publish 主线已不含历史 release 的全部对象，无法幂等重放。"
        )

    sample_meta = source_contract.get("sampleBundle") or {}
    bundle = {
        "schemaVersion": "quwoquan.content_sample_bundle",
        "environment": env,
        "sampleRatio": sample_meta.get("sampleRatio", 1.0),
        "salt": sample_meta.get("salt", ""),
        "posts": sorted(set(desired_posts)),
        "entities": sorted(set(desired_entities)),
        "forcedPosts": [],
        "forcedEntities": [],
        "isolatedForcedSample": True,
        "rollbackOf": to_release_id,
        "counts": {
            "posts": len(set(desired_posts)),
            "entities": len(set(desired_entities)),
        },
    }
    return {"bundle": bundle, "sourceContract": source_contract}


def handle_ship_rollback(args: argparse.Namespace) -> None:
    """qwq-data ship rollback --to-release <dataReleaseId>：历史目标态 sync+tombstone 重放。"""
    to_release = str(getattr(args, "to_release", "") or "").strip()
    if not to_release:
        raise SystemExit("[ship] rollback: 需要 --to-release <dataReleaseId>")
    env_arg = str(getattr(args, "env", "") or "").strip()
    release_dir = PUBLISH_ROOT / "env_releases" / to_release
    if env_arg:
        envs = [e.strip() for e in env_arg.split(",") if e.strip()]
    else:
        # 未指定环境时，回滚该 release 覆盖的全部环境（按 contract 文件识别）。
        envs = sorted(
            p.stem
            for p in release_dir.glob("*.json")
            if p.is_file()
            and isinstance((data := read_json(p)), dict)
            and str(data.get("schemaVersion") or "") == "quwoquan.data_env_release.v1"
        ) if release_dir.is_dir() else []
    if not envs:
        raise SystemExit(f"[ship] rollback: 在 {release_dir} 未找到任何环境 release contract")

    if "prod" in envs and bool(getattr(args, "import_to_db", False)) \
            and not bool(getattr(args, "dry_run", False)) and not bool(getattr(args, "confirm_prod_apply", False)):
        raise SystemExit("[ship] rollback: prod apply 需要 --confirm-prod-apply（或先 --dry-run 演练）")

    posts, entities = load_publish_records()
    rollback_release_id = normalize_release_id(
        getattr(args, "data_release_id", None) or f"rollback_{to_release}_{now_iso()}",
        env="-".join(envs),
    )

    bundles: list[Path] = []
    for env in envs:
        plan = build_rollback_plan(to_release, env, posts=posts, entities=entities)
        bundle = plan["bundle"]
        bundle_path = PUBLISH_ROOT / "env_releases" / rollback_release_id / f"rollback-bundle-{env}.json"
        write_json(bundle_path, bundle)

        image_cdn_base, video_cdn_base = _media_cdn_bases_for_env(env)
        media_manifest = materialize_release_media(
            env=env,
            release_id=rollback_release_id,
            post_refs=list(bundle["posts"]),
            entity_refs=list(bundle["entities"]),
            publish_root=PUBLISH_ROOT,
            source_owner=str(plan["sourceContract"].get("sourceOwner") or DEFAULT_SOURCE_OWNER),
            image_cdn_base_url=image_cdn_base,
            video_cdn_base_url=video_cdn_base,
        )
        contract = build_release_contract(
            env=env,
            bundle=bundle,
            posts=posts,
            entities=entities,
            release_id=rollback_release_id,
            mode="sync",
            delete_policy="tombstone",
            source_owner=str(plan["sourceContract"].get("sourceOwner") or DEFAULT_SOURCE_OWNER),
            approved_by=getattr(args, "approved_by", None),
            media_manifest=media_manifest,
        )
        contract["rollbackOf"] = to_release
        release_path = write_release_contract(contract, publish_root=PUBLISH_ROOT)
        report = scan_release_contract(contract, publish_root=PUBLISH_ROOT, phase="preflight")
        report_path = release_path.parent / f"consistency-preflight-{env}.json"
        write_consistency_report(report, report_path)
        if report["status"] != "passed":
            raise SystemExit(f"[ship] rollback consistency preflight failed for {env}: {report_path}")
        bundles.append(bundle_path)
        print(
            f"[ship] rollback plan {env}: posts={bundle['counts']['posts']} "
            f"entities={bundle['counts']['entities']} rollbackOf={to_release} -> {release_path}"
        )

    if bool(getattr(args, "import_to_db", False)):
        if not getattr(args, "mongo_uri", None):
            raise SystemExit("[ship] rollback: --import 需要 --mongo-uri")
        _run_importer(
            args.mongo_uri,
            bundles,
            release_id=rollback_release_id,
            mode="sync",
            delete_policy="tombstone",
            source_owner=DEFAULT_SOURCE_OWNER,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
    else:
        print("[ship] rollback plan 已生成（未 --import，不写运行库）")


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
    force_current_batch = bool(getattr(args, "force_current_batch_sample", False))
    if force_current_batch and not (args.task and args.batch):
        raise SystemExit("[ship] --force-current-batch-sample requires --task and --batch")
    forced_post_refs = sorted(
        set(_current_batch_post_refs(args.task, args.batch) if force_current_batch else [])
        | set(_split_refs(getattr(args, "force_post_refs", None)))
        | set(_refs_from_file(getattr(args, "force_post_refs_file", None)))
    )
    _assert_forced_posts_in_publish_index(forced_post_refs, posts)
    forced_entity_refs = sorted(
        set(_current_batch_entity_refs(args.task, args.batch) if force_current_batch else [])
        | set(_split_refs(getattr(args, "force_entity_refs", None)))
    )
    _assert_forced_entities_in_publish_index(forced_entity_refs, entities)
    isolate_forced_sample = bool(getattr(args, "isolate_forced_sample", False))

    bundles: list[Path] = []
    summary: list[dict] = []
    for env in envs:
        bundle = build_sample_bundle(
            env,
            manifest,
            posts,
            entities,
            forced_post_refs=forced_post_refs,
            forced_entity_refs=forced_entity_refs,
            isolate_forced_sample=isolate_forced_sample,
        )
        path = write_sample_bundle(bundle)
        image_cdn_base, video_cdn_base = _media_cdn_bases_for_env(env)
        media_manifest = materialize_release_media(
            env=env,
            release_id=release_id,
            post_refs=list(bundle.get("posts") or []),
            entity_refs=list(bundle.get("entities") or []),
            publish_root=PUBLISH_ROOT,
            source_owner=source_owner,
            image_cdn_base_url=image_cdn_base,
            video_cdn_base_url=video_cdn_base,
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
            "forcedPosts": list(bundle.get("forcedPosts") or []),
            "forcedEntities": list(bundle.get("forcedEntities") or []),
            "isolatedForcedSample": bool(bundle.get("isolatedForcedSample")),
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

    sync_media_root = str(getattr(args, "sync_media_root", "") or "").strip()
    if sync_media_root:
        _sync_media_to_root(sync_media_root, release_id=release_id)

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
        reload_url = str(getattr(args, "entity_reload_url", "") or "").strip()
        if reload_url and not bool(getattr(args, "dry_run", False)):
            report = _trigger_entity_reload(reload_url, release_id=release_id)
            if report is not None:
                import_reports.append(report)
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
    src.add_argument("--task", help="data/local/runtime/tasks 下的 task id")
    p.add_argument("--batch", help="batch id（与 --task 同用）")
    p.add_argument("--copy-entities", action="store_true", help="promote 时同时拷贝 task entities/")
    p.add_argument("--env", help="目标环境逗号分隔（默认采样 manifest 内全部）")
    p.add_argument("--skip-promote", action="store_true", help="跳过 promote，仅对现有 publish 主线重采样")
    p.add_argument("--skip-index", action="store_true", help="跳过 lookup 索引重建")
    p.add_argument("--import", dest="import_to_db", action="store_true", help="采样后直接调用服务侧 importer 灌库")
    p.add_argument("--mongo-uri", help="importer 目标 mongo uri（与 --import 同用）")
    p.add_argument(
        "--entity-reload-url",
        dest="entity_reload_url",
        help="entity-service base URL；灌库后 POST /v1/homepages:reload 免停服重载（dry-run 不触发）",
    )
    p.add_argument("--data-release-id", help="环境数据发布 releaseId（默认按环境与时间生成）")
    p.add_argument("--mode", choices=["upsert", "sync", "reset-source"], default=DEFAULT_MODE, help="环境 apply 模式")
    p.add_argument("--delete-policy", choices=["none", "tombstone", "hard-delete"], default=DEFAULT_DELETE_POLICY, help="缺失对象处理策略")
    p.add_argument("--source-owner", default=DEFAULT_SOURCE_OWNER, help="本次发布管理的数据所有者")
    p.add_argument("--approved-by", help="生产硬删除审批人/审批 id")
    p.add_argument("--dry-run", action="store_true", help="生成 release artifact 并让 importer 只报告不写入")
    p.add_argument("--confirm-prod-apply", action="store_true", help="确认对 prod 执行真实写入（dry-run 不需要）")
    p.add_argument(
        "--force-current-batch-sample",
        action="store_true",
        help="受控发布时强制把当前 task/batch 物化的 post refs 纳入目标环境样本",
    )
    p.add_argument(
        "--force-post-refs",
        help="受控发布时额外强制纳入的 postRef，逗号分隔；必须已存在于 publish index",
    )
    p.add_argument(
        "--force-entity-refs",
        help="受控发布时额外强制纳入的 entityRef（domain/etype/name 三段），逗号分隔；必须已存在于 publish index",
    )
    p.add_argument(
        "--force-post-refs-file",
        help="受控发布时额外强制纳入的 postRef 文件；支持 JSON array 或一行一个 ref，避免标题含逗号时被拆分",
    )
    p.add_argument(
        "--isolate-forced-sample",
        action="store_true",
        help="受控发布时只采 forced post/entity refs，不混入环境默认随机样本",
    )
    p.add_argument(
        "--sync-media-root",
        help="CAS 媒体库增量同步目标（环境媒体根，如 .qwq_output/env/gamma/local/gamma-local/media 或 /srv/media）；sha256 校验失败即阻断",
    )
    p.set_defaults(handler=handle_ship)

    ship_sub = p.add_subparsers(dest="ship_command", required=False)
    rb = ship_sub.add_parser(
        "rollback",
        help="用历史 release contract 以 sync+tombstone 幂等重放目标环境",
    )
    rb.add_argument("--to-release", required=True, help="历史环境数据发布 dataReleaseId（publish/env_releases/ 下）")
    rb.add_argument("--env", help="目标环境逗号分隔（默认回滚该 release 覆盖的全部环境）")
    rb.add_argument("--data-release-id", help="本次回滚发布的 releaseId（默认 rollback_<原id>_<时间>）")
    rb.add_argument("--import", dest="import_to_db", action="store_true", help="生成回滚计划后直接调 importer 重放")
    rb.add_argument("--mongo-uri", help="importer 目标 mongo uri（与 --import 同用）")
    rb.add_argument("--approved-by", help="生产回滚审批人/审批 id")
    rb.add_argument("--dry-run", action="store_true", help="importer 只报告不写入")
    rb.add_argument("--confirm-prod-apply", action="store_true", help="确认对 prod 执行真实回滚写入")
    rb.set_defaults(handler=handle_ship_rollback)
