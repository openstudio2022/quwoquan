#!/usr/bin/env python3
"""推荐标签链路 StrictTyping 门禁。

把 cloud_map_typing_audit_anchor.dart 的 StrictTyping 规范（"跨文件不得用裸
`dynamic`/`Object?` 作业务契约；`Object?` 仅见于解码入口、下一跳须转 DTO 或
CloudJsonMap"）落为可执行门禁，覆盖此前盲区：verify_ui_map_literal_budget 只锁
lib/ui、report_map_typing_baseline 仅报告非门禁。

scope: quwoquan_app/lib/cloud/services/tag/**/*.dart（推荐标签链路）。

FAIL 条件（裸弱类型返回契约）:
  - `Future<dynamic>` / `Future<Object?>`（HTTP 中转裸返回，应直出 DTO/List<DTO>）。
  - 方法/函数返回类型为裸 `dynamic` / `Object?`（如 `dynamic _get(` / `Object? _post(`）。

豁免（合规，不计 FAIL）:
  - `Object? decoded` 等【解码入口参数】（参数非返回契约）。
  - `CloudJsonMap` / `Map<String, dynamic>` 局部 parse 与 DTO `fromJson` 入参。

用法: python3 quwoquan_app/scripts/runtime/verify_cloud_tag_strict_typing.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TAG_DIR = ROOT / "quwoquan_app" / "lib" / "cloud" / "services" / "tag"

FUTURE_DYNAMIC = re.compile(r"Future<\s*dynamic\s*>")
FUTURE_OBJECTQ = re.compile(r"Future<\s*Object\?\s*>")
# 行首缩进 + 裸 dynamic/Object? 返回类型 + 标识符 + `(` 或 `<`（方法声明），不匹配参数（标识符后为 `,`/`)`）。
METHOD_RET = re.compile(r"^\s+(?:dynamic|Object\?)\s+\w+\s*[(<]")


def main() -> int:
    if not TAG_DIR.is_dir():
        print(
            f"verify_cloud_tag_strict_typing: BLOCK: scope 不存在 {TAG_DIR}",
            file=sys.stderr,
        )
        return 2
    violations: list[str] = []
    for f in sorted(TAG_DIR.rglob("*.dart")):
        if f.name.endswith(".g.dart"):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if (
                FUTURE_DYNAMIC.search(line)
                or FUTURE_OBJECTQ.search(line)
                or METHOD_RET.match(line)
            ):
                violations.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()}")

    if violations:
        print(
            "verify_cloud_tag_strict_typing: FAIL "
            "（推荐标签链路禁裸 Future<dynamic>/Future<Object?> 或裸 dynamic/Object? 返回契约）"
        )
        for v in violations:
            print(f"  - {v}")
        print(
            "  修复：经 CloudResponseDecoder 直出 DTO/List<DTO>/CloudJsonMap"
            "（见 tag_repository_remote 的 _getList/_getObject/_postList/_postObject）。"
        )
        return 1

    print(
        "verify_cloud_tag_strict_typing: OK"
        "（lib/cloud/services/tag 无裸 dynamic/Object? 返回契约）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
