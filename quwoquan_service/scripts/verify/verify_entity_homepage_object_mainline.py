#!/usr/bin/env python3
"""阻断 entity homepage 对象化主线回退。

不维护 allowlist：旧快照、进程自增 ID、合成 fake、客户端身份 header 与三套
页面表单/标签映射均已退役，一旦回归即 GATE_BLOCK。
"""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = (
    REPO_ROOT / "quwoquan_service/services/entity-service"
)
APP_ENTITY_ROOT = REPO_ROOT / "quwoquan_app/lib/ui/entity"

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
    "quwoquan_service/services/entity-service/internal/domain/homepage/model/homepage.go",
    "quwoquan_service/services/entity-service/internal/domain/homepage/ports/aggregate_store.go",
    "quwoquan_service/services/entity-service/internal/infrastructure/homepage/persistence/mongo_homepage_store.go",
    "quwoquan_service/services/entity-service/internal/domain/homepage_claim_request/model/homepage_claim_request.go",
    "quwoquan_service/services/entity-service/internal/domain/homepage_status_report/model/homepage_status_report.go",
    "quwoquan_app/lib/ui/entity/models/homepage_type_labels.dart",
)


def _go_sources() -> list[Path]:
    return sorted(
        path
        for path in SERVICE_ROOT.rglob("*.go")
        if not path.name.endswith("_test.go")
    )


def _dart_sources() -> list[Path]:
    return sorted(APP_ENTITY_ROOT.rglob("*.dart"))


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

    if issues:
        print("[entity-homepage-object-mainline] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[entity-homepage-object-mainline] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
