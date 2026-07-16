"""Homepage review sidecars use the shared typed review evidence contract."""
from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import content.homepage.homepage_review as homepage_review  # noqa: E402
from core.io import read_json  # noqa: E402
from core.schema import assert_valid  # noqa: E402


def test_homepage_review_evidence_uses_canonical_schema(tmp_path: Path, monkeypatch) -> None:
    execution_id = "20260715--travel-homepage-review-evidence--cn-zhejiang--canary-001"
    object_dir = tmp_path / "entity"
    draft_dir = object_dir / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "page.md").write_text("# 测试景区\n\n正文。", encoding="utf-8")
    (draft_dir / "prompt.md").write_text("prompt", encoding="utf-8")
    (object_dir / "page.md").write_text("# 测试景区\n\n正文。", encoding="utf-8")
    monkeypatch.setattr(homepage_review, "execution_entity_object_dir", lambda *_args: object_dir)
    monkeypatch.setattr(
        homepage_review,
        "execution_entity_stage_dir",
        lambda *_args: draft_dir if _args[-1] == "4.draft" else object_dir / "5.review",
    )
    monkeypatch.setattr(
        homepage_review,
        "stage_execution_context",
        lambda _execution_id: {"executionId": _execution_id, "executionBinding": "frozen"},
    )
    monkeypatch.setattr(homepage_review, "write_entity_object_index", lambda *_args: None)

    homepage_review._write_entity_review_sidecars(
        execution_id,
        "地点",
        "景区",
        "测试景区",
        source_paths=[],
        review_payload={
            "decision": "approved",
            "issues": [],
            "checks": {
                "entityPageQuality": {"passed": True, "issues": []},
                "sourceQualification": {"passed": True, "issues": []},
            },
        },
    )

    review_dir = object_dir / "5.review"
    for schema_name, file_name in (
        ("deterministic_gate", "deterministic_gate.json"),
        ("media_ref_review", "media_ref_review.json"),
        ("evidence_index", "evidence_index.json"),
    ):
        assert_valid(read_json(review_dir / file_name), "content", schema_name)
