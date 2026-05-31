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

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _common.io import read_json, write_json
from _common.paths import NOW_ISO, PUBLISH_ROOT, publish_meta_path
from ship.sampler import (
    build_sample_bundle,
    load_publish_records,
    load_sampling_manifest,
    write_sample_bundle,
)


def _promote(args: argparse.Namespace) -> int:
    from promote_to_publish import (
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
    from build_publish_lookup_indexes import build_publish_lookup_indexes

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


def _run_importer(mongo_uri: str, bundles: list[Path]) -> None:
    """调用服务侧 content/entity importer 把 sample bundle 灌进运行库。"""
    service_root = PUBLISH_ROOT.parent.parent / "quwoquan_service"
    for bundle in bundles:
        env = bundle.stem
        cmd = [
            "go", "run", "./services/content-service/cmd/import",
            "--publish-root", str(PUBLISH_ROOT),
            "--sample-bundle", str(bundle),
            "--mongo-uri", mongo_uri,
            "--env", env,
        ]
        print(f"[ship] importing {env}: {' '.join(cmd)}")
        subprocess.run(cmd, cwd=str(service_root), check=True)


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

    bundles: list[Path] = []
    summary: list[dict] = []
    for env in envs:
        bundle = build_sample_bundle(env, manifest, posts, entities)
        path = write_sample_bundle(bundle)
        bundles.append(path)
        summary.append({"env": env, "posts": bundle["counts"]["posts"], "entities": bundle["counts"]["entities"]})
        print(f"[ship] sampled {env}: posts={bundle['counts']['posts']} entities={bundle['counts']['entities']} -> {path}")

    meta = read_json(publish_meta_path()) if publish_meta_path().exists() else {"schemaVersion": "quwoquan.publish.meta"}
    meta["lastShip"] = NOW_ISO
    meta["shipSummary"] = summary
    write_json(publish_meta_path(), meta)

    if args.import_to_db:
        if not args.mongo_uri:
            print("[ship] ERROR: --import 需要 --mongo-uri", file=sys.stderr)
            raise SystemExit(2)
        _run_importer(args.mongo_uri, bundles)
    else:
        print("[ship] 灌库（按需）：")
        print("       go run ./services/content-service/cmd/import \\")
        print(f"         --publish-root {PUBLISH_ROOT} --sample-bundle <bundle> --mongo-uri <uri> --env <env>")


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
    p.set_defaults(handler=handle_ship)
