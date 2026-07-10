from pathlib import Path

from build.homepage import homepage_introduction_seed_from_triplet
from _common.io import write_json


def test_homepage_triplet_maps_to_introduction_seed(tmp_path: Path) -> None:
    entity_dir = tmp_path / "entities" / "地点" / "景区" / "西湖景区"
    entity_dir.mkdir(parents=True)
    (entity_dir / "page.md").write_text(
        "\n".join(
            [
                "# 西湖景区",
                "西湖景区是杭州核心游览区，承接散步、摄影、历史节点和城市公共生活。",
                "## 核心信息",
                "- 所在城市：杭州",
                "- 推荐方式：步行、骑行、分段游览",
                "## 时间线",
                "- 唐宋以来：湖堤治理与文人书写共同塑造西湖。",
                "- 今天：内容、讨论和兴趣圈持续沉淀。",
                "## 相关地点和事物",
                "断桥残雪、曲院风荷等共同构成杭州旅行关联网络。",
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
    assert seed["sourceRefs"]
    kinds = {section["kind"] for section in seed["sections"]}
    assert {"overview", "keyFacts", "timeline", "relatedObjects"} <= kinds
    timeline = next(section for section in seed["sections"] if section["kind"] == "timeline")
    assert len(timeline["timelineItems"]) == 2
    assert seed["relatedObjects"][0]["name"] == "西湖散步兴趣群"
