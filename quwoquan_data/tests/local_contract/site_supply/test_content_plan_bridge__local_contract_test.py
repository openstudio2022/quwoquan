from __future__ import annotations



from support.site_supply_fixtures import *  # noqa: F401,F403



def test_content_plan_bridge_materializes_standard_batch_with_source_assets():
    from _common.io import read_json
    from _common.paths import batch_content_plan_packet_path, batch_root

    batch = "content_plan_bridge"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_batch"
    _write_frontier(batch)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/bridge001",
        lane="article",
        title="九寨沟两日玩法",
        text=ARTICLE_TEXT * 8,
        published_at="2026-06-01",
        assets=[
            {
                "assetId": "asset_bridge_001",
                "url": "https://example-cdn.test/jiuzhaigou.png",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Jiuzhaigou.png",
                "license": "CC BY-SA 4.0",
                "credit": "Example Photographer",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "wikimedia_commons_open_license_publish_candidate",
                "modelReleaseStatus": "not_required",
                "sourceCollectionId": "wikimedia_commons:jiuzhaigou_bridge",
                "width": 1200,
                "height": 800,
            }
        ],
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    original_fetch_image_payload = ss.fetch_image_payload

    def fake_fetch_image_payload(url: str):
        assert url == "https://example-cdn.test/jiuzhaigou.png"
        return {
            "url": url,
            "requestedUrl": url,
            "ext": ".png",
            "bytes": PNG_BYTES,
            "contentType": "image/png",
            "sha256": "sha256:test",
        }

    try:
        ss.fetch_image_payload = fake_fetch_image_payload
        report = ss.build_site_content_plan(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=batch,
            task_id=task_id,
            target_batch=target_batch,
            limit=1,
            allow_partial=False,
        )
    finally:
        ss.fetch_image_payload = original_fetch_image_payload

    assert report["gate"]["passed"], report
    packet = read_json(batch_content_plan_packet_path(task_id, target_batch))
    assert packet["generatedBy"] == "site_supply_content_plan_bridge"
    assert packet["items"][0]["baseSourceRef"].endswith("/source.md")
    root = batch_root(task_id, target_batch)
    assert (root / "entities" / "地点" / "景区" / "九寨沟").is_dir()
    asset_indexes = list(root.glob("sources/*/assets/index.json"))
    assert len(asset_indexes) == 1
    asset = read_json(asset_indexes[0])["assets"][0]
    assert asset["license"] == "CC BY-SA 4.0"
    assert asset["credit"] == "Example Photographer"
    assert asset["termsUrl"].startswith("https://creativecommons.org/")
    assert asset["sourceCollectionId"] == "wikimedia_commons:jiuzhaigou_bridge"

def test_content_plan_bridge_blocks_short_article_base_draft():
    batch = "content_plan_short_article"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_short_article_batch"
    _write_frontier(batch)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/short001",
        lane="article",
        title="九寨沟短攻略",
        text=ARTICLE_TEXT * 2,
        published_at="2026-06-01",
        assets=[],
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        max_images_per_candidate=0,
        allow_partial=True,
    )

    assert not report["gate"]["passed"], report
    skipped = "\n".join(report["skipped"][candidate["candidateRef"]])
    assert "candidate baseDraftText too short for content_plan" in skipped
    assert report["itemCount"] == 0

def test_content_plan_bridge_revalidates_stale_score_works_decision():
    batch = "content_plan_stale_works_score"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_stale_works_score_batch"
    _write_frontier(batch)
    casual_long_text = (
        "这一天主要就是在九寨沟附近随便逛逛拍拍照，天气不错，吃了小吃，"
        "路上也没有特别规划，只是把心情和流水账记下来。"
    ) * 70
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/stale-works",
        lane="article",
        title="九寨沟随手记录",
        text=casual_long_text,
        published_at="2026-06-01",
        assets=[],
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    score["productionEligible"] = True
    score["publishRecommendation"] = "publish_candidate"
    score["issues"] = []
    score.pop("worksDecision", None)
    score.pop("worksCarrier", None)
    score.pop("worksSourceTier", None)
    score["gate"] = ss._gate_report("site_score", [], [])
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        max_images_per_candidate=0,
        allow_partial=True,
    )

    assert not report["gate"]["passed"], report
    skipped = "\n".join(report["skipped"][candidate["candidateRef"]])
    assert "works classifier rejected content_plan candidate as 'moment'" in skipped
    assert report["itemCount"] == 0

