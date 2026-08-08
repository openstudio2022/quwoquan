"""Post review admits a carrier batch by spec quota, not candidate perfection."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution import spec_contract
from content.execution.closure import post_review as post_review_closure
from content.execution.controller import (
    content_plan_decisions,
    post_independent_review,
    professional_asset_independent_review,
    stage_post_compose,
    stage_post_review,
)
from content.execution.controller.execute import handoff
from content.execution.recovery import post_recovery
from content.post import object_index
from content.post.article import base_draft
from content.release.canonical import post_promotion
from content.source.media import check as media_check
from core.control_types import StageStatus
from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json

EXECUTION_ID = "20260728--travel-article-supply--test-region-a--pilot-903"


def _targets() -> dict[str, str]:
    return {
        "article-a": "posts/article/攻略/文章甲/1",
        "article-b": "posts/article/攻略/文章乙/1",
        "article-c": "posts/article/攻略/文章丙/1",
    }


@pytest.mark.parametrize("carrier", ("article", "image", "video"))
def test_post_review_closure_uses_one_quota_contract_for_each_post_carrier(
    monkeypatch: pytest.MonkeyPatch,
    carrier: str,
) -> None:
    monkeypatch.setattr(spec_contract, "approved_quota", lambda _execution_id: 1)
    execution_id = EXECUTION_ID.replace("-article-", f"-{carrier}-")
    closure = post_review_closure.resolve_post_review_closure(
        execution_id,
        carrier=carrier,
        object_targets={
            f"{carrier}-a": f"posts/{carrier}/测试/作品甲/1",
            f"{carrier}-b": f"posts/{carrier}/测试/作品乙/1",
        },
        object_issues={f"{carrier}-b": ["object review issue"]},
    )

    assert closure.passed
    assert closure.qualified_object_refs == (f"{carrier}-a",)
    assert tuple(row.object_ref for row in closure.discarded) == (f"{carrier}-b",)


def test_post_review_quota_met_with_discarded_object_is_publishable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # spec_ref: runtime-data-engineering article/image/video commercial closure.
    monkeypatch.setattr(spec_contract, "approved_quota", lambda _execution_id: 2)

    closure = post_review_closure.resolve_post_review_closure(
        EXECUTION_ID,
        carrier="article",
        object_targets=_targets(),
        object_issues={"article-c": ["independent reviewer rejected the object"]},
    )
    path = post_review_closure.write_post_review_closure(closure, root=tmp_path)

    assert closure.passed
    assert closure.qualified_object_refs == ("article-a", "article-b")
    assert tuple(row.object_ref for row in closure.discarded) == ("article-c",)
    payload = read_json(path)
    assert [row["disposition"] for row in payload["objects"]] == [
        "qualified",
        "qualified",
        "discarded",
    ]
    loaded = post_review_closure.load_post_review_closure(
        EXECUTION_ID,
        root=tmp_path,
        expected_object_targets=_targets(),
    )
    assert loaded.qualified_publish_refs == (
        "posts/article/攻略/文章甲/1",
        "posts/article/攻略/文章乙/1",
    )


def test_post_review_quota_shortfall_still_loads_the_qualified_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """配额未达成只是统计缺口；有一个合格对象就必须能继续走发布。"""
    monkeypatch.setattr(spec_contract, "approved_quota", lambda _execution_id: 2)
    targets = {
        "article-a": "posts/article/攻略/文章甲/1",
        "article-b": "posts/article/攻略/文章乙/1",
    }
    closure = post_review_closure.resolve_post_review_closure(
        EXECUTION_ID,
        carrier="article",
        object_targets=targets,
        object_issues={"article-b": ["rights closure is incomplete"]},
    )
    post_review_closure.write_post_review_closure(closure, root=tmp_path)

    assert not closure.passed
    assert closure.qualified_count == 1
    incremental = post_review_closure.load_post_review_closure(
        EXECUTION_ID,
        root=tmp_path,
        expected_object_targets=targets,
    )
    assert incremental.qualified_object_refs == ("article-a",)
    assert not incremental.passed
    # 只有显式的规模 promotion 才把配额达成当成硬条件。
    with pytest.raises(ValueError, match="quota shortfall"):
        post_review_closure.load_post_review_closure(
            EXECUTION_ID,
            root=tmp_path,
            expected_object_targets=targets,
            require_quota_milestone=True,
        )


def test_content_plan_absorbs_twelve_video_shortfalls_when_three_real_items_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spec_contract, "approved_quota", lambda _execution_id: 10)
    names = [f"视频候选-{index:02d}" for index in range(15)]
    active_spec = {
        "scope": {
            "coverageTargets": [
                {"name": name, "entityType": "地点/景区"} for name in names
            ]
        }
    }
    items = [
        {"ref": f"video-{index}", "entityTags": [name]}
        for index, name in enumerate(names[:3])
    ]
    issues = [
        data_issue(
            DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=name,
            lane=DataIssueLane.VIDEO,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            message="no acquired playable video",
        )
        for name in names[3:]
    ]
    persisted: dict[str, object] = {}

    absorbed = content_plan_decisions.absorb_content_plan_shortfalls(
        ctx=SimpleNamespace(execution_id=EXECUTION_ID.replace("article", "video")),
        active_spec=active_spec,
        items=items,
        issues=issues,
        carrier="video",
        persist_absorb=lambda execution_id, **kwargs: persisted.update(
            {"executionId": execution_id, **kwargs}
        ),
    )

    assert absorbed
    assert [row["name"] for row in active_spec["scope"]["coverageTargets"]] == names[:3]
    assert persisted["successful_names"] == names[:3]
    assert len(persisted["issues"]) == 12
    assert all(
        issue.code is DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL
        and issue.stage is DataIssueStage.CONTENT_PLAN
        and issue.recovery is DataRecoveryAction.RETRY_SOURCE_DISCOVERY
        for issue in persisted["issues"]
    )


def test_canonical_promotion_consumes_the_same_qualified_closure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(spec_contract, "approved_quota", lambda _execution_id: 2)
    targets = {
        "article-a": "posts/article/攻略/文章甲/1",
        "article-b": "posts/article/攻略/文章乙/1",
    }
    closure = post_review_closure.resolve_post_review_closure(
        EXECUTION_ID,
        carrier="article",
        object_targets=targets,
        object_issues={"article-b": ["discarded after review"]},
    )
    monkeypatch.setattr(
        post_review_closure,
        "indexed_post_targets",
        lambda _execution_id: targets,
    )

    def load_incremental(*_args, **kwargs):
        assert kwargs["require_quota_milestone"] is False
        return closure

    monkeypatch.setattr(
        post_review_closure,
        "load_post_review_closure",
        load_incremental,
    )

    assert post_promotion._qualified_post_refs(EXECUTION_ID) == (
        "article/攻略/文章甲/1",
    )


@pytest.mark.parametrize(
    ("approved_quota", "expected_status"),
    ((2, StageStatus.DONE), (3, StageStatus.DONE)),
)
def test_post_review_stage_allows_incremental_publish_before_quota_milestone(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    approved_quota: int,
    expected_status: StageStatus,
) -> None:
    execution_id = "20260728--travel-image-supply--test-region-a--pilot-904"
    refs = ("image-a", "image-b", "image-c")
    object_dirs = {ref: tmp_path / f"posts/image/画报/{ref}/1" for ref in refs}
    for object_dir in object_dirs.values():
        review_dir = object_dir / "5.review"
        review_dir.mkdir(parents=True)
        (review_dir / "review_gate.json").write_text(
            json.dumps({"passed": True, "issues": []}),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        stage_post_review, "_is_homepage_only_execution", lambda _ctx: False
    )
    monkeypatch.setattr(
        stage_post_review, "_review_gate_is_stale", lambda *_args: False
    )
    monkeypatch.setattr(
        stage_post_compose,
        "compose_brief_absorbed_path",
        lambda _execution_id, ref: tmp_path / f"{ref}.not-absorbed",
    )
    monkeypatch.setattr(
        stage_post_review, "_materialize_reviewed_refs", lambda *_args: []
    )
    monkeypatch.setattr(
        stage_post_review,
        "_post_exit_issues",
        lambda _ctx, selected: (
            ["image rights closure failed"] if selected == ["image-c"] else []
        ),
    )
    monkeypatch.setattr(
        stage_post_review,
        "_aggregate_review_fallback",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        object_index, "iter_content_refs", lambda _execution_id: list(refs)
    )
    monkeypatch.setattr(
        object_index,
        "content_object_dir",
        lambda _execution_id, ref: object_dirs[ref],
    )
    monkeypatch.setattr(
        object_index,
        "content_object_rel",
        lambda _execution_id, ref: object_dirs[ref].relative_to(tmp_path).as_posix(),
    )
    monkeypatch.setattr(
        object_index,
        "content_coords",
        lambda _execution_id, _ref: {"contentType": "image"},
    )
    monkeypatch.setattr(base_draft, "load_base_draft_ledger", lambda _execution_id: {})
    monkeypatch.setattr(base_draft, "save_base_draft_ledger", lambda *_args: None)
    monkeypatch.setattr(
        post_recovery,
        "_content_plan_base_draft_shortfall_refs",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        post_recovery,
        "_release_base_draft_shortfall_refs",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        post_independent_review,
        "run_post_independent_reviews",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        professional_asset_independent_review,
        "run_professional_asset_independent_reviews",
        lambda *_args: [],
    )
    monkeypatch.setattr(media_check, "check_images", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(handoff, "write_execution_reducer_gate", lambda *_args: "")
    monkeypatch.setattr(
        post_review_closure, "write_post_review_closure", lambda *_args: tmp_path
    )
    monkeypatch.setattr(
        spec_contract,
        "approved_quota",
        lambda _execution_id: approved_quota,
    )

    result = stage_post_review._run_post_review(
        SimpleNamespace(execution_id=execution_id)
    )

    assert result.status is expected_status
    assert f"qualified=2/{approved_quota}" in result.message
