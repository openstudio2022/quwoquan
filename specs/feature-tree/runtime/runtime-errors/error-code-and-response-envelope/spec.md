# L3 Story：错误代码与响应信封 (`error-code-and-response-envelope`)

> 所属能力：[`runtime-errors`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为调用或维护服务的工程角色，
我希望让所有服务用 canonical error code、response envelope 和 recovery action 表达失败，
从而在端云之间稳定识别错误并执行正确恢复。

## 2. 范围与非目标

### In Scope

- “错误代码与响应信封”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 错误代码与响应信封

- “错误代码与响应信封”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 与上层 runtime 契约一致，禁止服务内重复实现

- 与上层 runtime 契约一致，禁止服务内重复实现。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 错误代码与响应信封

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“错误代码与响应信封”对应的公开行为。
- THEN 通过父能力公开契约交付“错误代码与响应信封”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 错误上下文与恢复动作保持一致

- GIVEN 服务以 canonical error code 返回失败。
- WHEN 调用方解析响应信封并呈现恢复动作。
- THEN 错误上下文、稳定 code 与恢复语义一致，且不以成功响应掩盖失败。

## 6. 依赖

- 前置要求：[`runtime-errors`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 错误代码与响应信封主路径尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：将服务失败映射为统一 RuntimeErrorResponse，并让调用方按稳定 code 获得恢复动作。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 错误上下文与恢复动作保持一致尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：将服务失败映射为统一 RuntimeErrorResponse，并让调用方按稳定 code 获得恢复动作。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
