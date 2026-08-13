# L3 Story：告警演练动态闭环 (`alert-drill-closure`)

> 所属能力：[`observability-and-alerting`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为平台运维、安全或审核角色，我希望通过受控故障演练证明「注入 → 指标/告警命中 → 恢复 → 回执」的动态闭环，从而确认告警规则不只是与契约静态同源，而是在真实故障发生时能够按时命中并可恢复。

## 2. 范围与非目标

### In Scope

- 演练闭环验收：注入、真实观测面 readback、告警命中、恢复与结构化回执。
- MTTD/MTTR 的演练侧度量口径。

### Out of Scope

- 故障注入与恢复的编排实现（由 [`fault-injection-harness`](../../../runtime/runtime-testinfra/fault-injection-harness/spec.md) 拥有）。
- 告警规则与契约的静态同源校验（由既有 alert overlay 门禁拥有）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 演练断言只消费真实观测面

- 演练期间的指标与日志断言必须查询真实观测面（Prometheus/ES readback），禁止 mock 观测面或人工填报充当命中证据。
- 被断言的告警规则只从 contracts alert overlay 派生，演练不得旁路定义第二套告警规则。
- 演练只允许 alpha/beta/gamma 环境；Prod 不执行注入，仅保留放量后 soak 观测。

<a id="req-002"></a>
### REQ-002 演练闭环产出可比较回执

- 每次演练产出结构化回执：注入时刻、异常日志/指标出现时刻、告警规则命中时刻、恢复时刻与恢复后确认，回执写入 `.qwq_output` 且可幂等重建。
- 回执必须能派生 MTTD 与 MTTR；告警未在声明窗口内命中或恢复未闭合时演练判定失败，不写入伪成功事实。
- 恢复后观测面必须回落到注入前基线语义，残留异常必须显式登记而非静默通过。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 注入到告警恢复的动态闭环

- GIVEN alpha/beta/gamma 候选环境健康，目标错误码具备契约派生的告警规则，故障注入 harness 可用。
- WHEN 参与者执行受控演练：注入声明的故障 profile，等待观测与告警，然后恢复。
- THEN 真实观测面 readback 证明异常日志与指标产生、对应告警规则在声明窗口内命中。
- AND 恢复后观测面回落基线，结构化回执含注入、命中、恢复时刻并可派生 MTTD/MTTR；任一环节未闭合即判定失败。

## 6. 依赖

- 前置要求：[`observability-and-alerting`](../spec.md) 的范围、要求与 SIT；[`fault-injection-harness`](../../../runtime/runtime-testinfra/fault-injection-harness/spec.md) 的注入与恢复能力。
- 下游结果：本 Story 声明的 GWT 可观察结果；[`slo-error-budget-governance`](../slo-error-budget-governance/spec.md) OPEN-002 所述非 HTTP 面 SLI 建立后可复用本闭环验收。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 告警演练闭环实现与首批核心域证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前门禁只验证告警规则与契约的静态同源，从未以真实故障
  证明告警会按时命中与恢复闭合；尚缺演练编排接入、真实 readback 断言与
  content/chat/user 核心域各至少一条常绿演练通路。AppRoot 异常恢复
  Journey 的 Prod 故障注入 telemetry 闭合（AppRoot OPEN-002）与非 HTTP 面
  SLI/SLO（`slo-error-budget-governance` OPEN-002）的动态验收均以本 Story
  为承载锚点。现有 `quwoquan_ops/tools/alert_drill.py` 承担合成告警投递链
  冒烟（Alertmanager v2 注入 → 接收 → 控制面回流），与本 Story 的真实
  故障闭环互补而非替代——合成告警不满足「真实故障派生命中」的完成判定；
  该脚本后续应收编入 `stackctl` 演练编排，避免第二演练入口。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
- 依赖：[`fault-injection-harness`](../../../runtime/runtime-testinfra/fault-injection-harness/spec.md) OPEN-001 关闭。
