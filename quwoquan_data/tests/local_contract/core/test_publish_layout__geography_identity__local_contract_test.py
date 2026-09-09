# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-040
from pathlib import PurePosixPath

import pytest

from core.publish_layout import (
    LayoutPolicy, ObjectPlacement, PublishLayoutError, allocate_object_path,
    entity_namespace, logical_object_ref, path_component,
)


def entity(**extra):
    return {
        "entityId": "entity:park:first", "entityRef": "/entity/地点/公园/人民公园",
        "version": 1, "domain": "地点", "type": "公园", "label": "人民公园",
        "geographyMode": "administrative",
        "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/青羊区", **extra,
    }


def test_real_administrative_chain_is_not_padded():
    assert entity_namespace(entity()) == PurePosixPath("entities/地点/中国/四川省/成都市/青羊区/公园")
    assert entity_namespace(entity(geoTagRef="Topic/地理/行政区/中国/北京市/昌平区")) == PurePosixPath("entities/地点/中国/北京市/昌平区/公园")
    assert entity_namespace(entity(geoTagRef="Topic/地理/行政区/中国/辽宁省/大连市")) == PurePosixPath("entities/地点/中国/辽宁省/大连市/公园")
    assert logical_object_ref(entity(), "entities") == "地点/公园/人民公园"


def test_non_geographic_domain_has_no_fabricated_region():
    document = entity(domain="作品", type="书籍", geographyMode="none")
    document.pop("geoTagRef")
    assert entity_namespace(document) == PurePosixPath("entities/作品/书籍")
    with pytest.raises(PublishLayoutError, match="GEOGRAPHY"):
        entity_namespace(entity(geoTagRef=""))
    with pytest.raises(PublishLayoutError, match="GEOGRAPHY"):
        entity_namespace(entity(geographyMode="none"))


def test_same_name_stays_in_partition_even_when_full():
    prefix = str(entity_namespace(entity()))
    rows = [ObjectPlacement(f"{prefix}/p0003/人民公园/4", "older", 1, "old", 500)]
    result = allocate_object_path(entity(), "entities", rows, LayoutPolicy(1, 100, 400), logical_bytes=40)
    assert result == f"{prefix}/p0003/人民公园/5"


def test_new_name_uses_capacity_but_never_moves_existing_group():
    prefix = str(entity_namespace(entity()))
    rows = [ObjectPlacement(f"{prefix}/p0001/已有/1", "older", 1, "old", 100)]
    assert allocate_object_path(entity(), "entities", rows, LayoutPolicy(2, 100, 400), logical_bytes=1) == f"{prefix}/p0002/人民公园/1"


def test_replay_keeps_path_and_cross_district_names_are_independent():
    document = entity()
    old = "entities/地点/中国/四川省/成都市/青羊区/公园/p0008/人民公园/7"
    row = ObjectPlacement(old, document["entityId"], 1, logical_object_ref(document, "entities"), 10)
    assert allocate_object_path(document, "entities", [row], LayoutPolicy(256, 1000, 4000)) == old
    other = entity(entityId="entity:park:second", entityRef="/entity/地点/公园/另一人民公园", geoTagRef="Topic/地理/行政区/中国/四川省/成都市/武侯区")
    assert allocate_object_path(other, "entities", [row], LayoutPolicy(256, 1000, 4000)).endswith("武侯区/公园/p0001/人民公园/1")


def test_names_reject_escape_and_normalize_unicode():
    assert path_component("  Cafe\u0301  ") == "Café"
    for name in ("../公园", "a/b", "a\\b", ".", "..", "a\x00", " "):
        with pytest.raises(PublishLayoutError):
            path_component(name)


def test_case_collision_and_split_group_are_not_silently_accepted():
    document = entity(label="Park")
    prefix = str(entity_namespace(document))
    with pytest.raises(PublishLayoutError, match="NAME_COLLISION"):
        allocate_object_path(document, "entities", [ObjectPlacement(f"{prefix}/p0001/park/1", "other", 1, "other", 1)], LayoutPolicy(256, 1000, 4000))
    rows = [ObjectPlacement(f"{prefix}/p000{n}/Park/1", f"other{n}", 1, f"other{n}", 1) for n in (1, 2)]
    with pytest.raises(PublishLayoutError, match="GROUP_SPLIT"):
        allocate_object_path(document, "entities", rows, LayoutPolicy(256, 1000, 4000))


def test_logical_ref_cannot_be_reassigned_to_a_different_identity():
    document = entity()
    prefix = str(entity_namespace(document))
    row = ObjectPlacement(f"{prefix}/p0001/人民公园/1", "another-identity", 1, logical_object_ref(document, "entities"), 10)
    with pytest.raises(PublishLayoutError, match="IDENTITY_CONFLICT"):
        allocate_object_path(document, "entities", [row], LayoutPolicy(256, 1000, 4000))


def test_post_layout_does_not_gain_a_region_axis():
    document = {"contentId": "post:1", "objectRef": "article/导览/旧标题/1", "version": 1, "contentType": "article", "publishAngle": "导览", "publishTitle": "百山祖速览"}
    assert allocate_object_path(document, "posts", [], LayoutPolicy(256, 1000, 4000)) == "posts/article/导览/p0001/百山祖速览/1"
    assert logical_object_ref(document, "posts") == "article/导览/旧标题/1"
