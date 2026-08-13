"""Canonical execution target-selection contracts."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from content.execution.planning.selection import select_targets
from content.execution.planning.source_selection import (
    TargetSourceCandidate,
    TargetSourceQualification,
)
from content.source.contracts import HomepageAuthorityProvider, QualifiedHomepageSource
from core.control_types import TargetSelector
from core.data_issue import DataIssueCode, DataIssueError
from support.target_selection_fixture import _coverage_file


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


def test_video_source_ready_priority_does_not_persist_homepage_evidence(
    tmp_path: Path,
) -> None:
    path = _coverage_file(tmp_path / "视频预选市.yaml")

    def qualify(target: TargetSourceCandidate) -> TargetSourceQualification:
        return TargetSourceQualification(
            True,
            QualifiedHomepageSource(
                provider=HomepageAuthorityProvider.WIKIPEDIA,
                title=target.name,
                url="https://commons.wikimedia.org/wiki/File:video",
            ),
        )

    targets, report = select_targets(
        discovery_path=path,
        limit=1,
        quota=1,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=qualify,
        qualification_source_key="qualifiedVideoSource",
        persist_qualified_source=False,
    )

    assert "qualifiedHomepageSource" not in targets[0]
    assert report["sourceQualification"]["candidates"][0][
        "qualifiedVideoSource"
    ] == {
        "provider": "wikipedia",
        "title": "测试实体甲",
        "url": "https://commons.wikimedia.org/wiki/File:video",
    }


def test_video_source_ready_priority_fills_oversample_pool(
    tmp_path: Path,
) -> None:
    path = tmp_path / "视频过采市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "甲区",
                        "leaves": [
                            {
                                "name": f"视频景区{index}",
                                "canonicalName": f"视频景区{index}",
                                "entityType": "地点/景区",
                                "geoTagRef": f"Topic/地理/行政区/中国/test-region-a/甲区/{index}",
                                "typeTagRefs": ["Entity/地点/景区/4A景区"],
                            }
                            for index in range(1, 6)
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    def qualify(target: TargetSourceCandidate) -> TargetSourceQualification:
        calls.append(target.name)
        if target.name in {"视频景区1", "视频景区2"}:
            return TargetSourceQualification(
                True,
                QualifiedHomepageSource(
                    provider=HomepageAuthorityProvider.WIKIPEDIA,
                    title=target.name,
                    url=f"https://commons.wikimedia.org/wiki/File:{target.name}",
                ),
            )
        return TargetSourceQualification(
            False,
            None,
            rejection_code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        )

    targets, report = select_targets(
        discovery_path=path,
        limit=5,
        quota=2,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=qualify,
        qualification_source_key="qualifiedVideoSource",
        persist_qualified_source=False,
    )

    assert len(targets) == 5
    assert [item["name"] for item in targets[:2]] == ["视频景区1", "视频景区2"]
    assert report["sourceQualification"]["acceptedCount"] == 2
    assert report["sourceQualification"]["oversampleFilled"] == 3
    # Qualification may overshoot by one worker batch, but must include the
    # accepted quota and must not evaluate the entire reference set.
    assert {"视频景区1", "视频景区2"}.issubset(set(calls))
    assert "视频景区5" not in calls


def test_retry_inherit_frozen_targets_skips_source_requalification(
    tmp_path: Path,
) -> None:
    path = tmp_path / "继承冻结市.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "甲区",
                        "leaves": [
                            {
                                "name": "继承景区甲",
                                "canonicalName": "继承景区甲",
                                "entityType": "地点/景区",
                                "geoTagRef": "Topic/地理/行政区/中国/test-region-a/甲区",
                                "typeTagRefs": ["Entity/地点/景区/5A景区"],
                            },
                            {
                                "name": "继承景区乙",
                                "canonicalName": "继承景区乙",
                                "entityType": "地点/宗教场所",
                                "geoTagRef": "Topic/地理/行政区/中国/test-region-a/甲区",
                                "typeTagRefs": ["Entity/地点/景区/4A景区"],
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

    def qualify(_target: TargetSourceCandidate) -> TargetSourceQualification:
        raise AssertionError("inherited frozen targets must not re-qualify")

    inherited_targets = (
        {
            "name": "继承景区乙",
            "canonicalName": "继承景区乙",
            "entityType": "地点/宗教场所",
            "geoTagRef": "Topic/地理/行政区/中国/test-region-a/甲区",
            "typeTagRefs": ["Entity/地点/景区/4A景区"],
            "qualifiedHomepageSource": {
                "provider": "wikipedia",
                "title": "继承景区乙",
                "url": "https://zh.wikipedia.org/wiki/继承景区乙",
            },
        },
        {
            "name": "继承景区甲",
            "canonicalName": "继承景区甲",
            "entityType": "地点/景区",
            "geoTagRef": "Topic/地理/行政区/中国/test-region-a/甲区",
            "typeTagRefs": ["Entity/地点/景区/5A景区"],
            "qualifiedHomepageSource": {
                "provider": "wikipedia",
                "title": "继承景区甲",
                "url": "https://zh.wikipedia.org/wiki/继承景区甲",
            },
        },
    )

    targets, report = select_targets(
        discovery_path=path,
        limit=2,
        quota=2,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=qualify,
        target_names=("继承景区乙", "继承景区甲"),
        inherit_frozen_targets=True,
        persist_qualified_source=False,
        inherited_targets=inherited_targets,
        category="景区",
    )

    assert [item["name"] for item in targets] == ["继承景区乙", "继承景区甲"]
    assert report["strategy"] == "inherited frozen target order"
    assert report["inheritedFrozenTargets"] is True
    assert "sourceQualification" not in report
    assert targets[0]["qualifiedHomepageSource"]["title"] == "继承景区乙"


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
