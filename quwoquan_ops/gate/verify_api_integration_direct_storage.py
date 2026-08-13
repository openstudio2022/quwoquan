#!/usr/bin/env python3
"""api_integration 直插存储的 persistence 专项区分棘轮。

api_integration 的前置状态只能经真实进程的 application command 或
provider-state harness 构造；对存储的直接写入只允许显式声明的专项形态：

1. 文件名携带 ``__data_consistency__`` facet（persistence adapter、migration、
   corruption recovery 专项）；
2. 文件名以 ``contract_provider_state_persistence`` 开头（provider-state
   harness 本体，即构造前置状态的 canonical 通道）；
3. 包级 seed/setup harness：basename 去掉 ``__api_integration_test.go`` 后以
   ``__support`` 或 ``_test_support`` 结尾，是同包 contract 用例共享的前置
   状态收口点，业务断言不得写在 harness 文件内。

专项之外的直插存量以棘轮圈住只减不增：迁移批次改走公开 command/provider-state
或补专项声明后同步下调基线，新增一般用例直插立即阻断。

规格：specs/feature-tree/runtime/runtime-test-pyramid/design.md#dec-005
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = ROOT / "quwoquan_service" / "services"

#: 直接写存储的语法特征；readback 断言（读操作）是合法验证手段，不在扫描面。
#: DeleteMany 清库属 harness 用例间隔离，不构造业务事实，同样不在扫描面
#: （带业务过滤器的删除若要构造前置状态，必然伴随 Insert/Update 被捕获）。
#: 覆盖 pgx Pool/Tx/Conn 的 SQL 写句与 Mongo 全部单/多文档写形态；
#: Mongo Update/Replace/FindOneAnd*/BulkWrite 不限定首参形态
#: （ctx 变量或 context.Background() 均命中）。
DIRECT_WRITE_RE = re.compile(
    r"pgPool\.Exec\("
    r"|\.Exec\(\s*(?:ctx|context\.Background\(\))\s*,\s*[\"`]\s*(?:INSERT|UPDATE|DELETE)"
    r"|\bInsertOne\("
    r"|\bInsertMany\("
    r"|\bUpdateOne\("
    r"|\bUpdateMany\("
    r"|\bReplaceOne\("
    r"|\bFindOneAndUpdate\("
    r"|\bFindOneAndReplace\("
    r"|\bBulkWrite\("
)

#: 一般用例直插文件数棘轮基线；只减不增，迁移批次同步下调。
#: 基线随扫描口径收紧重定（补齐 Mongo Update/Replace/FindOneAnd*/BulkWrite
#: 与跨行 SQL 写句形态），并随 user_account 首批 harness 归并下调；
#: circle `file_owner/placement_owner` 两件为口径收紧同窗口的并行增量，
#: 与同包 owner contract 同族并入留置批次。剩余存量为 harness 改造批次
#: 留置项（chat 会话组、content 供给组、user/circle 多处直插 contract
#: seed），见 runtime-test-pyramid OPEN-002。
DIRECT_STORAGE_FILE_CEILING = 28


def is_declared_specialised(name: str) -> bool:
    if "__data_consistency__" in name or name.startswith(
        "contract_provider_state_persistence"
    ):
        return True
    subject = name.removesuffix("__api_integration_test.go")
    return subject.endswith("__support") or subject.endswith("_test_support")


def main() -> int:
    if not SERVICES_ROOT.is_dir():
        print(f"[verify-api-integration-direct-storage] FAIL: missing {SERVICES_ROOT}")
        return 1
    residue: list[str] = []
    for path in sorted(SERVICES_ROOT.rglob("*__api_integration_test.go")):
        relative = path.relative_to(ROOT).as_posix()
        if "/tests/api_integration/" not in relative:
            continue
        if is_declared_specialised(path.name):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if DIRECT_WRITE_RE.search(text):
            residue.append(relative)
    count = len(residue)
    if count > DIRECT_STORAGE_FILE_CEILING:
        print(
            "[verify-api-integration-direct-storage] FAIL: undeclared direct-storage "
            f"api_integration files grew to {count} (> {DIRECT_STORAGE_FILE_CEILING}); "
            "build preconditions through application commands or the provider-state "
            "harness, or declare the persistence speciality via the "
            "'__data_consistency__' facet"
        )
        for item in residue:
            print(f"  - {item}")
        return 1
    print(
        "[verify-api-integration-direct-storage] OK: undeclared direct-storage files="
        f"{count} (ceiling={DIRECT_STORAGE_FILE_CEILING})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
