"""Public source-pool CLI for host-only source semantic review facts."""
from __future__ import annotations

import argparse
from pathlib import Path

from core.io import read_json
from content.source.host_source_review import (
    prepare_host_source_review_request,
    record_host_source_review_result,
)
from content.source.research.handler_cli_io import print_document, typed_error


def _role_refs(values: list[str]) -> dict[str, str]:
    refs: dict[str, str] = {}
    for value in values:
        role, separator, ref = str(value).partition("=")
        if not separator or not role.strip() or not ref.strip() or role.strip() in refs:
            raise ValueError("--evidence must be unique ROLE=REF values")
        refs[role.strip()] = ref.strip()
    return refs


def handle_prepare_host_source_review_request(args: argparse.Namespace) -> None:
    try:
        request, request_ref = prepare_host_source_review_request(
            evidence_root=Path(args.evidence_root),
            source_identity={
                "sourceRevision": args.source_revision,
                "sourceDigest": args.source_digest,
                "entityCatalogDigest": args.entity_catalog_digest,
                "executionBundleDigest": args.execution_bundle_digest,
                "handoffDigest": args.handoff_digest,
            },
            asset_kind=args.asset_kind,
            asset_id=args.asset_id,
            asset_ref=args.asset_ref,
            content_sha256=args.content_sha256,
            entity_id=args.entity_id,
            observed_entity_id=args.observed_entity_id,
            content_ref=args.content_ref,
            evidence_refs=_role_refs(args.evidence),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            "[source-pool prepare-host-source-review-request] GATE_BLOCK "
            f"{typed_error(exc)}"
        ) from exc
    print_document({
        "schema": "quwoquan_data.host_source_review_request_write_result",
        "requestRef": request_ref,
        "requestDigest": request["requestDigest"],
        "assetId": request["assetBinding"]["assetId"],
        "status": "pending_host_review",
        "nextAction": "record_host_source_review_result",
        "reentryRef": request["requestDigest"],
    })


def handle_record_host_source_review_result(args: argparse.Namespace) -> None:
    try:
        payload = read_json(Path(args.result_input).expanduser().resolve())
        if not isinstance(payload, dict):
            raise TypeError("result input must be one JSON object")
        result, result_ref = record_host_source_review_result(
            evidence_root=Path(args.evidence_root), result_input=payload
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            "[source-pool record-host-source-review-result] GATE_BLOCK "
            f"{typed_error(exc)}"
        ) from exc
    print_document({
        "schema": "quwoquan_data.host_source_review_result_write_result",
        "resultRef": result_ref,
        "resultDigest": result["resultDigest"],
        "requestDigest": result["requestDigest"],
        "assetId": result["assetBinding"]["assetId"],
        "status": result["verdict"]["status"],
    })


def register_host_source_review_parsers(commands: argparse._SubParsersAction) -> None:
    prepare = commands.add_parser(
        "prepare-host-source-review-request",
        help="零语义判断地冻结 host source review request 与 exact evidence 摘要",
    )
    prepare.add_argument("--evidence-root", required=True)
    prepare.add_argument("--asset-kind", choices=("image", "video"), required=True)
    prepare.add_argument("--asset-id", required=True)
    prepare.add_argument("--asset-ref", required=True)
    prepare.add_argument("--content-sha256", required=True)
    prepare.add_argument("--entity-id", required=True)
    prepare.add_argument("--observed-entity-id", required=True)
    prepare.add_argument("--content-ref", required=True)
    prepare.add_argument("--source-revision", required=True)
    prepare.add_argument("--source-digest", required=True)
    prepare.add_argument("--entity-catalog-digest", required=True)
    prepare.add_argument("--execution-bundle-digest", required=True)
    prepare.add_argument("--handoff-digest", required=True)
    prepare.add_argument("--evidence", action="append", required=True)
    prepare.set_defaults(handler=handle_prepare_host_source_review_request)

    record = commands.add_parser(
        "record-host-source-review-result",
        help="校验宿主会话判断并按 request digest create-once 落盘",
    )
    record.add_argument("--evidence-root", required=True)
    record.add_argument("--result-input", required=True)
    record.set_defaults(handler=handle_record_host_source_review_result)


__all__ = [
    "handle_prepare_host_source_review_request",
    "handle_record_host_source_review_result",
    "register_host_source_review_parsers",
]
