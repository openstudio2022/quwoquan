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

from vertical.source_registry import (  # noqa: E402
    TRAVEL_SOURCE_REGISTRY_PATH,
    match_travel_source_site,
    load_travel_source_registry,
    resolve_travel_source_runtime,
    verify_travel_source_registry,
)


def test_repository_travel_source_registry_is_valid():
    data = load_travel_source_registry()
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
    text = """schemaVersion: quwoquan.travel_source_registry.v1
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

    from vertical import source_registry as sr

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
    assert resolve_travel_source_runtime("https://baike.baidu.com/item/稻城亚丁")["extractor"] == "baidu_baike_html"
    assert resolve_travel_source_runtime("https://baike.sogou.com/v123")["extractor"] == "sogou_baike_html"
    official = resolve_travel_source_runtime("https://www.aba.gov.cn/scenic/detail.html")
    assert official["extractor"] == "static_official_html", official
    ems = resolve_travel_source_runtime("http://www.ems517.com/new/visitor?preferential=1")
    assert ems["siteId"] == "scenic_official", ems
    assert ems["extractor"] == "static_official_html", ems
    qunar = resolve_travel_source_runtime("https://travel.qunar.com/p-oi123456-jingdian")
    assert qunar["siteId"] == "qunar_guide", qunar
    assert qunar["extractor"] == "qunar_html", qunar
    assert qunar["fetchable"] is True, qunar
    mafengwo = resolve_travel_source_runtime("https://www.mafengwo.cn/i/123456.html")
    assert mafengwo["siteId"] == "mafengwo_travelogue", mafengwo
    assert mafengwo["fetchable"] is False, mafengwo


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"travel source registry tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
