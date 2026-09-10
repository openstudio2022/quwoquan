# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t9
"""水印只记录不阻断：AI 申报的 watermarkStatus/watermarkKind 经 rights 行进入 release admission，
present 的资产汇总为 watermarkedAssetIds 供运营逐条审核；缺席只能是 unknown，不得假定 absent。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical import release_admission  # noqa: E402
from governance.coverage.distribution import project_asset_admission  # noqa: E402


def _rights_row(asset_id: str, **overrides: object) -> dict:
    row = {
        "assetId": asset_id,
        "contentSha256": "sha256:" + "1" * 64,
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:x.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0",
        "authorizationProof": "https://creativecommons.org/licenses/by-sa/4.0",
        "creator": "唐代吉",
        "platform": "Wikimedia Commons",
        "capturedAt": "2026-09-07T00:00:00Z",
        "rightsStatus": "verified",
        "rightsIssues": [],
        "asset": {"sha256": "sha256:" + "1" * 64, "bytes": 10, "mimeType": "image/jpeg"},
    }
    row.update(overrides)
    return row


def test_projection_transcribes_declared_watermark_and_defaults_to_unknown() -> None:
    signed = project_asset_admission(
        _rights_row("a", watermarkStatus="present", watermarkKind="author_signature"), object_ref="posts/image/x/1"
    )
    assert (signed["watermarkStatus"], signed["watermarkKind"]) == ("present", "author_signature")

    legacy = project_asset_admission(_rights_row("b"), object_ref="posts/image/x/1")
    assert (legacy["watermarkStatus"], legacy["watermarkKind"]) == ("unknown", "unknown")


def test_admission_lists_watermarked_assets_without_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _projected(asset_id: str, object_ref: str, **overrides: object) -> dict:
        return project_asset_admission(_rights_row(asset_id, **overrides), object_ref=object_ref)

    objects = [
        {
            "objectRef": "posts/image/风光/a/1",
            "carrier": "image",
            "assets": [_projected("logo", "posts/image/风光/a/1", watermarkStatus="present", watermarkKind="platform_logo")],
            "manifest": {"assets": [{"assetId": "logo", "kind": "image"}]},
            "contentReviewApproved": True,
        },
        {
            "objectRef": "posts/image/风光/b/1",
            "carrier": "image",
            "assets": [_projected("clean", "posts/image/风光/b/1", watermarkStatus="absent", watermarkKind="none")],
            "manifest": {"assets": [{"assetId": "clean", "kind": "image"}]},
            "contentReviewApproved": True,
        },
    ]
    monkeypatch.setattr(release_admission, "_object_rows", lambda *_args, **_kwargs: objects)

    document = release_admission.build_release_asset_admission(
        release_id="watermark-001",
        objects_root=tmp_path,
        desired={"entities": [], "posts": ["image/风光/a/1", "image/风光/b/1"]},
    )

    assert document["watermarkedAssetIds"] == ["logo"]
    assert document["authorizationRequiredAssetIds"] == []
    assert len(document["assets"]) == 2, "水印只记录，不把对象排除出 release"
    by_id = {row["assetId"]: row for row in document["assets"]}
    assert by_id["logo"]["watermarkKind"] == "platform_logo"
    assert by_id["clean"]["watermarkStatus"] == "absent"
