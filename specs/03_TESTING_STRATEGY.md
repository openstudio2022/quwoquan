# 三层测试策略与治理规范

本文是仓库测试目录、命名、统计、覆盖与门禁的唯一执行规范。

## 1. 唯一测试层

测试目录层只允许三类：

- `local_contract`
- `api_integration`
- `user_acceptance`

`alpha`、`beta`、`gamma`、`prod` 只是 runner、配置、报告和证据维度，不允许作为测试目录层级。生产灰度是 `prod` rollout stage，不存在独立 `prod-gray` 测试目录或环境。

## 2. Coverage Spine

覆盖治理沿同一条脊柱追踪：

```text
Journey -> Scenario -> Surface/Page -> App boundary -> API operation
  -> Service capability -> Store/Event/Data release -> Observability/SLO
```

统计字段统一为：

```text
area / layer / domain_service / service / test_object / quality_facet
env / rollout_stage / case_id / source_file / recorded_artifact
```

`quality_facet` 闭集：

- `functional`
- `contract`
- `reliability`
- `availability`
- `observability`
- `experience`
- `security`
- `performance`
- `data_consistency`

`rollout_stage` 只用于生产发布阶段，例如 `gray_initial`。它不能替代环境；生产灰度必须表达为 `env=prod` + `rollout_stage=gray_initial`，不得写成 `prod_gray_initial` 或 `prod-gray` 环境。

`test_object` 闭集：

| area | allowed test_object |
|---|---|
| App | `page`、`component`、`widget`、`provider`、`repository`、`mapper`、`route`、`runtime_config`、`observability`、`security_policy`、`performance_budget` |
| Service | `metadata`、`handler`、`application_service`、`domain_rule`、`store_repository`、`message_event`、`api_operation`、`job`、`config_release`、`observability` |
| Data | `schema`、`cli_command`、`workflow`、`source_adapter`、`quality_gate`、`publisher`、`importer`、`release_bundle` |
| Ops | `stackctl_command`、`environment_topology`、`package_contract`、`deploy_gate`、`observability_collector`、`portal_surface` |
| Rec-model | `algorithm`、`model_contract`、`feature_pipeline`、`serving_api`、`evaluation`、`performance` |

## 3. 非功能质量矩阵

非功能测试不新增第四层目录，统一通过 `quality_facet` 横切到三层测试。每个可发布 feature、页面、API 或服务能力都要判断下列维度是否适用；适用但缺证据时必须返回 `GATE_BLOCK`。

| 质量维度 | local_contract | api_integration | user_acceptance |
|---|---|---|---|
| 异常与恢复 | 错误码、mapper、Provider/UI 状态、恢复按钮、Mock 错误响应 | HTTP status、RuntimeErrorResponse、request/trace、真实错误边界 | 用户旅程中的错误提示、权限态、重试、降级 |
| 性能 | 预算静态检查、算法容量、组件渲染预算 | API P95/P99、队列 lag、存储查询、推理延迟 | 启动、滚动、首屏、交互反馈、弱网体验 |
| 安全与隐私 | 权限矩阵、脱敏、secret/token 禁止入日志、隐私配置 | auth/authz negative cases、越权、幂等、审计记录 | 登录、权限、隐私设置用户路径 |
| 可观测 | 事件字典、log 字段白名单、metrics 命名、trace 传播 | RED 指标、access/exception/event/audit、trace/request 串联 | 页面 open/return/perf、关键行为上报、端云关联 |
| 可靠性/可用性 | retry/backoff、timeout、offline queue、幂等状态机 | 依赖失败、MQ/outbox、回滚、健康检查 | 断网、恢复、降级路径 |
| 数据一致性 | schema、投影、去重、稳定 ID | 真实存储读写、导入/发布、事件最终一致 | 用户看到的数据与发布、推荐、行为归因一致 |

性能阈值必须来自 `spec.md`、`acceptance.yaml` 或 SLO 文档，不能在测试中自造第二真相源。日志、指标、trace、audit 继续遵守瘦身后的 observability 合同。

## 4. 目录合同

### App

```text
quwoquan_app/test/
  local_contract/
    ui/
    cloud/
    core/
    app/
    quality/
  api_integration/
    ui/
    cloud/
    observability/
    security/
    performance/
  user_acceptance/
    journeys/
    pages/
    patrol/
    quality/
  support/
```

