#!/usr/bin/env python3
"""qwq-data CLI — data root + task/workflow/ops command families.

Commands:
  data       — Explore / baseline / download / build / produce / publish / workflow
  reset      — Clear runtime data
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.python_runtime import maybe_reexec_for_agent_command
from _common.paths import RUNTIME_ROOT, RELEASE_ROOT, PUBLISH_ROOT


def _preserve_tags_reset_release_root(release_root: Path) -> None:
    """清空 release 但保留 tags/ 子树（用户契约：release 下 tags 不清除）。"""
    tags_backup: Path | None = None
    tags_dir = release_root / "tags"
    if tags_dir.is_dir():
        import tempfile

        tags_backup = Path(tempfile.mkdtemp(prefix="qwq_release_tags_"))
        shutil.copytree(tags_dir, tags_backup / "tags", dirs_exist_ok=True)
    if release_root.exists():
        shutil.rmtree(release_root)
    release_root.mkdir(parents=True, exist_ok=True)
    if tags_backup is not None:
        shutil.copytree(tags_backup / "tags", tags_dir, dirs_exist_ok=True)
        shutil.rmtree(tags_backup)


def handle_reset(args: argparse.Namespace) -> None:
    """Clear runtime and/or release directories."""
    if RUNTIME_ROOT.exists():
        shutil.rmtree(RUNTIME_ROOT)
        print(f"[reset] Removed: {RUNTIME_ROOT}")
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"[reset] Created empty: {RUNTIME_ROOT}")

    if args.include_release:
        _preserve_tags_reset_release_root(RELEASE_ROOT)
        print(f"[reset] Cleared release (preserved tags): {RELEASE_ROOT}")
        # publish/tags 是发布主线标签真相源，同样保留。
        pub_tags = PUBLISH_ROOT / "tags"
        pub_tags_backup: Path | None = None
        if pub_tags.is_dir() and PUBLISH_ROOT.exists():
            import tempfile

            pub_tags_backup = Path(tempfile.mkdtemp(prefix="qwq_publish_tags_"))
            shutil.copytree(pub_tags, pub_tags_backup / "tags", dirs_exist_ok=True)
            for child in PUBLISH_ROOT.iterdir():
                if child.name == "tags":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            shutil.copytree(pub_tags_backup / "tags", pub_tags, dirs_exist_ok=True)
            shutil.rmtree(pub_tags_backup)
            print(f"[reset] Cleared publish (preserved tags): {PUBLISH_ROOT}")


def main() -> None:
    maybe_reexec_for_agent_command(sys.argv)

    parser = argparse.ArgumentParser(prog="qwq-data", description="Data engineering pipeline CLI")
    subparsers = parser.add_subparsers(dest="command")

    from env.handler import register_parser as reg_env
    from media.handler import register_parser as reg_media
    from template.handler import register_parser as reg_template
    from plan.handler import register_parser as reg_plan
    from verify.handler import register_parser as reg_verify
    from annotate.handler import register_parser as reg_annotate
    from ship.handler import register_parser as reg_ship
    from task.handler import register_parser as reg_task
    from homepage_assets.handler import register_parser as reg_homepage_assets
    from vertical.handler import register_parser as reg_vertical
    from quality.handler import register_parser as reg_quality
    from data.handler import register_parser as reg_data
    from governance.handler import register_parser as reg_governance
    from audit.handler import register_parser as reg_audit
    from site_supply.handler import register_parser as reg_site_supply
    from task.object_queue import register_object_queue_parser as reg_object_queue

    reg_audit(subparsers)
    reg_env(subparsers)
    reg_data(subparsers)
    reg_site_supply(subparsers)
    reg_object_queue(subparsers)
    reg_media(subparsers)
    reg_template(subparsers)
    reg_plan(subparsers)
    reg_verify(subparsers)
    reg_annotate(subparsers)
    reg_ship(subparsers)
    reg_task(subparsers)
    reg_homepage_assets(subparsers)
    reg_vertical(subparsers)
    reg_quality(subparsers)
    reg_governance(subparsers)

    p_reset = subparsers.add_parser("reset", help="Clear runtime data")
    p_reset.add_argument("--include-release", action="store_true", help="Also clear release/")
    p_reset.set_defaults(handler=handle_reset)

    args = parser.parse_args()
    if not hasattr(args, "handler"):
        parser.print_help()
        sys.exit(1)

    args.handler(args)


if __name__ == "__main__":
    main()
