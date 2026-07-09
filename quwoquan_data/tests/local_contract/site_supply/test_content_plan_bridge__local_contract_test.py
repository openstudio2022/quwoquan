from __future__ import annotations



from pathlib import Path

from support.site_supply_fixtures import *  # noqa: F401,F403



def _write_large_image(path: Path) -> Path:
    import hashlib

    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(path.as_posix().encode("utf-8")).digest()
    Image.new("RGB", (1800, 1200), color=(digest[0], digest[1], digest[2])).save(path, format="JPEG")
    return path


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


def test_content_plan_bridge_materializes_authorized_image_work_lane():
    from _common.io import read_json
    from _common.paths import batch_content_plan_packet_path, batch_root

    batch = "content_plan_authorized_image_work"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_authorized_image_work_batch"
    frontier = ss.build_site_frontier_packet(
        vertical="photography",
        site_id="photographer_authorized_pool",
        batch_id=batch,
        daily_target=1_000,
        queue_backend="reliabletask",
        end_date="2026-07-04",
        admission_mode=ss.ADMISSION_LICENSED_ASSET_INGEST,
    )
    assert frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    image_dir = _TMP / "authorized_image_work_assets"
    assets = []
    for index in range(1, 5):
        image_path = _write_large_image(image_dir / f"{index}.jpg")
        assets.append(
            {
                "assetId": f"pool-a-{index}",
                "url": f"https://photographers.example/download/pool-a-{index}.jpg",
                "sourceUrl": f"https://photographers.example/works/pool-a-{index}",
                "sourcePath": str(image_path),
                "localPath": str(image_path),
                "license": "photographer_authorized",
                "credit": "签约摄影师 A / 摄影师授权池",
                "creator": "签约摄影师 A",
                "termsUrl": "https://photographers.example/terms/authorized-pool",
                "usageScope": "commercial",
                "authorizationProof": f"https://photographers.example/proofs/pool-a-{index}",
                "modelReleaseStatus": "not_required",
                "propertyReleaseStatus": "not_required",
                "sourceCollectionId": "photographer_pool:jiuzhaigou:a",
                "collectionPageUrl": "https://photographers.example/collections/jiuzhaigou-a",
                "caption": f"九寨沟授权摄影作品 {index}",
                "title": f"九寨沟授权摄影作品 {index}",
                "width": 1800,
                "height": 1200,
                "mimeType": "image/jpeg",
            }
        )
    candidate = ss.build_site_candidate_packet(
        vertical="photography",
        site_id="photographer_authorized_pool",
        batch_id=batch,
        url="https://authorized.assets.quwoquan.local/collections/photographer_pool%3Ajiuzhaigou%3Aa",
        lane="image",
        title="九寨沟·授权摄影作品",
        text="",
        published_at="2026-07-04",
        author="签约摄影师 A",
        assets=assets,
        entity_mentions=["地点/景区/九寨沟"],
        tag_mentions=["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影"],
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
        vertical="photography",
        site_id="photographer_authorized_pool",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        allow_partial=False,
    )

    assert report["gate"]["passed"], report
    packet = read_json(batch_content_plan_packet_path(task_id, target_batch))
    assert packet["items"][0]["carrier"] == "image"
    assert packet["items"][0]["researchLane"] == "image"
    assert packet["items"][0]["sourceCollectionId"] == "photographer_pool:jiuzhaigou:a"
    assert len(packet["items"][0]["assetRefs"]) == 4
    root = batch_root(task_id, target_batch)
    first_asset = root / packet["items"][0]["assetRefs"][0]
    assert first_asset.is_file()
    source_meta = read_json(first_asset.parent.parent / "meta.json")
    assert source_meta["researchLane"] == "image"
    assert source_meta["sourceUseMode"] == "licensed_publish_asset"
    from _common.content_object import BRIEF_FILE, content_object_stage_dir
    from _common.paths import STAGE_COMPOSE

    brief = content_object_stage_dir(task_id, target_batch, candidate["candidateRef"], STAGE_COMPOSE) / BRIEF_FILE
    assert brief.is_file()


