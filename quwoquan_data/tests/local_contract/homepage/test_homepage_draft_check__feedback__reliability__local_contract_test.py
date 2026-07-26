from __future__ import annotations

import json
from types import SimpleNamespace

from verify import verify_homepage_draft


def test_homepage_draft_check_reports_fidelity_before_finalization(tmp_path, monkeypatch):
    object_dir = tmp_path / "entities" / "地点" / "景区" / "测试实体"
    draft_dir = object_dir / "4.draft"
    compose_dir = object_dir / "3.compose"
    draft_dir.mkdir(parents=True)
    compose_dir.mkdir(parents=True)
    base_text = "测试实体位于测试区域。" * 80
    (draft_dir / "page.md").write_text(
        "## 概况\n" + base_text,
        encoding="utf-8",
    )
    input_path = compose_dir / "entity_page_input.json"
    input_path.write_text(
        json.dumps(
            {
                "payload": {
                    "baseDraft": {
                        "text": base_text,
                        "sourceUseMode": "licensed_adaptation",
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

    report = verify_homepage_draft.homepage_draft_report(
        "20260722--travel-homepage-supply--test-region-a--pilot-001",
        "测试实体",
    )

    assert report["passed"] is False
    assert report["baseDraftFidelity"] > 0.92
    assert any("base draft fidelity" in issue for issue in report["issues"])
