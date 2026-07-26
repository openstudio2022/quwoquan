from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import governance.coverage.entity_extract as entity_extract  # noqa: E402
from governance.creators.candidates.store import CandidateRepository  # noqa: E402


EXECUTION_ID = "20260714--travel-homepage-governance--test-region-a--pilot-001"


def test_unknown_entity_is_candidate_not_placeholder_homepage(tmp_path: Path, monkeypatch) -> None:
    sidecar_path = tmp_path / "review_entities.json"
    repository = CandidateRepository(tmp_path / "governance", now=lambda: "2026-06-13T00:00:00+00:00")
    try:
        entity_extract.generate_entity_homepage(
            EXECUTION_ID,
            "洛绒牛场",
            "地点",
            "自然景观",
            candidate_repository=repository,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("legacy homepage helper must not bypass governance approval")

    monkeypatch.setattr(entity_extract, "entities_path", lambda *_args: sidecar_path)
    monkeypatch.setattr(entity_extract, "homepage_exists", lambda *_args: False)

    def fail_generate(*_args, **_kwargs):
        raise AssertionError("placeholder homepage generation must stay disabled")

    monkeypatch.setattr(entity_extract, "generate_entity_homepage", fail_generate)
    meta = {
        "extractedEntities": [
            {"name": "洛绒牛场", "type": "牧场", "evidenceRef": "source:1"},
        ]
    }
    article = "😀从洛绒牛场出发，傍晚再回到洛绒牛场。"
    sidecar = entity_extract.build_entities_sidecar(
        EXECUTION_ID,
        "post:1",
        meta,
        article_text=article,
        candidate_repository=repository,
    )
    entity = sidecar["entities"][0]
    assert entity["hasHomepage"] is False
    assert entity["generated"] is False
    assert entity["governanceStatus"] == "pending_review"
    assert len(entity["mentionIds"]) == 2
    assert sidecar["semanticMentions"][0]["startUtf16"] == 3

    candidate = repository.get(entity["candidateId"])
    assert candidate is not None
    assert candidate["naturalKey"] == "/entity/地点/自然景观/洛绒牛场"
    assert candidate["mentionIds"] == entity["mentionIds"]

    repository.review(
        entity["candidateId"],
        decision="approve",
        reviewer="homepage-ops",
        decision_id="approve-homepage-1",
    )
    approved_sidecar = entity_extract.build_entities_sidecar(
        EXECUTION_ID,
        "post:1",
        meta,
        article_text=article,
        candidate_repository=repository,
    )
    assert approved_sidecar["entities"][0]["governanceStatus"] == "published"
    assert approved_sidecar["entities"][0]["hasHomepage"] is False
    assert [row["mentionId"] for row in approved_sidecar["semanticMentions"]] == entity["mentionIds"]


def test_extracted_tags_emit_tag_semantic_mentions(tmp_path: Path, monkeypatch) -> None:
    """草稿 extractedTags → tag mention：已发布标签 published 可点击，未发布 pending_review 待治理。"""
    monkeypatch.setattr(entity_extract, "entities_path", lambda *_args: tmp_path / "review_entities.json")
    monkeypatch.setattr(entity_extract, "homepage_exists", lambda *_args: False)
    published_refs = {"Topic/摄影/晨雾"}
    monkeypatch.setattr(entity_extract, "tag_exists", lambda ref: ref in published_refs)
    repository = CandidateRepository(tmp_path / "governance")
    meta = {
        "extractedEntities": [],
        "extractedTags": [
            {"label": "晨雾", "dimensionId": "Topic/摄影", "isNew": False},
            {"label": "小众路线", "dimensionId": "Topic/旅行", "isNew": True},
        ],
    }
    article = "清晨拍到了晨雾，这是一条小众路线。"
    sidecar = entity_extract.build_entities_sidecar(
        EXECUTION_ID,
        "post:tag",
        meta,
        article_text=article,
        candidate_repository=repository,
    )
    tags = {row["label"]: row for row in sidecar["tags"]}
    assert tags["晨雾"]["ref"] == "Topic/摄影/晨雾"
    assert tags["晨雾"]["published"] is True
    assert tags["晨雾"]["governanceStatus"] == "published"
    assert tags["小众路线"]["published"] is False
    assert tags["小众路线"]["governanceStatus"] == "pending_review"

    tag_mentions = [row for row in sidecar["semanticMentions"] if row["kind"] == "tag"]
    assert {row["surface"] for row in tag_mentions} == {"晨雾", "小众路线"}
    published_mention = next(row for row in tag_mentions if row["surface"] == "晨雾")
    assert published_mention["status"] == "published"
    assert published_mention["targetRef"] == "Topic/摄影/晨雾"
    assert tags["晨雾"]["mentionIds"] == [published_mention["mentionId"]]


def test_existing_offline_homepage_marks_mentions_offline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(entity_extract, "entities_path", lambda *_args: tmp_path / "review_entities.json")
    monkeypatch.setattr(entity_extract, "homepage_exists", lambda *_args: True)
    monkeypatch.setattr(entity_extract, "_existing_homepage_status", lambda *_args: "offline")
    repository = CandidateRepository(tmp_path / "governance")
    sidecar = entity_extract.build_entities_sidecar(
        EXECUTION_ID,
        "post:2",
        {"extractedEntities": [{"name": "旧景区", "type": "景区"}]},
        article_text="旧景区目前已关闭。",
        candidate_repository=repository,
    )
    assert sidecar["entities"][0]["candidateId"] == ""
    assert sidecar["entities"][0]["governanceStatus"] == "offline"
    assert sidecar["semanticMentions"][0]["status"] == "offline"
    assert not repository.candidates_dir.exists()
