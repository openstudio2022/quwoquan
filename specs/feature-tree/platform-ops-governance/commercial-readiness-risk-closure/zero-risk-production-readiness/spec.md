# L3 Story：零风险风险生产就绪 (`zero-risk-production-readiness`)

> 所属能力：[`commercial-readiness-risk-closure`](../spec.md)
>
> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为平台运维、安全或审核角色，我希望执行 RP1-RP7；仓内风险全部解决、外部前置条件真实满足后才允许 production release，从而获得可审计且可回滚的平台治理结果。

## 2. 范围与非目标

### In Scope

- 身份双签、遥测日志、供应链、灰度回滚、观测灾备、配置数据和验收清零
- local_contract、api_integration、user_acceptance 与 stackctl release 证据

### Out of Scope

- 伪造外部凭据、法务主体、IdP、GitHub entitlement 或 prod-hosted 结果

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 任一未解决风险阻断生产发布

- 缺失项逐一有稳定错误与修复指引，发布不能继续。

<a id="req-002"></a>
### REQ-002 全部风险关闭后完成不可变灰度与恢复验证

- stackctl release report、health/inspect/doctor、rollback/restore receipt 均可复验。

## 4. 契约引用

- canonical：`specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md`
- canonical：`specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/design.md`
- canonical：父能力 [`OPEN`](../spec.md#8-开放事项) 与动态 `make feature-tree-overview` 输出
- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/environments/prod/access-isolation.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 任一未解决风险阻断生产发布

- GIVEN 风险门读取目标父链 OPEN、外部前置审计和真实测试结果。
- WHEN 任一 RP 未完成，或 IdP/GitHub protection/法务主体/prod 凭据不可验证。
- THEN pre-release 与 deploy workflow fail-closed。
- THEN 不存在 warn-only、skip、allowlist 或风险豁免参数。

<a id="gwt-002"></a>
### GWT-002 全部风险关闭后完成不可变灰度与恢复验证

- GIVEN RP1-RP7 全部完成，外部前置条件真实可用。
- WHEN 运行 gray-initial、carry-on、full、告警闭环和隔离恢复演练。
- THEN 三阶段使用同一 ReleaseManifest digest。
- THEN 真实 Prometheus SLO、锁/CAS、双签、config ACK、告警与恢复证据完整。
- THEN 本 Story 范围内所有阻断级 `OPEN` 均达到完成判定，且不存在未归属风险。

## 6. 依赖

- 前置要求：[`commercial-readiness-risk-closure`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 任一未解决风险阻断生产发布

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺失项逐一有稳定错误与修复指引，发布不能继续。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 全部风险关闭后完成不可变灰度与恢复验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：stackctl release report、health/inspect/doctor、rollback/restore receipt 均可复验。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
