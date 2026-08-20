# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t7
"""download_fetch 的局部失败必须是 typed exclusion，而不是静默丢弃或整批失败。

`REQ-003`：「单 Provider 或 shard 的 typed failure 只阻断自身，不阻断同 carrier
其他来源。」`GWT-006`：「无法映射或歧义的单资产写 typed exclusion，局部 source/safety
失败只形成该 workUnit shortfall。仍有至少一个真实对象时继续 partial，零对象才
blocked。」

因此 download_fetch 阶段的每一次局部失败都必须同时满足三条：

1. 留下可机器消费的 typed 证据（stable code + stage + ref + recovery），失败不得
   退化为空返回或静默跳过；
2. 处置粒度显式落在被排除的那一个对象上（实体级 `excluded`、来源级
   `source_rejected`），不扩散到兄弟对象；
3. 编排分支只读 code/recovery，不解析 message。
"""
from __future__ import annotations

import pytest
from content.source.handler_fetch_contract import (
    source_fetch_failure_issue,
    source_unit_write_failure_issue,
)
from content.source.handler_fetch_failure import entity_fetch_issue
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueError,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    issues_for_ref,
)


def _source(
    source_id: str,
    *,
    research_lane: str = "homepage",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "url": f"https://example.test/{source_id}",
        "researchLane": research_lane,
        "platform": "web",
        "category": "web",
        "sourceKind": "tourism_site",
        "articleSiteId": f"site-{source_id}",
    }


def test_entity_fetch_failure_is_a_typed_exclusion_naming_the_excluded_entity() -> None:
    """被排除的实体必须留下 typed 证据，并显式声明处置为 excluded。"""

    issue = entity_fetch_issue(
        "峨眉山",
        OSError("source adapter timed out"),
        selected_lanes={"homepage"},
    )

    assert issue.code is DataIssueCode.SOURCE_UNREADABLE
    assert issue.stage is DataIssueStage.DOWNLOAD_FETCH
    assert issue.ref == "峨眉山"
    assert issue.lane is DataIssueLane.HOMEPAGE
    assert issue.recovery is DataRecoveryAction.RETRY_SOURCE_DISCOVERY
    assert dict(issue.attributes)["disposition"] == "excluded"
    assert dict(issue.attributes)["errorType"] == "OSError"


def test_typed_exclusion_survives_the_wire_contract_without_losing_disposition() -> None:
    """typed exclusion 必须能通过 `_common/data_issue` 契约落盘并原样取回。"""

    issue = entity_fetch_issue(
        "西湖",
        TimeoutError("upstream stalled"),
        selected_lanes={"video"},
    )
    payload = issue.as_dict()

    assert payload["code"] == "DATA.SOURCE.UNREADABLE"
    assert payload["stage"] == "download_fetch"
    assert payload["ref"] == "西湖"
    assert payload["lane"] == "video"
    assert payload["recovery"] == "retry_source_discovery"
    assert payload["attrs"]["disposition"] == "excluded"
    assert DataIssue.from_dict(payload) == issue


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ValueError("contract violated"), DataIssueCode.CONTRACT_INVALID),
        (TypeError("wrong shape"), DataIssueCode.CONTRACT_INVALID),
        (OSError("socket closed"), DataIssueCode.SOURCE_UNREADABLE),
        (TimeoutError("read timeout"), DataIssueCode.SOURCE_UNREADABLE),
        (RuntimeError("unexpected"), DataIssueCode.INTERNAL_UNEXPECTED),
    ],
)
def test_exclusion_code_is_derived_from_the_cause_not_collapsed_to_one_value(
    error: Exception,
    expected: DataIssueCode,
) -> None:
    """运营动作由 code 决定，因此不同成因不得塌陷成同一个笼统 code。"""

    issue = entity_fetch_issue("青城山", error, selected_lanes=None)

    assert issue.code is expected
    assert issue.recovery is DataRecoveryAction.RETRY_SOURCE_DISCOVERY


@pytest.mark.parametrize(
    ("selected_lanes", "expected"),
    [
        ({"homepage"}, DataIssueLane.HOMEPAGE),
        ({"article"}, DataIssueLane.ARTICLE),
        ({"image"}, DataIssueLane.IMAGE),
        ({"video"}, DataIssueLane.VIDEO),
        ({"homepage", "article"}, DataIssueLane.ALL),
        (None, DataIssueLane.ALL),
    ],
)
def test_exclusion_lane_reports_the_selected_lane_without_guessing_one(
    selected_lanes: set[str] | None,
    expected: DataIssueLane,
) -> None:
    """单载体运行的排除归属该 lane；多载体或未选定不得挑一个 lane 冒充。"""

    issue = entity_fetch_issue("千岛湖", OSError("boom"), selected_lanes=selected_lanes)

    assert issue.lane is expected


def test_one_failed_entity_leaves_its_siblings_without_any_issue() -> None:
    """`REQ-003`：局部 typed failure 只阻断自身；兄弟实体不得因此被标记。"""

    issues = [
        entity_fetch_issue("峨眉山", OSError("adapter down"), selected_lanes={"homepage"}),
    ]

    assert [issue.ref for issue in issues] == ["峨眉山"]
    assert issues_for_ref(issues, "峨眉山") == issues
    assert issues_for_ref(issues, "西湖") == []
    assert issues_for_ref(issues, "青城山") == []


