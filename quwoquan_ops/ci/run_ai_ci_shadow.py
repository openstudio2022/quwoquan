#!/usr/bin/env python3
"""Run least-privilege AI analysis over redacted, immutable CI evidence.

The remote endpoint receives no repository credential and cannot mutate GitHub
or deployment state.  Its response is narrowed to advisory content and is then
validated by :mod:`ai_ci_advisory`; control fields and secret-like material are
rejected before a canonical artifact is written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from quwoquan_ops.ci.ai_ci_advisory import (
    AdvisoryContractError,
    FORBIDDEN_SECRET_KEY_PARTS,
    FORBIDDEN_SECRET_VALUE_PATTERNS,
    canonical_advisory,
    canonical_digest,
)


PROMPT_POLICY = {
    "objective": "Rank likely CI/CD root causes and propose read-only actions.",
    "allowedOutput": [
        "modelIdentity",
        "findings",
        "confidence",
        "suggestedActions",
    ],
    "forbiddenActions": [
        "change a gate result",
        "approve promotion",
        "execute deployment",
        "execute rollback",
        "hide or retry away a deterministic failure",
    ],
}
REDACTION_POLICY = {
    "secretKeyParts": sorted(FORBIDDEN_SECRET_KEY_PARTS),
    "secretValuePatternCount": len(FORBIDDEN_SECRET_VALUE_PATTERNS),
    "replacement": "[REDACTED]",
}
MODEL_FIELDS = frozenset(
    {"modelIdentity", "findings", "confidence", "suggestedActions"}
)


class ShadowAnalysisError(RuntimeError):
    pass


def _redact(value: Any) -> tuple[Any, int]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        redacted_count = 0
        for raw_key, nested in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("_", "").replace("-", "")
            if any(part in normalized for part in FORBIDDEN_SECRET_KEY_PARTS):
                result[key] = "[REDACTED]"
                redacted_count += 1
                continue
            result[key], nested_count = _redact(nested)
            redacted_count += nested_count
        return result, redacted_count
    if isinstance(value, list):
        result_list: list[Any] = []
        redacted_count = 0
        for nested in value:
            redacted, nested_count = _redact(nested)
            result_list.append(redacted)
            redacted_count += nested_count
        return result_list, redacted_count
    if isinstance(value, str) and any(
        pattern.search(value) for pattern in FORBIDDEN_SECRET_VALUE_PATTERNS
    ):
        return "[REDACTED]", 1
    return value, 0


def _residual_sensitive_values(value: Any) -> int:
    if isinstance(value, Mapping):
        total = 0
        for raw_key, nested in value.items():
            normalized = str(raw_key).lower().replace("_", "").replace("-", "")
            if any(part in normalized for part in FORBIDDEN_SECRET_KEY_PARTS):
                if nested != "[REDACTED]":
                    total += 1
            total += _residual_sensitive_values(nested)
        return total
    if isinstance(value, list):
        return sum(_residual_sensitive_values(nested) for nested in value)
    if isinstance(value, str):
        return sum(
            1 for pattern in FORBIDDEN_SECRET_VALUE_PATTERNS if pattern.search(value)
        )
    return 0


def prepare_request(
    source: Any,
    *,
    source_ref_prefix: str,
    source_kind: str,
    source_git_sha: str,
    workflow_run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_digest = canonical_digest(source)
    redacted, redacted_count = _redact(source)
    residual_count = _residual_sensitive_values(redacted)
    if residual_count:
        raise ShadowAnalysisError(
            "redaction scan found residual sensitive values; no model request was sent"
        )
    model_input_digest = canonical_digest(redacted)
    source_ref = source_ref_prefix.rstrip("@") + "@" + source_digest
    evidence = {
        "kind": source_kind,
        "sourceRef": source_ref,
        "sourceDigest": source_digest,
        "modelInputDigest": model_input_digest,
        "sourceGitSha": source_git_sha,
        "workflowRunId": workflow_run_id,
    }
    receipt_unsigned = {
        "sourceDigest": source_digest,
        "modelInputDigest": model_input_digest,
        "policyDigest": canonical_digest(REDACTION_POLICY),
        "scanDigest": canonical_digest(
            {
                "modelInputDigest": model_input_digest,
                "residualSensitiveValueCount": residual_count,
            }
        ),
        "redactedValueCount": redacted_count,
        "residualSensitiveValueCount": residual_count,
    }
    receipt = {
        **receipt_unsigned,
        "receiptDigest": canonical_digest(receipt_unsigned),
    }
    request = {
        "promptPolicy": PROMPT_POLICY,
        "promptDigest": canonical_digest(PROMPT_POLICY),
        "sourceEvidence": evidence,
        "evidence": redacted,
    }
    return request, evidence, receipt


def _default_open(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


def run_shadow(
    *,
    source: Any,
    endpoint: str,
    bearer_token: str,
    source_ref_prefix: str,
    source_kind: str,
    source_git_sha: str,
    workflow_run_id: str,
    timeout_seconds: float = 30.0,
    opener: Callable[[urllib.request.Request, float], Any] = _default_open,
) -> dict[str, Any]:
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ShadowAnalysisError("AI shadow endpoint must be a credential-free HTTPS URL")
    if not bearer_token.strip():
        raise ShadowAnalysisError("AI shadow bearer token is unavailable")
    request_payload, evidence, receipt = prepare_request(
        source,
        source_ref_prefix=source_ref_prefix,
        source_kind=source_kind,
        source_git_sha=source_git_sha,
        workflow_run_id=workflow_run_id,
    )
    encoded = json.dumps(
        request_payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=encoded,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + bearer_token.strip(),
            "Content-Type": "application/json",
        },
    )
    try:
        with opener(request, timeout_seconds) as response:
            raw_response = response.read()
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        raise ShadowAnalysisError(f"AI shadow endpoint request failed: {error}") from error
    try:
        response_payload = json.loads(raw_response)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ShadowAnalysisError("AI shadow endpoint returned invalid JSON") from error
    if not isinstance(response_payload, Mapping) or set(response_payload) != MODEL_FIELDS:
        raise ShadowAnalysisError(
            "AI shadow endpoint must return only modelIdentity, findings, confidence and suggestedActions"
        )
    draft = {
        "sourceEvidence": [evidence],
        "modelIdentity": response_payload["modelIdentity"],
        "promptDigest": request_payload["promptDigest"],
        "findings": response_payload["findings"],
        "confidence": response_payload["confidence"],
        "suggestedActions": response_payload["suggestedActions"],
        "redactions": [receipt],
    }
    return canonical_advisory(draft)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-ref-prefix", required=True)
    parser.add_argument("--source-kind", default="ci-job-summary")
    parser.add_argument("--source-git-sha", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--token-env", default="AI_CI_SHADOW_TOKEN")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        source = json.loads(args.source.read_text(encoding="utf-8"))
        advisory = run_shadow(
            source=source,
            endpoint=args.endpoint,
            bearer_token=os.environ.get(args.token_env, ""),
            source_ref_prefix=args.source_ref_prefix,
            source_kind=args.source_kind,
            source_git_sha=args.source_git_sha,
            workflow_run_id=args.workflow_run_id,
            timeout_seconds=args.timeout_seconds,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(advisory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        AdvisoryContractError,
        ShadowAnalysisError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"GATE_BLOCK: AI shadow advisory was not materialized: {error}")
        return 2
    print(f"AI shadow advisory written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
