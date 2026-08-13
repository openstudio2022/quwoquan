"""Site-first Article source-ready acquisition contracts."""
from __future__ import annotations

from content.source.research.article_frontier_contract import ArticleSourceCandidate
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
)
from content.source.research.article_source_unit_catalog import (
    build_article_source_unit_catalog,
)
import content.source.research.homepage_article_source_ready_article_site as subject


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64
SHA_C = "sha256:" + "c" * 64


def test_site_frontier_skips_non_exact_listing_and_freezes_exact_qunar_detail(
    monkeypatch,
) -> None:
    site = article_search_sites(site_ids=frozenset({"qunar_guide"}))[0]
    profile_digest = article_profile_digest(site)
    candidates = (
        ArticleSourceCandidate(
            source_id="listing",
            site_id="qunar_guide",
            platform="去哪儿攻略",
            category="travelogue",
            canonical_url="https://touch.travel.qunar.com/p-cs300001-sichuan-jingdian",
            title="四川旅游景点大全",
            discovery_method="site_listing_scan",
            relevance_score=0.99,
            profile_digest=profile_digest,
        ),
        ArticleSourceCandidate(
            source_id="detail",
            site_id="qunar_guide",
            platform="去哪儿攻略",
            category="travelogue",
            canonical_url="https://touch.travel.qunar.com/poi/5942737",
            title="2026洗象池门票与游玩攻略",
            discovery_method="site_listing_scan",
            relevance_score=0.99,
            profile_digest=profile_digest,
        ),
    )
    monkeypatch.setattr(
        subject,
        "_candidate_batches",
        lambda **_kwargs: iter(
            ((
                "qunar_guide",
                {
                "schema": "quwoquan.content.article_source_discovery_evidence",
                "entityId": "洗象池",
                "frontierDigest": SHA_A,
                },
                candidates,
            ),)
        ),
    )
    calls: list[str] = []

    def fetch(url: str, **_kwargs):
        calls.append(url)
        text = ("洗象池位于峨眉山，提供门票、开放时间、交通、路线与避坑建议。" * 45)
        return {
            "text": text,
            "htmlBytes": text.encode("utf-8"),
            "runtime": {"fetchFinalUrl": url},
        }

    monkeypatch.setattr(subject, "fetch_source_payload", fetch)
    acquired = subject.acquire_article_site_source_ready_candidate(
        {
            "entityType": "地点/遗址",
            "canonicalEntityRef": "/entity/地点/遗址/洗象池",
            "candidateName": "洗象池",
        },
        source_revision=SHA_A,
        source_digest=SHA_B,
        entity_catalog_digest=SHA_C,
        captured_at="2026-08-12T06:00:00Z",
    )

    assert calls == ["https://touch.travel.qunar.com/poi/5942737"]
    assert acquired.source_selection_origin == "site_frontier"
    assert acquired.candidate["articleSiteId"] == "qunar_guide"
    assert acquired.candidate["entityRef"] == "/entity/地点/遗址/洗象池"
    assert acquired.candidate["publishMediaMode"] == "text_only"
    assert acquired.candidate["assets"] == []
    assert acquired.source_unit["sourceKind"] == "travelogue"
    assert acquired.source_unit["qualityStatus"] == "passed"
    catalog = build_article_source_unit_catalog(
        catalog_id="site-first",
        created_at="2026-08-12T06:00:00Z",
        minimum_candidate_count=1,
        source_revision=SHA_A,
        source_digest=SHA_B,
        entity_catalog_digest=SHA_C,
        candidates=[acquired.candidate],
    )
    assert catalog["candidates"][0]["sourceUrl"].endswith("/poi/5942737")


def test_qunar_site_api_and_creator_expansion_precede_search_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setattr(subject.network_io, "curl_text", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        subject,
        "_qunar_travelogue_sources",
        lambda *_args, **_kwargs: [
            {
                "source_id": "article_qunar_base_1",
                "platform": "去哪儿攻略",
                "url": "https://touch.travel.qunar.com/youji/123456",
                "category": "travelogue",
                "title": "洗象池旅行攻略",
                "discoveryProvider": "qunar_author_books_page",
                "matchConfidence": 0.91,
                "authorId": "creator-1",
            }
        ],
    )
    monkeypatch.setattr(
        subject,
        "discover_article_source_frontier",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("search fallback ran before the site-direct batch was consumed")
        ),
    )

    batches = subject._candidate_batches(
        entity_ref="/entity/地点/遗址/洗象池",
        entity_name="洗象池",
        aliases=("洗象池",),
    )
    poi_site_id, poi_evidence, poi_candidates = next(batches)
    site_id, evidence, candidates = next(batches)

    assert poi_site_id == "qunar_guide"
    assert poi_evidence["discoveryMethod"] == "site_exact_poi_search"
    assert poi_candidates == ()
    assert site_id == "qunar_guide"
    assert evidence["discoveryMethod"] == "site_public_api_then_creator_public_works"
    assert evidence["providerError"] == ""
    assert candidates[0].canonical_url.endswith("/youji/123456")
    assert candidates[0].discovery_method == "qunar_author_books_page"


