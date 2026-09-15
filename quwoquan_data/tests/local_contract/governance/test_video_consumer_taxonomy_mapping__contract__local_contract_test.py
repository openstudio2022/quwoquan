"""视频复用已声明消费的共享题材叶子，不另建入口表或制作参数分类。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
TAXONOMY = DATA_ROOT / "control_plane/governance/taxonomy"
TOPIC_ROOT = TAXONOMY / "Topic"

# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-047.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-047.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-047.t3
CONSUMED = ["recall", "scorer", "intersection", "search_facet"]

SHARED_SUBJECTS = (
    "Topic/自然风光/日照金山",
    "Topic/自然风光/河流",
    "Topic/自然风光/瀑布",
    "Topic/自然风光/海岸海岛",
    "Topic/自然风光/草原",
    "Topic/自然风光/荒漠",
    "Topic/自然风光/湿地滩涂",
    "Topic/人文社科/城市天际线",
    "Topic/人文社科/城市夜景",
    "Topic/宠物动物/动物行为/取食",
    "Topic/宠物动物/动物行为/求偶",
    "Topic/宠物动物/动物行为/筑巢",
    "Topic/宠物动物/动物行为/育雏",
    "Topic/摄影/摄影教程",
)

CONSUMER_QUERIES = {
    "日照金山": ("Topic/自然风光/日照金山",),
    "燕鸥求偶": ("Topic/宠物动物/动物行为/求偶",),
    "古镇夜景": ("Topic/人文社科/城市夜景",),
    "海边旅行": ("Topic/自然风光/海岸海岛",),
    "学摄影": ("Topic/摄影/摄影教程",),
}

FORBIDDEN_LEAVES = (
    "Topic/人文社科/城市景观",
    "Topic/宠物动物/动物行为/觅食",
    "Topic/宠物动物/动物行为/求偶展示",
    "Format/内容角度/观赏",
    "Format/内容角度/风景欣赏",
    "Topic/自然风光/冰川",
    "Entity/生物/野生动物/昆虫",
    "Entity/生物/野生动物/两栖动物",
    "Entity/生物/野生动物/鱼类",
)

CAMERA_TERMS = ("光圈", "快门", "ISO", "三分法", "焦段")
UNDECLARED_FORMAT_HINTS = (
    "Format/内容角度/科普/知识科普",
    "Format/内容角度/攻略/行前指南",
    "Format/内容角度/攻略/路线推荐",
    "Format/内容角度/教程/实操步骤",
    "Format/内容角度/测评/横向对比",
)


def _definition(ref: str) -> dict:
    path = TAXONOMY / ref / "_definition.json"
    assert path.is_file(), ref
    return json.loads(path.read_text(encoding="utf-8"))


TOPIC_DIRECTORY_ROOTS = {"场景", "时间", "地理"}


def test_topic_first_level_dirs_map_to_definitions_or_directory_roots() -> None:
    actual = sorted(path.name for path in TOPIC_ROOT.iterdir() if path.is_dir())
    assert len(actual) == 39
    defined = [
        name
        for name in actual
        if (TOPIC_ROOT / name / "_definition.json").is_file()
    ]
    roots = [
        name
        for name in actual
        if not (TOPIC_ROOT / name / "_definition.json").is_file()
    ]
    assert len(defined) == 36
    assert set(roots) == TOPIC_DIRECTORY_ROOTS
    for name in defined:
        assert _definition(f"Topic/{name}")["label"] == name


@pytest.mark.parametrize("ref", SHARED_SUBJECTS)
def test_shared_subject_leaves_declare_consumption(ref: str) -> None:
    data = _definition(ref)
    assert data["consumedBy"] == CONSUMED
    for term in CAMERA_TERMS:
        assert term not in data.get("description", "")


@pytest.mark.parametrize("ref", UNDECLARED_FORMAT_HINTS)
def test_undeclared_format_angles_are_not_contract_entries(ref: str) -> None:
    data = _definition(ref)
    assert "consumedBy" not in data
    assert "collectionChannel" not in data


@pytest.mark.parametrize("ref", FORBIDDEN_LEAVES)
def test_video_does_not_create_duplicate_or_production_taxonomy(ref: str) -> None:
    assert not (TAXONOMY / ref / "_definition.json").exists()


EXISTING_BIO_TYPES = (
    "Entity/生物/野生动物/鸟类",
    "Entity/生物/野生动物/哺乳动物",
    "Entity/生物/野生动物/海洋生物",
    "Entity/生物/野生动物/爬行动物",
)
TOPIC_INDEX = {
    "看世界及共享题材": ("自然风光", "历史文化", "旅行", "人文社科", "宠物动物", "非遗民俗"),
    "生活题材": ("美食餐饮", "住宿", "时尚穿搭", "美妆护肤", "健康养生", "运动", "家居生活", "亲子育儿"),
    "学习与选择": ("科技", "数码", "汽车文化", "教育成长", "职场效率", "艺术创作", "摄影", "购物消费", "金融理财"),
    "娱乐与关系": ("影视娱乐", "游戏电竞", "二次元", "情感关系"),
    "社会文化": ("三农生活", "宗教信仰", "命理玄学", "法律政务", "公益社会", "军事国防", "国际视野"),
    "跨入口维度": ("场景", "事件", "话题", "时间", "地理"),
}


def test_snow_mountain_already_covers_glacier_wording() -> None:
    assert "冰川" in _definition("Topic/自然风光/雪山")["description"]


def test_thirty_nine_topic_index_reuses_existing_paths() -> None:
    indexed = [name for names in TOPIC_INDEX.values() for name in names]
    assert len(indexed) == 39
    actual = sorted(path.name for path in TOPIC_ROOT.iterdir() if path.is_dir())
    assert sorted(indexed) == actual
    for name in indexed:
        if name in TOPIC_DIRECTORY_ROOTS:
            assert not (TOPIC_ROOT / name / "_definition.json").is_file()
            continue
        assert _definition(f"Topic/{name}")["label"] == name


def test_existing_bio_types_are_reused_without_new_encyclopedia() -> None:
    for ref in EXISTING_BIO_TYPES:
        assert _definition(ref)["label"]
    assert not (TAXONOMY / "Audience/用户/人口画像").exists()


def test_video_script_tag_refs_have_no_five_item_import_cap() -> None:
    schema = json.loads(
        (DATA_ROOT / "schema/content/video_script.schema.json").read_text(encoding="utf-8")
    )
    tag_refs = schema["properties"]["tagRefs"]
    assert "maxItems" not in tag_refs
    assert tag_refs["type"] == "array"


@pytest.mark.parametrize("query,refs", CONSUMER_QUERIES.items())
def test_video_queries_resolve_to_declared_subject_leaves(query: str, refs: tuple[str, ...]) -> None:
    for ref in refs:
        data = _definition(ref)
        assert data["consumedBy"] == CONSUMED
        for term in CAMERA_TERMS:
            assert term not in data.get("description", "")
    if query == "日照金山":
        assert "暖色" in _definition("Topic/自然风光/日照金山")["description"]
    if query == "燕鸥求偶":
        assert "拟人" in _definition("Topic/宠物动物/动物行为/求偶")["description"]
    if query == "古镇夜景":
        assert "城市" in _definition("Topic/人文社科/城市夜景")["description"]
