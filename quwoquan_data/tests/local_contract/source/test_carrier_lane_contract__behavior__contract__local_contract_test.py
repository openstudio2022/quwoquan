"""All four carriers reuse the common source-plan layer with explicit adapters."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import tempfile

_TMP = Path(tempfile.mkdtemp(prefix="carrier_smoke_"))

from core.carrier_contract import CARRIER_LANES  # noqa: E402
from core.io import read_json  # noqa: E402
from core.paths import STAGE_DOWNLOAD, execution_root, execution_shared_dir  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir  # noqa: E402
from content.source.prepare import RESEARCH_PLAN_FILES, prepare_source_plan  # noqa: E402

_TASK = "20260711--travel-article-carrier-lane--test-region-a--pilot-001"
_EID = "西湖"


def _prepared_object_dir() -> Path:
    prepare_source_plan(
        _TASK,
        [{"entityId": _EID, "canonicalName": _EID, "entityType": "景区"}],
    )
    return resolve_entity_object_dir(_TASK, _EID, etype_hint="景区")


def test_article_image_lanes_reuse_common_prepare_layer():
    """article/image 与 homepage 共用同一 prepare 入口与目录协议（共同层复用）。"""
    obj = _prepared_object_dir()
    dl = obj / STAGE_DOWNLOAD
    for lane, filename in RESEARCH_PLAN_FILES.items():
        plan_path = dl / filename
        assert plan_path.is_file(), f"{lane} 缺下载计划 {filename}"
        envelope = read_json(plan_path)
        assert envelope["schema"] == "quwoquan_data.stage_envelope"
        assert envelope["step"] == f"{lane}_research"
        payload = envelope["payload"]
        assert payload["researchLane"] == lane
        assert payload["entityType"] == "景区"
    # 共同层静态指引单一真相源：批次共享文件只写一份，per-lane 计划只引用。
    guidance = execution_shared_dir(_TASK) / "source_research_guidance.json"
    assert guidance.is_file()
    rel_guidance = str(guidance.relative_to(execution_root(_TASK)))
    for lane in ("homepage", "article"):
        payload = read_json(dl / RESEARCH_PLAN_FILES[lane])["payload"]
        assert payload["sourceGuidanceRef"] == rel_guidance


def test_lane_adapter_payload_differences_match_contract():
    """lane adapter 差异只出现在契约声明的字段（文字源 vs 图片集合源）。"""
    obj = _prepared_object_dir()
    dl = obj / STAGE_DOWNLOAD
    article = read_json(dl / RESEARCH_PLAN_FILES["article"])["payload"]
    image = read_json(dl / RESEARCH_PLAN_FILES["image"])["payload"]
    # article：文字来源 + 单源图片策略；无图片集合策略。
    assert "sources" in article and "sourceImagePolicy" in article
    assert "sourceCollectionPolicy" not in article
    # image：图片集合采集策略；无文字 sources 面。
    assert "collections" in image and "sourceCollectionPolicy" in image
    assert "sources" not in image
    assert image["sourceCollectionPolicy"]["aiImagesAllowed"] is False


def test_video_lane_has_formal_rights_cleared_render_plan():
    obj = _prepared_object_dir()
    dl = obj / STAGE_DOWNLOAD
    plan = read_json(dl / "video_source_plan.json")["payload"]
    assert CARRIER_LANES["video"].source_plan_file == "video_source_plan.json"
    assert plan["renderStrategy"] == "rights_cleared_image_sequence"
    assert plan["sourceAssetPolicy"]["rightsEvidenceRequired"] is True
