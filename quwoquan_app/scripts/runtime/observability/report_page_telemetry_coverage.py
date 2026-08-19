#!/usr/bin/env python3
"""页面埋点覆盖矩阵：telemetry_descriptor 声明 ↔ 实际 tracker 调用。

page_object_contract.yaml 的 telemetry_descriptor 声明页面生命周期与交互
动作；enter/exit 由路由层 AppPageExperienceTracker 全局承接，交互动作
（submit/publish/otp_send/...）必须由页面实现经强类型遥测出口上报。
本工具产出全量覆盖矩阵报告，并只对黄金指标 primary 漏斗页面（登录 /
创作发布 / 搜索，见 golden_metric_catalog.yaml 的 account_access /
content_creation / search_discovery 业务）做 BLOCK——声明了交互动作却
扫描不到任何遥测出口调用即失败。

报告输出：.qwq_output/env/repo/runs/telemetry-coverage/report.{md,json}
（可删除可重建，凭本文件与契约真相源再生）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT  # noqa: E402

APP_ROOT = REPO_ROOT / "quwoquan_app"
PAGE_CONTRACT = (
    REPO_ROOT / "quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml"
)
REPORT_DIR = REPO_ROOT / ".qwq_output/env/repo/runs/telemetry-coverage"

# 强类型遥测出口的调用标记；命中任意一个即认为页面（或其展示目录）
# 已接入交互埋点。只认强类型出口，不认自由字符串事件。
TRACKER_MARKERS = (
    "JourneyEventTracker",
    "trackLoginFunnel",
    "trackContentPublication",
    "reportCreateEditorSurfaceEvent",
    "AppTelemetryPayload.",
    "ContentBehaviorTracker",
    "BehaviorReporter",
    "ContentEngagementTracker",
    "recordPageErrorOutcome",
)
# 由路由层全局承接的 lifecycle，不要求页面内出现调用标记。
GLOBAL_LIFECYCLE = {"enter", "exit", "route_failure", "failure"}
# BLOCK 范围：黄金指标 primary 漏斗页面的 event_namespace 前缀
# （golden_metric_catalog: account_access / content_creation / search_discovery）。
BLOCKING_NAMESPACE_PREFIXES = (
    "page.user.login",
    "page.content.create",
    "page.search",
)


def _load_pages() -> list[dict]:
    document = yaml.safe_load(PAGE_CONTRACT.read_text(encoding="utf-8"))
    return [row for row in document.get("pages", []) if isinstance(row, dict)]


def _resolve_descriptor(
    page: dict, by_id: dict[str, dict], depth: int = 0
) -> tuple[dict, bool]:
    """返回 (descriptor, inherited)。继承 descriptor 的页面共享父页面的
    事件命名空间，交互埋点由父页面承担，不独立要求覆盖。"""
    descriptor = page.get("telemetry_descriptor")
    if not isinstance(descriptor, dict):
        return {}, False
    if "inherit_from" in descriptor and depth < 8:
        parent = by_id.get(str(descriptor["inherit_from"]))
        if parent is not None:
            resolved, _ = _resolve_descriptor(parent, by_id, depth + 1)
            return resolved, True
        return {}, True
    return descriptor, False


def _interaction_actions(descriptor: dict) -> list[str]:
    lifecycle = descriptor.get("lifecycle")
    if not isinstance(lifecycle, list):
        return []
    return [
        str(action)
        for action in lifecycle
        if str(action) not in GLOBAL_LIFECYCLE and not str(action).endswith("_failure")
    ]


def _scan_markers(source_path: str) -> list[str]:
    page_file = APP_ROOT / source_path
    if not page_file.is_file():
        return []
    hits: set[str] = set()
    # 页面文件 + 同目录（页面拆分出的 state/helper 文件共享埋点出口）。
    candidates = [page_file, *sorted(page_file.parent.glob("*.dart"))]
    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for marker in TRACKER_MARKERS:
            if marker in content:
                hits.add(marker)
    return sorted(hits)


def main() -> int:
    pages = _load_pages()
    by_id = {str(page.get("page_id")): page for page in pages}
    rows: list[dict] = []
    blocking_failures: list[str] = []
    for page in pages:
        page_id = str(page.get("page_id", ""))
        source_path = str(page.get("source_path", ""))
        descriptor, inherited = _resolve_descriptor(page, by_id)
        namespace = str(descriptor.get("event_namespace", ""))
        actions = [] if inherited else _interaction_actions(descriptor)
        markers = _scan_markers(source_path) if source_path else []
        covered = bool(markers) if actions else True
        rows.append(
            {
                "pageId": page_id,
                "sourcePath": source_path,
                "eventNamespace": namespace,
                "inherited": inherited,
                "interactionActions": actions,
                "trackerMarkers": markers,
                "covered": covered,
            }
        )
        if (
            actions
            and not markers
            and any(namespace.startswith(prefix) for prefix in BLOCKING_NAMESPACE_PREFIXES)
        ):
            blocking_failures.append(
                f"{page_id} ({namespace}) declares {actions} but no telemetry "
                f"egress call was found in {source_path} or its directory"
            )

    declared = [row for row in rows if row["interactionActions"]]
    uncovered = [row for row in declared if not row["covered"]]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "report.json").write_text(
        json.dumps(
            {
                "totalPages": len(rows),
                "pagesWithInteractionDeclarations": len(declared),
                "uncoveredPages": len(uncovered),
                "blockingFailures": blocking_failures,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# 页面埋点覆盖矩阵",
        "",
        f"- 登记页面：{len(rows)}",
        f"- 声明交互动作页面：{len(declared)}",
        f"- 声明但未扫描到遥测出口：{len(uncovered)}",
        "",
        "| page_id | namespace | 交互动作 | 遥测出口 | 覆盖 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in sorted(declared, key=lambda item: (item["covered"], item["pageId"])):
        lines.append(
            "| {pageId} | {eventNamespace} | {actions} | {markers} | {covered} |".format(
                pageId=row["pageId"],
                eventNamespace=row["eventNamespace"],
                actions=", ".join(row["interactionActions"]),
                markers=", ".join(row["trackerMarkers"]) or "（无）",
                covered="✔" if row["covered"] else "✘",
            )
        )
    (REPORT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"telemetry coverage: pages={len(rows)} declared={len(declared)} "
        f"uncovered={len(uncovered)} report={REPORT_DIR.relative_to(REPO_ROOT)}"
    )
    if blocking_failures:
        print("FAIL: primary funnel pages lack telemetry egress")
        for failure in blocking_failures:
            print(f"  - {failure}")
        return 1
    print("PASS: primary funnel pages are instrumented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
