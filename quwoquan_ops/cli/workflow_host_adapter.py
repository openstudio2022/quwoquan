#!/usr/bin/env python3
"""Neutral versioned host adapter: resolve, verify, then expose Skill PRE routing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(REPO_ROOT))

from lib.workflow_resolution import ContractError, ResolutionError, resolve, verify_receipt  # noqa: E402
from lib.workflow_resolution.resolver import contract_failure, input_failure  # noqa: E402


class TypedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ResolutionError("WFR.INPUT_INVALID", message)


def _emit(value: object) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def _manifest(ref: str | None, target: str | None, scope: str | None) -> dict[str, object] | None:
    if ref is None and target is None and scope is None:
        return None
    if not ref or not target:
        raise ResolutionError("WFR.INPUT_INVALID", "manifest-ref and expected-target must be supplied together")
    return {"ref": ref, "expected_target": target, "expected_scope": scope}


def build_parser() -> argparse.ArgumentParser:
    parser = TypedArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--schema-version", type=int, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--manifest-ref")
    parser.add_argument("--expected-target")
    parser.add_argument("--expected-scope")
    parser.add_argument("--discovery-evidence-ref")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--canonical-command")
    mode.add_argument("--natural-input")
    return parser


def _read_json(path: str) -> Any:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.schema_version != 1:
            raise ResolutionError("WFR.INPUT_INVALID", "host adapter schema-version must be 1")
        common = {
            "host_label": args.host,
            "host_adapter": args.adapter,
            "owner_manifest": _manifest(args.manifest_ref, args.expected_target, args.expected_scope),
        }
        if args.discovery_evidence_ref:
            common["discovery_evidence_ref"] = args.discovery_evidence_ref
        if args.canonical_command:
            payload = {"input_mode": "explicit", "command": args.canonical_command, **common}
        else:
            natural = _read_json(args.natural_input)
            if not isinstance(natural, dict):
                raise ResolutionError("WFR.INPUT_INVALID", "natural input must be a JSON object")
            payload = {"input_mode": "natural_structured", **natural, **common}
        receipt = resolve(payload)
        verification = verify_receipt(receipt)
        result = {
            "schema_id": "workflow-host-adapter-result",
            "schema_version": 1,
            "result": receipt["result"],
            "terminal_code": receipt["terminal_code"],
            "recovery": receipt["recovery"],
            "selected_workflow": receipt["selected_workflow"],
            "skill_ref": receipt["skill_ref"],
            "next_segment": receipt["next_segment"],
            "semantic_identity": receipt["semantic_identity"],
            "receipt": receipt,
            "verification": verification,
        }
    except ContractError as error:
        _emit(contract_failure(str(error)))
        return 2
    except ResolutionError as error:
        _emit(input_failure(error.code, error.detail))
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        _emit(input_failure("WFR.INPUT_INVALID", str(error)))
        return 2
    _emit(result)
    return 0 if result["result"] == "selected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
