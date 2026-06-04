"""Article Markdown package 格式契约测试（与交付物格式约定对齐，不依赖具体 release）。

构造一个 agent 创作正文的 article 包（front-matter + 封面 figure + 正文 + 资产清单），
断言 qwq-rich-md/1 版本标记、asset:// 引用在 manifest 声明、封面/标题/正文同文档流。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.article_package import (  # noqa: E402
    MARKDOWN_VERSION,
    asset_id_from_object_key,
    build_article_asset_manifest,
    compute_document_sha256,
)

TITLE = "峨眉山周末·自驾两日的真实体验"


def _build_fixture() -> tuple[str, dict]:
    object_key = "media/objects/sha256/ab/cd/" + ("abcd" * 16) + ".jpg"
    asset_id = asset_id_from_object_key(object_key)
    assets = [
        {
            "assetId": asset_id,
            "fileName": "cover.jpg",
            "caption": "峨眉山",
            "kind": "image",
            "scope": "cold_start",
            "objectKey": object_key,
            "imageLayout": "fullWidth",
        }
    ]
    body = (
        f"# {TITLE}\n\n"
        f"---\n"
        f"title: {TITLE}\n"
        f"template: journal\n"
        f"articleMarkdownVersion: {MARKDOWN_VERSION}\n"
        f"coverImage: asset://{asset_id}\n"
        f"---\n\n"
        "出发地成都，周五下班后我其实犹豫了很久要不要走这趟。\n\n"
        f':::figure id="cover" layout="fullWidth" caption="峨眉山"\n'
        f"asset://{asset_id}\n"
        ":::\n\n"
        "如果你也想看金顶日出，我会建议把第一天的车程压在六小时内。\n"
    )
    render_profile = {"template": "journal", "fontPreset": "clean"}
    article_asset_manifest = build_article_asset_manifest(body, assets, render_profile=render_profile)
    manifest = {
        "topicId": "峨眉山周末_自驾",
        "publishTitle": TITLE,
        "articleMarkdownVersion": MARKDOWN_VERSION,
        "articleAssetManifest": article_asset_manifest,
        "articleRenderProfile": render_profile,
        "articleMarkdownDigest": compute_document_sha256(body),
        "generator": "agent",
    }
    return body, manifest


def test_article_markdown_package_uses_qwq_rich_markdown_triple():
    markdown, manifest = _build_fixture()

    assert "articleMarkdownVersion: qwq-rich-md/1" in markdown
    assert manifest["articleMarkdownVersion"] == "qwq-rich-md/1"
    assert manifest["articleAssetManifest"]["articleMarkdownVersion"] == "qwq-rich-md/1"
    assert manifest["articleRenderProfile"]["template"] == "journal"
    assert manifest["articleRenderProfile"]["fontPreset"] == "clean"
    assert manifest["articleAssetManifest"]["documentSha256"] == manifest["articleMarkdownDigest"]
    assert manifest["articleAssetManifest"]["assetManifestSha256"].startswith("sha256:")
    assert manifest["articleAssetManifest"]["documentVersionSha256"].startswith("sha256:")


def test_article_markdown_asset_refs_are_declared_in_manifest():
    markdown, manifest = _build_fixture()

    markdown_asset_ids = set(re.findall(r"asset://([A-Za-z0-9_\-.]+)", markdown))
    manifest_asset_ids = {
        asset["assetId"] for asset in manifest["articleAssetManifest"]["assets"]
    }

    assert markdown_asset_ids
    assert markdown_asset_ids <= manifest_asset_ids
    for asset in manifest["articleAssetManifest"]["assets"]:
        assert asset["objectKey"]
        assert asset["scope"] == "cold_start"


def test_article_markdown_keeps_cover_title_and_body_in_same_document_flow():
    markdown, manifest = _build_fixture()

    title = manifest["publishTitle"]
    title_index = markdown.index(f"# {title}")
    cover_index = markdown.index(":::figure")
    body_index = markdown.index("出发地成都")

    assert title_index < body_index < cover_index
    assert "coverImage: asset://" in markdown
