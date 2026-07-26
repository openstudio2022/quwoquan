"""作品准入闸口（produce/works_gate）端到端编排契约。

覆盖 evaluate_object_works 的编排职责（判定本身由 test_works_classifier 覆盖）：
- 调度 classify_works 并把 verdict 落 works_verdict.json（审计全覆盖）。
- article/image/gallery 载体下 decision != work → 返回阻断 issue（创作前拦截，省 Agent token）。
- gallery 载体归一为 image 判定。
- homepage 等非阻断载体 → 只落审计 verdict、不二次阻断。
"""
from __future__ import annotations

from pathlib import Path

import content.post.image.works_gate as works_gate
from core.data_issue import DataIssueCode, DataIssueStage, DataRecoveryAction
from core.io import read_json

_AUTHORITATIVE = """# 九寨沟旅游全攻略

九寨沟位于test-region-b阿坝州，是著名的自然风景区。最佳游览时间为秋季十月。

## 交通与门票
门票旺季169元，观光车90元。从成都出发约8小时车程。

## 核心景点
五花海、诺日朗瀑布、长海等海子色彩斑斓，值得细细游览。海拔约2000米，注意高反。
"""
_CASUAL = "今天天气真好，随手拍了张照片，开心！这家店还不错下次再来。"

_SAFE = {"imageStatus": "safe"}
EXECUTION_ID = "20260711--travel-works-gate--test-region-b--pilot-001"


def _brief() -> dict:
    return {"baseSourceRef": "sources/01.base", "title": "九寨沟"}


def _patch(monkeypatch, stage: Path, text: str, meta: dict | None = None) -> None:
    monkeypatch.setattr(works_gate, "load_base_draft_text", lambda *a, **k: text)
    monkeypatch.setattr(works_gate, "base_source_unit_meta", lambda *a, **k: dict(meta or {}))
    monkeypatch.setattr(
        works_gate.content_object, "content_object_stage_dir", lambda *a, **k: stage
    )


def test_work_article_passes_and_writes_verdict(tmp_path: Path, monkeypatch) -> None:
    stage = tmp_path / "compose"
    _patch(monkeypatch, stage, _AUTHORITATIVE)
    verdict, issues = works_gate.evaluate_object_works(
        EXECUTION_ID, "post:1", _brief(), {}, [_SAFE, _SAFE],
        carrier="article", narrative_volume=4, entity_name="九寨沟",
    )
    assert verdict["decision"] == "work"
    assert verdict["carrier"] == "article"
    assert issues == []
    written = read_json(stage / works_gate.WORKS_VERDICT_FILE)
    assert written["decision"] == "work"
    assert written["thresholdsVersion"] == verdict["thresholdsVersion"]


def test_casual_article_is_blocked_before_compose(tmp_path: Path, monkeypatch) -> None:
    stage = tmp_path / "compose"
    _patch(monkeypatch, stage, _CASUAL)
    verdict, issues = works_gate.evaluate_object_works(
        EXECUTION_ID, "post:2", _brief(), {}, [_SAFE],
        carrier="article", narrative_volume=0,
    )
    assert verdict["decision"] != "work"
    assert len(issues) == 1
    assert issues[0].code is DataIssueCode.CONTENT_CLASSIFICATION_REJECTED
    assert issues[0].stage is DataIssueStage.COMPOSE_BRIEF
    assert issues[0].recovery is DataRecoveryAction.STOP
    assert issues[0].ref == "post:2"
    assert read_json(stage / works_gate.WORKS_VERDICT_FILE)["decision"] != "work"


def test_image_work_passes(tmp_path: Path, monkeypatch) -> None:
    stage = tmp_path / "compose"
    _patch(monkeypatch, stage, "黄山日出云海")
    verdict, issues = works_gate.evaluate_object_works(
        EXECUTION_ID, "post:3", _brief(), {}, [_SAFE] * 6,
        carrier="image", narrative_volume=0, entity_name="黄山",
    )
    assert verdict["decision"] == "work"
    assert verdict["carrier"] == "image"
    assert issues == []


def test_gallery_maps_to_image_with_single_safe_asset(tmp_path: Path, monkeypatch) -> None:
    stage = tmp_path / "compose"
    _patch(monkeypatch, stage, "黄山")
    verdict, issues = works_gate.evaluate_object_works(
        EXECUTION_ID, "post:4", _brief(), {}, [_SAFE],
        carrier="image", narrative_volume=0, entity_name="黄山",
    )
    assert verdict["decision"] == "work"
    assert verdict["carrier"] == "image"
    assert issues == []


def test_homepage_audits_without_blocking(tmp_path: Path, monkeypatch) -> None:
    stage = tmp_path / "compose"
    _patch(monkeypatch, stage, _CASUAL)
    verdict, issues = works_gate.evaluate_object_works(
        EXECUTION_ID, "post:5", _brief(), {}, [],
        carrier="homepage", narrative_volume=0,
    )
    assert verdict["decision"] != "work"
    assert issues == []
    assert (stage / works_gate.WORKS_VERDICT_FILE).is_file()


def test_unsafe_images_excluded_from_image_count(tmp_path: Path, monkeypatch) -> None:
    """imageStatus 非 safe/text_heavy 的素材不计入图片作品图量门槛。"""
    stage = tmp_path / "compose"
    _patch(monkeypatch, stage, "黄山日出")
    unsafe = [{"imageStatus": "face"}, {"imageStatus": "watermark"}, {"imageStatus": "near_dup"}]
    verdict, issues = works_gate.evaluate_object_works(
        EXECUTION_ID, "post:6", _brief(), {}, unsafe,
        carrier="image", narrative_volume=0, entity_name="黄山",
    )
    assert verdict["decision"] != "work"
    assert issues
