"""CLI binding for create-once media source admission receipts."""
from __future__ import annotations

import argparse
from pathlib import Path

from content.source.media_source_admission import (
    MediaSourceAdmissionCommandWriter,
    MediaSourceAdmissionQuery,
)
from content.source.research.handler_cli_io import print_document, typed_error


def handle_admit_media_source(args: argparse.Namespace) -> None:
    try:
        receipt, receipt_ref = MediaSourceAdmissionCommandWriter(
            Path(args.evidence_root)
        ).write(
            asset_kind=args.asset_kind,
            asset_id=args.asset_id,
            object_ref=args.object_ref,
            source_revision=args.source_revision,
            source_digest=args.source_digest,
            entity_catalog_digest=args.entity_catalog_digest,
            evidence_refs={
                "catalog": args.catalog_ref,
                "acquisition": args.acquisition_ref,
                "media_probe": args.media_probe_ref,
                "rights_attribution": args.rights_attribution_ref,
                "source_semantic_review": args.source_semantic_review_ref,
            },
            recorded_at=args.recorded_at,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[source-pool admit-media-source] GATE_BLOCK {typed_error(exc)}"
        ) from exc
    print_document(
        {
            "schema": "quwoquan_data.media_source_admission_write_result",
            "receiptRef": receipt_ref,
            "receiptDigest": receipt["receiptDigest"],
            "admissionDecision": receipt["admissionDecision"],
            "blockers": receipt["blockers"],
        }
    )


def handle_inspect_media_source_admission(args: argparse.Namespace) -> None:
    try:
        result = MediaSourceAdmissionQuery(Path(args.evidence_root)).read(
            args.receipt_ref
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            "[source-pool inspect-media-source-admission] "
            f"GATE_BLOCK {typed_error(exc)}"
        ) from exc
    print_document(
        {
            "schema": "quwoquan_data.media_source_admission_query_result",
            "status": result["status"],
            "receiptRef": result["receiptRef"],
            "receiptDigest": result["receiptDigest"],
            "blockers": result["receipt"]["blockers"],
        }
    )


def register_media_source_admission_parsers(
    commands: argparse._SubParsersAction,
) -> None:
    admit_media = commands.add_parser(
        "admit-media-source",
        help="从同一 portable evidence root create-once 冻结媒体来源准入",
    )
    admit_media.add_argument(
        "--asset-kind", choices=("image", "video"), required=True
    )
    admit_media.add_argument("--asset-id", required=True)
    admit_media.add_argument("--object-ref", required=True)
    admit_media.add_argument("--source-revision", required=True)
    admit_media.add_argument("--source-digest", required=True)
    admit_media.add_argument("--entity-catalog-digest", required=True)
    admit_media.add_argument("--evidence-root", required=True)
    admit_media.add_argument("--catalog-ref", required=True)
    admit_media.add_argument("--acquisition-ref", required=True)
    admit_media.add_argument("--media-probe-ref", required=True)
    admit_media.add_argument("--rights-attribution-ref", required=True)
    admit_media.add_argument("--source-semantic-review-ref", required=True)
    admit_media.add_argument("--recorded-at", required=True)
    admit_media.set_defaults(handler=handle_admit_media_source)

    inspect_media = commands.add_parser(
        "inspect-media-source-admission",
        help="逐字节复验 accepted/blocked 媒体来源准入事实",
    )
    inspect_media.add_argument("--evidence-root", required=True)
    inspect_media.add_argument("--receipt-ref", required=True)
    inspect_media.set_defaults(handler=handle_inspect_media_source_admission)


__all__ = [
    "handle_admit_media_source",
    "handle_inspect_media_source_admission",
    "register_media_source_admission_parsers",
]
