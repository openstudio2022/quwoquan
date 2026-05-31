"""review_ledger 发布态状态机（agent/human 判定+打分 → fix/discard/publishable）。"""
from _common.review_ledger import (
    DEFAULT_POLICY,
    JUDGE_CREDIBLE,
    JUDGE_DOUBTFUL,
    JUDGE_UNJUDGED,
    KIND_ARTICLE,
    KIND_IMAGE,
    OVERRIDE_DISCARD,
    OVERRIDE_PUBLISHABLE,
    STATE_DISCARD,
    STATE_FIX,
    STATE_PUBLISHABLE,
    ReviewItem,
    ReviewLedger,
    needs_human,
    post_publishability,
    reprocess_exhausted,
    resolve_publish_state,
)


def _item(**kw) -> ReviewItem:
    base = dict(kind=KIND_IMAGE, target="data_asset_x")
    base.update(kw)
    return ReviewItem(**base)


def test_human_override_wins():
    assert resolve_publish_state(_item(humanOverride=OVERRIDE_DISCARD)) == STATE_DISCARD
    assert resolve_publish_state(_item(agentJudgment=JUDGE_DOUBTFUL, agentScore=1, humanOverride=OVERRIDE_PUBLISHABLE)) == STATE_PUBLISHABLE


def test_human_credible_or_score_publishes():
    assert resolve_publish_state(_item(humanJudgment=JUDGE_CREDIBLE)) == STATE_PUBLISHABLE
    assert resolve_publish_state(_item(humanScore=3)) == STATE_PUBLISHABLE
    assert resolve_publish_state(_item(humanScore=5)) == STATE_PUBLISHABLE


def test_human_doubtful_is_fix():
    assert resolve_publish_state(_item(humanJudgment=JUDGE_DOUBTFUL)) == STATE_FIX


def test_agent_doubtful_requires_human():
    # 默认 requireHumanWhenDoubtful=True：agent 存疑且人未判 → fix
    it = _item(agentJudgment=JUDGE_DOUBTFUL, agentScore=4, humanJudgment=JUDGE_UNJUDGED)
    assert resolve_publish_state(it) == STATE_FIX
    assert needs_human(it) is True


def test_agent_credible_high_score_auto_publish():
    assert resolve_publish_state(_item(agentJudgment=JUDGE_CREDIBLE, agentScore=3)) == STATE_PUBLISHABLE
    assert resolve_publish_state(_item(agentJudgment=JUDGE_CREDIBLE, agentScore=5)) == STATE_PUBLISHABLE


def test_agent_low_quality_is_fix_and_reprocessable():
    it = _item(agentJudgment=JUDGE_CREDIBLE, agentScore=2, reprocessCount=0)
    assert resolve_publish_state(it) == STATE_FIX
    assert reprocess_exhausted(it) is False
    assert needs_human(it) is False  # 还能再加工，无需人工


def test_reprocess_exhausted_needs_human():
    it = _item(agentJudgment=JUDGE_CREDIBLE, agentScore=2, reprocessCount=3)
    assert reprocess_exhausted(it) is True
    assert resolve_publish_state(it) == STATE_FIX
    assert needs_human(it) is True  # 加工耗尽，必须人工裁决


def test_configurable_auto_approve_disabled():
    policy = {"autoApprove": {"agentMinScore": 5, "requireHumanWhenDoubtful": True}, "reprocess": {"maxAttempts": 3}}
    assert resolve_publish_state(_item(agentJudgment=JUDGE_CREDIBLE, agentScore=4), policy) == STATE_FIX
    assert resolve_publish_state(_item(agentJudgment=JUDGE_CREDIBLE, agentScore=5), policy) == STATE_PUBLISHABLE


def test_post_publishability_discard_image_not_blocking():
    ledger = ReviewLedger(
        taskId="t", batchId="b", ref="稻城亚丁_体验",
        article=ReviewItem(kind=KIND_ARTICLE, target="article", agentJudgment=JUDGE_CREDIBLE, agentScore=4),
        images=[
            _item(target="img_ok", agentJudgment=JUDGE_CREDIBLE, agentScore=4),
            _item(target="img_bad", humanOverride=OVERRIDE_DISCARD),
        ],
    )
    ok, reasons, discards = post_publishability(ledger)
    assert ok is True
    assert reasons == []
    assert discards == ["img_bad"]


def test_post_publishability_blocked_by_fix_image():
    ledger = ReviewLedger(
        taskId="t", batchId="b", ref="r",
        article=ReviewItem(kind=KIND_ARTICLE, target="article", agentJudgment=JUDGE_CREDIBLE, agentScore=4),
        images=[_item(target="img_doubt", agentJudgment=JUDGE_DOUBTFUL, agentScore=2)],
    )
    ok, reasons, _ = post_publishability(ledger)
    assert ok is False
    assert any("img_doubt" in r for r in reasons)


def test_roundtrip_serialization():
    led = ReviewLedger(
        taskId="t", batchId="b", ref="r",
        article=ReviewItem(kind=KIND_ARTICLE, target="article"),
        images=[_item(target="i1")],
        facts=[ReviewItem(kind="fact", target="海拔4500米", agentJudgment=JUDGE_DOUBTFUL, agentScore=2)],
    )
    again = ReviewLedger.from_dict(led.to_dict())
    assert again.ref == "r"
    assert again.facts[0].target == "海拔4500米"
    # publishState 是派生字段，序列化时计算
    assert led.to_dict()["images"][0]["publishState"] in (STATE_FIX, STATE_PUBLISHABLE, STATE_DISCARD)


def test_default_policy_shape():
    assert DEFAULT_POLICY["autoApprove"]["agentMinScore"] == 3
    assert DEFAULT_POLICY["reprocess"]["maxAttempts"] == 3
