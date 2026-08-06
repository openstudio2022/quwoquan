"""Canonical CLI binding for provenance-bound independent asset review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.io import read_json

from content.source.independent_asset_review import (
    IndependentAssetReviewError,
    write_independent_asset_review_receipt,
)


def handle_review_asset(args: argparse.Namespace) -> None:
    judgment_path = Path(str(args.judgment)).expanduser().resolve()
    try:
        judgment = read_json(judgment_path)
        if not isinstance(judgment, dict):
            raise TypeError("independent asset judgment must be one JSON object")
        receipt, path = write_independent_asset_review_receipt(
            acquisition_receipt_path=Path(str(args.acquisition_receipt))
            .expanduser()
            .resolve(),
            asset_kind=str(args.asset_kind),
            asset_id=str(args.asset_id),
            execution_manifest_path=Path(str(args.execution_manifest))
            .expanduser()
            .resolve(),
            author_evidence_path=Path(str(args.author_evidence)).expanduser().resolve(),
            reviewer_evidence_path=Path(str(args.reviewer_evidence))
            .expanduser()
            .resolve(),
            object_ref=str(args.object_ref),
            judgment=judgment,
        )
    except (
        FileNotFoundError,
        IndependentAssetReviewError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(f"[task review-asset] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {
                "schema": "quwoquan_data.independent_asset_review_result",
                "reviewId": receipt["reviewId"],
                "reviewDecision": receipt["reviewDecision"],
                "assetKind": receipt["assetKind"],
                "objectRef": receipt["objectRef"],
                "receiptDigest": receipt["receiptDigest"],
                "receiptPath": path.resolve().as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_review_asset_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "review-asset",
        help="将真实 author/reviewer evidence 绑定为独立素材 create-once review receipt",
    )
    parser.add_argument("--acquisition-receipt", required=True)
    parser.add_argument("--asset-kind", required=True, choices=("image", "video"))
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--execution-manifest", required=True)
    parser.add_argument("--author-evidence", required=True)
    parser.add_argument("--reviewer-evidence", required=True)
    parser.add_argument("--object-ref", required=True)
    parser.add_argument("--judgment", required=True)
    parser.set_defaults(handler=handle_review_asset)


__all__ = ["handle_review_asset", "register_review_asset_parser"]
