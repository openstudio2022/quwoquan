#!/usr/bin/env python3
"""Verify source-page image enumeration, download and homepage disposition closure.

Two verdicts with different decidable moments (DEC-029), plus their union:

- decision: owed the moment `1.download` closes, reads only sources and the frozen
  dispositions.
- fulfillment: owed once the object is materialized, reconciles the manifest against
  those same frozen dispositions in both directions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections.abc import Collection
from typing import Any, Iterable, Mapping

sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core import paths
from core.data_issue import DataIssue, DataIssueCode
from core.io import read_json
from content.execution.execution_terminal import load_terminal_execution_evidence
from verify import homepage_media_decision as decision
from verify import homepage_media_fulfillment as fulfillment
from verify.homepage_media_issue import issue as _issue, mapping_rows as _mapping_rows


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


def _entity_manifest_by_name(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    out: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted((root / "entities").glob("*/*/*/manifest.json")):
        out[path.parent.name] = (path, read_json(path))
    return out


def _scan_sources(
    root: Path,
    *,
    scope: set[str] | None,
    dispositions: Mapping[str, list[dict[str, Any]]],
    published_source_assets: set[str],
    include_decision: bool,
    include_fulfillment: bool,
) -> tuple[list[DataIssue], int]:
    """Walk 每个有图片 placement 的来源单元，按视图收集问题并计数。"""

    issues: list[DataIssue] = []
    checked_sources = 0
    for meta_path in sorted((root / "sources").glob("*/meta.json")):
        meta = read_json(meta_path)
        if scope is not None and str(meta.get("entityName") or "").strip() not in scope:
            continue
        placements = _mapping_rows(meta.get("imagePlacements"))
        if not placements:
            continue
        checked_sources += 1
        source_ref = meta_path.parent.name
        index_path = meta_path.parent / "assets" / "index.json"
        index_payload = read_json(index_path) if index_path.is_file() else {}
        index_assets = _mapping_rows(index_payload.get("assets"))
        if include_decision:
            issues.extend(decision.funnel_issues(source_ref, meta, index_assets))
            issues.extend(
                decision.disposition_issues(source_ref, index_assets, dispositions)
            )
            issues.extend(decision.placement_caption_issues(source_ref, placements))
        if include_fulfillment:
            issues.extend(
                fulfillment.reconciliation_issues(
                    source_ref,
                    index_assets,
                    dispositions,
                    published_source_assets,
                )
            )
    return issues, checked_sources


def _media_report(
    execution_id: str,
    *,
    publishable_names: Collection[str] | None,
    include_decision: bool,
    include_fulfillment: bool,
) -> dict[str, Any]:
    """Shared scan behind the decision, fulfillment and combined verdicts.

    ``publishable_names`` narrows the audit to the objects being released.  The
    decision view never passes a scope: at download time no object has been
    discarded yet, so every downloaded image owes an outcome.
    """
    root = paths.execution_root(execution_id)
    issues: list[DataIssue] = []
    checked_sources = 0
    scope = (
        None
        if publishable_names is None
        else {str(name).strip() for name in publishable_names if str(name).strip()}
    )
    manifests = _entity_manifest_by_name(root) if root.is_dir() else {}
    if scope is not None:
        manifests = {name: row for name, row in manifests.items() if name in scope}
    dispositions = _homepage_media_dispositions(root) if root.is_dir() else {}
    published_source_assets = {
        str(asset.get("sourceAssetRef") or "").strip()
        for _manifest_path, manifest in manifests.values()
        for asset in _mapping_rows(manifest.get("assets"))
        if str(asset.get("sourceAssetRef") or "").strip()
    }
    if root.is_dir():
        source_issues, checked_sources = _scan_sources(
            root,
            scope=scope,
            dispositions=dispositions,
            published_source_assets=published_source_assets,
            include_decision=include_decision,
            include_fulfillment=include_fulfillment,
        )
        issues.extend(source_issues)
    else:
        issues.append(
            _issue(
                DataIssueCode.CONTRACT_INVALID,
                "execution 工作包不存在",
                ref=execution_id,
                attrs={"path": root},
            )
        )
    if include_fulfillment:
        issues.extend(fulfillment.scan_manifests(manifests))
    report = {
        "passed": (
            not issues
            and checked_sources > 0
            and (bool(manifests) or not include_fulfillment)
        ),
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
        # 纯 verifier 对 active 与 terminal 工作包都只读；该调用只负责让无效的
        # stale/supersession candidate fail closed，不把报告反写进 execution inventory。
        load_terminal_execution_evidence(root)
    return report


def homepage_media_decision_report(execution_id: str) -> dict[str, Any]:
    """`1.download` 完成判据：每张下载图的处置已冻结且合法。

    只读 `sources/**` 与冻结处置，不读 manifest，因此下载一闭合即可判定。
    """
    return _media_report(
        execution_id,
        publishable_names=None,
        include_decision=True,
        include_fulfillment=False,
    )


def homepage_media_fulfillment_report(
    execution_id: str,
    *,
    publishable_names: Collection[str] | None = None,
) -> dict[str, Any]:
    """物化后判据：manifest 与冻结处置双向对账，差集 fail closed。"""
    return _media_report(
        execution_id,
        publishable_names=publishable_names,
        include_decision=False,
        include_fulfillment=True,
    )


def homepage_media_completeness_report(
    execution_id: str,
    *,
    publishable_names: Collection[str] | None = None,
) -> dict[str, Any]:
    """校验主页图片枚举与发布处置的完整性（决策 + 兑现的合并口径）。

    ``publishable_names`` 为 None 时审计整个工作包（独立 verifier 口径）。批次准出
    调用方必须传入本次准出集合：候选池经过采后必然留下未产出的丢弃对象，它们的来源
    图片既不会进入任何 manifest，也不该阻断已达标对象发布。
    """
    return _media_report(
        execution_id,
        publishable_names=publishable_names,
        include_decision=True,
        include_fulfillment=True,
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution", required=True)
    parser.add_argument(
        "--view",
        choices=("decision", "fulfillment", "combined"),
        default="combined",
        help="decision 供 1.download 判据；fulfillment 供物化后对账；combined 为整包审计",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.view == "decision":
        report = homepage_media_decision_report(args.execution)
    elif args.view == "fulfillment":
        report = homepage_media_fulfillment_report(args.execution)
    else:
        report = homepage_media_completeness_report(args.execution)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
