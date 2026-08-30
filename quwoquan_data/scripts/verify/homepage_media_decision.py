"""Download-time closure of homepage page-image dispositions (DEC-029).

Everything here is decidable the moment `1.download` closes: it reads the source
unit's asset funnel, `assets/index.json` and the frozen dispositions, and never a
manifest or a page body. Whether materialization honoured those outcomes is the
separate concern owned by `homepage_media_fulfillment`.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from core.data_issue import DataIssue, DataIssueCode
from core.page_media import (
    HomepageAssetDisposition,
    PageImageDropCode,
    is_image_dimension_token,
)
from verify.homepage_media_issue import issue as _issue, mapping_rows as _mapping_rows

_CAP_REASON_RE = re.compile(r"capReached|maxKeptPerSource|group_aware", re.IGNORECASE)

PUBLISHED_DISPOSITIONS = frozenset(
    {
        HomepageAssetDisposition.COVER.value,
        HomepageAssetDisposition.INLINE.value,
        HomepageAssetDisposition.RELATED.value,
    }
)


def funnel_issues(
    source_ref: str,
    meta: Mapping[str, Any],
    index_assets: list[dict[str, Any]],
) -> list[DataIssue]:
    """来源页图片必须全部归因：下载、策略排除或去重，且不得被配额截断。"""

    issues: list[DataIssue] = []
    funnel = meta.get("assetFunnel") if isinstance(meta.get("assetFunnel"), Mapping) else {}
    candidate_count = int(funnel.get("candidateCount") or 0)
    kept_count = int(funnel.get("keptCount") or 0)
    drops = _mapping_rows(funnel.get("drops"))
    dropped_count = int(funnel.get("droppedCount") or 0)
    dedupe_removed = int(funnel.get("dedupeRemoved") or 0)
    if _CAP_REASON_RE.search(json.dumps(funnel, ensure_ascii=False)):
        issues.append(
            _issue(
                DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
                "页面图片存在数量上限或配额截断",
                ref=source_ref,
                attrs={"candidateCount": candidate_count, "keptCount": kept_count},
            )
        )
    if candidate_count != kept_count + dropped_count:
        issues.append(
            _issue(
                DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
                "图片漏失未被下载或策略排除归因",
                ref=source_ref,
                attrs={
                    "candidateCount": candidate_count,
                    "keptCount": kept_count,
                    "droppedCount": dropped_count,
                },
            )
        )
    if kept_count != len(index_assets):
        issues.append(
            _issue(
                DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
                "asset funnel keptCount 与 assets/index.json 不一致",
                ref=source_ref,
                attrs={"keptCount": kept_count, "indexCount": len(index_assets)},
            )
        )
    if dropped_count != len(drops) or dedupe_removed > dropped_count:
        issues.append(
            _issue(
                DataIssueCode.CONTRACT_INVALID,
                "asset funnel 丢弃计数与终态记录不一致",
                ref=source_ref,
                attrs={
                    "droppedCount": dropped_count,
                    "dropRecordCount": len(drops),
                    "dedupeRemoved": dedupe_removed,
                },
            )
        )
    issues.extend(_drop_issues(source_ref, drops))
    return issues


def _drop_issues(source_ref: str, drops: list[dict[str, Any]]) -> list[DataIssue]:
    issues: list[DataIssue] = []
    for drop in drops:
        raw_code = str(drop.get("code") or "")
        reason = str(drop.get("reason") or "")
        try:
            code = PageImageDropCode(raw_code)
        except ValueError:
            issues.append(
                _issue(
                    DataIssueCode.CONTRACT_INVALID,
                    "图片丢弃缺少稳定闭集代码",
                    ref=source_ref,
                    attrs={"code": raw_code, "reason": reason[:240]},
                )
            )
            continue
        if not reason:
            issues.append(
                _issue(
                    DataIssueCode.CONTRACT_INVALID,
                    "图片丢弃缺少可审计说明",
                    ref=source_ref,
                    attrs={"code": code.value},
                )
            )
        if not code.is_policy_outcome:
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
                    "页面图片下载未闭合",
                    ref=source_ref,
                    attrs={"code": code.value, "reason": reason[:240]},
                )
            )
    return issues


def disposition_issues(
    source_ref: str,
    index_assets: list[dict[str, Any]],
    dispositions: Mapping[str, list[dict[str, Any]]],
) -> list[DataIssue]:
    """Every downloaded image must carry exactly one legal outcome."""

    found = [_disposition_issue(source_ref, asset, dispositions) for asset in index_assets]
    return [item for item in found if item is not None]


def _disposition_issue(
    source_ref: str,
    asset: Mapping[str, Any],
    dispositions: Mapping[str, list[dict[str, Any]]],
) -> DataIssue | None:
    """The single terminal verdict owed by one indexed download, if it is missing."""

    file_name = str(asset.get("fileName") or "").strip()
    if not file_name:
        return _issue(
            DataIssueCode.CONTRACT_INVALID,
            "assets/index.json 缺少 fileName，无法闭合页面图片处置",
            ref=source_ref,
            attrs={"sourceAssetId": str(asset.get("sourceAssetId") or "")},
        )
    source_asset_ref = f"sources/{source_ref}/assets/{file_name}"
    outcomes = dispositions.get(source_asset_ref, [])
    if len(outcomes) != 1:
        return _issue(
            DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
            "下载图片没有且只能有一个发布处置",
            ref=source_ref,
            attrs={"sourceAssetRef": source_asset_ref, "outcomeCount": len(outcomes)},
        )
    outcome = outcomes[0]
    disposition = str(outcome.get("disposition") or "")
    asset_id = str(outcome.get("assetId") or "")
    if disposition not in {item.value for item in HomepageAssetDisposition} or not str(
        outcome.get("reason") or ""
    ):
        return _issue(
            DataIssueCode.CONTRACT_INVALID,
            "页面图片处置不符合闭集合同",
            ref=source_ref,
            attrs={"sourceAssetRef": source_asset_ref, "disposition": disposition},
        )
    published = disposition in PUBLISHED_DISPOSITIONS
    if published and not asset_id:
        return _issue(
            DataIssueCode.CONTRACT_INVALID,
            "发布处置必须冻结 assetId",
            ref=source_ref,
            attrs={"sourceAssetRef": source_asset_ref, "disposition": disposition},
        )
    if not published and asset_id:
        return _issue(
            DataIssueCode.CONTRACT_INVALID,
            "策略排除或重复别名图片不得指向发布资产",
            ref=source_ref,
            attrs={"sourceAssetRef": source_asset_ref, "assetId": asset_id},
        )
    return None


def placement_caption_issues(
    source_ref: str,
    placements: list[dict[str, Any]],
) -> list[DataIssue]:
    return [
        _issue(
            DataIssueCode.MEDIA_CAPTION_INVALID,
            "source placement 图注是尺寸参数",
            ref=source_ref,
            attrs={
                "fileName": placement.get("fileName") or "",
                "caption": str(placement.get("caption") or "").strip(),
            },
        )
        for placement in placements
        if str(placement.get("caption") or "").strip()
        and is_image_dimension_token(str(placement.get("caption") or "").strip())
    ]
