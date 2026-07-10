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
area / layer / domain_service / test_object / quality_facet / env
case_id / source_file / recorded_artifact
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

## 3. 目录合同

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

## 4. 文件命名与 Case ID

文件名必须带物理层后缀：

- Dart：`<subject>__<case>__[facet]__<layer>_test.dart`
- Go：`<subject>__<case>__[facet]__<layer>_test.go`
- Python：`test_<subject>__<case>__[facet]__<layer>_test.py`

其中 `[facet]` 取值只能来自 `quality_facet` 闭集。存量文件若未显式写 facet，统计器按目录和文件语义推导；新增或重命名测试必须显式携带 facet。

Case ID 必须匹配层级：

- `local_contract.<domain>.<object>.<case>`
- `api_integration.<domain>.<boundary>.<case>`
- `user_acceptance.<journey_or_surface>.<scenario>.<case>`

## 5. Evidence 规则

`tests.recorded` 只允许：

- canonical 三层测试文件
- `.qwq_output/env/repo/runs/tests/**/report.json`

禁止把 shell command、Markdown 报告、历史路径或桥接文件作为当前执行证据。需要保留背景信息时，只能进入 `notes` 或 changelog。

## 6. Page 与 API 覆盖

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

## 7. 门禁

```bash
make verify-test-specs
make verify-test-directory-layout
make verify-test-no-fake
make verify-test-coverage-map
make verify-test-remote-env MODE=api_integration ENV=beta|gamma|prod
make verify-test-remote-env MODE=user_acceptance TARGET=gamma-local|prod-hosted
```

含义：

- `verify-test-specs`：验收 schema、三层 case id、状态与字段约束。
- `verify-test-directory-layout`：物理目录、文件名后缀、support 纯度、旧目录回潮。
- `verify-test-no-fake`：禁止空断言、纯 skip、生成桥接、伪 report。
- `verify-test-coverage-map`：校验 feature/page/API/service/facet 的 recorded evidence 可追溯。
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
