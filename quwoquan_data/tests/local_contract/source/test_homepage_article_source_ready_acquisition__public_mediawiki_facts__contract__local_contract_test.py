"""场景组：homepage 结构化事实闭集抽取与治理来源分轨。

homepage/article source-ready acquisition 契约测试（public mediawiki）。

从 test_homepage_article_source_ready_acquisition__public_mediawiki__contract__local_contract_test.py
按场景拆出：渲染正文闭集事实抽取、头条百科独立事实轨回退、无闭集事实保持
拒绝；测试逐字搬移。共享常量与构造 helper 见
tests/support/homepage_article_source_ready_acquisition_fixture.py。
"""

from __future__ import annotations

import json

import pytest
from content.source.mediawiki_page import MediaWikiPageBundle
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredAsset,
    MediaWikiSourceReadyRejected,
    acquire_mediawiki_source_ready_candidate,
)
from support.homepage_article_source_ready_acquisition_fixture import (
    CAPTURED_AT,
    IDENTITY,
    _asset_document,
    _planned,
    _sha,
)


def _fact_bundle(body: str, wikitext: str = "{{Infobox}}") -> MediaWikiPageBundle:
    return MediaWikiPageBundle(
        requested_title="测试景区",
        resolved_title="测试景区",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext=wikitext,
        rendered_image_titles=("File:a.jpg",),
        raw='{"query":{"pages":{"10":{}}}}',
    )


