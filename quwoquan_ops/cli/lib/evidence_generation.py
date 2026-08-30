"""Canonical generation envelope for stackctl evidence reports.

The envelope links each consumer report to one immutable candidate and, where
available, one startup receipt and one exact upstream report byte sequence.
Unexecuted layers are explicit typed facts; empty strings never claim evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA = "stackctl-evidence-generation-envelope"
STATUSES = frozenset({"executed", "not_executed", "not_applicable"})
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _typed(status: str, value: object = None, *, reason: str = "") -> dict[str, Any]:
    normalized = str(status or "").strip()
    if normalized not in STATUSES:
        raise ValueError(f"evidence generation status is invalid: {normalized}")
    payload: dict[str, Any] = {"status": normalized}
    if normalized == "executed":
        if value in (None, ""):
            raise ValueError("executed evidence generation value is required")
        payload["value"] = value
    else:
        if not str(reason or "").strip():
            raise ValueError(f"{normalized} evidence generation reason is required")
        payload["reason"] = str(reason).strip()
    return payload


def _candidate_digest(snapshot: Mapping[str, Any] | None) -> str:
    if not isinstance(snapshot, Mapping):
        return ""
    return str(snapshot.get("baselineId") or "").strip()


def _startup_attempt_id(receipt: Mapping[str, Any] | None) -> str:
    if not isinstance(receipt, Mapping):
        return ""
    return str(receipt.get("attemptId") or "").strip()


def build_evidence_generation_envelope(
    *,
    command: str,
    candidate_snapshot: Mapping[str, Any] | None = None,
    startup_receipt: Mapping[str, Any] | None = None,
    upstream_report: Path | None = None,
    startup_status: str | None = None,
    startup_reason: str = "",
    upstream_status: str | None = None,
    upstream_reason: str = "",
) -> dict[str, Any]:
    command_name = str(command or "").strip()
    if not command_name:
        raise ValueError("evidence generation command is required")
    candidate_digest = _candidate_digest(candidate_snapshot)
    if candidate_digest and _DIGEST.fullmatch(candidate_digest) is None:
        raise ValueError("evidence generation candidate digest is invalid")

    attempt_id = _startup_attempt_id(startup_receipt)
    resolved_startup_status = startup_status or (
        "executed" if attempt_id else "not_executed"
    )
    if resolved_startup_status == "executed":
        startup_attempt = _typed("executed", attempt_id)
    else:
        startup_attempt = _typed(
            resolved_startup_status,
            reason=startup_reason or "startup was not executed by this evidence layer",
        )

    report_path = upstream_report.resolve() if upstream_report is not None else None
    resolved_upstream_status = upstream_status or (
        "executed" if report_path is not None else "not_applicable"
    )
    if resolved_upstream_status == "executed":
        if report_path is None or not report_path.is_file() or report_path.is_symlink():
            raise ValueError("executed upstream report must be one regular file")
        upstream = _typed(
            "executed",
            {"ref": str(report_path), "digest": sha256_file(report_path)},
        )
    else:
        upstream = _typed(
            resolved_upstream_status,
            reason=upstream_reason or "this evidence layer has no upstream report",
        )

    generation_payload = {
        "command": command_name,
        "candidateDigest": candidate_digest or "not_applicable",
        "startupAttempt": startup_attempt,
        "upstreamReport": upstream,
    }
    generation = "sha256:" + hashlib.sha256(
        json.dumps(
            generation_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "generation": generation,
        "candidateDigest": (
            _typed("executed", candidate_digest)
            if candidate_digest
            else _typed(
                "not_applicable",
                reason="this evidence layer is not bound to an immutable candidate",
            )
        ),
        "startupAttemptId": startup_attempt,
        "upstreamReport": upstream,
    }


def validate_evidence_generation_envelope(
    value: object,
    *,
    expected_candidate_digest: str = "",
    expected_startup_attempt_id: str = "",
    verify_upstream: bool = True,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "generation",
        "candidateDigest",
        "startupAttemptId",
        "upstreamReport",
    }:
        raise ValueError("evidence generation envelope fields mismatch")
    if value.get("schema") != SCHEMA or _DIGEST.fullmatch(
        str(value.get("generation") or "")
    ) is None:
        raise ValueError("evidence generation envelope identity is invalid")

    for field in ("candidateDigest", "startupAttemptId", "upstreamReport"):
        typed = value.get(field)
        if not isinstance(typed, dict) or typed.get("status") not in STATUSES:
            raise ValueError(f"evidence generation {field} status is invalid")
        if typed["status"] == "executed":
            if set(typed) != {"status", "value"} or typed.get("value") in (None, ""):
                raise ValueError(f"evidence generation {field} executed value is invalid")
        elif set(typed) != {"status", "reason"} or not str(typed.get("reason") or ""):
            raise ValueError(f"evidence generation {field} typed absence is invalid")

    candidate = value["candidateDigest"]
    if candidate["status"] == "executed" and _DIGEST.fullmatch(
        str(candidate["value"] or "")
    ) is None:
        raise ValueError("evidence generation candidate digest is invalid")
    if expected_candidate_digest and candidate != _typed(
        "executed", expected_candidate_digest
    ):
        raise ValueError("evidence generation candidate mismatch")

    startup = value["startupAttemptId"]
    if expected_startup_attempt_id and startup != _typed(
        "executed", expected_startup_attempt_id
    ):
        raise ValueError("evidence generation startup attempt mismatch")

    upstream = value["upstreamReport"]
    if verify_upstream and upstream["status"] == "executed":
        descriptor = upstream.get("value")
        if not isinstance(descriptor, dict) or set(descriptor) != {"ref", "digest"}:
            raise ValueError("evidence generation upstream report identity is invalid")
        path = Path(str(descriptor.get("ref") or ""))
        if (
            _DIGEST.fullmatch(str(descriptor.get("digest") or "")) is None
            or not path.is_absolute()
            or not path.is_file()
            or path.is_symlink()
            or sha256_file(path) != descriptor["digest"]
        ):
            raise ValueError("evidence generation upstream report is stale")
    return value
