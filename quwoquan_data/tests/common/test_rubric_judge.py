"""LLM-as-judge 严格性门 contract tests（rubric judge rigor）。

可直接运行：python3 quwoquan_data/tests/common/test_rubric_judge.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common import rubric_judge as rj  # noqa: E402


def _good_review() -> dict:
    return {
        "schemaVersion": "quwoquan_data.rubric_review/1",
        "ref": "r1",
        "generationModelFamily": "composer",
        "judges": [
            {"modelId": "claude-x", "modelFamily": "claude", "promptHash": "abc123", "temperature": 0.0},
            {"modelId": "gpt-x", "modelFamily": "gpt", "promptHash": "abc123", "temperature": 0.0},
            {"modelId": "gemini-x", "modelFamily": "gemini", "promptHash": "abc123", "temperature": 0.0},
        ],
        "biasControls": {"positionSwapApplied": True, "lengthControlApplied": True},
        "dimensions": [
            {"name": "mainlineConsistency", "scores": [8, 8], "verdict": "pass", "rationale": "主线清晰"},
            {"name": "readability", "scores": [7, 7], "verdict": "pass", "rationale": "口语自然"},
        ],
        "decision": "approved",
    }


def test_good_review_passes_rigor():
    assert rj.review_rigor_issues(_good_review(), require_jury=True) == []


def test_missing_judge_metadata_flagged():
    r = _good_review()
    r["judges"][0].pop("promptHash")
    issues = rj.review_rigor_issues(r)
    assert any("promptHash" in i for i in issues)


def test_self_preference_family_blocked():
    r = _good_review()
    r["generationModelFamily"] = "claude"  # 与第一个 judge 同族
    issues = rj.review_rigor_issues(r)
    assert any("self-preference" in i for i in issues)


def test_non_binary_verdict_and_missing_rationale_flagged():
    r = _good_review()
    r["dimensions"][0]["verdict"] = "3"  # 非二元
    r["dimensions"][1]["rationale"] = ""  # 缺 reason
    issues = rj.review_rigor_issues(r)
    assert any("binary verdict" in i for i in issues)
    assert any("rationale required" in i for i in issues)


def test_bias_controls_required():
    r = _good_review()
    r["biasControls"] = {"positionSwapApplied": False, "lengthControlApplied": True}
    issues = rj.review_rigor_issues(r)
    assert any("positionSwapApplied" in i for i in issues)


def test_jury_minimum_enforced_when_required():
    r = _good_review()
    r["judges"] = r["judges"][:1]
    assert any("jury" in i for i in rj.review_rigor_issues(r, require_jury=True))
    # 不要求 jury 时单判官可放行（其余合规）
    assert rj.review_rigor_issues(r, require_jury=False) == []


def test_jury_majority_vote():
    assert rj.jury_majority(["pass", "pass", "fail"]) == "pass"
    assert rj.jury_majority(["fail", "fail", "pass"]) == "fail"
    assert rj.jury_majority(["pass", "fail"]) == "tie"


def test_position_consistency_detects_flip():
    assert rj.position_consistency_issues("pass", "pass") == []
    assert rj.position_consistency_issues("pass", "fail")


def test_cohen_kappa_and_agreement():
    judge = ["bad", "bad", "good", "good"]
    human = ["bad", "bad", "good", "good"]
    assert rj.cohen_kappa(judge, human) == 1.0
    assert rj.agreement_rate(judge, human) == 1.0
    # 一半错 → kappa 显著下降
    judge2 = ["good", "good", "good", "good"]
    assert rj.cohen_kappa(judge2, human) < 0.6


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"rubric_judge tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
