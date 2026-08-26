#!/usr/bin/env python3
"""Validate the derived spec_ref-to-test coverage map.

The map is rebuilt from physical test files on every run. No inventory or
recorded test path is accepted as an input truth source.

spec_ref 语法解析复用 feature-tree 库唯一 lexical 入口 ``extract_spec_refs``
（同行 marker 与列表块两种显式形态同源生效，裸字符串不计）；本门只保留
语义校验：验收锚点类型过滤、`.tN` 子句剥离到主锚点、spec 文件与锚点存在性。
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
# 导入仓内包前禁写字节码：裸跑本 gate 不得在源码树留 __pycache__（与
# cli/feature_tree.py 等入口惯例一致）。
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# 完全限定包路径导入：顶层名 `feature_tree` 被 cli/feature_tree.py 薄壳占用，
# 短名导入会在同进程（如 pytest 全目录收集）中与其冲突。
from quwoquan_ops.cli.lib.feature_tree.evidence import extract_spec_refs  # noqa: E402

TEST_ROOTS = (
    ROOT / "quwoquan_app/test",
    ROOT / "quwoquan_data/tests",
    ROOT / "quwoquan_ops/tests",
    ROOT / "quwoquan_service/services",
    ROOT / "quwoquan_service/control-plane",
)
# 本门只关注验收锚点绑定；`.tN` 子句剥离到主锚点，其余锚点（req/dec 等）不进映射。
CASE_ANCHOR = re.compile(r"^((?:uat|dom|sit|gwt)-\d+)(?:\.t\d+)?$", re.IGNORECASE)
TEST_FILE = re.compile(
    r"(?:_test\.go|_test\.dart|_test\.py|__local_contract_test\.go|"
    r"__api_integration_test\.go)$"
)


def test_files() -> list[Path]:
    result: list[Path] = []
    for root in TEST_ROOTS:
        if not root.is_dir():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file() or not TEST_FILE.search(candidate.name):
                continue
            if any(part in {"vendor", ".dart_tool", "generated"} for part in candidate.parts):
                continue
            result.append(candidate)
    return sorted(set(result))


def case_bindings(source: str) -> list[tuple[str, str]]:
    """返回源码中显式绑定的 (spec_path, 主锚点) 列表，同文件去重后排序。"""
    bindings: set[tuple[str, str]] = set()
    for ref in extract_spec_refs(source):
        spec_path, _, raw_anchor = ref.partition("#")
        match = CASE_ANCHOR.match(raw_anchor)
        if match is None:
            continue
        bindings.add((spec_path, match.group(1).lower()))
    return sorted(bindings)


def main() -> int:
    failures: list[str] = []
    mapping: list[tuple[str, str]] = []
    for test in test_files():
        source = test.read_text(encoding="utf-8", errors="replace")
        for spec_path, case_id in case_bindings(source):
            spec = ROOT / spec_path
            reference = f"{spec_path}#{case_id}"
            if not spec.is_file():
                failures.append(f"missing spec target: {reference} <- {test.relative_to(ROOT)}")
                continue
            spec_source = spec.read_text(encoding="utf-8", errors="replace").lower()
            anchor = f'<a id="{case_id}"></a>'
            if anchor not in spec_source:
                failures.append(f"missing case anchor: {reference} <- {test.relative_to(ROOT)}")
                continue
            mapping.append((reference, test.relative_to(ROOT).as_posix()))

    if not mapping:
        failures.append("no physical tests declare a stable spec_ref")
    if failures:
        for failure in failures:
            print(f"[verify-test-coverage-map] FAIL: {failure}")
        return 1
    counts = Counter(reference.split("#", 1)[1].split("-", 1)[0] for reference, _ in mapping)
    print(
        "[verify-test-coverage-map] OK: "
        f"bindings={len(mapping)}, tests={len(set(test for _, test in mapping))}, "
        f"layers={dict(sorted(counts.items()))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
