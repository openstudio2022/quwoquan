from __future__ import annotations

from content.source import handler_fetch_setup
from content.source.research import auto_plan_video
from content.source.research.auto_plan_video import (
    discover_commons_sourced_videos,
    write_video_lane,
)
from core.io import read_json


def _video() -> dict[str, object]:
    return {
        "sourceId": "wikimedia_commons_video",
        "assetUrl": "https://upload.wikimedia.org/wikipedia/commons/test.webm",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:Test.webm",
    }


def test_video_lane_writes_only_direct_video_candidates(tmp_path) -> None:
    report: dict[str, object] = {"sourceUnavailable": []}
    updated: list[dict[str, object]] = []

    write_video_lane(
        entity_id="测试实体甲",
        plan_dir=tmp_path,
        force=True,
        report=report,
        updated=updated,
        sourced_video_pool=[_video()],
    )

    payload = read_json(tmp_path / "video_source_plan.json")["payload"]
    assert payload["renderStrategy"] == "sourced_video"
    assert payload["videos"] == [_video()]
    assert "assets" not in payload
    assert payload["sourceUnavailable"] == []
    assert updated == [
        {"entityId": "测试实体甲", "lane": "video", "videos": 1}
    ]


def test_video_lane_writes_each_desired_asset_for_one_entity(tmp_path) -> None:
    videos = [
        {
            **_video(),
            "assetUrl": f"https://upload.wikimedia.org/video-{index}.webm",
        }
        for index in range(3)
    ]
    report: dict[str, object] = {"sourceUnavailable": []}

    write_video_lane(
        entity_id="测试实体甲",
        plan_dir=tmp_path,
        force=True,
        report=report,
        updated=[],
        sourced_video_pool=videos,
        desired_video_works=3,
    )

    payload = read_json(tmp_path / "video_source_plan.json")["payload"]
    assert payload["videos"] == videos
    assert len(payload["videos"]) == 3
    assert payload["sourceUnavailable"] == []


def test_video_lane_matches_frozen_receipt_by_entity_alias(
    tmp_path, monkeypatch
) -> None:
    """frozen receipt 的 entityId 允许是 canonical 名的别名。

    receipt 在「西湖」名下采集，catalog canonical 名是「杭州西湖」；名字
    归一化按 canonical 名 -> aliases 依次匹配（历史缺陷：M100 video lane
    对齐 receipt 时 0 匹配导致零供给 fail-closed）。
    """
    queried: list[str] = []
    spec = {
        "sourceId": "wikimedia_commons_video",
        "assetUrl": "https://upload.wikimedia.org/wikipedia/commons/westlake.webm",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:Westlake.webm",
        "professionalContentSha256": "sha256:" + "c" * 64,
    }

    def fake_specs(receipt_refs, *, entity_id, root=None, **_kwargs):
        queried.append(entity_id)
        return [dict(spec)] if entity_id == "西湖" else []

    monkeypatch.setattr(
        auto_plan_video, "acquired_video_specs_for_entity", fake_specs
    )
    report: dict[str, object] = {"sourceUnavailable": []}
    updated: list[dict[str, object]] = []

    write_video_lane(
        entity_id="杭州西湖",
        plan_dir=tmp_path,
        force=True,
        report=report,
        updated=updated,
        sourced_video_pool=[],
        acquisition_receipt_refs=["receipts/receipt-a.json"],
        entity_aliases=("西湖", "West Lake"),
    )

    assert queried == ["杭州西湖", "西湖"]
    payload = read_json(tmp_path / "video_source_plan.json")["payload"]
    assert payload["videos"] == [spec]
    assert updated == [{"entityId": "杭州西湖", "lane": "video", "videos": 1}]


def test_video_lane_shortfall_never_falls_back_to_images(tmp_path) -> None:
    report: dict[str, object] = {"sourceUnavailable": []}

    write_video_lane(
        entity_id="测试实体甲",
        plan_dir=tmp_path,
        force=True,
        report=report,
        updated=[],
        sourced_video_pool=[],
    )

    payload = read_json(tmp_path / "video_source_plan.json")["payload"]
    assert payload["videos"] == []
    assert payload["sourceUnavailable"][0]["code"] == (
        "DATA.MEDIA.PUBLISHABLE_SHORTFALL"
    )
    assert "assets" not in payload


def test_commons_video_discovery_records_anonymous_provider_funnel(
    monkeypatch,
) -> None:
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
                                "https://commons.wikimedia.org/wiki/"
                                "File:West_Lake.webm"
                            ),
                            "mediatype": "VIDEO",
                            "size": 1024,
                            "duration": 12,
                            "extmetadata": {
                                "ImageDescription": value("西湖水面旅行航拍"),
                                "LicenseShortName": value("CC BY-SA 4.0"),
                                "LicenseUrl": value(
                                    "https://creativecommons.org/"
                                    "licenses/by-sa/4.0/"
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
                                "https://commons.wikimedia.org/wiki/"
                                "File:Rejected.webm"
                            ),
                            "mediatype": "VIDEO",
                            "size": 1024,
                            "duration": 12,
                            "extmetadata": {
                                "ImageDescription": value("西湖水面"),
                                "LicenseShortName": value(
                                    "All rights reserved"
                                ),
                                "LicenseUrl": value(
                                    "https://example.test/terms"
                                ),
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
    assert diagnostics[0]["discovered"] == 2
    assert diagnostics[0]["rejectedByRights"] == 1
    assert diagnostics[0]["selectedForAnonymousDownload"] == 1


def test_direct_video_failure_does_not_collect_frame_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        handler_fetch_setup,
        "curated_sourced_videos_for_entity",
        lambda *_args, **_kwargs: [_video()],
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "fetch_admitted_sourced_videos",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("watermark detected")
        ),
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "curated_homepage_media_for_entity",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "curated_images_for_entity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("video lane must not request image candidates")
        ),
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "resolve_entity_object_dir",
        lambda *_args, **_kwargs: tmp_path,
    )

    plan = handler_fetch_setup.prepare_entity_fetch_plan(
        execution_id=(
            "20260731--travel-video-supply--test-region-a--pilot-001"
        ),
        entity_id="测试实体甲",
        entity_type="地点/景区",
        domain="地点",
        etype="景区",
        selected_lanes={"video"},
    )

    assert plan.sourced_video_evidence == []
    assert plan.sourced_video_failure == "ValueError: watermark detected"
    assert plan.image_specs == []
