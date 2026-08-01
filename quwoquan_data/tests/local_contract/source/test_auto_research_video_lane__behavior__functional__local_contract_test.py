from __future__ import annotations

from core.io import read_json
from content.execution import store
from content.source.research.auto_plan_public import write_auto_research_plans
from content.source.research import auto_plan_video
from content.source.research.auto_plan_video import (
    discover_commons_sourced_videos,
    write_video_lane,
)
from content.source import handler_fetch_setup
from content.source.source_unit import resolve_entity_object_dir
from governance.content_supply_policy import load_content_supply_policy
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def _frame(entity: str, ordinal: int) -> dict[str, object]:
    proof = f"https://commons.wikimedia.org/wiki/File:{entity}_{ordinal}.jpg"
    return {
        "url": f"https://upload.wikimedia.org/{entity}_{ordinal}.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY-SA 4.0",
        "credit": f"Creator {ordinal}",
        "creator": f"Creator {ordinal}",
        "sourceUrl": proof,
        "collectionPageUrl": proof,
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "licenseSnapshot": "CC BY-SA 4.0 recorded on the Commons file page",
        "authorizationProof": proof,
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "width": 1600,
        "height": 1000,
        "caption": f"{entity} 景观画面 {ordinal}",
        "relevance": f"{entity} 景观画面 {ordinal}",
    }


def test_video_lane_writes_minimum_rights_cleared_frame_plan(tmp_path):
    entity = "测试实体甲"
    required = (
        load_content_supply_policy("travel").video_delivery.minimum_source_frames
    )
    report: dict[str, object] = {"sourceUnavailable": [], "videoFrames": []}
    updated: list[dict[str, object]] = []

    write_video_lane(
        entity_id=entity,
        entity_aliases=[entity],
        vertical="travel",
        plan_dir=tmp_path,
        force=True,
        report=report,
        updated=updated,
        open_license_image_pool=[
            _frame(entity, ordinal) for ordinal in range(1, required + 2)
        ],
        sourced_video_pool=[],
    )

    payload = read_json(tmp_path / "video_source_plan.json")["payload"]
    assert len(payload["assets"]) == required
    assert payload["sourceUnavailable"] == []
    assert {asset["researchLane"] for asset in payload["assets"]} == {"video"}
    assert all(asset["authorizationProof"] for asset in payload["assets"])
    assert updated == [
        {"entityId": entity, "lane": "video", "videos": 0, "assets": required}
    ]


def test_video_lane_retains_frame_sequence_under_direct_video_candidate(tmp_path):
    video = {
        "sourceId": "wikimedia_commons_video",
        "assetUrl": "https://upload.wikimedia.org/wikipedia/commons/test.webm",
    }
    report: dict[str, object] = {"sourceUnavailable": [], "videoFrames": []}
    updated: list[dict[str, object]] = []

    write_video_lane(
        entity_id="测试实体甲",
        entity_aliases=["测试实体甲"],
        vertical="travel",
        plan_dir=tmp_path,
        force=True,
        report=report,
        updated=updated,
        open_license_image_pool=[_frame("测试实体甲", 1), _frame("测试实体甲", 2)],
        sourced_video_pool=[video],
    )

    payload = read_json(tmp_path / "video_source_plan.json")["payload"]
    assert payload["videos"] == [video]
    assert len(payload["assets"]) == 2
    assert payload["diagnostic"]["fallbackFramesRetained"] is True
    assert payload["sourceUnavailable"] == []


def test_commons_video_discovery_records_anonymous_provider_funnel(monkeypatch):
    def value(raw: str) -> dict[str, str]:
        return {"value": raw}

    monkeypatch.setattr(
        auto_plan_video.network_io,
        "wiki_api",
        lambda *_args, **_kwargs: {
            "query": {
                "pages": [
                    {
                        "pageid": 1,
                        "title": "File:西湖旅游航拍.webm",
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/west-lake.webm",
                            "descriptionurl": (
                                "https://commons.wikimedia.org/wiki/File:West_Lake.webm"
                            ),
                            "mediatype": "VIDEO",
                            "size": 1024,
                            "duration": 12,
                            "extmetadata": {
                                "ImageDescription": value("西湖水面旅行航拍"),
                                "LicenseShortName": value("CC BY-SA 4.0"),
                                "LicenseUrl": value(
                                    "https://creativecommons.org/licenses/by-sa/4.0/"
                                ),
                                "Artist": value("Commons Creator"),
                            },
                        }],
                    },
                    {
                        "pageid": 2,
                        "title": "File:西湖无许可.webm",
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/rejected.webm",
                            "descriptionurl": (
                                "https://commons.wikimedia.org/wiki/File:Rejected.webm"
                            ),
                            "mediatype": "VIDEO",
                            "size": 1024,
                            "duration": 12,
                            "extmetadata": {
                                "ImageDescription": value("西湖水面"),
                                "LicenseShortName": value("All rights reserved"),
                                "LicenseUrl": value("https://example.test/terms"),
                                "Artist": value("Unknown"),
                            },
                        }],
                    },
                ],
            },
        },
    )

    diagnostics: list[dict[str, object]] = []
    videos = discover_commons_sourced_videos(
        "西湖",
        entity_aliases=[],
        diagnostics=diagnostics,
    )

    assert len(videos) == 1
    assert videos[0]["anonymousAccess"] is True
    assert videos[0]["rightsStatus"] == "unverified"
    assert videos[0]["credentialAssertion"] == (
        "no_cookie_no_api_key_no_account_session"
    )
    assert diagnostics == [{
        "provider": "wikimedia_commons_video",
        "entityId": "西湖",
        "attempted": True,
        "queryCount": 1,
        "discovered": 2,
        "rejectedMalformed": 0,
        "rejectedByRelevance": 0,
        "rejectedByRights": 1,
        "rejectedByQuality": 0,
        "selectedForAnonymousDownload": 1,
        "notAttemptedProviders": [
            "pexels_videos",
            "pixabay_videos",
            "pond5",
            "storyblocks",
            "youtube",
            "vimeo",
            "bilibili",
            "douyin",
            "tiktok",
            "weibo",
            "toutiao_video",
        ],
    }]


