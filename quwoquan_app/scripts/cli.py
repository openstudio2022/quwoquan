#!/usr/bin/env python3
"""qwq-app CLI — App-side maintenance and verification commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(prog="qwq-app", description="Quwoquan app maintenance CLI")
    subparsers = parser.add_subparsers(dest="domain", required=True)

    from fonts.handler import register_parser as register_fonts
    from web.handler import register_parser as register_web

    register_fonts(subparsers)
    register_web(subparsers)

    args = parser.parse_args()
    if not hasattr(args, "handler"):
        parser.print_help()
        raise SystemExit(1)
    args.handler(args)


if __name__ == "__main__":
    main()
