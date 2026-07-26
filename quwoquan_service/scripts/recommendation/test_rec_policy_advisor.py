#!/usr/bin/env python3
"""Unit tests for rec_policy_advisor: guardrail evaluation + no-activate guard.

Run: python3 -m pytest quwoquan_service/scripts/recommendation/test_rec_policy_advisor.py
"""
from __future__ import annotations

import importlib.util
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "rec_policy_advisor", os.path.join(_HERE, "rec_policy_advisor.py")
)
advisor = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(advisor)


GUARDRAILS = [
    {"metric": "ctr", "baselinePreset": "control", "minRatio": 0.95, "minSamples": 1000,
     "window": "24h", "action": "suggest_only"},
    {"metric": "dwell", "baselinePreset": "control", "minRatio": 0.93, "minSamples": 1000,
     "window": "24h", "action": "suggest_only"},
]


def _cohort(preset, ctr, dwell, samples, segment="none"):
    return {"preset": preset, "segment": segment, "bucket": preset, "samples": samples,
            "metrics": {"ctr": ctr, "dwell": dwell}}


def test_candidate_meeting_all_floors_is_recommend_review():
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("engagement_heavy", 0.079, 12.5, 3000),  # ctr ratio ~0.99, dwell >1
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, "v1")
    sug = {s["preset"]: s for s in report["suggestions"]}
    assert sug["engagement_heavy"]["verdict"] == advisor.VERDICT_RECOMMEND_REVIEW
    assert sug["engagement_heavy"]["action"] == advisor.ACTION_SUGGEST_ONLY


def test_candidate_below_floor_is_rejected():
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("explore_heavy", 0.060, 12.5, 3000),  # ctr ratio 0.75 < 0.95
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, "v1")
    sug = {s["preset"]: s for s in report["suggestions"]}
    assert sug["explore_heavy"]["verdict"] == advisor.VERDICT_REJECT
    assert any("ctr" in r for r in sug["explore_heavy"]["reasons"])


def test_insufficient_samples_is_hold():
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("freshness_heavy", 0.082, 12.5, 100),  # samples < minSamples
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, "v1")
    sug = {s["preset"]: s for s in report["suggestions"]}
    assert sug["freshness_heavy"]["verdict"] == advisor.VERDICT_HOLD


def test_reject_dominates_over_review_across_metrics():
    # ctr passes but dwell fails -> overall reject (worst verdict wins).
    cohorts = [
        _cohort("control", 0.080, 12.0, 5000),
        _cohort("engagement_heavy", 0.079, 5.0, 3000),  # dwell ratio ~0.42 < 0.93
    ]
    report = advisor.evaluate(cohorts, GUARDRAILS, "v1")
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
        "policyVersion: v1\ndefaultPreset: control\n"
        "guardrails:\n  - {metric: ctr, baselinePreset: control, minRatio: 0.9, "
        "minSamples: 10, window: 24h, action: auto_rollback}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        advisor.load_guardrails(str(bad_policy))


def test_real_policy_yaml_loads_suggest_only():
    repo_root = os.path.abspath(os.path.join(_HERE, "..", ".."))
    policy_path = os.path.join(
        repo_root,
        "services",
        "content-service",
        "resources",
        "policies",
        "content",
        "post",
        "recommendation_policy.yaml",
    )
    version, default_preset, guardrails = advisor.load_guardrails(policy_path)
    assert version
    assert default_preset
    assert guardrails  # real policy has guardrails
    for g in guardrails:
        assert g["action"] == advisor.ACTION_SUGGEST_ONLY
