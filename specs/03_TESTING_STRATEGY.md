# 三层测试策略与迁移真相源

本文是仓库三层测试治理的唯一执行规范。测试工程层只允许：

- `local_contract`
- `api_integration`
- `user_acceptance`

禁止再引入 `T1/T2/T3/T4`、`L1/L2/L3/L4` 作为测试目录、门禁名字、验收证据层或新测试资产命名。

## 1. 环境语义

| 测试层 | 主环境 | 说明 |
|---|---|---|
| `local_contract` | `alpha` / `local` | 本地契约、DTO/wire、metadata/codegen、Provider/Widget/纯函数、Mock/Remote 等价断言 |
| `api_integration` | `beta` / `gamma` | gateway/API、真实存储、错误码、requestId/traceId、一致性副作用、seed/fixture、回滚/降级 |
| `user_acceptance` | `gamma_local` / `prod_gray_initial` | 用户旅程、页面状态、主 CTA、权限/错误/空态、trace/referral/feedRequestId、发布前灰度验收 |

约束：

- 生产没有 `prod-gray` 环境；灰度只是 `prod` rollout stage。
- `user_acceptance` 的远端主证据来自 `gamma_local` 与 `prod_gray_initial`，而不是单独再维护第二套“远端 gamma”口径。

## 2. 顶层用例模型

统一 case id 口径：

- Journey：`user_acceptance.<journey_id>.<scenario_id>.<case>`
- Page：`user_acceptance.page.<surface_id>.<state_or_action>`
- Service/API：`api_integration.<domain>.<capability>.<story>.<case>`
- Local contract：`local_contract.<domain>.<capability>.<story>.<case>`

页面 case 的 `surface_id` 直接来自 metadata `ui_surfaces.yaml`；route-only 页面归属来自
`specs/gates/user_acceptance_page_inventory.yaml`，不再维护第二套人工页面清单。

每个已实现的 Journey / Page `user_acceptance` 用例都必须反向绑定：

- 至少 1 个 `local_contract`
- 至少 1 个 `api_integration`

缺任一层，不得标记为 `implemented` / `completed`。

## 3. 特性树映射

| 特性树层级 | 主验收意图 | 主证据 | 支撑证据 |
|---|---|---|---|
| `AppRoot` | `UAT` | `user_acceptance` | `api_integration` + `local_contract` |
| `L1_domain_service` | domain acceptance | `api_integration` | `local_contract`，必要时 `user_acceptance` |
| `L2_business_capability` | `SIT` | `api_integration` | `local_contract`，面向用户能力时补 `user_acceptance` |
| `L3_story` | `GWT` / `contract` | `local_contract` | 远端边界补 `api_integration`，页面/旅程补 `user_acceptance` |

## 4. 工程目录

### App

```text
quwoquan_app/test/
  local_contract/**
  api_integration/**
  user_acceptance/<journey>/**
  user_acceptance/pages/<owner>/<surface_id>/**
```

### Service

```text
quwoquan_service/services/<service>/tests/
  local_contract/**
  api_integration/**
```

说明：

- `internal/**`、`cmd/**` 的既有 Go 测试通过 canonical bridge 映射到 `tests/local_contract/**`
- `tests/**` 的 HTTP/真实存储/跨服务既有套件通过 canonical bridge 映射到 `tests/api_integration/**`

### Data

```text
quwoquan_data/tests/
  local_contract/**
  api_integration/**
  user_acceptance/**
```

### Ops

```text
agent_ops/tests/local_contract/**
agent_ops/acceptance/api_integration/**
agent_ops/acceptance/user_acceptance/**
```

## 5. 物理迁移与 bridge

全仓 legacy 测试源文件允许暂时保留在原目录，但从治理角度一律不再作为执行真相源：

