"""场景组：MediaWiki provider 公开正文、原始媒体与权利证据。

homepage/article source-ready acquisition 契约测试（public mediawiki）。

由 1000 行硬顶拆分：本文件保留 MediaWiki/Commons/Openverse provider 的媒体
补充、权利与页面身份场景组；批处理生命周期组见
test_homepage_article_source_ready_acquisition__public_mediawiki_batch__contract__local_contract_test.py；
幂等 resume 组见 ..._resume__contract__...；article frontier 回退组见
..._article_fallback__contract__...；结构化事实闭集组见
..._facts__contract__...；共享常量与构造 helper 下沉
tests/support/homepage_article_source_ready_acquisition_fixture.py。
测试逐字搬移。
"""
from __future__ import annotations

import pytest
from content.source.mediawiki_page import MediaWikiPageBundle
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredAsset,
    MediaWikiSourceReadyRejected,
    acquire_mediawiki_source_ready_candidate,
    acquire_open_image_assets,
)
from content.source.research.network_io import HttpFetchResult
from core.image_decode import ImageProbe
from core.image_safety import ImageVerdict
from support.homepage_article_source_ready_acquisition_fixture import (
    CAPTURED_AT,
    IDENTITY,
    _asset_document,
    _planned,
    _sha,
)


def test_wikidata_official_website_is_frozen_as_raw_fact_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from content.source.research import (
        homepage_article_source_ready_wikidata as wikidata,
    )
    from content.source.research.homepage_source_unit_catalog import (
        build_homepage_source_unit_catalog,
    )

    body = (
        "测试景区位于成都市，历史悠久并保存多处文化遗产。\n"
        "景区包含湖泊、园林和展馆，公共交通可到达。\n\n"
        "游客可以沿步道参观不同区域，了解当地历史、生态保护与社区文化。"
        "园区设有导览、休息和无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = MediaWikiPageBundle(
        requested_title="测试景区",
        resolved_title="测试景区",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext="{{Infobox}}",
        rendered_image_titles=("File:a.jpg",),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    monkeypatch.setattr(mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle)
    monkeypatch.setattr(
        mod,
        "_mediawiki_page_images",
        lambda *a, **k: [{"url": "https://upload.wikimedia.org/a.jpg", "pageRevisionId": 20, "pageContentSha256": "page-sha"}],
    )
    monkeypatch.setattr(
        wikidata.network_io,
        "wiki_api",
        lambda *a, **k: {"query": {"pages": {"10": {"pageprops": {"wikibase_item": "Q123"}}}}},
    )
    monkeypatch.setattr(
        wikidata.network_io,
        "curl_json",
        lambda *a, **k: {
            "entities": {
                "Q123": {
                    "claims": {
                        "P856": [{"mainsnak": {"datavalue": {"value": "http://official.example.test/"}}}]
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        wikidata.network_io,
        "fetch_http",
        lambda *a, **k: HttpFetchResult(
            0, 200, "https://official.example.test/", b"official"
        ),
    )

    def acquire_assets(_rows, *, source_unit_ref, roles, captured_at):
        document, asset_body = _asset_document(
            source_unit_ref=source_unit_ref, role=roles[0], seed="wikidata-hero"
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

    assert acquired.candidate["structuredFacts"]["officialWebsite"] == "https://official.example.test/"
    fact = acquired.candidate["factEvidence"][0]
    assert fact["sourceId"] == "official_site"
    assert str(fact["evidenceRef"]).startswith("raw/homepage/")
    assert fact["contentSha256"] == _sha(acquired.raw_evidence)
    assert b"Q123" in acquired.raw_evidence
    assert b"officialWebsiteAccess" in acquired.raw_evidence
    catalog = build_homepage_source_unit_catalog(
        catalog_id="wikidata-official-site",
        created_at=CAPTURED_AT,
        minimum_candidate_count=1,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        candidates=[acquired.candidate],
    )
    assert catalog["candidates"][0]["structuredFacts"]["factSources"][0][
        "sourceClass"
    ] == "official_site"


@pytest.mark.parametrize("carrier", ("homepage", "article"))
def test_mediawiki_supplements_sparse_page_images_with_entity_matched_originals(
    carrier: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod

    body = (
        "测试景区位于成都市，历史悠久并保存多处文化遗产。\n"
        "景区包含湖泊、园林和展馆，公共交通可到达。\n\n"
        "游客可以沿步道参观不同区域，了解当地历史、生态保护与社区文化。"
        "园区设有导览、休息和无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = MediaWikiPageBundle(
        requested_title="测试景区",
        resolved_title="测试景区",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext=(
            "{{Infobox\n"
            "| website = https://example.test/official\n"
            "}}"
        ),
        rendered_image_titles=("File:a.jpg",),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    page_image = {"url": "https://upload.wikimedia.org/a.jpg", "pageRevisionId": 20, "pageContentSha256": "page-sha"}
    supplement = {"url": "https://images.openverse.org/b.jpg", "sourceUrl": "https://example.test/b"}
    page_images = [] if carrier == "homepage" else [page_image]
    monkeypatch.setattr(mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle)
    monkeypatch.setattr(mod, "_mediawiki_page_images", lambda *a, **k: page_images)
    monkeypatch.setattr(
        mod,
        "wikidata_commons_images_for_entity",
        lambda *a, **k: [supplement] if carrier == "homepage" else [],
    )
    monkeypatch.setattr(mod, "commons_images_for_entity", lambda *a, **k: [])
    monkeypatch.setattr(
        mod,
        "openverse_images_for_entity",
        lambda *a, **k: [supplement] if carrier == "article" else [],
    )
    captured_rows: list[dict[str, object]] = []

    def acquire_assets(rows, *, source_unit_ref, roles, captured_at):
        captured_rows.extend(rows)
        result = []
        for index, role in enumerate(roles):
            document, asset_body = _asset_document(
                source_unit_ref=source_unit_ref, role=role, seed=f"supplement-{index}"
            )
            result.append(AcquiredAsset(body=asset_body, document=document))
        return tuple(result)

    monkeypatch.setattr(mod, "acquire_open_image_assets", acquire_assets)
    acquired = acquire_mediawiki_source_ready_candidate(
        _planned("测试景区"),
        carrier=carrier,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    assert len(acquired.assets) == (1 if carrier == "homepage" else 2)
    expected_urls = (
        [supplement["url"]]
        if carrier == "homepage"
        else [page_image["url"], supplement["url"]]
    )
    assert [row["url"] for row in captured_rows] == expected_urls


def test_public_domain_commons_file_page_is_the_https_terms_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from core import image_decode

    monkeypatch.setattr(
        mod.network_io,
        "fetch_http",
        lambda *a, **k: HttpFetchResult(0, 200, str(a[0]), b"public-domain-image"),
    )
    monkeypatch.setattr(
        mod,
        "assess_image",
        lambda *a, **k: ImageVerdict(
            path="fixture",
            status="safe",
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(),
            backends=("cv", "ocr"),
        ),
    )
    monkeypatch.setattr(
        image_decode,
        "probe_image_bytes",
        lambda body: ImageProbe(width=1600, height=1000, mime_type="image/jpeg"),
    )
    source_page = "https://commons.wikimedia.org/wiki/File:Public_domain.jpg"
    acquired = mod.acquire_open_image_assets(
        [
            {
                "url": "https://upload.wikimedia.org/public-domain.jpg",
                "sourceUrl": source_page,
                "license": "Public domain",
                "termsUrl": "",
                "authorizationProof": source_page,
                "creator": "Archive author",
                "credit": "Archive author",
                "usageScope": "app_publish",
                "modelReleaseStatus": "not_required",
            }
        ],
        source_unit_ref="sources/public-domain",
        roles=("hero",),
        captured_at=CAPTURED_AT,
    )

    assert acquired[0].document["termsUrl"] == source_page


@pytest.mark.parametrize(
    ("carrier", "expected_roles"),
    (("homepage", ("hero",)), ("article", ("cover", "body"))),
)
def test_mediawiki_provider_uses_public_body_original_media_and_safety(
    carrier: str,
    expected_roles: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from core import image_decode

    body = (
        "成都市位于四川盆地西部。\n成都市拥有悠久的城市历史。\n"
        "成都市分布有多处公共文化空间。\n成都市包括河流与历史建筑。\n"
        "交通可乘坐公共汽车到达，开放区域以现场公告为准。\n\n"
        "园区沿湖分布多处步道、展馆和观景平台，游客可以依次了解"
        "当地生态保护、历史沿革与社区文化。春季和秋季景观层次丰富，"
        "公共服务区域设有导览、休息与无障碍设施。参观前应核对开放"
        "时间、天气和交通信息，并遵守现场的生态保护与安全提示。"
    )
    bundle = MediaWikiPageBundle(
        requested_title="成都市",
        resolved_title="成都市",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext=(
            "{{Infobox\n"
            "| website = https://example.test/official\n"
            "}}"
        ),
        rendered_image_titles=("File:a.jpg", "File:b.jpg"),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    monkeypatch.setattr(mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle)
    images = [
        {
            "url": f"https://upload.wikimedia.org/{name}.jpg",
            "sourceUrl": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
            "termsUrl": "http://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
            "license": "CC BY-SA 4.0",
            "credit": f"Creator {name}",
            "creator": f"Creator {name}",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
            "pageRevisionId": 20,
            "pageContentSha256": "page-sha",
        }
        for name in ("a", "b")
    ]
    monkeypatch.setattr(mod, "_mediawiki_page_images", lambda *a, **k: images)
    monkeypatch.setattr(mod, "wikidata_commons_images_for_entity", lambda *a, **k: [])
    monkeypatch.setattr(mod, "commons_images_for_entity", lambda *a, **k: [])
    monkeypatch.setattr(mod, "openverse_images_for_entity", lambda *a, **k: [])
    responses = iter((b"image-a", b"image-b")[: len(expected_roles)])
    monkeypatch.setattr(
        mod.network_io,
        "fetch_http",
        lambda url, timeout: HttpFetchResult(0, 200, url, next(responses)),
    )
    monkeypatch.setattr(
        mod,
        "assess_image",
        lambda *a, **k: ImageVerdict(
            path="fixture",
            status="safe",
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(),
            backends=("cv", "ocr"),
        ),
    )
    monkeypatch.setattr(
        image_decode,
        "probe_image_bytes",
        lambda body: ImageProbe(width=1600, height=1000, mime_type="image/jpeg"),
    )

    acquired = acquire_mediawiki_source_ready_candidate(
        _planned("四川省成都市", "地点/城市", source_title="成都市"),
        carrier=carrier,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    if carrier == "article":
        assert acquired.candidate["articleSiteId"] == "wikipedia_zh"
    else:
        assert acquired.candidate["entityRef"] == "/entity/地点/城市/四川省成都市"
        assert acquired.candidate["hero"]["entityRef"] == acquired.candidate["entityRef"]
        assert acquired.candidate["hero"]["sourceUnitDigest"] == acquired.candidate[
            "primarySource"
        ]["sourceUnitDigest"]
    assert tuple(asset.document["role"] for asset in acquired.assets) == expected_roles
    assert all(
        asset.document["distributionDecision"] == "research_allowed"
        for asset in acquired.assets
    )
    assert all(
        asset.document["usageScope"] == "app_publish"
        for asset in acquired.assets
    )
    assert all(
        asset.document["modelReleaseStatus"] == "not_required"
        for asset in acquired.assets
    )
    assert all(
        asset.document["termsUrl"].startswith("https://creativecommons.org/")
        for asset in acquired.assets
    )


def test_mediawiki_rejects_page_title_different_from_frozen_coverage_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod

    bundle = MediaWikiPageBundle(
        requested_title="成都市",
        resolved_title="成都",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text="成都页面",
        wikitext="{{Infobox}}",
        rendered_image_titles=(),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    monkeypatch.setattr(
        mod, "fetch_mediawiki_page_bundle_for_url", lambda *args, **kwargs: bundle
    )

    with pytest.raises(MediaWikiSourceReadyRejected, match="page identity drift"):
        acquire_mediawiki_source_ready_candidate(
            _planned("四川省成都市", "地点/城市", source_title="成都市"),
            carrier="homepage",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
        )


def test_openverse_supplement_preserves_provider_and_original_rights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from core import image_decode

    monkeypatch.setattr(
        mod.network_io,
        "fetch_http",
        lambda url, timeout: HttpFetchResult(0, 200, url, b"openverse-image"),
    )
    monkeypatch.setattr(
        mod,
        "assess_image",
        lambda *a, **k: ImageVerdict(
            path="fixture",
            status="safe",
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(),
            backends=("cv", "ocr"),
        ),
    )
    monkeypatch.setattr(
        image_decode,
        "probe_image_bytes",
        lambda body: ImageProbe(width=1600, height=1000, mime_type="image/jpeg"),
    )
    acquired = acquire_open_image_assets(
        [
            {
                "url": "https://images.openverse.org/test.jpg",
                "platform": "Openverse",
                "sourceUrl": "https://example.test/original-work",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": "https://example.test/original-work",
                "license": "CC BY 4.0",
                "credit": "Original Creator",
                "creator": "Original Creator",
                "usageScope": "app_publish",
                "modelReleaseStatus": "not_required",
            }
        ],
        source_unit_ref="sources/openverse-test",
        roles=("hero",),
        captured_at=CAPTURED_AT,
    )
    assert acquired[0].document["provider"] == "openverse"
    assert acquired[0].document["platform"] == "Openverse"
    assert acquired[0].document["creator"] == "Original Creator"
