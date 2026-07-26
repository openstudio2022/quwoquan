# L3 Story：指标追踪核心 (`metrics-trace-core`)

> 所属能力：[`runtime-observability`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发或运维服务的工程角色，
我希望通过统一指标与 trace API 记录低基数维度并传播关联上下文，
从而跨服务定位性能、失败与因果链路。

## 2. 范围与非目标

### In Scope

- “指标追踪核心”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 指标追踪核心

- “指标追踪核心”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 与上层 runtime 契约一致，禁止服务内重复实现

- 与上层 runtime 契约一致，禁止服务内重复实现。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 指标追踪核心

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“指标追踪核心”对应的公开行为。
- THEN 通过父能力公开契约交付“指标追踪核心”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 exporter 与日志指标追踪关联字段一致

- GIVEN 服务导出结构化日志、指标与 trace。
- WHEN 运维按服务、operation 或错误查询关联信号。
- THEN 三类信号以低基数维度和一致关联字段收敛到同一因果链路。

## 6. 依赖

- 前置要求：[`runtime-observability`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 指标追踪核心主路径尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：统一结构化日志、指标和 trace 关联，并按服务、operation 与错误聚合。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 exporter 与日志指标追踪关联字段一致尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：统一结构化日志、指标和 trace 关联，并按服务、operation 与错误聚合。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
