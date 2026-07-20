# L2 特性：Runtime Testinfra

## Summary

`runtime-testinfra` 负责把三层测试迁移所需的基础设施、bridge 生成、目录清单、report 结构和页面矩阵真相源变成可重复执行的仓库能力。

## In Scope

- `generate_canonical_test_bridges.py` 生成 App / Service / Data / Ops canonical bridge
- `generate_test_directory_inventory.py` 与 `specs/gates/test_directory_inventory.yaml`
- `specs/gates/test_legacy_source_allowlist.yaml`
- `specs/gates/user_acceptance_page_inventory.yaml`
- `artifacts/tests/**/report.json` 的报告口径
- Go / Python / Dart bridge runner 的最小执行契约

## Core Rules

- 任何新增 legacy 测试文件，若无 canonical bridge，`verify-test-directory-layout` 必须失败
- 任何新增 legacy 测试文件，即使同步补了 bridge，也必须因 `test_legacy_source_allowlist.yaml` ratchet 而失败；新增测试只能直接落 canonical 根
- 页面 inventory 必须与 metadata `ui_surfaces` / `app_routes` 同步
- bridge 是执行入口，不得把 fake assertion、手写绿报告或纯说明文档当作测试证据；`verify-test-no-fake` 必须同时扫描 canonical bridge 与其背后的 legacy 源
- 不为 App / Service / Data / Ops 维护第二套目录清单或第二套页面矩阵
- bench-only legacy runner 必须显式登记例外；未登记的 benchmark-only 源文件不得混入 `api_integration` 命名空间

## Done When

- canonical bridge 可覆盖全仓现有 legacy suite
- inventory 中 `pending=0`，且该状态只表示“全部 legacy suite 已被 canonical bridge 接管”，不表示 legacy 文件已从磁盘移除
- `test_legacy_source_allowlist.yaml` 只减不增；如需新增条目，必须先被视为新的治理风险并单独评审
- page inventory 与 metadata surface/route 无漂移
- `verify-test-no-fake` 与 `verify-test-coverage-map` 能独立阻断伪迁移与证据漂移
