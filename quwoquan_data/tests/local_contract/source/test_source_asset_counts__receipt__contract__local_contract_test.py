from __future__ import annotations

from types import SimpleNamespace

from content.source.handler_fetch_images import _provider_asset_counts
from core.data_issue import DataIssueCode


def test_provider_asset_counts_expose_display_name_funnel_and_rights_status() -> None:
    specs = [
        {
            "platform": "Pinterest",
            "sourceId": "pin-board-1",
            "title": "西湖秋季摄影",
        },
        {
            "platform": "Pinterest",
            "sourceId": "pin-board-1",
            "title": "西湖秋季摄影",
        },
        {
            "platform": "Tuchong",
            "sourceId": "tuchong-topic-1",
            "title": "西湖蓝调时刻",
        },
    ]

    rows = _provider_asset_counts(
        image_specs=specs,
        downloaded_by_source={
            ("Pinterest", "pin-board-1"): 2,
            ("Tuchong", "tuchong-topic-1"): 1,
        },
        accepted_images=[
            {
                "platform": "Pinterest",
                "sourceId": "pin-board-1",
                "rightsAuditStatus": "unverified",
            },
            {
                "platform": "Tuchong",
                "sourceId": "tuchong-topic-1",
                "rightsAuditStatus": "unknown",
            },
        ],
    )

    assert rows == [
        {
            "displayName": "西湖秋季摄影",
            "provider": "Pinterest",
            "plannedAssetCount": 2,
            "discoveredAssetCount": 2,
            "downloadedAssetCount": 2,
            "acceptedAssetCount": 1,
            "rejectedAssetCount": 1,
            "verifiedAssetCount": 0,
            "unverifiedAssetCount": 1,
            "restrictedAssetCount": 0,
            "unknownAssetCount": 0,
        },
        {
            "displayName": "西湖蓝调时刻",
            "provider": "Tuchong",
            "plannedAssetCount": 1,
            "discoveredAssetCount": 1,
            "downloadedAssetCount": 1,
            "acceptedAssetCount": 1,
            "rejectedAssetCount": 0,
            "verifiedAssetCount": 0,
            "unverifiedAssetCount": 0,
            "restrictedAssetCount": 0,
            "unknownAssetCount": 1,
        },
    ]


def test_one_professional_work_unit_exclusion_is_typed_without_dropping_siblings() -> None:
    from content.source.handler_fetch_images import (
        _is_frozen_professional_image_work_unit,
        _professional_image_work_unit_exclusions,
    )

    specs = [
        {
            "researchLane": "image",
            "acquisitionReceiptRef": "receipts/current.json",
            "professionalAssetId": f"professional:{index:02d}",
            "professionalContentSha256": "sha256:" + f"{index:064x}",
        }
        for index in range(11)
    ]
    accepted = [
        {
            "professionalAssetId": spec["professionalAssetId"],
            "professionalContentSha256": spec["professionalContentSha256"],
        }
        for spec in specs[:10]
    ]

    assert all(_is_frozen_professional_image_work_unit(spec) for spec in specs)
    exclusions = _professional_image_work_unit_exclusions(
        entity_id="神仙居",
        image_specs=specs,
        accepted_images=accepted,
    )

    assert len(exclusions) == 1
    assert exclusions[0].code is DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL
    assert exclusions[0].ref == "神仙居"
    assert dict(exclusions[0].attributes)["assetId"] == "professional:10"
    assert all(
        sibling["professionalAssetId"] not in exclusions[0].message
        for sibling in specs[:10]
    )

    from content.source.handler_fetch_media import _media_gate_issues

    fetch_issues, blocking_issues, typed_issues = _media_gate_issues(
        SimpleNamespace(
            entity_id="神仙居",
            image_lane_selected=True,
            required_image_work_images=10,
            homepage_media_selected=False,
            required_homepage_media=0,
            image_rights_issues=(),
            required_images=10,
            professional_exclusions=tuple(exclusions),
        ),
        kept_by_lane={"image": 10, "homepage": 0},
        kept_images=10,
    )
    assert fetch_issues == []
    assert blocking_issues == []
    assert typed_issues == exclusions
