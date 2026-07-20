"""Typed review verdict state-machine contract."""
from dataclasses import replace
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.control_types import (
    ReviewItemKind,
    ReviewJudgment,
    ReviewOverride,
    ReviewPublishState,
)
from content.review.ledger import (
    ReviewLedger,
    ReviewVerdict,
    needs_human,
    post_publishability,
    reprocess_exhausted,
    resolve_publish_state,
)
from content.review.policy import review_policy


def _item(**kw) -> ReviewVerdict:
    base = dict(
        kind=ReviewItemKind.IMAGE,
        target="data_asset_x",
        agent_judgment=ReviewJudgment.CREDIBLE,
        agent_score=review_policy().agent_publish_at_least,
    )
    base.update(kw)
    return ReviewVerdict(**base)


def test_human_override_wins():
    assert resolve_publish_state(_item(human_override=ReviewOverride.DISCARD)) is ReviewPublishState.DISCARD
    assert resolve_publish_state(_item(agent_judgment=ReviewJudgment.DOUBTFUL, agent_score=1, human_override=ReviewOverride.PUBLISHABLE)) is ReviewPublishState.PUBLISHABLE


def test_human_credible_or_score_publishes():
    assert resolve_publish_state(_item(human_judgment=ReviewJudgment.CREDIBLE)) is ReviewPublishState.PUBLISHABLE
    assert resolve_publish_state(_item(human_score=3)) is ReviewPublishState.PUBLISHABLE
    assert resolve_publish_state(_item(human_score=5)) is ReviewPublishState.PUBLISHABLE


def test_human_doubtful_is_fix():
    assert resolve_publish_state(_item(human_judgment=ReviewJudgment.DOUBTFUL)) is ReviewPublishState.FIX


def test_agent_doubtful_requires_human():
    # 默认 requireHumanWhenDoubtful=True：agent 存疑且人未判 → fix
    it = _item(agent_judgment=ReviewJudgment.DOUBTFUL, agent_score=4, human_judgment=ReviewJudgment.UNJUDGED)
    assert resolve_publish_state(it) is ReviewPublishState.FIX
    assert needs_human(it) is True


def test_agent_credible_high_score_auto_publish():
    assert resolve_publish_state(_item(agent_judgment=ReviewJudgment.CREDIBLE, agent_score=3)) is ReviewPublishState.PUBLISHABLE
    assert resolve_publish_state(_item(agent_judgment=ReviewJudgment.CREDIBLE, agent_score=5)) is ReviewPublishState.PUBLISHABLE


def test_agent_low_quality_is_fix_and_reprocessable():
    it = _item(agent_judgment=ReviewJudgment.CREDIBLE, agent_score=2, reprocess_count=0)
    assert resolve_publish_state(it) is ReviewPublishState.FIX
    assert reprocess_exhausted(it) is False
    assert needs_human(it) is False  # 还能再加工，无需人工


def test_reprocess_exhausted_needs_human():
    it = _item(agent_judgment=ReviewJudgment.CREDIBLE, agent_score=2, reprocess_count=3)
    assert reprocess_exhausted(it) is True
    assert resolve_publish_state(it) is ReviewPublishState.FIX
    assert needs_human(it) is True  # 加工耗尽，必须人工裁决


def test_configurable_auto_approve_disabled():
    policy = replace(review_policy(), agent_publish_at_least=5)
    assert resolve_publish_state(_item(agent_judgment=ReviewJudgment.CREDIBLE, agent_score=4), policy) is ReviewPublishState.FIX
    assert resolve_publish_state(_item(agent_judgment=ReviewJudgment.CREDIBLE, agent_score=5), policy) is ReviewPublishState.PUBLISHABLE


def test_post_publishability_discard_image_not_blocking():
    ledger = ReviewLedger(
        execution_id="20260711--travel-article-review--cn-sichuan--canary-001", ref="稻城亚丁_体验",
        article=ReviewVerdict(kind=ReviewItemKind.ARTICLE, target="article", agent_judgment=ReviewJudgment.CREDIBLE, agent_score=4),
        images=(
            _item(target="img_ok", agent_judgment=ReviewJudgment.CREDIBLE, agent_score=4),
            _item(target="img_bad", human_override=ReviewOverride.DISCARD),
        ),
    )
    ok, reasons, discards = post_publishability(ledger)
    assert ok is True
    assert reasons == []
    assert discards == ["img_bad"]


def test_post_publishability_blocked_by_fix_image():
    ledger = ReviewLedger(
        execution_id="20260711--travel-article-review--cn-sichuan--canary-002", ref="r",
        article=ReviewVerdict(kind=ReviewItemKind.ARTICLE, target="article", agent_judgment=ReviewJudgment.CREDIBLE, agent_score=4),
        images=(_item(target="img_doubt", agent_judgment=ReviewJudgment.DOUBTFUL, agent_score=2),),
    )
    ok, reasons, _ = post_publishability(ledger)
    assert ok is False
    assert any("img_doubt" in r for r in reasons)


def test_roundtrip_serialization():
    led = ReviewLedger(
        execution_id="20260711--travel-article-review--cn-sichuan--canary-003", ref="r",
        article=ReviewVerdict(kind=ReviewItemKind.ARTICLE, target="article", agent_judgment=ReviewJudgment.CREDIBLE, agent_score=3),
        images=(_item(target="i1"),),
        facts=(ReviewVerdict(kind=ReviewItemKind.FACT, target="海拔4500米", agent_judgment=ReviewJudgment.DOUBTFUL, agent_score=2),),
    )
    again = ReviewLedger.from_document(led.to_document())
    assert again.ref == "r"
    assert again.facts[0].target == "海拔4500米"
    # publishState 是派生字段，序列化时计算
    assert led.to_document()["images"][0]["publishState"] in {item.value for item in ReviewPublishState}


def test_review_policy_is_repository_owned():
    policy = review_policy()
    assert policy.agent_publish_at_least == 3
    assert policy.max_reprocess_attempts == 3
