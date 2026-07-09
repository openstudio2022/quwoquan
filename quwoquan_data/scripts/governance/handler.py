"""qwq-data governance — auditable data governance candidate operations."""
from __future__ import annotations

import argparse

from governance.review_candidates import main as review_candidates_main
from governance.state_machine import STATUSES


def handle_governance(args: argparse.Namespace) -> None:
    cmd = getattr(args, "governance_command", None)
    if cmd == "creator-pool":
        from governance.creator_pool.handler import handle_creator_pool

        handle_creator_pool(args)
        return
    if cmd == "user-pool":
        from governance.user_pool.handler import handle_user_pool

        handle_user_pool(args)
        return
    if cmd == "review-candidates":
        argv: list[str] = []
        if getattr(args, "root", None):
            argv.extend(["--root", str(args.root)])
        if getattr(args, "reviews", None):
            argv.extend(["--reviews", str(args.reviews)])
        if getattr(args, "list_status", None):
            argv.extend(["--list-status", str(args.list_status)])
        if getattr(args, "kind", None):
            argv.extend(["--kind", str(args.kind)])
        raise SystemExit(review_candidates_main(argv))
    raise SystemExit(f"unknown governance command: {cmd}")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("governance", help="Data governance candidate operations")
    sub = p.add_subparsers(dest="governance_command")

    from governance.creator_pool.handler import register_creator_pool_parser
    from governance.user_pool.handler import register_user_pool_parser

    register_creator_pool_parser(sub)
    register_user_pool_parser(sub)

    review = sub.add_parser("review-candidates", help="Apply or list isolated governance candidate reviews")
    review.add_argument("--root")
    action = review.add_mutually_exclusive_group(required=True)
    action.add_argument("--reviews")
    action.add_argument("--list-status", choices=sorted(STATUSES))
    review.add_argument("--kind")

    p.set_defaults(handler=handle_governance)
