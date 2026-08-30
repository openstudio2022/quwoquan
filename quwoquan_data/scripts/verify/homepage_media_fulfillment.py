"""Post-materialization reconciliation of homepage media (DEC-029).

This is an audit, never a second decision. A published outcome with no manifest
asset means materialization dropped an image it was told to publish; a manifest
asset with no outcome means it published one nobody decided on. Both directions
fail closed, which is what makes the frozen dispositions the single decision point.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from core.data_issue import DataIssue, DataIssueCode
from core.page_media import (
    is_image_dimension_token,
    normalized_subject_core,
    normalized_subject_key,
    subject_keys_conflict,
)
from verify.homepage_media_decision import PUBLISHED_DISPOSITIONS
from verify.homepage_media_issue import issue as _issue, mapping_rows as _mapping_rows

_ASSET_REF_RE = re.compile(r"asset://([^\s,\"')]+)")
_COVER_DIMENSION_RE = re.compile(r"(?:^|_)cover_(?:x?\d+|\d+[x×]\d+)px(?:_|$)", re.I)


def _subject_core(caption: str, file_name: str, entity_name: str) -> str:
    return normalized_subject_core(
        normalized_subject_key(caption, file_name),
        entity_name=entity_name,
    )


def reconciliation_issues(
    source_ref: str,
    index_assets: list[dict[str, Any]],
    dispositions: Mapping[str, list[dict[str, Any]]],
    published_source_assets: set[str],
) -> list[DataIssue]:
    """Both differences between the manifest and the frozen dispositions."""

    issues: list[DataIssue] = []
    decided_refs: set[str] = set()
    for asset in index_assets:
        file_name = str(asset.get("fileName") or "").strip()
        if not file_name:
            continue
        source_asset_ref = f"sources/{source_ref}/assets/{file_name}"
        outcomes = dispositions.get(source_asset_ref, [])
        if len(outcomes) != 1:
            continue
        decided_refs.add(source_asset_ref)
        outcome = outcomes[0]
        if str(outcome.get("disposition") or "") not in PUBLISHED_DISPOSITIONS:
            continue
        if source_asset_ref not in published_source_assets:
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
                    "已发布图片没有对应主页 manifest 资产",
                    ref=source_ref,
                    attrs={
                        "sourceAssetRef": source_asset_ref,
                        "assetId": str(outcome.get("assetId") or ""),
                    },
                )
            )
    prefix = f"sources/{source_ref}/assets/"
    issues.extend(
        _issue(
            DataIssueCode.CONTRACT_INVALID,
            "主页 manifest 发布了没有冻结处置的图片",
            ref=source_ref,
            attrs={"sourceAssetRef": ref},
        )
        for ref in sorted(published_source_assets - decided_refs)
        if ref.startswith(prefix)
    )
    return issues


def manifest_issues(
    entity_name: str,
    manifest: Mapping[str, Any],
    page_text: str,
) -> list[DataIssue]:
    """封面唯一性、视觉主题冲突与图注污染——只在成品在场时可判定。"""

    issues: list[DataIssue] = []
    assets = _mapping_rows(manifest.get("assets"))
    invalid_roles = sorted(
        {str(row.get("role") or "") for row in assets} - {"cover", "inline", "related"}
    )
    if invalid_roles:
        issues.append(
            _issue(
                DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
                "主页资产存在未归一角色",
                ref=entity_name,
                attrs={"roles": ",".join(invalid_roles)},
            )
        )
    if not assets:
        return issues
    covers = [row for row in assets if row.get("role") == "cover"]
    if len(covers) != 1:
        issues.append(
            _issue(
                DataIssueCode.MEDIA_COVER_CONFLICT,
                "主页必须且只能有一个封面",
                ref=entity_name,
                attrs={"coverCount": len(covers)},
            )
        )
        return issues
    issues.extend(_cover_issues(entity_name, assets, covers[0], page_text))
    issues.extend(_caption_issues(entity_name, assets))
    return issues


def _cover_issues(
    entity_name: str,
    assets: list[dict[str, Any]],
    cover: Mapping[str, Any],
    page_text: str,
) -> list[DataIssue]:
    issues: list[DataIssue] = []
    cover_id = str(cover.get("assetId") or "")
    if cover_id in _ASSET_REF_RE.findall(page_text.split("---\n", 2)[-1]):
        issues.append(
            _issue(
                DataIssueCode.MEDIA_COVER_CONFLICT,
                "coverImage 被正文或相关图片区重复引用",
                ref=entity_name,
                attrs={"assetId": cover_id},
            )
        )
    cover_subject = _subject_core(
        str(cover.get("caption") or ""),
        str(cover.get("fileName") or ""),
        entity_name,
    )
    issues.extend(_group_member_issues(entity_name, assets, cover))
    for asset in assets:
        if asset is cover:
            continue
        subject = _subject_core(
            str(asset.get("caption") or ""),
            str(asset.get("fileName") or ""),
            entity_name,
        )
        if subject_keys_conflict(cover_subject, subject, entity_name=entity_name):
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_COVER_CONFLICT,
                    "封面与正文/相关图片使用同一视觉主题",
                    ref=entity_name,
                    attrs={"cover": cover_id, "assetId": asset.get("assetId") or ""},
                )
            )
    return issues


def _group_member_issues(
    entity_name: str,
    assets: list[dict[str, Any]],
    cover: Mapping[str, Any],
) -> list[DataIssue]:
    """图集成员只能进相关图片区，不能混入正文或占据封面。"""

    return [
        _issue(
            DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
            "groupMember 必须归入相关图片",
            ref=entity_name,
            attrs={"assetId": asset.get("assetId") or ""},
        )
        for asset in assets
        if asset is not cover
        and str(asset.get("placementType") or "") == "groupMember"
        and asset.get("role") != "related"
    ]


def _caption_issues(entity_name: str, assets: list[dict[str, Any]]) -> list[DataIssue]:
    issues: list[DataIssue] = []
    for asset in assets:
        caption = str(asset.get("caption") or "").strip()
        asset_id = str(asset.get("assetId") or "")
        if caption and is_image_dimension_token(caption):
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_CAPTION_INVALID,
                    "图片尺寸参数被错误保存为图注",
                    ref=entity_name,
                    attrs={"assetId": asset_id, "caption": caption},
                )
            )
        if _COVER_DIMENSION_RE.search(asset_id):
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_CAPTION_INVALID,
                    "封面 assetId 含尺寸伪图注",
                    ref=entity_name,
                    attrs={"assetId": asset_id},
                )
            )
    return issues


def scan_manifests(
    manifests: Mapping[str, tuple[Path, dict[str, Any]]],
) -> list[DataIssue]:
    issues: list[DataIssue] = []
    for entity_name, (manifest_path, manifest) in manifests.items():
        page_path = manifest_path.parent / "page.md"
        page_text = page_path.read_text(encoding="utf-8") if page_path.is_file() else ""
        issues.extend(manifest_issues(entity_name, manifest, page_text))
    return issues
