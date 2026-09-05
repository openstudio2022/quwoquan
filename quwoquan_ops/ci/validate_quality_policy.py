#!/usr/bin/env python3
"""Fail-closed validation for test ownership, flaky policy and SLO activation."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
OCI_REF_RE = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")


class QualityPolicyError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualityPolicyError(f"{path} is unreadable: {error}") from error
    if not isinstance(value, dict):
        raise QualityPolicyError(f"{path} must contain an object")
    return value


def validate(now: dt.datetime | None = None) -> dict[str, object]:
    from quwoquan_ops.ci.impact_planner_core import _load_test_ownership_policy

    _ownership, ownership_digest = _load_test_ownership_policy()
    flaky = _load(ROOT / "quwoquan_ops/policies/flaky_test_policy.json")
    if flaky.get("schema") != "flaky-test-policy" or flaky.get("schemaVersion") != 1:
        raise QualityPolicyError("flaky test policy schema is unsupported")
    retry = flaky.get("retry")
    if retry != {
        "maximumFreshRetries": 1,
        "allowedClassifications": ["infra", "transport", "device_bridge"],
        "deterministicFailureRetryForbidden": True,
    }:
        raise QualityPolicyError("flaky retry policy must allow exactly one classified fresh retry")
    quarantine = flaky.get("quarantine")
    if not isinstance(quarantine, dict) or quarantine.get("maximumDays") != 7 or quarantine.get("promotionCriticalAllowed") is not False:
        raise QualityPolicyError("flaky quarantine must expire in seven days and exclude promotion-critical tests")
    current = now or dt.datetime.now(dt.timezone.utc)
    tests = flaky.get("quarantinedTests")
    if not isinstance(tests, list):
        raise QualityPolicyError("quarantinedTests must be a list")
    for entry in tests:
        if not isinstance(entry, dict):
            raise QualityPolicyError("quarantine entry must be an object")
        required = quarantine.get("requiredFields")
        if not isinstance(required, list) or any(not entry.get(name) for name in required):
            raise QualityPolicyError("quarantine entry is missing owner/evidence fields")
        opened = dt.datetime.fromisoformat(str(entry["openedAt"]).replace("Z", "+00:00"))
        expires = dt.datetime.fromisoformat(str(entry["expiresAt"]).replace("Z", "+00:00"))
        if expires <= opened or expires - opened > dt.timedelta(days=7) or expires <= current:
            raise QualityPolicyError(f"quarantine {entry['testId']} is expired or exceeds seven days")
        if entry.get("promotionCritical") is True:
            raise QualityPolicyError("promotion-critical tests cannot be quarantined")

    slo = _load(ROOT / "quwoquan_ops/environments/feedback_slo_activation.json")
    if set(slo) != {
        "activationRule",
        "cleanRunEvidenceRefs",
        "gate",
        "minimumCleanRuns",
        "observedCleanRuns",
        "schema",
        "state",
    }:
        raise QualityPolicyError("feedback SLO activation fields must be closed")
    if slo.get("schema") != "feedback-slo-activation":
        raise QualityPolicyError("feedback SLO activation schema is unsupported")
    refs = slo.get("cleanRunEvidenceRefs")
    observed = slo.get("observedCleanRuns")
    minimum = slo.get("minimumCleanRuns")
    if not isinstance(refs, list) or len(refs) != len(set(refs)) or any(OCI_REF_RE.fullmatch(str(ref)) is None for ref in refs):
        raise QualityPolicyError("clean-run evidence refs must be unique exact OCI digests")
    if observed != len(refs) or minimum != 20:
        raise QualityPolicyError("clean-run counter must be evidence-derived with minimum 20")
    state = slo.get("state")
    expected_state = "enforced" if observed >= minimum else "learning"
    if state != expected_state:
        raise QualityPolicyError("feedback SLO state contradicts evidence count")
    return {
        "testOwnershipDigest": ownership_digest,
        "quarantinedTestCount": len(tests),
        "feedbackSloState": state,
        "observedCleanRuns": observed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = validate()
    except (QualityPolicyError, ValueError) as error:
        print(f"validate_quality_policy: FAIL: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
