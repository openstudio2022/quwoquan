#!/usr/bin/env python3
"""qwq-data CLI — 6 commands for the data engineering pipeline.

Commands:
  explore    — Discover POI candidates for a geographic region
  build      — Construct entities, tags, entity pages, and graph
  download   — Multi-platform source acquisition
  produce    — Content production (article/image/video)
  publish    — Assemble release package
  reconcile  — Consistency check and patch loop
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

    from explore.handler import register_parser as reg_explore
    from build.handler import register_parser as reg_build
    from download.handler import register_parser as reg_download
    from produce.handler import register_parser as reg_produce
    from publish.handler import register_parser as reg_publish
    from reconcile.handler import register_parser as reg_reconcile

    reg_explore(subparsers)
    reg_build(subparsers)
    reg_download(subparsers)
    reg_produce(subparsers)
    reg_publish(subparsers)
    reg_reconcile(subparsers)

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
