"""Homepage summary must preserve facts without duplicating the page H1."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.homepage.homepage_text import _homepage_summary, _split_fact_sentences  # noqa: E402


def test_homepage_summary__dedupes_joined_h1_and_opening_fact__functional__local_contract() -> None:
    summary = _homepage_summary(
        "普陀山",
        ["# 普陀山\n普陀山，是中华人民共和国浙江省舟山群岛中的一个岛屿。"],
    )

    assert summary == "普陀山，是中华人民共和国浙江省舟山群岛中的一个岛屿。"


def test_homepage_summary__preserves_single_entity_prefix__functional__local_contract() -> None:
    summary = _homepage_summary("东钱湖", ["东钱湖，亦称东湖、万金湖，位于宁波市。"]) 

    assert summary == "东钱湖，亦称东湖、万金湖，位于宁波市。"


def test_homepage_summary__excludes_markdown_section_heading__functional__local_contract() -> None:
    page = """# 海螺沟

## 概况

海螺沟位于中国四川省甘孜藏族自治州泸定县境内，磨西镇旁，是国家5A级旅游景区。
"""
    facts = _split_fact_sentences(page, entity_name="海螺沟")

    summary = _homepage_summary("海螺沟", facts, base_text=page)

    assert summary == "海螺沟位于中国四川省甘孜藏族自治州泸定县境内，磨西镇旁，是国家5A级旅游景区。"
