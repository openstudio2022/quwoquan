# Runtime Test Pyramid

## Summary

`runtime-test-pyramid` 是全仓三层测试治理的能力真相源，负责把：

- `gamma-local + prod gray-initial` 的 Journey / Page `user_acceptance`
- `beta/gamma` 的 `api_integration`
- `alpha/local` 的 `local_contract`

串成单一、自洽、可门禁的迁移与执行模型。

## In Scope

- 三层测试层与四环境语义的统一命名和阻断规则
- Journey / Page 顶层 case 模型
- canonical 目录、bridge、`tests.recorded` 与 `artifacts/tests/**/report.json` 口径
- `verify-test-specs` / `verify-test-directory-layout` / `verify-test-no-fake` / `verify-test-coverage-map`
- `make gate` / `make gate-full` / `test-local-contract` / `test-api-integration` / `test-user-acceptance`

## Out Of Scope

- 具体某个业务 Story 的产品行为细节
- 替代各域已有的 service / app / data 专项验证脚本
- 生产灰度的审批、放量或回滚流程本身

## Core Rules

### 1. 三层 only

测试工程层只允许：

- `local_contract`
- `api_integration`
- `user_acceptance`

不再新增 `T1-T4`、`L1-L4`、`contract-test` 等第二口径目录或 case id。

### 2. 顶层真相源

- Journey case：`user_acceptance.<journey_id>.<scenario_id>.<case>`
- Page case：`user_acceptance.page.<surface_id>.<state_or_action>`
- 页面清单来自 metadata `ui_surfaces.yaml` / `app_routes.yaml`
- `specs/gates/user_acceptance_page_inventory.yaml` 是页面 owner、route-only 归属、source test 与反向绑定的真相源

### 3. 反向绑定

任何已实现的 Journey / Page `user_acceptance` case，都必须至少绑定：

- 1 个 `local_contract`
- 1 个 `api_integration`

否则不得标记为 `implemented` / `completed`。

### 4. 目录与 bridge

- 执行入口只认 canonical 三层目录
- legacy 测试源文件可暂留原处，但必须有 canonical bridge，且 `tests.recorded` 不得再直接引用 legacy 路径
- bridge 覆盖与目录状态以 `specs/gates/test_directory_inventory.yaml` 为唯一清单
- 允许继续存在的 legacy 源测试与 bench-only / skip grandfathering 例外以 `specs/gates/test_legacy_source_allowlist.yaml` 为唯一清单；新增测试不得再走 legacy + bridge 路线
- canonical 根成为唯一执行/证据真相源，并不自动表示 legacy 测试文件已从磁盘物理迁走

### 5. 门禁

- `make gate`：schema + directory + no-fake + coverage-map + local_contract
- `make gate-full`：`make gate` + `api_integration` + `gamma_local user_acceptance`
- 发布前远端只认 `prod gray-initial` 的只读/幂等 `api_integration` 与 Journey/Page `user_acceptance`
- `verify-test-no-fake` 必须同时扫描 canonical bridge、legacy 源文件与 `artifacts/tests/**/report.json`，防止 wrapper 伪绿或 legacy source 伪绿

## Exit Evidence

本能力关闭时必须能证明：

- metadata surface/page matrix 完整覆盖
- `tests.recorded` 只引用 canonical 三层测试或 `artifacts/tests/**/report.json`
- App / Service / Data / Ops canonical 根全部落地，并成为唯一执行入口
- `R-TST01` / `R-TST02` 已在 backlog 回写关闭与验证证据
