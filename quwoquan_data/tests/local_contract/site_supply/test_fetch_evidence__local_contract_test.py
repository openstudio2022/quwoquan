from __future__ import annotations



from support.site_supply_fixtures import *  # noqa: F401,F403



def test_fetch_stability_classification_does_not_treat_short_text_as_empty_extract():
    packet = {
        "fetch": {"statusCode": 200},
        "gate": {"blockers": ["fetch extracted text is too short (<600 chars)"]},
    }
    assert ss._classify_fetch_packet(packet) == (0, 0, 0, 0)

def test_site_fetch_packet_materializes_real_fetch_evidence_before_candidate():
    _write_frontier("fetch_ok")
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="fetch_ok",
        url="https://touch.travel.qunar.com/youji/123456",
        lane="article",
        title="九寨沟真实抓取候选",
        published_at="2026-06-01",
        min_text_chars=60,
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
            "runtime": {"siteId": "qunar_guide", "fetchable": True},
        },
    )
    assert fetch["gate"]["passed"], fetch["gate"]
    path = ss.write_site_fetch_packet(fetch, html_bytes=ARTICLE_TEXT.encode("utf-8"))
    assert (path.parent / "raw" / "page.html").is_file()
    candidate = ss.build_site_candidate_from_fetch(fetch)
    assert candidate["gate"]["passed"], candidate["gate"]
    assert candidate["candidateRef"] == fetch["candidateRef"]

def test_site_fetch_uses_wiki_url_title_as_extract_title_and_default_mention():
    packet = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id="fetch_wiki_title",
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert packet["gate"]["passed"], packet["gate"]
    ss.write_site_frontier_packet(packet)
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id="fetch_wiki_title",
        url="https://zh.wikivoyage.org/wiki/%E4%B9%9D%E5%AF%A8%E6%B2%9F",
        lane="article",
        entity_mentions=[],
        min_text_chars=60,
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
            "runtime": {"siteId": "wikivoyage_zh", "fetchable": True},
        },
    )
    assert fetch["gate"]["passed"], fetch["gate"]
    assert fetch["extraction"]["title"] == "九寨沟"
    assert fetch["semanticMentions"]["entities"] == ["九寨沟"]

def test_site_fetch_candidate_preserves_extracted_assets():
    _write_frontier("fetch_assets")
    asset = {
        "assetId": "asset_fetch_001",
        "url": "https://example-cdn.test/jiuzhaigou.jpg",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Jiuzhaigou.jpg",
        "license": "CC BY-SA 4.0",
        "credit": "Example Photographer",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "usageScope": "wikimedia_commons_open_license_publish_candidate",
        "modelReleaseStatus": "not_required",
        "sourceCollectionId": "wikimedia_commons:jiuzhaigou",
    }
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id="fetch_assets",
        url="https://touch.travel.qunar.com/youji/123456",
        lane="article",
        title="九寨沟真实抓取候选",
        published_at="2026-06-01",
        min_text_chars=60,
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "assets": [asset],
            "sha256": "sha",
            "runtime": {"siteId": "qunar_guide", "fetchable": True},
        },
    )
    assert fetch["gate"]["passed"], fetch["gate"]
    candidate = ss.build_site_candidate_from_fetch(fetch)
    assert candidate["gate"]["passed"], candidate["gate"]
    assert candidate["assets"][0]["license"] == "CC BY-SA 4.0"
    assert candidate["assets"][0]["sourceCollectionId"] == "wikimedia_commons:jiuzhaigou"

def test_site_fetch_stops_when_frontier_is_not_batch_crawl_allowed():
    frontier = ss.build_site_frontier_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id="fetch_blocked_ctrip",
        daily_target=10_000,
        queue_backend="reliabletask",
        end_date="2026-06-19",
    )
    assert not frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    fetch = ss.build_site_fetch_packet(
        vertical="travel",
        site_id="ctrip_travelogue",
        batch_id="fetch_blocked_ctrip",
        url="https://you.ctrip.com/travels/example.html",
        lane="article",
        title="不应进入抓取",
        payload={
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
        },
    )
    assert not fetch["gate"]["passed"]
    text = "\n".join(fetch["gate"]["blockers"])
    assert "site_frontier gate did not pass" in text

def test_fetch_retry_budget_recovers_transient_empty_body():
    calls = {"count": 0}
    original = ss.fetch_source_payload

    def fake_fetch(url: str, source=None):
        assert source is None
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError(f"fetch failed for {url} (status=200)")
        return {
            "statusCode": 200,
            "htmlBytes": ARTICLE_TEXT.encode("utf-8"),
            "text": ARTICLE_TEXT,
            "sha256": "sha",
            "runtime": {"siteId": "qunar_guide", "fetchable": True},
        }

    try:
        ss.fetch_source_payload = fake_fetch
        payload, error, attempts = ss._fetch_with_retry(
            "https://touch.travel.qunar.com/youji/123456",
            retry_budget=2,
            retry_delay_seconds=0,
        )
    finally:
        ss.fetch_source_payload = original
    assert error == ""
    assert attempts == 2
    assert payload and payload["statusCode"] == 200

