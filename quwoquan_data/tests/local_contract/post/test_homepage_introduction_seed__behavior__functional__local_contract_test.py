from pathlib import Path

from content.homepage.homepage_introduction import homepage_introduction_seed_from_triplet
from core.io import write_json


def test_homepage_triplet_maps_to_introduction_seed(tmp_path: Path) -> None:
    entity_dir = tmp_path / "entities" / "地点" / "景区" / "西湖景区"
    entity_dir.mkdir(parents=True)
    (entity_dir / "page.md").write_text(
        "\n".join(
            [
                "---",
                "coverImage: asset://west_lake_cover",
                "---",
                "# 西湖景区",
                "西湖景区是杭州核心游览区，承接散步、摄影、历史节点和城市公共生活。",
                "## 核心信息",
                "- 所在城市：杭州",
                "- 推荐方式：步行、骑行、分段游览",
                ':::figure id="fig_01" layout="fullWidth" caption="苏堤春晓"',
                "asset://west_lake_inline",
                ":::",
                "## 时间线",
                "- 唐宋以来：湖堤治理与文人书写共同塑造西湖。",
                "- 今天：内容、讨论和兴趣圈持续沉淀。",
                "## 相关地点和事物",
                "断桥残雪、曲院风荷等共同构成杭州旅行关联网络。",
                "## 相关图片",
                ':::gallery ids="west_lake_related" layout="grid"',
                ":::",
            ]
        ),
        encoding="utf-8",
    )
    write_json(
        entity_dir / "_entity.json",
        {
            "homepageId": "homepage_sight_west_lake",
            "label": "西湖景区",
            "domain": "地点",
            "type": "景区",
            "sourceRefs": ["source/wiki/west_lake"],
            "primarySource": {
                "sourceKind": "wikipedia",
                "sourceUrl": "https://zh.wikipedia.org/wiki/西湖",
                "title": "西湖",
                "fetchedAt": "2026-07-11T00:00:00Z",
                "snapshotHash": "sha256:" + ("a" * 64),
                "policyRevision": "encyclopedia-primary",
                "sourceUseMode": "licensed_adaptation",
            },
            "sourceUrls": ["https://zh.wikipedia.org/wiki/西湖"],
        },
    )
    write_json(
        entity_dir / "manifest.json",
        {
            "coverUrl": "https://example.invalid/west-lake.jpg",
            "assets": [
                {
                    "assetId": "west_lake_cover",
                    "url": "https://example.invalid/west-lake.jpg",
                    "caption": "西湖湖面",
                    "sourceRef": "manifest.assets[0]",
                    "role": "cover",
                },
                {
                    "assetId": "west_lake_inline",
                    "url": "https://example.invalid/west-lake-inline.jpg",
                    "caption": "苏堤春晓",
                    "sourceRef": "manifest.assets[1]",
                    "role": "inline",
                },
                {
                    "assetId": "west_lake_related",
                    "url": "https://example.invalid/west-lake-related.jpg",
                    "caption": "曲院风荷",
                    "sourceRef": "manifest.assets[2]",
                    "role": "related",
                }
            ],
            "relatedObjects": [
                {
                    "circleId": "west_lake_circle_1",
                    "name": "西湖散步兴趣群",
                    "memberCount": 146,
                }
            ],
            "updatedAt": "2026-06-12T00:00:00Z",
        },
    )

    seed = homepage_introduction_seed_from_triplet(entity_dir)

    assert seed["homepageId"] == "homepage_sight_west_lake"
    assert seed["displayName"] == "西湖景区"
    assert seed["summary"].startswith("西湖景区是杭州核心游览区")
    assert seed["primarySource"]["sourceKind"] == "wikipedia"
    assert seed["sourceUrls"] == ["https://zh.wikipedia.org/wiki/西湖"]
    assert "sourceRefs" not in seed
    kinds = {section["kind"] for section in seed["sections"]}
    assert {"overview", "keyFacts", "timeline", "relatedObjects"} <= kinds
    timeline = next(section for section in seed["sections"] if section["kind"] == "timeline")
    assert len(timeline["timelineItems"]) == 2
    bound_ids = [asset["assetId"] for section in seed["sections"] for asset in section["assets"]]
    assert "west_lake_cover" not in bound_ids
    assert bound_ids.count("west_lake_inline") == 1
    assert bound_ids.count("west_lake_related") == 1
    related = next(section for section in seed["sections"] if section["kind"] == "relatedImages")
    assert related["assets"][0]["role"] == "related"
    assert seed["relatedObjects"][0]["name"] == "西湖散步兴趣群"