def test_content_plan_bridge_allows_single_asset_attribution_image_work():
    from _common.io import read_json
    from _common.paths import batch_content_plan_packet_path

    batch = "content_plan_attribution_single_asset"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "bridge_attribution_single_asset_batch"
    frontier = ss.build_site_frontier_packet(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        daily_target=1_000,
        queue_backend="reliabletask",
        end_date="2026-07-05",
        admission_mode=ss.ADMISSION_ATTRIBUTION_PUBLISH_INGEST,
    )
    assert frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)
    image_path = _write_large_image(_TMP / "attribution_single_asset" / "lake_baikal.jpg")
    candidate = ss.build_site_candidate_packet(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        url="https://www.pinterest.com/pin/lake-baikal-smoke-349099408623239532/",
        lane="image",
        title="Lake Baikal: Capturing the Beauty of the Deepest & Oldest Lake on Earth",
        text="",
        published_at="2026-07-05",
        author="HOBOPEEBA",
        assets=[
            {
                "assetId": "pin-lake-baikal-1",
                "url": "https://i.pinimg.com/736x/36/ba/0e/36ba0edaa578001335693b1977f6739c.jpg",
                "sourceUrl": "https://www.boredpanda.com/photography-lake-baikal-in-the-spring-kristina-makeeva/?media_id=1807498",
                "downloadUrl": "https://i.pinimg.com/736x/36/ba/0e/36ba0edaa578001335693b1977f6739c.jpg",
                "sourcePath": str(image_path),
                "localPath": str(image_path),
                "license": "attribution_no_watermark",
                "credit": "HOBOPEEBA",
                "creator": "HOBOPEEBA",
                "termsUrl": "https://policy.pinterest.com/terms-of-service",
                "usageScope": "commercial",
                "authorizationProof": "https://www.pinterest.com/pin/lake-baikal-smoke-349099408623239532/",
                "authorizationBasis": "attribution_no_watermark",
                "modelReleaseStatus": "not_required",
                "propertyReleaseStatus": "not_required",
                "sourceCollectionId": "pin_349099408623239532",
                "collectionPageUrl": "https://www.pinterest.com/meredithxu1995/painting-photo-mood-and-light/",
                "caption": "Explore the stunning beauty of Lake Baikal, the deepest and oldest lake on Earth.",
                "title": "Lake Baikal: Capturing the Beauty of the Deepest & Oldest Lake on Earth",
                "width": 1800,
                "height": 1200,
                "mimeType": "image/jpeg",
                "pinUrl": "https://www.pinterest.com/pin/lake-baikal-smoke-349099408623239532/",
                "discoveryUrl": "https://www.pinterest.com/pin/lake-baikal-smoke-349099408623239532/",
                "originalAssetUrl": "https://i.pinimg.com/736x/36/ba/0e/36ba0edaa578001335693b1977f6739c.jpg",
                "sourceAuthor": "HOBOPEEBA",
                "repostAttribution": "Pinterest pin saved by meredithxu1995; linked source https://www.boredpanda.com/photography-lake-baikal-in-the-spring-kristina-makeeva/?media_id=1807498",
                "watermarkScan": "no_explicit_watermark",
                "ocrScan": "no_text_detected",
                "collectedAt": "2026-07-05T11:00:53.470157+00:00",
            }
        ],
        entity_mentions=["地点/景区/贝加尔湖"],
        tag_mentions=["Topic/旅行/玩法/自然风光", "Topic/摄影/风光摄影"],
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
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=1,
        allow_partial=False,
    )

    assert report["gate"]["passed"], report
    packet = read_json(batch_content_plan_packet_path(task_id, target_batch))
    assert packet["items"][0]["carrier"] == "image"
    assert packet["items"][0]["researchLane"] == "image"
    assert packet["items"][0]["sourceCollectionId"] == "pin_349099408623239532"
    assert len(packet["items"][0]["assetRefs"]) == 1


