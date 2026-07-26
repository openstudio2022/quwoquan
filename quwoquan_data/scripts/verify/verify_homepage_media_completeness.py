#!/usr/bin/env python3
"""Verify source-page image enumeration, download and homepage disposition closure."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core import paths
from core.data_issue import DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, data_issue
from core.io import read_json, write_json
from core.page_media import (
    HomepageAssetDisposition,
    is_image_dimension_token,
    normalized_subject_core,
    normalized_subject_key,
    subject_keys_conflict,
)


_ASSET_REF_RE = re.compile(r"asset://([^\s,\"')]+)")
_CAP_REASON_RE = re.compile(r"capReached|maxKeptPerSource|group_aware", re.IGNORECASE)
_POLICY_REASON_RE = re.compile(
    r"license|rights|pixel|dimension|map|locator|unsupported|format|mime|duplicate|dedupe|safety|watermark|relevance",
    re.IGNORECASE,
)


def _issue(
    code: DataIssueCode,
    message: str,
    *,
    ref: str,
    attrs: Mapping[str, object] | None = None,
) -> DataIssue:
    return data_issue(
        code,
        stage=DataIssueStage.VERIFY_HOMEPAGE_MEDIA,
        ref=ref,
        message=message,
        recovery=DataRecoveryAction.STOP,
        attributes=attrs,
    )


def _mapping_rows(value: object) -> list[dict[str, Any]]:
    return [dict(row) for row in (value or []) if isinstance(row, Mapping)]


def _homepage_media_dispositions(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Index runtime disposition evidence by immutable source-asset reference."""

    rows: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(root.glob("entities/*/*/*/evidence/media_dispositions.json")):
        payload = read_json(path)
        for row in _mapping_rows(payload.get("assets")):
            source_asset_ref = str(row.get("sourceAssetRef") or "").strip()
            if source_asset_ref:
                rows.setdefault(source_asset_ref, []).append(row)
    return rows


def _disposition_issues(
    source_ref: str,
    index_assets: list[dict[str, Any]],
    dispositions: Mapping[str, list[dict[str, Any]]],
    published_source_assets: set[str],
) -> list[DataIssue]:
    """Every downloaded image must have one publish, policy, or dedupe outcome."""

    issues: list[DataIssue] = []
    allowed = {item.value for item in HomepageAssetDisposition}
    published = {
        HomepageAssetDisposition.COVER.value,
        HomepageAssetDisposition.INLINE.value,
        HomepageAssetDisposition.RELATED.value,
    }
    for asset in index_assets:
        file_name = str(asset.get("fileName") or "").strip()
        if not file_name:
            issues.append(
                _issue(
                    DataIssueCode.CONTRACT_INVALID,
                    "assets/index.json 缺少 fileName，无法闭合页面图片处置",
                    ref=source_ref,
                    attrs={"sourceAssetId": str(asset.get("sourceAssetId") or "")},
                )
            )
            continue
        source_asset_ref = f"sources/{source_ref}/assets/{file_name}"
        outcomes = dispositions.get(source_asset_ref, [])
        if len(outcomes) != 1:
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
                    "下载图片没有且只能有一个发布处置",
                    ref=source_ref,
                    attrs={"sourceAssetRef": source_asset_ref, "outcomeCount": len(outcomes)},
                )
            )
            continue
        outcome = outcomes[0]
        disposition = str(outcome.get("disposition") or "")
        reason = str(outcome.get("reason") or "")
        asset_id = str(outcome.get("assetId") or "")
        if disposition not in allowed or not reason:
            issues.append(
                _issue(
                    DataIssueCode.CONTRACT_INVALID,
                    "页面图片处置不符合闭集合同",
                    ref=source_ref,
                    attrs={"sourceAssetRef": source_asset_ref, "disposition": disposition},
                )
            )
            continue
        if disposition in published:
            if not asset_id or source_asset_ref not in published_source_assets:
                issues.append(
                    _issue(
                        DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
                        "已发布图片没有对应主页 manifest 资产",
                        ref=source_ref,
                        attrs={"sourceAssetRef": source_asset_ref, "assetId": asset_id},
                    )
                )
        elif asset_id:
            issues.append(
                _issue(
                    DataIssueCode.CONTRACT_INVALID,
                    "策略排除或重复别名图片不得指向发布资产",
                    ref=source_ref,
                    attrs={"sourceAssetRef": source_asset_ref, "assetId": asset_id},
                )
            )
    return issues


def _subject_core(caption: str, file_name: str, entity_name: str) -> str:
    return normalized_subject_core(
        normalized_subject_key(caption, file_name),
        entity_name=entity_name,
    )


