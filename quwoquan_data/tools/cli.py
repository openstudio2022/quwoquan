from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import batch
import tree_ops


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qwq-data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tree_parser = subparsers.add_parser("tree")
    tree_sub = tree_parser.add_subparsers(dest="tree_command", required=True)
    tree_validate = tree_sub.add_parser("validate")
    tree_validate.add_argument("--tree", choices=["entities", "content", "tags", "all"], default="all")
    tree_validate.set_defaults(handler=tree_ops.handle_validate)

    batch_parser = subparsers.add_parser("batch")
    batch_sub = batch_parser.add_subparsers(dest="batch_command", required=True)
    batch_plan_retrieval = batch_sub.add_parser("plan-retrieval")
    batch_plan_retrieval.add_argument("--plan", required=True)
    batch_plan_retrieval.set_defaults(handler=batch.handle_plan_retrieval)
    batch_status = batch_sub.add_parser("status")
    batch_status.add_argument("--plan", required=True)
    batch_status.set_defaults(handler=batch.handle_status)
    batch_run = batch_sub.add_parser("run")
    batch_run.add_argument("--plan", required=True)
    batch_run.add_argument("--targets", default="")
    batch_run.add_argument("--dry-run", action="store_true")
    batch_run.set_defaults(handler=batch.handle_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
