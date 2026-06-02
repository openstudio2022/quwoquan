#!/usr/bin/env python3
"""Discover Flutter devices visible to the current runner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_ops.deploy.lib.dev_up import build_device_report, discover_flutter_devices


DEFAULT_APP_DIR = REPO_ROOT / "quwoquan_app"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-dir",
        default=str(DEFAULT_APP_DIR),
        help="Flutter app directory used to run `flutter devices --machine`.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--include-web",
        action="store_true",
        help="Include Flutter web devices such as Chrome.",
    )
    parser.add_argument(
        "--include-desktop",
        action="store_true",
        help="Include Flutter desktop devices such as macOS.",
    )
    parser.add_argument(
        "--require-mobile",
        action="store_true",
        help="Exit with code 2 when no iOS/Android device is visible.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app_dir = Path(args.app_dir)
    report = build_device_report(
        discover_flutter_devices(
            app_dir,
            include_mobile=True,
            include_web=args.include_web,
            include_desktop=args.include_desktop,
        )
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    if args.require_mobile and report["mobileCount"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