def test_content_plan_bridge_preserves_source_titles_without_synthetic_dedupe():
    from _common.io import read_json
    from _common.paths import batch_content_plan_packet_path

    spec = store.scaffold_spec(
        vertical="photography",
        organize_by="主题",
        key="Pinterest归因图验证",
        name="Bridge标题去重",
        scope={
            "theme": "Pinterest归因图验证",
            "entityTypes": ["主题/摄影"],
            "coverageTargets": [{"entityType": "主题/摄影", "name": "风光摄影"}],
        },
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityHomepagesPerTarget": 0,
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 2,
            },
        },
        created_by="test",
    )
    task_id = spec["taskId"]
    store.save_spec(spec)
    ss._known_coverage_entity_targets.cache_clear()

    batch = "content_plan_pinterest_title_dedupe"
    target_batch = "bridge_pinterest_title_dedupe_batch"
    frontier = ss.build_site_frontier_packet(
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        daily_target=1_000,
        queue_backend="reliabletask",
        end_date="2026-07-05",
        admission_mode=ss.ADMISSION_ATTRIBUTION_PUBLISH_INGEST,
    )
    assert frontier["gate"]["passed"], frontier["gate"]
    ss.write_site_frontier_packet(frontier)

    image_dir = _TMP / "attribution_title_dedupe"
    image_a = _write_large_image(image_dir / "a.jpg")
    image_b = _write_large_image(image_dir / "b.jpg")
    rows = [
        {
            "ref": "art_a",
            "url": "https://www.pinterest.com/pin/140806234820407/",
            "caption": "Canada landscape photography",
            "image_path": image_a,
            "collection_id": "pin_140806234820407",
        },
        {
            "ref": "art_b",
            "url": "https://www.pinterest.com/pin/140806234660858/",
            "caption": "Snow mountain silhouette",
            "image_path": image_b,
            "collection_id": "pin_140806234660858",
        },
    ]
    for row in rows:
        candidate = ss.build_site_candidate_packet(
            vertical="photography",
            site_id="pinterest",
            batch_id=batch,
            url=row["url"],
            lane="image",
            title="Art",
            text="",
            published_at="2026-07-05",
            author="Pinterest原作者A",
            assets=[
                {
                    "assetId": row["ref"],
                    "url": "https://i.pinimg.com/originals/example.jpg",
                    "sourceUrl": row["url"],
                    "downloadUrl": "https://i.pinimg.com/originals/example.jpg",
                    "sourcePath": str(row["image_path"]),
                    "localPath": str(row["image_path"]),
                    "license": "attribution_no_watermark",
                    "credit": "Pinterest原作者A",
                    "creator": "Pinterest原作者A",
                    "termsUrl": "https://policy.pinterest.com/terms-of-service",
                    "usageScope": "commercial",
                    "authorizationProof": row["url"],
                    "authorizationBasis": "attribution_no_watermark",
                    "modelReleaseStatus": "not_required",
                    "propertyReleaseStatus": "not_required",
                    "sourceCollectionId": row["collection_id"],
                    "collectionPageUrl": row["url"],
                    "caption": row["caption"],
                    "title": "Art",
                    "width": 1800,
                    "height": 1200,
                    "mimeType": "image/jpeg",
                    "pinUrl": row["url"],
                    "discoveryUrl": row["url"],
                    "originalAssetUrl": "https://i.pinimg.com/originals/example.jpg",
                    "sourceAuthor": "Pinterest原作者A",
                    "repostAttribution": f"Pinterest public pin {row['url']}",
                    "watermarkScan": "no_explicit_watermark",
                    "ocrScan": "no_text_detected",
                    "collectedAt": "2026-07-05T11:00:53.470157+00:00",
                }
            ],
            entity_mentions=["主题/摄影/风光摄影"],
            tag_mentions=["Topic/摄影/风光摄影", "Topic/旅行/玩法/自然风光"],
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
        vertical="photography",
        site_id="pinterest",
        batch_id=batch,
        task_id=task_id,
        target_batch=target_batch,
        limit=2,
        entity_type="主题/摄影",
        allow_partial=False,
    )

    assert report["gate"]["passed"], report
    packet = read_json(batch_content_plan_packet_path(task_id, target_batch))
    titles = [item["title"] for item in packet["items"]]
    assert titles == ["Art", "Art"]
    assert sorted(item["caption"] for item in packet["items"]) == sorted(
        [
        "Canada landscape photography",
        "Snow mountain silhouette",
        ]
    )


def test_handle_content_plan_prints_json_report(monkeypatch, capsys):
    import argparse
    import site_supply.content_plan as content_plan_mod

    report = {
        "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
        "gate": {"passed": True},
        "itemCount": 1,
    }

    monkeypatch.setattr(content_plan_mod, "build_site_content_plan", lambda **_kwargs: report)

    content_plan_mod.handle_content_plan(
        argparse.Namespace(
            vertical="photography",
            site_id="pinterest",
            batch="smoke_real_pin_1",
            task="摄影/主题/Pinterest归因图验证/景区/贝加尔湖图片作品Smoke",
            target_batch="smoke_real_pin_1_task",
            limit=1,
            refs="",
            entity_type="地点/景区",
            intent="",
            audience="",
            max_images_per_candidate=4,
            allow_partial=False,
        )
    )

    captured = capsys.readouterr()
    assert "\"itemCount\": 1" in captured.out
    assert "\"passed\": true" in captured.out


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
