# L2 特性：Runtime Test Pyramid

## Summary

`runtime-test-pyramid` 是全仓三层测试治理的能力真相源，负责把：

- `alpha` 的 smoke 投影与 `local_contract`
- `beta/gamma` 内容数据面的 `api_integration`
- `gamma/prod` 的商业准出 `user_acceptance`

串成单一、自洽、可门禁的迁移与执行模型。

## In Scope

- 三层测试层与四环境语义的统一命名和阻断规则
- Journey / Page 顶层 case 模型
- canonical 目录、`tests.recorded` 与 `.qwq_output/env/repo/runs/tests/**/report.json` 口径
- `verify-test-specs` / `verify-test-directory-layout` / `verify-test-no-fake` / `verify-test-coverage-map`
- `make gate` / `make gate-smoke` / `make gate-integration ENV=<beta|gamma>` /
  `make gate-release ENV=<gamma|prod>`

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

### 4. 目录与证据

- 测试文件只允许位于 canonical 三层目录；不保留 bridge、旧目录或豁免清单。
- `tests.recorded` 只可引用 canonical 测试源或可删除的运行证据。
- 运行报告只写 `.qwq_output/env/repo/runs/tests/**`，不得进入源码或 `artifacts/`。

### 5. 门禁

- `make gate`：baseline，只运行规格、目录、非功能契约、coverage 与 local contract。
- `make gate-smoke`：alpha smoke，验证固定投影、关键页面/API/导入形状和恢复契约。
- `make gate-integration ENV=beta|gamma`：内容数据面 full-sync、API、媒体、幂等、回滚/replay；不读取 SLS。
- `make gate-release ENV=gamma|prod`：商业观测、真机 UAT、SLO 与生产灰度；外部条件缺失必须 `GATE_BLOCK`。
- `verify-test-no-fake` 只扫描 canonical 测试源与当前运行证据，阻断 wrapper 伪绿。

## Exit Evidence

本能力关闭时必须能证明：

- metadata surface/page matrix 完整覆盖
- `tests.recorded` 只引用 canonical 三层测试或 `.qwq_output/env/repo/runs/tests/**/report.json`
- App / Service / Data / Ops canonical 根全部落地，并成为唯一执行入口
- `R-TST01` / `R-TST02` 已在 backlog 回写关闭与验证证据
