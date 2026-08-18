"""回填 canonical publish 树中缺失的 ``distributionDecision``。

存量 ``rights.json`` 有一批资产行没有写入 ``distributionDecision``，导致对象无法
通过商用闭合判定。缺的是字段本身，不是权利：这些行的 licenseUrl / author /
authorizationProof 都齐备，许可证也已在发现阶段经
``license_allows_commercial_distribution`` 筛过。

判定语义直接复用 ``governance.coverage.distribution.image_distribution_decision``，
不在此处重新实现，避免出现第二真相源。

``acquisitionStatus`` 不存在于 publish 侧的 rights 投影里（它属于采集层）。本迁移
以「资产在 CAS 中有 ref 与 sha256」作为 ACQUIRED 的证据；没有 CAS ref 的行会被跳过
并报告，不做猜测。

只写 ``rights.json``，不改 ``quwoquan_data/scripts``，因此不触发分级验收冻结门。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_SCRIPTS = _REPO_ROOT / "quwoquan_data" / "scripts"
if str(_DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DATA_SCRIPTS))

from governance.coverage.distribution import (  # noqa: E402
    AcquisitionStatus,
    RightsStatus,
    image_distribution_decision,
)


class BackfillError(RuntimeError):
    """迁移无法在不猜测的前提下继续。"""


def _publish_root() -> Path:
    override = os.environ.get("QWQ_PUBLISH_ROOT")
    if override:
        return Path(override)
    return _REPO_ROOT / "quwoquan_data" / "publish"


_STYLES: tuple[dict[str, Any], ...] = (
    {"separators": (",", ":"), "ensure_ascii": False, "sort_keys": True},
    {"indent": 2, "ensure_ascii": False, "sort_keys": True},
)


def _detect_style(pristine: Any, original: str) -> dict[str, Any]:
    """从未改动的解析结果反推原文件风格，避免整文件 reformat 淹没真实改动。

    必须在改动 document 之前调用：一旦写入新字段，任何风格都无法复现原文。
    """
    for style in _STYLES:
        if json.dumps(pristine, **style) + "\n" == original:
            return style
    raise BackfillError("无法识别既有 JSON 风格，拒绝重写以免产生全文件 diff")


def _dump_with_style(document: Any, style: dict[str, Any]) -> str:
    return json.dumps(document, **style) + "\n"


def _has_acquisition_evidence(row: dict[str, Any]) -> bool:
    asset = row.get("asset")
    if not isinstance(asset, dict):
        return False
    ref = str(asset.get("ref") or "")
    digest = str(asset.get("sha256") or "")
    return ref.startswith("cas/") and digest.startswith("sha256:")


def _decide(row: dict[str, Any]) -> str:
    raw_status = str(row.get("rightsAuditStatus") or row.get("rightsStatus") or "").strip()
    try:
        rights_status = RightsStatus(raw_status)
    except ValueError as exc:
        raise BackfillError(f"未知 rightsAuditStatus：{raw_status!r}") from exc
    decision = image_distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=rights_status,
        authorization_proof=str(row.get("authorizationProof") or ""),
        usage_scope=str(row.get("usageScope") or ""),
        model_release_status=str(row.get("modelReleaseStatus") or ""),
    )
    return decision.value


def backfill(publish_root: Path, *, apply: bool) -> dict[str, Any]:
    decisions: Counter[str] = Counter()
    skipped: list[str] = []
    touched_files = 0
    filled_rows = 0

    for rights_path in sorted(publish_root.rglob("rights.json")):
        original = rights_path.read_text()
        document = json.loads(original)
        assets = document.get("assets")
        if not isinstance(assets, list):
            continue

        style = _detect_style(json.loads(original), original) if apply else None
        file_changed = False
        for index, row in enumerate(assets):
            if not isinstance(row, dict):
                continue
            if str(row.get("distributionDecision") or "").strip():
                continue
            location = f"{rights_path.relative_to(publish_root)}#assets[{index}]"
            if not _has_acquisition_evidence(row):
                skipped.append(f"{location}: 缺 CAS ref/sha256，无法证明已采集")
                continue
            decision = _decide(row)
            row["distributionDecision"] = decision
            decisions[decision] += 1
            filled_rows += 1
            file_changed = True

        if file_changed:
            touched_files += 1
            if apply and style is not None:
                rights_path.write_text(_dump_with_style(document, style))

    return {
        "filledRows": filled_rows,
        "touchedFiles": touched_files,
        "decisions": dict(decisions),
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish-root",
        type=Path,
        default=None,
        help="canonical publish 根，默认取 QWQ_PUBLISH_ROOT 或仓内 quwoquan_data/publish",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写盘；缺省只预演并打印将要发生的变更",
    )
    args = parser.parse_args(argv)

    publish_root = args.publish_root or _publish_root()
    if not publish_root.is_dir():
        print(f"FAIL: publish 根不存在：{publish_root}", file=sys.stderr)
        return 2

    try:
        report = backfill(publish_root, apply=args.apply)
    except BackfillError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[rights_distribution_backfill] {mode} root={publish_root}")
    print(f"  待回填行数 {report['filledRows']}，涉及文件 {report['touchedFiles']}")
    for decision, count in sorted(report["decisions"].items()):
        print(f"    {decision}: {count}")
    if report["skipped"]:
        print(f"  跳过 {len(report['skipped'])} 行（缺采集证据）：")
        for item in report["skipped"][:20]:
            print(f"    {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
