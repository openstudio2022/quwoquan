"""data explore — discover POI candidates for a geographic region."""
from __future__ import annotations

import argparse
from pathlib import Path

from _common.paths import ensure_task_layout, task_catalog, task_root
from _common.io import write_ndjson, write_json


def handle_explore(args: argparse.Namespace) -> None:
    """Orchestrate the explore command: geo_query → deduplicate → classify.

    Steps:
    1. geo_query: Query Overpass/open data for POIs (script-driven)
    2. deduplicate: Agent semantic deduplication
    3. classify: Agent semantic classification

    Final output: tasks/{task_id}/catalog.ndjson
    """
    task_id = args.task
    regions = args.regions.split(",") if args.regions else []
    entity_types = args.entity_types.split(",") if args.entity_types else []

    root = ensure_task_layout(task_id)
    print(f"[explore] Task: {task_id}")
    print(f"[explore] Regions: {regions}")
    print(f"[explore] Entity types: {entity_types}")
    print(f"[explore] Task root: {root}")
    print(f"[explore] Ready for Agent semantic processing.")
    print(f"[explore] Agent should produce: {task_catalog(task_id)}")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("explore", help="Discover POI candidates for a region")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--regions", required=True, help="Comma-separated target regions")
    p.add_argument("--entity-types", required=True, help="Comma-separated entity types")
    p.set_defaults(handler=handle_explore)
