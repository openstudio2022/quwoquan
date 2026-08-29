# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-001
# readiness_case: account_enforcement_gamma_uat_ops_env
"""Fail-closed Gamma account-enforcement UAT evidence aggregation.

The live journey crosses operator OIDC, Product Ops PostgreSQL/outbox,
UserAccount, two physical App platforms, fault injection, readiness and
observability.  This module deliberately does not invent a test-only service
or a second environment entry.  It accepts only immutable artifacts below
``QWQ_OUTPUT_ROOT`` and emits a passed CaseResult after every required fact is
present, internally consistent and bound to one candidate digest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


sys.dont_write_bytecode = True

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

from account_enforcement_gamma_uat_shared import (  # noqa: E402
    CASE_RESULT_SCHEMA,
    DEFAULT_MANIFEST,
    EVIDENCE_SCHEMA,
    EXPECTED_ARTIFACT_KINDS,
    EXPECTED_ASSERTIONS,
    EXPECTED_DEVICE_TARGETS,
    EXPECTED_OPERATION_SCOPES,
    EXPECTED_SPEC_REFS,
    EvidenceError,
    JOURNEY_SCHEMA,
    MANIFEST_SCHEMA,
    REPO_ROOT,
    RUN_ID_RE,
    SHA256_RE,
    _evidence_path,
    load_manifest,
    output_root,
    utc_now,
)
from account_enforcement_gamma_uat_validators import (  # noqa: E402
    _validate_approved_case,
    _validate_artifact_refs,
    aggregate_case_result,
    validate_device_report,
    validate_journey_receipt,
)

def _report_path(raw: str, run_id: str) -> Path:
    if raw.strip():
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
    else:
        candidate = (
            output_root()
            / "env"
            / "gamma"
            / "runs"
            / "account-enforcement-gamma-uat"
            / (run_id or "preflight")
            / "case-result.json"
        )
    candidate = candidate.resolve()
    try:
        candidate.relative_to(output_root())
    except ValueError as exc:
        raise EvidenceError("CaseResult report must stay below QWQ_OUTPUT_ROOT") from exc
    return candidate


def _write_once(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise EvidenceError(f"CaseResult artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--run-id",
        default=os.environ.get("QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RUN_ID", ""),
    )
    parser.add_argument(
        "--candidate-digest",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST", ""
        ),
    )
    parser.add_argument(
        "--journey-receipt",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_JOURNEY_RECEIPT", ""
        ),
    )
    parser.add_argument(
        "--suspended-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_DEVICE_REPORT", ""
        ),
    )
    parser.add_argument(
        "--restored-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RESTORED_DEVICE_REPORT", ""
        ),
    )
    parser.add_argument("--report", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = str(args.run_id or "").strip()
    candidate_digest = str(args.candidate_digest or "").strip()
    try:
        report_path = _report_path(args.report, run_id)
        if RUN_ID_RE.fullmatch(run_id) is None:
            raise EvidenceError("runId must be a unique 8-128 character execution id")
        if SHA256_RE.fullmatch(candidate_digest) is None:
            raise EvidenceError("candidateDigest must be canonical sha256")
        journey_path, journey_ref = _evidence_path(
            args.journey_receipt, "journey receipt"
        )
        suspended_path, suspended_ref = _evidence_path(
            args.suspended_device_report, "suspended device report"
        )
        restored_path, restored_ref = _evidence_path(
            args.restored_device_report, "restored device report"
        )
        payload = aggregate_case_result(
            manifest_path=Path(args.manifest).expanduser().resolve(),
            run_id=run_id,
            candidate_digest=candidate_digest,
            journey_path=journey_path,
            journey_ref=journey_ref,
            suspended_path=suspended_path,
            suspended_ref=suspended_ref,
            restored_path=restored_path,
            restored_ref=restored_ref,
        )
        _write_once(report_path, payload)
    except EvidenceError as exc:
        issue = str(exc)
        try:
            report_path = _report_path(args.report, run_id)
            _write_once(
                report_path,
                {
                    "schema": CASE_RESULT_SCHEMA,
                    "status": "gate_block",
                    "capturedAt": utc_now(),
                    "environment": "gamma",
                    "target": "gamma-local",
                    "runId": run_id,
                    "candidateDigest": candidate_digest,
                    "issues": [issue],
                    "caseResults": [],
                },
            )
        except EvidenceError as report_error:
            print(f"GATE_BLOCK: {issue}; report error: {report_error}", file=sys.stderr)
            return 2
        print(f"GATE_BLOCK: {issue}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
