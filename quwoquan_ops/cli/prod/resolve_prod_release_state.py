#!/usr/bin/env python3
"""Resolve the next Prod rollout action from the hosted release ledger only."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod import hosted_release_ledger


SERVICE = "prod-stack"
RESUME_STAGES = {"canary", "5", "20", "50", "100", "complete"}
_NEXT_STAGE = {
    "canary": "5",
    "5": "20",
    "20": "50",
    "50": "100",
    "100": "complete",
}
_STEP_BY_STAGE = {"canary": "0", "5": "5", "20": "20", "50": "50", "100": "100"}
_RECEIPT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")

_READBACK_FIELDS = {
    "schema",
    "authority",
    "state",
    "receipt",
    "receiptRef",
}
_STATE_FIELDS = set(hosted_release_ledger.STATE_FIELDS)
_RECEIPT_FIELDS = set(hosted_release_ledger.RECEIPT_FIELDS)


class GateBlockError(RuntimeError):
    """A fail-closed release-state resolution result."""


def _require_digest(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or hosted_release_ledger.SHA256_RE.fullmatch(value) is None
    ):
        raise GateBlockError(
            f"hosted release ledger {field} must be an immutable digest"
        )
    return value


def _require_non_empty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateBlockError(f"hosted release ledger {field} is missing")
    return value


def _receipt_id(receipt: dict[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate_post_checks(value: object) -> None:
    if not isinstance(value, list):
        raise GateBlockError("hosted release receipt postChecks must be a list")
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "name",
            "status",
            "receiptDigest",
        }:
            raise GateBlockError("hosted release receipt postChecks is incomplete")
        _require_non_empty_string(item.get("name"), field="postChecks.name")
        if item.get("status") not in {"passed", "failed"}:
            raise GateBlockError("hosted release receipt postChecks status is invalid")
        _require_digest(
            item.get("receiptDigest"),
            field="postChecks.receiptDigest",
        )


def _validate_hosted_readback(
    value: object,
) -> tuple[dict[str, str], dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != _READBACK_FIELDS:
        raise GateBlockError("hosted release ledger readback has a non-canonical shape")
    if value.get("schema") != hosted_release_ledger.READBACK_SCHEMA:
        raise GateBlockError("hosted release ledger readback schema is not canonical")
    if value.get("authority") != hosted_release_ledger.AUTHORITY:
        raise GateBlockError("hosted release ledger authority is invalid")

    state = value.get("state")
    receipt = value.get("receipt")
    if not state or not receipt:
        raise GateBlockError("hosted release ledger is empty or incomplete")
    if not isinstance(state, dict) or set(state) != _STATE_FIELDS:
        raise GateBlockError("hosted release ledger state has a non-canonical shape")
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise GateBlockError("hosted release receipt has a non-canonical shape")

    if (
        state.get("schema") != hosted_release_ledger.STATE_SCHEMA
        or state.get("authority") != hosted_release_ledger.AUTHORITY
        or state.get("service") != SERVICE
        or receipt.get("schema") != hosted_release_ledger.RECEIPT_SCHEMA
        or receipt.get("authority") != hosted_release_ledger.AUTHORITY
        or receipt.get("service") != SERVICE
    ):
        raise GateBlockError("hosted release ledger identity is invalid")

    stage = state.get("stage")
    trigger_stage = state.get("trigger_stage")
    decision = state.get("decision")
    rollback_outcome = state.get("rollback_outcome")
    if stage not in hosted_release_ledger.STAGES:
        raise GateBlockError("hosted release ledger stage is invalid")
    if trigger_stage not in hosted_release_ledger.STAGES:
        raise GateBlockError("hosted release ledger trigger stage is invalid")
    if state.get("step") != _STEP_BY_STAGE[stage]:
        raise GateBlockError("hosted release ledger stage step is invalid")
    if decision not in hosted_release_ledger.DECISIONS:
        raise GateBlockError("hosted release ledger decision is invalid")
    if rollback_outcome not in hosted_release_ledger.ROLLBACK_OUTCOMES:
        raise GateBlockError("hosted release ledger rollback outcome is invalid")
    expected_outcome = (
        decision
        if decision in {"rolled_back", "rollback_failed"}
        else "not_triggered"
    )
    if rollback_outcome != expected_outcome:
        raise GateBlockError("hosted release ledger decision/outcome binding is invalid")
    if decision == "rolled_back" and stage != "100":
        raise GateBlockError("hosted release ledger rollback is not terminal")

    digest_bindings = {
        "from_candidate_digest": "fromCandidateDigest",
        "to_candidate_digest": "toCandidateDigest",
        "artifact_digest": "artifactDigest",
        "image_digest": "imageDigest",
        "config_digest": "configDigest",
        "contract_graph_digest": "contractGraphDigest",
        "adapter_digest": "adapterDigest",
        "last_good_candidate_digest": "lastGoodCandidateDigest",
    }
    for state_field, receipt_field in digest_bindings.items():
        state_digest = _require_digest(state.get(state_field), field=state_field)
        receipt_digest = _require_digest(receipt.get(receipt_field), field=receipt_field)
        if state_digest != receipt_digest:
            raise GateBlockError(
                f"hosted release ledger {state_field} is not receipt-bound"
            )

    string_bindings = {
        "step": "step",
        "stage": "stage",
        "trigger_stage": "triggerStage",
        "from_release_evidence_ref": "fromReleaseEvidenceRef",
        "to_release_evidence_ref": "toReleaseEvidenceRef",
        "from_image_transport_tag": "fromImageTransportTag",
        "to_image_transport_tag": "toImageTransportTag",
        "decision": "decision",
        "rollback_outcome": "rollbackOutcome",
        "updated_at": "verifiedAt",
    }
    for state_field, receipt_field in string_bindings.items():
        state_value = _require_non_empty_string(
            state.get(state_field),
            field=state_field,
        )
        receipt_value = _require_non_empty_string(
            receipt.get(receipt_field),
            field=receipt_field,
        )
        if state_value != receipt_value:
            raise GateBlockError(
                f"hosted release ledger {state_field} is not receipt-bound"
            )

    for field in ("fromReleaseEvidenceRef", "toReleaseEvidenceRef"):
        if hosted_release_ledger.OCI_REF_RE.fullmatch(receipt[field]) is None:
            raise GateBlockError(f"hosted release receipt {field} is not immutable")
    for field in ("fromImageTransportTag", "toImageTransportTag"):
        if hosted_release_ledger.SAFE_VALUE_RE.fullmatch(receipt[field]) is None:
            raise GateBlockError(f"hosted release receipt {field} is unsafe")

    generation = state.get("generation")
    if (
        not isinstance(generation, str)
        or _POSITIVE_INTEGER_RE.fullmatch(generation) is None
    ):
        raise GateBlockError("hosted release ledger generation is invalid")
    expected_generation = receipt.get("expectedGeneration")
    committed_generation = receipt.get("committedGeneration")
    if (
        not isinstance(expected_generation, int)
        or isinstance(expected_generation, bool)
        or expected_generation < 0
        or not isinstance(committed_generation, int)
        or isinstance(committed_generation, bool)
        or committed_generation != expected_generation + 1
        or committed_generation != int(generation)
    ):
        raise GateBlockError("hosted release ledger generation is not receipt-bound")
    if not isinstance(receipt.get("sloReadback"), dict):
        raise GateBlockError("hosted release receipt sloReadback is incomplete")
    if decision == "continue":
        try:
            hosted_release_ledger.validate_promotion_evidence(
                receipt["sloReadback"].get("promotionEvidence"),
                candidate_id=receipt.get("toCandidateDigest"),
                artifact_digest=receipt.get("artifactDigest"),
                stage=receipt.get("triggerStage"),
            )
        except ValueError as error:
            raise GateBlockError(
                "hosted release receipt promotion evidence is invalid"
            ) from error
    _validate_post_checks(receipt.get("postChecks"))

    receipt_id = receipt.get("receiptId")
    if not isinstance(receipt_id, str) or _RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise GateBlockError("hosted release receipt identity is invalid")
    if (
        receipt_id != _receipt_id(receipt)
        or state.get("receipt_id") != receipt_id
        or value.get("receiptRef") != f"receipt:hosted:{receipt_id}"
    ):
        raise GateBlockError("hosted release receipt digest binding is invalid")

    for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values():
        history_receipt_id = state.get(field)
        if not isinstance(history_receipt_id, str) or (
            history_receipt_id
            and hosted_release_ledger.RECEIPT_ID_RE.fullmatch(history_receipt_id)
            is None
        ):
            raise GateBlockError(
                f"hosted release ledger {field} is not a canonical receipt id"
            )
    active_history_field = hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.get(
        state["trigger_stage"]
    )
    if (
        active_history_field is None
        or state[active_history_field] != receipt_id
    ):
        raise GateBlockError(
            "hosted release ledger current receipt is not bound to trigger stage"
        )

    if decision == "continue" and stage == "100":
        if state["last_good_candidate_digest"] != state["to_candidate_digest"]:
            raise GateBlockError("hosted 100 release is not marked stable")
    elif decision in {"continue", "pause"}:
        if state["last_good_candidate_digest"] != state["from_candidate_digest"]:
            raise GateBlockError("hosted in-progress release lost its stable base")
    elif decision == "rolled_back":
        if state["last_good_candidate_digest"] != state["to_candidate_digest"]:
            raise GateBlockError("hosted rollback did not restore a stable candidate")
    elif decision == "rollback_failed":
        if state["last_good_candidate_digest"] != state["from_candidate_digest"]:
            raise GateBlockError("hosted rollback failure lost its stable base")

    return dict(state), dict(receipt)


def resolve_release_state(
    readback: object,
    *,
    to_candidate_digest: str,
) -> dict[str, str]:
    requested_target = _require_digest(
        to_candidate_digest,
        field="toCandidateDigest",
    )
    state, _ = _validate_hosted_readback(readback)
    decision = state["decision"]

    # A runner may disappear after the hosted authority has durably committed
    # rollback terminal state but before local lifecycle files are written. In
    # that case the only safe recovery is to seal the existing transaction; a
    # retry of the failed candidate would be a new Prod write, not idempotence.
    if (
        decision == "rolled_back"
        and state["from_candidate_digest"] == requested_target
    ):
        return {
            "fromCandidateDigest": state["to_candidate_digest"],
            "resumeStage": "complete",
            "authority": hosted_release_ledger.AUTHORITY,
        }
    if decision == "rollback_failed":
        if state["to_candidate_digest"] == requested_target:
            return {
                "fromCandidateDigest": state["last_good_candidate_digest"],
                "resumeStage": "complete",
                "authority": hosted_release_ledger.AUTHORITY,
            }
        raise GateBlockError("hosted release ledger records rollback_failed")

    current_target = state["to_candidate_digest"]
    if current_target == requested_target:
        if decision == "pause":
            resume_stage = state["stage"]
        elif decision == "continue":
            resume_stage = _NEXT_STAGE[state["stage"]]
        elif decision == "rolled_back":
            # The stable target was restored, but the rollback receipt belongs
            # to the failed candidate artifact. Re-run the restored candidate
            # as a fresh no-op transaction so it can produce its own complete
            # candidate-bound rollout evidence.
            resume_stage = "canary"
        else:
            raise GateBlockError("hosted release ledger target is not resumable")
        from_candidate_digest = (
            current_target
            if decision == "rolled_back"
            else state["from_candidate_digest"]
        )
    else:
        stable_boundary = (
            state["stage"] == "100"
            and decision in {"continue", "rolled_back"}
            and state["last_good_candidate_digest"] == current_target
        )
        if not stable_boundary:
            raise GateBlockError(
                "a different target requires a stable 100 or rolled_back ledger"
            )
        from_candidate_digest = current_target
        resume_stage = "canary"

    if resume_stage not in RESUME_STAGES:
        raise GateBlockError("hosted release ledger produced an invalid resume stage")
    return {
        "fromCandidateDigest": from_candidate_digest,
        "resumeStage": resume_stage,
        "authority": hosted_release_ledger.AUTHORITY,
    }


def _fetch_hosted_readback() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="qwq-prod-release-state-") as temporary:
        output = Path(temporary) / "readback.json"
        result = subprocess.run(
            [
                "bash",
                "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh",
                "--plane",
                "service",
                "--operation",
                "release-ledger-fetch",
                "--service",
                SERVICE,
                "--output-path",
                str(output),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise GateBlockError(f"hosted release ledger fetch failed: {detail}")
        try:
            readback = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise GateBlockError(
                "hosted release ledger returned non-canonical JSON"
            ) from error
    if not isinstance(readback, dict):
        raise GateBlockError("hosted release ledger readback must be an object")
    return readback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve Prod recovery exclusively from the hosted release ledger.",
    )
    parser.add_argument("--to-candidate-digest", required=True)
    parser.add_argument("--output-format", choices=("json", "shell"), default="json")
    parser.add_argument(
        "--readback-output",
        type=Path,
        help="Optional disposable copy of the validated hosted readback",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        readback = _fetch_hosted_readback()
        payload = resolve_release_state(
            readback,
            to_candidate_digest=args.to_candidate_digest,
        )
        if args.readback_output is not None:
            output = args.readback_output.expanduser()
            if output.is_symlink():
                raise GateBlockError("hosted readback output must not be a symlink")
            output = output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(readback, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
    except (GateBlockError, OSError, ValueError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    if args.output_format == "shell":
        print(
            "RESOLVED_FROM_CANDIDATE_DIGEST="
            + shlex.quote(payload["fromCandidateDigest"])
        )
        print("RESOLVED_RESUME_STAGE=" + shlex.quote(payload["resumeStage"]))
        print("RESOLVED_HOSTED_AUTHORITY=" + shlex.quote(payload["authority"]))
    else:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
