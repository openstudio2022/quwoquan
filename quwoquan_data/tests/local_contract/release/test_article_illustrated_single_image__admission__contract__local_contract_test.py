# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t3
"""文章配图张数不设下限：一张图的 illustrated 文章在 pool-query 与 release admission 两处都合法。

策略侧早已声明 `requireCoverAndBodyImage: false`；这里锁定代码与策略一致，避免「≥2 图」硬门回潮。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical import pool_query, release_admission  # noqa: E402
from content.release.canonical.object_transaction_contract import ObjectTransactionError  # noqa: E402


def _cover(asset_id: str = "cover") -> dict:
    return {"assetId": asset_id, "kind": "image", "role": "cover", "sourceRef": "sources/x/source.md"}


def _detail(asset_id: str) -> dict:
    return {"assetId": asset_id, "kind": "image", "role": "detail", "sourceRef": "sources/x/source.md"}


def test_pool_query_admits_single_image_article(tmp_path: Path) -> None:
    post_ref = "article/人文/单图文章/1"
    manifest = tmp_path / "posts" / post_ref / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"publishMediaMode": "illustrated", "assets": [_cover()]}), encoding="utf-8")

    assert pool_query._illustrated_article_issue(tmp_path, post_ref) == ""

    manifest.write_text(json.dumps({"publishMediaMode": "illustrated", "assets": [_cover(), _detail("d1"), _detail("d2")]}), encoding="utf-8")
    assert pool_query._illustrated_article_issue(tmp_path, post_ref) == ""

    manifest.write_text(json.dumps({"publishMediaMode": "illustrated", "assets": [_detail("d1")]}), encoding="utf-8")
    assert "needs exactly 1 cover" in pool_query._illustrated_article_issue(tmp_path, post_ref)


def test_release_admission_counts_single_image_article_as_illustrated() -> None:
    single = {"objectRef": "posts/article/人文/单图文章/1", "manifest": {"publishMediaMode": "illustrated", "assets": [_cover()]}}
    assert release_admission._article_media_mode(single) == "illustrated"

    many = {"objectRef": "posts/article/人文/多图文章/1", "manifest": {"publishMediaMode": "illustrated", "assets": [_cover(), _detail("d1")]}}
    assert release_admission._article_media_mode(many) == "illustrated"

    text_only = {"objectRef": "posts/article/人文/无图/1", "manifest": {"publishMediaMode": "text_only", "assets": []}}
    assert release_admission._article_media_mode(text_only) == "text_only"

    two_covers = {"objectRef": "posts/article/人文/双封面/1", "manifest": {"publishMediaMode": "illustrated", "assets": [_cover("a"), _cover("b")]}}
    with pytest.raises(ObjectTransactionError, match="exactly one cover"):
        release_admission._article_media_mode(two_covers)
