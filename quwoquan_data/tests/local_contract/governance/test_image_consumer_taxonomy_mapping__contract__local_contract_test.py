"""图片消费者入口只映射既有题材，不复制地貌词，也不把器材/参数当兴趣。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
TAXONOMY = DATA_ROOT / "control_plane/governance/taxonomy"

CHIP = "creator_chip"
CHIP_CONSUMERS = ["recall", "scorer", "intersection", "search_facet"]

# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046
CONSUMER_QUERIES = {
    "雪山日照金山": ("Topic/自然风光/雪山", "Topic/自然风光/日照金山"),
    "燕鸥求偶": ("Entity/生物/野生动物/鸟类", "Topic/宠物动物/动物行为/求偶"),
    "古镇夜景": ("Topic/历史文化/古镇文化", "Topic/人文社科/城市夜景"),
    "清爽的海边": ("Topic/自然风光/海岸海岛", "Format/视觉风格/视觉调性/高调明亮"),
    "植物细节": ("Entity/生物/植物/花卉", "Topic/家居生活/园艺植物"),
}

FORBIDDEN_LEAVES = (
    "Topic/人文社科/城市景观",
    "Topic/宠物动物/动物行为/觅食",
)

NEW_LEAVES = (
    "Topic/自然风光/日照金山",
    "Topic/自然风光/河流",
    "Topic/自然风光/瀑布",
    "Topic/自然风光/海岸海岛",
    "Topic/自然风光/草原",
    "Topic/自然风光/荒漠",
    "Topic/自然风光/湿地滩涂",
    "Topic/人文社科/城市天际线",
    "Topic/人文社科/城市夜景",
    "Topic/宠物动物/动物行为",
    "Topic/宠物动物/动物行为/取食",
    "Topic/宠物动物/动物行为/求偶",
    "Topic/宠物动物/动物行为/筑巢",
    "Topic/宠物动物/动物行为/育雏",
)


def _definition(ref: str) -> dict:
    path = TAXONOMY / ref / "_definition.json"
    assert path.is_file(), ref
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("ref", NEW_LEAVES)
def test_new_image_subject_tags_declare_real_collection_and_consumption(ref: str) -> None:
    data = _definition(ref)
    assert data["axisRole"] == "topic"
    assert data["collectionChannel"] == CHIP
    assert data["consumedBy"] == CHIP_CONSUMERS


@pytest.mark.parametrize("ref", FORBIDDEN_LEAVES)
def test_consumer_catalog_cancels_duplicate_parent_and_food_alias(ref: str) -> None:
    assert not (TAXONOMY / ref / "_definition.json").exists()


def test_foraging_alias_stays_on_food_tour_not_animal_behavior() -> None:
    food = _definition("Topic/旅行/旅行主题/美食之旅")
    assert "觅食" in food.get("aliases", [])
    assert not (TAXONOMY / "Topic/宠物动物/动物行为/觅食" / "_definition.json").exists()


@pytest.mark.parametrize("query,refs", CONSUMER_QUERIES.items())
def test_consumer_queries_resolve_to_subject_not_camera_metadata(query: str, refs: tuple[str, ...]) -> None:
    for ref in refs:
        data = _definition(ref)
        assert data["label"]
        assert "光圈" not in data.get("description", "")
        assert "ISO" not in data.get("description", "")
        assert "三分法" not in data.get("description", "")
    if query == "雪山日照金山":
        assert "城市" in _definition("Topic/自然风光/日照金山")["description"]
    if query == "燕鸥求偶":
        assert "拟人" in _definition("Topic/宠物动物/动物行为/求偶")["description"]
