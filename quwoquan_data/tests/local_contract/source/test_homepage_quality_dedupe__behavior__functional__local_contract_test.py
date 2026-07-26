"""homepage 源质量门 / 同实体 URL 消重 / 非开放源事实化压缩 合同测试。

覆盖（quality-dedupe-backfill 交付项）：
1. homepage_text_quality_issue：弱事实文本（西岭雪山类）与消歧义页必须打回，富事实文本放行。
2. factual_compress_text：<=1000 不压缩；>2000 压至约 50% 并保留结构行与事实句。
3. handler_fetch 消重/归一 helper：canonical URL 归一、非开放百科识别。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.factual_compression import compression_policy, factual_compress_text  # noqa: E402
from content.source.handler_fetch import (  # noqa: E402
    _canonicalize_source_url,
    _is_non_open_baike_source,
    _publishable_homepage_source_image_count,
    _source_fetch_failure_issue,
)
from content.source.handler_fetch_contract import homepage_base_draft_admission  # noqa: E402
from content.source.research.homepage_text_quality import homepage_text_quality_issue  # noqa: E402
from content.source.source_inputs import _normalize_image_specs  # noqa: E402


# ---------------------------------------------------------------------------
# homepage 事实门
# ---------------------------------------------------------------------------

def test_homepage_gate_rejects_thin_text():
    """西岭雪山类弱源：几句泛泛而谈，无事实密度，必须打回。"""
    thin = (
        "西岭雪山很美。\n\n这里风景不错，值得一去。\n\n大家都喜欢来这里玩。"
    )
    issue = homepage_text_quality_issue(thin, "西岭雪山")
    assert issue in {"insufficient_homepage_facts", "homepage_text_too_short"}, issue


def test_homepage_gate_rejects_disambiguation_page():
    text = (
        "武侯祠可以指下列建筑：\n\n"
        "- 成都武侯祠：位于test-region-b成都市武侯区。\n"
        "- 勉县武侯祠：位于陕西省汉中市勉县。\n"
        "- 南阳武侯祠：位于河南省南阳市。\n"
        "- 白帝城武侯祠：位于重庆市奉节县。\n"
    )
    assert homepage_text_quality_issue(text, "武侯祠") == "disambiguation_homepage"


def test_homepage_gate_rejects_short_disambiguation_with_link_list():
    text = (
        "九龙山可以指：\n\n"
        "* 九龍山 (天津)\n"
        "* 九龍山 (嘉兴)\n"
        "* 九龍山 (香港)\n"
    )

    assert homepage_text_quality_issue(text, "平湖九龙山旅游度假区", require_fact_ready=False) == (
        "disambiguation_homepage"
    )


def test_homepage_gate_rejects_flattened_bare_disambiguation_lead():
    """条目列表被抓取器压平时，消歧义导语本身仍必须拒绝。"""
    text = (
        "示例楼可以指：\n\n"
        "示例楼甲，位于甲地，是当地建筑。 "
        "示例楼乙，位于乙地，设有展览空间。"
    )

    assert homepage_text_quality_issue(text, "示例楼（甲地）", require_fact_ready=False) == (
        "disambiguation_homepage"
    )


def test_homepage_gate_rejects_flattened_disambiguation_entries():
    text = (
        "九龍山可以指：\n\n"
        "九龙山 (天津)，天津市国家森林公园。 "
        "九龙山 (嘉兴)，浙江省嘉兴市国家森林公园。 "
        "九龍山 (香港)，香港九龙半岛的一座山。 "
        "九龍山 (首尔)，韩国首尔附近的一座山峰。"
    )

    assert homepage_text_quality_issue(text, "平湖九龙山旅游度假区", require_fact_ready=False) == (
        "disambiguation_homepage"
    )


def test_homepage_gate_rejects_disambiguation_intro_with_many_unrelated_facts():
    text = (
        "铁佛寺，可能是指以下事物：\n\n"
        "鐵佛寺 (湖州)，位于浙江湖州，浙江省文物保护单位。\n"
        "銅梁鐵佛寺，位于重庆铜梁县，重庆市文物保护单位。\n"
        "铁佛寺 (临汾)，位于山西临汾，中国全国重点文物保护单位。\n"
        "高平铁佛寺，位于山西晋城高平，山西省文物保护单位。"
    )
    assert homepage_text_quality_issue(text, "湖州铁佛寺") == "disambiguation_homepage"


def test_homepage_gate_accepts_fact_rich_text():
    rich = (
        "黄龙风景名胜区位于test-region-b阿坝藏族羌族自治州松潘县，海拔1700米至5588米。\n\n"
        "景区占地700平方公里，1992年被列入世界自然遗产名录。\n\n"
        "黄龙以彩池、雪山、峡谷、森林四绝著称，主要景点包括五彩池、争艳池、迎宾池。\n\n"
        "景区开放时间为8:00-17:00，门票旺季170元，可在官网预约购票。\n\n"
        "黄龙沟全长约7.5公里，钙华滩流是其核心地质景观。"
    )
    assert homepage_text_quality_issue(rich, "黄龙风景名胜区") == ""


def test_homepage_gate_preserves_structured_line_facts_before_counting():
    text = (
        "越剧小镇位于test-region-a嵊州市，也是女子越剧诞生地。\n"
        "小镇包括剧院、工坊、艺术家村落和百亩果园。\n"
        "项目占地百余亩，集现代农业、休闲旅游和文化创意于一体。\n"
        "园区坐落在剡溪之畔，主要文化设施包括越剧艺术学校。"
    )

    assert homepage_text_quality_issue(text, "越剧小镇") == ""


def test_homepage_gate_does_not_treat_travel_station_guidance_as_station_entity():
    text = (
        "中南百草原位于test-region-a湖州市安吉县，占地5600亩，是国家AAAA级旅游景区。\n\n"
        "景区包含植物世界、动物世界和运动世界，核心游览区设有湿地、竹林和草原。\n\n"
        "园区开放时间为8:00至17:00，游客可通过官方渠道预约门票。\n\n"
        "乘高铁至湖州站后可换乘旅游专线，车站有直达安吉的客运班次。\n\n"
        "自驾游客可从杭长高速百丈出口前往，全程约30公里。"
    )

    assert homepage_text_quality_issue(text, "中南百草原") == ""


def test_homepage_gate_rejects_unrelated_taxonomy_page_without_keyword_blacklist():
    text = (
        "中华大刀螳学名为Tenodera sinensis，属于昆虫纲螳螂目螳科。\n\n"
        "该物种体长约90毫米，主要分布于东亚地区。\n\n"
        "成虫具有发达的前足，通常栖息于草地和灌木。\n\n"
        "雌虫可产多个卵鞘，每个卵鞘包含数百枚卵。"
    )

    assert homepage_text_quality_issue(text, "中南百草原") == "insufficient_homepage_facts"


def test_homepage_source_image_count_excludes_locator_maps():
    assert _publishable_homepage_source_image_count(
        [
            {"isMapLike": True},
            {"placementType": "locatorMap"},
            {"coverCandidateRank": -1},
            {"coverCandidateRank": 1, "placementType": "infoboxLead"},
        ]
    ) == 1


def test_source_image_normalization_preserves_layout_semantics():
    rows = _normalize_image_specs(
        [
            {
                "url": "https://upload.wikimedia.org/map.jpg",
                "placementType": "locatorMap",
                "groupId": "map-group",
                "sectionSlug": "位置",
                "sourceOrder": 3,
                "coverCandidateRank": -1,
                "isMapLike": True,
                "fileTitle": "File:Map.jpg",
            }
        ]
    )

    assert rows[0]["placementType"] == "locatorMap"
    assert rows[0]["groupId"] == "map-group"
    assert rows[0]["sectionSlug"] == "位置"
    assert rows[0]["sourceOrder"] == 3
    assert rows[0]["coverCandidateRank"] == -1
    assert rows[0]["isMapLike"] is True
    assert rows[0]["fileTitle"] == "File:Map.jpg"


# ---------------------------------------------------------------------------
# 事实化压缩
# ---------------------------------------------------------------------------

def test_compression_policy_tiers():
    assert compression_policy(800) == ("none", 1.0)
    assert compression_policy(1500) == ("light", 0.75)
    assert compression_policy(2500) == ("factual_half", 0.5)


def test_factual_compress_keeps_short_text_unchanged():
    text = "都江堰位于test-region-b成都市。始建于公元前256年。"
    result = factual_compress_text(text, entity_name="都江堰")
    assert result["policy"] == "none"
    assert result["text"] == text


def test_factual_compress_halves_long_text_and_keeps_facts():
    fact = "都江堰位于test-region-b成都市，始建于公元前256年，占地约200平方公里。"
    filler = "这里的风光真是让人流连忘返，随手一拍就是大片，朋友们都说不虚此行，下次还想再来。"
    paragraphs = []
    for _ in range(20):
        paragraphs.append(fact + filler + filler)
    text = "## 概况\n\n" + "\n\n".join(paragraphs)
    result = factual_compress_text(text, entity_name="都江堰")
    assert result["policy"] == "factual_half"
    # 压缩后显著小于原文（目标 ~50%，允许边界波动）。
    assert result["compressedChars"] < result["originalChars"] * 0.75
    # 结构行恒保留；事实句保留。
    assert "## 概况" in result["text"]
    assert "公元前256年" in result["text"]


def test_factual_compress_preserves_figure_placeholder_lines():
    fact = "青城山位于test-region-b都江堰市西南，最高峰海拔1260米，是中国道教发祥地之一。"
    filler = "山间云雾缭绕美不胜收，游人如织好不热闹，来过的人都说还想再来一次。"
    body = "\n\n".join((fact + filler * 3) for _ in range(15))
    text = f"## 简介\n\n:::figure\nasset://source-inline-001\n:::\n\n{body}"
    result = factual_compress_text(text, entity_name="青城山")
    assert ":::figure" in result["text"]
    assert "asset://source-inline-001" in result["text"]


# ---------------------------------------------------------------------------
# URL 消重与非开放源识别
# ---------------------------------------------------------------------------

def test_canonicalize_source_url_normalizes_variants():
    a = _canonicalize_source_url("https://zh.wikipedia.org/wiki/黄龙风景名胜区")
    b = _canonicalize_source_url("http://ZH.WIKIPEDIA.ORG/wiki/黄龙风景名胜区/?from=search#history")
    # 大小写：host 归一后路径大小写保留原样（中文路径无大小写差异）。
    assert a == b.replace("zh.wikipedia.org", "zh.wikipedia.org")
    assert a == "zh.wikipedia.org/wiki/黄龙风景名胜区"
    assert _canonicalize_source_url("") == ""


def test_is_non_open_baike_source_detects_baidu_and_toutiao():
    # 来源使用模式只接受 registry 中已冻结的 sourceKind，不按 URL host 猜测。
    assert _is_non_open_baike_source(
        {"sourceKind": "baidu_baike", "url": "https://baike.baidu.com/item/黄龙/123"}
    )
    assert _is_non_open_baike_source(
        {"sourceKind": "toutiao_baike", "url": "https://www.baike.com/wiki/黄龙"}
    )
    assert not _is_non_open_baike_source(
        {"sourceKind": "wikipedia", "url": "https://zh.wikipedia.org/wiki/黄龙"}
    )


def test_homepage_fetch_uses_shared_base_draft_admission(monkeypatch):
    captured: dict[str, object] = {}

    def shared_readiness(meta, text, **kwargs):
        captured["meta"] = meta
        captured["text"] = text
        captured["kwargs"] = kwargs
        return {"ready": True, "factCount": 4}

    monkeypatch.setattr(
        "content.homepage.homepage_text.homepage_base_draft_readiness",
        shared_readiness,
    )
    admission = homepage_base_draft_admission(
        {
            "researchLane": "homepage",
            "sourceKind": "baidu_baike",
            "sourceTitle": "莫氏庄园",
            "qualifiedAuthorityTitle": "莫氏庄园",
        },
        source_text="莫氏庄园有足够的事实正文。",
        entity_id="平湖莫氏庄园",
        resolved_title="莫氏庄园",
    )

    assert admission.accepted is True
    assert admission.fact_count == 4
    assert admission.issue_code is None
    assert captured["meta"]["resolvedTitle"] == "莫氏庄园"
    assert captured["kwargs"]["aliases"] == ("莫氏庄园",)


def test_source_fetch_exception_is_converted_to_typed_issue():
    issue = _source_fetch_failure_issue(
        {"source_id": "home_baidu_baike", "researchLane": "homepage"},
        entity_id="杭州金沙湖",
        error=TimeoutError("request timed out"),
    )
    assert issue.code.value == "DATA.SOURCE.UNREADABLE"
    assert issue.lane.value == "homepage"
    assert issue.recovery.value == "retry_source_discovery"
    assert dict(issue.attributes)["errorType"] == "TimeoutError"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"homepage quality/dedupe tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
