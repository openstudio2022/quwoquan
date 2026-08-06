"""Canonical CLI writer for one immutable four-lane campaign envelope set."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.io import read_json

from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_request_envelope import write_scale_envelopes
from content.execution.model_contract import SEMANTIC_SELECTION_IDS


def _declarations(
    rows: Iterable[Iterable[str]] | None,
    *,
    kind: str,
    acquisition_root_ref: str,
) -> list[dict[str, str]]:
    declarations: list[dict[str, str]] = []
    for row in rows or ():
        values = tuple(str(value or "").strip() for value in row)
        if len(values) != 2 or not all(values):
            raise ValueError(
                "external input requires one manifestRef and one receiptRef"
            )
        declarations.append(
            {
                "kind": kind,
                "acquisitionRootRef": acquisition_root_ref,
                "manifestRef": values[0],
                "receiptRef": values[1],
            }
        )
    return declarations


def _retry_predecessors(args: argparse.Namespace) -> dict[str, str]:
    rows = {
        carrier: str(getattr(args, f"{carrier}_retry_of", "") or "").strip()
        for carrier in CAMPAIGN_CARRIERS
    }
    return {carrier: value for carrier, value in rows.items() if value}


def _summary(paths: dict[str, Path]) -> dict[str, Any]:
    envelopes = {carrier: read_json(path) for carrier, path in paths.items()}
    homepage = envelopes["homepage"]
    return {
        "schema": "quwoquan_data.campaign_envelope_prepare_result",
        "scale": homepage["scale"],
        "rootExecutionId": homepage["rootExecutionId"],
        "sourceRevision": homepage["sourceRevision"],
        "sourceDigest": homepage["sourceDigest"]["digest"],
        "entityCatalogDigest": homepage["entityCatalogDigest"],
        "semanticSelectionId": homepage["semanticSelectionId"],
        "semanticPreflightReceipt": homepage["semanticPreflightReceipt"],
        "articleExternalInputMode": "execution_source_unit_freeze",
        "envelopes": {
            carrier: {
                "executionId": envelopes[carrier]["executionId"],
                "retryOf": envelopes[carrier]["retryOf"],
                "requestDigest": envelopes[carrier]["requestDigest"],
                "path": path.resolve().as_posix(),
            }
            for carrier, path in paths.items()
        },
    }


def handle_prepare_campaign(args: argparse.Namespace) -> None:
    preflight = Path(str(args.semantic_preflight_receipt)).expanduser().resolve()
    external_inputs = {
        "homepage": _declarations(
            args.homepage_image_input,
            kind="professional_image_acquisition",
            acquisition_root_ref=".",
        ),
        "article": [],
        "image": _declarations(
            args.image_input,
            kind="professional_image_acquisition",
            acquisition_root_ref=".",
        ),
        "video": _declarations(
            args.video_input,
            kind="professional_video_acquisition",
            acquisition_root_ref="video",
        ),
    }
    try:
        paths = write_scale_envelopes(
            str(args.scale),
            region_ref=str(args.region_ref),
            topic=str(args.topic).strip() if str(args.topic or "").strip() else None,
            target_names=tuple(args.target_names or ()),
            source_providers=tuple(args.source_providers or ()),
            day=str(args.run_date),
            sequence=int(args.sequence),
            semantic_selection_id=str(args.semantic_selection_id),
            semantic_preflight_receipt=preflight,
            predecessor_execution_ids_by_carrier=_retry_predecessors(args),
            predecessor_reconciliation_receipt=(
                Path(str(args.predecessor_reconciliation_receipt))
                .expanduser()
                .resolve()
                if str(args.predecessor_reconciliation_receipt or "").strip()
                else None
            ),
            promotion_receipt=(
                Path(str(args.promotion_receipt)).expanduser().resolve()
                if str(args.promotion_receipt or "").strip()
                else None
            ),
            external_input_refs_by_carrier=external_inputs,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task prepare-campaign] GATE_BLOCK {exc}") from exc
    print(json.dumps(_summary(paths), ensure_ascii=False, indent=2))


def register_prepare_campaign_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "prepare-campaign",
        help=(
            "冻结四载体同源 request envelope；article 图片仅由 execution 内 "
            "create-once sourceUnit freeze 提供"
        ),
    )
    parser.add_argument("--scale", required=True)
    parser.add_argument("--region-ref", required=True)
    parser.add_argument("--run-date", required=True, help="YYYYMMDD；retry 保持前序日期")
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--topic")
    parser.add_argument(
        "--target", dest="target_names", action="append", default=[]
    )
    parser.add_argument(
        "--source-provider", dest="source_providers", action="append", default=[]
    )
    parser.add_argument(
        "--semantic-selection-id",
        choices=SEMANTIC_SELECTION_IDS,
        default="default",
    )
    parser.add_argument("--semantic-preflight-receipt", required=True)
    parser.add_argument("--predecessor-reconciliation-receipt")
    parser.add_argument("--promotion-receipt")
    for carrier in CAMPAIGN_CARRIERS:
        parser.add_argument(f"--{carrier}-retry-of")
    parser.add_argument(
        "--homepage-image-input",
        nargs=2,
        action="append",
        required=True,
        metavar=("MANIFEST_REF", "RECEIPT_REF"),
    )
    parser.add_argument(
        "--image-input",
        nargs=2,
        action="append",
        required=True,
        metavar=("MANIFEST_REF", "RECEIPT_REF"),
    )
    parser.add_argument(
        "--video-input",
        nargs=2,
        action="append",
        required=True,
        metavar=("MANIFEST_REF", "RECEIPT_REF"),
    )
    parser.set_defaults(handler=handle_prepare_campaign)


__all__ = ["handle_prepare_campaign", "register_prepare_campaign_parser"]
