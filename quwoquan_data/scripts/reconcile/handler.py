"""data reconcile — consistency check and patch loop."""
from __future__ import annotations

import argparse

from _common.paths import ensure_batch_layout, batch_command_root


def handle_reconcile(args: argparse.Namespace) -> None:
    """Orchestrate reconcile: diff → patch_plan → apply_patch → verify.

    Checks consistency between entities/tags/graph and produced posts.
    Incorporates reverse-extract candidates from produce.
    Agent plans patches for inconsistencies.
    """
    task_id = args.task
    batch_id = args.batch

    ensure_batch_layout(task_id, batch_id)
    rec_root = batch_command_root(task_id, batch_id, "reconcile")

    print(f"[reconcile] Task: {task_id}, Batch: {batch_id}")
    print(f"[reconcile] Work dir: {rec_root}")
    print(f"[reconcile] Steps: diff → patch_plan → apply_patch → verify")
    print(f"[reconcile] Ready for Agent semantic processing (patch_plan).")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("reconcile", help="Consistency check and patch loop")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.set_defaults(handler=handle_reconcile)
