"""Canonical execution target-selection contracts."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from content.execution import store
from content.execution.planning.selection import (
    build_execution_spec,
    select_targets,
)
from content.execution.planning.source_selection import (
    TargetSourceCandidate,
    TargetSourceQualification,
)
from content.source.contracts import HomepageAuthorityProvider, QualifiedHomepageSource
from core.control_types import TargetSelector
from support.capacity_calibration_fixture import (
    synthetic_capacity_source_binding,
    synthetic_governed_execution_authority,
)
from support.target_selection_fixture import _coverage_file


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


@pytest.mark.parametrize(("intent", "quota"), (("m100", 100), ("m1000", 1000)))
def test_scale_selection_uses_local_semantic_backend_and_independent_delivery(
    intent: str,
    quota: int,
) -> None:
    spec = build_execution_spec(
        execution_id=(
            f"20260811--travel-article-{intent}--china--scale-{quota:04d}"
        ),
        name=f"{intent} semantic delivery split",
        title=f"{intent} semantic delivery split",
        region="中国",
        category="旅行",
        targets=[
            {"name": f"候选-{index:04d}", "entityType": "地点/城市"}
            for index in range(quota)
        ],
        created_by="contract-test",
        entity_articles_per_target=1,
        entity_homepages_per_target=0,
        image_works_per_target=0,
        video_works_per_target=0,
        target_entity_count=quota,
        approved_quota=quota,
        oversample_factor=1.0,
        capacity_calibration=synthetic_capacity_source_binding(),
    )

    assert spec["queuePolicy"]["backend"] == "local_file"
    assert spec["queuePolicy"]["reliableTask"] == {
        "taskType": "data.content_object.execute",
        "queue": "reliabletask.data.content_supply",
        "store": "MongoStore",
        "readyIndex": "RedisReadyIndex",
    }


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


def test_retry_source_name_resolves_to_canonical_work_identity(tmp_path: Path) -> None:
    path = tmp_path / "杭州市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "西湖区",
                        "leaves": [
                            {
                                "name": "西湖",
                                "canonicalName": "杭州西湖",
                                "entityType": "地点/景区",
                                "aliases": ["西湖风景名胜区"],
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

    targets, report = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.ALL,
        target_names=("西湖",),
    )

    assert [target["name"] for target in targets] == ["杭州西湖"]
    assert targets[0]["sourceName"] == "西湖"
    assert report["requestedTargetNames"] == ["西湖"]


def test_source_ready_retry_qualifies_resolved_canonical_work(tmp_path: Path) -> None:
    path = tmp_path / "杭州来源预选市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "西湖区",
                        "leaves": [
                            {
                                "name": "西湖",
                                "canonicalName": "杭州西湖",
                                "entityType": "地点/景区",
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
    qualified: list[TargetSourceCandidate] = []

    def qualify(target: TargetSourceCandidate) -> TargetSourceQualification:
        qualified.append(target)
        return TargetSourceQualification(
            True,
            QualifiedHomepageSource(
                provider=HomepageAuthorityProvider.WIKIPEDIA,
                title=target.name,
                url="https://zh.wikipedia.org/wiki/西湖",
            ),
        )

    targets, report = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=qualify,
        target_names=("西湖",),
    )

    assert [target["name"] for target in targets] == ["杭州西湖"]
    assert qualified == [
        TargetSourceCandidate(name="杭州西湖", aliases=("西湖",), geo_tag_ref="")
    ]
    assert report["requestedTargetNames"] == ["西湖"]


def test_retry_alias_ambiguity_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "歧义市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "甲区",
                        "leaves": [
                            {
                                "name": "景区甲",
                                "canonicalName": "杭州景区甲",
                                "aliases": ["共享别名"],
                            },
                            {
                                "name": "景区乙",
                                "canonicalName": "杭州景区乙",
                                "aliases": ["共享别名"],
                            },
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="requested target is ambiguous"):
        select_targets(
            discovery_path=path,
            limit=1,
            quota=1,
            target_selector=TargetSelector.ALL,
            target_names=("共享别名",),
        )


def test_select_targets_filters_to_declared_category(tmp_path: Path) -> None:
    path = tmp_path / "类别筛选市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "测试区",
                        "leaves": [
                            {"name": "景区对象", "entityType": "地点/景区"},
                            {"name": "博物馆对象", "entityType": "地点/博物馆"},
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
        limit=1,
        quota=1,
        target_selector=TargetSelector.ALL,
        category="景区",
    )

    assert [target["name"] for target in targets] == ["景区对象"]
    assert report["category"] == "景区"
    with pytest.raises(ValueError, match="候选池耗尽"):
        select_targets(
            discovery_path=path,
            limit=1,
            quota=1,
            target_selector=TargetSelector.ALL,
            category="不存在的类别",
        )


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
