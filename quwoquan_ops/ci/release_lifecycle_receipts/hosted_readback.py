"""hosted release ledger 回读（receipt/soak/ledger readback）的校验。

原单文件 ``render_release_lifecycle_receipts.py`` 拆分出的回读校验子模块。
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import DIGEST_PATTERN

from .constants import (
    HOSTED_AUTHORITY,
    HOSTED_READBACK_SCHEMA,
    HOSTED_RECEIPT_FIELDS,
    HOSTED_RECEIPT_READBACK_SCHEMA,
    HOSTED_RECEIPT_SCHEMA,
    HOSTED_SOAK_READBACK_SCHEMA,
    HOSTED_SOAK_RECEIPT_SCHEMA,
    HOSTED_STATE_FIELDS,
    HOSTED_STATE_SCHEMA,
    RECEIPT_ID_PATTERN,
    STAGES,
)
from .receipt_codec import _receipt_id, _validate_timestamp


def _validate_hosted_receipt(value: Any, *, service: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != HOSTED_RECEIPT_FIELDS:
        raise ValueError("hosted release receipt shape is not canonical")
    receipt_id = str(value.get("receiptId") or "")
    if (
        value.get("schema") != HOSTED_RECEIPT_SCHEMA
        or value.get("authority") != HOSTED_AUTHORITY
        or value.get("service") != service
        or RECEIPT_ID_PATTERN.fullmatch(receipt_id) is None
        or _receipt_id(value) != receipt_id
    ):
        raise ValueError("hosted release receipt identity is invalid")
    for field in (
        "fromCandidateDigest",
        "toCandidateDigest",
        "artifactDigest",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
    ):
        if DIGEST_PATTERN.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"hosted release receipt {field} is not immutable")
    if value.get("stage") not in STAGES:
        raise ValueError("hosted release receipt stage is invalid")
    if value.get("triggerStage") not in STAGES:
        raise ValueError("hosted release receipt triggerStage is invalid")
    for field in ("fromReleaseEvidenceRef", "toReleaseEvidenceRef"):
        ref = str(value.get(field) or "")
        if re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}", ref) is None:
            raise ValueError(f"hosted release receipt {field} is not exact OCI")
    for field in ("fromImageTransportTag", "toImageTransportTag"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f"hosted release receipt {field} is missing")
    if value.get("decision") not in {
        "continue",
        "pause",
        "rolled_back",
        "rollback_failed",
    }:
        raise ValueError("hosted release receipt decision is invalid")
    if value.get("rollbackOutcome") not in {
        "not_triggered",
        "rolled_back",
        "rollback_failed",
    }:
        raise ValueError("hosted release receipt rollback outcome is invalid")
    if (
        not isinstance(value.get("expectedGeneration"), int)
        or not isinstance(value.get("committedGeneration"), int)
        or value["expectedGeneration"] < 0
        or value["committedGeneration"] != value["expectedGeneration"] + 1
        or not isinstance(value.get("sloReadback"), dict)
    ):
        raise ValueError("hosted release receipt generation or SLO evidence is invalid")
    if service == "prod-stack" and value.get("decision") == "continue":
        hosted_release_ledger.validate_promotion_evidence(
            value["sloReadback"].get("promotionEvidence"),
            candidate_id=value.get("toCandidateDigest"),
            artifact_digest=value.get("artifactDigest"),
            stage=value.get("triggerStage"),
        )
    post_checks = value.get("postChecks")
    if not isinstance(post_checks, list) or not all(
        isinstance(item, dict)
        and set(item) == {"name", "status", "receiptDigest"}
        and isinstance(item.get("name"), str)
        and bool(item["name"])
        and item.get("status") in {"passed", "failed"}
        and DIGEST_PATTERN.fullmatch(str(item.get("receiptDigest") or ""))
        is not None
        for item in post_checks
    ):
        raise ValueError("hosted release receipt post-check evidence is invalid")
    _validate_timestamp(value.get("verifiedAt"), "hosted release receipt")
    return value


def _validate_receipt_readback(
    payload: dict[str, Any], *, service: str
) -> dict[str, Any]:
    if (
        set(payload) != {"schema", "authority", "receipt", "receiptRef"}
        or payload.get("schema") != HOSTED_RECEIPT_READBACK_SCHEMA
        or payload.get("authority") != HOSTED_AUTHORITY
    ):
        raise ValueError("hosted receipt readback shape is invalid")
    receipt = _validate_hosted_receipt(payload.get("receipt"), service=service)
    if payload.get("receiptRef") != f"receipt:hosted:{receipt['receiptId']}":
        raise ValueError("hosted receipt readback reference is invalid")
    return receipt


def _validate_soak_readback(
    payload: dict[str, Any], *, service: str
) -> dict[str, Any]:
    if (
        set(payload) != {"schema", "authority", "receipt", "receiptRef"}
        or payload.get("schema") != HOSTED_SOAK_READBACK_SCHEMA
        or payload.get("authority") != HOSTED_AUTHORITY
    ):
        raise ValueError("hosted prod soak readback shape is invalid")
    receipt = payload.get("receipt")
    if (
        not isinstance(receipt, dict)
        or set(receipt) != hosted_release_ledger.SOAK_RECEIPT_FIELDS
        or receipt.get("schema") != HOSTED_SOAK_RECEIPT_SCHEMA
        or receipt.get("authority") != HOSTED_AUTHORITY
        or receipt.get("service") != service
        or RECEIPT_ID_PATTERN.fullmatch(str(receipt.get("receiptId") or "")) is None
        or _receipt_id(receipt) != receipt.get("receiptId")
        or payload.get("receiptRef")
        != f"receipt:hosted-soak:{receipt.get('receiptId')}"
    ):
        raise ValueError("hosted prod soak receipt identity is invalid")
    request = {
        field: receipt[field]
        for field in hosted_release_ledger.SOAK_REQUEST_FIELDS
        if field != "schema"
    }
    request["schema"] = hosted_release_ledger.SOAK_REQUEST_SCHEMA
    hosted_release_ledger._validate_soak_request(request)
    started_at = dt.datetime.fromisoformat(
        _validate_timestamp(receipt.get("soakStartedAt"), "prod soak start").replace(
            "Z", "+00:00"
        )
    )
    ended_at = dt.datetime.fromisoformat(
        _validate_timestamp(receipt.get("soakEndedAt"), "prod soak end").replace(
            "Z", "+00:00"
        )
    )
    verified_at = dt.datetime.fromisoformat(
        _validate_timestamp(receipt.get("verifiedAt"), "prod soak receipt").replace(
            "Z", "+00:00"
        )
    )
    duration = receipt.get("soakDurationSeconds")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration != int((ended_at - started_at).total_seconds())
        or duration < receipt["requiredSoakSeconds"]
        or ended_at > verified_at
    ):
        raise ValueError("hosted prod soak receipt duration is invalid")
    return receipt


def _validate_ledger_readback(
    payload: dict[str, Any], *, service: str
) -> dict[str, Any]:
    if (
        set(payload) != {"schema", "authority", "state", "receipt", "receiptRef"}
        or payload.get("schema") != HOSTED_READBACK_SCHEMA
        or payload.get("authority") != HOSTED_AUTHORITY
        or not isinstance(payload.get("state"), dict)
    ):
        raise ValueError("hosted ledger readback shape is invalid")
    state = payload["state"]
    receipt = _validate_hosted_receipt(payload.get("receipt"), service=service)
    history_is_invalid = any(
        not isinstance(state.get(field), str)
        or (
            bool(state.get(field))
            and RECEIPT_ID_PATTERN.fullmatch(str(state[field])) is None
        )
        for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values()
    )
    active_history_field = hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.get(
        str(state.get("trigger_stage") or "")
    )
    if (
        set(state) != HOSTED_STATE_FIELDS
        or state.get("schema") != HOSTED_STATE_SCHEMA
        or state.get("authority") != HOSTED_AUTHORITY
        or state.get("service") != service
        or state.get("receipt_id") != receipt["receiptId"]
        or payload.get("receiptRef") != f"receipt:hosted:{receipt['receiptId']}"
        or str(receipt["committedGeneration"]) != state.get("generation")
        or receipt["fromCandidateDigest"] != state.get("from_candidate_digest")
        or receipt["toCandidateDigest"] != state.get("to_candidate_digest")
        or receipt["artifactDigest"] != state.get("artifact_digest")
        or receipt["rollbackOutcome"] != state.get("rollback_outcome")
        or receipt["triggerStage"] != state.get("trigger_stage")
        or receipt["fromReleaseEvidenceRef"]
        != state.get("from_release_evidence_ref")
        or receipt["toReleaseEvidenceRef"] != state.get("to_release_evidence_ref")
        or receipt["fromImageTransportTag"]
        != state.get("from_image_transport_tag")
        or receipt["toImageTransportTag"] != state.get("to_image_transport_tag")
        or receipt["lastGoodCandidateDigest"]
        != state.get("last_good_candidate_digest")
        or history_is_invalid
        or active_history_field is None
        or state.get(active_history_field) != receipt["receiptId"]
    ):
        raise ValueError("hosted ledger state and receipt binding is invalid")
    return receipt
