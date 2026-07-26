"""One execution work package uses publish-isomorphic object paths."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.entity_object import execution_entity_type_conflicts, collect_execution_entity_objects  # noqa: E402
from core.io import write_json  # noqa: E402
from core.paths import (  # noqa: E402
    OBJECT_STAGES,
    STAGE_COMPOSE,
    STAGE_DOWNLOAD,
    STAGE_REVIEW,
    execution_entity_object_dir,
    execution_entity_page_input_path,
    execution_entity_stage_dir,
    execution_runtime_state_path,
    execution_post_object_dir,
    execution_post_stage_dir,
    execution_root,
    execution_shared_dir,
    execution_source_unit_dir,
    execution_command_packet_path,
    publish_data,
    relative_execution_ref,
)

EXECUTION_ID = "20260711--travel-homepage-object-paths--test-region-b--pilot-001"


def test_entity_and_post_paths_are_publish_isomorphic():
    entity = execution_entity_object_dir(EXECUTION_ID, "地点", "景区", "测试实体丙")
    post = execution_post_object_dir(EXECUTION_ID, "article", "攻略", "测试实体丙两天", 2)
    root = execution_root(EXECUTION_ID)
    assert entity.relative_to(root).as_posix() == "entities/地点/景区/测试实体丙"
    assert post.relative_to(root).as_posix() == "posts/article/攻略/测试实体丙两天/2"
    published = publish_data().entity_dir("地点", "景区", "测试实体丙")
    assert published.relative_to(published.parents[3]).as_posix() == "entities/地点/景区/测试实体丙"


def test_object_stage_and_source_paths_are_stable():
    assert OBJECT_STAGES == ("1.download", "2.quality", "3.compose", "4.draft", "5.review")
    root = execution_root(EXECUTION_ID)
    assert execution_entity_stage_dir(
        EXECUTION_ID, "地点", "景区", "测试实体丙", STAGE_DOWNLOAD
    ).name == "1.download"
    assert execution_entity_stage_dir(
        EXECUTION_ID, "地点", "景区", "测试实体丙", STAGE_COMPOSE
    ).name == "3.compose"
    assert execution_post_stage_dir(
        EXECUTION_ID, "article", "攻略", "测试实体丙两天", 1, STAGE_REVIEW
    ).name == "5.review"
    assert execution_entity_page_input_path(
        EXECUTION_ID, "地点", "景区", "测试实体丙"
    ).relative_to(root).as_posix() == "entities/地点/景区/测试实体丙/3.compose/entity_page_input.json"
    source = execution_source_unit_dir(EXECUTION_ID, "su_fixture") / "source.md"
    assert relative_execution_ref(source, EXECUTION_ID) == "sources/su_fixture/source.md"


def test_shared_runtime_state_is_not_a_root_level_batch_manifest():
    root = execution_root(EXECUTION_ID)
    assert execution_runtime_state_path(EXECUTION_ID) == root / "_shared/runtime_state.json"
    assert execution_shared_dir(EXECUTION_ID) == root / "_shared"
    packet = execution_command_packet_path(EXECUTION_ID, "build_homepage")
    assert packet.relative_to(root).as_posix() == "_shared/command_packets/build_homepage.json"


def test_single_execution_release_id_is_the_validated_execution_id():
    """per-execution release 已退役；发布身份即 execution 身份（aggregate 唯一建 release）。"""
    from content.execution.identity import validate_execution_id

    assert validate_execution_id(EXECUTION_ID) == EXECUTION_ID


def test_execution_collects_only_approved_entities():
    approved = execution_entity_object_dir(EXECUTION_ID, "地点", "景区", "都江堰")
    rejected = execution_entity_object_dir(EXECUTION_ID, "地点", "景区", "青城山")
    for entity, decision in ((approved, "approved"), (rejected, "rejected")):
        entity.mkdir(parents=True, exist_ok=True)
        (entity / "page.md").write_text(f"# {entity.name}\n", encoding="utf-8")
        write_json(entity / "_entity.json", {"label": entity.name, "domain": "地点", "type": "景区"})
        write_json(entity / "5.review/review.json", {"decision": decision})
    refs = {row["entityRel"] for row in collect_execution_entity_objects(EXECUTION_ID, approved_only=True)}
    assert "entities/地点/景区/都江堰" in refs
    assert "entities/地点/景区/青城山" not in refs


def test_execution_blocks_dual_scenic_location_trees():
    for entity_type in ("景区", "打卡地"):
        entity = execution_entity_object_dir(EXECUTION_ID, "地点", entity_type, "都江堰")
        entity.mkdir(parents=True, exist_ok=True)
        (entity / "page.md").write_text(f"# 都江堰{entity_type}\n", encoding="utf-8")
        write_json(entity / "_entity.json", {"label": "都江堰", "domain": "地点", "type": entity_type})
    conflicts = execution_entity_type_conflicts(EXECUTION_ID)
    assert conflicts and conflicts[0]["name"] == "都江堰"


def _run_all() -> None:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"execution object path tests passed ({len(tests)})")


if __name__ == "__main__":
    _run_all()
