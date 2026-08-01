from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import evaluate_gate


@pytest.mark.parametrize(
    ("scenario", "metrics", "dry_run", "expected_status", "expected_reason"),
    [
        (
            "content_feed",
            {"auc": 0.55, "ndcg_20": 0.06},
            False,
            "blocked",
            "AUC 0.5500 < absolute min 0.65",
        ),
        (
            "content_feed",
            {"auc": 0.55, "ndcg_20": 0.06},
            True,
            "pass",
            "AUC=0.5500 NDCG=0.0600",
        ),
        (
            "content_feed_multiobjective",
            {"fused_auc": 0.48, "ndcg_20": 0.06},
            False,
            "blocked",
            "fused_auc 0.4800 < absolute min 0.6",
        ),
        (
            "content_feed_multiobjective",
            {"fused_auc": 0.48, "ndcg_20": 0.06},
            True,
            "pass",
            "fused_auc=0.4800",
        ),
    ],
)
def test_evaluate_gate_uses_explicit_evidence_thresholds(
    scenario: str,
    metrics: dict[str, float],
    dry_run: bool,
    expected_status: str,
    expected_reason: str,
) -> None:
    status, reason, _diversity = evaluate_gate.evaluate_metrics(
        scenario=scenario,
        candidate_metrics=metrics,
        dry_run=dry_run,
    )
    assert status == expected_status
    if expected_status == "pass":
        assert reason == expected_reason
    else:
        assert expected_reason in reason


def test_evaluate_gate_compares_candidate_to_explicit_active_evidence() -> None:
    status, reason, _diversity = evaluate_gate.evaluate_metrics(
        scenario="content_feed",
        candidate_metrics={"auc": 0.80, "ndcg_20": 0.30},
        active_metrics={"auc": 0.85, "ndcg_20": 0.35},
    )
    assert status == "blocked"
    assert "vs active" in reason


def test_gate_cli_reads_files_and_writes_verification_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "releaseId": "release-001",
                "scenario": "content_feed",
                "modelDigest": "a" * 64,
                "artifactUri": "s3://models/content_feed/release-001/model.txt",
                "featureContractDigest": "b" * 64,
                "evaluationMetrics": {"auc": 0.80, "ndcg_20": 0.30},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "verification.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_gate.py",
            "--candidate-evidence",
            str(candidate),
            "--out",
            str(output),
        ],
    )
    assert evaluate_gate.main() == 0
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["status"] == "pass"
    assert evidence["releaseId"] == "release-001"
