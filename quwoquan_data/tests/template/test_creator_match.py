"""match_creator 内容感知匹配契约。

验证「在底稿/内容信号基础上找最适配的虚拟作者」，而非随意安排：
- 同 archetype（travel_blogger）内，川西内容选区域作者、非川西/无地域信号选全国作者；
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

from template.creator import carrier_affinity, coverage_range_fit, match_creator  # noqa: E402
from template.registry import TemplateRegistry  # noqa: E402

_TRAVEL_BLUEPRINT = {
    "carrier": "article",
    "vertical": "travel",
    "creatorPersona": {"archetype": "travel_blogger"},
}


def _registry() -> TemplateRegistry:
    return TemplateRegistry.load()


def test_chuanxi_region_content_prefers_regional_creator():
    creator = match_creator(
        _registry(),
        _TRAVEL_BLUEPRINT,
        carrier="article",
        tag_refs=["Topic/地理/行政区/中国/四川省/甘孜藏族自治州", "Topic/旅行/旅行主题/文化深度游"],
        region="四川省",
        vertical="travel",
        seed="entity/地点/景区/稻城亚丁",
    )
    assert creator["authorId"] == "builtin_travel_blogger_chuanxi"


def test_specialty_content_prefers_matching_specialist_creator():
    # 标签体系规范化（2 级短标签 → 3 级规范叶子）后，内容 tagRef 能与池内专精作者的
    # recommendationTagRefs 精确重叠：海岛度假内容必须命中携带该专精标签的作者，而非泛化全国
    # builtin。这正是放量到 100「按内容适配把内容分摊给专精作者」的目标行为；
    # 「无信号回退全国作者」由 test_no_region_signal_defaults_to_nationwide 守护。
    creator = match_creator(
        _registry(),
        _TRAVEL_BLUEPRINT,
        carrier="article",
        tag_refs=["Topic/旅行/旅行主题/海岛度假"],
        region="沿海海岛",
        vertical="travel",
        seed="entity/地点/景区/鼓浪屿",
    )
    creator_tags = set(creator.get("publicProfileTagRefs", [])) | set(
        creator.get("recommendationTagRefs", [])
    )
    assert "Topic/旅行/旅行主题/海岛度假" in creator_tags, creator["creatorProfileId"]


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


def test_coverage_range_fit_regional_hit_beats_miss_and_nationwide_is_neutral():
    reg = _registry()
    chuanxi = reg.creators["qwq_creator_travel_blogger_chuanxi_001"]
    nationwide = reg.creators["qwq_creator_travel_blogger_001"]
    hit = coverage_range_fit(
        chuanxi, region="四川省", tag_refs=["Topic/地理/行政区/中国/四川省/甘孜藏族自治州"]
    )
    miss = coverage_range_fit(chuanxi, region="沿海海岛", tag_refs=["Topic/旅行/旅行主题/海岛度假"])
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
