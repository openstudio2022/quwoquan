"""Travel source registry contract tests."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from governance.coverage.source_registry import (  # noqa: E402
    TRAVEL_SOURCE_REGISTRY_PATH,
    build_article_commercial_onboarding_summary,
    match_travel_source_site,
    load_travel_source_registry,
    resolve_travel_source_runtime,
    verify_travel_source_registry,
)


def test_repository_travel_source_registry_is_valid():
    data = load_travel_source_registry()
    assert data["schemaVersion"] == "quwoquan.travel_source_registry"
    assert data["vertical"] == "travel"
    assert verify_travel_source_registry(
        allowed_extractors={
            "wikipedia_api",
            "baidu_baike_html",
            "sogou_baike_html",
            "qunar_html",
            "static_official_html",
            "generic_html",
        }
    ) == []


def test_registry_rejects_unknown_extractor():
    text = """schemaVersion: quwoquan.travel_source_registry
vertical: travel
qualityTiers: [A]
licensePolicies: [factual_citation_only]
extractors: [unknown_extractor]
sites:
  - siteId: bad
    platform: 维基百科
    category: encyclopedia
    domains: [zh.wikipedia.org]
    urlPatterns: [https://zh.wikipedia.org/wiki/*]
    fetchable: true
    extractor: unknown_extractor
    licensePolicy: factual_citation_only
    qualityTier: A
"""
    tmp = Path(tempfile.mkdtemp(prefix="travel_source_registry_"))
    registry = tmp / "quwoquan_data" / "verticals" / "travel" / "sources"
    registry.mkdir(parents=True, exist_ok=True)
    path = registry / "source_registry.yaml"
    path.write_text(text, encoding="utf-8")

    from governance.coverage import source_registry as sr

    old = sr.TRAVEL_SOURCE_REGISTRY_PATH
    try:
        sr.TRAVEL_SOURCE_REGISTRY_PATH = path
        issues = sr.verify_travel_source_registry(allowed_extractors={"wikipedia_api"})
    finally:
        sr.TRAVEL_SOURCE_REGISTRY_PATH = old
    assert any("unknown extractors" in issue or "not declared in top-level extractors" in issue for issue in issues), issues


def test_registry_matches_runtime_sites_and_extractors():
    wiki = match_travel_source_site("https://zh.wikipedia.org/wiki/九寨沟")
    assert wiki and wiki["siteId"] == "wikipedia_zh", wiki
    assert resolve_travel_source_runtime("https://zh.wikipedia.org/wiki/九寨沟")["extractor"] == "wikipedia_api"
    wikivoyage = resolve_travel_source_runtime("https://zh.wikivoyage.org/wiki/九寨沟")
    assert wikivoyage["articleCommercialAdmission"] == "commercial_release", wikivoyage
    assert resolve_travel_source_runtime("https://baike.baidu.com/item/稻城亚丁")["extractor"] == "baidu_baike_html"
    assert resolve_travel_source_runtime("https://baike.sogou.com/v123")["extractor"] == "sogou_baike_html"
    official = resolve_travel_source_runtime("https://www.aba.gov.cn/scenic/detail.html")
    assert official["extractor"] == "static_official_html", official
    ems = resolve_travel_source_runtime("http://www.ems517.com/new/visitor?preferential=1")
    assert ems["siteId"] == "scenic_official", ems
    assert ems["extractor"] == "static_official_html", ems
    bipenggou = resolve_travel_source_runtime("http://www.bipenggou.net/")
    assert bipenggou["siteId"] == "scenic_official", bipenggou
    bifengxia = resolve_travel_source_runtime("http://www.bifengxia.com/info?crid=74&lan=cn&ckey=jqgk_dfbfx")
    assert bifengxia["siteId"] == "scenic_official", bifengxia
    snzh = resolve_travel_source_runtime("https://www.snzh.cn/")
    assert snzh["siteId"] == "scenic_official", snzh
    qunar = resolve_travel_source_runtime("https://travel.qunar.com/p-oi123456-jingdian")
    assert qunar["siteId"] == "qunar_guide", qunar
    assert qunar["extractor"] == "qunar_html", qunar
    assert qunar["fetchable"] is True, qunar
    assert qunar["articleCommercialAdmission"] == "commercial_release", qunar
    mafengwo = resolve_travel_source_runtime("https://www.mafengwo.cn/i/123456.html")
    assert mafengwo["siteId"] == "mafengwo_travelogue", mafengwo
    assert mafengwo["fetchable"] is False, mafengwo
    assert mafengwo["articleCommercialAdmission"] == "controlled_trial", mafengwo
    xiaohongshu = resolve_travel_source_runtime("https://www.xiaohongshu.com/explore/123456")
    assert xiaohongshu["siteId"] == "xiaohongshu_travel_reference", xiaohongshu
    assert xiaohongshu["category"] == "travelogue", xiaohongshu
    assert xiaohongshu["fetchable"] is False, xiaohongshu
    assert xiaohongshu["articleCommercialAdmission"] == "reference_only", xiaohongshu
    toutiao = resolve_travel_source_runtime("https://www.toutiao.com/article/123456/")
    assert toutiao["siteId"] == "toutiao_article_reference", toutiao
    assert toutiao["category"] == "platform_article", toutiao
    assert toutiao["fetchable"] is False, toutiao
    assert toutiao["articleCommercialAdmission"] == "reference_only", toutiao
    weibo = resolve_travel_source_runtime("https://weibo.com/123456789/ABC")
    assert weibo["siteId"] == "weibo_travel_reference", weibo
    assert weibo["category"] == "community_post", weibo
    assert weibo["articleCommercialAdmission"] == "reference_only", weibo
    pinterest = resolve_travel_source_runtime("https://www.pinterest.com/pin/123456/")
    assert pinterest["siteId"] == "pinterest_travel_reference", pinterest
    assert pinterest["category"] == "editorial_reference_only", pinterest
    assert pinterest["licensePolicy"] == "attribution_no_watermark", pinterest
    pinterest_locale = resolve_travel_source_runtime("https://fi.pinterest.com/pin/123456/")
    assert pinterest_locale["siteId"] == "pinterest_travel_reference", pinterest_locale
    assert pinterest_locale["category"] == "editorial_reference_only", pinterest_locale
    tuchong_stock = resolve_travel_source_runtime("https://stock.tuchong.com/image/123456")
    assert tuchong_stock["siteId"] == "tuchong_stock_authorized", tuchong_stock
    assert tuchong_stock["category"] == "stock_authorized", tuchong_stock


def test_discovery_strategy_is_content_first_not_author_first():
    sites = {
        str(site.get("siteId")): site
        for site in load_travel_source_registry().get("sites", [])
        if isinstance(site, dict)
    }
    expected_modes = {
        "xiaohongshu_travel_reference": "content_search",
        "toutiao_article_reference": "content_search",
        "weibo_travel_reference": "content_search",
        "pinterest_travel_reference": "content_search",
        "qunar_guide": "site_listing_scan",
        "ctrip_travelogue": "site_listing_scan",
        "mafengwo_travelogue": "site_listing_scan",
        "tuchong_community_reference": "site_listing_scan",
        "tuchong_stock_authorized": "licensed_asset_manifest",
    }
    for site_id, mode in expected_modes.items():
        profile = sites[site_id]["siteCrawlProfile"]
        strategy = profile["discoveryStrategy"]
        assert strategy["mode"] == mode
        axes = {str(axis).lower() for axis in strategy["seedAxes"]}
        assert "author" not in axes
        assert "creator" not in axes
        assert "photographer" not in axes
        assert "scenery_or_photography_classification" in strategy["precheckGates"]
        assert "quality_gate" in strategy["precheckGates"]
    assert sites["xiaohongshu_travel_reference"]["siteCrawlProfile"]["controlledTrial"]["rawFetchAllowed"] is False
    assert sites["toutiao_article_reference"]["siteCrawlProfile"]["controlledTrial"]["publishableAssetsAllowed"] is False
    pinterest_profile = sites["pinterest_travel_reference"]["siteCrawlProfile"]
    assert pinterest_profile["fetchMode"] == "attribution_manifest"
    assert pinterest_profile["rightsPolicy"] == "attribution_no_watermark"
    assert pinterest_profile["attributionPublish"]["allowed"] is True


def test_article_commercial_onboarding_summary_is_explicit():
    summary = build_article_commercial_onboarding_summary()
    counts = summary["admissionCounts"]
    assert summary["siteCount"] == 7, summary
    assert counts["commercial_release"] == 2, summary
    assert counts["controlled_trial"] == 2, summary
    assert counts["reference_only"] == 3, summary
    assert counts["blocked"] == 0, summary
    assert set(summary["sharedCommercialPoolSites"]) == {"wikivoyage_zh", "qunar_guide"}, summary


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"travel source registry tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
