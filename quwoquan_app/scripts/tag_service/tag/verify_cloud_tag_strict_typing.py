#!/usr/bin/env python3
"""App 标签链路 StrictTyping 门禁。

手写 Tag Remote 与 pure contracts 不得用 `dynamic` 或
`Map<String, dynamic>` 穿透业务边界；`Object?` 只允许停留在解码入口，方法返回
必须是 DTO 或 typed Slice。

scope:
  - quwoquan_app/lib/service/tag_service/tag/*/adapters/**/*.dart
  - quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/tag/**/*.dart

FAIL 条件:
  - `dynamic` / `Map<String, dynamic>`。
  - `Future<dynamic>` / `Future<Object?>`（HTTP 中转裸返回，应直出 DTO/List<DTO>）。
  - 方法/函数返回类型为裸 `dynamic` / `Object?`（如 `dynamic _get(` / `Object? _post(`）。

豁免（合规，不计 FAIL）:
  - `Object? decoded` 等【解码入口参数】（参数非返回契约）。

用法: python3 quwoquan_app/scripts/tag_service/tag/verify_cloud_tag_strict_typing.py
"""
from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import re

ROOT = REPO_ROOT
APP_TAG_ROOT = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "service"
    / "tag_service"
    / "tag"
)
PACKAGE_TAG_ROOT = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "tag"
)

FUTURE_DYNAMIC = re.compile(r"Future<\s*dynamic\s*>")
FUTURE_OBJECTQ = re.compile(r"Future<\s*Object\?\s*>")
MAP_STRING_DYNAMIC = re.compile(r"Map\s*<\s*String\s*,\s*dynamic\s*>")
DYNAMIC_KEYWORD = re.compile(r"\bdynamic\b")
# 行首缩进 + 裸 dynamic/Object? 返回类型 + 标识符 + `(` 或 `<`（方法声明），不匹配参数（标识符后为 `,`/`)`）。
METHOD_RET = re.compile(r"^\s+(?:dynamic|Object\?)\s+\w+\s*[(<]")


def main() -> int:
    app_adapter_scopes = tuple(sorted(APP_TAG_ROOT.glob("*/adapters")))
    TAG_SCOPES = (*app_adapter_scopes, PACKAGE_TAG_ROOT)
    missing_scopes = [scope for scope in TAG_SCOPES if not scope.is_dir()]
    if not app_adapter_scopes:
        print(
            "verify_cloud_tag_strict_typing: BLOCK: canonical Tag adapter scope 为空",
            file=sys.stderr,
        )
        return 2
    if missing_scopes:
        for scope in missing_scopes:
            print(
                f"verify_cloud_tag_strict_typing: BLOCK: scope 不存在 {scope}",
                file=sys.stderr,
            )
        return 2

    violations: list[str] = []
    for scope in TAG_SCOPES:
        for f in sorted(scope.rglob("*.dart")):
            if f.name.endswith(".g.dart"):
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if (
                    FUTURE_DYNAMIC.search(line)
                    or FUTURE_OBJECTQ.search(line)
                    or MAP_STRING_DYNAMIC.search(line)
                    or DYNAMIC_KEYWORD.search(line)
                    or METHOD_RET.match(line)
                ):
                    violations.append(
                        f"{f.relative_to(ROOT)}:{i}: {line.strip()}"
                    )

    if violations:
        print(
            "verify_cloud_tag_strict_typing: FAIL "
            "（Tag 手写边界禁 dynamic/Map<String, dynamic> 及裸弱类型返回）"
        )
        for v in violations:
            print(f"  - {v}")
        print(
            "  修复：解码入口使用 Object?，并在同一函数内收口为 "
            "Map<String, Object?>、DTO 或 typed Slice。"
        )
        return 1

    print(
        "verify_cloud_tag_strict_typing: OK"
        "（Remote/pure contracts 无弱类型穿透）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
