# L3 Story：日志 Schema 与键值策略 (`log-schema-and-kv-policy`)

> 所属能力：[`runtime-observability`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望统一信封：`logType + level + sourceDomain + sourceService + component + target + action`，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “日志 Schema 与键值策略”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 日志 Schema 与键值策略

- 统一信封：`logType + level + sourceDomain + sourceService + component + target + action`。

<a id="req-002"></a>
### REQ-002 统一信封：logType + level + sourceDomain + sourceService + component + target + action

- 统一信封：`logType + level + sourceDomain + sourceService + component + target + action`
- 统一关联：`sessionId + pageVisitId + traceId + requestId`
- 统一失败码：`failureCode` 枚举化，禁止仅靠 message 文本归因。
- 端侧 `quwoquan_app` 日志模型升级（只认当前信封字段；禁止兼容旧字段双读）
- 与 runtime 上层契约一致，禁止服务内重复定义日志语义。
- 兼容记录查询：查询脚本可读取记录 `currentLogType`，新写入链路不得继续写入该字段。
- Release 模式遵循采样策略，错误日志必须全量。
- 端侧日志事件包含统一信封必填字段。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 日志 Schema 与键值策略

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“日志 Schema 与键值策略”对应的公开行为。
- THEN 统一信封：`logType + level + sourceDomain + sourceService + component + target + action`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 exporter 与日志指标追踪关联字段一致

- GIVEN 日志经 exporter 与指标、trace 共同导出。
- WHEN 运维按一次请求或会话查询关联记录。
- THEN 日志、指标与 trace 使用一致的关联字段，且敏感值按策略脱敏。

## 6. 依赖

- 前置要求：[`runtime-observability`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 日志 Schema 与键值策略主路径尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：建立端云统一的日志信封、字段、隐私脱敏与检索契约。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 exporter 与日志指标追踪关联字段一致尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：建立端云统一的日志信封、字段、隐私脱敏与检索契约。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
