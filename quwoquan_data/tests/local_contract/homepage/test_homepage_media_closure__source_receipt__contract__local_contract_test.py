from __future__ import annotations

from pathlib import Path

import pytest
from content.homepage import homepage_media_contract as contract
from core.io import write_json


def _write_source(root: Path) -> str:
    source_ref = "sources/homepage-source/source.md"
    unit = root / "sources" / "homepage-source"
    unit.mkdir(parents=True)
    (unit / "source.md").write_text("# source\n", encoding="utf-8")
    write_json(
        unit / "meta.json",
        {
            "title": "实体主页摄影素材",
            "platform": "Pinterest",
            "assetCount": 2,
            "assetFunnel": {
                "candidateCount": 3,
                "keptCount": 2,
                "fetchFailures": [],
            },
        },
    )
    write_json(
        unit / "assets" / "index.json",
        {
            "assets": [
                {"sourceAssetId": "cover", "rightsAuditStatus": "unverified"},
                {"sourceAssetId": "inline", "rightsAuditStatus": "verified"},
            ]
        },
    )
    return source_ref


def test_homepage_receipt_manifest_and_cli_read_back_same_source_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_ref = _write_source(tmp_path)
    monkeypatch.setattr(contract, "execution_root", lambda _execution_id: tmp_path)
    object_dir = tmp_path / "entities" / "place"
    assets = [
        {
            "assetId": "homepage-cover",
            "role": "cover",
            "sourceRef": source_ref,
        },
        {
            "assetId": "homepage-inline",
            "role": "inline",
            "sourceRef": source_ref,
        },
    ]

    receipt, receipt_ref = contract.write_homepage_source_asset_receipt(
        "execution",
        entity_dir=object_dir,
        object_ref="place",
        source_ref=source_ref,
        assets=assets,
    )
    manifest = {
        "assets": assets,
        "heroAssetId": "homepage-cover",
        "mediaAssetIds": ["homepage-cover", "homepage-inline"],
        "sourceAssetReceiptRef": receipt_ref,
        "sourceAssetReceiptDigest": receipt["receiptDigest"],
        "sourceAssetCounts": receipt["sourceAssetCounts"],
    }
    entity = {"imageSourceRefs": [source_ref]}

    assert contract.homepage_manifest_media_issues(
        object_dir, manifest, entity, "place"
    ) == []
    assert receipt["assetCount"] == 2
    assert receipt["sourceAssetCounts"][0]["displayName"] == "实体主页摄影素材"
    assert receipt["sourceAssetCounts"][0]["provider"] == "Pinterest"
    assert receipt["sourceAssetCounts"][0]["acceptedAssetCount"] == 2
    assert receipt["sourceAssetCounts"][0]["rejectedAssetCount"] == 1
    output = capsys.readouterr().out
    assert "displayName=实体主页摄影素材 provider=Pinterest assets=2" in output


def test_homepage_media_closure_rejects_empty_assets(tmp_path: Path) -> None:
    issues = contract.homepage_manifest_media_issues(
        tmp_path,
        {"assets": [], "heroAssetId": "", "mediaAssetIds": []},
        {"imageSourceRefs": []},
        "place",
    )
    assert any("manifest.assets must not be empty" in issue for issue in issues)
    assert any("imageSourceRefs must not be empty" in issue for issue in issues)