def test_mediawiki_homepage_fact_extracts_governed_field_from_rendered_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """infobox 无闭集字段时，同一 Wikipedia 渲染正文中的闭集事实必须被抽取。"""
    from content.source.research import homepage_article_source_ready_mediawiki as mod

    body = (
        "测试景区位于成都市，历史悠久并保存多处文化遗产，海拔约2070米。\n"
        "景区包含湖泊、园林和展馆，公共交通可到达。\n\n"
        "游客可以沿步道参观不同区域，了解当地历史、生态保护与社区文化。"
        "园区设有导览、休息和无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = _fact_bundle(body)
    monkeypatch.setattr(
        mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle
    )
    monkeypatch.setattr(
        mod,
        "_mediawiki_page_images",
        lambda *a, **k: [
            {
                "url": "https://upload.wikimedia.org/a.jpg",
                "pageRevisionId": 20,
                "pageContentSha256": "page-sha",
            }
        ],
    )
    monkeypatch.setattr(
        mod,
        "wikidata_structured_fact",
        lambda *a, **k: pytest.fail("body fact must win before Wikidata"),
    )

    def acquire_assets(_rows, *, source_unit_ref, roles, captured_at):
        document, asset_body = _asset_document(
            source_unit_ref=source_unit_ref, role=roles[0], seed="body-fact-hero"
        )
        return (AcquiredAsset(body=asset_body, document=document),)

    monkeypatch.setattr(mod, "acquire_open_image_assets", acquire_assets)
    acquired = acquire_mediawiki_source_ready_candidate(
        _planned("测试景区"),
        carrier="homepage",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    facts = acquired.candidate["structuredFacts"]
    assert facts["altitudeMeters"] == 2070
    assert facts["factSources"][0]["sourceId"] == "wikipedia"
    assert facts["factSources"][0]["sourceClass"] == "encyclopedia"
    fact_evidence = acquired.candidate["factEvidence"][0]
    assert fact_evidence["evidenceRef"].endswith("source.md")


def test_mediawiki_homepage_fact_falls_back_to_governed_baike_fact_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wikipedia/Wikidata 双双无闭集事实时，事实轨允许独立的头条百科证据源，正文仍绑定 Wikipedia。"""
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from content.source.research.baike_com import BaikePageResolution

    body = (
        "测试景区位于成都市，历史悠久并保存多处文化遗产。\n"
        "景区包含湖泊、园林和展馆，公共交通可到达。\n\n"
        "游客可以沿步道参观不同区域，了解当地历史、生态保护与社区文化。"
        "园区设有导览、休息和无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = _fact_bundle(body)
    monkeypatch.setattr(
        mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle
    )
    monkeypatch.setattr(
        mod,
        "_mediawiki_page_images",
        lambda *a, **k: [
            {
                "url": "https://upload.wikimedia.org/a.jpg",
                "pageRevisionId": 20,
                "pageContentSha256": "page-sha",
            }
        ],
    )
    monkeypatch.setattr(mod, "wikidata_structured_fact", lambda *a, **k: None)
    observed_geo: list[tuple[str, ...]] = []

    def resolve(entity_id: str, *, geo_context_terms=(), **_: object):
        observed_geo.append(tuple(geo_context_terms))
        assert entity_id == "测试景区"
        return BaikePageResolution(
            url="https://www.baike.com/wikiid/123",
            title="测试景区",
            matched_term="测试景区",
            match_confidence=0.95,
        )

    monkeypatch.setattr(mod, "resolve_toutiao_baike_page", resolve)
    monkeypatch.setattr(
        mod,
        "fetch_source_payload",
        lambda url, **_: {
            "text": "测试景区门票价格为50元，全年对公众开放。",
            "htmlBytes": b"<html>baike</html>",
        },
    )

    def acquire_assets(_rows, *, source_unit_ref, roles, captured_at):
        document, asset_body = _asset_document(
            source_unit_ref=source_unit_ref, role=roles[0], seed="baike-fact-hero"
        )
        return (AcquiredAsset(body=asset_body, document=document),)

    monkeypatch.setattr(mod, "acquire_open_image_assets", acquire_assets)
    acquired = acquire_mediawiki_source_ready_candidate(
        _planned("测试景区"),
        carrier="homepage",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    assert observed_geo == [("测试省甲", "测试市甲", "测试区甲")]
    facts = acquired.candidate["structuredFacts"]
    assert facts["ticketPriceRange"] == {
        "currency": "CNY",
        "minAmountCents": 5000,
        "maxAmountCents": 5000,
        "free": False,
    }
    fact_source = facts["factSources"][0]
    assert fact_source["sourceId"] == "toutiao_baike"
    assert fact_source["sourceClass"] == "encyclopedia"
    assert fact_source["sourceUrl"] == "https://www.baike.com/wikiid/123"
    fact_evidence = acquired.candidate["factEvidence"][0]
    assert str(fact_evidence["evidenceRef"]).startswith("raw/homepage/")
    assert fact_evidence["contentSha256"] == _sha(acquired.raw_evidence)
    raw = json.loads(acquired.raw_evidence.decode("utf-8"))
    assert "mediawikiRaw" in raw
    baike_raw = json.loads(raw["baikeRaw"])
    assert baike_raw["sourceUrl"] == "https://www.baike.com/wikiid/123"
    assert "门票价格" in baike_raw["bodyText"]
    # 正文轨保持 Wikipedia 绑定，不因事实轨换源。
    assert acquired.candidate["primarySource"]["sourceKind"] == "wikipedia"


def test_mediawiki_homepage_without_any_governed_fact_stays_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod

    body = (
        "测试景区位于成都市，历史悠久并保存多处文化遗产。\n"
        "景区包含湖泊、园林和展馆，公共交通可到达。\n\n"
        "游客可以沿步道参观不同区域，了解当地历史、生态保护与社区文化。"
        "园区设有导览、休息和无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = _fact_bundle(body)
    monkeypatch.setattr(
        mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle
    )
    monkeypatch.setattr(mod, "wikidata_structured_fact", lambda *a, **k: None)
    monkeypatch.setattr(mod, "resolve_toutiao_baike_page", lambda *a, **k: None)
    with pytest.raises(MediaWikiSourceReadyRejected) as captured:
        acquire_mediawiki_source_ready_candidate(
            _planned("测试景区"),
            carrier="homepage",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
        )
    assert "lacks an immutable structured fact" in str(captured.value)
