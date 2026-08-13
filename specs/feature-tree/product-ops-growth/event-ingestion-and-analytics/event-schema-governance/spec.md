# L3 Story：事件 Schema 治理 (`event-schema-governance`)

> 所属能力：[`event-ingestion-and-analytics`](../spec.md)

> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为产品运营或增长角色，
我希望`page_error_outcome`：统一阻塞错误面依次记录 `shown/recovery_started/recovered/recovery_failed`，
从而获得可度量、可回滚的运营结果。

## 2. 范围与非目标

### In Scope

- “事件 Schema 治理”的输入、可观察主路径、失败语义以及与父能力的交接。
- event_catalog.yaml 与 app_pages.yaml 三端 codegen。
- App/Service 双端 strict validation 与 canonical batch digest。
- Elasticsearch raw/aggregate 单轨和 Portal 查询门面。
- 推荐 BehaviorSignal、Assistant 学习、visit_record。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 事件 Schema 治理

- `page_error_outcome`：统一阻塞错误面依次记录 `shown/recovery_started/recovered/recovery_failed`。

<a id="req-002"></a>
### REQ-002 page_error_outcome：统一阻塞错误面依次记录 shown/recovery_started/recovered/recovery_failed

- `page_error_outcome`：统一阻塞错误面依次记录 `shown/recovery_started/recovered/recovery_failed`
- 重试期间 body、顺序和 digest 不得变化；服务端重算摘要并全批校验。
- sessionId 为可逆账号用户键会话标识，必须按 `SENSITIVE` 管理：raw 3d、Portal 默认掩码、完整查询审计。
- callStack 只允许方法名数组，最多十层、单层 256 字符；禁止路径、token、用户输入，且不建全文索引。
- VisitRecord 使用独立 MongoDB 权威聚合与 actor-scoped 幂等回执；聚合更新与回执同事务提交，不复用 EventBatch ledger、不写 PostgreSQL 访问副本、不发布第二路推荐事件。

## 4. 契约引用

- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/app_pages.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/storage.yaml`
- canonical：`event/error`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 事件 Schema 治理

- GIVEN 产品运营或增长角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“事件 Schema 治理”对应的公开行为。
- THEN `page_error_outcome`：统一阻塞错误面依次记录 `shown/recovery_started/recovered/recovery_failed`。
- AND 相同 actor 与 Idempotency-Key 的 VisitRecord 重放只计数一次，且推荐只接收 canonical BehaviorSignal。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`event-ingestion-and-analytics`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 事件 Schema 治理 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“事件 Schema 治理”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 注册专用漏斗事件缺失，首注与回登不可区分

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺注册专用事件——`event_catalog.yaml` 只有
  `login_funnel`/`login_operation`；首注转化只能从登录结果与
  `ops_actor_first_seen` 间接推断，新老用户混淆，获客漏斗无法作为
  黄金指标注册。登录页埋点区当前由 auth 工作流活跃改造中，事件与埋点
  必须在其静止后同一增量落地，避免死 schema 与调用点冲突。
  已探明的实施路径：登录响应现有 `identityOrigin` 是身份来源类型
  （anonymous_device、phone、federated、migrated_seed），不能区分
  账号本次新建与回登，须先在 user-service `account_session` 登录响应
  增加账号新建标志字段并 codegen；端侧埋点承载文件是
  `login_page_auth_flow.dart`（`_trackln` 调用族），云侧
  `login_lifecycle` rowKind 以该标志维度扩展即可，不必新增 rowKind。
- 完成判定：注册漏斗事件进入 canonical catalog 并经 codegen 产出端侧
  payload，登录/注册页埋点调用与云侧 rollup 同一增量交付，满足
  [GWT-001](#gwt-001) 的 schema 同源可观察结果。
- 依赖：user-identity 登录页工作流静止
  （`account_session` contracts 当前处于并行改造中间态）；
  ContractGraph 静止点 codegen。

<a id="open-003"></a>
### OPEN-003 40 个已声明交互动作页面缺遥测出口

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚有 40 个页面缺强类型遥测出口——埋点覆盖矩阵
  （`make verify-page-telemetry-coverage`，报告 `.qwq_output/env/repo/runs/telemetry-coverage/report.md`）
  显示 70 个自有交互声明页面中 40 个扫描不到强类型遥测出口调用；
  primary 漏斗页面（登录/创作/搜索）已全埋并被门禁 BLOCK 保护，
  剩余为非关键页面的渐进补齐面。
- 完成判定：覆盖报告 `uncoveredPages` 归零或对应页面的
  `telemetry_descriptor` 声明被修正为实际行为，满足 [GWT-001](#gwt-001)
  的声明与实现同源。
- 依赖：各页面 owner 领域的埋点补齐增量。
