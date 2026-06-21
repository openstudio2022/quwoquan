# 三层测试策略与工程目录规范

本文是仓库测试体系的唯一执行规范。特性树仍表达产品与领域责任，测试工程只使用三层：

- `local_contract`
- `api_integration`
- `user_acceptance`

禁止新增以 `T1/T2/T3/T4` 作为测试目录、证据层或新验收字段；存量历史文本只能作为迁移前记录存在，新增验收必须使用三层测试证据。

## 1. 三层定义

| 测试层 | 环境 | 测试对象 | 测试策略 |
|---|---|---|---|
| `local_contract` | 本地开发机、CI、alpha fixture | 单模块、领域规则、DTO/wire、metadata、错误码、Provider、Widget、MockRepository、纯函数、handler 内部契约 | 快速、确定性、无外部网络；优先 Red -> Green；用 fixture 和 typed contract 证明最小行为 |
| `api_integration` | beta、gamma-local、prod rollout 只读/幂等阶段 | RemoteRepository、gateway/API、真实存储、事件/outbox、跨服务读写一致性、错误响应、trace/request id | 端云契约和真实环境一致性；beta 支持人工验收，gamma-local 自动化镜像验证，prod 只跑低风险健康与回滚对账 |
| `user_acceptance` | gamma-local、prod rollout、设备矩阵 | 用户旅程、页面功能、UI/UX 可用性、页面生命周期、权限、弱网、冷启动、灰度包、观测/SLO | 从用户价值出发；覆盖主路径、失败路径、边界、恢复动作、页面状态、埋点和发布准出 |

## 2. 特性树映射

特性树不是测试层。测试层只回答“如何证明”，特性树回答“证明什么”。

| 特性树层级 | 关注点 | 验收表达 | 主证据 | 支撑证据 |
|---|---|---|---|---|
| `AppRoot` | 跨领域 Journey / Scenario、产品 superpower、发布前用户价值 | UAT 用户验收用例，不使用 GWT | `user_acceptance` | `api_integration` |
| `L1_domain_service` | 领域边界、上下游依赖、权限、生命周期、观测、发布 guardrails | domain acceptance | `api_integration` | `local_contract`，必要时 `user_acceptance` |
| `L2_business_capability` | 多 Story 组合、状态机、端云协作、数据一致性 | SIT 能力验收用例 | `api_integration` | `local_contract`，面向用户能力补 `user_acceptance` |
| `L3_story` | 最小可闭环价值点 | GWT + contract | `local_contract` | 远端边界补 `api_integration`，页面行为补 `user_acceptance` |

`contract_acceptance` 是 L3 或 metadata 的契约验收块，必须与 `gwt_acceptance` 一样被主校验器覆盖。

## 3. 工程目录

新增测试必须优先使用三层目录。存量目录通过 `specs/gates/test_directory_inventory.yaml` 清单映射逐步收敛，并由 `make verify-test-directory-layout` 阻断任何新增 legacy 测试路径。

### App

```text
quwoquan_app/test/
  local_contract/<domain>/<capability>/<story>/<case>_test.dart
  api_integration/<domain>/<capability>/<story>/<case>_test.dart
  user_acceptance/<journey_id>/<scenario_id>/<case>_test.dart
  user_acceptance/pages/<domain>/<surface_id>/<case>_test.dart
```

存量映射：

- `test/cloud/**`：按是否访问真实环境映射到 `local_contract` 或 `api_integration`。
- `test/ui/**`、`test/components/**`、`test/core/**`：默认映射到 `local_contract`；若表达完整页面验收，迁入 `user_acceptance/pages/**`。
- `test/patrol/**`：映射到 `user_acceptance`。
- `integration_test/**` 不作为仓库测试分层入口。

### Service

```text
quwoquan_service/services/<service>/tests/
  local_contract/<story_or_contract>_test.go
  api_integration/<api_or_flow>_test.go
```

存量 `services/<service>/tests/*_contract_test.go` 先映射到 `local_contract` 或 `api_integration`，后续随触达迁移。

### Ops / Release

```text
agent_ops/acceptance/
  api_integration/<domain>/<suite>.yaml
  user_acceptance/<journey_id>/manifest.yaml
  lib/**
```

`agent_ops/acceptance/lib/**` 只放 runner、HTTP client、断言、report 结构和环境解析，不放业务假数据。

## 4. 命名

