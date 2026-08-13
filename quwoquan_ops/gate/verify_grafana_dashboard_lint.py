#!/usr/bin/env python3
"""Grafana 看板 JSON 契约 lint。

看板真相源是 quwoquan_ops/observability/monitoring/dashboards/**，由 Grafana
file provisioning 直接加载。本门禁保证：

1. 顶层是 bare dashboard model（含 title/uid），禁止 API 响应形状的
   {"dashboard": ...} 包装——包装文件会被 provisioning 静默拒载。
2. uid 全局唯一且形如 qwq-l<N>-*；文件名 l<N>_ 前缀与 uid 层级一致，
   保证 L1-L4 分层语义单一真相源。
3. 每个 panel 的 targets[].expr 非空——空表达式面板在页面上是死面板。
4. panel/datasource 若显式声明 uid，必须指向 provisioning 唯一数据源
   quwoquan-prometheus。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS_ROOT = REPO_ROOT / "quwoquan_ops/observability/monitoring/dashboards"
CANONICAL_DATASOURCE_UID = "quwoquan-prometheus"
# 规格 SIT 引用的必备看板（specs/feature-tree/product-ops-growth 飞轮、
# platform-ops-governance Error Governance）；缺失即规格回退。
REQUIRED_DASHBOARDS = {
    "l2_content_flywheel.json",
    "l3_error_governance.json",
}
_UID_PATTERN = re.compile(r"^qwq-l([1-4])-[a-z0-9-]+$")
_FILE_PATTERN = re.compile(r"^l([1-4])_[a-z0-9_]+\.json$")


def _iter_panels(value):
    if isinstance(value, dict):
        if "targets" in value and isinstance(value.get("targets"), list):
            yield value
        for child in value.values():
            yield from _iter_panels(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_panels(child)


def _datasource_uids(value):
    if isinstance(value, dict):
        datasource = value.get("datasource")
        if isinstance(datasource, dict) and isinstance(datasource.get("uid"), str):
            yield datasource["uid"]
        for child in value.values():
            yield from _datasource_uids(child)
    elif isinstance(value, list):
        for child in value:
            yield from _datasource_uids(child)


def main() -> int:
    errors: list[str] = []
    seen_uids: dict[str, str] = {}
    files = sorted(DASHBOARDS_ROOT.glob("*.json"))
    if not files:
        print("FAIL: no dashboards found under monitoring/dashboards")
        return 1
    missing_required = REQUIRED_DASHBOARDS - {path.name for path in files}
    for name in sorted(missing_required):
        errors.append(f"spec-required dashboard is missing: {name}")
    for path in files:
        name = path.name
        try:
            dashboard = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            errors.append(f"{name}: invalid JSON: {error}")
            continue
        if not isinstance(dashboard, dict):
            errors.append(f"{name}: dashboard root must be an object")
            continue
        if "dashboard" in dashboard and "title" not in dashboard:
            errors.append(
                f"{name}: wrapped API payload is not loadable by file "
                "provisioning; store the bare dashboard model"
            )
            continue
        title = dashboard.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{name}: dashboard title must be non-empty")
        uid = str(dashboard.get("uid", ""))
        uid_match = _UID_PATTERN.fullmatch(uid)
        if uid_match is None:
            errors.append(f"{name}: uid must match qwq-l<1..4>-<slug>, got {uid!r}")
        if uid in seen_uids:
            errors.append(f"{name}: uid {uid} duplicates {seen_uids[uid]}")
        else:
            seen_uids[uid] = name
        file_match = _FILE_PATTERN.fullmatch(name)
        if file_match is None:
            errors.append(f"{name}: file name must match l<1..4>_<slug>.json")
        elif uid_match is not None and file_match.group(1) != uid_match.group(1):
            errors.append(
                f"{name}: file level l{file_match.group(1)} disagrees with "
                f"uid level l{uid_match.group(1)}"
            )
        for panel in _iter_panels(dashboard):
            panel_title = str(panel.get("title", "<untitled>"))
            for index, target in enumerate(panel.get("targets", [])):
                if not isinstance(target, dict):
                    continue
                expression = target.get("expr")
                if not isinstance(expression, str) or not expression.strip():
                    errors.append(
                        f"{name}: panel {panel_title!r} target[{index}] has an "
                        "empty expr"
                    )
        for datasource_uid in _datasource_uids(dashboard):
            if datasource_uid not in (CANONICAL_DATASOURCE_UID, "-- Grafana --"):
                errors.append(
                    f"{name}: datasource uid {datasource_uid!r} is not the "
                    f"provisioned {CANONICAL_DATASOURCE_UID}"
                )
    if errors:
        print("FAIL: grafana dashboard lint")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS: grafana dashboard lint")
    print(f"  - {len(files)} dashboards, {len(seen_uids)} unique uids")
    return 0


if __name__ == "__main__":
    sys.exit(main())
