"""Creative autonomy contract tests.

AI should have room to choose title/structure/narrative moves inside a locked
evidence boundary.  The review gate must then verify that the agent recorded
its creative plan and did not cross persona/evidence boundaries.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from core.creative_brief import complete_creative_meta, creative_governance_issues  # noqa: E402
from content.post.writing_pack import build_writing_pack, render_prompt_md  # noqa: E402


def _pack() -> dict:
    execution_id = "20260711--travel-article-creative-autonomy--cn-sichuan--canary-001"
    return build_writing_pack(
        execution_id=execution_id,
        ref="九寨沟_decision",
        kind="entity",
        brief={
            "titleHint": "九寨沟·值不值得去",
            "templateId": "travel.entity.guide",
            "writingIntent": "decision_experience",
            "mustIncludeFacts": ["九寨沟有多处湖泊景观", "旺季需要提前规划"],
            "creativeBrief": {
                "allowedMoves": ["价值与劝退并置", "结论先行"],
            },
        },
        evidence_bundle={"routeNodes": [{"entityName": "九寨沟", "factEvidence": [{"text": "九寨沟有多处湖泊景观"}]}]},
        assets=[],
        carrier="article",
        byline="平台旅行编辑",
        publish_layout="entity",
        section_intents=["围绕是否值得去组织正文"],
        source_urls=["https://example.test/source"],
        source_paths=["sources/01/source.md"],
    )


def test_writing_pack_carries_creative_brief_and_prompt_contract():
    pack = _pack()
    creative = pack["creativeBrief"]
    assert creative["readerPromise"]
    assert creative["contentAngle"] == "决策体验/值不值得去"
    assert "价值与劝退并置" in creative["allowedMoves"]

    prompt = render_prompt_md(pack)
    assert "creativeBrief" in prompt
    # P1：指令区改为模板渲染，人设=创作 agent，删除"会话模型"措辞与 review gate 硬门复述
    # （gate 细则收回 review）。但创作输出契约（creativePlan/selfCritique）仍须由 output_format 模板下发。
    assert "会话模型" not in prompt
    assert "创作 agent" in prompt
    assert "Review Gate 硬检查" not in prompt
    assert "reviewGateChecklist" not in prompt
    assert "creativePlan" in prompt
    assert "selfCritique" in prompt
    assert "主实体: **九寨沟**" in prompt
    assert "正文必须至少自然出现一次完整名称" in prompt
    assert "去过…之后" in prompt


def test_prompt_limits_numeric_facts_to_source_allowlist():
    pack = _pack()
    pack["baseDraftText"] = "景区接驳车票价80元，游览步行约2公里，常见安排是3小时左右。"
    prompt = render_prompt_md(pack)
    assert "带单位数字白名单" in prompt
    assert "80元" in prompt
    assert "2公里" in prompt
    assert "3小时" in prompt
    assert "3500元" not in prompt


def test_prompt_makes_base_draft_light_edit_contract_explicit():
    pack = _pack()
    pack["sourceUseMode"] = "licensed_adaptation"
    pack["baseDraftText"] = "第一段写真实出行动机和现场观察。\n\n第二段写喜欢点和不足点。"
    prompt = render_prompt_md(pack)

    assert "底稿编辑硬合同" in prompt
    assert "先把下方底稿当作初稿骨架处理" in prompt
    assert "baseDraftFidelity" in prompt
    assert "baseDraftFidelityStrategy" in prompt
    # 单底稿零参考宪法 v2：prompt 必须显式禁止用其它来源补全/校正/重写，
    # 稳定子串「用百科/官网/其它来源」跨新旧措辞保留，并补「单底稿零参考」契约标记。
    assert "用百科/官网/其它来源" in prompt
    assert "单底稿零参考" in prompt


def test_prompt_for_factual_reference_uses_base_draft_light_edit_contract():
    """产品裁定 full light-edit：factual_reference_only 与 licensed 同走底稿轻改合同。"""
    pack = _pack()
    pack["sourceUseMode"] = "factual_reference_only"
    pack["baseDraftText"] = "第一段写真实出行动机和现场观察。\n\n第二段写喜欢点和不足点。"
    prompt = render_prompt_md(pack)

    assert "底稿编辑硬合同" in prompt
    assert "先把下方底稿当作初稿骨架处理" in prompt
    assert "baseDraftFidelity" in prompt
    assert "baseDraftFidelityStrategy" in prompt
    assert "事实引用硬合同" not in prompt


def test_creative_governance_requires_plan_and_self_critique():
    pack = _pack()
    article = (
        "# 九寨沟·值不值得去\n\n"
        "先说结论：如果你重视湖泊景观和成熟动线，九寨沟值得优先规划；"
        "但如果你只能旺季临时出发，就要提前接受排队和预算的不确定。\n\n"
        "## 适合和不适合的人\n\n"
        "资料里反复出现的价值，是景观密度高、游览组织成熟；不足则是旺季人流和预约压力。"
    )
    issues = creative_governance_issues(article, pack, {"generator": "agent"})
    assert any("creativePlan missing" in issue for issue in issues), issues
    assert any("selfCritique missing" in issue for issue in issues), issues


def test_creative_governance_blocks_false_first_person_experience():
    pack = _pack()
    meta = {
        "creativePlan": {
            "concepts": [{"planId": "a"}, {"planId": "b"}],
            "selectedPlanId": "a",
            "selectionReason": "最能兑现读者承诺",
        },
        "selfCritique": {
            "readerPromise": "已兑现",
            "titlePromise": "已兑现",
            "informationDensity": "每段都有新判断",
            "evidenceBoundary": "未新增来源",
            "personaBoundary": "平台编辑口吻",
        },
    }
    article = (
        "# 九寨沟·值不值得去\n\n"
        "我亲自去了九寨沟，先说结论：如果你重视湖泊景观和成熟动线，九寨沟值得优先规划。"
    )
    issues = creative_governance_issues(article, pack, meta)
    assert any("personaBoundary" in issue for issue in issues), issues


_PASSING_ARTICLE = (
    "# 九寨沟·值不值得去\n\n"
    "先说结论：如果你重视湖泊景观和成熟动线，九寨沟值得优先规划；"
    "但如果你只能旺季临时出发，就要提前接受排队和预算的不确定。\n\n"
    "## 适合和不适合的人\n\n"
    "资料里反复出现的价值，是景观密度高、游览组织成熟；不足则是旺季人流和预约压力。"
)


def test_complete_creative_meta_unblocks_body_passing_draft():
    # fix A：creativePlan/selfCritique 是结构化规划产物，正文已由 body 级门把关。
    # agent 漏填结构化字段时按锁定的 creativeBrief 预置补全，让正文达标稿有可靠成稿路径，
    # 不再被 creativeGovernance 100% 硬拦。
    pack = _pack()
    raw_meta = {"generator": "agent", "model": "cursor"}
    assert any(
        "creativePlan" in issue or "selfCritique" in issue
        for issue in creative_governance_issues(_PASSING_ARTICLE, pack, raw_meta)
    )

    completed, changed = complete_creative_meta(raw_meta, pack, body=_PASSING_ARTICLE)
    assert changed is True
    assert len(completed["creativePlan"]["concepts"]) >= 2
    assert completed["creativePlan"]["selectedPlanId"]
    assert completed["creativePlan"]["selectionReason"]
    assert all(
        "creativePlan" not in issue and "selfCritique" not in issue
        for issue in creative_governance_issues(_PASSING_ARTICLE, pack, completed)
    )
    # body 不在补全范围（只补 meta），generator 维持 agent。
    assert completed["generator"] == "agent"


def test_complete_creative_meta_preserves_agent_supplied_fields():
    pack = _pack()
    agent_meta = {
        "generator": "agent",
        "creativePlan": {
            "concepts": [
                {"planId": "agent_a", "titleCandidate": "AGENT 自定义"},
                {"planId": "agent_b", "titleCandidate": "AGENT 自定义2"},
            ],
            "selectedPlanId": "agent_a",
            "selectionReason": "AGENT 自己的理由",
        },
        "selfCritique": {
            "readerPromise": "AGENT readerPromise",
            "titlePromise": "AGENT titlePromise",
            "informationDensity": "AGENT density",
            "evidenceBoundary": "AGENT boundary",
            "personaBoundary": "AGENT persona",
        },
    }
    completed, changed = complete_creative_meta(agent_meta, pack, body=_PASSING_ARTICLE)
    assert changed is False
    assert completed["creativePlan"]["selectedPlanId"] == "agent_a"
    assert completed["creativePlan"]["selectionReason"] == "AGENT 自己的理由"
    assert completed["selfCritique"]["readerPromise"] == "AGENT readerPromise"


def test_complete_creative_meta_noop_for_image_carrier():
    pack = _pack()
    pack["carrier"] = "image"
    completed, changed = complete_creative_meta({"generator": "agent"}, pack, body="")
    assert changed is False
    assert "creativePlan" not in completed


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
