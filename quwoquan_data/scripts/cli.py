#!/usr/bin/env python3
"""唯一数据工程门面：执行、发布、环境交付、治理与验证。"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Callable
from typing import NamedTuple
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_ROOT.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(REPO_ROOT))

class _CommandDefinition(NamedTuple):
    module: str
    register: str
    help: str


_COMMANDS = {
    "task": _CommandDefinition(
        "content.execution.handler",
        "register_parser",
        "内容执行与任务控制面",
    ),
    "source-pool": _CommandDefinition(
        "content.source.research.handler_cli",
        "register_parser",
        "研究内容源池",
    ),
    "filter-catalog": _CommandDefinition(
        "content.filter_catalog.handler",
        "register_parser",
        "过滤目录发布与验证",
    ),
    "release": _CommandDefinition(
        "content.release.canonical.handler",
        "register_parser",
        "canonical immutable release",
    ),
    "ship": _CommandDefinition(
        "content.release.environment.cli",
        "register_parser",
        "immutable release 环境交付与 readback",
    ),
    "template": _CommandDefinition(
        "content.templates.handler",
        "register_parser",
        "内容模板控制面",
    ),
    "governance": _CommandDefinition(
        "governance.handler",
        "register_parser",
        "数据治理控制面",
    ),
    "verify": _CommandDefinition(
        "verify.handler",
        "register_parser",
        "Data 静态与按需门禁",
    ),
}


def _requested_command(argv: list[str]) -> str | None:
    if not argv or argv[0].startswith("-"):
        return None
    return argv[0]


def _register_selected_command(
    subparsers: argparse._SubParsersAction,
    command: str,
) -> None:
    definition = _COMMANDS[command]
    module = importlib.import_module(definition.module)
    register = getattr(module, definition.register, None)
    if not isinstance(register, Callable):
        raise TypeError(f"Data CLI command {command!r} has no register function")
    register(subparsers)


def _register_command_overview(
    subparsers: argparse._SubParsersAction,
) -> None:
    for name, definition in _COMMANDS.items():
        subparsers.add_parser(name, help=definition.help)


def main() -> None:
    parser = argparse.ArgumentParser(prog="qwq-data", description="Data engineering facade")
    subparsers = parser.add_subparsers(dest="command", required=True)
    requested = _requested_command(sys.argv[1:])
    if requested in _COMMANDS:
        _register_selected_command(subparsers, requested)
    else:
        # Root help and invalid-command diagnostics need only the stable command
        # names.  Domain implementations are imported after one command is
        # selected, so ship/verify never require production or media toolchains.
        _register_command_overview(subparsers)

    args = parser.parse_args()
    handler = getattr(args, "handler", None)
    if not isinstance(handler, Callable):
        parser.error(f"command {args.command!r} requires a subcommand")
    handler(args)


if __name__ == "__main__":
    main()
