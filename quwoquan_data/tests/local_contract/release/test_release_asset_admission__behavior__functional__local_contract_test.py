from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.release_admission import (
    _article_media_coverage,
    build_release_asset_admission,
)
from governance.coverage.distribution import (
    ProductLifecycleState,
    ReleaseClass,
    load_content_distribution_policy,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _rights_asset(asset_id: str) -> dict[str, object]:
    return {
        "assetId": asset_id,
        "asset": {"sha256": "sha256:" + asset_id[-1] * 64, "bytes": 128},
        "rightsAuditStatus": "unverified",
        "rightsAuditIssues": ["commercial authorization missing"],
        "sourceUrl": f"https://media.example/{asset_id}",
        "platform": "Pinterest",
        "creator": "摄影师",
        "capturedAt": "2026-08-02T00:00:00Z",
        "license": "unknown",
        "termsUrl": "https://media.example/terms",
        "authorizationProof": "",
    }


def _release_objects(root: Path) -> dict[str, list[str]]:
    desired = {
        "entities": ["home"],
        "posts": ["article", "image", "video"],
        "creators": ["creator"],
        "tags": [],
    }
    _write(root / "entities/home/manifest.json", {"entityRef": "home"})
    _write(root / "entities/home/rights.json", {"assets": [_rights_asset("asset-h")]})
    _write(
        root / "posts/article/manifest.json",
        {
            "contentType": "article",
            "publishMediaMode": "same_source_illustrated",
            "assets": [
                {
                    "assetId": "article-cover",
                    "kind": "image",
                    "role": "cover",
                    "sourceUnitRef": "sources/article-1/source.md",
                },
                {
                    "assetId": "article-body",
                    "kind": "image",
                    "role": "embedded",
                    "sourceUnitRef": "sources/article-1/source.md",
                },
            ],
            "imageBindings": [
                {"assetId": "article-cover"},
                {"assetId": "article-body"},
            ],
        },
    )
    _write(
        root / "posts/article/rights.json",
        {"assets": [_rights_asset("asset-a"), _rights_asset("asset-b")]},
    )
    for name, suffix in (("image", "i"), ("video", "v")):
        _write(root / f"posts/{name}/manifest.json", {"contentType": name, "assets": []})
        _write(
            root / f"posts/{name}/rights.json",
            {"assets": [_rights_asset(f"asset-{suffix}")]},
        )
    _write(
        root / "creators/creator/rights_snapshots/avatar.json",
        {"commercialRights": _rights_asset("asset-c")},
    )
    return desired


def test_research_release_accepts_unverified_assets_for_all_four_carriers(
    tmp_path: Path,
) -> None:
    desired = _release_objects(tmp_path)
    admission = build_release_asset_admission(
        release_id="research-release",
        objects_root=tmp_path,
        desired=desired,
        policy=load_content_distribution_policy(),
    )

    assert admission["releaseClass"] == "research"
    assert admission["containsUnverifiedAssets"] is True
    assert admission["rightsStatusCounts"]["unverified"] == 6
    assert admission["researchAcceptedCount"] == 4
    assert admission["commercialAcceptedCount"] == 0
    assert {row["carrier"]: row["researchAcceptedCount"] for row in admission["carrierCounts"]} == {
        "homepage": 1,
        "article": 1,
        "image": 1,
        "video": 1,
    }


def test_commercial_release_rejects_same_unverified_assets(tmp_path: Path) -> None:
    desired = _release_objects(tmp_path)
    research = load_content_distribution_policy()
    commercial = replace(
        research,
        product_lifecycle_state=ProductLifecycleState.COMMERCIAL,
        release_class=ReleaseClass.COMMERCIAL,
    )

    with pytest.raises(ObjectTransactionError, match="non-commercial assets"):
        build_release_asset_admission(
            release_id="commercial-release",
            objects_root=tmp_path,
            desired=desired,
            policy=commercial,
        )


def test_article_media_coverage_requires_ninety_percent() -> None:
    policy = load_content_distribution_policy()
    illustrated = {
        "carrier": "article",
        "objectRef": "posts/illustrated",
        "manifest": {
            "assets": [
                {
                    "kind": "image",
                    "role": "cover",
                    "sourceUnitRef": "sources/article-1/source.md",
                },
                {
                    "kind": "image",
                    "role": "embedded",
                    "sourceUnitRef": "sources/article-1/source.md",
                },
            ],
            "imageBindings": [{}, {}],
        },
    }
    text_only = {
        "carrier": "article",
        "objectRef": "posts/text-only",
        "manifest": {"assets": [], "publishMediaMode": "text_only"},
    }
    coverage = _article_media_coverage(
        [illustrated] * 9 + [text_only],
        policy=policy,
    )
    assert coverage["illustratedRate"] == 0.9

    with pytest.raises(ObjectTransactionError, match="article media coverage"):
        _article_media_coverage(
            [illustrated] * 8 + [text_only] * 2,
            policy=policy,
        )
