"""Canonical execution target-selection contracts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from content.execution import store
from content.execution.planning.selection import (
    build_execution_spec,
    select_targets,
    write_selected_task,
)
from content.execution.spec_contract import ExecutionSpec
from core.control_types import TargetSelector

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
EXECUTION_ID = "20260711--travel-homepage-coverage--test-region-a--pilot-001"


def _spec() -> dict:
    return build_execution_spec(
        execution_id=EXECUTION_ID,
        name="test-region-a实体主页金丝雀",
        title="test-region-a实体主页金丝雀",
        region="中国/test-region-a",
        category="景区",
        targets=[
            {
                "name": "测试实体甲",
                "entityType": "地点/景区",
                "geoTagRef": "Topic/地理/行政区/中国/test-region-a/舟山市/普陀区",
                "typeTagRefs": ["Entity/地点/景区/5A景区"],
                "qualifiedHomepageSource": {
                    "provider": "wikipedia",
                    "title": "测试实体甲",
                    "url": "https://zh.wikipedia.org/wiki/测试实体甲",
                },
            }
        ],
        created_by="test",
        intent_label="zhejiang-homepage-pilot",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        video_works_per_target=0,
        target_entity_count=1,
        approved_quota=1,
        oversample_factor=1.0,
        required_workers=1,
        partition_count=16,
        capacity_plan_digest="sha256:" + "1" * 64,
    )

def test_execution_spec_has_one_identity_and_readable_intent():
    spec = _spec()
    assert spec["schema"] == "quwoquan.content.execution_spec"
    assert spec["executionId"] == EXECUTION_ID
    assert spec["intentLabel"] == "zhejiang-homepage-pilot"
    assert "taskId" not in spec
    assert "batchId" not in spec


def test_execution_spec_freezes_branch_and_commit_evidence(monkeypatch):
    def _stamp(spec: dict) -> str:
        spec["executionPolicy"]["executionBranch"] = "dev1.0"
        spec["executionPolicy"]["gitCommitSha"] = "a" * 40
        return "dev1.0"

    monkeypatch.setattr("content.execution.planning.selection.stamp_execution_branch", _stamp)

    policy = _spec()["executionPolicy"]
    assert policy["executionBranch"] == "dev1.0"
    assert policy["gitCommitSha"] == "a" * 40


def test_homepage_execution_rejects_target_without_frozen_qualified_source():
    spec = store.resolve_spec(_spec())
    del spec["scope"]["coverageTargets"][0]["qualifiedHomepageSource"]

    with pytest.raises(ValueError, match="qualifiedHomepageSource"):
        ExecutionSpec.from_mapping(spec)


def test_homepage_execution_inherits_media_policy_from_preset_only():
    raw = _spec()
    research_override = raw["content"]["research"]
    assert "imageAssetStrategy" not in research_override
    assert "imageCountPolicy" not in research_override
    assert "minimumPublishableImagesPerTarget" not in research_override

    effective = store.resolve_spec(raw)
    research = effective["content"]["research"]
    assert research["imageAssetStrategy"] == "attribution_audited_publish"
    assert research["imageCountPolicy"] == "score_bonus"
    assert "minimumPublishableImagesPerTarget" not in research


def test_execution_spec_derives_entity_types_from_selected_targets():
    spec = build_execution_spec(
        execution_id="20260712--travel-homepage-coverage--test-region-a--scale-001",
        name="test-region-a实体主页SCALE百级放量",
        title="test-region-a实体主页SCALE百级放量",
        region="中国/test-region-a",
        category="景区",
        targets=[
            {"name": "测试实体甲", "entityType": "地点/景区"},
            {"name": "良渚博物院", "entityType": "地点/博物馆"},
            {"name": "前童古镇", "entityType": "地点/古镇"},
        ],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        video_works_per_target=0,
        target_entity_count=3,
        approved_quota=3,
        oversample_factor=1.0,
        required_workers=1,
        partition_count=16,
        capacity_plan_digest="sha256:" + "1" * 64,
    )

    assert spec["scope"]["entityTypes"] == [
        "地点/博物馆",
        "地点/古镇",
        "地点/景区",
    ]


def test_execution_spec_supports_strict_full_delivery():
    spec = build_execution_spec(
        execution_id="20260712--travel-homepage-coverage--test-region-a--scale-002",
        name="test-region-a实体主页SCALE严格放量",
        title="test-region-a实体主页SCALE严格放量",
        region="中国/test-region-a",
        category="景区",
        targets=[{"name": "测试实体甲", "entityType": "地点/景区"}],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        video_works_per_target=0,
        target_entity_count=1,
        approved_quota=1,
        oversample_factor=1.0,
        required_workers=1,
        partition_count=16,
        capacity_plan_digest="sha256:" + "1" * 64,
    )

    assert spec["executionPolicy"]["selectionPolicy"] == "frozen"
    assert spec["executionPolicy"]["targetEntityCount"] == 1
    assert spec["executionPolicy"]["targetObjectCount"] == 1
    assert not {
        "allowPartialContent",
        "allowQuotaShortfall",
        "deliveryMode",
        "minCompletionMode",
        "replacementPolicy",
    } & set(spec["executionPolicy"])


def test_write_selected_execution_creates_only_canonical_plan_and_shared_evidence():
    spec = _spec()
    path = write_selected_task(
        spec,
        {
            "executionId": EXECUTION_ID,
            "selectedCount": 1,
            "discoveryPath": str(DATA_ROOT / "reference/travel/entities/china/浙江省"),
        },
    )
    root = path.parent.parent
    assert path == root / "0.plan" / "execution_spec.yaml"
    assert (root / "_shared/execution_progress.json").is_file()
    assert (root / "_shared/target_selection.json").is_file()
    assert (root / "_shared/catalog.ndjson").is_file()
    assert (root / "0.plan/target_set.json").is_file()
    assert all(
        (root / "entities/地点/景区/测试实体甲" / stage).is_dir()
        for stage in ("1.download", "2.quality", "3.compose", "4.draft", "5.review")
    )

    for artifact in root.rglob("*"):
        if not artifact.is_file() or artifact.suffix not in {".json", ".yaml", ".ndjson"}:
            continue
        text = artifact.read_text(encoding="utf-8")
        assert "taskId" not in text, artifact
        assert "batchId" not in text, artifact

    progress = json.loads((root / "_shared/execution_progress.json").read_text(encoding="utf-8"))
    assert progress["schema"] == "quwoquan.content.execution_progress"
    assert progress["executionId"] == EXECUTION_ID


def test_execution_spec_requires_readable_execution_id():
    try:
        build_execution_spec(
            execution_id="old-task-id",
            name="bad",
            title="bad",
            region="中国/test-region-a",
            category="景区",
            targets=[],
            created_by="test",
            entity_articles_per_target=0,
            entity_homepages_per_target=1,
            image_works_per_target=0,
            video_works_per_target=0,
            approved_quota=1,
            oversample_factor=1.0,
            required_workers=1,
            partition_count=16,
            capacity_plan_digest="sha256:" + "1" * 64,
        )
    except ValueError as exc:
        assert "executionId" in str(exc)
    else:
        raise AssertionError("retired task identity must be rejected")




def _pool_discovery(path: Path, count: int) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "过采区",
                        "leaves": [
                            {
                                "name": f"过采对象{index}",
                                "canonicalName": f"过采对象{index}",
                                "entityType": "地点/景区",
                                "geoTagRef": (
                                    "Topic/地理/行政区/中国/test-region-a/舟山市/过采区"
                                ),
                                "typeTagRefs": ["Entity/地点/景区/5A景区"],
                                "selectionPriority": index + 1,
                            }
                            for index in range(count)
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_candidate_pool_may_exceed_the_approved_quota(tmp_path: Path) -> None:
    """过采：候选池 5、配额 3，冻结整池，配额只约束下界。"""
    path = _pool_discovery(tmp_path / "过采市.yaml", 5)

    targets, report = select_targets(
        discovery_path=path,
        limit=5,
        quota=3,
        target_selector=TargetSelector.PRIORITY,
    )

    assert len(targets) == 5
    assert report["limit"] == 5
    assert report["approvedQuota"] == 3
    assert report["selectionShortfall"] == 0


def test_partial_supply_above_quota_still_freezes(tmp_path: Path) -> None:
    """候选池只供给 4 个，但配额 3 已满足 → 放行，shortfall 归零。"""
    path = _pool_discovery(tmp_path / "浅池市.yaml", 4)

    targets, report = select_targets(
        discovery_path=path,
        limit=6,
        quota=3,
        target_selector=TargetSelector.PRIORITY,
    )

    assert len(targets) == 4  # < limit，但 >= quota
    assert report["selectedCount"] == 4
    assert report["selectionShortfall"] == 0


def test_candidate_pool_exhausted_below_quota_is_a_selection_failure(
    tmp_path: Path,
) -> None:
    """供给低于配额才算失败，错误必须说明候选池耗尽。"""
    path = _pool_discovery(tmp_path / "枯竭市.yaml", 2)

    with pytest.raises(ValueError, match="候选池耗尽，区域实体供给不足"):
        select_targets(
            discovery_path=path,
            limit=6,
            quota=4,
            target_selector=TargetSelector.PRIORITY,
        )


def test_quota_above_candidate_pool_is_rejected_upfront(tmp_path: Path) -> None:
    path = _pool_discovery(tmp_path / "越界市.yaml", 5)

    with pytest.raises(ValueError, match="exceeds the candidate pool"):
        select_targets(
            discovery_path=path,
            limit=2,
            quota=3,
            target_selector=TargetSelector.PRIORITY,
        )


def test_execution_spec_binds_acceptance_to_the_quota_not_the_pool() -> None:
    """准出门只认配额；候选池只描述过采规模。"""
    spec = build_execution_spec(
        execution_id="20260712--travel-homepage-coverage--test-region-a--scale-777",
        name="test-region-a实体主页过采",
        title="test-region-a实体主页过采",
        region="中国/test-region-a",
        category="景区",
        targets=[
            {"name": f"过采对象{index}", "entityType": "地点/景区"}
            for index in range(5)
        ],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        video_works_per_target=0,
        target_entity_count=5,
        approved_quota=3,
        oversample_factor=1.8,
        required_workers=1,
        partition_count=16,
        capacity_plan_digest="sha256:" + "1" * 64,
    )

    assert spec["executionPolicy"]["targetEntityCount"] == 5
    assert spec["executionPolicy"]["approvedQuota"] == 3
    assert spec["executionPolicy"]["oversampleFactor"] == 1.8
    assert spec["acceptance"]["minEntities"] == 3
