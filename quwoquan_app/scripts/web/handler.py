"""qwq-app web subcommands."""

from __future__ import annotations

import argparse

from web.bootstrap_assets import check as check_bootstrap_assets
from web.bootstrap_assets import generate as generate_bootstrap_assets
from web.verify_offline import verify_offline


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    web = subparsers.add_parser("web", help="Web offline resource checks")
    web_sub = web.add_subparsers(dest="web_command", required=True)

    verify = web_sub.add_parser("verify-offline", help="Verify bundled fonts and web bootstrap")
    verify.add_argument("--build", action="store_true")
    verify.add_argument("--build-mode", choices=["debug", "release"], default="debug")
    verify.set_defaults(handler=_handle_verify_offline)

    generate = web_sub.add_parser(
        "generate-bootstrap",
        help="Generate web bootstrap surface assets from design tokens and l10n ARB",
    )
    generate.add_argument("--check", action="store_true")
    generate.set_defaults(handler=_handle_generate_bootstrap)


def _handle_verify_offline(args: argparse.Namespace) -> None:
    verify_offline(build=args.build, build_mode=args.build_mode)


def _handle_generate_bootstrap(args: argparse.Namespace) -> None:
    if args.check:
        check_bootstrap_assets()
        return
    for path in generate_bootstrap_assets():
        print(f"generated {path}")
