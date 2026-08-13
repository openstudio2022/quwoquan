#!/usr/bin/env python3
"""
阻断 production lib、App pubspec 与运行入口对聚合 Mock/fixture 的依赖。

## 替身判定按结构，不按类名

替身可达性由三类结构事实判定：

* **import 边**：`TEST_LIBRARY_IMPORT_PREFIXES` 与 `FORBIDDEN_PRODUCTION_IMPORT_TOKENS`。
  Dart 必须先 import 才能引用，因此「production lib import 了测试框架/替身库/test 目录」
  对这门语言既 sound 又 complete。
* **声明位置**：production `lib/**/mock/*.dart` 这类 test-only 目录。
* **配置与专有 token**：`RETIRED_PRODUCTION_FIXTURE_TOKENS`，判定对象本身就是这些字面量。

刻意不判类名词汇（原 `class (Mock|Stub|Noop|Fake|Memory|InMemory)*Repository`）：
assistant 长期记忆的 `MemoryProfileRepository` 一出现就会被误伤，而替身改名成
`LocalPostRepository` 就直接逃逸——两个方向都错，且都不可复核。

## 已知盲点

「类型实现了 production port 但内部只返回字面量」这种**内联**替身，Dart 侧同样需要
全程序类型分析才能判定；本门禁不做该判定，也不用类名近似它。该维度目前无覆盖，
不假装通过。已验证的替代覆盖点是 test/support 物理隔离与 typed port override 契约测试。

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
APP_TEST_SUPPORT = APP / "test" / "support"
RETIRED_AGGREGATE_MOCK_PACKAGE = APP / "packages/quwoquan_cloud_mock"
RETIRED_PRODUCTION_FIXTURE_TOKENS = (
    "contract_fixture_runtime_loader",
    "prefab_user_resolver",
    "mock_session_identity",
    "kMockCurrentOwnerId",
    "kMockCurrentPersonaId",
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
#: 测试框架与 mock 库：Dart 同样必须先 import 才能引用，判定对象是包名本身。
#: production lib import 了它们，就是编译器可见的「替身可达」，与类名叫什么无关。
TEST_LIBRARY_IMPORT_PREFIXES = (
    "package:flutter_test/",
    "package:test/",
    "package:integration_test/",
    "package:mockito/",
    "package:mocktail/",
    "package:patrol/",
    "package:http/testing.dart",
)
DART_IMPORT_RE = re.compile(r"""(?m)^\s*(?:import|export)\s+['"]([^'"]+)['"]""")
#: production lib 的测试库 import 豁免已归零。保留空集合供结构契约证明基线不得回潮；
#: 新增任何条目或 production import 都必须 BLOCK。
TEST_LIBRARY_IMPORT_BASELINE: frozenset[str] = frozenset()

# package:quwoquan_app/.../mock/ 或 .../mock/xxx.dart
IMPORT_MOCK = re.compile(
    r"""import\s+['"]package:quwoquan_app/[^'"]*/mock/[^'"]*['"]\s*;"""
)
# 域名占位行（与 ChatContactsRow 等对齐）
PROTOTYPE_RE = re.compile(
    r"\bprototype(Circles|Groups)\b",
)
TEST_SUPPORT_FIXTURE_READER_TOKENS = (
    "object_contract_example_reader",
    "ObjectContractExampleReader",
    "objectContractExampleReader",
    "requireExample(",
)
TEST_SUPPORT_DOMAIN_DOCUMENT_RE = re.compile(
    r"""\.document\(\s*['"](?:assistant|chat|circle|content|entity|gateway|"""
    r"""integration|notification|ops|realtime|recommendation|rtc|search|tag|user)['"]"""
)
DART_IO_IMPORT_RE = re.compile(r"""(?m)^\s*import\s+['"]dart:io['"]\s*;""")

def test_library_imports(text: str) -> list[str]:
    """该 Dart 源文件 import 了哪些测试框架/替身库。类名长什么样与判定无关。"""
    return [
        target
        for target in DART_IMPORT_RE.findall(text)
        if target.startswith(TEST_LIBRARY_IMPORT_PREFIXES)
    ]


def scan_dart_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.dart"))


def test_support_fixture_reader_violations(path: Path, text: str) -> list[str]:
    """返回 test/support 中跨域 fixture reader 的结构性违规。"""
    violations = [
        f"禁止 test/support 跨域 fixture reader token {token!r}"
        for token in TEST_SUPPORT_FIXTURE_READER_TOKENS
        if token in text
    ]
    if TEST_SUPPORT_DOMAIN_DOCUMENT_RE.search(text):
        violations.append("禁止 test/support 通过 document(domain) 选择跨域场景")
    if "fixtures" in path.parts and DART_IO_IMPORT_RE.search(text):
        violations.append("test/support fixture builder 禁止 import dart:io 读取运行时 JSON")
    return violations


def main() -> int:
    errors: list[str] = []

    if RETIRED_AGGREGATE_MOCK_PACKAGE.exists():
        errors.append("packages/quwoquan_cloud_mock: 聚合 Mock package 必须物理删除")
    if "quwoquan_cloud_mock" in (APP / "pubspec.yaml").read_text(encoding="utf-8"):
        errors.append("pubspec.yaml: dev_dependencies 也不得引用聚合 Mock package")

    # production lib 不得保留业务 Mock 源文件或顶层业务 test double。
    for path in sorted(APP_LIB.glob("**/mock/*.dart")):
        rel = path.relative_to(APP_LIB).as_posix()
        errors.append(f"{rel}: production lib 禁止保留 mock 源文件")
    # P0: production lib（包括 generated）不能通过运行时 loader / resolver、
    # mock identity、环境变量或仓库相对路径读取 fixture，也不得承载 fixture
    # user/persona 数据。对象级 typed doubles 只能物理隔离在 test/support。
    test_library_importers: set[str] = set()
    for path in scan_dart_files(APP_LIB):
        rel = path.relative_to(APP_LIB).as_posix()
        text = path.read_text(encoding="utf-8")
        for target in test_library_imports(text):
            test_library_importers.add(rel)
            if rel in TEST_LIBRARY_IMPORT_BASELINE:
                continue
            errors.append(
                f"{rel}: production lib 禁止 import 测试框架/替身库 {target!r}"
                "（对象级 typed double 只能物理隔离在 test/support）"
            )
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

    # canonical object/runtime/design-system roots 全量扫描；旧技术根不再是
    # positive input，避免目录迁空后门禁假绿。
    for base in (APP_LIB,):
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

    for stale in sorted(TEST_LIBRARY_IMPORT_BASELINE - test_library_importers):
        errors.append(
            f"{stale}: 已不再 import 测试框架/替身库，必须同步删除基线条目，"
            "否则基线退化成永久豁免"
        )

    for path in scan_dart_files(APP_TEST_SUPPORT):
        rel = path.relative_to(APP).as_posix()
        text = path.read_text(encoding="utf-8")
        for violation in test_support_fixture_reader_violations(path, text):
            errors.append(f"{rel}: {violation}")

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
