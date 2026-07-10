"""homepage 源质量门 / 同实体 URL 消重 / 非开放源事实化压缩 合同测试。

覆盖（quality-dedupe-backfill 交付项）：
1. homepage_text_quality_issue：弱事实文本（西岭雪山类）与消歧义页必须打回，富事实文本放行。
2. factual_compress_text：<=1000 不压缩；>2000 压至约 50% 并保留结构行与事实句。
3. handler_fetch 消重/归一 helper：canonical URL 归一、百度/搜狗百科识别。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.factual_compression import compression_policy, factual_compress_text  # noqa: E402
from download.handler_fetch import (  # noqa: E402
    _canonicalize_source_url,
    _is_non_open_baike_source,
)
from download.research.source_quality import homepage_text_quality_issue  # noqa: E402


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
        "- 成都武侯祠：位于四川省成都市武侯区。\n"
        "- 勉县武侯祠：位于陕西省汉中市勉县。\n"
        "- 南阳武侯祠：位于河南省南阳市。\n"
        "- 白帝城武侯祠：位于重庆市奉节县。\n"
    )
    assert homepage_text_quality_issue(text, "武侯祠") == "disambiguation_homepage"


def test_homepage_gate_accepts_fact_rich_text():
    rich = (
        "黄龙风景名胜区位于四川省阿坝藏族羌族自治州松潘县，海拔1700米至5588米。\n\n"
        "景区占地700平方公里，1992年被列入世界自然遗产名录。\n\n"
        "黄龙以彩池、雪山、峡谷、森林四绝著称，主要景点包括五彩池、争艳池、迎宾池。\n\n"
        "景区开放时间为8:00-17:00，门票旺季170元，可在官网预约购票。\n\n"
        "黄龙沟全长约7.5公里，钙华滩流是其核心地质景观。"
    )
    assert homepage_text_quality_issue(rich, "黄龙风景名胜区") == ""


# ---------------------------------------------------------------------------
# 事实化压缩
# ---------------------------------------------------------------------------

def test_compression_policy_tiers():
    assert compression_policy(800) == ("none", 1.0)
    assert compression_policy(1500) == ("light", 0.75)
    assert compression_policy(2500) == ("factual_half", 0.5)


def test_factual_compress_keeps_short_text_unchanged():
    text = "都江堰位于四川省成都市。始建于公元前256年。"
    result = factual_compress_text(text, entity_name="都江堰")
    assert result["policy"] == "none"
    assert result["text"] == text


def test_factual_compress_halves_long_text_and_keeps_facts():
    fact = "都江堰位于四川省成都市，始建于公元前256年，占地约200平方公里。"
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
    fact = "青城山位于四川省都江堰市西南，最高峰海拔1260米，是中国道教发祥地之一。"
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


def test_is_non_open_baike_source_detects_baidu_and_sogou():
    assert _is_non_open_baike_source({"url": "https://baike.baidu.com/item/黄龙/123"})
    assert _is_non_open_baike_source({"url": "https://baike.sogou.com/v123.htm"})
    assert not _is_non_open_baike_source({"url": "https://zh.wikipedia.org/wiki/黄龙"})


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"homepage quality/dedupe tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
