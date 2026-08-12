"""CLI binding for source-bound Wikimedia Commons metadata discovery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.source.professional_image_supported_api_metadata import (
    METADATA_DISCOVERY_ROOT,
    ProfessionalImageSupportedApiMetadataError,
    discover_supported_api_metadata,
)


def handle_discover_image_supported_api_metadata(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or METADATA_DISCOVERY_ROOT).expanduser().resolve()
    try:
        receipt, receipt_path, catalog_path = discover_supported_api_metadata(
            handoff_ref=Path(args.handoff_ref).expanduser().resolve(),
            discovery_plan_path=Path(args.discovery_plan).expanduser().resolve(),
            entity_catalog_path=Path(args.entity_catalog).expanduser().resolve(),
            candidate_target=int(args.candidate_target),
            results_per_query=int(args.results_per_query),
            providers=tuple(
                args.providers or ("wikimedia_commons", "openverse")
            ),
            output_root=output_root,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[task discover-image-supported-api-metadata] GATE_BLOCK {exc}"
        ) from exc
    except ProfessionalImageSupportedApiMetadataError as exc:
        checkpoint = f" checkpointRef={exc.receipt_ref}" if exc.receipt_ref else ""
        raise SystemExit(
            "[task discover-image-supported-api-metadata] "
            f"GATE_BLOCK {exc}{checkpoint}"
        ) from exc
    if catalog_path is None:
        raise SystemExit(
            "[task discover-image-supported-api-metadata] "
            "GATE_BLOCK DATA.SOURCE.POOL_SHORTFALL: catalog was not materialized"
        )
    print(
        json.dumps(
            {
                **receipt,
                "receiptRef": receipt_path.relative_to(output_root).as_posix(),
                "catalogRef": catalog_path.relative_to(output_root).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_discover_image_supported_api_metadata_parser(
    sub: argparse._SubParsersAction,
) -> None:
    parser = sub.add_parser(
        "discover-image-supported-api-metadata",
        help="从current handoff/实体目录与fresh Commons API生成create-once metadata catalog",
    )
    parser.add_argument("--handoff-ref", required=True)
    parser.add_argument("--discovery-plan", required=True)
    parser.add_argument("--entity-catalog", required=True)
    parser.add_argument("--candidate-target", required=True, type=int)
    parser.add_argument("--results-per-query", type=int, default=50)
    parser.add_argument(
        "--provider",
        dest="providers",
        action="append",
        choices=("wikimedia_commons", "openverse"),
        default=[],
        help="只查询显式受治理 supported-API provider；可重复，默认两者",
    )
    parser.add_argument("--output-root")
    parser.set_defaults(handler=handle_discover_image_supported_api_metadata)


__all__ = [
    "handle_discover_image_supported_api_metadata",
    "register_discover_image_supported_api_metadata_parser",
]
