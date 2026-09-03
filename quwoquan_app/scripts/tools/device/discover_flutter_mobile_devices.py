#!/usr/bin/env python3
"""Discover Flutter devices visible to the current runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.dev_up import (
    build_device_report,
    discover_flutter_devices,
    select_device,
)


DEFAULT_APP_DIR = APP_ROOT


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    parser.add_argument(
        "--pick",
        action="store_true",
        help="Return only the canonical selected mobile device id.",
    )
    parser.add_argument(
        "--device-id",
        default="",
        help="Explicit exact mobile device id to validate in --pick mode.",
    )
    parser.add_argument(
        "--real-flutter",
        default=os.environ.get("QWQ_REAL_FLUTTER", "flutter"),
        help="Exact real Flutter executable used for device discovery.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.device_id and not args.pick:
        print("GATE_BLOCK: --device-id requires --pick.", file=sys.stderr)
        return 2
    app_dir = Path(args.app_dir)
    if not args.real_flutter.strip():
        print("GATE_BLOCK: --real-flutter requires a non-empty executable.", file=sys.stderr)
        return 2
    if args.pick and not Path(args.real_flutter).is_absolute():
        print(
            "GATE_BLOCK: --pick requires an exact absolute real Flutter executable.",
            file=sys.stderr,
        )
        return 2
    try:
        devices = discover_flutter_devices(
            app_dir,
            include_mobile=True,
            include_web=args.include_web if not args.pick else False,
            include_desktop=args.include_desktop if not args.pick else False,
            flutter_executable=args.real_flutter,
        )
        if args.pick:
            print(
                select_device(
                    devices,
                    device_id=args.device_id,
                    label="[flutter-device-authority]",
                )
            )
            return 0
        report = build_device_report(devices)
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
    except (OSError, RuntimeError, ValueError) as error:
        message = str(error)
        if not message.startswith("GATE_BLOCK:"):
            message = f"GATE_BLOCK: device discovery failed: {message}"
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
