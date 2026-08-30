#!/usr/bin/env python3
"""Inspect governance pipeline observe-only admission without mutation or authority."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.governance_pipeline_admission import (  # noqa: E402
    ContractError,
    GovernancePipelineAdmissionError,
    assemble_evidence_bundle,
    contract_failure,
    inspect,
    invalid_inspection,
    load_contract,
    current_repository_input,
)


def _read_input(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def _emit(value: object) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("contract")
    query = commands.add_parser("inspect")
    query.add_argument("--input", required=True)
    current = commands.add_parser("current")
    current.add_argument("--evidence-bundle")
    bundle = commands.add_parser("bundle")
    bundle.add_argument("--refs", required=True, help="JSON object of explicit owner receipt refs")
    bundle.add_argument("--run-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        contract = load_contract()
    except (GovernancePipelineAdmissionError, OSError, UnicodeError, yaml.YAMLError) as error:
        _emit(contract_failure(str(error)))
        return 2
    if args.command == "contract":
        _emit(contract)
        return 0
    if args.command == "bundle":
        try:
            refs = _read_input(args.refs)
            path = assemble_evidence_bundle(contract, run_id=args.run_id, refs=refs)
            _emit({"result": "bundle_assembled", "path": path.relative_to(ROOT).as_posix()})
            return 0
        except (ContractError, GovernancePipelineAdmissionError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            _emit(invalid_inspection(str(error), contract=contract))
            return 2
    try:
        payload = (
            current_repository_input(contract, evidence_bundle=args.evidence_bundle)
            if args.command == "current"
            else _read_input(args.input)
        )
        result = inspect(payload)
    except (ContractError, GovernancePipelineAdmissionError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        result = invalid_inspection(str(error), contract=contract)
    _emit(result)
    return 2 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
