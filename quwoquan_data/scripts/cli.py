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

from _common.paths import RUNTIME_ROOT, RELEASE_ROOT


def handle_reset(args: argparse.Namespace) -> None:
    """Clear runtime and/or release directories."""
    if RUNTIME_ROOT.exists():
        shutil.rmtree(RUNTIME_ROOT)
        print(f"[reset] Removed: {RUNTIME_ROOT}")
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"[reset] Created empty: {RUNTIME_ROOT}")

    if args.include_release and RELEASE_ROOT.exists():
        shutil.rmtree(RELEASE_ROOT)
        print(f"[reset] Removed: {RELEASE_ROOT}")
        RELEASE_ROOT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="qwq-data", description="Data engineering pipeline CLI")
    subparsers = parser.add_subparsers(dest="command")

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

    reg_data(subparsers)
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
