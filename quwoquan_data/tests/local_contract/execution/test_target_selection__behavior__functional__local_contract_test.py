"""Canonical execution target-selection contracts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from content.execution.selection import (
    build_execution_spec,
    select_targets,
    write_selected_task,
)
from content.execution.source_selection import (
    TargetSourceCandidate,
    TargetSourceQualification,
)
from content.source.contracts import HomepageAuthorityProvider, QualifiedHomepageSource
from core.data_issue import DataIssueCode, DataIssueError
from core.control_types import TargetSelector
from content.execution import store
from content.execution.spec_contract import ExecutionSpec


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
EXECUTION_ID = "20260711--travel-homepage-coverage--test-region-a--pilot-001"


def _coverage_file(path: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "普陀区",
                        "leaves": [
                            {
                                "name": "测试实体甲",
                                "canonicalName": "测试实体甲",
                                "entityType": "地点/景区",
                                "geoTagRef": "Topic/地理/行政区/中国/test-region-a/舟山市/普陀区",
                                "typeTagRefs": ["Entity/地点/景区/5A景区"],
                                "selectionPriority": 1,
                            }
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
    )


def test_select_targets_uses_static_coverage_identity_only(tmp_path: Path):
    targets, report = select_targets(
        discovery_path=_coverage_file(tmp_path / "舟山市.yaml"),
        limit=1,
        quota=1,
        target_selector=TargetSelector.ALL,
    )
    assert [item["name"] for item in targets] == ["测试实体甲"]
    assert targets[0]["geoTagRef"].endswith("/普陀区")
    assert {"name", "entityType", "geoTagRef", "typeTagRefs", "region", "sourceName"}.issubset(targets[0])
    assert all("readiness" not in key.lower() and "primarysource" not in key.lower() for key in targets[0])
    assert report["selectedCount"] == 1


def test_select_targets_preserves_leaf_name_as_canonical_alias(tmp_path: Path):
    path = tmp_path / "杭州市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "钱塘区",
                        "leaves": [
                            {
                                "name": "金沙湖",
                                "canonicalName": "杭州金沙湖",
                                "entityType": "地点/公园",
                                "aliases": ["金沙湖公园"],
                            }
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    targets, _report = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.ALL,
    )

    assert targets[0]["name"] == "杭州金沙湖"
    assert targets[0]["sourceName"] == "金沙湖"
    assert targets[0]["aliases"] == ["金沙湖", "金沙湖公园"]


def test_select_targets_applies_priority_only_when_explicit(tmp_path: Path) -> None:
    path = tmp_path / "排序市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "测试区",
                        "leaves": [
                            {"name": "主清单顺序对象", "selectionPriority": 2},
                            {"name": "优先对象", "selectionPriority": 1},
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    all_targets, _ = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.ALL,
    )
    priority_targets, report = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.PRIORITY,
    )

    assert all_targets[0]["name"] == "主清单顺序对象"
    assert priority_targets[0]["name"] == "优先对象"
    assert report["targetSelector"] == TargetSelector.PRIORITY.value


def test_post_selection_preserves_parent_homepage_target_order(tmp_path: Path) -> None:
    path = tmp_path / "父主页目标市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "测试区",
                        "leaves": [
                            {"name": "测试实体甲"},
                            {"name": "测试实体乙"},
                            {"name": "测试实体丙"},
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    targets, report = select_targets(
        discovery_path=path,
        limit=2,
        quota=2,
        target_selector=TargetSelector.ALL,
        target_names=("测试实体丙", "测试实体甲"),
    )

    assert [target["name"] for target in targets] == ["测试实体丙", "测试实体甲"]
    assert report["requestedTargetNames"] == ["测试实体丙", "测试实体甲"]


def test_source_ready_priority_qualifies_until_target_set_is_frozen(tmp_path: Path) -> None:
    path = tmp_path / "来源预选市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "测试区",
                        "leaves": [
                            {"name": "缺百科来源对象", "selectionPriority": 1},
                            {"name": "缺百科来源对象乙", "selectionPriority": 2},
                            {"name": "缺百科来源对象丙", "selectionPriority": 3},
                            {"name": "可用百科来源对象", "selectionPriority": 4},
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    def qualify(target: TargetSourceCandidate) -> TargetSourceQualification:
        if target.name == "可用百科来源对象":
            return TargetSourceQualification(
                True,
                QualifiedHomepageSource(
                    provider=HomepageAuthorityProvider.WIKIPEDIA,
                    title=target.name,
                    url="https://zh.wikipedia.org/wiki/可用百科来源对象",
                ),
            )
        return TargetSourceQualification(
            False,
            None,
            rejection_code=DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
        )

    targets, report = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=qualify,
    )

    assert [item["name"] for item in targets] == ["可用百科来源对象"]
    qualification = report["sourceQualification"]
    assert qualification["evaluatedCount"] == 4
    assert qualification["acceptedCount"] == 1
    assert qualification["rejectedCount"] == 3
    assert qualification["candidates"][0]["rejectionCode"] == "DATA.SOURCE.PRIMARY_AUTHORITY_MISSING"
    assert targets[0]["qualifiedHomepageSource"] == {
        "provider": "wikipedia",
        "title": "可用百科来源对象",
        "url": "https://zh.wikipedia.org/wiki/可用百科来源对象",
    }


def test_source_ready_priority_uses_explicit_runtime_targets_before_freezing(tmp_path: Path) -> None:
    path = tmp_path / "显式来源预选市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "测试区",
                        "leaves": [
                            {"name": "非目标对象", "selectionPriority": 1},
                            {"name": "金丝雀对象", "selectionPriority": 2},
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    qualified: list[str] = []

    def qualify(target: TargetSourceCandidate) -> TargetSourceQualification:
        qualified.append(target.name)
        return TargetSourceQualification(
            True,
            QualifiedHomepageSource(
                provider=HomepageAuthorityProvider.WIKIPEDIA,
                title=target.name,
                url=f"https://zh.wikipedia.org/wiki/{target.name}",
            ),
        )

    targets, report = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=qualify,
        target_names=("金丝雀对象",),
    )

    assert [item["name"] for item in targets] == ["金丝雀对象"]
    assert qualified == ["金丝雀对象"]
    assert report["requestedTargetNames"] == ["金丝雀对象"]


def test_source_ready_priority_reports_exhaustion_only_after_all_candidates(tmp_path: Path) -> None:
    path = tmp_path / "预算来源预选市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "测试区",
                        "leaves": [{"name": f"对象{index}"} for index in range(3)],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(DataIssueError) as raised:
        select_targets(
            discovery_path=path,
            limit=1,
            quota=1,
            target_selector=TargetSelector.SOURCE_READY_PRIORITY,
            source_qualifier=lambda _target: TargetSourceQualification(
                False,
                None,
                rejection_code=DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
            ),
        )

    issue = raised.value.issues[0]
    assert issue.code is DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED
    assert dict(issue.attributes)["candidateCount"] == "3"
    assert dict(issue.attributes)["evaluatedCount"] == "3"
    assert dict(issue.attributes)["rejectionCounts"] == "DATA.SOURCE.PRIMARY_AUTHORITY_MISSING:3"


def test_execution_spec_has_one_identity_and_readable_intent():
    spec = _spec()
    assert spec["schema"] == "quwoquan.content.execution_spec"
    assert spec["executionId"] == EXECUTION_ID
    assert spec["intentLabel"] == "zhejiang-homepage-pilot"
    assert "taskId" not in spec
    assert "batchId" not in spec


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
    )

    assert spec["executionPolicy"]["targetEntityCount"] == 5
    assert spec["executionPolicy"]["approvedQuota"] == 3
    assert spec["executionPolicy"]["oversampleFactor"] == 1.8
    assert spec["acceptance"]["minEntities"] == 3
