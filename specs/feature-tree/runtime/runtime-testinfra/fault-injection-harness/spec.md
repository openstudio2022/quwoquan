# L3 Story：环境边缘受控故障注入 (`fault-injection-harness`)

> 所属能力：[`runtime-testinfra`](../spec.md)

> Journey / Scenario：横切工程能力，不直接拥有 AppRoot Scenario。

> 设计归属：[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为开发、测试或运维角色，我希望以闭集故障 profile 在环境边缘受控注入并可靠恢复，从而让重试、超时、降级与弱网体验可以被三层测试真实验证，而 production 装配保持零注入侵入。

## 2. 范围与非目标

### In Scope

- 故障 profile 闭集（延迟、错误、断连、弱网带宽）及其契约登记。
- 环境边缘受控代理的注入、观测与恢复编排（`stackctl drill`）。
- 测试树内 typed fault double 的对象级故障注入边界。

### Out of Scope

- 业务对象的具体错误码与恢复语义（由对象 `errors.yaml` 与所属节点拥有）。
- 告警命中与恢复回执的闭环验收（由 `alert-drill-closure` 拥有）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 故障 profile 闭集且注入面受限

- 故障 profile 是闭集枚举：延迟、错误响应、连接断开、弱网带宽；新增 profile 必须先扩展 harness 契约再实现。
- 注入面只允许环境边缘受控代理与测试树内 typed fault double；production `lib/**`、服务运行装配与环境 artifact 不得携带任何注入开关或故障分支。
- 错误响应注入只使用对象 `errors.yaml` 声明的错误码语义，不得合成契约外错误形态。

<a id="req-002"></a>
### REQ-002 注入可恢复且产出结构化回执

- 每次注入必须声明目标环境、作用面与故障 profile；注入只允许 alpha/beta/gamma，Prod 在注入前拒绝。
- 演练结束必须恢复注入前状态；恢复失败时保持环境隔离并阻断，不得写入伪恢复事实。
- 每次演练产出结构化回执（注入时刻、作用面、profile、恢复时刻），写入 `.qwq_output` 且可幂等重建。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 受控注入与恢复闭合

- GIVEN alpha/beta/gamma 候选环境健康且故障 profile 属于契约闭集。
- WHEN 参与者以显式作用面执行 `stackctl drill` 注入并结束演练。
- THEN 注入期间受影响调用表现出声明的故障语义，未声明作用面不受影响。
- AND 演练结束后环境恢复注入前状态，结构化回执可从 `.qwq_output` 幂等重建；Prod 目标在注入前被拒绝。

## 6. 依赖

- 前置要求：[`runtime-testinfra`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果；[`alert-drill-closure`](../../../platform-ops-governance/observability-and-alerting/alert-drill-closure/spec.md) 消费本 Story 的注入与恢复能力。
- 父级设计：[L2 DEC-005](../design.md#dec-005)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 故障注入 harness 实现与首批演练证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺健康环境上的真实断连演练回执——本地环境互斥，
  alpha-local 运行时活跃期间 gamma-local 无法拉起且演练不得打断在用环境；
  另缺 latency/error/bandwidth 三个 profile 的边缘代理实现。故障 profile
  闭集、`stackctl drill` 编排与 disconnect 的容器级实现已落地并有合约测试
  与 CLI 回执覆盖。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
