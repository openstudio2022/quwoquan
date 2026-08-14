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


def test_source_ready_priority_accepts_shared_wave_target_names_above_pool(
    tmp_path: Path,
) -> None:
    """四载体共享大名单可超过小载体候选池上限，只交付 quota 个。"""
    path = tmp_path / "共享名单来源预选市.yaml"
    names = tuple(f"共享对象{index}" for index in range(6))
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "测试区",
                        "leaves": [
                            {"name": name, "selectionPriority": index + 1}
                            for index, name in enumerate(names)
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
        return TargetSourceQualification(
            True,
            QualifiedHomepageSource(
                provider=HomepageAuthorityProvider.WIKIPEDIA,
                title=target.name,
                url=f"https://commons.wikimedia.org/wiki/File:{target.name}",
            ),
        )

    # len(names)=6 > limit=2：共享名单是预期形态，不得整体拒绝。
    targets, report = select_targets(
        discovery_path=path,
        limit=2,
        quota=1,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=qualify,
        qualification_source_key="qualifiedVideoSource",
        persist_qualified_source=False,
        target_names=names,
    )

    assert len(targets) <= 2
    assert report["approvedQuota"] == 1
    assert report["requestedTargetNames"] == list(names)


def test_source_ready_priority_rejects_target_names_below_quota(
    tmp_path: Path,
) -> None:
    """名单收缩到 quota 之下仍然 fail-closed。"""
    path = _coverage_file(tmp_path / "配额下限来源预选市.yaml")

    with pytest.raises(ValueError, match="must reach the approved --quota"):
        select_targets(
            discovery_path=path,
            limit=3,
            quota=2,
            target_selector=TargetSelector.SOURCE_READY_PRIORITY,
            source_qualifier=lambda target: TargetSourceQualification(
                True,
                QualifiedHomepageSource(
                    provider=HomepageAuthorityProvider.WIKIPEDIA,
                    title=target.name,
                    url=f"https://zh.wikipedia.org/wiki/{target.name}",
                ),
            ),
            target_names=("测试实体甲",),
        )


def _partial_supply_coverage_file(path: Path, count: int = 5) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "districts": [
                    {
                        "district": "甲区",
                        "leaves": [
                            {
                                "name": f"部分供给景区{index}",
                                "canonicalName": f"部分供给景区{index}",
                                "entityType": "地点/景区",
                                "geoTagRef": f"Topic/地理/行政区/中国/test-region-a/甲区/{index}",
                                "typeTagRefs": ["Entity/地点/景区/4A景区"],
                            }
                            for index in range(1, count + 1)
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


def _supply_qualifier(accepted_names: set[str]):
    def qualify(target: TargetSourceCandidate) -> TargetSourceQualification:
        if target.name in accepted_names:
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

    return qualify


def test_video_partial_supply_advances_with_typed_shortfall(tmp_path: Path) -> None:
    """非 persist lane（video）供给不足配额时以 typed shortfall 推进 partial 交付。"""
    path = _partial_supply_coverage_file(tmp_path / "部分供给市.yaml")

    targets, report = select_targets(
        discovery_path=path,
        limit=5,
        quota=3,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=_supply_qualifier({"部分供给景区1", "部分供给景区2"}),
        qualification_source_key="qualifiedVideoSource",
        persist_qualified_source=False,
    )

    assert [item["name"] for item in targets[:2]] == ["部分供给景区1", "部分供给景区2"]
    assert len(targets) == 5
    qualification = report["sourceQualification"]
    assert qualification["acceptedCount"] == 2
    assert qualification["approvedQuota"] == 3
    assert qualification["supplyShortfallCount"] == 1


def test_persist_lane_never_fills_selected_with_rejected_rows(tmp_path: Path) -> None:
    """persist lane（homepage）的 selected 只能是合格行。

    frozen coverage targets 逐行要求 qualifiedHomepageSource（spec_contract
    fail-closed）；accepted < limit 时用 rejected 行凑满 oversample 池会把
    不合格实体写进交付承诺（历史缺陷：M100 homepage lane 在 spec 冻结时
    ValueError: homepage execution targets require qualifiedHomepageSource）。
    """
    path = _partial_supply_coverage_file(tmp_path / "持久合格市.yaml")

    targets, report = select_targets(
        discovery_path=path,
        limit=5,
        quota=2,
        target_selector=TargetSelector.SOURCE_READY_PRIORITY,
        source_qualifier=_supply_qualifier({"部分供给景区1", "部分供给景区2", "部分供给景区3"}),
        qualification_source_key="qualifiedHomepageSource",
        persist_qualified_source=True,
    )

    assert [item["name"] for item in targets] == [
        "部分供给景区1",
        "部分供给景区2",
        "部分供给景区3",
    ]
    assert all(item.get("qualifiedHomepageSource") for item in targets)
    assert report["sourceQualification"]["oversampleFilled"] == 0


def test_video_zero_supply_still_fails_closed(tmp_path: Path) -> None:
    """非 persist lane 零供给仍必须 QUALIFICATION_EXHAUSTED，不允许空交付。"""
    path = _partial_supply_coverage_file(tmp_path / "零供给市.yaml")

    with pytest.raises(DataIssueError) as raised:
        select_targets(
            discovery_path=path,
            limit=5,
            quota=3,
            target_selector=TargetSelector.SOURCE_READY_PRIORITY,
            source_qualifier=_supply_qualifier(set()),
            qualification_source_key="qualifiedVideoSource",
            persist_qualified_source=False,
        )

    assert raised.value.issues[0].code is DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED


def test_homepage_below_quota_still_fails_closed(tmp_path: Path) -> None:
    """persist lane（homepage）qualification 是交付准入门，低于配额必须硬失败。"""
    path = _partial_supply_coverage_file(tmp_path / "主页配额市.yaml")

    with pytest.raises(DataIssueError) as raised:
        select_targets(
            discovery_path=path,
            limit=5,
            quota=3,
            target_selector=TargetSelector.SOURCE_READY_PRIORITY,
            source_qualifier=_supply_qualifier({"部分供给景区1", "部分供给景区2"}),
            persist_qualified_source=True,
        )

    issue = raised.value.issues[0]
    assert issue.code is DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED
    assert dict(issue.attributes)["acceptedCount"] == "2"


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
