#!/usr/bin/env python3
"""Project one hosted receipt readback into a terminal replay deploy report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.render_release_lifecycle_receipts import (
    HOSTED_AUTHORITY,
    STAGES,
    _validate_receipt_readback,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    validate_manifest,
)
from quwoquan_ops.cli.prod import hosted_release_ledger


ROLLBACK_BUDGET_MS = 300_000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--stage-readback", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--service", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _load_json(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def render(
    *,
    manifest: dict[str, Any],
    stage_readback: dict[str, Any],
    stage: str,
    service: str,
) -> dict[str, Any]:
    validate_manifest(manifest, allowed_statuses={"deployable"})
    if stage not in STAGES:
        raise ValueError("hosted release stage is invalid")
    if not service.strip():
        raise ValueError("hosted release service is missing")
    receipt = _validate_receipt_readback(stage_readback, service=service)
    candidate = str(manifest.get("candidateId") or "")
    artifact = str(manifest.get("artifactDigest") or "")
    post_checks = receipt.get("postChecks")
    rollback_outcome = receipt.get("rollbackOutcome")
    rollback_evidence = hosted_release_ledger.validate_rollback_evidence(
        receipt.get("rollbackEvidence"),
        decision=receipt.get("decision"),
        rollback_outcome=rollback_outcome,
        verified_at=receipt.get("verifiedAt"),
    )
    if (
        receipt.get("artifactDigest") != artifact
        or receipt.get("triggerStage") != stage
        or not isinstance(post_checks, list)
    ):
        raise ValueError("hosted receipt is not manifest and stage bound")

    if rollback_outcome == "not_triggered":
        if (
            receipt.get("decision") != "continue"
            or receipt.get("toCandidateDigest") != candidate
            or receipt.get("stage") != stage
            or any(check.get("status") != "passed" for check in post_checks)
        ):
            raise ValueError(
                "hosted receipt cannot project a successful candidate-bound stage report"
            )
        exit_code = 0
        rollout_decision = "continue"
        rollback_report: dict[str, Any] = {"triggered": False}
        rollback_post_checks: list[dict[str, Any]] = []
    elif rollback_outcome == "rolled_back":
        if not (
            receipt.get("decision") == "rolled_back"
            and receipt.get("fromCandidateDigest") == candidate
            and receipt.get("toCandidateDigest")
            == receipt.get("lastGoodCandidateDigest")
            and receipt.get("stage") == "full"
            and rollback_evidence["durationMs"] <= ROLLBACK_BUDGET_MS
        ):
            raise ValueError(
                "hosted receipt cannot project a candidate-bound successful rollback"
            )
        exit_code = 1
        rollout_decision = "rollback"
        rollback_report = {
            "triggered": True,
            "startedAt": rollback_evidence["startedAt"],
            "endedAt": rollback_evidence["endedAt"],
            "durationMs": rollback_evidence["durationMs"],
        }
        rollback_post_checks = _project_check_summaries(
            rollback_evidence["postChecks"]
        )
    elif rollback_outcome == "rollback_failed":
        if not (
            receipt.get("decision") == "rollback_failed"
            and receipt.get("fromCandidateDigest")
            == receipt.get("lastGoodCandidateDigest")
            and receipt.get("toCandidateDigest") == candidate
            and receipt.get("stage") == stage
            and rollback_evidence["durationMs"] <= ROLLBACK_BUDGET_MS
        ):
            raise ValueError(
                "hosted receipt cannot project a candidate-bound rollback failure"
            )
        exit_code = 1
        rollout_decision = "rollback"
        rollback_report = {
            "triggered": True,
            "startedAt": rollback_evidence["startedAt"],
            "endedAt": rollback_evidence["endedAt"],
            "durationMs": rollback_evidence["durationMs"],
        }
        rollback_post_checks = _project_check_summaries(
            rollback_evidence["postChecks"]
        )
    else:
        raise ValueError("paused hosted receipt cannot project a terminal stage report")

    receipt_id = str(receipt["receiptId"])
    receipt_ref = f"receipt:hosted:{receipt_id}"
    return {
        "command": "deploy",
        "target": "prod-hosted",
        "rolloutStage": stage,
        "triggerStage": stage,
        "terminalStage": receipt["stage"],
        "rolloutDecision": rollout_decision,
        "artifactDigest": artifact,
        "candidateId": candidate,
        "releaseReceiptId": receipt_id,
        "releaseReceiptRef": receipt_ref,
        "releaseReceiptAuthority": HOSTED_AUTHORITY,
        "exitCode": exit_code,
        "dryRun": False,
        "postDeployChecks": post_checks,
        "postDeployFailures": [
            check["name"] for check in post_checks if check.get("status") == "failed"
        ],
        "rollbackPostChecks": rollback_post_checks,
        "sloReadback": receipt["sloReadback"],
        "rollback": rollback_report,
        "replayed": True,
        "projectionPurpose": "terminal-sealing-only",
        "sourceAuthority": HOSTED_AUTHORITY,
        "endedAt": receipt["verifiedAt"],
    }


def _project_check_summaries(
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "summary": check["name"],
            "exitCode": 0 if check["status"] == "passed" else 1,
            "receiptDigest": check["receiptDigest"],
            "sourceAuthority": HOSTED_AUTHORITY,
        }
        for check in checks
    ]


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = _load_json(args.manifest, "ReleaseEvidenceManifest")
        readback = _load_json(args.stage_readback, "hosted stage readback")
        payload = render(
            manifest=manifest,
            stage_readback=readback,
            stage=args.stage,
            service=args.service,
        )
        output = args.output.expanduser()
        if output.is_symlink():
            raise ValueError("hosted stage report output must not be a symlink")
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_hosted_release_stage_report: GATE_BLOCK: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
