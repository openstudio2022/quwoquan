"""`qwq-data filter-catalog` 命令面。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.paths import REPO_ROOT
from content.filter_catalog.artifact import (
    APP_BOOTSTRAP_REF,
    initialize_from_legacy,
    materialize_release,
    validate_repository,
)
from content.filter_catalog.contract import CatalogContractError


def handle_filter_catalog(args: argparse.Namespace) -> None:
    try:
        if args.filter_catalog_command == "initialize":
            report = initialize_from_legacy(
                repo_root=REPO_ROOT,
                legacy_source=Path(args.legacy_source),
                release_id=str(args.release_id),
                source_owner=str(args.source_owner),
            )
        elif args.filter_catalog_command == "materialize":
            report = materialize_release(
                repo_root=REPO_ROOT,
                release_id=str(args.release_id),
            )
        elif args.filter_catalog_command == "validate":
            report = validate_repository(REPO_ROOT)
        else:
            raise CatalogContractError("filter-catalog subcommand required")
    except (CatalogContractError, FileNotFoundError, OSError) as exc:
        raise SystemExit(f"[filter-catalog] GATE_BLOCK: {exc}") from exc

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not bool(report.get("passed")):
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "filter-catalog",
        help="构建、物化并校验 FilterCatalogRelease canonical artifact",
    )
    commands = parser.add_subparsers(
        dest="filter_catalog_command",
        required=True,
    )

    initialize = commands.add_parser(
        "initialize",
        help="一次性把旧 App 目录提升为不可变 canonical release",
    )
    initialize.add_argument(
        "--legacy-source",
        default=str(REPO_ROOT / APP_BOOTSTRAP_REF),
    )
    initialize.add_argument("--release-id", required=True)
    initialize.add_argument("--source-owner", required=True)

    materialize = commands.add_parser(
        "materialize",
        help="从既有 canonical release 重生 bootstrap 与四环境输入",
    )
    materialize.add_argument("--release-id", required=True)

    commands.add_parser(
        "validate",
        help="校验 canonical、digest、bootstrap 与四环境引用同源",
    )
    parser.set_defaults(handler=handle_filter_catalog)