def test_content_plan_bridge_dedupes_validation_targets_for_same_entity():
    from _common.io import read_json
    from _common.paths import batch_content_plan_packet_path

    batch = "content_plan_duplicate_entity_targets"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_duplicate_entity_targets_batch"
    _write_frontier(batch)
    for idx in range(2):
        candidate = ss.build_site_candidate_packet(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=batch,
            url=f"https://touch.travel.qunar.com/travelbook/note/dup{idx}",
            lane="article",
            title=f"九寨沟真实游记 {idx}",
            text=ARTICLE_TEXT * 8,
            published_at="2026-06-01",
            assets=[],
            entity_mentions=["地点/景区/九寨沟"],
            tag_mentions=["Topic/旅行/玩法/自然风光"],
        )
        assert candidate["gate"]["passed"], candidate["gate"]
        ss.write_site_candidate_packet(candidate)
        score = ss.build_site_score_packet(candidate)
        assert score["gate"]["passed"], score
        ss.write_site_score_packet(score)
        mapped = ss.build_site_map_packet(candidate, score)
        assert mapped["gate"]["passed"], mapped
        ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=2,
        max_images_per_candidate=0,
        allow_partial=False,
    )

    assert report["gate"]["passed"], report
    assert report["itemCount"] == 2
    packet = read_json(batch_content_plan_packet_path(task_id, target_batch))
    assert len(packet["items"]) == 2

def test_content_plan_bridge_blocks_missing_committed_task_spec():
    from _common.paths import batch_content_plan_packet_path

    batch = "content_plan_missing_committed_task"
    task_id = "site_supply_bridge_test/missing_task"
    target_batch = "bridge_missing_task_batch"
    candidate = _write_candidate(batch)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    report = ss.build_site_content_plan(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        allow_partial=True,
    )
    assert not report["gate"]["passed"], report
    assert "committed task spec missing" in "\n".join(report["gate"]["blockers"])
    assert not batch_content_plan_packet_path(task_id, target_batch).exists()

def test_content_plan_bridge_blocks_unverified_raw_entity_for_scenic_type():
    batch = "content_plan_unverified_entity"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_unverified_entity_batch"
    _write_frontier(batch)
    candidate = ss.build_site_candidate_packet(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=batch,
        url="https://touch.travel.qunar.com/travelbook/note/bridge002",
        lane="article",
        title="北京首都国际机场",
        text=ARTICLE_TEXT * 8,
        published_at="2026-06-01",
        assets=[
            {
                "assetId": "asset_bridge_002",
                "url": "https://example-cdn.test/airport.png",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Airport.png",
                "license": "CC BY-SA 4.0",
                "credit": "Example Photographer",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": "wikimedia_commons_open_license_publish_candidate",
                "modelReleaseStatus": "not_required",
                "sourceCollectionId": "wikimedia_commons:airport_bridge",
                "width": 1200,
                "height": 800,
            }
        ],
        entity_mentions=["北京首都国际机场"],
        tag_mentions=["Topic/旅行/交通/机场"],
    )
    assert candidate["gate"]["passed"], candidate["gate"]
    ss.write_site_candidate_packet(candidate)
    score = ss.build_site_score_packet(candidate)
    assert score["gate"]["passed"], score
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    assert mapped["gate"]["passed"], mapped
    ss.write_site_map_packet(mapped)

    original_fetch_image_payload = ss.fetch_image_payload
    try:
        ss.fetch_image_payload = lambda url: {
            "url": url,
            "requestedUrl": url,
            "ext": ".png",
            "bytes": PNG_BYTES,
            "contentType": "image/png",
            "sha256": "sha256:test",
        }
        report = ss.build_site_content_plan(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=batch,
            task_id=task_id,
            target_batch=target_batch,
            limit=1,
            allow_partial=True,
        )
    finally:
        ss.fetch_image_payload = original_fetch_image_payload

    assert not report["gate"]["passed"], report
    skipped = "\n".join("\n".join(issues) for issues in report["skipped"].values())
    assert "candidate lacks verified 地点/景区 mapping" in skipped
