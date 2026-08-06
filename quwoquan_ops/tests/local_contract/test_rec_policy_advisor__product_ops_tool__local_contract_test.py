#!/usr/bin/env python3
"""Unit tests for rec_policy_advisor: guardrail evaluation + no-activate guard.

Run: python3 -m pytest quwoquan_ops/tests/local_contract/test_rec_policy_advisor__product_ops_tool__local_contract_test.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "rec_policy_advisor",
    _ROOT
    / "quwoquan_service/scripts/tools/product_ops/rec_policy_advisor.py",
)
advisor = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(advisor)


GUARDRAILS = [
    {"metric": "ctr", "baselinePreset": "control", "minRatio": 0.95, "minSamples": 1000,
     "window": "24h", "action": "suggest_only"},
    {"metric": "dwell", "baselinePreset": "control", "minRatio": 0.93, "minSamples": 1000,
     "window": "24h", "action": "suggest_only"},
]
POLICY_DIGEST = "sha256:" + "a" * 64


def _cohort(preset, ctr, dwell, samples, segment="none"):
    return {"preset": preset, "segment": segment, "bucket": preset, "samples": samples,
            "metrics": {"ctr": ctr, "dwell": dwell}}


def test_candidate_meeting_all_floors_is_recommend_review():
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("engagement_heavy", 0.079, 12.5, 3000),  # ctr ratio ~0.99, dwell >1
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, POLICY_DIGEST)
    sug = {s["preset"]: s for s in report["suggestions"]}
    assert sug["engagement_heavy"]["verdict"] == advisor.VERDICT_RECOMMEND_REVIEW
    assert sug["engagement_heavy"]["action"] == advisor.ACTION_SUGGEST_ONLY


def test_candidate_below_floor_is_rejected():
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("explore_heavy", 0.060, 12.5, 3000),  # ctr ratio 0.75 < 0.95
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, POLICY_DIGEST)
    sug = {s["preset"]: s for s in report["suggestions"]}
    assert sug["explore_heavy"]["verdict"] == advisor.VERDICT_REJECT
    assert any("ctr" in r for r in sug["explore_heavy"]["reasons"])


def test_insufficient_samples_is_hold():
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("freshness_heavy", 0.082, 12.5, 100),  # samples < minSamples
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, POLICY_DIGEST)
    sug = {s["preset"]: s for s in report["suggestions"]}
    assert sug["freshness_heavy"]["verdict"] == advisor.VERDICT_HOLD


def test_reject_dominates_over_review_across_metrics():
    # ctr passes but dwell fails -> overall reject (worst verdict wins).
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("engagement_heavy", 0.079, 5.0, 3000),  # dwell ratio ~0.42 < 0.93
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, POLICY_DIGEST)
    sug = {s["preset"]: s for s in report["suggestions"]}
    assert sug["engagement_heavy"]["verdict"] == advisor.VERDICT_REJECT


def test_simulate_url_is_always_simulate():
    url = advisor.simulate_url("http://ops:18090/", "policy_x")
    assert url.endswith(":simulate")
    assert ":activate" not in url


def test_no_activate_symbol_exists():
    # The module must not expose any activate capability.
    assert not hasattr(advisor, "activate_url")
    assert not hasattr(advisor, "call_activate")


def test_guardrail_rejects_non_suggest_only_action(tmp_path):
    bad_policy = tmp_path / "policy.yaml"
    bad_policy.write_text(
        "defaultPreset: control\n"
        "guardrails:\n  - {metric: ctr, baselinePreset: control, minRatio: 0.9, "
        "minSamples: 10, window: 24h, action: auto_rollback}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        advisor.load_guardrails(str(bad_policy))


def test_real_policy_yaml_loads_suggest_only():
    policy_path = (
        _ROOT
        / "quwoquan_service"
        / "services"
        / "content-service"
        / "resources"
        / "policies"
        / "content"
        / "post"
        / "recommendation_policy.yaml"
    )
    default_preset, guardrails = advisor.load_guardrails(str(policy_path))
    assert default_preset
    assert guardrails  # real policy has guardrails
    for g in guardrails:
        assert g["action"] == advisor.ACTION_SUGGEST_ONLY


def test_metrics_file_requires_runtime_policy_digest(tmp_path):
    metrics = tmp_path / "metrics.json"
    metrics.write_text('{"cohorts": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="Store.EffectiveHash"):
        advisor.metrics_from_file(str(metrics))


def test_report_uses_digest_not_manual_version():
    report = advisor.evaluate([], GUARDRAILS, POLICY_DIGEST)
    assert report["policyDigest"] == POLICY_DIGEST
    assert "policyVersion" not in report