- 用例 ID：`<layer>.<domain>.<capability>.<story>.<case>`。
- Journey 用例：`user_acceptance.<journey_id>.<scenario_id>.<case>`。
- 页面用例：`user_acceptance.page.<surface_id>.<state_or_action>`。
- API 用例：`api_integration.<domain>.<operation_id>.<case>`。
- 本地契约用例：`local_contract.<domain>.<contract_or_story>.<case>`。
- 文件名：`<story_or_operation>__<layer>_test.<ext>` 只适用于 canonical 三层根目录。legacy 源文件可暂保留原名，但必须被 `test_directory_inventory.yaml` 映射，且其 canonical 目标路径必须遵守该命名。
- 报告：`artifacts/tests/<layer>/<env>/<suite>/<run_id>/report.json`。

## 5. Acceptance Schema

验收项必须使用 `test_evidence`：

```yaml
test_evidence:
  primary:
    - layer: user_acceptance
      suite: profile_identity_sync
      cases:
        - user_acceptance.profile_identity_sync.create_update_sync
      envs: [gamma, prod]
  supporting:
    - layer: api_integration
      suite: user_profile_api
      cases:
        - api_integration.user.get_me.default_nickname
      envs: [beta, gamma]
tests:
  planned: []
  recorded: []
```

规则：

- `test_evidence.primary` 必须非空。
- `layer` 只能是 `local_contract`、`api_integration`、`user_acceptance`。
- `cases` 中每个 case id 必须以对应 `layer` 开头。
- `envs` 只能使用 `local`、`alpha`、`beta`、`gamma`、`prod`。
- `status` 仅允许 `pending`、`partial`、`implemented`、`completed`、`pending_evidence`、`blocked`。
- `status` 为 `implemented` 或 `completed` 时，`tests.recorded` 必须非空且引用真实存在的测试文件、命令或报告。
- `tests.planned` / `tests.recorded` 只能使用结构化 `file` / `command` / `artifact` 记录，不允许富文本串联说明。
- 不允许在验收项中新增旧字段 `evidence`。

## 6. 命令与门禁

统一命令入口：

```bash
make test-local-contract
make test-api-integration ENV=beta|gamma|prod
make test-user-acceptance TARGET=gamma-local|prod-hosted ROLLOUT_STAGE=<stage>
make verify-test-specs
make verify-test-directory-layout
make verify-test-no-fake
make verify-test-coverage-map
```

门禁分层：

- `make gate`：必须覆盖 `local_contract`、`verify-test-specs`、`verify-test-directory-layout`。
- `make gate-full`：必须覆盖 `local_contract + api_integration + gamma user_acceptance`。
- 发布前 prod rollout：必须补 `api_integration` 只读/幂等校验、`user_acceptance` 灰度旅程、SLO/告警/回滚证据。

## 7. 防造假

- 禁止手写全绿 `report.json` 充当测试结果。
- 禁止空断言、全 skip、`assert true`、只凭富文本输出宣称通过。
- 测试通过必须以退出码、机器可读 report、真实测试文件和可复跑命令共同证明。
- 输出损坏或日志截断时，以退出码、JUnit/JSON/report 和二次交叉验证为准。

## 8. SDD / DevOps / 超级自动化接入

- `/prd`：冻结用户价值、验收表达和三层证据计划。
- `/design`：在 AppRoot/L1/L2 层说明测试边界、环境、观测、回滚和自动化入口。
- `/dev`：从 Story GWT/contract 下钻到 `local_contract`，再补必要 `api_integration` 和 `user_acceptance`。
- `/verify`：按三层证据回收真实命令、退出码、report 和剩余风险。
- `/continue` 或自然语言续作：必须先读当前 acceptance 与最近 report，禁止凭聊天记忆宣称完成。
- Vibe coding：聊天中对齐规格也必须形成 Spec Entry、Pre-work Reflection、Exit Review，并落到三层测试证据。

## 9. 用户资料试点

用户资料创建到更新作为三层覆盖示范：

- `local_contract.user.profile.default_nickname_format`
- `local_contract.app.edit_profile_page.dirty_state`
- `api_integration.user.update_profile.patch_and_versions`
- `api_integration.chat.profile_snapshot_alignment`
- `user_acceptance.profile_identity_sync.create_update_chat_sync`

该试点必须能从 AppRoot UAT 下钻到 L2 SIT、L3 GWT/contract、工程 case id 和真实 `report.json`。
