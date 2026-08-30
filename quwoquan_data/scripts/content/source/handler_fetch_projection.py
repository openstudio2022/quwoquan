"""Project one fetched source into the rows that downstream evidence reads.

抓取阶段的循环里混着两类事：有副作用的落盘，和把已定结果换算成一行记录的纯投影。
后者一旦留在循环体内就没法单独验证，也会让 funnel 口径散落在各处。所以这里只放
投影：输入是已经拿到的 manifest / funnel / 资产列表，输出是一行确定的计数或一份
补全后的来源字典，不读磁盘、不写磁盘。

计数口径在这里收敛为一处：下载数按候选数减去抓取失败数得出，而拒绝数按候选数减
去接受数得出——一条被拒绝的来源整单不计入接受，因此它的候选全部落到拒绝侧。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.source.contracts import MediaProvenance

_RIGHTS_COUNT_FIELDS = (
    "verifiedAssetCount",
    "unverifiedAssetCount",
    "restrictedAssetCount",
    "unknownAssetCount",
)


def source_asset_count_row(
    *,
    source: Mapping[str, Any],
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    source_images: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    source_image_funnel: Mapping[str, Any],
    vertical: str,
) -> dict[str, Any]:
    """Count one source's assets by funnel stage and rights audit status."""
    candidate_count = int(source_image_funnel.get("candidateCount") or 0)
    accepted_count = (
        int(manifest.get("assetCount") or 0)
        if str(quality.get("quality") or "") != "Reject"
        else 0
    )
    fetch_failures = source_image_funnel.get("fetchFailures")
    downloaded_count = candidate_count - (
        len(fetch_failures) if isinstance(fetch_failures, list) else 0
    )
    rights_counts = dict.fromkeys(_RIGHTS_COUNT_FIELDS, 0)
    for image in source_images if accepted_count else ():
        status = MediaProvenance.from_mapping(
            image,
            vertical=vertical,
        ).rights_audit_status.value
        rights_counts[f"{status}AssetCount"] += 1
    return {
        "displayName": str(manifest.get("title") or source["source_id"]),
        "provider": str(manifest.get("platform") or "web"),
        "plannedAssetCount": candidate_count,
        "discoveredAssetCount": candidate_count,
        "downloadedAssetCount": max(0, downloaded_count),
        "acceptedAssetCount": accepted_count,
        "rejectedAssetCount": max(0, candidate_count - accepted_count),
        **rights_counts,
    }


def source_with_observed_fetch_runtime(
    source: Mapping[str, Any],
    *,
    fetch_runtime: Mapping[str, Any],
) -> dict[str, Any]:
    """Overlay what the fetch actually observed onto the planned source.

    计划里的标题与 URL 是请求意图，重定向后的落点才是这次抓取的事实。落盘的来源单元
    要能自证读了哪一页，所以观测值覆盖计划值，而不是并列保留两套。
    """
    projected = dict(source)
    for key in ("requestedTitle", "resolvedTitle", "redirectChain", "fetchFinalUrl"):
        if key in fetch_runtime:
            projected["finalUrl" if key == "fetchFinalUrl" else key] = fetch_runtime[key]
    return projected


__all__ = [
    "source_asset_count_row",
    "source_with_observed_fetch_runtime",
]
