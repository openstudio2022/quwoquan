# L3 Story：App Cloud 业务对象商用闭环 (`app-cloud-business-object-commercial-closure`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为维护端云契约的开发者，
我希望从服务本地 contracts 幂等生成并校验 App 与服务共用的业务对象合同，
从而避免手写类型和派生索引成为第二真相源。

## 2. 范围与非目标

### In Scope

- “App Cloud 业务对象商用闭环”的输入、可观察主路径、失败语义以及与父能力的交接。
- 通用 CRUD、事件溯源、分布式事务或通用 Saga。
- 推荐、内容生产和 edge-media 内部算法。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

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
### REQ-006 十条真实 Remote Scenario 完成商业准出

- local_contract、api_integration、user_acceptance 均有真实 CaseResult。
- retired/Mock/fixture/empty Remote/reverse import/dynamic skip/path-UAT 全部为 0。
- production AOT/SBOM、Web release、OHOS HAP、SLO、灰度和回滚证据绑定同一候选版本。

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
- canonical：[`AppRoot UAT`](../../../spec.md#uat-001)
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
### GWT-006 十条真实 Remote Scenario 完成商业准出

- GIVEN 候选版本已部署到声明环境。
- WHEN 十条 Remote Scenario 分别执行 local_contract、api_integration 与 user_acceptance。
- THEN 三层结果、制品摘要、SLO、灰度与回滚证据可关联到同一候选版本。

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
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Account/Persona/Relationship、Content/Media/TrustSafety、Circle、Chat、Assistant、Notification、Search、Tag、Recommendation、Ops、RTC/Realtime/Integration 的对象与强/最终一致性有唯一裁决。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 App 只消费业务对象类型化 ContractGraph

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：ContractGraph validate/generate/check 可在 clean checkout 幂等重生。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 服务端从可信 principal 执行 operation 与对象授权

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：required operation 服务端 guard 覆盖率为 100%。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 四环境 Remote 与 test-only double 物理隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺四环境 dependency/kernel/AOT/SBOM 与 UAT transitive import 证据；目标：App/runner/UAT 内 Mock 顶层类、fixture runtime loader、空 Remote 和 fallback 数量为 0。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 Runtime 对 deadline cancellation retry error telemetry 语义唯一

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Cloud 只有一条 context/config/transport/error/telemetry 执行链。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-006"></a>
### OPEN-006 十条真实 Remote Scenario 完成商业准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：local_contract、api_integration、user_acceptance 均有真实 CaseResult。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效。
