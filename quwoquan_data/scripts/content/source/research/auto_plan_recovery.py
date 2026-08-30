"""Forced plan invalidation and bounded homepage source-plan recovery."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.carrier_contract import research_plan_files
from core.data_issue import (
    DataIssue,
    DataIssueCode, DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json
from core.paths import STAGE_DOWNLOAD
from content.source.prepare import resolve_research_entity_types
from content.source.source_unit import resolve_entity_object_dir

from content.source.research import network_breaker
from content.source.research.auto_plan_report import _merge_auto_reports
from content.source.research.auto_plan_writer import _write_auto_research_plans_impl
from content.source.research.network_io import NetworkFetchError
from content.source.research.plan_state import _plan_has_payload


def _invalidate_forced_lane_plans(
    execution_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    lanes: set[str],
) -> None:
    """Remove stale consumable plans before a forced source-contract rebuild."""
    resolved_types = resolve_research_entity_types(
        execution_id,
        entity_ids,
        fallback_type=entity_type,
    )
    filenames = research_plan_files()
    for entity_id in entity_ids:
        object_dir = resolve_entity_object_dir(
            execution_id,
            entity_id,
            etype_hint=resolved_types[entity_id],
        )
        for lane in lanes:
            filename = filenames.get(lane)
            if filename:
                (object_dir / STAGE_DOWNLOAD / filename).unlink(missing_ok=True)


def _homepage_source_plan_missing_entity_ids(
    execution_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
) -> list[str]:
    """Return homepage targets whose current plan has no encyclopedia source.

    The initial parallel pass favors throughput. A source plan with no homepage
    source can result from a transient provider response, so it receives the
    bounded recovery pass declared by the runtime policy before Agent repair is
    considered. This reads the current plan, never a report diagnostic.
    """
    resolved_types = resolve_research_entity_types(
        execution_id,
        entity_ids,
        fallback_type=entity_type,
    )
    filename = research_plan_files()["homepage"]
    missing: list[str] = []
    for entity_id in entity_ids:
        object_dir = resolve_entity_object_dir(
            execution_id,
            entity_id,
            etype_hint=resolved_types[entity_id],
        )
        # 与 `_write_lane` 共用同一个「计划是否已有内容」判据：两处若各自判定，
        # 恢复会把写入方认为已完成的计划反复重跑。
        if not _plan_has_payload(
            read_json(object_dir / STAGE_DOWNLOAD / filename),
            "homepage",
        ):
            missing.append(entity_id)
    return missing


def _discard_recovered_homepage_source_issues(
    report: dict[str, Any],
    *,
    recovered_entity_ids: set[str],
) -> None:
    """Discard only superseded homepage primary-source absence diagnostics."""
    retained: list[dict[str, Any]] = []
    for raw in report.get("sourceUnavailable") or []:
        if not isinstance(raw, dict):
            raise TypeError("sourceUnavailable rows must use DataIssue objects")
        issue = DataIssue.from_dict(raw)
        if (
            issue.ref in recovered_entity_ids
            and issue.lane is DataIssueLane.HOMEPAGE
            and issue.code is DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING
        ):
            continue
        retained.append(raw)
    report["sourceUnavailable"] = retained


def _network_failure_entity_result(
    entity_id: str,
    exc: NetworkFetchError,
) -> dict[str, Any]:
    """Render one entity's outcome when its source discovery never completed.

    上游拒绝或限流是基础设施失败，不是「该实体无可用来源」。落到网络码才能让重试与
    预筛把它同不合格候选区分开，也才不会让一个实体的出口故障中断整批探测。
    """
    return {
        "updated": [],
        "issues": [f"{entity_id}: source discovery network failure: {exc}"],
        "candidates": [],
        "imageCollections": [],
        "sourceUnavailable": [
            data_issue(
                DataIssueCode.NETWORK_UNREACHABLE,
                stage=DataIssueStage.DOWNLOAD_PLAN,
                ref=entity_id,
                lane=DataIssueLane.ALL,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                message="source research outbound fetch did not complete",
                attributes={
                    "statusCode": str(exc.status_code),
                    "curlExit": str(exc.returncode),
                    "reason": exc.reason,
                },
            ).as_dict()
        ],
    }


def _recover_homepage_source_plans(
    execution_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    recovery_passes: int,
    report: dict[str, Any],
    external_input_context: Any | None = None,
) -> list[str]:
    """Replay only empty homepage plans within the declared recovery passes."""
    recovered: list[str] = []
    for _ in range(recovery_passes):
        unresolved = _homepage_source_plan_missing_entity_ids(
            execution_id,
            entity_ids,
            entity_type=entity_type,
        )
        if not unresolved:
            break
        _invalidate_forced_lane_plans(
            execution_id,
            unresolved,
            entity_type=entity_type,
            lanes={"homepage"},
        )
        network_breaker.BREAKER.reset()
        with ThreadPoolExecutor(max_workers=len(unresolved)) as executor:
            future_entity_ids = {
                executor.submit(
                    _write_auto_research_plans_impl,
                    execution_id,
                    [entity_id],
                    entity_type=entity_type,
                    force=True,
                    lanes={"homepage"},
                    write_shared_report=False,
                    external_input_context=external_input_context,
                ): entity_id
                for entity_id in unresolved
            }
            futures = list(future_entity_ids)
            for future in as_completed(futures):
                entity_id = future_entity_ids[future]
                try:
                    _merge_auto_reports(report, future.result())
                except NetworkFetchError as exc:
                    # 恢复是一次尝试，不是承诺。出口故障让该实体留在 unresolved 由上层
                    # 按既有缺失语义处理，而不该把同一批里其它实体的恢复一起带走。
                    _merge_auto_reports(
                        report,
                        _network_failure_entity_result(entity_id, exc),
                    )
        still_unresolved = set(
            _homepage_source_plan_missing_entity_ids(
                execution_id,
                unresolved,
                entity_type=entity_type,
            )
        )
        newly_recovered = [entity_id for entity_id in unresolved if entity_id not in still_unresolved]
        recovered.extend(newly_recovered)
        if newly_recovered:
            _discard_recovered_homepage_source_issues(
                report,
                recovered_entity_ids=set(newly_recovered),
            )
    return recovered
