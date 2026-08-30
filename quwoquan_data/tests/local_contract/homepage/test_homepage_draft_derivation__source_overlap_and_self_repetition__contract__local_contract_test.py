# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-006
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-006.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-006.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-006.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-006.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-006.t5
"""homepage 正文派生度判据：复述原文与自我重复在 4.draft 自检即判否且点名到段落。

三份用例的字数与章节都已达标，因此它们只可能被派生度判据拦下——这正是本判据要
补的口径：只判字数与章节均衡时，复述原文与复读都能通过。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.homepage.quality_policy import (  # noqa: E402
    homepage_derivation_paragraph_char_minimum,
    homepage_intra_body_similarity_limit,
    homepage_source_paragraph_overlap_limit,
)
from content.homepage.draft_derivation import (  # noqa: E402
    paragraph_repetition_findings,
    paragraph_repetition_issues,
    source_overlap_findings,
    source_overlap_issues,
)
from governance.content_supply_policy import load_content_supply_policy  # noqa: E402


EXECUTION_ID = "20260722--travel-homepage-generate--test-region-a--pilot-001"

# 底稿 source.clean.md：正文事实落在第 7 行与第 9 行，中间隔一个空行。
SOURCE_CLEAN = """---
title: 九寨沟
---

# 九寨沟

九寨沟位于四川省阿坝藏族羌族自治州九寨沟县境内，是长江水系嘉陵江支流白水江上游白河的支沟，海拔在两千米以上。

沟内分布着一百一十四个高山湖泊，以及十七个瀑布群、五处钙华滩流，被誉为人间仙境。

一九九二年被联合国教科文组织列入世界自然遗产名录。
"""

# 复述原文：把底稿第 7 行与第 9 行原样搬进同一段。
VERBATIM_PAGE = """## 概览

九寨沟位于四川省阿坝藏族羌族自治州九寨沟县境内，是长江水系嘉陵江支流白水江上游白河的支沟，海拔在两千米以上。沟内分布着一百一十四个高山湖泊，以及十七个瀑布群、五处钙华滩流，被誉为人间仙境。
"""

# 自我重复：两段只差「听见/听到」与「声音/声响」。
REPEATED_PAGE = """## 清晨

清晨的湖面几乎没有风，倒影把对岸的针叶林压成一条深绿的带子，走在栈道上能听见水从钙华台阶漫过去的声音，节奏很慢，让人愿意多停一会儿。

## 午后

清晨的湖面几乎没有风，倒影把对岸的针叶林压成一条深绿的带子，走在栈道上能听到水从钙华台阶漫过去的声响，节奏很慢，让人愿意多停一会儿。
"""

# 独立改写：与底稿共享实体名与主题，但不共享逐字片段，两段之间也各说各的事实。
REWRITTEN_PAGE = """## 印象

九寨沟给人的第一印象往往不是海拔与水系这些数字，而是水色随光线变化的节奏，走在栈道上很容易忘记时间，湖面通透得能看清水下倒伏了多年的枯木。

## 节奏

