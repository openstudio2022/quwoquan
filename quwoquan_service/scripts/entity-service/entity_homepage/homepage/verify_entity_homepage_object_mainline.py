#!/usr/bin/env python3
"""阻断 entity homepage 对象化主线回退。

不维护 allowlist：旧快照、进程自增 ID、合成 fake、客户端身份 header 与三套
页面表单/标签映射均已退役，一旦回归即 GATE_BLOCK。
"""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "quwoquan_app").is_dir() and (parent / "quwoquan_service").is_dir()
)
SERVICE_ROOT = (
    REPO_ROOT / "quwoquan_service/services/entity-service"
)
APP_ENTITY_ROOT = (
    REPO_ROOT
    / "quwoquan_app/lib/service/entity_service/entity_homepage"
)
HOMEPAGE_FIELDS = (
    SERVICE_ROOT / "contracts/entity_homepage/homepage/fields.yaml"
)
MONITORING_ROOT = REPO_ROOT / "quwoquan_ops/observability/monitoring"
ENTITY_ALERTS = MONITORING_ROOT / "alerts/quwoquan_alerts.yaml"
ENTITY_DASHBOARD = MONITORING_ROOT / "dashboards/l2_entity_objects.json"

# homepage-import 是离线批任务，指标不来自 ContractGraph operation，
# 因此这两条导入告警与看板证据由本域主线门禁守卫；operation 级覆盖统一由
# quwoquan_service/scripts/verify/observability/verify_object_alert_coverage.py 判定。
REQUIRED_IMPORT_ALERTS = ("HomepageImportIssuesPresent", "HomepageImportStale")
REQUIRED_DASHBOARD_EVIDENCE = (
    "quwoquan_homepage_import_objects",
    "runtime_health_check_status",
)

FORBIDDEN_SERVICE = {
    "HomepageStateSnapshot": "单文档 homepage_state 快照",
    'Collection("homepage_state")': "homepage_state 集合装配",
    '"homepage_state"': "homepage_state 字面量",
    "persistLocked(": "全量快照持久化",
    "snapshotLocked(": "全量快照构造",
    "applySnapshot(": "全量快照水合",
    "nextID(": "进程内自增业务 ID",
    "applyDefaultShellData(": "读路径合成 fake",
    "defaultIntersectionReasons(": "合成交集理由",
    'Header.Get("X-Client-User-Id")': "客户端可伪造身份 header",
    '"mock-user"': "默认假身份",
}

FORBIDDEN_APP = {
    "_EntityFormCard": "claim 自造表单卡",
    "_MaintenanceCard": "maintenance 自造表单卡",
    "_ReportCard": "status report 自造表单卡",
    "_homepageTypeLabel(": "私有 homepageType 文案映射",
}

REQUIRED_FILES = (
    "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model/homepage.go",
    "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports/aggregate_store.go",
    "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence/mongo_homepage_store.go",
    "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/domain/model/homepage_claim_request.go",
    "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/domain/model/homepage_status_report.go",
    "quwoquan_app/lib/service/entity_service/entity_homepage/homepage/presentation/homepage_type_labels.dart",
)


def _go_sources() -> list[Path]:
    return sorted(
        path
        for path in SERVICE_ROOT.rglob("*.go")
        if not path.name.endswith("_test.go")
    )


def _dart_sources() -> list[Path]:
    return sorted(APP_ENTITY_ROOT.rglob("*.dart"))


def _observability_issues() -> list[str]:
    issues: list[str] = []
    for pattern in ("**/*.yaml", "**/*.yml", "**/*.json"):
        for path in sorted(MONITORING_ROOT.glob(pattern)):
            if "homepage_state" in path.read_text(encoding="utf-8"):
                issues.append(
                    f"{path.relative_to(REPO_ROOT)}: 观测定义仍引用已退役 homepage_state"
                )

    if ENTITY_ALERTS.is_file():
        alerts_text = ENTITY_ALERTS.read_text(encoding="utf-8")
        issues.extend(
            f"{ENTITY_ALERTS.relative_to(REPO_ROOT)}: 缺少 homepage-import 告警 {alert}"
            for alert in REQUIRED_IMPORT_ALERTS
            if f"alert: {alert}" not in alerts_text
        )
    else:
        issues.append("缺少 quwoquan_alerts.yaml")

    if ENTITY_DASHBOARD.is_file():
        dashboard_text = ENTITY_DASHBOARD.read_text(encoding="utf-8")
        issues.extend(
            f"{ENTITY_DASHBOARD.relative_to(REPO_ROOT)}: 缺少真实 PromQL 证据 {evidence}"
            for evidence in REQUIRED_DASHBOARD_EVIDENCE
            if evidence not in dashboard_text
        )
    else:
        issues.append("缺少 entity 对象看板 l2_entity_objects.json")
    return issues


def main() -> int:
    issues: list[str] = []
    for relative in REQUIRED_FILES:
        if not (REPO_ROOT / relative).is_file():
            issues.append(f"缺少对象化主线文件: {relative}")

    for path in _go_sources():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO_ROOT)
        for symbol, reason in FORBIDDEN_SERVICE.items():
            if symbol in text:
                issues.append(f"{relative}: 回归 {reason}: {symbol}")

    for path in _dart_sources():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO_ROOT)
        for symbol, reason in FORBIDDEN_APP.items():
            if symbol in text:
                issues.append(f"{relative}: 回归 {reason}: {symbol}")

    if HOMEPAGE_FIELDS.is_file():
        fields_text = HOMEPAGE_FIELDS.read_text(encoding="utf-8")
        aggregate_fields = fields_text.split("\ntypes:", maxsplit=1)[0]
        if "\n  role: projection" in aggregate_fields:
            issues.append(
                "entity homepage 聚合根顶层字段重新混入 role: projection"
            )
        shell_marker = "  HomepageShellView:"
        shell_start = fields_text.find(shell_marker)
        if shell_start < 0:
            issues.append("缺少 HomepageShellView typed read model")
        else:
            shell_tail = fields_text[shell_start + len(shell_marker) :]
            next_type = shell_tail.find("\n  HomepageReviewSummaryView:")
            shell_text = shell_tail if next_type < 0 else shell_tail[:next_type]
            for retired in ("type: object", "type: '[]object'"):
                if retired in shell_text:
                    issues.append(
                        "HomepageShellView 重新以内联裸类型复制投影: "
                        f"{retired}"
                    )
    else:
        issues.append("缺少 entity homepage canonical fields.yaml")

    issues.extend(_observability_issues())

    if issues:
        print("[entity-homepage-object-mainline] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[entity-homepage-object-mainline] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
