#!/usr/bin/env python3
"""唯一数据工程门面：执行、发布、环境交付、治理与验证。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_ROOT.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from core.python_environment import maybe_reexec_for_agent_command


def main() -> None:
    maybe_reexec_for_agent_command(sys.argv)
    parser = argparse.ArgumentParser(prog="qwq-data", description="Data engineering facade")
    subparsers = parser.add_subparsers(dest="command", required=True)

    from content.execution.handler import register_parser as register_task
    from content.filter_catalog.handler import (
        register_parser as register_filter_catalog,
    )
    from content.release.canonical.handler import register_parser as register_release
    from content.release.environment.cli import register_parser as register_ship
    from content.templates.handler import register_parser as register_template
    from governance.handler import register_parser as register_governance
    from verify.handler import register_parser as register_verify

    register_task(subparsers)
    register_filter_catalog(subparsers)
    register_release(subparsers)
    register_ship(subparsers)
    register_template(subparsers)
    register_governance(subparsers)
    register_verify(subparsers)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
