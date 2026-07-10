"""多载体统一框架最小 smoke（Phase 4）：article/image lane 复用共同层 CLI 阶段契约。

不放量、不触 bridge/managed 段：只验证 download prepare（target selection →
source unit 目录协议）对 article/image lane 的复用与 lane adapter 差异边界，
以及 video 载体「只冻结 schema、无下载计划」的口径。
author 段 smoke 依 M1 批期间 bridge 独占约定推迟（见 pipeline_directory_layout_spec §2.6）。
"""
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
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

from _common.carrier_contract import CARRIER_LANES  # noqa: E402
from _common.io import read_json  # noqa: E402
from _common.paths import STAGE_DOWNLOAD, batch_root, batch_shared_dir  # noqa: E402
from _common.schema import validate_result  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from download.prepare import RESEARCH_PLAN_FILES, prepare_source_plan  # noqa: E402

_TASK = "旅行/地域/浙江省/景区/载体smoke"
_BATCH = "carrier_lane_smoke"
_EID = "西湖"


def _prepared_object_dir() -> Path:
    prepare_source_plan(
        _TASK,
        _BATCH,
        [{"entityId": _EID, "canonicalName": _EID, "entityType": "景区"}],
    )
    return resolve_entity_object_dir(_TASK, _BATCH, _EID, etype_hint="景区")


def test_article_image_lanes_reuse_common_prepare_layer():
    """article/image 与 homepage 共用同一 prepare 入口与目录协议（共同层复用）。"""
    obj = _prepared_object_dir()
    dl = obj / STAGE_DOWNLOAD
    for lane, filename in RESEARCH_PLAN_FILES.items():
        plan_path = dl / filename
        assert plan_path.is_file(), f"{lane} 缺下载计划 {filename}"
        envelope = read_json(plan_path)
        assert envelope["schemaVersion"] == "quwoquan_data.stage_envelope"
        assert envelope["step"] == f"{lane}_research"
        payload = envelope["payload"]
        assert payload["researchLane"] == lane
        assert payload["entityType"] == "景区"
    # 共同层静态指引单一真相源：批次共享文件只写一份，per-lane 计划只引用。
    guidance = batch_shared_dir(_TASK, _BATCH) / "source_research_guidance.json"
    assert guidance.is_file()
    rel_guidance = str(guidance.relative_to(batch_root(_TASK, _BATCH)))
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


def test_video_lane_has_no_download_plan_and_smoke_only():
    """video 载体：无下载计划文件、rollout=smoke_only（排产放量 BLOCK 口径）。"""
    obj = _prepared_object_dir()
    dl = obj / STAGE_DOWNLOAD
    assert not (dl / "video_source_plan.json").exists()
    assert CARRIER_LANES["video"].rollout == "smoke_only"
    assert CARRIER_LANES["video"].source_plan_file is None


def _minimal_video_manifest() -> dict:
    return {
        "schemaVersion": "quwoquan_data.post_manifest",
        "topicId": "浙江省/杭州市/西湖",
        "contentType": "video",
        "entityRefs": ["西湖"],
        "tagRefs": ["地点/景区"],
        "sourceUrls": ["https://example.invalid/video"],
        "generator": "smoke",
        "createdAt": "2026-07-10T00:00:00+08:00",
        "updatedAt": "2026-07-10T00:00:00+08:00",
        "assets": [
            {"assetId": "v1", "kind": "video", "thumbnailUrl": "https://example.invalid/v1.jpg"}
        ],
        "videoBindings": [{"assetId": "v1", "role": "cover"}],
    }


def test_video_manifest_minimal_instance_passes_light_schema_lint():
    """schema lint：最小合法 video manifest 过轻量校验；缺 required 字段必报错。"""
    manifest = _minimal_video_manifest()
    assert validate_result(manifest, "produce", "post_manifest") == []
    broken = dict(manifest)
    del broken["contentType"]
    errors = validate_result(broken, "produce", "post_manifest")
    assert any("contentType" in e for e in errors)