def test_direct_video_failure_keeps_frozen_frame_fallback(monkeypatch, tmp_path):
    entity = "测试实体甲"
    frames = [_frame(entity, 1), _frame(entity, 2)]
    direct = {
        "sourceId": "wikimedia_commons_video",
        "assetUrl": "https://upload.wikimedia.org/wikipedia/commons/test.webm",
    }
    monkeypatch.setattr(
        handler_fetch_setup,
        "curated_sourced_videos_for_entity",
        lambda *_args: [direct],
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "fetch_admitted_sourced_videos",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("watermark detected")),
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "curated_homepage_media_for_entity",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "curated_images_for_entity",
        lambda *_args, research_lane=None, **_kwargs: (
            frames if research_lane == "video" else []
        ),
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "resolve_entity_object_dir",
        lambda *_args, **_kwargs: tmp_path,
    )

    plan = handler_fetch_setup.prepare_entity_fetch_plan(
        execution_id="20260731--travel-video-supply--test-region-a--pilot-001",
        entity_id=entity,
        entity_type="地点/景区",
        domain="地点",
        etype="景区",
        selected_lanes={"video"},
    )

    assert plan.sourced_video_evidence == []
    assert plan.sourced_video_failure == "ValueError: watermark detected"
    assert plan.image_specs == frames


def test_video_lane_rescues_nonempty_but_underfilled_frame_pool(monkeypatch):
    import content.source.research.auto_plan_writer as research_mod

    entity = "故宫博物院"
    task = "20260731--travel-video-source-rescue--test-region-a--pilot-001"
    builder = ExecutionFixtureBuilder(
        task,
        targets=({"entityType": "地点/景区", "name": entity},),
    )
    builder.build()
    spec = builder.spec_payload()
    store.save_spec(spec)
    first_pass = [_frame(entity, 1)]
    rescue_frames = [_frame(entity, 2), _frame(entity, 3)]
    calls = {"count": 0}

    def fake_pools(entity_id, **kwargs):
        assert entity_id == entity
        calls["count"] += 1
        assert kwargs["entity_aliases"]
        images = first_pass if calls["count"] == 1 else rescue_frames
        return {
            "commons": images,
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [],
            "voyage_page_images": [],
        }

    monkeypatch.setattr(
        research_mod,
        "_wiki_title_for_entity",
        lambda host, *_args, **_kwargs: entity if host == "zh.wikipedia.org" else "",
    )
    monkeypatch.setattr(research_mod, "_wiki_related_titles_for_entity", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(research_mod, "_wikidata_item_for_zhwiki", lambda *_args: "")
    monkeypatch.setattr(research_mod, "_wikidata_item_for_entity_search", lambda *_args: "")
    monkeypatch.setattr(research_mod, "_wikidata_entity_aliases", lambda *_args: [])
    monkeypatch.setattr(research_mod, "_known_entity_aliases", lambda *_args: [])
    monkeypatch.setattr(research_mod, "_official_website", lambda *_args: "")
    monkeypatch.setattr(research_mod, "_known_official_website", lambda *_args: "")
    monkeypatch.setattr(research_mod, "discover_homepage_authority", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(research_mod, "_verified_image_collections_from_prior_plans", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(research_mod, "_discover_open_license_image_pools", fake_pools)
    monkeypatch.setattr(research_mod, "discover_commons_sourced_videos", lambda *_args, **_kwargs: [])

    report = write_auto_research_plans(
        task,
        [entity],
        entity_type="景区",
        force=True,
        lanes={"video"},
    )

    assert calls["count"] == 2
    assert report["sourceUnavailable"] == []
    rescue = [
        row
        for row in report["rescueEvents"]
        if row["lane"] == "video"
    ]
    assert rescue == [{
        "entityId": entity,
        "lane": "video",
        "reason": "qualified_video_frames_below_minimum",
        "qualifiedFramesBefore": 1,
        "qualifiedFramesAfter": 2,
        "minimumFrames": 2,
        "addedCandidates": 2,
    }]
    plan = read_json(
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "video_source_plan.json"
    )["payload"]
    assert len(plan["assets"]) == 2
    assert plan["sourceUnavailable"] == []
