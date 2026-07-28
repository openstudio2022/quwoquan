#!/usr/bin/env python3
"""
阻断 production lib、App pubspec 与运行入口对聚合 Mock/fixture 的依赖。

规格：feature-tree 的 app-cloud-business-object-commercial-closure REQ-004。

用法（仓库根）:
  python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
APP_LIB = APP / "lib"
PRODUCTION_SERVICE_MOCK_ROOT = APP_LIB / "cloud" / "services"
RETIRED_AGGREGATE_MOCK_PACKAGE = APP / "packages/quwoquan_cloud_mock"
RETIRED_PRODUCTION_FIXTURE_TOKENS = (
    "contract_fixture_runtime_loader",
    "prefab_user_resolver",
    "mock_session_identity",
    "kMockCurrentOwnerId",
    "kMockCurrentSubAccountId",
    "PrefabUserMetadata",
    "prefab_user_metadata",
    "prefab_user_provenance",
    "QWQ_REPO_ROOT",
    "contract_fixtures",
    "test_fixtures",
    "fixture_user_",
    "fixture_persona_",
)
FORBIDDEN_PRODUCTION_IMPORT_TOKENS = (
    "package:quwoquan_cloud_mock/",
    "package:quwoquan_app/test/",
    "/test/support/",
    "/runners/alpha/",
)
BUSINESS_TEST_DOUBLE_CLASS_RE = re.compile(
    r"\bclass\s+(?:Mock|Stub|Noop|Fake|Memory|InMemory)"
    r"[A-Za-z0-9_]*(?:Repository|Query|Writer|Reader|Facet|Store|Service|Client|Adapter)\b"
)

# package:quwoquan_app/.../mock/ 或 .../mock/xxx.dart
IMPORT_MOCK = re.compile(
    r"""import\s+['"]package:quwoquan_app/[^'"]*/mock/[^'"]*['"]\s*;"""
)
# 域名占位行（与 ChatContactsRow 等对齐）
PROTOTYPE_RE = re.compile(
    r"\bprototype(Circles|Groups)\b",
)

def scan_dart_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.dart"))


def main() -> int:
    errors: list[str] = []

    if RETIRED_AGGREGATE_MOCK_PACKAGE.exists():
        errors.append("packages/quwoquan_cloud_mock: 聚合 Mock package 必须物理删除")
    if "quwoquan_cloud_mock" in (APP / "pubspec.yaml").read_text(encoding="utf-8"):
        errors.append("pubspec.yaml: dev_dependencies 也不得引用聚合 Mock package")

    # production lib 不得保留业务 Mock 源文件或顶层业务 test double。
    if PRODUCTION_SERVICE_MOCK_ROOT.is_dir():
        for path in sorted(PRODUCTION_SERVICE_MOCK_ROOT.glob("**/mock/*.dart")):
            rel = path.relative_to(APP_LIB).as_posix()
            errors.append(
                f"{rel}: production lib 禁止保留 cloud/services/*/mock 源文件"
            )
        for path in scan_dart_files(PRODUCTION_SERVICE_MOCK_ROOT):
            rel = path.relative_to(APP_LIB).as_posix()
            text = path.read_text(encoding="utf-8")
            if BUSINESS_TEST_DOUBLE_CLASS_RE.search(text):
                errors.append(
                    f"{rel}: production cloud/services 禁止业务 test double 顶层类"
                )

    # P0: production lib（包括 generated）不能通过运行时 loader / resolver、
    # mock identity、环境变量或仓库相对路径读取 fixture，也不得承载 fixture
    # user/persona 数据。对象级 typed doubles 只能物理隔离在 test/support。
    for path in scan_dart_files(APP_LIB):
        rel = path.relative_to(APP_LIB).as_posix()
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_PRODUCTION_IMPORT_TOKENS:
            if token in text:
                errors.append(
                    f"{rel}: production lib 禁止引用 test/runner/Mock token {token!r}"
                )
        for token in RETIRED_PRODUCTION_FIXTURE_TOKENS:
            if token in text:
                errors.append(
                    f"{rel}: production lib 禁止 fixture/Mock runtime token {token!r}"
                )

    # lib/cloud 纳入扫描：production adapter/provider 同样禁止 import …/mock/。
    roots = [
        APP_LIB / "ui",
        APP_LIB / "app",
        APP_LIB / "core",
        APP_LIB / "cloud",
    ]
    for base in roots:
        for path in scan_dart_files(base):
            rel = path.relative_to(APP_LIB).as_posix()
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if IMPORT_MOCK.search(line):
                    errors.append(
                        f"{rel}:{i}: 禁止 import cloud …/mock/（{line.strip()}）"
                    )
            # 仅扫描 UI 模型文件，避免 provider 引用 ChatContactsRow.prototype* 误报
            if "/models/" in rel and PROTOTYPE_RE.search(text):
                errors.append(
                    f"{rel}: 禁止在 UI 模型中内嵌 prototypeCircles/prototypeGroups 等域名占位"
                )

    if errors:
        print("ui_mock_isolation 校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print("说明见 app-cloud-business-object-commercial-closure REQ-004", file=sys.stderr)
        return 1

    print("ui_mock_isolation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
