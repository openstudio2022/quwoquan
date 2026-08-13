#!/usr/bin/env python3
"""聚合 Mock 替身退役棘轮。

`local_contract` 只允许对象级窄端口 typed double；聚合 `Mock*Repository` /
`Mock*Facets` 门面（多端口、多对象场景桶）是待退役存量。本门禁统计 App 测试树
中引用聚合替身符号的文件数，只减不增：迁移到对象级 typed double 的批次逐步把
棘轮推到 0，新增聚合替身立即阻断。

规格：specs/feature-tree/runtime/runtime-test-pyramid/spec.md#open-002
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = ROOT / "quwoquan_app" / "test"

#: 聚合替身符号：Mock + 聚合 Repository/Facets 门面命名。
AGGREGATE_MOCK_RE = re.compile(r"\bMock\w*(?:Repository|Facets)\b")

#: 引用文件数棘轮基线；只减不增，迁移批次同步下调。
AGGREGATE_MOCK_FILE_CEILING = 43


def main() -> int:
    if not TEST_ROOT.is_dir():
        print(f"[verify-app-aggregate-mock-ratchet] FAIL: missing {TEST_ROOT}")
        return 1
    referencing: list[str] = []
    for path in sorted(TEST_ROOT.rglob("*.dart")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if AGGREGATE_MOCK_RE.search(text):
            referencing.append(path.relative_to(ROOT).as_posix())
    count = len(referencing)
    if count > AGGREGATE_MOCK_FILE_CEILING:
        print(
            "[verify-app-aggregate-mock-ratchet] FAIL: aggregate Mock*Repository/"
            f"Mock*Facets references grew to {count} files "
            f"(> {AGGREGATE_MOCK_FILE_CEILING}); new suites must inject "
            "object-level typed ports instead of aggregate mock facades"
        )
        for item in referencing:
            print(f"  - {item}")
        return 1
    print(
        "[verify-app-aggregate-mock-ratchet] OK: aggregate mock files="
        f"{count} (ceiling={AGGREGATE_MOCK_FILE_CEILING})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