def _entity_manifest_by_name(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    out: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted((root / "entities").glob("*/*/*/manifest.json")):
        out[path.parent.name] = (path, read_json(path))
    return out


def _funnel_issues(
    source_ref: str,
    placements: list[dict[str, Any]],
    meta: Mapping[str, Any],
    index_assets: list[dict[str, Any]],
) -> list[DataIssue]:
    issues: list[DataIssue] = []
    funnel = meta.get("assetFunnel") if isinstance(meta.get("assetFunnel"), Mapping) else {}
    candidate_count = int(funnel.get("candidateCount") or len(placements))
    kept_count = int(funnel.get("keptCount") or len(index_assets))
    drops = _mapping_rows(funnel.get("drops"))
    dropped_count = int(funnel.get("droppedCount") or len(drops))
    serialized_funnel = json.dumps(funnel, ensure_ascii=False)
    if _CAP_REASON_RE.search(serialized_funnel):
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
    for drop in drops:
        reason = str(drop.get("reason") or "")
        if not _POLICY_REASON_RE.search(reason):
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
                    "图片下载失败没有稳定策略归因",
                    ref=source_ref,
                    attrs={"reason": reason[:240]},
                )
            )
    return issues


def _manifest_issues(
    entity_name: str,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    page_text: str,
) -> list[DataIssue]:
    issues: list[DataIssue] = []
    assets = _mapping_rows(manifest.get("assets"))
    roles = {"cover", "inline", "related"}
    invalid_roles = sorted({str(row.get("role") or "") for row in assets} - roles)
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
    cover = covers[0]
    cover_id = str(cover.get("assetId") or "")
    body_refs = _ASSET_REF_RE.findall(page_text.split("---\n", 2)[-1])
    if cover_id in body_refs:
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
    for asset in assets:
        if asset is cover:
            continue
        if str(asset.get("placementType") or "") == "groupMember" and asset.get("role") != "related":
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
                    "groupMember 必须归入相关图片",
                    ref=entity_name,
                    attrs={"assetId": asset.get("assetId") or ""},
                )
            )
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
    for asset in assets:
        caption = str(asset.get("caption") or "").strip()
        if caption and is_image_dimension_token(caption):
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_CAPTION_INVALID,
                    "图片尺寸参数被错误保存为图注",
                    ref=entity_name,
                    attrs={"assetId": asset.get("assetId") or "", "caption": caption},
                )
            )
        if re.search(r"(?:^|_)cover_(?:x?\d+|\d+[x×]\d+)px(?:_|$)", str(asset.get("assetId") or ""), re.I):
            issues.append(
                _issue(
                    DataIssueCode.MEDIA_CAPTION_INVALID,
                    "封面 assetId 含尺寸伪图注",
                    ref=entity_name,
                    attrs={"assetId": asset.get("assetId") or ""},
                )
            )
    return issues


def homepage_media_completeness_report(execution_id: str) -> dict[str, Any]:
    root = paths.execution_root(execution_id)
    issues: list[DataIssue] = []
    checked_sources = 0
    manifests = _entity_manifest_by_name(root) if root.is_dir() else {}
    dispositions = _homepage_media_dispositions(root) if root.is_dir() else {}
    published_source_assets = {
        str(asset.get("sourceAssetRef") or "").strip()
        for _manifest_path, manifest in manifests.values()
        for asset in _mapping_rows(manifest.get("assets"))
        if str(asset.get("sourceAssetRef") or "").strip()
    }
    if not root.is_dir():
        issues.append(
            _issue(
                DataIssueCode.CONTRACT_INVALID,
                "execution 工作包不存在",
                ref=execution_id,
                attrs={"path": root},
            )
        )
    for meta_path in sorted((root / "sources").glob("*/meta.json")) if root.is_dir() else []:
        meta = read_json(meta_path)
        placements = _mapping_rows(meta.get("imagePlacements"))
        if not placements:
            continue
        checked_sources += 1
        source_ref = meta_path.parent.name
        index_path = meta_path.parent / "assets" / "index.json"
        index_payload = read_json(index_path) if index_path.is_file() else {}
        index_assets = _mapping_rows(index_payload.get("assets"))
        issues.extend(_funnel_issues(source_ref, placements, meta, index_assets))
        issues.extend(
            _disposition_issues(
                source_ref,
                index_assets,
                dispositions,
                published_source_assets,
            )
        )
        for placement in placements:
            caption = str(placement.get("caption") or "").strip()
            if caption and is_image_dimension_token(caption):
                issues.append(
                    _issue(
                        DataIssueCode.MEDIA_CAPTION_INVALID,
                        "source placement 图注是尺寸参数",
                        ref=source_ref,
                        attrs={"fileName": placement.get("fileName") or "", "caption": caption},
                    )
                )
    for entity_name, (manifest_path, manifest) in manifests.items():
        page_path = manifest_path.parent / "page.md"
        page_text = page_path.read_text(encoding="utf-8") if page_path.is_file() else ""
        issues.extend(_manifest_issues(entity_name, manifest_path, manifest, page_text))
    report = {
        "passed": not issues and checked_sources > 0 and bool(manifests),
        "executionId": execution_id,
        "checkedSourceCount": checked_sources,
        "checkedHomepageCount": len(manifests),
        "issues": [issue.as_dict() for issue in issues],
    }
    if not checked_sources:
        report["issues"].append(
            _issue(
                DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
                "execution 没有可校验的页面图片 placements",
                ref=execution_id,
            ).as_dict()
        )
        report["passed"] = False
    if root.is_dir():
        evidence = root / "evidence" / "homepage_media_completeness.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        write_json(evidence, report)
        report["reportPath"] = str(evidence)
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = homepage_media_completeness_report(args.execution)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
