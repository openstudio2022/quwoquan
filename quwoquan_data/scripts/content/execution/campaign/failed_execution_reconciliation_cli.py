"""CLI registration for terminal campaign reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core import paths

from content.execution.campaign.failed_execution_reconciliation_common import (
    _ERROR_CODES,
)


def _handle(args: argparse.Namespace) -> None:
    from content.execution.campaign.failed_execution_reconciliation import (
        reconcile_failed_campaign,
    )

    receipt, path = reconcile_failed_campaign(
        str(args.campaign_root_execution_id),
        blocker_evidence=(
            Path(str(args.blocker_evidence)) if args.blocker_evidence else None
        ),
        reason=str(args.reason),
    )
    print(
        json.dumps(
            {
                "rootExecutionId": receipt["rootExecutionId"],
                "decision": receipt["decision"],
                "reason": receipt["reason"],
                "predecessorExecutionIds": {
                    carrier: receipt["submissions"][carrier]["executionId"]
                    for carrier in receipt["activeCarriers"]
                },
                "receiptRef": path.relative_to(paths.OUTPUT_ROOT).as_posix(),
                "receiptDigest": receipt["receiptDigest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_reconcile_failed_campaign_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "reconcile-failed-campaign",
        help="对 terminal failed campaign 写 create-once supersession",
    )
    parser.add_argument("--campaign-root-execution-id", required=True)
    parser.add_argument(
        "--reason",
        choices=tuple(_ERROR_CODES),
        default="source_drift",
    )
    parser.add_argument("--blocker-evidence")
    parser.set_defaults(handler=_handle)


__all__ = ["register_reconcile_failed_campaign_parser"]
