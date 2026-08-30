#!/usr/bin/env python3
"""Thin JSON CLI over the neutral Human-Agent Delivery implementation."""
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

from lib.human_agent_delivery import (  # noqa: E402
    CalibrationError,
    balanced_permutations,
    commercial_evidence_blocker,
    project_commercial_evidence_payload,
    project_role_card,
    project_role_interaction,
    read_calibration_store,
    route,
    typed_blocker,
    validate_calibration_session,
    write_create_once_calibration_session,
)
from lib.human_agent_delivery.calibration import DEFAULT_STORE  # noqa: E402
from lib.human_agent_delivery.eval_runner import POLICY_PATH, run_eval  # noqa: E402


def _read_payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("input JSON must be an object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in (
        "route", "project-card", "project-interaction", "balanced-permutations",
        "commercial-evidence-project",
    ):
        child = sub.add_parser(command)
        child.add_argument("--input", default="-", help="JSON object path, or - for stdin")
        if command in {"project-card", "commercial-evidence-project"}:
            child.add_argument("--harness", choices=("cursor", "codex"), required=True)
        elif command == "project-interaction":
            child.add_argument("--harness", required=True)
    calibration_validate = sub.add_parser("calibration-validate")
    calibration_validate.add_argument("--input", default="-", help="JSON object path, or - for stdin")
    calibration_record = sub.add_parser("calibration-record")
    calibration_record.add_argument("--input", default="-", help="JSON object path, or - for stdin")
    calibration_record.add_argument("--store", default=str(DEFAULT_STORE))
    calibration_readback = sub.add_parser("calibration-readback")
    calibration_readback.add_argument("--store", default=str(DEFAULT_STORE))
    eval_child = sub.add_parser("eval")
    eval_child.add_argument("--policy", default=str(POLICY_PATH))
    eval_child.add_argument("--report", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "eval":
        result = run_eval(policy_path=args.policy, report_path=args.report)
        json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0 if result["status"] == "pass" else 1
    if args.command in {"calibration-validate", "calibration-record", "calibration-readback"}:
        try:
            if args.command == "calibration-validate":
                session = validate_calibration_session(_read_payload(args.input))
                result = {"result": "valid", "session_id": session["session_id"]}
            elif args.command == "calibration-record":
                written = write_create_once_calibration_session(
                    store=Path(args.store), session=_read_payload(args.input)
                )
                result = {
                    "result": "recorded", "created": written.created,
                    "session_id": written.session["session_id"],
                    "ref": written.ref, "digest": written.digest,
                    "readback": read_calibration_store(Path(args.store)),
                }
            else:
                result = read_calibration_store(Path(args.store))
        except CalibrationError as error:
            result = typed_blocker(error.code, detail=error.detail)
        json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 1 if result.get("result") == "typed_blocker" else 0
    if args.command == "project-interaction":
        try:
            result = project_role_interaction(_read_payload(args.input), harness=args.harness)
        except Exception as error:
            result = {
                "result": "typed_blocker", "code": "HAD.INTERACTION_FIELD_INVALID",
                "terminal": "pause", "recovery": "repair_role_interaction_envelope",
                "detail": str(error),
            }
        json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 1 if result.get("result") == "typed_blocker" else 0
    if args.command == "commercial-evidence-project":
        try:
            result = project_commercial_evidence_payload(_read_payload(args.input))
        except Exception as error:
            result = commercial_evidence_blocker(error)
        json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sys.stdout.write("\n")
        return 1 if result.get("result") == "typed_blocker" else 0
    payload = _read_payload(args.input)
    if args.command == "route":
        result = route(**payload)
    elif args.command == "project-card":
        result = project_role_card(**payload)
    else:
        permutations = balanced_permutations(payload["options"], payload["seed"])
        result = {"permutations": permutations}
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
