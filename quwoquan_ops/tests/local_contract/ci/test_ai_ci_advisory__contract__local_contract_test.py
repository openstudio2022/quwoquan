"""local_contract: AI CI advisory is read-only and single-track."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quwoquan_ops.ci.ai_ci_advisory import (
    AdvisoryContractError,
    canonical_advisory,
    canonical_digest,
)


ROOT = Path(__file__).resolve().parents[4]
SOURCE_DIGEST = "sha256:" + "1" * 64
MODEL_INPUT_DIGEST = "sha256:" + "2" * 64
POLICY_DIGEST = "sha256:" + "3" * 64
SCAN_DIGEST = "sha256:" + "4" * 64
GIT_SHA = "a" * 40
WORKFLOW_RUN_ID = "42"


def redaction_receipt(
    *,
    source_digest: str = SOURCE_DIGEST,
    model_input_digest: str = MODEL_INPUT_DIGEST,
    redacted_value_count: int = 1,
) -> dict[str, object]:
    receipt: dict[str, object] = {
        "sourceDigest": source_digest,
        "modelInputDigest": model_input_digest,
        "policyDigest": POLICY_DIGEST,
        "scanDigest": SCAN_DIGEST,
        "redactedValueCount": redacted_value_count,
        "residualSensitiveValueCount": 0,
    }
    return {**receipt, "receiptDigest": canonical_digest(receipt)}


def draft() -> dict[str, object]:
    return {
        "sourceEvidence": [
            {
                "kind": "ci-job-log",
                "sourceRef": (
                    "github-actions://quwoquan/quwoquan/runs/42/jobs/7@"
                    + SOURCE_DIGEST
                ),
                "sourceDigest": SOURCE_DIGEST,
                "modelInputDigest": MODEL_INPUT_DIGEST,
                "sourceGitSha": GIT_SHA,
                "workflowRunId": WORKFLOW_RUN_ID,
            }
        ],
        "modelIdentity": "ci-triage-shadow",
        "promptDigest": "sha256:" + "5" * 64,
        "findings": [{"title": "cache miss", "evidence": "build step"}],
        "confidence": 0.75,
        "suggestedActions": ["inspect the BuildKit cache key"],
        "redactions": [redaction_receipt()],
    }


def test_canonical_advisory_has_no_version_or_control_envelope() -> None:
    payload = canonical_advisory(draft())
    assert payload["schema"] == "ai-ci-advisory"
    assert set(payload) == {
        "schema",
        "generatedAt",
        "sourceEvidence",
        "modelIdentity",
        "promptDigest",
        "findings",
        "confidence",
        "suggestedActions",
        "redactions",
    }
    assert set(payload["sourceEvidence"][0]) == {
        "kind",
        "sourceRef",
        "sourceDigest",
        "modelInputDigest",
        "sourceGitSha",
        "workflowRunId",
    }
    receipt = payload["redactions"][0]
    assert receipt["sourceDigest"] == payload["sourceEvidence"][0]["sourceDigest"]
    assert receipt["modelInputDigest"] == payload["sourceEvidence"][0][
        "modelInputDigest"
    ]
    unsigned_receipt = dict(receipt)
    assert canonical_digest(
        {
            key: value
            for key, value in unsigned_receipt.items()
            if key != "receiptDigest"
        }
    ) == receipt["receiptDigest"]
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "schemaVersion",
        "contractVersion",
        "registryRevision",
        '"version"',
        '"versions"',
        "promotionDecision",
        "gateStatus",
        "exitCode",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "field",
    [
        "gateStatus",
        "gate_status",
        "promotionDecision",
        "rollbackDecision",
        "exitCode",
    ],
)
def test_advisory_rejects_ci_cd_control_fields(field: str) -> None:
    payload = draft()
    payload["findings"] = [{field: "pass"}]
    with pytest.raises(AdvisoryContractError, match="cannot own CI/CD control field"):
        canonical_advisory(payload)


def test_advisory_rejects_secret_bearing_fields() -> None:
    payload = draft()
    payload["findings"] = [{"accessToken": "must-not-enter-evidence"}]
    with pytest.raises(AdvisoryContractError, match="secret-bearing"):
        canonical_advisory(payload)


def test_advisory_rejects_secret_like_values_under_innocuous_keys() -> None:
    payload = draft()
    payload["findings"] = [{"message": "Bearer synthetic-secret-value"}]
    with pytest.raises(AdvisoryContractError, match="secret-like material"):
        canonical_advisory(payload)


@pytest.mark.parametrize(
    "source_evidence",
    [
        ["unbound-string"],
        [
            {
                "kind": "ci-job-log",
                "sourceRef": "ci/service/summary.json",
                "sourceDigest": SOURCE_DIGEST,
                "modelInputDigest": MODEL_INPUT_DIGEST,
                "sourceGitSha": GIT_SHA,
                "workflowRunId": WORKFLOW_RUN_ID,
            }
        ],
        [
            {
                "kind": "ci-job-log",
                "sourceRef": (
                    "github-actions://quwoquan/quwoquan/runs/42?token=value@"
                    + SOURCE_DIGEST
                ),
                "sourceDigest": SOURCE_DIGEST,
                "modelInputDigest": MODEL_INPUT_DIGEST,
                "sourceGitSha": GIT_SHA,
                "workflowRunId": WORKFLOW_RUN_ID,
            }
        ],
        [
            {
                "kind": "ci-job-log",
                "sourceRef": (
                    "github-actions://quwoquan/quwoquan/runs/42/jobs/7@sha256:"
                    + "9" * 64
                ),
                "sourceDigest": SOURCE_DIGEST,
                "modelInputDigest": MODEL_INPUT_DIGEST,
                "sourceGitSha": GIT_SHA,
                "workflowRunId": WORKFLOW_RUN_ID,
            }
        ],
    ],
)
def test_advisory_rejects_unbound_or_mutable_source_evidence(
    source_evidence: list[object],
) -> None:
    payload = draft()
    payload["sourceEvidence"] = source_evidence
    with pytest.raises(AdvisoryContractError):
        canonical_advisory(payload)


def test_advisory_accepts_one_digest_bound_code_health_summary() -> None:
    payload = draft()
    payload["sourceEvidence"][0]["kind"] = "code-health-delta"
    result = canonical_advisory(payload)
    assert result["sourceEvidence"][0]["kind"] == "code-health-delta"
    assert "gateStatus" not in json.dumps(result)


def test_advisory_rejects_duplicate_code_health_sources() -> None:
    payload = draft()
    first = dict(payload["sourceEvidence"][0])
    first["kind"] = "code-health-delta"
    second = {**first, "sourceRef": "repo://quwoquan/code-health.json@sha256:" + "6" * 64, "sourceDigest": "sha256:" + "6" * 64, "modelInputDigest": "sha256:" + "7" * 64}
    payload["sourceEvidence"] = [first, second]
    payload["redactions"] = [redaction_receipt(), redaction_receipt(source_digest="sha256:" + "6" * 64, model_input_digest="sha256:" + "7" * 64)]
    with pytest.raises(AdvisoryContractError, match="at most once"):
        canonical_advisory(payload)


def test_advisory_rejects_source_evidence_from_different_runs() -> None:
    payload = draft()
    second = dict(payload["sourceEvidence"][0])
    second.update(
        {
            "sourceRef": (
                "repo://quwoquan/contract-graph.json@sha256:" + "6" * 64
            ),
            "sourceDigest": "sha256:" + "6" * 64,
            "modelInputDigest": "sha256:" + "7" * 64,
            "workflowRunId": "43",
        }
    )
    payload["sourceEvidence"] = [payload["sourceEvidence"][0], second]
    payload["redactions"] = [
        redaction_receipt(),
        redaction_receipt(
            source_digest="sha256:" + "6" * 64,
            model_input_digest="sha256:" + "7" * 64,
        ),
    ]
    with pytest.raises(AdvisoryContractError, match="same Git SHA and workflow run"):
        canonical_advisory(payload)


def test_advisory_requires_one_redaction_receipt_per_source() -> None:
    payload = draft()
    payload["redactions"] = []
    with pytest.raises(AdvisoryContractError, match="one digest-bound receipt"):
        canonical_advisory(payload)


def test_advisory_rejects_receipt_for_a_different_source() -> None:
    payload = draft()
    payload["redactions"] = [
        redaction_receipt(
            source_digest="sha256:" + "6" * 64,
            model_input_digest="sha256:" + "7" * 64,
        )
    ]
    with pytest.raises(AdvisoryContractError, match="bind exactly every"):
        canonical_advisory(payload)


def test_advisory_accepts_zero_redactions_only_for_identical_content() -> None:
    payload = draft()
    evidence = dict(payload["sourceEvidence"][0])
    evidence["sourceRef"] = (
        "github-actions://quwoquan/quwoquan/runs/42/jobs/7@" + SOURCE_DIGEST
    )
    evidence["modelInputDigest"] = SOURCE_DIGEST
    payload["sourceEvidence"] = [evidence]
    payload["redactions"] = [
        redaction_receipt(model_input_digest=SOURCE_DIGEST, redacted_value_count=0)
    ]
    result = canonical_advisory(payload)
    assert result["redactions"][0]["redactedValueCount"] == 0


def test_advisory_rejects_redaction_receipt_digest_drift() -> None:
    payload = draft()
    payload["redactions"][0]["redactedValueCount"] = 2
    with pytest.raises(AdvisoryContractError, match="receiptDigest does not match"):
        canonical_advisory(payload)


def test_advisory_rejects_residual_sensitive_values() -> None:
    payload = draft()
    receipt = dict(payload["redactions"][0])
    receipt["residualSensitiveValueCount"] = 1
    unsigned = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    receipt["receiptDigest"] = canonical_digest(unsigned)
    payload["redactions"] = [receipt]
    with pytest.raises(AdvisoryContractError, match="must be the integer zero"):
        canonical_advisory(payload)


def test_advisory_rejects_claimed_redaction_without_changed_digest() -> None:
    payload = draft()
    evidence = dict(payload["sourceEvidence"][0])
    evidence["modelInputDigest"] = SOURCE_DIGEST
    payload["sourceEvidence"] = [evidence]
    payload["redactions"] = [
        redaction_receipt(model_input_digest=SOURCE_DIGEST, redacted_value_count=1)
    ]
    with pytest.raises(AdvisoryContractError, match="without a changed model input"):
        canonical_advisory(payload)


def test_cli_returns_gate_block_for_noncanonical_input(tmp_path: Path) -> None:
    source = tmp_path / "draft.json"
    output = tmp_path / "advisory.json"
    invalid = draft()
    invalid["schemaVersion"] = 1
    source.write_text(json.dumps(invalid), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "quwoquan_ops/ci/ai_ci_advisory.py",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "GATE_BLOCK" in result.stdout
    assert not output.exists()


def test_cli_materializes_only_the_canonical_read_only_shape(tmp_path: Path) -> None:
    source = tmp_path / "draft.json"
    output = tmp_path / "advisory.json"
    source.write_text(json.dumps(draft()), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "quwoquan_ops/ci/ai_ci_advisory.py",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "ai-ci-advisory"
    assert payload["sourceEvidence"] == draft()["sourceEvidence"]
    assert payload["redactions"] == draft()["redactions"]
