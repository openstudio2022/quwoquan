#!/usr/bin/env python3
"""Thin local projection/journal/readback/admission CLI; no mutation provider is bundled."""
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

from lib.objective_execution import inspect_admission, readback  # noqa: E402
from lib.objective_execution.contract import load_contract  # noqa: E402

DEFAULT_ROOT = REPO_ROOT / ".qwq_output/env/repo/local/objective-execution/process"


def _payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("contract")
    sub.add_parser("admission-inspect")
    query = sub.add_parser("readback")
    query.add_argument("--subject-kind", required=True, choices=("objective", "increment"))
    query.add_argument("--subject-id", required=True)
    query.add_argument("--journal-root", type=Path, default=DEFAULT_ROOT)
    projection = sub.add_parser("projection-inspect")
    projection.add_argument("--input", default="-")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "contract":
        result = load_contract()
    elif args.command == "admission-inspect":
        result = inspect_admission()
    elif args.command == "readback":
        result = readback(args.journal_root, args.subject_kind, args.subject_id).as_dict()
    else:
        projection = _payload(args.input)
        result = {
            "result": "projection",
            "authenticated": False,
            "executable": False,
            "mutation_performed": False,
            "payload": projection,
        }
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result.get("result") != "typed_blocker" else 2


if __name__ == "__main__":
    raise SystemExit(main())
