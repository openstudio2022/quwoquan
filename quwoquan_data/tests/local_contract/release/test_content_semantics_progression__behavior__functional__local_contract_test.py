from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.io import write_json  # noqa: E402
from verify import verify_content_semantics as semantics  # noqa: E402


def _post(tmp_path: Path, *, ref: str, route_entities: list[str]) -> Path:
    posts = tmp_path / "posts"
    leaf = posts / "article" / "攻略" / "标题" / "1"
    leaf.mkdir(parents=True)
    (leaf / "article.md").write_text(
        "# 标题\n\n正文围绕单一景区展开，包含足够长度的独立表达与事实说明。",
        encoding="utf-8",
    )
    write_json(
        leaf / "manifest.json",
        {
            "topicId": ref,
            "sourceUrls": ["https://example.test/source"],
            "storySpine": {"routeEntities": route_entities},
        },
    )
    return posts


def test_single_entity_story_does_not_require_route_transitions(tmp_path, monkeypatch):
    monkeypatch.setattr(semantics, "_load_brief_facts", lambda *_args: [])
    issues = semantics.verify_semantics(
        _post(tmp_path, ref="single_entity_ref", route_entities=["墨石公园"]),
        execution_id="20260711--travel-semantics--test-region-b--pilot-001",
    )
    assert not any("narrativeContinuity" in issue for issue in issues), issues


def test_multi_entity_story_reports_topic_id_for_missing_transitions(tmp_path, monkeypatch):
    monkeypatch.setattr(semantics, "_load_brief_facts", lambda *_args: [])
    issues = semantics.verify_semantics(
        _post(tmp_path, ref="multi_entity_ref", route_entities=["甲景区", "乙景区"]),
        execution_id="20260711--travel-semantics--test-region-b--pilot-001",
    )
    assert "multi_entity_ref: narrativeContinuity lacks progression transitions" in issues
