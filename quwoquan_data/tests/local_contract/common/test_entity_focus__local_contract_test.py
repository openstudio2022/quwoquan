"""entity_focus 单一真相源契约：实体指代弃稿门 + 环线多地点识别。

对应需求：从实体角度挖掘的文章，标题/正文必须明确指代此实体，否则弃稿（off_entity）；
多地点环线游记走网站角度（coverage_targets_mentioned >= 3）。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(p for p in Path(__file__).resolve().parents if p.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from _common import entity_focus as ef  # noqa: E402


def _multi_city_travelogue(entity: str) -> str:
    lines = ["成都重庆三峡六日自驾游记，跨多个城市的环线行程"]
    for i in range(40):
        lines.append("第%d天从重庆出发，沿长江看三峡风光，途经宜昌的小镇。" % i)
        lines.append("晚上住宜昌江景酒店，次日去武隆天坑，风景壮丽。")
    lines.append(f"行程最后一天顺路去了成都的{entity}打卡，人不多。")
    return "\n".join(lines)


def _focused_travelogue(entity: str) -> str:
    lines = [f"{entity}两日深度游记"]
    for _ in range(30):
        lines.append(f"{entity}的核心景观层次丰富，这一段步道走起来很舒服。")
        lines.append(f"在{entity}沟口换乘观光车，建议早点进{entity}避开人流。")
    return "\n".join(lines)


def test_multi_location_travelogue_is_off_entity_for_single_entity():
    body = _multi_city_travelogue("杜甫草堂")
    score, verdict = ef.classify_entity_focus(body, "杜甫草堂", title="成都重庆三峡六日自驾游记")
    assert verdict == ef.VERDICT_OFF_ENTITY, (score, verdict)
    assert score < ef.ENTITY_FOCUS_STRONG_FLOOR
    # 弃稿门：off_entity 不得作单实体文章底稿主源。
    assert ef.verdict_is_primary_eligible(verdict) is False


def test_focused_single_entity_is_strong():
    body = _focused_travelogue("九寨沟")
    score, verdict = ef.classify_entity_focus(body, "九寨沟", title="九寨沟两日深度游记")
    assert verdict == ef.VERDICT_STRONG, (score, verdict)
    assert ef.verdict_is_primary_eligible(verdict) is True


def test_title_reference_relaxes_strong_floor():
    # 正文聚焦处在 weak/strong 之间，但标题明确点名该实体 → 放宽到 strong。
    lines = ["乐山大佛半日游记"]
    for i in range(30):
        lines.append("从码头坐船远观，江风很舒服，沿途讲解很细致。")
        if i % 3 == 0:
            lines.append("乐山大佛的脚趾平台排队较久，建议早到。")
    body = "\n".join(lines)
    score_no_title, verdict_no_title = ef.classify_entity_focus(body, "乐山大佛", title="")
    score_title, verdict_title = ef.classify_entity_focus(body, "乐山大佛", title="乐山大佛半日游记")
    assert score_no_title == score_title
    # 标题点名时门槛更宽松（verdict 不应更差）。
    order = {ef.VERDICT_OFF_ENTITY: 0, ef.VERDICT_SUPPORTING: 1, ef.VERDICT_STRONG: 2}
    assert order[verdict_title] >= order[verdict_no_title]


def test_image_only_no_text_is_off_entity():
    score, verdict = ef.classify_entity_focus("", "都江堰", title="")
    assert verdict == ef.VERDICT_OFF_ENTITY
    assert ef.verdict_is_primary_eligible(verdict) is False


def _route_featuring_entity(entity: str, *siblings: str) -> str:
    lines = ["川西大环线七日游记，串起多个高原打卡地"]
    for _ in range(20):
        lines.append(f"{entity}的五花海层次分明，是这趟环线的重头戏，走起来很舒服。")
    for sibling in siblings:
        lines.append(f"随后我们去了{sibling}，风景同样惊艳，值得停留。")
    return "\n".join(lines)


def test_route_featuring_entity_is_off_entity_via_siblings():
    # 关键缺口：环线突出写了当前实体（聚焦度其实达标），但还覆盖 >=2 个兄弟覆盖目标，
    # 必须判 off_entity（单实体角度弃稿），改走网站角度 route。
    body = _route_featuring_entity("九寨沟", "黄龙", "稻城亚丁")
    siblings = ["黄龙", "稻城亚丁", "峨眉山", "都江堰"]
    score, verdict = ef.classify_entity_focus(
        body, "九寨沟", title="川西大环线七日游记", sibling_names=siblings
    )
    assert score >= ef.ENTITY_FOCUS_STRONG_FLOOR, score  # 对九寨沟聚焦度其实达标
    assert verdict == ef.VERDICT_OFF_ENTITY, (score, verdict)
    assert ef.verdict_is_primary_eligible(verdict) is False
    # 反证：不传 siblings 时退化为纯聚焦度 → strong，说明 off_entity 来自环线判定。
    _, verdict_no_sib = ef.classify_entity_focus(body, "九寨沟", title="川西大环线七日游记")
    assert verdict_no_sib == ef.VERDICT_STRONG, verdict_no_sib


def test_single_sibling_mention_is_still_single_entity():
    # 只顺带提及 1 个兄弟目标，不构成环线，仍是合格单实体底稿。
    body = _route_featuring_entity("九寨沟", "黄龙")
    score, verdict = ef.classify_entity_focus(
        body, "九寨沟", title="九寨沟深度两日", sibling_names=["黄龙", "稻城亚丁", "峨眉山"]
    )
    assert verdict == ef.VERDICT_STRONG, (score, verdict)
    assert ef.verdict_is_primary_eligible(verdict) is True


def test_coverage_targets_mentioned_detects_route_over_three_places():
    body = _multi_city_travelogue("宽窄巷子")
    targets = ["成都", "重庆", "三峡", "宜昌", "宽窄巷子", "九寨沟"]
    mentioned = ef.coverage_targets_mentioned(body, "成都重庆三峡六日自驾游记", targets)
    # 多地点环线：明确提及 >= 3 个覆盖目标 → 适合作网站角度 route 底稿。
    assert len(mentioned) >= 3, mentioned
    assert "九寨沟" not in mentioned  # 未提及的不计入


def test_strong_verdict_is_primary_eligible_and_empty_is_lenient():
    assert ef.verdict_is_primary_eligible(ef.VERDICT_STRONG) is True
    assert ef.verdict_is_primary_eligible("") is True  # 缺失 verdict 不主动拦截
    assert ef.verdict_is_primary_eligible("mismatch") is False


if __name__ == "__main__":
    test_multi_location_travelogue_is_off_entity_for_single_entity()
    test_focused_single_entity_is_strong()
    test_title_reference_relaxes_strong_floor()
    test_image_only_no_text_is_off_entity()
    test_route_featuring_entity_is_off_entity_via_siblings()
    test_single_sibling_mention_is_still_single_entity()
    test_coverage_targets_mentioned_detects_route_over_three_places()
    test_strong_verdict_is_primary_eligible_and_empty_is_lenient()
    print("entity_focus contract tests passed")