- 执行、门禁、`tests.recorded`、目录规范只认 canonical 三层根
- legacy 到 canonical 的映射以 `specs/gates/test_directory_inventory.yaml` 为唯一清单
- 允许继续存在的 legacy 源文件白名单以 `specs/gates/test_legacy_source_allowlist.yaml` 为唯一 ratchet；新增测试不得再通过“legacy + bridge”进入仓库
- canonical bridge 由 `agent_ops/scaffold/generate_canonical_test_bridges.py` 生成
- 任何新增 legacy 测试路径如果没有 canonical bridge，会被 `verify-test-directory-layout` 阻断
- bench-only legacy runner 必须显式登记到 `test_legacy_source_allowlist.yaml`；当前仅保留已登记存量例外

说明：

- canonical bridge / inventory 收口表示“治理执行面完成”，不等于“legacy 测试文件已经全部物理搬迁或从磁盘移除”
- `specs/gates/test_directory_inventory.yaml` 中的 `pending_count` 只表示“仍未 bridge 的 legacy suite 数量”，不是磁盘上 legacy 文件总数

## 6. Acceptance / Evidence

规则：

- `tests.recorded` 只允许：
  - canonical 三层测试文件
  - `artifacts/tests/**/report.json`
- 旅程与页面的主证据优先落在 `user_acceptance`
- 带 `surface` / `route` 的 Story 必须在 page inventory 中登记；metadata surface 必须有 page-level `user_acceptance` wrapper
- 文档、脚本、命令、markdown 报告不再作为 `tests.recorded` 主证据；如需保留，只能进 `notes` / `contract_refs`

## 7. 门禁

统一测试治理门：

```bash
make verify-test-specs
make verify-test-directory-layout
make verify-test-no-fake
make verify-test-coverage-map
make verify-test-remote-env MODE=api_integration ENV=beta|gamma|prod
make verify-test-remote-env MODE=user_acceptance TARGET=prod-hosted
```

含义：

- `verify-test-specs`：验收 schema、三层 case id、状态与字段约束
- `verify-test-directory-layout`：legacy→canonical 映射、bridge 覆盖率，以及 no-new-legacy-tests ratchet
- `verify-test-no-fake`：同时扫描 canonical bridge 与其背后的 legacy 源文件，禁止空断言、纯跳过、伪 report；存量 skip / bench-only 仅允许显式登记例外
- `verify-test-coverage-map`：校验 acceptance、canonical 测试文件、page inventory、环境层与 recorded/artifact 可追溯；strict traceability 可按 feature node 或单个 acceptance item 逐步扩围，一旦纳入即必须保证 `test_evidence.cases[] -> canonical file / report.json.case_results[]` 可直连
- `verify-test-remote-env`：在真正触发远端 `api_integration` / hosted `user_acceptance` 前，先检查 base URL、product-ops URL、token 与 Patrol CLI wiring

执行入口：

```bash
make test-local-contract
make test-api-integration ENV=beta|gamma|prod
make test-user-acceptance TARGET=local|gamma-local|prod-hosted
make gate
make gate-full
```

约束：

- `make gate` 必须阻断 `schema + directory + no-fake + coverage-map + local_contract`
- `make gate-full` 必须在 `make gate` 之上补 `api_integration + gamma_local user_acceptance`
- 发布前只认 `prod_gray_initial` 的只读/幂等 `api_integration` 和 Journey/Page `user_acceptance`

## 8. 页面真相源

页面验收真相源统一为：

- metadata：`quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml`
- route：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml`
- page inventory：`specs/gates/user_acceptance_page_inventory.yaml`

每个 surface 至少覆盖：

- `load_success`
- `empty_permission_error`
- `primary_cta`
- `trace_context`

## 9. 当前迁移状态

本轮迁移后，canonical bridge 与 page inventory 已成为治理入口：

- App / Service / Data / Ops 全域 canonical bridge 已落盘
- `tests.recorded` 已统一 canonical 化，不再引用 legacy 路径
- `user_acceptance.page.*` 已由 metadata surface 矩阵生成并进入 acceptance/gate
- backlog `R-TST01` / `R-TST02` 的关闭标准是“bridge 落盘、coverage-map 生效、evidence 回写且完成定义无歧义”，不是“legacy 文件已全部物理搬迁完毕”
