# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md
"""article/homepage 来源单元必须解析出 pool delivery 要求的 sourceAttribution。

pool delivery 对 post manifest 的 ``sourceAttribution`` 是 fail-closed 的，而 post
manifest 只能从来源单元 meta 继承它。来源阶段一旦静默省略该字段，缺口要到 publish
收口才暴露成一条无信息的 OBJECT_PREPARATION_FAILED，所以把它钉成来源阶段的契约。
"""

from __future__ import annotations

import pytest
from content.source.source_unit_attribution import resolve_source_unit_attribution
from core.source_attribution import canonical_source_attribution

_SOURCE_URL = "https://zh.wikipedia.org/wiki/青城山"
_CAPTURED_AT = "2026-08-15T04:51:15Z"

_WIKIPEDIA_PAYLOAD = {
    "articleSiteId": "wikipedia_zh",
    "sourceKind": "encyclopedia",
    "extractor": "wikipedia_api",
    "platform": "维基百科",
    "researchLane": "article",
}


@pytest.mark.parametrize("research_lane", ["article", "homepage"])
def test_wikipedia_source_unit_resolves_pool_delivery_attribution(
    research_lane: str,
) -> None:
    resolved = resolve_source_unit_attribution(
        dict(_WIKIPEDIA_PAYLOAD),
        research_lane=research_lane,
        resolved_source_kind="encyclopedia",
        source_url=_SOURCE_URL,
        captured_at=_CAPTURED_AT,
    )

    assert resolved is not None, (
        "article/homepage 来源单元缺 sourceAttribution，"
        "pool delivery 会在 publish 阶段 fail-closed"
    )
    attribution = canonical_source_attribution(resolved)
    assert attribution["platform"] == "维基百科"
    assert attribution["rightsBasis"] == "CC BY-SA 4.0"
    assert attribution["publicationAdmission"] == "research_release"
    assert attribution["sourcePostUrl"] == _SOURCE_URL
    assert attribution["collectedAt"] == _CAPTURED_AT


def test_source_kind_alone_resolves_attribution() -> None:
    """采集载荷未带 articleSiteId 时，来源类别仍必须能解析出 attribution。"""

    resolved = resolve_source_unit_attribution(
        {},
        research_lane="article",
        resolved_source_kind="wikipedia",
        source_url=_SOURCE_URL,
        captured_at=_CAPTURED_AT,
    )

    assert resolved is not None
    assert canonical_source_attribution(resolved)["platform"] == "维基百科"


def test_unmapped_article_site_fails_closed_instead_of_omitting() -> None:
    with pytest.raises(ValueError, match="sourceAttribution cannot be resolved"):
        resolve_source_unit_attribution(
            {"articleSiteId": "unmapped_site"},
            research_lane="article",
            resolved_source_kind="unmapped_kind",
            source_url=_SOURCE_URL,
            captured_at=_CAPTURED_AT,
        )


def test_non_publishing_lane_stays_optional() -> None:
    """image/video 载体不经过这条 attribution 契约，保持可选。"""

    assert (
        resolve_source_unit_attribution(
            {"articleSiteId": "unmapped_site"},
            research_lane="image",
            resolved_source_kind="stock_photo",
            source_url=_SOURCE_URL,
            captured_at=_CAPTURED_AT,
        )
        is None
    )
