from __future__ import annotations

from pathlib import Path

import pytest
from content.post import object_index as content_object
from content.post.article import article_media_contract as contract
from core.io import read_json, write_json


def _source_unit(root: Path) -> str:
    ref = "sources/article-source/source.md"
    unit = root / "sources" / "article-source"
    unit.mkdir(parents=True)
    (unit / "source.md").write_text("# source\n", encoding="utf-8")
    write_json(
        unit / "meta.json",
        {
            "title": "同源文章摄影素材",
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
                {"sourceAssetId": "one", "rightsAuditStatus": "unverified"},
                {"sourceAssetId": "two", "rightsAuditStatus": "verified"},
            ]
        },
    )
    return ref


def _asset(asset_id: str, role: str, source_ref: str) -> dict[str, str]:
    return {
        "assetId": asset_id,
        "role": role,
        "sourceRef": source_ref,
        "sourceAssetRef": f"{source_ref.rsplit('/', 1)[0]}/assets/{asset_id}.jpg",
    }


def test_materialized_article_projects_single_read_api_and_body_figure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_ref = _source_unit(tmp_path)
    object_dir = tmp_path / "posts" / "article"
    monkeypatch.setattr(contract, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        content_object,
        "content_object_dir",
        lambda _execution_id, _ref: object_dir,
    )
    payload = {
        "carrier": "article",
        "baseSourceRef": source_ref,
        "assets": [
            _asset("cover-one", "cover", source_ref),
            _asset("body-one", "node", source_ref),
        ],
        "articleRenderProfile": {"template": "journal"},
    }

    article, actions = contract.materialize_article_media(
        "execution", "article-ref", "# 标题\n\n## 正文\n\n正文段落。\n", payload
    )

    assert "asset://body-one" in article
    assert "article_body_media_injected" in actions
    closure = contract.read_article_media_closure(
        {"articleRenderProfile": payload["articleRenderProfile"]}
    )
    assert closure["mode"] == "illustrated"
    assert closure["coverAssetId"] == "cover-one"
    assert closure["bodyAssetIds"] == ["body-one"]
    assert closure["assetCount"] == 2
    assert closure["sourceAssetCounts"][0] == {
        "displayName": "同源文章摄影素材",
        "provider": "Pinterest",
        "plannedAssetCount": 3,
        "discoveredAssetCount": 3,
        "downloadedAssetCount": 3,
        "acceptedAssetCount": 2,
        "rejectedAssetCount": 1,
        "verifiedAssetCount": 1,
        "unverifiedAssetCount": 1,
        "restrictedAssetCount": 0,
        "unknownAssetCount": 0,
    }
    receipt = read_json(object_dir / contract.ARTICLE_SOURCE_ASSET_RECEIPT_REF)
    assert receipt["assetCount"] == 2
    assert [row["position"] for row in receipt["usagePositions"]] == [
        "cover_frontmatter",
        "body_figure",
    ]
    assert contract.read_article_media_closure(
        {
            "articleRenderProfile": payload["articleRenderProfile"],
            "assets": payload["assets"],
        },
        object_dir=object_dir,
    ) == closure


def test_article_media_contract_rejects_cover_only_and_cross_source() -> None:
    source_ref = "sources/base/source.md"
    cover_only = {
        "carrier": "article",
        "assets": [_asset("cover", "cover", source_ref)],
    }
    issues = contract.article_media_contract_issues(cover_only, source_ref)
    assert any("cover and at least one body image" in issue for issue in issues)

    cross_source = {
        "carrier": "article",
        "assets": [
            _asset("cover", "cover", source_ref),
            _asset("body", "node", "sources/other/source.md"),
        ],
    }
    issues = contract.article_media_contract_issues(cross_source, source_ref)
    assert any("sourceRef must equal baseSourceRef" in issue for issue in issues)


def test_text_only_article_is_explicit_and_asset_free() -> None:
    source_ref = "sources/base/source.md"
    assert contract.article_media_contract_issues(
        {
            "carrier": "article",
            "publishMediaMode": "text_only",
            "assets": [],
        },
        source_ref,
    ) == []
    issues = contract.article_media_contract_issues(
        {
            "carrier": "article",
            "publishMediaMode": "text_only",
            "assets": [_asset("cover", "cover", source_ref)],
        },
        source_ref,
    )
    assert issues == ["text_only article must not retain image assets"]


def test_article_media_closure_reader_rejects_inference_from_assets() -> None:
    with pytest.raises(ValueError, match="missing or incomplete"):
        contract.read_article_media_closure(
            {
                "assets": [
                    {"assetId": "cover"},
                    {"assetId": "body"},
                ]
            }
        )
