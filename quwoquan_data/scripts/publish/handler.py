"""data publish — assemble release package from task outputs."""
from __future__ import annotations

import argparse

from _common.paths import release_root, RELEASE_ROOT


def handle_publish(args: argparse.Namespace) -> None:
    """Orchestrate publish: assemble → gate → package.

    Merges entities + tags + posts + entity_pages + graph from task batches
    into a unified release package.
    """
    task_id = args.task
    release_id = args.release_id

    root = release_root(release_id)
    print(f"[publish] Task: {task_id} → Release: {release_id}")
    print(f"[publish] Output: {root}")
    print(f"[publish] Steps: assemble → gate → package")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("publish", help="Assemble release package")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--release-id", required=True, help="Release identifier")
    p.set_defaults(handler=handle_publish)