def test_qunar_exact_poi_search_yields_detail_before_travelogue_api(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        subject.network_io,
        "curl_text",
        lambda *_args, **_kwargs: (
            '<a href="https://touch.go.qunar.com/poi/5942737" class="list_link">'
            '<dl><dt>洗象池</dt><dd>历史遗迹</dd></dl></a>'
        ),
    )
    monkeypatch.setattr(
        subject,
        "_qunar_travelogue_sources",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("travelogue API ran before exact POI candidate was consumed")
        ),
    )

    site_id, evidence, candidates = next(
        subject._candidate_batches(
            entity_ref="/entity/地点/遗址/洗象池",
            entity_name="洗象池",
            aliases=("洗象池",),
        )
    )

    assert site_id == "qunar_guide"
    assert evidence["searchResponseContentSha256"].startswith("sha256:")
    assert candidates[0].canonical_url == "https://touch.travel.qunar.com/poi/5942737"
    assert candidates[0].title == "洗象池"


def test_wikivoyage_child_district_cannot_impersonate_parent_city() -> None:
    assert subject._candidate_title_is_exact(
        site_id="wikivoyage_zh",
        title="广元 - 来自维基导游的旅行指南",
        aliases=("广元", "广元市"),
    )
    assert not subject._candidate_title_is_exact(
        site_id="wikivoyage_zh",
        title="旺苍 - 来自维基导游的旅行指南",
        aliases=("广元", "广元市"),
    )


def test_photography_seed_rejects_generic_guide_and_freezes_strong_topic(
    monkeypatch,
) -> None:
    site = article_search_sites(site_ids=frozenset({"qunar_guide"}))[0]
    profile_digest = article_profile_digest(site)
    generic = ArticleSourceCandidate(
        source_id="generic",
        site_id="qunar_guide",
        platform="去哪儿攻略",
        category="travelogue",
        canonical_url="https://touch.travel.qunar.com/poi/1",
        title="洗象池游玩攻略",
        discovery_method="site_direct",
        relevance_score=0.99,
        profile_digest=profile_digest,
        discovery_query="洗象池",
    )
    photography = ArticleSourceCandidate(
        source_id="photography",
        site_id="qunar_guide",
        platform="去哪儿攻略",
        category="travelogue",
        canonical_url="https://touch.travel.qunar.com/poi/2",
        title="洗象池摄影机位与拍摄攻略",
        discovery_method="topic_search",
        relevance_score=0.99,
        profile_digest=profile_digest,
        discovery_query="洗象池 摄影",
    )
    monkeypatch.setattr(
        subject,
        "_candidate_batches",
        lambda **_kwargs: iter(
            (("qunar_guide", {"query": "洗象池 摄影"}, (generic, photography)),)
        ),
    )

    def fetch(url: str, **_kwargs):
        if url.endswith("/1"):
            text = "洗象池门票交通路线与拍照建议。" * 90
        else:
            text = (
                "洗象池摄影路线从日出机位开始，根据光线安排构图，"
                "携带三脚架并按焦段选择取景。"
            ) * 45
        return {
            "text": text,
            "htmlBytes": text.encode("utf-8"),
            "runtime": {"fetchFinalUrl": url},
        }

    monkeypatch.setattr(subject, "fetch_source_payload", fetch)
    acquired = subject.acquire_article_site_source_ready_candidate(
        {
            "entityType": "地点/遗址",
            "canonicalEntityRef": "/entity/地点/遗址/洗象池",
            "candidateName": "洗象池",
            "seed": {
                "articleCategory": "photography",
                "writingIntent": "planning_consultation",
                "topicTagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            },
        },
        source_revision=SHA_A,
        source_digest=SHA_B,
        entity_catalog_digest=SHA_C,
        captured_at="2026-08-12T06:00:00Z",
    )

    candidate = acquired.candidate
    assert candidate["sourceUrl"].endswith("/2")
    assert candidate["articleCategory"] == "photography"
    assert candidate["writingIntent"] == "planning_consultation"
    assert candidate["topicTagRefs"] == ["Topic/旅行/玩法/摄影旅拍"]
    assert candidate["sourceClassification"]["matchedTitleSignals"]
    assert candidate["sourceClassification"]["matchedBodySignals"]
    assert acquired.source_unit["sourceClassification"] == candidate["sourceClassification"]
