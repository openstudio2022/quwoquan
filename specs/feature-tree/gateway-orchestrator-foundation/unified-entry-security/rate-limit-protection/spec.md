# L3 Story：服务端限流保护 (`rate-limit-protection`)

> 所属能力：[`unified-entry-security`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为调用应用服务的客户端或平台服务，
我希望按主体、operation 与环境执行权威限流，返回 canonical retry 语义且不绕过业务幂等，
从而获得安全、可追踪且可降级的统一入口。

## 2. 范围与非目标

### In Scope

- “服务端限流保护”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 服务端限流保护

- 按主体、operation 与环境执行权威限流，返回 canonical retry 语义且不绕过业务幂等。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- 限流领域对象、字段、错误与存储契约：`quwoquan_service/services/api-edge/contracts/edge_security/rate_limit_bucket/`。
- 四环境配置真相源：`quwoquan_service/services/api-edge/config/schema.yaml` 与 `quwoquan_service/services/api-edge/environments/`。
- 可观测与准出预算：`quwoquan_service/services/api-edge/observability/slo/rate_limit_admission_slo.yaml`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 服务端限流保护

- GIVEN 调用应用服务的客户端或平台服务具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“服务端限流保护”对应的公开行为。
- THEN 按主体、operation 与环境执行权威限流，返回 canonical retry 语义且不绕过业务幂等。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`unified-entry-security`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 统一入口权威限流能力与三层证据

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前仓库已建立 `api-edge` 单轨入口、Redis Lua 跨副本原子准入、有界且脱敏的 `(environment, subject, operation)` bucket、显式状态故障策略与 canonical retry 语义。Caddy 业务 HTTP 只转发到 `api-edge`，owner 端仅保留资源并发背压。尚缺 `user_acceptance` 在真实公开入口和同一 immutable release digest 下的峰值压测、Redis 故障、指标与告警 readback 及回滚回执，因此当前仍不具备 `GWT-001` 商用准出证据。
- 完成判定：canonical 统一入口先完成认证与 operation/可信主体解析，再以共享原子状态对同一 `(environment, subject, operation)` 执行一致限流。`local_contract` 覆盖主体/operation 隔离、并发原子性、key/TTL 上限、配置和共享状态故障策略，`api_integration` 证明至少两个业务副本以及 stable/gray 并存时总阈值不随实例数放大、typed `429` 与 retry 语义一致，`user_acceptance` 从公开入口完成同一 release digest 的峰值、故障、指标/告警 readback 与回滚验证。三层证据均直接引用 `GWT-001` 后方可关闭。