午后的光线转硬，湖水的蓝会往青色偏，游人多半集中在几个观景平台，想拍到没有人影的水面得往沟口方向再走一段路，避开团队的行进节奏。
"""


def _overlap_limit() -> float:
    return homepage_source_paragraph_overlap_limit(EXECUTION_ID)


def _similarity_limit() -> float:
    return homepage_intra_body_similarity_limit(EXECUTION_ID)


def _paragraph_minimum() -> int:
    return homepage_derivation_paragraph_char_minimum(EXECUTION_ID)


def test_source_overlap__verbatim_paragraph_is_named_with_source_line_span__local_contract() -> None:
    """GWT-006.t1：逐字同构段落判否，并点名正文段落序号与底稿行号区间。"""
    findings = source_overlap_findings(
        VERBATIM_PAGE,
        SOURCE_CLEAN.splitlines(),
        max_overlap_ratio=_overlap_limit(),
        minimum_paragraph_chars=_paragraph_minimum(),
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.paragraph_index == 1
    assert finding.overlap_ratio > _overlap_limit()
    # 底稿事实落在第 7 行与第 9 行，中间的空行不该把区间切断。
    assert (finding.source_line_start, finding.source_line_end) == (7, 9)

    issues = source_overlap_issues(
        VERBATIM_PAGE,
        SOURCE_CLEAN.splitlines(),
        max_overlap_ratio=_overlap_limit(),
        minimum_paragraph_chars=_paragraph_minimum(),
        label="travel/scenic_spot/九寨沟",
    )
    assert len(issues) == 1
    assert "正文第 1 段" in issues[0]
    assert "底稿第 7-9 行" in issues[0]


def test_intra_body_repetition__both_paragraph_indexes_are_named__local_contract() -> None:
    """GWT-006.t2：互为复读的两段判否，并点名两个正文段落序号。"""
    findings = paragraph_repetition_findings(
        REPEATED_PAGE,
        max_similarity=_similarity_limit(),
        minimum_paragraph_chars=_paragraph_minimum(),
    )

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.first_paragraph_index, finding.second_paragraph_index) == (1, 2)
    assert finding.similarity > _similarity_limit()

    issues = paragraph_repetition_issues(
        REPEATED_PAGE,
        max_similarity=_similarity_limit(),
        minimum_paragraph_chars=_paragraph_minimum(),
        label="travel/scenic_spot/九寨沟",
    )
    assert len(issues) == 1
    assert "正文第 1 段与第 2 段" in issues[0]


def test_rewritten_body__shared_entity_name_and_topic_do_not_trigger__local_contract() -> None:
    """GWT-006.t3：独立改写不被判否，共享专有名词与主题不构成逐字重合。"""
    assert (
        source_overlap_findings(
            REWRITTEN_PAGE,
            SOURCE_CLEAN.splitlines(),
            max_overlap_ratio=_overlap_limit(),
            minimum_paragraph_chars=_paragraph_minimum(),
        )
        == []
    )
    assert (
        paragraph_repetition_findings(
            REWRITTEN_PAGE,
            max_similarity=_similarity_limit(),
            minimum_paragraph_chars=_paragraph_minimum(),
        )
        == []
    )


def test_thresholds__come_from_vertical_policy_and_cannot_be_omitted__local_contract() -> None:
    """GWT-006.t4：判否线取自 vertical policy 显式声明，判据不接受省略阈值的调用。"""
    policy = load_content_supply_policy("travel")
    assert _overlap_limit() == policy.homepage_max_source_paragraph_overlap
    assert _similarity_limit() == policy.homepage_max_intra_body_paragraph_similarity
    assert _paragraph_minimum() == policy.homepage_derivation_paragraph_minimum_chars

    # 阈值是必填关键字：判据内没有可被静默使用的默认值。
    with pytest.raises(TypeError):
        source_overlap_findings(VERBATIM_PAGE, SOURCE_CLEAN.splitlines())  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        paragraph_repetition_findings(REPEATED_PAGE)  # type: ignore[call-arg]


def test_derivation_findings__same_input_yields_identical_findings__local_contract() -> None:
    """GWT-006.t5：同输入同结论，段落序号与行号区间逐字一致。"""
    overlap_runs = [
        source_overlap_findings(
            VERBATIM_PAGE,
            SOURCE_CLEAN.splitlines(),
            max_overlap_ratio=_overlap_limit(),
            minimum_paragraph_chars=_paragraph_minimum(),
        )
        for _ in range(3)
    ]
    repetition_runs = [
        paragraph_repetition_findings(
            REPEATED_PAGE,
            max_similarity=_similarity_limit(),
            minimum_paragraph_chars=_paragraph_minimum(),
        )
        for _ in range(3)
    ]

    assert overlap_runs[0] == overlap_runs[1] == overlap_runs[2]
    assert repetition_runs[0] == repetition_runs[1] == repetition_runs[2]
