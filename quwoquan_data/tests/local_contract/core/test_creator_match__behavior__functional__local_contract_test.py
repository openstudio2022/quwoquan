"""match_creator 内容感知匹配契约。

验证「在底稿/内容信号基础上找最适配的虚拟作者」，而非随意安排：
- 同 archetype（travel_blogger）内，高原主题内容选主题作者、无主题信号选全国作者；
- 载体偏向 carrierAffinity 读取正确；
- 范围契合 coverage_range_fit 命中>未命中、全国为中性基线；
- 相同 seed 确定性命中同一作者（幂等 + 等分负载分摊）。

不修改全局 os.environ，直接 TemplateRegistry.load() 读真实 builtin 作者。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(p for p in Path(__file__).resolve().parents if p.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.templates.creator import carrier_affinity, coverage_range_fit, match_creator  # noqa: E402
from content.templates.registry import TemplateRegistry  # noqa: E402

_TRAVEL_BLUEPRINT = {
    "carrier": "article",
    "vertical": "travel",
    "creatorPersona": {"archetype": "travel_blogger"},
}


def _registry() -> TemplateRegistry:
    return TemplateRegistry.load()


def _travel_blogger_specialty_tag() -> str:
    for creator in _registry().creators_by_archetype("travel_blogger"):
        if str(creator.get("status") or "") != "active":
            continue
        if (creator.get("verticalRefs") or []) != ["travel"]:
            continue
        if (creator.get("carrierAffinity") or {}).get("article", 0) <= 0:
            continue
        scope = creator.get("coverageScope") if isinstance(creator.get("coverageScope"), dict) else {}
        topic_refs = [str(item) for item in (scope.get("topicRefs") or []) if str(item).strip()]
        for topic in topic_refs:
            if topic.startswith("Topic/旅行/") and topic != "Topic/旅行":
                return topic
    raise AssertionError("missing topical travel_blogger creator in active registry")


def test_highland_topic_content_prefers_specialist_creator():
    creator = match_creator(
        _registry(),
        _TRAVEL_BLUEPRINT,
        carrier="article",
        tag_refs=["Topic/地理/行政区/中国/test-region-b/甘孜藏族自治州", "Topic/旅行/旅行主题/高原秘境"],
        region="test-region-b",
        vertical="travel",
        seed="entity/地点/景区/稻城亚丁",
    )
    assert creator["authorId"] == "builtin_highland_travel_blogger"


def test_specialty_content_prefers_matching_specialist_creator():
    # 不再把某个固定标签硬编码到测试里；直接从 active creator registry 里挑一个
    # 真实存在的 topical travel_blogger 专精标签，验证 match_creator 会优先命中
    # 携带该标签的作者，而不是退回无关全国作者。
    specialty_tag = _travel_blogger_specialty_tag()
    creator = match_creator(
        _registry(),
        _TRAVEL_BLUEPRINT,
        carrier="article",
        tag_refs=[specialty_tag],
        region=None,
        vertical="travel",
        seed=f"entity/specialty/{specialty_tag}",
    )
    creator_tags = set(creator.get("publicProfileTagRefs", [])) | set(
        creator.get("recommendationTagRefs", [])
    )
    assert specialty_tag in creator_tags, creator["creatorProfileId"]


def test_no_region_signal_defaults_to_nationwide():
    creator = match_creator(
        _registry(),
        _TRAVEL_BLUEPRINT,
        carrier="article",
        vertical="travel",
        seed="no-region",
    )
    assert creator["creatorProfileId"] == "qwq_creator_travel_blogger_001"


def test_deterministic_same_seed_same_creator():
    reg = _registry()
    kwargs = dict(carrier="article", tag_refs=["Topic/旅行"], region="高原", vertical="travel", seed="stable-seed")
    first = match_creator(reg, _TRAVEL_BLUEPRINT, **kwargs)
    second = match_creator(reg, _TRAVEL_BLUEPRINT, **kwargs)
    assert first["creatorProfileId"] == second["creatorProfileId"]


def test_spread_mode_distributes_equal_fit_creators_by_seed():
    reg = _registry()
    picks = {
        match_creator(
            reg,
            {"carrier": "image", "vertical": "travel", "creatorPersona": {}},
            carrier="image",
            tag_refs=["Topic/旅行", "Topic/旅行/玩法/摄影旅拍"],
            region="test-region-b",
            vertical="travel",
            seed=f"spread-seed-{index}",
            preferred_archetype="",
            selection_mode="spread",
        )["creatorProfileId"]
        for index in range(40)
    }
    stable_a = match_creator(
        reg,
        {"carrier": "image", "vertical": "travel", "creatorPersona": {}},
        carrier="image",
        tag_refs=["Topic/旅行", "Topic/旅行/玩法/摄影旅拍"],
        region="test-region-b",
        vertical="travel",
        seed="same-spread-seed",
        preferred_archetype="",
        selection_mode="spread",
    )
    stable_b = match_creator(
        reg,
        {"carrier": "image", "vertical": "travel", "creatorPersona": {}},
        carrier="image",
        tag_refs=["Topic/旅行", "Topic/旅行/玩法/摄影旅拍"],
        region="test-region-b",
        vertical="travel",
        seed="same-spread-seed",
        preferred_archetype="",
        selection_mode="spread",
    )
    # 当前受控 creator pool 对该 image 画像保留两位同等候选；spread 必须实际分散，
    # 不再对已删除的历史 creator 池硬编码 20 人规模。
    assert len(picks) >= 2
    assert stable_a["creatorProfileId"] == stable_b["creatorProfileId"]


def test_single_candidate_archetype_returns_that_creator():
    # self_drive_expert 只有一个作者，必须稳定返回它（保留 archetype→作者类型映射）。
    creator = match_creator(
        _registry(),
        {"carrier": "article", "vertical": "travel", "creatorPersona": {"archetype": "self_drive_expert"}},
        carrier="article",
        region="沿海海岛",
        vertical="travel",
        seed="anything",
    )
    assert creator["authorId"] == "builtin_travel_self_drive_guide"


def test_carrier_affinity_reads_weights():
    reg = _registry()
    geo = reg.creators["qwq_creator_geo_editor_001"]
    assert carrier_affinity(geo, "video") == 0.0
    assert carrier_affinity(geo, "article") > 0
    photographer = reg.creators["qwq_creator_landscape_photographer_001"]
    assert carrier_affinity(photographer, "image") > carrier_affinity(photographer, "article")


def test_coverage_range_fit_topic_hit_beats_miss_and_nationwide_is_neutral():
    reg = _registry()
    highland = reg.creators["qwq_creator_highland_travel_blogger_001"]
    nationwide = reg.creators["qwq_creator_travel_blogger_001"]
    hit = coverage_range_fit(
        highland, region="test-region-b", tag_refs=["Topic/旅行/旅行主题/高原秘境"]
    )
    miss = coverage_range_fit(highland, region="沿海海岛", tag_refs=["Topic/旅行/旅行主题/海岛度假"])
    neutral = coverage_range_fit(nationwide, region=None, tag_refs=None)
    assert miss < neutral < hit


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"creator match tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
