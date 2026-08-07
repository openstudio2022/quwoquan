from __future__ import annotations

import json
from types import SimpleNamespace

from content.execution.agent import agent_managed
from content.execution.controller import checkpoints
from content.execution.recovery import download_gate
from content.execution.recovery import download_unresolved
from content.execution.controller import homepage_authoring
from content.source import source_unit


def test_managed_homepage_repair_budget_includes_initial_authoring_pass__contract__local_contract():
    """A two-pass ReAct budget means initial authoring plus two corrections."""
    assert agent_managed._managed_checkpoint_repair_budget_exhausted(0) is False
    assert agent_managed._managed_checkpoint_repair_budget_exhausted(agent_managed.MAX_REACT_REWINDS) is False
    assert agent_managed._managed_checkpoint_repair_budget_exhausted(agent_managed.MAX_REACT_REWINDS + 1) is True
from content.source.research import reject_memory as plan_state


def test_source_failure_is_typed_and_rewinds_before_another_author_attempt(
    tmp_path,
    monkeypatch,
):
    entity = "南雁荡山"
    ctx = SimpleNamespace(execution_id="execution")
    monkeypatch.setattr(
        checkpoints,
        "_active_spec",
        lambda _ctx: {
            "scope": {
                "coverageTargets": [
                    {"name": entity, "entityType": "地点/自然景观"},
                ]
            }
        },
    )
    monkeypatch.setattr(
        download_unresolved,
        "_active_spec",
        lambda _ctx: {
            "scope": {
                "coverageTargets": [
                    {"name": entity, "entityType": "地点/自然景观"},
                ]
            }
        },
    )
    monkeypatch.setattr(download_unresolved, "execution_root", lambda _execution_id: tmp_path)
    draft_dir = tmp_path / "entities" / "地点" / "自然景观" / entity / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "failure.json").write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.entity_page_failure",
                "targetEntity": entity,
                "failureKind": "source_entity_mismatch",
                "reasons": ["MediaWiki resolved title points to 雁荡山"],
                "evidence": [{"field": "resolvedTitle", "quote": "雁荡山"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    failures = download_unresolved._homepage_source_failure_entities(ctx)
    assert list(failures) == [entity]
    assert failures[entity]["homepage"][0].startswith(
        "entity_page_failure:source_entity_mismatch:"
    )

    monkeypatch.setattr(checkpoints, "_entity_homepages_per_target", lambda _ctx: 1)
    monkeypatch.setattr(homepage_authoring, "_homepages_done", lambda _ctx: (False, ["page missing"]))
    # 配额门：候选池已耗尽仍达不到配额，来源不匹配才升级为 source 回退。
    monkeypatch.setattr(
        homepage_authoring,
        "homepage_quota_verdict",
        lambda _ctx: homepage_authoring.HomepageQuotaVerdict(
            approved_quota=1,
            qualified_refs=(),
            discarded={f"地点/自然景观/{entity}": ("page missing",)},
        ),
    )
    # 唯一候选已是 source-failure → remaining_authorable=0 < gap=1 → 必须 rewind。
    monkeypatch.setattr(
        homepage_authoring,
        "_homepage_pending_entities",
        lambda _ctx: [entity],
    )
    result = checkpoints._checkpoint_build_homepage(ctx)
    assert result.status == "failed"
    assert result.fallback_stage == "download_plan"
    assert "source_entity_mismatch" in result.issues[0]


def test_source_failure_is_absorbed_when_oversample_still_covers_quota(
    tmp_path,
    monkeypatch,
):
    """过采池里仍有足够非 failure 候选时，个别 source-failure 不得烧 ReAct 回退。"""
    failed = "南雁荡山"
    healthy = "雁荡山"
    ctx = SimpleNamespace(execution_id="execution")
    monkeypatch.setattr(checkpoints, "_entity_homepages_per_target", lambda _ctx: 1)
    monkeypatch.setattr(checkpoints, "_active_spec", lambda _ctx: {"scope": {"coverageTargets": []}})
    monkeypatch.setattr(homepage_authoring, "_homepages_done", lambda _ctx: (False, ["page missing"]))
    monkeypatch.setattr(
        homepage_authoring,
        "homepage_quota_verdict",
        lambda _ctx: homepage_authoring.HomepageQuotaVerdict(
            approved_quota=1,
            qualified_refs=(),
            discarded={
                f"地点/自然景观/{failed}": ("source_entity_mismatch",),
                f"地点/自然景观/{healthy}": ("page missing",),
            },
        ),
    )
    monkeypatch.setattr(
        download_unresolved,
        "_homepage_source_failure_entities",
        lambda _ctx: {failed: {"homepage": ["entity_page_failure:source_entity_mismatch: bad"]}},
    )
    monkeypatch.setattr(
        homepage_authoring,
        "_homepage_pending_entities",
        lambda _ctx: [failed, healthy],
    )
    monkeypatch.setattr(
        "content.homepage.homepage.homepage_runtime_spec",
        lambda *_args, **_kwargs: {"scope": {"coverageTargets": []}},
    )
    monkeypatch.setattr(
        "content.homepage.homepage_release.materialize_entity_pages",
        lambda *_args, **_kwargs: [],
    )
    prepared: list[str] = []

    def _prepare(ctx_arg, checkpoint):
        prepared.append(checkpoint)
        return []

    monkeypatch.setattr(
        "content.execution.queue.reliabletask.jobs.prepare_reliable_author_jobs",
        _prepare,
    )
    result = checkpoints._checkpoint_build_homepage(ctx)
    assert result.status == "waiting"
    assert result.fallback_stage is None
    assert prepared == ["build_homepage"]


def test_source_failure_does_not_rewind_once_the_quota_is_met(tmp_path, monkeypatch):
    """过采吸收：配额已满时，个别对象的来源不匹配只是丢弃，不回退 source。"""
    entity = "南雁荡山"
    ctx = SimpleNamespace(execution_id="execution")
    monkeypatch.setattr(checkpoints, "_entity_homepages_per_target", lambda _ctx: 1)
    monkeypatch.setattr(homepage_authoring, "_homepages_done", lambda _ctx: (False, ["page missing"]))
    monkeypatch.setattr(
        homepage_authoring,
        "homepage_quota_verdict",
        lambda _ctx: homepage_authoring.HomepageQuotaVerdict(
            approved_quota=1,
            qualified_refs=("地点/自然景观/雁荡山",),
            discarded={f"地点/自然景观/{entity}": ("source_entity_mismatch",)},
        ),
    )

    def _unexpected(_ctx):
        raise AssertionError("quota met; source failures must not be inspected")

    monkeypatch.setattr(download_unresolved, "_homepage_source_failure_entities", _unexpected)
    result = checkpoints._checkpoint_build_homepage(ctx)
    assert result.status == "done"
    assert "1/1" in result.message


def test_homepage_only_freshness_ignores_disabled_article_and_image_plans(
    tmp_path,
    monkeypatch,
):
    ctx = SimpleNamespace(
        execution_id="execution",
        spec={"vertical": "travel"},
    )
    monkeypatch.setattr(
        checkpoints,
        "_active_spec",
        lambda _ctx: {
            "content": {
                "quotas": {
                    "entityHomepagesPerTarget": 1,
                    "entityArticlesPerTarget": 0,
                    "routeArticles": 0,
                    "imageWorksPerTarget": 0,
                }
            }
        },
    )
    monkeypatch.setattr(
        download_gate,
        "_active_spec",
        lambda _ctx: {
            "content": {
                "quotas": {
                    "entityHomepagesPerTarget": 1,
                    "entityArticlesPerTarget": 0,
                    "routeArticles": 0,
                    "imageWorksPerTarget": 0,
                }
            }
        },
    )
    monkeypatch.setattr(
        source_unit,
        "resolve_entity_object_dir",
        lambda *_args, **_kwargs: tmp_path,
    )
    plan_dir = tmp_path / "1.download"
    plan_dir.mkdir()
    for lane in ("homepage", "article", "image"):
        (plan_dir / f"{lane}_source_plan.json").write_text("{}", encoding="utf-8")

    assert download_gate._source_plan_lane_paths(ctx, "南雁荡山", "地点/自然景观") == [
        plan_dir / "homepage_source_plan.json"
    ]


def test_typed_source_failure_url_enters_research_reject_memory(tmp_path, monkeypatch):
    execution_id = "20260711--travel-homepage-source-recovery--test-region-a--pilot-001"
    entity = "南雁荡山"
    source_url = "https://zh.wikipedia.org/wiki/%E5%8D%97%E9%9B%81%E8%8D%A1%E5%B1%B1"
    draft_dir = tmp_path / "entities" / "地点" / "自然景观" / entity / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "failure.json").write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.entity_page_failure",
                "targetEntity": entity,
                "failureKind": "source_entity_mismatch",
                "reasons": ["resolved page describes a different entity"],
                "evidence": [{"field": "primarySource.canonicalUrl", "quote": source_url}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(plan_state, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        plan_state,
        "execution_command_root",
        lambda _execution_id, _command: tmp_path / "_shared" / "workspace" / "source",
    )
    monkeypatch.setattr(
        plan_state,
        "_entity_download_dirs_for_history",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(plan_state, "_execution_dirs", lambda *_args: [])

    memory = plan_state._download_reject_memory(
        execution_id,
        entity,
        entity_type="地点/自然景观",
    )

    assert plan_state._url_in_memory(source_url, memory["sourceUrls"])
