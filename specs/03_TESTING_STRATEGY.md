# 三层测试策略与治理规范

本文是仓库测试目录、命名、统计、覆盖与门禁的唯一执行规范。

## 1. 唯一测试层

测试目录层只允许三类：

- `local_contract`
- `api_integration`
- `user_acceptance`

`alpha`、`beta`、`gamma`、`prod` 只是 runner、Provider Binding、配置、报告和证据维度，
不允许作为测试目录层级。生产灰度是 `prod` rollout stage，不存在独立 `prod-gray`
测试目录或环境。商用外部能力必须把同一三层测试按 Alpha/Beta/Gamma 展开为 3×3 执行
矩阵；九格增加的是执行证据，不是第四测试层。

## 2. Coverage Spine

覆盖治理沿同一条脊柱追踪：

```text
Journey -> Scenario -> Surface/Page -> App boundary -> API operation
  -> Service capability -> Store/Event/Data release -> Observability/SLO
```

统计字段统一为：

```text
area / layer / domain_service / service / test_object / quality_facet
env / rollout_stage / execution_profile / case_id / source_file / recorded_artifact
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

`rollout_stage` 只用于生产发布阶段，例如 `gray_initial`。它不能替代环境；生产灰度必须表达为 `env=prod` + `rollout_stage=gray_initial`，不得写成派生环境名。

`execution_profile` 是运行与证据维度，不是第四层测试目录。每项环境相关证据只能属于一个 profile：

- `baseline`：不跨网络；规格、契约、静态质量和全部 `local_contract`。外部能力的
  local_contract 可以加载 Alpha/Beta/Gamma 对应 Binding 下的真实 Adapter 类与本地
  协议/故障 harness，但不得读取 endpoint、Secret 或访问外网。
- `smoke`：Alpha；可控实现或轻量参考服务的跨进程 API 与完整用户旅程。Alpha 不可用、
  固定成功或跳过合同校验即 `FAIL`。
- `integration`：Beta/Gamma `api_integration` 及 Beta `user_acceptance`；连接远端沙箱、
  自建兼容服务或厂商测试环境，验证真实 TLS、鉴权、回调、重试、超时和限流。核心依赖
  不可达为 `GATE_BLOCK`。
- `release`：Gamma production-grade Adapter 的完整用户/运营旅程、trace/SLO/readback，
  以及 Prod 审批/灰度。商业依赖缺失为 `GATE_BLOCK`，绝不降级成 integration 通过。

### 2.1 外部 Provider 3×3 语义

| 环境 | local_contract | api_integration | user_acceptance |
|---|---|---|---|
| Alpha | 对 Alpha Adapter/参考实现跑离线合同与故障注入 | 跨进程调用可控参考服务 | 完整功能/异常/恢复旅程 |
| Beta | 对 Beta production Adapter 类跑离线协议 harness | 真实沙箱、TLS、鉴权、callback | Beta Remote composition 的用户/运营旅程 |
| Gamma | 对 Gamma production Adapter 类跑离线协议 harness | 隔离 Gamma 租户真实调用与 readback | gamma-local 真机/浏览器或运营旅程、观测与回滚 |

每格必须有独立 `case_id/env/provider_adapter_digest/config_digest/data_digest` 和执行结果。
同一测试源码可以参数化复用，但报告不得跨环境复制。`NOT_RUN`、required skip、零断言、
dry-run、Memory/Mock 替代远端、旧 digest 或仅存在测试文件均不计通过。

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

Data 离线阶段异常必须断言稳定 `DataIssue.code/recovery/ref/lane`，不得断言或解析
`message` 来驱动重试、回退或目标替补；进入 importer/API 后再验证其到 metadata
错误码与 `RuntimeErrorResponse` 的显式边界映射。

性能阈值必须来自 `spec.md`、`acceptance.yaml` 或 SLO 文档，不能在测试中自造第二真相源。日志、指标、trace、audit 继续遵守瘦身后的 observability 合同。

## 4. 目录合同

### App

```text
quwoquan_app/test/
  local_contract/
    ui/
    cloud/
      runtime/
      generated/
      <domain>/adapter_conformance/
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

App Cloud 的合同包、Mock 包和 production/alpha composition 使用同一三层目录，
不新增 `package_test` 第四层：

- `local_contract/cloud/generated` 验证固定 ContractGraph hash、output manifest、
  clean rebuild 和 pure Dart package DAG。
- `local_contract/cloud/<domain>/adapter_conformance` 对同一 BehaviorSpec 跑
  Mock 与 RemoteStub，验证字段、分页、权限、错误和 actor 语义。
- `api_integration/cloud/<domain>` 必须直接构造 generated client/Remote adapter
  连接已预制环境；裸 HTTP 请求不能替代客户端集成证据。
