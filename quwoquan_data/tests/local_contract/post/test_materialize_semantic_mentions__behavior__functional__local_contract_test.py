from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.io import write_json  # noqa: E402
import content.post.materialize_contract as materialize  # noqa: E402


EXECUTION_ID = "20260711--travel-article-semantic-mentions--cn-sichuan--canary-001"


def test_resolve_semantic_mentions_merges_sidecar_into_manifest(tmp_path: Path, monkeypatch) -> None:
    """缺口 A 契约：review sidecar 的 entity/tag mention 必须流入 manifest.semanticMentions。"""
    sidecar_path = tmp_path / "review_entities.json"
    write_json(
        sidecar_path,
        {
            "schema": "quwoquan_data.review_entities",
            "ref": "post:1",
            "semanticMentions": [
                {
                    "mentionId": "m_entity",
                    "kind": "entity",
                    "surface": "洛绒牛场",
                    "location": "body",
                    "rangeStart": 0,
                    "rangeEnd": 4,
                    "status": "pending_review",
                    "targetRef": "/entity/地点/景区/洛绒牛场",
                    "candidateId": "cand_1",
                },
                {
                    "mentionId": "m_tag",
                    "kind": "tag",
                    "surface": "晨雾",
                    "location": "body",
                    "rangeStart": 6,
                    "rangeEnd": 8,
                    "status": "published",
                    "targetRef": "Topic/摄影/晨雾",
                },
            ],
        },
    )
    monkeypatch.setattr(materialize, "entities_path", lambda *_args: sidecar_path)

    compose_payload = {
        "semanticMentions": [
            # 与 sidecar 重复 → 去重（sidecar 优先）
            {
                "mentionId": "m_tag",
                "kind": "tag",
                "surface": "晨雾",
                "location": "body",
                "rangeStart": 6,
                "rangeEnd": 8,
                "status": "published",
                "targetRef": "Topic/摄影/晨雾",
            },
            # compose 内联 mention → 作补充保留
            {
                "mentionId": "m_inline",
                "kind": "entity",
                "surface": "九寨沟",
                "location": "body",
                "rangeStart": 10,
                "rangeEnd": 13,
                "status": "published",
                "targetRef": "/entity/地点/景区/九寨沟",
            },
        ],
    }
    merged = materialize._resolve_semantic_mentions(EXECUTION_ID, "post:1", compose_payload)
    assert [row["mentionId"] for row in merged] == ["m_entity", "m_tag", "m_inline"]
    assert {row["kind"] for row in merged} == {"entity", "tag"}


def test_resolve_semantic_mentions_tolerates_missing_sidecar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(materialize, "entities_path", lambda *_args: tmp_path / "absent.json")
    merged = materialize._resolve_semantic_mentions(EXECUTION_ID, "post:x", {})
    assert merged == []


def test_resolve_semantic_mentions_tolerates_unregistered_sidecar(monkeypatch) -> None:
    def raise_key(*_args):
        raise KeyError("review entities not registered")

    monkeypatch.setattr(materialize, "entities_path", raise_key)
    merged = materialize._resolve_semantic_mentions(
        EXECUTION_ID,
        "post:x",
        {
            "semanticMentions": [
                {
                    "mentionId": "only_compose",
                    "kind": "entity",
                    "surface": "x",
                    "location": "body",
                    "rangeStart": 0,
                    "rangeEnd": 1,
                    "status": "published",
                }
            ]
        },
    )
    assert [row["mentionId"] for row in merged] == ["only_compose"]
