"""image collection 归因的「缺席」与「在场但无效」必须报成两件事。

可发布归因只由受审计采集铸造。检索阶段手写的 collection 根本没有归因，这是
缺席；若把它塌陷成空对象，schema 会报 15 个 required 字段缺失，读者会以为
补字段就能修，从而错过真正该走的 acquisition receipt 路径。

可直接运行：python3 quwoquan_data/tests/local_contract/source/test_image_collection_attribution__absence_versus_invalid__contract__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import pytest  # noqa: E402
from content.source.handler_fetch_images import (  # noqa: E402
    _planned_attribution_fragment,
)
from content.source.handler_fetch_media import (  # noqa: E402
    EntityMediaClosureInput,
    _materialize_image_collections,
)


def _closure_input(image: dict[str, object]) -> EntityMediaClosureInput:
    return EntityMediaClosureInput(
        execution_id="20260817--travel-image-attribution--china-sichuan--pilot-001",
        entity_id="峨眉山",
        entity_index=1,
        entity_count=1,
        object_dir=Path("/nonexistent/object"),
        target_ref="地点/景区/峨眉山",
        sources=(),
        image_specs=(),
        pending_images=(image,),
        provider_asset_counts=(),
        professional_exclusions=(),
        existing_image_source_dirs=frozenset(),
        written_source_dirs=frozenset(),
        written_rejected_source_dirs=frozenset(),
        selected_lanes=frozenset({"image"}),
        image_rights_issues=(),
        image_quality_issues=(),
        rejected_by_category={},
        image_lane_selected=True,
        homepage_media_selected=False,
        required_image_work_images=1,
        required_homepage_media=0,
        required_images=1,
        planned_homepage_source_images=0,
        kept_source_homepage_images=0,
    )


def _planned_image(**overrides: object) -> dict[str, object]:
    image = {
        "researchLane": "image",
        "sourceCollectionId": "commons_file:峨眉山:emeishan-54534486385",
        "url": "https://upload.wikimedia.org/wikipedia/commons/b/b8/Emeishan.jpg",
        "creator": "Xiquinho Silva",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Emeishan.jpg",
        "platform": "Wikimedia Commons",
    }
    image.update(overrides)
    return image


def test_planned_attribution_absence_never_becomes_an_empty_object():
    """检索计划没铸归因时，键必须不在场，而不是落一个空对象。"""

    assert _planned_attribution_fragment(_planned_image()) == {}
    assert _planned_attribution_fragment(_planned_image(sourceAttribution={})) == {}
    assert _planned_attribution_fragment(_planned_image(sourceAttribution=None)) == {}
    minted = {"isOriginal": False, "platform": "Wikimedia Commons"}
    assert _planned_attribution_fragment(
        _planned_image(sourceAttribution=minted)
    ) == {"sourceAttribution": minted}


def test_absent_collection_attribution_names_the_acquisition_gap():
    """缺席要指向受审计采集，不能报成 schema 字段缺失。"""

    with pytest.raises(ValueError) as absent:
        _materialize_image_collections(_closure_input(_planned_image()))
    message = str(absent.value)
    assert "缺 sourceAttribution" in message
    assert "commons_file:峨眉山:emeishan-54534486385" in message
    assert "acquisition" in message
    assert "required" not in message


def test_invalid_collection_attribution_still_reports_schema_violation():
    """在场但不合契约仍报 schema violation，与缺席区分开。"""

    with pytest.raises(ValueError) as invalid:
        _materialize_image_collections(
            _closure_input(_planned_image(sourceAttribution={"platform": "Commons"}))
        )
    message = str(invalid.value)
    assert "schema violation" in message
    assert "缺 sourceAttribution" not in message


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
