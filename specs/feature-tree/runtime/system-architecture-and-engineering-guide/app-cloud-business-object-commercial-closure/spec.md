# L3 Story：App Cloud 业务对象商用闭环 (`app-cloud-business-object-commercial-closure`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)

> Journey / Scenario：AppRoot 当前全部 Journey；统一准出锚点为 [`REQ-009`](../../../spec.md#req-009)、[`REQ-010`](../../../spec.md#req-010) 与 [`UAT-009`](../../../spec.md#uat-009)。

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为维护端云契约的开发者，
我希望从服务本地 contracts 幂等生成并校验 App 与服务共用的业务对象合同，
从而避免手写类型和派生索引成为第二真相源。

## 2. 范围与非目标

### In Scope

- 服务本地 contracts 到 ContractGraph、服务端安全描述符、App typed client 与 generated manifest 的单一生成链。
- App Remote composition、服务端 operation/object guard、Cloud runtime 单轨和 test-only double 物理隔离。
- 当前全部 AppRoot Journey 的三层 CaseResult、四环境制品、Provider、SLO、灰度与回滚证据闭环。

### Out of Scope

- 通用 CRUD 框架、通用事件溯源、分布式事务或通用 Saga。
- 推荐、内容生产和 edge-media 内部算法。
- 父能力中由其他 Story 独立拥有的产品行为与领域事实。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 App Cloud 业务对象商用闭环

- ContractGraph validate/generate/check 可在 clean checkout 幂等重生。

<a id="req-002"></a>
### REQ-002 App 只消费业务对象类型化 ContractGraph

- ContractGraph validate/generate/check 可在 clean checkout 幂等重生。
- canonical object 与 App-exposed operation coverage 均为 100%。

<a id="req-003"></a>
### REQ-003 服务端从可信 principal 执行 operation 与对象授权

- required operation 服务端 guard 覆盖率为 100%。
- 每个对象的身份拒绝错误由本对象 `errors.yaml` 唯一拥有并生成；禁止从兄弟对象借用通用错误码。
- RTC/Realtime、Chat/Content Media、Assistant consent、Behavior/Ops 的跨 actor 拒绝语义必须有直接负向测试证据。
- production 缺 JWT key/issuer/audience 时启动失败且不存在默认 secret。

<a id="req-004"></a>
### REQ-004 四环境 Remote 与 test-only double 物理隔离

- App 内 Mock 顶层类、fixture runtime loader、空 Remote 和 fallback 数量为 0。
- alpha/beta/gamma/prod dependency resolution、kernel/AOT/SBOM 与 Remote wiring 必须由可执行门禁直接证明。

<a id="req-005"></a>
### REQ-005 Runtime 对 deadline cancellation retry error telemetry 语义唯一

- Cloud 只有一条 context/config/transport/error/telemetry 执行链。
- Runtime import DAG、generated-client-only 与 `RuntimeFailure` 零旁路必须由可执行门禁直接证明。

<a id="req-006"></a>
### REQ-006 当前全部真实 Remote Scenario 完成商业准出

- local_contract、api_integration、user_acceptance 均有真实 CaseResult。
- retired/Mock/fixture/empty Remote/reverse import/dynamic skip/path-UAT 全部为 0。
- production AOT/SBOM、Web release、OHOS HAP、SLO、灰度和回滚证据绑定同一不可变候选。

<a id="req-007"></a>
### REQ-007 L3 Story 与 AppRoot 十条 Scenario 双向可追踪

- 父 L2 的 Story 列表与目录一致，AppRoot Scenario 与参与 L1 双向引用。
- 本 Story 只保留 `spec.md`，设计归属上收到 L2 DEC。
- 测试 `spec_ref` 必须指向现存 GWT/SIT/UAT 锚点。

<a id="req-008"></a>
### REQ-008 App application coordinator 只组合无需原子一致的少量 capability；稳定排序、统一权限或复用页面 Slice 由服务端 projection owner 提供

- App application coordinator 只组合无需原子一致的少量 capability；稳定排序、统一权限或复用页面 Slice 由服务端 projection owner 提供。
- command 仅在 metadata 声明幂等且具有 key 时允许重试。
- deadline 使用剩余预算并向 HTTP、数据库、对象存储和消息执行传播。
- 取消后不得继续产生副作用。

## 4. 契约引用

- canonical：[`L2 DEC-001`](../design.md#dec-001)
- canonical：`quwoquan_service/contracts/metadata`
- canonical：`quwoquan_service/contracts/metadata/_schemas/context.schema.json`
- canonical：`quwoquan_service/contracts/metadata/_schemas/object.schema.json`
- canonical：`quwoquan_service/contracts/metadata/_schemas/operations.schema.json`
- canonical：`quwoquan_service/contracts/metadata/_schemas/contract_graph.schema.json`
- canonical：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md`
- canonical：`quwoquan_service/runtime/auth`
- canonical：`quwoquan_ops/environments`
- canonical：本文件 `REQ-004`、`GWT-004` 与 `OPEN-004`
- canonical：`quwoquan_app/packages/quwoquan_cloud_contracts`
- canonical：`quwoquan_app/lib/cloud/runtime`
- canonical：[`AppRoot REQ-009`](../../../spec.md#req-009)
- canonical：[`AppRoot REQ-010`](../../../spec.md#req-010)
- canonical：[`AppRoot UAT-009`](../../../spec.md#uat-009)
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 App Cloud 业务对象商用闭环

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“App Cloud 业务对象商用闭环”对应的公开行为。
- THEN ContractGraph validate/generate/check 可在 clean checkout 幂等重生。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 App 只消费业务对象类型化 ContractGraph

- GIVEN App 需要访问服务业务对象。
- WHEN 端侧生成并装配业务对象客户端。
- THEN canonical object 与 App-exposed operation coverage 均为 100%，且不保留手写业务类型副本。

<a id="gwt-003"></a>
### GWT-003 服务端从可信 principal 执行 operation 与对象授权

- GIVEN 请求携带可验证 principal 或缺失、过期、越权身份。
- WHEN 服务端执行业务 operation。
- THEN 仅可信 principal 可通过对应 guard，拒绝结果使用 canonical failure 且不产生业务写入。

<a id="gwt-004"></a>
### GWT-004 四环境 Remote 与 test-only double 物理隔离

- GIVEN 分别装配 alpha、beta、gamma、prod 运行入口与 local_contract。
- WHEN 构建依赖图、kernel/AOT 与 SBOM。
- THEN 四环境 artifact 只包含 Remote 和真实基础设施，typed double 仅存在 local_contract 测试树。

<a id="gwt-005"></a>
### GWT-005 Runtime 对 deadline cancellation retry error telemetry 语义唯一

- GIVEN Cloud 请求经过 context、config、transport、error 与 telemetry 链。
- WHEN 请求超时、取消、重试或失败。
- THEN 运行时只使用一条可追踪执行链，并按 canonical failure 和恢复语义结束。

<a id="gwt-006"></a>
### GWT-006 当前全部真实 Remote Scenario 完成商业准出

- GIVEN 同一不可变候选已部署到声明环境。
- WHEN 当前全部 AppRoot Remote Scenario 分别执行 local_contract、api_integration 与 user_acceptance。
- THEN 三层结果、制品摘要、SLO、灰度与回滚证据可关联到该唯一不可变候选。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 DDD/CQRS 业务对象架构硬门

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前对象目录与 kind-aware 层门已覆盖既有服务，但运行时存储复核仍发现 AssistantSession/AssistantTurnView 直读 AssistantRun、Chat/Circle/Content 的账号关闭与查询实现直写兄弟或跨服务集合，以及 App operation 仍保留手写 `client_contract`/业务 decoder。新增 Travel 对象正在其唯一 owner 任务内完成物理分拆与测试，最终 canonical 对象数必须以同一 ContractGraph source hash 的实际 roster 为准，不再维护失效的固定数量台账。上述存储旁路、第二 wire 真相源、对象级测试或生成归属任一非零时，本 OPEN 不得删除，也不得声明 `MODEL_GOVERNANCE_READY`。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 服务端从可信 principal 执行 operation 与对象授权

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺每个服务 production composition root 对 required operation 的 100% 挂载覆盖报告与同一候选环境拒绝回执；ContractGraph 已为全部 operation 生成 fail-closed descriptor，runtime guard 与重点跨 actor 负向测试已通过。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 四环境 Remote 与 test-only double 物理隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺同一候选的 alpha/beta/gamma/prod dependency/kernel/AOT/SBOM、双端安装包与 UAT transitive import 回执；静态纯度、包依赖与 Remote 单轨门已通过。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-006"></a>
### OPEN-006 当前全部真实 Remote Scenario 完成商业准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺当前全部 AppRoot Journey 在同一候选上的 alpha/beta/gamma/prod 真实 user_acceptance、Provider、SLO、灰度与回滚 CaseResult；局部 local_contract 与 api_integration 已有直接证据，但 ContractGraph 仍有 blocked operation。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效。
