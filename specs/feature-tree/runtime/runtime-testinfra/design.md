# Design: runtime-testinfra

> Status: implemented.

## Summary

`runtime-testinfra` 不再只指某个语言内的测试 helper，而是全仓三层测试迁移的基础设施层：

- 生成 canonical bridge
- 维护目录与页面清单真相源
- 为 acceptance `tests.recorded` 与 `artifacts/tests/**/report.json` 提供统一证据口径
- 通过独立门禁阻断伪迁移、假报告和 page matrix 漏洞

## Canonical Bridge 设计

### App

- `quwoquan_app/test/{local_contract,api_integration,user_acceptance}` 是唯一执行根
- legacy `ui/**`、`patrol/**`、分散根目录测试通过 Dart wrapper bridge 进入 canonical 根
- 页面级 `user_acceptance/pages/<owner>/<surface_id>/...` 由 page inventory 自动生成

### Service

- `quwoquan_service/services/<svc>/tests/{local_contract,api_integration}` 是唯一执行根
- Go bridge 使用最小 exec runner 回放 legacy suite，避免复制断言
- `classification_basis` 显式记录 `internal/cmd -> local_contract`、`tests -> api_integration`
  的归属依据

### Data / Ops

- `quwoquan_data/tests/{local_contract,api_integration,user_acceptance}` 与
  `agent_ops/tests/local_contract`、`agent_ops/acceptance/{api_integration,user_acceptance}` 成为唯一根
- Python bridge 使用 importlib wrapper，保证既有套件可被 canonical 根直接发现与执行

## Truth Sources

- `specs/gates/test_directory_inventory.yaml`
  - 记录 `current_path`、`target_path`、`classification_basis`、`migration_status`
  - version 2 以后 `pending_count` 表示尚未 bridge 的 suite 数，`bridged_count` 表示已桥接数
  - `pending_count=0` 只说明治理入口已被 canonical bridge 接管，不说明 legacy 文件已从磁盘移除
- `specs/gates/user_acceptance_page_inventory.yaml`
  - 记录 metadata `ui_surfaces`、`app_routes` 对应的 page owner、route 归属、source tests 与
    反向绑定 API tests

## Guardrails

- `verify-test-directory-layout`
  - 没有 canonical bridge 的 legacy 测试一律失败
- `verify-test-no-fake`
  - 扫描 canonical 根与 `artifacts/tests/**/report.json`，阻断占位测试、假断言、假报告
- `verify-test-coverage-map`
  - 校验 acceptance case id、canonical 测试文件、执行环境、report/artifact 一一可追溯
  - 阻断 page case 缺失、recorded 仍指向 legacy、implemented 但缺 lower-layer binding

## Constraints

- 不维护第二套 inventory、第二套页面矩阵或第二套 report 目录
- 不允许手写“绿色报告”替代真实 canonical 测试文件
- 任何 canonical remap 必须通过 bridge generator / inventory 真相源落地，不能只改 acceptance 文本
