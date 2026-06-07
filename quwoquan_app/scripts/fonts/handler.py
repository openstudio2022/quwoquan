"""qwq-app fonts subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path

from fonts.check_updates import check_updates
from fonts.fetch import fetch_fonts, write_sha256
from fonts.gate import gate_verify


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    fonts = subparsers.add_parser("fonts", help="Bundled fonts lifecycle")
    fonts_sub = fonts.add_subparsers(dest="fonts_command", required=True)

    fetch = fonts_sub.add_parser("fetch", help="Download fonts from upstream manifest")
    fetch.add_argument("--manifest", type=Path, default=None)
    fetch.add_argument("--family", default=None)
    fetch.add_argument("--dry-run", action="store_true")
    fetch.add_argument("--output", choices=["text", "json"], default="text")
    fetch.set_defaults(handler=_handle_fetch)

    write_sha = fonts_sub.add_parser("write-sha", help="Recompute manifest sha256 values")
    write_sha.add_argument("--manifest", type=Path, default=None)
    write_sha.set_defaults(handler=_handle_write_sha)

    verify = fonts_sub.add_parser("verify", help="Verify manifest, disk, and pubspec")
    verify.add_argument("--manifest", type=Path, default=None)
    verify.add_argument("--pubspec", type=Path, default=None)
    verify.set_defaults(handler=_handle_verify)

    check = fonts_sub.add_parser("check-updates", help="Check upstream font drift")
    check.add_argument("--manifest", type=Path, default=None)
    check.add_argument("--output", choices=["text", "json", "markdown"], default="text")
    check.add_argument("--report", type=Path, default=None)
    check.add_argument("--fail-on-drift", action="store_true")
    check.set_defaults(handler=_handle_check_updates)


def _handle_fetch(args: argparse.Namespace) -> None:
    fetch_fonts(
        manifest_file=args.manifest,
        family_filter=args.family,
        dry_run=args.dry_run,
        output=args.output,
    )


def _handle_write_sha(args: argparse.Namespace) -> None:
    write_sha256(manifest_file=args.manifest)


def _handle_verify(args: argparse.Namespace) -> None:
    gate_verify(manifest_file=args.manifest, pubspec_file=args.pubspec)


def _handle_check_updates(args: argparse.Namespace) -> None:
    check_updates(
        manifest_file=args.manifest,
        output=args.output,
        report=args.report,
        fail_on_drift=args.fail_on_drift,
    )
