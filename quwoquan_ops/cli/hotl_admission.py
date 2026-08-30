#!/usr/bin/env python3
"""Read-only HOTL admission CLI; no activate, grant, or resume mutation surface."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(REPO_ROOT))

from lib.hotl_admission import (  # noqa: E402
    HotlAdmissionError, contract_failure, inspect, invalid_inspection, load_contract,
)


def _input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("contract")
    query = commands.add_parser("inspect")
    query.add_argument("--input", required=True)
    return parser


def _emit(value: object) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        contract = load_contract()
    except (HotlAdmissionError, OSError, UnicodeError, yaml.YAMLError) as error:
        _emit(contract_failure(str(error)))
        return 2
    if args.command == "contract":
        _emit(contract)
        return 0

    policy = contract["admission_policy"]
    try:
        result = inspect(_input(args.input))
    except (HotlAdmissionError, OSError, UnicodeError, json.JSONDecodeError) as error:
        _emit(invalid_inspection(str(error), policy=policy))
        return 2
    _emit(result)
    return 2 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
