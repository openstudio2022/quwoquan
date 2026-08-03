from __future__ import annotations

from content.source.handler_fetch_images import _provider_asset_counts


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
