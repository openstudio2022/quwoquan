# L3 Story：Persona 资料主体与可见性 (`persona-profile-subject-and-visibility`)

> 所属能力：[`persona-follow-graph`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “Persona 资料主体与可见性”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Persona 资料主体与可见性

- 外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段。

<a id="req-002"></a>
### REQ-002 既要统一管理 owner 基线，又希望某些分身拥有局部覆写资料的多身份用户

- 既要统一管理 owner 基线，又希望某些分身拥有局部覆写资料的多身份用户。
- 外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段。
- `PersonaDto` 可以继续作为 user 域内部管理对象，但不得直接作为公开主页首屏真相源。
- `strict`：公开读取返回 `404` 或等效不可见语义。
- 记录内容、评论、聊天消息、通知保留不可变作者快照。
- 停用后的 `ProfileSubject` 是否继续开放公开页，由 user 域可见性策略统一决定；第一版允许公开页关闭，但记录对象仍应使用快照正常渲染。
- 内部身份引用统一使用 `profileSubjectId` 或 `subAccountId`。
- 停用分身不得继续作为新动作主体，但其记录归因必须可追踪、可渲染、可审计。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Persona 资料主体与可见性

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“Persona 资料主体与可见性”对应的公开行为。
- THEN 外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Persona 资料主体与可见性 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“Persona 资料主体与可见性”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
