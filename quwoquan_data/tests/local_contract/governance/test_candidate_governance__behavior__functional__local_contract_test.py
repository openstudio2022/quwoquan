from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from governance.creators.candidates.store import CandidateRepository  # noqa: E402
from governance.creators.candidates.review import apply_review_rows  # noqa: E402
from governance.creators.candidates.state import (  # noqa: E402
    STATUS_OFFLINE,
    STATUS_PENDING_REVIEW,
    STATUS_PUBLISHED,
    STATUS_REJECTED,
    transition_target,
)


def _read_ndjson(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_candidate_requires_human_review_and_emits_audit_backfill(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "governance", now=lambda: "2026-06-13T00:00:00+00:00")
    candidate = repository.intake(
        kind="entity_homepage",
        natural_key="/entity/地点/景区/九寨沟",
        payload={"name": "九寨沟"},
        source_refs=["post:1"],
        mention_ids=["mention_1234567890abcdef12345678"],
    )
    assert candidate["status"] == STATUS_PENDING_REVIEW
    assert candidate["revision"] == 1
    assert "version" not in candidate
    assert not repository.backfill_path.exists()

    for kwargs in (
        {"reviewer": "", "decision_id": "review-1"},
        {"reviewer": "alice", "decision_id": ""},
    ):
        try:
            repository.review(candidate["candidateId"], decision="approve", **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("publication must require reviewer and decision_id")

    published = repository.review(
        candidate["candidateId"],
        decision="approve",
        reviewer="alice",
        decision_id="review-1",
        reason="来源与实体类型已核验",
    )
    assert published["status"] == STATUS_PUBLISHED
    assert published["revision"] == 2
    reviews = _read_ndjson(repository.review_path(candidate["candidateId"]))
    assert reviews[0]["actorType"] == "human"
    assert reviews[0]["fromStatus"] == STATUS_PENDING_REVIEW
    assert reviews[0]["toStatus"] == STATUS_PUBLISHED

    events = _read_ndjson(repository.backfill_path)
    assert len(events) == 1
    assert events[0]["mentionIds"] == ["mention_1234567890abcdef12345678"]
    assert events[0]["approvedBy"] == "alice"

    repository.review(
        candidate["candidateId"],
        decision="approve",
        reviewer="alice",
        decision_id="review-1",
    )
    assert len(_read_ndjson(repository.backfill_path)) == 1, "replayed decision must be idempotent"
    audit_rows = _read_ndjson(repository.audit_path)
    assert [row["action"] for row in audit_rows] == [
        "candidate.intake",
        "candidate.reviewed",
    ]
    assert [row["candidateRevision"] for row in audit_rows] == [1, 2]
    assert all("version" not in row for row in audit_rows)


def test_candidate_repository_rejects_retired_version_shape(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "governance")
    candidate_id = "candidate_1234567890abcdef12345678"
    path = repository.candidate_path(candidate_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.governance_candidate",
                "candidateId": candidate_id,
                "kind": "tag",
                "naturalKey": "Topic/主题/旧形态",
                "status": STATUS_PENDING_REVIEW,
                "payload": {},
                "sourceRefs": [],
                "mentionIds": [],
                "createdAt": "2026-06-13T00:00:00+00:00",
                "updatedAt": "2026-06-13T00:00:00+00:00",
                "version": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    try:
        repository.get(candidate_id)
    except ValueError as exc:
        assert "schema violation" in str(exc)
        assert "revision" in str(exc) or "version" in str(exc)
    else:
        raise AssertionError("retired version-shaped candidate must be rejected")


def test_explicit_state_machine_reject_offline_and_restore(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "governance", now=lambda: "2026-06-13T00:00:00+00:00")
    rejected = repository.intake(kind="tag", natural_key="Topic/主题/测试", payload={"label": "测试"})
    rejected = repository.review(
        rejected["candidateId"],
        decision="reject",
        reviewer="bob",
        decision_id="reject-1",
    )
    assert rejected["status"] == STATUS_REJECTED
    reopened = repository.review(
        rejected["candidateId"],
        decision="reopen",
        reviewer="bob",
        decision_id="reopen-1",
    )
    assert reopened["status"] == STATUS_PENDING_REVIEW
    published = repository.review(
        rejected["candidateId"],
        decision="approve",
        reviewer="bob",
        decision_id="approve-1",
    )
    assert published["status"] == STATUS_PUBLISHED
    offline = repository.review(
        rejected["candidateId"],
        decision="offline",
        reviewer="bob",
        decision_id="offline-1",
    )
    assert offline["status"] == STATUS_OFFLINE
    restored = repository.review(
        rejected["candidateId"],
        decision="approve",
        reviewer="bob",
        decision_id="restore-1",
    )
    assert restored["status"] == STATUS_PUBLISHED
    assert len(_read_ndjson(repository.backfill_path)) == 2

    try:
        transition_target(STATUS_PENDING_REVIEW, "offline")
    except ValueError as exc:
        assert "invalid candidate transition" in str(exc)
    else:
        raise AssertionError("pending candidate cannot be offlined")


def test_recursive_intake_is_depth_two_cycle_safe_and_capped(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "governance", now=lambda: "2026-06-13T00:00:00+00:00")
    graph = {
        "a": ["b"],
        "b": ["a", "c"],
        "c": ["d"],
        "d": [],
    }

    def descriptor(name: str) -> dict:
        return {"kind": "tag", "naturalKey": f"Topic/主题/{name}", "payload": {"label": name}}

    rows = repository.intake_graph(
        [descriptor("a")],
        lambda row: [descriptor(name) for name in graph[row["payload"]["label"]]],
    )
    assert [row["payload"]["label"] for row in rows] == ["a", "b", "c"]
    assert [row["payload"]["discoveryDepth"] for row in rows] == [0, 1, 2]
    assert len(repository.list_candidates(status=STATUS_PENDING_REVIEW, kind="tag")) == 3


def test_generic_review_checkpoint_applies_human_records(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "governance", now=lambda: "2026-06-13T00:00:00+00:00")
    candidate = repository.intake(
        kind="entity_homepage",
        natural_key="/entity/地点/景区/四姑娘山",
        payload={"name": "四姑娘山"},
    )
    reviewed = apply_review_rows(
        repository,
        [
            {
                "candidateId": candidate["candidateId"],
                "decisionId": "homepage-review-1",
                "decision": "approve",
                "reviewer": "homepage-ops",
                "actorType": "human",
            }
        ],
    )
    assert reviewed[0]["status"] == STATUS_PUBLISHED
    assert repository.backfill_path.is_file()
    try:
        repository.get("../../outside")
    except ValueError as exc:
        assert "invalid candidate id" in str(exc)
    else:
        raise AssertionError("candidate ids must not allow path traversal")
