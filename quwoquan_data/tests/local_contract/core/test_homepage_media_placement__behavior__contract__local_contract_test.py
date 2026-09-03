from core.asset_placement import place_homepage_assets_in_markdown
from core.page_media import is_image_dimension_token, subject_keys_conflict


def test_dimension_tokens_and_putuoshan_subject_alias_are_normalized() -> None:
    assert is_image_dimension_token("291x291px")
    assert is_image_dimension_token("291×291px")
    assert is_image_dimension_token("x300px")
    assert subject_keys_conflict(
        "测试实体甲南海观音",
        "南海观音像",
        entity_name="测试实体甲",
    )


def test_group_members_and_unanchored_images_only_enter_related_gallery() -> None:
    body = """---
coverImage: asset://cover_arch
---
# 测试实体甲

概况正文。

## 地理生态

地理正文。

:::figure id="gallery_group" layout="fullWidth" caption="图集图"
asset://gallery_01
:::
"""
    # role 是 `1.download` 冻结的处置（DEC-029）；本函数只按它落版面。
    # inline_model 在冻结阶段已被定为内嵌，unanchored 冻结为 related——
    # 后者的 placementType 仍写 inline，用来证明版面提示不能翻转冻结处置。
    assets = [
        {"assetId": "cover_arch", "role": "cover", "caption": "测试实体甲海岸牌坊"},
        {
            "assetId": "inline_model",
            "role": "inline",
            "caption": "测试实体甲全貌模型",
            "placementType": "inline",
        },
        {
            "assetId": "gallery_01",
            "role": "related",
            "caption": "测试实体甲石刻",
            "placementType": "groupMember",
        },
        {
            "assetId": "unanchored",
            "role": "related",
            "caption": "无结构锚点图片",
            "placementType": "inline",
        },
    ]
    placements = [
        {
            "assetId": "inline_model",
            "placementType": "inline",
            "sectionSlug": "地理生态",
        },
        {
            "assetId": "gallery_01",
            "placementType": "groupMember",
            "sectionSlug": "图集",
            "groupId": "gal-001",
        },
        {
            "assetId": "unanchored",
            "placementType": "inline",
            "sectionSlug": "不存在章节",
        },
    ]

    result = place_homepage_assets_in_markdown(body, assets, placements=placements)

    assert "asset://cover_arch" in result.split("---\n", 2)[1]
    assert result.count("asset://cover_arch") == 1
    assert result.count("asset://inline_model") == 1
    assert result.count("gallery_01") == 1
    assert result.count("unanchored") == 1
    assert result.count("## 相关图片") == 1
    gallery_line = next(line for line in result.splitlines() if line.startswith(":::gallery"))
    assert "gallery_01" in gallery_line
    assert "unanchored" in gallery_line
    assert "inline_model" not in gallery_line
    # 渲染不裁决：冻结处置在函数返回后必须逐字不变。这里点名断言而不是只看版面，
    # 因为一旦函数又开始依据正文改写 role，版面可能仍然「看起来对」，
    # 而第二个决策点已经悄悄回来了。
    assert [asset["role"] for asset in assets] == [
        "cover",
        "inline",
        "related",
        "related",
    ]


def test_empty_source_gallery_heading_is_removed_after_related_gallery_is_materialized() -> None:
    body = """# 测试实体甲

## 寺院机构

寺院正文。

### 图集

### 文化交流

文化正文。
"""
    assets = [
        {"assetId": "cover", "role": "cover", "caption": "测试实体甲海岸牌坊"},
        {
            "assetId": "gallery",
            "role": "related",
            "caption": "测试实体甲石刻",
            "placementType": "groupMember",
        },
    ]

    result = place_homepage_assets_in_markdown(
        body,
        assets,
        placements=[{"assetId": "gallery", "placementType": "groupMember", "groupId": "gal-001"}],
    )

    assert "### 图集" not in result
    assert "### 文化交流" in result
    assert result.count("## 相关图片") == 1
