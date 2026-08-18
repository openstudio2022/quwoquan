"""CLI for create-once interrupted independent-review reconciliation."""

from __future__ import annotations

import argparse
import json

from core import paths


def _handle(args: argparse.Namespace) -> None:
    from content.execution.campaign.review_interruption_reconciliation import (
        reconcile_interrupted_post_review,
    )

    receipt, path = reconcile_interrupted_post_review(
        str(args.campaign_root_execution_id),
        str(args.execution_id),
        str(args.object_ref),
    )
    print(
        json.dumps(
            {
                "rootExecutionId": receipt["rootExecutionId"],
                "executionId": receipt["executionId"],
                "objectRef": receipt["objectRef"],
                "decision": receipt["decision"],
                "receiptRef": path.relative_to(paths.OUTPUT_ROOT).as_posix(),
                "receiptDigest": receipt["receiptDigest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_reconcile_interrupted_review_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "reconcile-interrupted-review",
        help="将唯一 pending review 与唯一 finished Grok journal 写成 create-once retry 证据",
    )
    parser.add_argument("--campaign-root-execution-id", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--object-ref", required=True)
    parser.set_defaults(handler=_handle)


__all__ = ["register_reconcile_interrupted_review_parser"]
