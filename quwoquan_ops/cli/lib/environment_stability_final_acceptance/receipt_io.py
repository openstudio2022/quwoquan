"""typed receipt 载入、摘要与通用校验原语（自原单文件逐字搬移）。"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (
    LoadedReceipt,
    MAX_FUTURE_SKEW_SECONDS,
    _Evaluation,
    _FORBIDDEN_INPUT_NAMES,
    _SELF_AUTHORITY_FIELDS,
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _load_receipt(
    evaluation: _Evaluation,
    *,
    label: str,
    path: Path | None,
) -> LoadedReceipt | None:
    if path is None or not str(path).strip():
        evaluation.block("MISSING_INPUT", label, "required typed JSON receipt is missing")
        return None
    candidate = Path(path).expanduser()
    if (
        candidate.suffix.lower() != ".json"
        or candidate.name.lower() in _FORBIDDEN_INPUT_NAMES
        or "todo" in candidate.name.lower()
    ):
        evaluation.block(
            "UNSUPPORTED_INPUT",
            label,
            "Markdown, Todo and VERDICT inputs are not accepted",
        )
        return None
    try:
        if candidate.is_symlink():
            raise OSError("symbolic links are not accepted")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("not a regular file")
        raw = resolved.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        evaluation.block("UNREADABLE_INPUT", label, f"typed JSON is unreadable: {exc}")
        return None
    if not isinstance(payload, dict):
        evaluation.block("SCHEMA_MISMATCH", label, "typed receipt root must be an object")
        return None
    return LoadedReceipt(label, resolved, payload, _sha256(raw))


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _reject_self_asserted_authority(
    evaluation: _Evaluation,
    receipt: LoadedReceipt,
    *,
    allow_prod_sim_non_promotable: bool = False,
) -> None:
    for key, value in _walk(receipt.payload):
        normalized = key.replace("_", "").lower()
        text = str(value or "").strip().lower() if isinstance(value, str) else ""
        if normalized in _SELF_AUTHORITY_FIELDS:
            evaluation.block(
                "UNVERIFIABLE_AUTHORITY",
                receipt.label,
                f"self-described authority field {key!r} is not trusted",
            )
        if (
            text.startswith(("hmac-sha256:", "local-sha256:"))
            or normalized in {"attestationauthority", "authority"}
            and text in {"local", "local-hmac", "developer", "workstation"}
        ):
            evaluation.block(
                "LOCAL_ATTESTATION",
                receipt.label,
                "local or self-calculated attestation cannot establish authority",
            )
        if normalized == "expectedskip" and value is True:
            evaluation.block(
                "EXPECTED_SKIP",
                receipt.label,
                "expected skip cannot qualify final acceptance",
            )
        non_promotable = (
            normalized == "promotable" and value is False
        ) or (
            normalized == "nonpromotable" and value is True
        ) or (
            normalized in {"status", "verdict"} and text == "gate_block"
        )
        if non_promotable and not allow_prod_sim_non_promotable:
            evaluation.block(
                "NON_PROMOTABLE",
                receipt.label,
                "non-promotable evidence cannot qualify final acceptance",
            )


def _timestamp(
    evaluation: _Evaluation,
    receipt: LoadedReceipt,
    fields: Sequence[str],
    *,
    now: datetime,
    max_age_seconds: int | None,
) -> str:
    raw = next(
        (
            receipt.payload.get(field)
            for field in fields
            if isinstance(receipt.payload.get(field), str)
            and str(receipt.payload[field]).strip()
        ),
        "",
    )
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone is required")
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        evaluation.block(
            "STALE_EVIDENCE",
            receipt.label,
            "authoritative timestamp is missing or invalid",
        )
        return ""
    age = (now - parsed).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or (
        max_age_seconds is not None and age > max_age_seconds
    ):
        freshness = (
            f"the {max_age_seconds}-second freshness window"
            if max_age_seconds is not None
            else "the accepted timestamp range"
        )
        evaluation.block(
            "STALE_EVIDENCE",
            receipt.label,
            f"receipt is outside {freshness}",
        )
    normalized = parsed.isoformat().replace("+00:00", "Z")
    evaluation.observed_at[receipt.label] = normalized
    return normalized


def _schema(
    evaluation: _Evaluation,
    receipt: LoadedReceipt,
    expected: str,
) -> bool:
    if receipt.payload.get("schema") != expected:
        evaluation.block(
            "SCHEMA_MISMATCH",
            receipt.label,
            f"expected schema {expected!r}",
        )
        return False
    return True


def _passed(evaluation: _Evaluation, receipt: LoadedReceipt) -> bool:
    if receipt.payload.get("status") != "passed":
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "receipt status must be exactly 'passed'",
        )
        return False
    return True


def _resolve_artifact_root(
    evaluation: _Evaluation,
    configured: Path | None,
) -> Path | None:
    if configured is None or not str(configured).strip():
        evaluation.block(
            "MISSING_INPUT",
            "artifact_root",
            "canonical ReleaseEvidenceManifest artifact root is required",
        )
        return None
    try:
        candidate = Path(configured).expanduser()
        if candidate.is_symlink():
            raise OSError("symbolic links are not accepted")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            raise OSError("artifact root is not a directory")
        return resolved
    except OSError as exc:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "artifact_root",
            f"artifact root is unavailable: {exc}",
        )
        return None
