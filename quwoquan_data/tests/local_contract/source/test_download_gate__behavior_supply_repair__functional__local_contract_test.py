"""场景组：download gate 供给通道判定与 download repair 记录。

download gate 契约测试（对象优先）。

从 test_download_gate__behavior__functional__local_contract_test.py
按场景拆出（本文件经 git mv 承接原文件历史）；测试逐字搬移。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.context import ExecutionContext
from content.execution.recovery.download_gate import (
    _download_repair_active_issues,
)
from content.execution.recovery.download_repair import (
    _record_download_repair,
)
from content.execution.recovery.download_research_gate import (
    _commercial_video_candidate_issues,
    _download_research_lane_issues,
)
from content.source.gate import download_requirements
from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json, write_json
from core.paths import (
    execution_entity_object_dir,
    execution_root,
)
from support.download_gate_fixture import (
    ARTICLE_TASK,
    TASK,
    VIDEO_TASK,
    _clean_execution_root,
)
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def test_homepage_only_download_requires_one_verified_text_source(monkeypatch):
    monkeypatch.setattr(
        "content.execution.store.load_spec_model",
        lambda _execution_id: ExecutionFixtureBuilder(TASK).spec(),
    )

    requirements = download_requirements(TASK)

    assert requirements.min_sources == 1
    assert requirements.min_homepage_sources == 1
    assert requirements.min_homepage_media == 0
    assert requirements.min_article_base_sources == 0


def test_homepage_low_resolution_candidate_does_not_invalidate_text_source():
    entity = "测试实体甲"
    fixture = ExecutionFixtureBuilder(TASK)
    obj = execution_entity_object_dir(TASK, "地点", "景区", entity)
    write_json(
        obj / "1.download" / "homepage_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "home_wikipedia",
                        "sourceKind": "wikipedia",
                        "platform": "维基百科",
                        "category": "encyclopedia",
                        "sourceRole": "primary",
                        "url": "https://zh.wikipedia.org/wiki/test-entity-a",
                        "extractor": "wikipedia_api",
                        "policyRevision": "encyclopedia-primary",
                        "imageUrls": [
                            {
                                "url": "https://upload.wikimedia.org/test-small.jpg",
                                "width": 320,
                                "height": 240,
                                "caption": entity,
                            }
                        ],
                    }
                ]
            }
        },
    )
    context = ExecutionContext(
        execution_id=TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    assert _download_research_lane_issues(
        context,
        entity,
        "地点/景区",
        "homepage",
    ) == []


def test_article_completion_gate_accepts_registry_encyclopedia_base_source():
    entity = "南浔古镇"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=({"entityType": "地点/景区", "name": entity},),
        approved_quota=1,
    )
    fixture.build()
    obj = execution_entity_object_dir(ARTICLE_TASK, "地点", "景区", entity)
    write_json(
        obj / "1.download" / "article_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "article_wikipedia_nanxun",
                        "platform": "维基百科",
                        "category": "encyclopedia",
                        "sourceRole": "base",
                        "entityMatch": "strong",
                        "url": "https://zh.wikipedia.org/wiki/南浔镇",
                    }
                ]
            }
        },
    )
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    assert _download_research_lane_issues(
        context,
        entity,
        "地点/景区",
        "article",
    ) == []


def test_video_download_does_not_accept_image_quota_as_video_supply(monkeypatch):
    fixture = ExecutionFixtureBuilder(VIDEO_TASK)
    monkeypatch.setattr(
        "content.execution.store.load_spec_model",
        lambda _execution_id: fixture.spec(),
    )

    requirements = download_requirements(VIDEO_TASK)

    assert requirements.min_images == 0
    assert not hasattr(requirements, "min_video_frames")


def test_commercial_video_candidate_requires_exact_rights_closure():
    admitted = {
        "publicationAdmission": "commercial_release",
        "commercialAuthorizationStatus": "verified",
        "rightsStatus": "verified",
        "rightsIssues": [],
        "authorizationProofUrl": "https://media.example/proof",
        "termsUrl": "https://media.example/terms",
    }
    assert _commercial_video_candidate_issues(admitted) == []

    stale_research = {
        **admitted,
        "publicationAdmission": "research_release",
        "commercialAuthorizationStatus": "unverified",
        "rightsStatus": "unverified",
        "rightsIssues": ["authorization pending"],
        "authorizationProofUrl": "",
    }
    assert _commercial_video_candidate_issues(stale_research) == [
        "publicationAdmission must be commercial_release",
        "commercialAuthorizationStatus must be verified",
        "rightsStatus must be verified",
        "rightsIssues must be empty",
        "authorizationProofUrl must use HTTPS",
    ]


def test_download_repair_active_issues_only_decodes_typed_records():
    issue = data_issue(
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref="测试实体甲",
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="retained source requirement is not met",
    )
    ctx = SimpleNamespace(entity_ids=["测试实体甲"])

    assert _download_repair_active_issues(
        ctx,
        {"entityId": "测试实体甲", "issueRecords": [issue.as_dict()]},
    ) == [str(issue)]

    with pytest.raises(ValueError, match="typed issueRecords"):
        _download_repair_active_issues(
            ctx,
            {"entityId": "测试实体甲", "issues": ["legacy message-only issue"]},
        )


def test_download_repair_uses_each_target_canonical_entity_type():
    entity = "刘基庙"
    shutil.rmtree(execution_root(TASK), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        TASK,
        targets=(
            {"entityType": "地点/景区", "name": "测试景区"},
            {"entityType": "地点/遗址", "name": entity},
        ),
    )
    fixture.build()
    plan = (
        execution_entity_object_dir(TASK, "地点", "遗址", entity)
        / "1.download"
        / "homepage_source_plan.json"
    )
    write_json(plan, {"payload": {"entityId": entity, "sources": []}})
    issue = data_issue(
        DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref=entity,
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="homepage primary authority source is missing",
    )

    packet_path = _record_download_repair(
        ExecutionContext(
            execution_id=TASK,
            entity_ids=(entity,),
            spec=fixture.spec(),
        ),
        [issue],
    )

    repair = read_json(packet_path)["entities"][0]
    assert Path(repair["sourcePlanPath"]) == plan
    assert all("/地点/遗址/刘基庙/" in path for path in repair["sourcePlanPaths"])
