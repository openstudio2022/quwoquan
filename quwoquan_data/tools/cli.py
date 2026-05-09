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

    crawl_parser = subparsers.add_parser("crawl")
    crawl_sub = crawl_parser.add_subparsers(dest="crawl_command", required=True)

    crawl_spec_discovery = crawl_sub.add_parser("spec-discovery")
    crawl_spec_discovery.add_argument("--spec", required=True)
    crawl_spec_discovery.set_defaults(handler=batch.handle_spec_discovery)

    crawl_status = crawl_sub.add_parser("status")
    crawl_status.add_argument("--spec", required=True)
    crawl_status.set_defaults(handler=batch.handle_status)

    crawl_fetch_source = crawl_sub.add_parser("fetch-source")
    crawl_fetch_source.add_argument("--spec", required=True)
    crawl_fetch_source.add_argument("--topic", required=True)
    crawl_fetch_source.add_argument("--task-type", required=True, choices=["article", "image"])
    crawl_fetch_source.add_argument("--source-id", required=True)
    crawl_fetch_source.add_argument("--url", required=True)
    crawl_fetch_source.add_argument("--title", default="")
    crawl_fetch_source.add_argument("--query", default="")
    crawl_fetch_source.add_argument("--snippet", default="")
    crawl_fetch_source.add_argument("--source-role", default="publish_candidate")
    crawl_fetch_source.add_argument("--rights-status", default="clear")
    crawl_fetch_source.add_argument("--watermark-status", default="clean")
    crawl_fetch_source.set_defaults(handler=batch.handle_fetch_source)

    crawl_run_topic = crawl_sub.add_parser("run-topic")
    crawl_run_topic.add_argument("--spec", required=True)
    crawl_run_topic.add_argument("--topic", required=True)
    crawl_run_topic.add_argument("--targets", default="")
    crawl_run_topic.add_argument("--dry-run", action="store_true")
    crawl_run_topic.set_defaults(handler=batch.handle_run_topic)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
