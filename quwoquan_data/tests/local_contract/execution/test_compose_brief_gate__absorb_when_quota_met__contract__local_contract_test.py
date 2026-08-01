# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Compose-brief may absorb object failures when remaining packs still meet quota."""
from __future__ import annotations

import shutil

from content.execution.controller import stage_post_compose as subject
from content.execution.context import ExecutionContext
from content.execution.support import StageStatus
from core.control_types import ExecutionStage, RuntimeEnvironment
from core.data_issue import DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction
from core.io import write_json
from core.paths import STAGE_COMPOSE, execution_root
from support.execution_manifest_fixture import ExecutionFixtureBuilder


EXECUTION_ID = "20260731--travel-article-compose-absorb--test-region-a--pilot-912"
_NAMES = ("实体甲", "实体乙", "实体丙", "实体丁")
_REFS = tuple(f"article/游记/{name}/1" for name in _NAMES)


def test_compose_absorbs_gate_failures_when_quota_still_met(monkeypatch) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=tuple({"name": name, "entityType": "地点/景区"} for name in _NAMES),
        approved_quota=3,
    )
    fixture.build()
    root = execution_root(EXECUTION_ID)
    failed = _REFS[-1]
    for ref in _REFS:
        obj = root / "posts" / ref
        write_json(obj / "coords.json", {"contentType": "article"})
        write_json(
            obj / STAGE_COMPOSE / "compose_brief_gate.json",
            {"payload": {"passed": ref != failed, "ref": ref, "issues": []}},
        )
        write_json(obj / STAGE_COMPOSE / "writing_pack.json", {"carrier": "article"})
        (obj / STAGE_COMPOSE / "prompt.md").write_text("ok", encoding="utf-8")
        (obj / STAGE_COMPOSE / "draft.md").write_text("# body\n" * 40, encoding="utf-8")
    # Force the failed ref back into pending repair.
    (root / "posts" / failed / STAGE_COMPOSE / "prompt.md").unlink()

    import content.post.object_index as content_object
    import content.post.article.draft_io as draft_io
    import content.post.content_plan as content_plan
    import content.post.handler as post_handler
    import content.execution.recovery.stage_reset as stage_reset

    monkeypatch.setattr(content_object, "iter_content_refs", lambda _eid: list(_REFS))
    monkeypatch.setattr(
        content_object,
        "content_coords",
        lambda _eid, _ref: {"contentType": "article"},
    )
    monkeypatch.setattr(
        content_object,
        "content_object_stage_dir",
        lambda eid, ref, stage: execution_root(eid) / "posts" / ref / stage,
    )
    monkeypatch.setattr(
        draft_io, "read_writing_pack", lambda _eid, _ref: {"carrier": "article"}
    )
    monkeypatch.setattr(
        draft_io,
        "writing_pack_path",
        lambda eid, ref: execution_root(eid)
        / "posts"
        / ref
        / STAGE_COMPOSE
        / "writing_pack.json",
    )
    monkeypatch.setattr(
        draft_io,
        "prompt_path",
        lambda eid, ref: execution_root(eid) / "posts" / ref / STAGE_COMPOSE / "prompt.md",
    )
    monkeypatch.setattr(
        draft_io,
        "draft_article_path",
        lambda eid, ref: execution_root(eid) / "posts" / ref / STAGE_COMPOSE / "draft.md",
    )
    monkeypatch.setattr(draft_io, "is_placeholder", lambda _text: False)
    monkeypatch.setattr(content_plan, "load_writing_intent_overrides", lambda _eid: {})
    monkeypatch.setattr(post_handler, "handle_post", lambda _request: None)
    monkeypatch.setattr(
        stage_reset,
        "_compose_brief_gate_failures",
        lambda _ctx, _selected: (
            [
                DataIssue(
                    code=DataIssueCode.CONTRACT_INVALID,
                    stage=DataIssueStage.COMPOSE_BRIEF,
                    ref=failed,
                    recovery=DataRecoveryAction.REWIND_DOWNLOAD,
                    message="routeCoverage: missing mainline evidence",
                )
            ],
            ExecutionStage.DOWNLOAD_PLAN,
        ),
    )

    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=_NAMES,
        spec=fixture.spec(),
        managed=False,
        runtime=RuntimeEnvironment.LOCAL,
    )
    result = subject._run_post_compose(ctx)
    assert result.status is StageStatus.DONE
    assert "absorbed" in result.message
    assert subject.compose_brief_absorbed_path(EXECUTION_ID, failed).is_file()
