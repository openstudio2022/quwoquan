"""文章发现查询复用现有标签，不扩地貌、营造或体裁目录。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
TAXONOMY = DATA_ROOT / "control_plane/governance/taxonomy"
FORMAT_ANGLE = TAXONOMY / "Format" / "内容角度"
ARCHITECTURE = TAXONOMY / "Topic" / "历史文化" / "建筑艺术"

# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-048.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-048.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-048.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-048.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-048.t5
CONSUMED = ["recall", "scorer", "intersection", "search_facet"]

SHARED_SUBJECTS = (
    "Topic/自然风光/雪山",
    "Topic/自然风光/日照金山",
    "Topic/宠物动物/动物行为/求偶",
    "Entity/生物/野生动物/鸟类",
    "Topic/旅行/旅行主题/古镇古村",
    "Topic/旅行/出行方式/公共交通",
    "Topic/旅行/旅行时长/周末短途",
    "Topic/历史文化/建筑艺术",
    "Topic/旅行/同行人/携长辈",
    "Format/内容角度/攻略/银发专享",
    "Topic/住宿",
    "Format/内容角度/攻略/住宿攻略",
    "Format/内容角度/测评/横向对比",
    "Format/内容角度/科普/知识科普",
    "Format/内容角度/攻略/行前指南",
)

CONSUMER_QUERIES = {
    "南迦巴瓦日照金山": ("Topic/自然风光/雪山", "Topic/自然风光/日照金山", "Format/内容角度/科普/知识科普"),
    "燕鸥求偶": ("Entity/生物/野生动物/鸟类", "Topic/宠物动物/动物行为/求偶"),
    "周末古镇公共交通": (
        "Topic/旅行/旅行主题/古镇古村",
        "Topic/旅行/出行方式/公共交通",
        "Topic/旅行/旅行时长/周末短途",
        "Format/内容角度/攻略/行前指南",
    ),
    "陈家祠有什么好看": ("Topic/历史文化/建筑艺术", "Format/内容角度/科普/知识科普"),
    "带长辈游园": ("Topic/旅行/同行人/携长辈", "Format/内容角度/攻略/银发专享"),
    "住宿比较": ("Topic/住宿", "Format/内容角度/攻略/住宿攻略", "Format/内容角度/测评/横向对比"),
}

FORBIDDEN_LEAVES = (
    "Topic/地理/地形地貌/冰川地貌",
    "Topic/地理/地形地貌/喀斯特地貌",
    "Topic/地理/地形地貌/丹霞地貌",
    "Topic/地理/地形地貌/峡谷地貌",
    "Topic/地理/地形地貌/火山地貌",
    "Topic/地理/地形地貌/海岸地貌",
    "Topic/地理/地形地貌/风沙地貌",
    "Topic/地理/地形地貌/河流地貌",
    "Topic/历史文化/建筑艺术/古桥营造",
    "Topic/历史文化/建筑艺术/木构营造",
    "Topic/历史文化/建筑艺术/园林营造",
    "Topic/历史文化/建筑艺术/建筑装饰工艺",
    "Topic/历史文化/建筑艺术/民居营造",
    "Topic/历史文化/建筑艺术/建筑保护修缮",
    "Format/内容载体/文章/散文",
    "Format/内容载体/文章/随笔",
    "Format/内容载体/文章/访谈",
    "Topic/人文社科/城市景观",
)

ANGLE_PARENTS = (
    "体验",
    "叙事",
    "拔草",
    "探店",
    "攻略",
    "教程",
    "日记",
    "测评",
    "盘点",
    "种草",
    "科普",
    "经验分享",
    "观点评论",
    "资讯",
    "避雷",
)

PARENT_NOT_ONLINE_LEAF = (
    "Format/内容载体/文章",
    "Format/内容角度/攻略",
    "Topic/住宿",
)

SEAL_RESOLVABLE_PARENTS = (
    "Format/内容载体/文章",
    "Topic/历史文化/建筑艺术",
    "Topic/住宿",
)


def _definition(ref: str) -> dict:
    path = TAXONOMY / ref / "_definition.json"
    assert path.is_file(), ref
    return json.loads(path.read_text(encoding="utf-8"))


def _has_child_tags(ref: str) -> bool:
    root = TAXONOMY / ref
    return any(
        path.parent != root
        for path in root.rglob("_definition.json")
    )


@pytest.mark.parametrize("query,refs", CONSUMER_QUERIES.items())
def test_article_queries_resolve_to_existing_tags(query: str, refs: tuple[str, ...]) -> None:
    for ref in refs:
        data = _definition(ref)
        assert data["label"]
        assert "Intent" not in data.get("description", "")


@pytest.mark.parametrize("ref", FORBIDDEN_LEAVES)
def test_article_does_not_add_landform_craft_or_genre_leaves(ref: str) -> None:
    assert not (TAXONOMY / ref / "_definition.json").exists()


def test_architecture_art_stays_a_leaf_definition() -> None:
    data = _definition("Topic/历史文化/建筑艺术")
    assert data["label"] == "建筑艺术"
    assert not _has_child_tags("Topic/历史文化/建筑艺术")
    assert not (ARCHITECTURE / "古桥营造" / "_definition.json").exists()


def test_format_angle_description_does_not_hardcode_count() -> None:
    data = json.loads((FORMAT_ANGLE / "_dimension.json").read_text(encoding="utf-8"))
    assert "14个" not in data["description"]
    assert "15个" not in data["description"]
    parents = sorted(
        path.name
        for path in FORMAT_ANGLE.iterdir()
        if path.is_dir() and (path / "_definition.json").is_file()
    )
    assert parents == sorted(ANGLE_PARENTS)
    assert len(parents) == 15


@pytest.mark.parametrize("ref", SHARED_SUBJECTS)
def test_article_shared_and_reading_tags_resolve(ref: str) -> None:
    data = _definition(ref)
    assert data["label"]
    if ref.startswith("Topic/自然风光/") or ref.startswith("Topic/宠物动物/动物行为/"):
        if "consumedBy" in data:
            assert data["consumedBy"] == CONSUMED


@pytest.mark.parametrize("ref", PARENT_NOT_ONLINE_LEAF)
def test_article_parent_tags_are_seal_resolvable_not_service_leaves(ref: str) -> None:
    _definition(ref)
    assert _has_child_tags(ref)


@pytest.mark.parametrize("ref", SEAL_RESOLVABLE_PARENTS)
def test_existing_article_parent_tags_keep_definitions(ref: str) -> None:
    assert (TAXONOMY / ref / "_definition.json").is_file()
