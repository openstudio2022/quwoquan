"""qwq-data governance user-pool subcommands."""
from __future__ import annotations

import argparse
import json

from _common.creator_pool.batch_policy import default_target_for_batch
from governance.user_pool.media_presets import run_media_presets_build, run_media_presets_verify
from governance.user_pool.rebuild_prefab_users import TRAVEL_PHOTO_BATCH, run_rebuild_prefab_users


def handle_user_pool(args: argparse.Namespace) -> None:
    cmd = args.user_pool_command
    if cmd == "media-presets":
        if args.media_presets_command == "build":
            print(json.dumps(run_media_presets_build(preset_set=args.preset_set, dry_run=bool(args.dry_run)), ensure_ascii=False))
            return
        if args.media_presets_command == "verify":
            print(json.dumps(run_media_presets_verify(preset_set=args.preset_set), ensure_ascii=False))
            return
    if cmd == "rebuild-prefab-users":
        result = run_rebuild_prefab_users(
            batch_id=args.batch,
            target_creators=int(args.target_creators),
            system_prefix=args.system_prefix,
            batch_code=args.batch_code,
            media_preset_set=args.media_preset_set,
            dry_run=bool(args.dry_run),
        )
        print(json.dumps(result, ensure_ascii=False))
        return
    raise SystemExit(f"unknown user-pool command: {cmd}")


def register_user_pool_parser(sub: argparse._SubParsersAction) -> None:
    up = sub.add_parser("user-pool", help="Prefab user-pool governance")
    up_sub = up.add_subparsers(dest="user_pool_command", required=True)

    media = up_sub.add_parser("media-presets", help="Build or verify profile media presets")
    media_sub = media.add_subparsers(dest="media_presets_command", required=True)
    for name in ("build", "verify"):
        p = media_sub.add_parser(name)
        p.add_argument("--preset-set", required=True)
        if name == "build":
            p.add_argument("--dry-run", action="store_true")
        p.set_defaults(handler=handle_user_pool, user_pool_command="media-presets")

    rebuild = up_sub.add_parser("rebuild-prefab-users", help="Rebuild prefab users and compact creator publish package")
    rebuild.add_argument("--batch", default=TRAVEL_PHOTO_BATCH)
    rebuild.add_argument("--target-creators", type=int, default=default_target_for_batch(TRAVEL_PHOTO_BATCH))
    rebuild.add_argument("--system-prefix", default="sys")
    rebuild.add_argument("--batch-code", default="tpdual1k")
    rebuild.add_argument("--media-preset-set", required=True)
    rebuild.add_argument("--dry-run", action="store_true")
    rebuild.set_defaults(handler=handle_user_pool)
