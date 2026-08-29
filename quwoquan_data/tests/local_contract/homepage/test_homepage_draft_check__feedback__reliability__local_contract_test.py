from __future__ import annotations

import json
from types import SimpleNamespace

from content.post.article import base_draft as base_draft_module
from verify import verify_homepage_draft

_EXECUTION_ID = "20260722--travel-homepage-supply--test-region-a--pilot-001"
_SOURCE_REF = "1.download/sources/unit-1/source.clean.md"


def _seed_draft(
    tmp_path,
    monkeypatch,
    *,
    page_text: str,
    base_text: str,
    source_use_mode: str,
):
    object_dir = tmp_path / "entities" / "地点" / "景区" / "测试实体"
    draft_dir = object_dir / "4.draft"
    compose_dir = object_dir / "3.compose"
    draft_dir.mkdir(parents=True)
    compose_dir.mkdir(parents=True)
    (draft_dir / "page.md").write_text(page_text, encoding="utf-8")
    # 底稿正文文件必须真实在场：派生度判据以 `source.clean.md` 的行号为坐标系，
    # 只给 `baseDraft.text` 的装置不代表生产形态（生产上 primaryEvidenceRef 必填）。
    source_path = tmp_path / _SOURCE_REF
    source_path.parent.mkdir(parents=True)
    source_path.write_text(base_text, encoding="utf-8")
    monkeypatch.setattr(
        base_draft_module, "execution_root", lambda _execution_id: tmp_path
    )
    input_path = compose_dir / "entity_page_input.json"
    input_path.write_text(
        json.dumps(
            {
                "payload": {
                    "baseDraft": {
                        "text": base_text,
                        "primaryEvidenceRef": _SOURCE_REF,
                        "sourceUseMode": source_use_mode,
                        "sectionOutline": [{"level": 2, "title": "概况"}],
                    },
                    "imagePlaceholderBindings": [],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    target = SimpleNamespace(name="测试实体", entity_type="地点/景区")
    monkeypatch.setattr(
        verify_homepage_draft.store,
        "load_spec_model",
        lambda _execution_id: SimpleNamespace(
            scope=SimpleNamespace(coverage_targets=(target,))
        ),
    )
    monkeypatch.setattr(
        verify_homepage_draft,
        "execution_entity_object_dir",
        lambda *_args: object_dir,
    )
    monkeypatch.setattr(
        verify_homepage_draft,
        "execution_entity_page_input_path",
        lambda *_args: input_path,
    )
    monkeypatch.setattr(
        verify_homepage_draft,
        "homepage_source_fidelity_limit",
        lambda _execution_id: 0.92,
    )


def test_homepage_draft_check_reports_fidelity_before_finalization(tmp_path, monkeypatch):
    base_text = "测试实体位于测试区域。" * 80
    _seed_draft(
        tmp_path,
        monkeypatch,
        page_text="## 概况\n" + base_text,
        base_text=base_text,
        source_use_mode="licensed_adaptation",
    )

    report = verify_homepage_draft.homepage_draft_report(_EXECUTION_ID, "测试实体")

    assert report["passed"] is False
    assert report["baseDraftFidelity"] > 0.92
    assert any("base draft fidelity" in issue for issue in report["issues"])
    # 整篇口径与段落口径互不替代：照抄整篇时两者都必须报，段落口径还要点名段落序号。
    assert any(
        "sourceParagraphOverlap: 正文第 1 段" in issue for issue in report["issues"]
    )


def test_homepage_draft_check_reports_copyright_mode_gate(tmp_path, monkeypatch):
    """自检必须与 checkpoint 的版权模式硬门同源。

    `base_draft_fidelity_issues` 对 factual_reference_only 直接放行，其边界由
    `copyright_mode_issues` 独立判定。自检漏掉后者时，Agent 自检为「通过」却在
    checkpoint 被抄写/压缩门拦下，放量期会产生大量误判返工。
    """
    base_text = "".join(
        f"测试实体第{index}段记载了具体年份与尺度细节。" for index in range(1, 61)
    )
    _seed_draft(
        tmp_path,
        monkeypatch,
        page_text="## 概况\n" + base_text,
        base_text=base_text,
        source_use_mode="factual_reference_only",
    )

    report = verify_homepage_draft.homepage_draft_report(_EXECUTION_ID, "测试实体")

    assert report["passed"] is False
    assert any("抄写超限" in issue for issue in report["issues"])
    assert any("压缩不足" in issue for issue in report["issues"])


def test_homepage_draft_check_passes_a_rewritten_compressed_draft(tmp_path, monkeypatch):
    base_text = "".join(
        f"测试实体第{index}段记载了具体年份与尺度细节。" for index in range(1, 61)
    )
    rewritten = "".join(
        f"该处第{index}项事实经改写后只保留要点。" for index in range(1, 26)
    )
    _seed_draft(
        tmp_path,
        monkeypatch,
        page_text="## 概况\n" + rewritten,
        base_text=base_text,
        source_use_mode="factual_reference_only",
    )

    report = verify_homepage_draft.homepage_draft_report(_EXECUTION_ID, "测试实体")

    assert report["issues"] == []
    assert report["passed"] is True
