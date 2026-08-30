#!/usr/bin/env python3
"""Resolve canonical workflows and verify WorkflowResolveReceipt JSON."""
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

from lib.workflow_resolution import ContractError, ResolutionError, load_contract, resolve, verify_receipt  # noqa: E402
from lib.workflow_resolution.resolver import contract_failure, input_failure, receipt_failure  # noqa: E402


def _json_input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def _emit(value: object) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


class TypedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ResolutionError("WFR.INPUT_INVALID", message)


def build_parser() -> argparse.ArgumentParser:
    parser = TypedArgumentParser(description=__doc__, add_help=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("contract-inspect")
    query = commands.add_parser("resolve")
    query.add_argument("--input", required=True)
    verify = commands.add_parser("verify-receipt")
    verify.add_argument("--input", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except ResolutionError as error:
        _emit(input_failure(error.code, error.detail))
        return 2
    try:
        if args.command == "contract-inspect":
            result = load_contract()
        elif args.command == "resolve":
            result = resolve(_json_input(args.input))
        else:
            result = verify_receipt(_json_input(args.input))
    except (ContractError, yaml.YAMLError) as error:
        _emit(contract_failure(str(error)))
        return 2
    except ResolutionError as error:
        failure = receipt_failure(error.detail) if args.command == "verify-receipt" else input_failure(error.code, error.detail)
        _emit(failure)
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        failure = receipt_failure(str(error)) if args.command == "verify-receipt" else input_failure("WFR.INPUT_INVALID", str(error))
        _emit(failure)
        return 2
    _emit(result)
    return 0 if result.get("result") in ("selected", "valid") or args.command == "contract-inspect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
