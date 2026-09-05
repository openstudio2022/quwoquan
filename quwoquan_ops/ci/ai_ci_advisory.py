#!/usr/bin/env python3
"""Validate and materialize read-only AI CI/CD advisory evidence.

This module deliberately does not call a model, redact source content, or mutate
CI/CD state.  It only validates the digest-bound evidence and redaction receipts
provided by an external, least-privilege shadow analysis job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


CANONICAL_SCHEMA = "ai-ci-advisory"
CODE_HEALTH_SOURCE_KIND = "code-health-delta"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
WORKFLOW_RUN_ID = re.compile(r"^[1-9][0-9]{0,19}$")
EVIDENCE_KIND = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
READ_ONLY_SOURCE_REF = re.compile(
    r"^(?:github-actions|hosted-ledger|oci|repo)://"
    r"[A-Za-z0-9][A-Za-z0-9._/@:+-]{2,2047}$"
)
MODEL_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@+:-]{1,127}$")
SOURCE_EVIDENCE_FIELDS = frozenset(
    {
        "kind",
        "sourceRef",
        "sourceDigest",
        "modelInputDigest",
        "sourceGitSha",
        "workflowRunId",
    }
)
REDACTION_RECEIPT_FIELDS = frozenset(
    {
        "sourceDigest",
        "modelInputDigest",
        "policyDigest",
        "scanDigest",
        "redactedValueCount",
        "residualSensitiveValueCount",
        "receiptDigest",
    }
)
FORBIDDEN_CONTROL_KEYS = frozenset(
    {
        "conclusion",
        "deployDecision",
        "exitCode",
        "gateResult",
        "gateStatus",
        "promotionDecision",
        "rollbackDecision",
        "shouldPromote",
        "shouldRollback",
    }
)
FORBIDDEN_SECRET_KEY_PARTS = (
    "authorization",
    "credential",
    "password",
    "privatekey",
    "secret",
    "token",
)
FORBIDDEN_VERSION_FIELDS = frozenset(
    {"contractVersion", "registryRevision", "schemaVersion", "version", "versions"}
)
NORMALIZED_FORBIDDEN_CONTROL_KEYS = frozenset(
    key.lower().replace("_", "").replace("-", "")
    for key in FORBIDDEN_CONTROL_KEYS
)
NORMALIZED_FORBIDDEN_VERSION_FIELDS = frozenset(
    key.lower().replace("_", "").replace("-", "")
    for key in FORBIDDEN_VERSION_FIELDS
)
FORBIDDEN_SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
        r"AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
    ),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"client[_-]?secret|password)\s*[:=]\s*[\"']?"
        r"[A-Za-z0-9._~+/-]{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"https?://[^/\s:@]+:[^@\s/]+@", re.IGNORECASE),
)


class AdvisoryContractError(ValueError):
    """Raised when an advisory attempts to escape its read-only boundary."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_digest(value: Any) -> str:
    """Digest a JSON value with the canonical serialization used by receipts."""
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _walk(value: Any, *, location: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise AdvisoryContractError(
                    f"AI advisory field name must be a string at {location}"
                )
            key = raw_key
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in NORMALIZED_FORBIDDEN_CONTROL_KEYS:
                raise AdvisoryContractError(
                    f"AI advisory cannot own CI/CD control field {location}.{key}"
                )
            if normalized in NORMALIZED_FORBIDDEN_VERSION_FIELDS:
                raise AdvisoryContractError(
                    f"AI advisory cannot carry contract version field {location}.{key}"
                )
            if any(part in normalized for part in FORBIDDEN_SECRET_KEY_PARTS):
                raise AdvisoryContractError(
                    f"AI advisory cannot contain secret-bearing field {location}.{key}"
                )
            _walk(nested, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _walk(nested, location=f"{location}[{index}]")
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in FORBIDDEN_SECRET_VALUE_PATTERNS):
            raise AdvisoryContractError(
                f"AI advisory contains secret-like material at {location}"
            )


def _require_digest(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise AdvisoryContractError(f"{field} must be a sha256 digest")
    return value


def _canonical_source_evidence(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AdvisoryContractError("sourceEvidence must be a non-empty list")

    canonical: list[dict[str, str]] = []
    source_refs: set[str] = set()
    digest_bindings: set[tuple[str, str]] = set()
    expected_git_sha: str | None = None
    expected_workflow_run_id: str | None = None
    for index, item in enumerate(value):
        label = f"sourceEvidence[{index}]"
        if not isinstance(item, Mapping) or set(item) != SOURCE_EVIDENCE_FIELDS:
            raise AdvisoryContractError(
                f"{label} must use the canonical digest-bound evidence shape"
            )
        kind = item.get("kind")
        source_ref = item.get("sourceRef")
        source_git_sha = item.get("sourceGitSha")
        workflow_run_id = item.get("workflowRunId")
        if not isinstance(kind, str) or EVIDENCE_KIND.fullmatch(kind) is None:
            raise AdvisoryContractError(f"{label}.kind is invalid")
        if (
            not isinstance(source_ref, str)
            or READ_ONLY_SOURCE_REF.fullmatch(source_ref) is None
        ):
            raise AdvisoryContractError(
                f"{label}.sourceRef must be an immutable read-only evidence reference"
            )
        if (
            not isinstance(source_git_sha, str)
            or GIT_SHA.fullmatch(source_git_sha) is None
        ):
            raise AdvisoryContractError(
                f"{label}.sourceGitSha must be a full immutable Git SHA"
            )
        if (
            not isinstance(workflow_run_id, str)
            or WORKFLOW_RUN_ID.fullmatch(workflow_run_id) is None
        ):
            raise AdvisoryContractError(f"{label}.workflowRunId is invalid")
        source_digest = _require_digest(
            item.get("sourceDigest"), field=f"{label}.sourceDigest"
        )
        model_input_digest = _require_digest(
            item.get("modelInputDigest"), field=f"{label}.modelInputDigest"
        )
        if not source_ref.endswith("@" + source_digest):
            raise AdvisoryContractError(
                f"{label}.sourceRef must bind its exact sourceDigest"
            )
        if source_ref in source_refs:
            raise AdvisoryContractError(f"{label}.sourceRef is duplicated")
        binding = (source_digest, model_input_digest)
        if binding in digest_bindings:
            raise AdvisoryContractError(f"{label} duplicates a digest binding")
        if expected_git_sha is None:
            expected_git_sha = source_git_sha
            expected_workflow_run_id = workflow_run_id
        elif (
            source_git_sha != expected_git_sha
            or workflow_run_id != expected_workflow_run_id
        ):
            raise AdvisoryContractError(
                "all sourceEvidence entries must bind the same Git SHA and workflow run"
            )
        source_refs.add(source_ref)
        digest_bindings.add(binding)
        canonical.append(
            {
                "kind": kind,
                "sourceRef": source_ref,
                "sourceDigest": source_digest,
                "modelInputDigest": model_input_digest,
                "sourceGitSha": source_git_sha,
                "workflowRunId": workflow_run_id,
            }
        )
    code_health = [item for item in canonical if item["kind"] == CODE_HEALTH_SOURCE_KIND]
    if len(code_health) > 1:
        raise AdvisoryContractError("code-health-delta sourceEvidence may appear at most once")
    return canonical


def _canonical_redaction_receipts(
    value: Any,
    *,
    source_evidence: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise AdvisoryContractError(
            "redactions must contain one digest-bound receipt per source evidence"
        )

    expected_bindings = {
        (item["sourceDigest"], item["modelInputDigest"])
        for item in source_evidence
    }
    actual_bindings: set[tuple[str, str]] = set()
    canonical: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        label = f"redactions[{index}]"
        if not isinstance(item, Mapping) or set(item) != REDACTION_RECEIPT_FIELDS:
            raise AdvisoryContractError(
                f"{label} must use the canonical redaction receipt shape"
            )
        source_digest = _require_digest(
            item.get("sourceDigest"), field=f"{label}.sourceDigest"
        )
        model_input_digest = _require_digest(
            item.get("modelInputDigest"), field=f"{label}.modelInputDigest"
        )
        policy_digest = _require_digest(
            item.get("policyDigest"), field=f"{label}.policyDigest"
        )
        scan_digest = _require_digest(
            item.get("scanDigest"), field=f"{label}.scanDigest"
        )
        receipt_digest = _require_digest(
            item.get("receiptDigest"), field=f"{label}.receiptDigest"
        )
        redacted_value_count = item.get("redactedValueCount")
        residual_sensitive_value_count = item.get("residualSensitiveValueCount")
        if (
            isinstance(redacted_value_count, bool)
            or not isinstance(redacted_value_count, int)
            or redacted_value_count < 0
        ):
            raise AdvisoryContractError(
                f"{label}.redactedValueCount must be a non-negative integer"
            )
        if residual_sensitive_value_count != 0 or isinstance(
            residual_sensitive_value_count, bool
        ):
            raise AdvisoryContractError(
                f"{label}.residualSensitiveValueCount must be the integer zero"
            )
        if redacted_value_count == 0 and source_digest != model_input_digest:
            raise AdvisoryContractError(
                f"{label} changed evidence but declares no redacted values"
            )
        if redacted_value_count > 0 and source_digest == model_input_digest:
            raise AdvisoryContractError(
                f"{label} declares redaction without a changed model input digest"
            )

        unsigned = {
            "sourceDigest": source_digest,
            "modelInputDigest": model_input_digest,
            "policyDigest": policy_digest,
            "scanDigest": scan_digest,
            "redactedValueCount": redacted_value_count,
            "residualSensitiveValueCount": residual_sensitive_value_count,
        }
        if canonical_digest(unsigned) != receipt_digest:
            raise AdvisoryContractError(
                f"{label}.receiptDigest does not match its body"
            )
        binding = (source_digest, model_input_digest)
        if binding in actual_bindings:
            raise AdvisoryContractError(f"{label} duplicates a source evidence receipt")
        actual_bindings.add(binding)
        canonical.append({**unsigned, "receiptDigest": receipt_digest})

    if actual_bindings != expected_bindings:
        raise AdvisoryContractError(
            "redactions must bind exactly every sourceEvidence digest pair"
        )
    return canonical


def canonical_advisory(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated canonical advisory without accepting legacy shapes."""
    _walk(payload)
    allowed = {
        "sourceEvidence",
        "modelIdentity",
        "promptDigest",
        "findings",
        "confidence",
        "suggestedActions",
        "redactions",
    }
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        raise AdvisoryContractError(
            "AI advisory input contains unsupported fields: " + ", ".join(unexpected)
        )
    missing = sorted(allowed - set(payload))
    if missing:
        raise AdvisoryContractError(
            "AI advisory input is missing fields: " + ", ".join(missing)
        )

    source_evidence = _canonical_source_evidence(payload["sourceEvidence"])
    findings = payload["findings"]
    suggested_actions = payload["suggestedActions"]
    redactions = _canonical_redaction_receipts(
        payload["redactions"], source_evidence=source_evidence
    )
    model_identity = payload["modelIdentity"]
    prompt_digest = payload["promptDigest"]
    confidence = payload["confidence"]

    if not isinstance(findings, list):
        raise AdvisoryContractError("findings must be a list")
    if not isinstance(suggested_actions, list) or not all(
        isinstance(item, str) and item.strip() for item in suggested_actions
    ):
        raise AdvisoryContractError("suggestedActions must contain non-empty strings")
    if (
        not isinstance(model_identity, str)
        or MODEL_IDENTITY.fullmatch(model_identity.strip()) is None
    ):
        raise AdvisoryContractError("modelIdentity is invalid")
    if not isinstance(prompt_digest, str) or SHA256.fullmatch(prompt_digest) is None:
        raise AdvisoryContractError("promptDigest must be a sha256 digest")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise AdvisoryContractError("confidence must be a number from 0 to 1")
    if not 0 <= float(confidence) <= 1:
        raise AdvisoryContractError("confidence must be a number from 0 to 1")

    body = {
        "sourceEvidence": source_evidence,
        "modelIdentity": model_identity.strip(),
        "promptDigest": prompt_digest,
        "findings": findings,
        "confidence": float(confidence),
        "suggestedActions": [item.strip() for item in suggested_actions],
        "redactions": redactions,
    }
    return {
        "schema": CANONICAL_SCHEMA,
        "generatedAt": utc_now(),
        **body,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="AI advisory draft JSON")
    parser.add_argument("--output", required=True, help="Canonical advisory JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise AdvisoryContractError("AI advisory input must be a JSON object")
        advisory = canonical_advisory(raw)
    except (OSError, json.JSONDecodeError, AdvisoryContractError) as error:
        print(f"GATE_BLOCK: invalid AI CI advisory: {error}")
        return 2
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(advisory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