- production/alpha dependency reachability、kernel/AOT 与 SBOM 归
  `local_contract/quality` 的 package contract，真实构建结果作为 artifact 记录。

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
- `QWQ_OUTPUT_ROOT/env/repo/runs/tests/**/report.json`

禁止把 shell command、Markdown 报告、历史路径或桥接文件作为当前执行证据。需要保留背景信息时，只能进入 `notes` 或 changelog。

Provider 九格的原始环境报告归
`QWQ_OUTPUT_ROOT/env/<env>/runs/<run-id>/**`，logs/traces/metrics 归
`QWQ_OUTPUT_ROOT/env/<env>/observability/<run-id>/**`；`tests.recorded` 只绑定统一聚合后的
`env/repo/runs/tests/provider-conformance/<run-id>/report.json`。配置、Binding、schema、
endpoint/Secret 值、渲染 `.env` 和 TLS material 不得进入 output。

## 7. Page 与 API 覆盖

页面真相源：

- `quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml`
- `quwoquan_service/contracts/metadata/_shared/app_routes.yaml`
- `specs/gates/user_acceptance_page_inventory.yaml`

每个 surface 必须在 inventory 中逐项声明 applicable/not_applicable，适用项至少覆盖：

- `load_success`
- `empty`
- `auth_required`
- `permission_denied`
- `runtime_error`
- `offline`
- `retry_recovered`
- `primary_cta`
- `trace_context`
- `theme_tokens`
- `responsive_layout`
- `accessibility`

禁止再用 `empty_permission_error` 把空态、权限态和错误态合并为一个路径型用例。

API 覆盖以 metadata / OpenAPI operation 为边界，至少要求：

- 服务 `api_integration` 覆盖 request/response、错误码、幂等与副作用。
- App `cloud` 或 `ui` 证据覆盖 decoder、mapper、用户可见错误和 trace/request 透传。
- 对敏感能力补 `security` 与 `data_consistency` facet。
- App Remote 证据必须经过 generated operation descriptor、统一 executor 和
  Remote adapter；测试内自 seed、失败后 fallback Mock/空集合、动态 skip 均失败。
- user_acceptance 必须启动真实页面并断言 CTA/状态/恢复；`File.existsSync` 或
  仅核验历史证据路径只能作 traceability 辅助，不能作为 UAT 主证据。

## 8. 对象级测试矩阵

每个 ContractGraph object 的测试合同按对象类型生成期望，禁止仅检查测试路径存在：

- Aggregate：invariant、state transition、version conflict、idempotency、authz、aggregate+outbox transaction。
- Command：success、validation、permission、conflict、duplicate、dependency failure、event side effect。
- Query：filter/sort/cursor、field policy、freshness、cache hit/miss、projection lag/rebuild、remote ACL。
- Slice/ReadModel：source mapping、schema、ordering、dedup、tombstone、replay。
- Adapter：authoritative role、real engine、transaction、unique/index/TTL、timeout、failure mapping。
- App Repository/Provider/Page：generated request/decoder、Mock/Remote parity、structured error/recovery、主题/多屏/无障碍/性能/trace。
- Journey：至少两个真实对象，覆盖用户结果、跨域 handoff、失败补偿、行为/推荐/运营回流。

测试报告必须输出结构化 `CaseResult`，包含 case id、object/operation/surface、layer、env、quality facet、assertion count、duration、artifact 和 pass/fail。路径存在、动态 skip、Memory adapter 或 `os.Exit(0)` 不构成通过证据。

## 9. 四环境数据预制合同

每个对象维护由 metadata/fixture 引用生成的 `ObjectTestDataManifest`：

- alpha：contract fixture + MockRepository；离线、确定、可重复。
- beta：RemoteRepository + gateway seed；多主体、权限、状态机、错误和边界数据齐全。
- gamma：API importer/release + 真实 Mongo/PG/Redis/ES/MQ；每次 run 独立 namespace 并可回放清理。
- prod：禁止 fixture、seed、Mock、Memory、Noop 和默认 secret；只允许脱敏合成探针和受控实时验收。

Manifest 至少声明 dataset/release id、schema version、actor set、object refs、状态覆盖、敏感级别、seed/import/cleanup command、TTL、预期 operation/page/Journey 和证据绑定。测试失败时必须保留可重放的 run id，成功后按环境策略清理。

## 10. 门禁

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
make gate-smoke
make gate-integration ENV=beta|gamma
make gate-release ENV=gamma|prod
```

`make gate` 是纯 `baseline`，不读取 SLS、法务主体、远端 URL、设备或运行输出。其余入口只验证指定 profile，不允许 Prod 未配置时改跑 Gamma。`PASS` 仅表示该 profile 的实际证据通过；外部能力缺失只能输出该 profile 的 `GATE_BLOCK`。
