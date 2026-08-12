"""CLI binding for physical supported-API image input preparation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.paths import OUTPUT_ROOT

from content.source.professional_image_supported_api_input import (
    PREPARATION_ROOT,
    ProfessionalImageSupportedApiInputError,
    prepare_supported_api_inputs,
)


def handle_prepare_image_supported_api_input(args: argparse.Namespace) -> None:
    output_root = Path(args.output_root or PREPARATION_ROOT).expanduser().resolve()
    try:
        receipt, path = prepare_supported_api_inputs(
            handoff_ref=Path(args.handoff_ref).expanduser().resolve(),
            discovery_plan_path=Path(args.discovery_plan).expanduser().resolve(),
            metadata_catalog_path=Path(args.metadata_catalog).expanduser().resolve(),
            accepted_target=int(args.accepted_target),
            output_root=output_root,
            reviewer_root=Path(args.reviewer_root or OUTPUT_ROOT).expanduser().resolve(),
            reviewer_result_refs=tuple(args.reviewer_result_ref or ()),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[task prepare-image-supported-api-input] GATE_BLOCK {exc}"
        ) from exc
    except ProfessionalImageSupportedApiInputError as exc:
        checkpoint = f" checkpointRef={exc.receipt_ref}" if exc.receipt_ref else ""
        raise SystemExit(
            "[task prepare-image-supported-api-input] "
            f"GATE_BLOCK {exc}{checkpoint}"
        ) from exc
    print(
        json.dumps(
            {**receipt, "receiptRef": path.relative_to(output_root).as_posix()},
            ensure_ascii=False,
            indent=2,
        )
    )


def register_prepare_image_supported_api_input_parser(
    sub: argparse._SubParsersAction,
) -> None:
    parser = sub.add_parser(
        "prepare-image-supported-api-input",
        help="fresh取得Commons API/原图并冻结机器评估、semantic复核请求和acquisition输入",
    )
    parser.add_argument("--handoff-ref", required=True)
    parser.add_argument("--discovery-plan", required=True)
    parser.add_argument("--metadata-catalog", required=True)
    parser.add_argument("--accepted-target", required=True, type=int)
    parser.add_argument("--reviewer-root")
    parser.add_argument("--reviewer-result-ref", action="append", default=[])
    parser.add_argument("--output-root")
    parser.set_defaults(handler=handle_prepare_image_supported_api_input)


__all__ = [
    "handle_prepare_image_supported_api_input",
    "register_prepare_image_supported_api_input_parser",
]
