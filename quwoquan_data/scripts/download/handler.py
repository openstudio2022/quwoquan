"""data download — multi-platform source acquisition."""
from __future__ import annotations

import argparse

from _common.paths import ensure_batch_layout, batch_command_root


def handle_download(args: argparse.Namespace) -> None:
    """Orchestrate download: source_plan → fetch → source_screen.

    Steps:
    1. source_plan: Agent plans multi-platform download strategy per entity
    2. fetch: Script executes HTTP fetches + text extraction
    3. source_screen: Agent screens quality/relevance/copyright

    Output: batches/{batch_id}/download/sources/{entity_id}/{source_id}/source.md
    """
    task_id = args.task
    batch_id = args.batch
    entity_ids = args.entity_ids.split(",") if args.entity_ids else []

    ensure_batch_layout(task_id, batch_id, "download")
    dl_root = batch_command_root(task_id, batch_id, "download")

    print(f"[download] Task: {task_id}, Batch: {batch_id}")
    print(f"[download] Target entities: {entity_ids}")
    print(f"[download] Work dir: {dl_root}")
    print(f"[download] Ready for Agent: source_plan → fetch → source_screen")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("download", help="Multi-platform source acquisition")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.add_argument("--entity-ids", required=True, help="Comma-separated entity IDs")
    p.set_defaults(handler=handle_download)
