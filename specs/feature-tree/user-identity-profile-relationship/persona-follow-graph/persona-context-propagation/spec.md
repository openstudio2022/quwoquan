# L3 Story：Persona 上下文传播 (`persona-context-propagation`)

> 所属能力：[`persona-follow-graph`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “Persona 上下文传播”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Persona 上下文传播

- 若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`。

<a id="req-002"></a>
### REQ-002 若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 personaId / profileSubjectId

- 若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`。
- 内容对象需保留不可变作者快照，避免停用后记录显示异常。
- 圈子相关写入必须明确落到具体分身，而不是 owner。
- 下游写入对象必须保存足够的作者快照，避免 persona 停用后记录渲染丢失。
- 下游域可以持久化 `personaId / subAccountId / profileSubjectId`，但不得反查或暴露 owner 映射。
- 助手会话与通知回放至少要带上 active persona 上下文，不得默认落回 owner。
- 通知与助手回放的 persona drift 事件必须可观测、可回滚。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Persona 上下文传播

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“Persona 上下文传播”对应的公开行为。
- THEN 若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Persona 上下文传播 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“Persona 上下文传播”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
