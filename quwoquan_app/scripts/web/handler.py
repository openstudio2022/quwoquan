"""qwq-app web subcommands."""

from __future__ import annotations

import argparse

from web.verify_offline import verify_offline


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    web = subparsers.add_parser("web", help="Web offline resource checks")
    web_sub = web.add_subparsers(dest="web_command", required=True)

    verify = web_sub.add_parser("verify-offline", help="Verify bundled fonts and web bootstrap")
    verify.add_argument("--build", action="store_true")
    verify.add_argument("--build-mode", choices=["debug", "release"], default="debug")
    verify.set_defaults(handler=_handle_verify_offline)


def _handle_verify_offline(args: argparse.Namespace) -> None:
    verify_offline(build=args.build, build_mode=args.build_mode)
