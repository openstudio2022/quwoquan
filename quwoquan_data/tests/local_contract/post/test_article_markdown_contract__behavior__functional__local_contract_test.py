"""Article Markdown package 格式契约测试（与交付物格式约定对齐，不依赖具体 release）。

构造一个 agent 创作正文的 article 包（front-matter + 封面 figure + 正文 + 资产清单），
断言 qwq-rich-md/1 版本标记、asset:// 引用在 manifest 声明、封面/标题/正文同文档流。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import re

import yaml

from core.article_package import (  # noqa: E402
    MARKDOWN_VERSION,
    build_markdown_frontmatter,
    compute_document_sha256,
    post_asset_id,
)

TITLE = "峨眉山周末·自驾两日的真实体验"


def _build_fixture() -> tuple[str, dict]:
    object_key = "media/objects/sha256/ab/cd/" + ("abcd" * 16) + ".jpg"
    asset_id = post_asset_id(
        entity_name="峨眉山",
        role="cover",
        execution_sequence=42,
        ref="峨眉山周末_自驾",
    )
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
    manifest = {
        "topicId": "峨眉山周末_自驾",
        "publishTitle": TITLE,
        "articleMarkdownVersion": MARKDOWN_VERSION,
        "assets": assets,
        "articleRenderProfile": render_profile,
        "generator": "agent",
    }
    return body, manifest


def test_article_markdown_package_uses_qwq_rich_markdown_triple():
    markdown, manifest = _build_fixture()

    assert "articleMarkdownVersion: qwq-rich-md/1" in markdown
    assert manifest["articleMarkdownVersion"] == "qwq-rich-md/1"
    assert manifest["assets"][0]["assetId"]
    assert manifest["articleRenderProfile"]["template"] == "journal"
    assert manifest["articleRenderProfile"]["fontPreset"] == "clean"
    assert manifest["assets"][0]["caption"] == "峨眉山"
    assert manifest["assets"][0]["imageLayout"] == "fullWidth"


def test_article_markdown_asset_refs_are_declared_in_manifest():
    markdown, manifest = _build_fixture()

    # asset id 形如「实体_角色_批次_hash」，实体名为中文，正则用 \w（默认匹配 Unicode）。
    markdown_asset_ids = set(re.findall(r"asset://([\w\-.]+)", markdown))
    manifest_asset_ids = {asset["assetId"] for asset in manifest["assets"]}

    assert markdown_asset_ids
    assert markdown_asset_ids <= manifest_asset_ids
    for asset in manifest["assets"]:
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


def test_frontmatter_builder_quotes_titles_with_embedded_quotes():
    title = '"安逸四川 雅安之夜"启幕雅安文旅消费季'
    block = build_markdown_frontmatter(
        {
            "title": title,
            "template": "journal",
            "articleMarkdownVersion": MARKDOWN_VERSION,
        }
    )

    parsed = yaml.safe_load(block.split("\n---\n", 1)[0][4:])

    assert parsed["title"] == title
    assert "articleMarkdownVersion: qwq-rich-md/1" in block


def test_document_digest_does_not_abort_on_legacy_malformed_frontmatter():
    markdown = (
        "---\n"
        'title: "安逸四川 雅安之夜"启幕雅安文旅消费季\n'
        "template: journal\n"
        "---\n\n"
        "# 碧峰峡\n\n正文。\n"
    )

    digest = compute_document_sha256(markdown)

    assert digest.startswith("sha256:")
