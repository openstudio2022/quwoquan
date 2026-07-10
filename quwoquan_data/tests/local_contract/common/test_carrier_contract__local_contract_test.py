"""统一多载体框架契约（Phase 4 冻结口径防漂移）。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import json

from _common.carrier_contract import (
    CARRIER_LANES,
    COMMON_LAYER_STAGES,
    CONTENT_MIX_TO_LANE,
    LANE_TO_CANONICAL_CONTENT_MIX,
    research_plan_files,
    scaled_lanes,
    smoke_only_lanes,
)


def test_four_carriers_frozen_and_video_smoke_only():
    """四载体齐备；video 只 smoke 不放量；homepage/article/image 可放量。"""
    assert set(CARRIER_LANES) == {"homepage", "article", "image", "video"}
    assert set(scaled_lanes()) == {"homepage", "article", "image"}
    assert smoke_only_lanes() == ("video",)
    assert not CARRIER_LANES["video"].agent_authored, "video 不得进入 produce_author"


def test_common_layer_stages_cover_end_to_end():
    """共同层契约：target selection → ... → coverage/env import 全链无缺段。"""
    assert COMMON_LAYER_STAGES == (
        "target_selection",
        "source_unit",
        "asset_index",
        "review_ledger",
        "publish",
        "ship",
        "coverage_env_import",
    )


def test_carrier_final_artifacts_match_layout_spec():
    """载体成品产物与 pipeline_directory_layout_spec 口径一致。"""
    assert CARRIER_LANES["homepage"].final_artifacts == ("page.md", "_entity.json", "manifest.json")
    assert "draft.article.md" in CARRIER_LANES["article"].draft_artifacts
    assert "writing_pack" in CARRIER_LANES["article"].draft_artifacts
    assert CARRIER_LANES["image"].draft_artifacts == (), "image 无 agent 写作段"


def test_download_prepare_consumes_contract_not_second_registry():
    """download/prepare 的 RESEARCH_PLAN_FILES 必须来自 carrier_contract（无第二真相源）。"""
    from download.prepare import RESEARCH_PLAN_FILES

    assert RESEARCH_PLAN_FILES == research_plan_files()
    assert RESEARCH_PLAN_FILES == {
        "homepage": "homepage_source_plan.json",
        "article": "article_source_plan.json",
        "image": "image_source_plan.json",
    }
    assert "video" not in RESEARCH_PLAN_FILES, "video 无独立下载计划（schema+smoke only）"


def test_batch_content_type_axis_matches_carrier_lanes():
    """批次三轴 contentType（paths.BATCH_CONTENT_TYPES）与 CARRIER_LANES 键集一致。

    paths.py 是运行热路径不反向 import 本契约；一致性由本测试防漂移。
    """
    from _common.paths import BATCH_CONTENT_TYPES

    assert tuple(sorted(BATCH_CONTENT_TYPES)) == tuple(sorted(CARRIER_LANES))


def test_content_mix_naming_maps_onto_lanes_single_source():
    """排产命名（content mix）→ lane 映射为单一真相源，双向自洽。

    - content_supply.VALID_CONTENT_TYPES 必须从 CONTENT_MIX_TO_LANE 派生；
    - 每个映射目标都必须是已冻结 lane；
    - 反向表覆盖全部 lane 且回环成立（canonical 主类型）。
    """
    from task.content_supply import VALID_CONTENT_TYPES

    assert VALID_CONTENT_TYPES == tuple(CONTENT_MIX_TO_LANE)
    assert set(CONTENT_MIX_TO_LANE.values()) <= set(CARRIER_LANES)
    assert set(LANE_TO_CANONICAL_CONTENT_MIX) == set(CARRIER_LANES)
    for lane, mix_name in LANE_TO_CANONICAL_CONTENT_MIX.items():
        assert CONTENT_MIX_TO_LANE[mix_name] == lane
    # knowledgeCard 是 article 载体的排产变体，不得出现在批次轴/lane 集合。
    assert CONTENT_MIX_TO_LANE["knowledgeCard"] == "article"
    assert "knowledgeCard" not in CARRIER_LANES


def test_video_schema_frozen_in_post_manifest():
    """video schema 冻结 smoke：post_manifest.schema.json 含 video enum 与 videoBindings。"""
    schema_path = DATA_ROOT / "schema" / "produce" / "post_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "video" in schema["properties"]["contentType"]["enum"]
    assert "videoBindings" in schema["properties"]
    bindings = schema["properties"]["videoBindings"]["items"]
    assert bindings["required"] == ["assetId"]
    assert set(bindings["properties"]["role"]["enum"]) == {"cover", "embedded", "node", "shortVideo"}


def test_video_schema_conditional_branch_frozen():
    """video 条件分支冻结：assets 必含 kind=video 资产且带 thumbnail/cover 之一。"""
    schema_path = DATA_ROOT / "schema" / "produce" / "post_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    video_branch = next(
        cond["then"]
        for cond in schema.get("allOf", [])
        if cond.get("if", {}).get("properties", {}).get("contentType", {}).get("const") == "video"
    )
    assert "assets" in video_branch["required"]
    contains = video_branch["properties"]["assets"]["contains"]
    assert contains["properties"]["kind"]["const"] == "video"
    alt_keys = {tuple(alt["required"]) for alt in contains["anyOf"]}
    assert alt_keys == {("thumbnailUrl",), ("coverUrl",)}