def test_partial_batch_reports_every_excluded_ref_across_one_typed_boundary() -> None:
    """整批不得因局部失败塌陷：每个被排除 ref 各自带 typed 证据穿过边界。"""

    excluded = ["峨眉山", "青城山"]
    issues = [
        entity_fetch_issue(ref, OSError(f"{ref} adapter down"), selected_lanes={"homepage"})
        for ref in excluded
    ]

    error = DataIssueError(issues)

    assert [issue.ref for issue in error.issues] == excluded
    assert all(issue.code is DataIssueCode.SOURCE_UNREADABLE for issue in error.issues)
    assert all(
        dict(issue.attributes)["disposition"] == "excluded" for issue in error.issues
    )


def test_a_failure_can_never_cross_the_boundary_as_an_empty_issue_set() -> None:
    """失败不得降级为「在场为空」：typed 边界必须至少携带一条 issue。"""

    with pytest.raises(ValueError, match="requires at least one DataIssue"):
        DataIssueError([])


def test_a_silent_exception_still_produces_a_locatable_typed_exclusion() -> None:
    """空 message 的异常同样必须产出可定位的 typed 证据，不得静默丢弃。"""

    issue = entity_fetch_issue("莫干山", RuntimeError(), selected_lanes={"homepage"})

    assert issue.ref == "莫干山"
    assert issue.code is DataIssueCode.INTERNAL_UNEXPECTED
    assert dict(issue.attributes)["errorType"] == "RuntimeError"
    assert issue.message.strip()
    assert issue.as_dict()["attrs"]["disposition"] == "excluded"


def test_an_oversized_failure_detail_still_fits_the_typed_contract() -> None:
    """超长上游报文不得让 typed 证据本身失效，否则失败会退化为无证据。"""

    issue = entity_fetch_issue(
        "雁荡山",
        OSError("x" * 5_000),
        selected_lanes={"homepage"},
    )

    assert issue.as_dict()["attrs"]["disposition"] == "excluded"
    assert len(issue.message) < 5_000


def test_one_unreadable_source_is_rejected_without_excluding_its_entity() -> None:
    """来源级失败的处置是 source_rejected，实体保留其余已计划来源。"""

    issue = source_fetch_failure_issue(
        _source("baike-1"),
        entity_id="峨眉山",
        error=OSError("adapter returned no payload"),
    )

    assert issue.code is DataIssueCode.SOURCE_UNREADABLE
    assert issue.stage is DataIssueStage.DOWNLOAD_FETCH
    assert issue.ref == "峨眉山"
    assert issue.lane is DataIssueLane.HOMEPAGE
    assert issue.recovery is DataRecoveryAction.RETRY_SOURCE_DISCOVERY
    assert dict(issue.attributes)["sourceId"] == "baike-1"
    assert "excluded" not in dict(issue.attributes).values()
    assert issue.as_dict()["attrs"]["sourceId"] == "baike-1"


def test_one_uncompliant_source_unit_is_rejected_source_scoped() -> None:
    """写不出合规单元的那一条来源只丢自己，且必须说明换来源。"""

    issue = source_unit_write_failure_issue(
        _source("attribution-missing", research_lane="article"),
        entity_id="峨眉山",
        error=ValueError("source attribution is unregistered"),
    )

    attributes = dict(issue.attributes)

    assert issue.code is DataIssueCode.SOURCE_PLAN_INVALID
    assert issue.stage is DataIssueStage.DOWNLOAD_FETCH
    assert issue.ref == "峨眉山"
    assert issue.lane is DataIssueLane.ARTICLE
    assert issue.recovery is DataRecoveryAction.REPLACE_SOURCE
    assert attributes["disposition"] == "source_rejected"
    assert attributes["sourceId"] == "attribution-missing"
    assert attributes["errorType"] == "ValueError"


def test_source_and_entity_dispositions_are_two_distinguishable_typed_states() -> None:
    """来源级拒绝与实体级排除必须可区分，否则运营者无法判断修哪一层。"""

    source_issue = source_fetch_failure_issue(
        _source("baike-1"),
        entity_id="峨眉山",
        error=OSError("adapter returned no payload"),
    )
    unit_issue = source_unit_write_failure_issue(
        _source("baike-2"),
        entity_id="峨眉山",
        error=ValueError("manifest schema violation"),
    )
    entity_issue = entity_fetch_issue(
        "峨眉山",
        OSError("adapter returned no payload"),
        selected_lanes={"homepage"},
    )

    assert dict(unit_issue.attributes)["disposition"] == "source_rejected"
    assert dict(entity_issue.attributes)["disposition"] == "excluded"
    assert "disposition" not in dict(source_issue.attributes)
    assert dict(source_issue.attributes)["sourceId"]
    assert entity_issue.ref == unit_issue.ref == source_issue.ref == "峨眉山"


def test_an_unknown_research_lane_falls_back_to_all_without_raising() -> None:
    """来源上的 lane 取值异常不得让 typed 证据构造本身失败。"""

    issue = source_fetch_failure_issue(
        _source("legacy", research_lane="legacy-lane"),
        entity_id="峨眉山",
        error=OSError("adapter down"),
    )

    assert issue.lane is DataIssueLane.ALL