### Service

```text
quwoquan_service/services/<service>/tests/
  local_contract/
  api_integration/
  support/
```

服务包内 `cmd/**`、`internal/**` 的 Go 白盒测试可以保留在被测包旁，但文件名必须以 `__local_contract_test.go` 结束。跨环境 smoke、device matrix、deployment proof 归 `quwoquan_ops/tests/acceptance/**`，禁止回流到服务私有 ops 测试分支。

算法服务 `rec-model-service` 使用同一层级：

```text
tests/local_contract/{algorithm,model_contract,data_contract,performance}/
tests/api_integration/{serving_api,cross_service,observability}/
```

### Data

```text
quwoquan_data/tests/
  local_contract/
  api_integration/
  user_acceptance/
  support/
```

### Ops

```text
quwoquan_ops/tests/
  local_contract/
  acceptance/
    api_integration/
    user_acceptance/
  support/
```

`support/` 只放 fixture、harness、fake、builder，禁止放测试文件。

## 5. 文件命名与 Case ID

文件名必须带物理层后缀：

- Dart：`<subject>__<case>__[facet]__<layer>_test.dart`
- Go：`<subject>__<case>__[facet]__<layer>_test.go`
- Python：`test_<subject>__<case>__[facet]__<layer>_test.py`

其中 `[facet]` 取值只能来自 `quality_facet` 闭集。存量文件若未显式写 facet，统计器按目录和文件语义推导；新增或重命名测试必须显式携带 facet。

Case ID 必须匹配层级：

- `local_contract.<domain>.<object>.<case>`
- `api_integration.<domain>.<boundary>.<case>`
- `user_acceptance.<journey_or_surface>.<scenario>.<case>`

## 6. Evidence 规则

`tests.recorded` 只允许：

- canonical 三层测试文件
- `.qwq_output/env/repo/runs/tests/**/report.json`

禁止把 shell command、Markdown 报告、历史路径或桥接文件作为当前执行证据。需要保留背景信息时，只能进入 `notes` 或 changelog。

## 7. Page 与 API 覆盖

页面真相源：

- `quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml`
- `quwoquan_service/contracts/metadata/_shared/app_routes.yaml`
- `specs/gates/user_acceptance_page_inventory.yaml`

每个 surface 至少覆盖：

- `load_success`
- `empty_permission_error`
- `primary_cta`
- `trace_context`

API 覆盖以 metadata / OpenAPI operation 为边界，至少要求：

- 服务 `api_integration` 覆盖 request/response、错误码、幂等与副作用。
- App `cloud` 或 `ui` 证据覆盖 decoder、mapper、用户可见错误和 trace/request 透传。
- 对敏感能力补 `security` 与 `data_consistency` facet。

## 8. 门禁

```bash
make verify-test-specs
make verify-test-directory-layout
make verify-test-no-fake
make verify-test-coverage-map
make verify-test-nonfunctional-coverage
make verify-test-remote-env MODE=api_integration ENV=beta|gamma|prod
make verify-test-remote-env MODE=user_acceptance TARGET=gamma-local|prod-hosted
```

含义：

- `verify-test-specs`：验收 schema、三层 case id、状态与字段约束。
- `verify-test-directory-layout`：物理目录、文件名后缀、support 纯度、旧目录回潮。
- `verify-test-no-fake`：禁止空断言、纯 skip、生成桥接、伪 report。
- `verify-test-coverage-map`：校验 feature/page/API/service/facet 的 recorded evidence 可追溯。
- `verify-test-nonfunctional-coverage`：校验 runtime error、安全、性能、可观测与数据一致性有可追溯证据。
- `verify-test-remote-env`：触发远端测试前检查 URL、token、Patrol/runner wiring。

执行入口：

```bash
make test-local-contract
make test-api-integration ENV=beta|gamma|prod
make test-user-acceptance TARGET=local|gamma-local|prod-hosted
make gate
make gate-full
```

`make gate` 覆盖静态规范、目录、no-fake、coverage 与 `local_contract`。`make gate-full` 在此基础上追加 beta/gamma `api_integration` 与 gamma-local UAT；外部依赖不可达时必须报告 `GATE_BLOCK`，不得假绿。
