# L3 Story：会话偏好即时生效与记忆可撤销 (`session-preference-memory-control`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣助理的用户，我希望结构化偏好事实的即时注入、可见、遗忘和撤销恢复，从而获得连续、可控制且可追溯的助理结果。

## 2. 范围与非目标

### In Scope

- session preference injection
- long-term preference management
- owner-scoped revoke and restore

### Out of Scope

- vector memory
- implicit personality inference
- 事实型长期记忆与长会话压缩，归 [`long-term-memory-compaction`](../long-term-memory-compaction/spec.md)

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 会话偏好立即影响下一次回答

- 用户选择的结构化会话偏好必须从下一次 Run 起生效，不得改写原始问题或泄漏到其他会话。

<a id="req-002"></a>
### REQ-002 用户遗忘偏好并撤销恢复

- 用户遗忘偏好后，列表和运行时召回必须立即排除该事实；撤销窗口内恢复后重新纳入，非 owner 不可见。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_preference_fact/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 会话偏好立即影响下一次回答

- GIVEN 用户已有一个可续聊的 assistant conversation
- WHEN 用户选择结构化重新生成风格并继续提问
- THEN 下一次 Run 的模型请求收到同 conversation 的 session preference
- THEN 用户原始问题不被拼接风格前缀
- THEN 其他 conversation 不继承该 session preference

<a id="gwt-002"></a>
### GWT-002 用户遗忘偏好并撤销恢复

- GIVEN 管理页展示 owner 的 active preference facts
- WHEN 用户遗忘一个事实并在撤销窗口内恢复
- THEN 遗忘后列表和运行时召回立即排除该事实
- THEN 恢复后列表和运行时召回重新包含该事实
- THEN 非 owner 始终得到 not-found

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 会话偏好立即影响下一次回答

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma-local 真实 Remote 用户旅程及受控环境运行证据，不能以 fixture 或本地 facade 替代。服务 local contract、Mongo API integration 与 App Remote facade 已证明会话隔离、原问题不变和模型请求分离。
- 完成判定：在可用 gamma-local Remote 上执行 `GWT-001` 用户旅程并产生环境证据；现有 direct `spec_ref` 不得回退。

<a id="open-002"></a>
### OPEN-002 用户遗忘偏好并撤销恢复

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma-local 真实 Remote 管理页旅程及受控环境运行证据，不能以 fixture 或本地 facade 替代。服务 local contract、Mongo API integration 与 App Remote facade 已证明遗忘、恢复、not-found 和 owner 隔离。
- 完成判定：在可用 gamma-local Remote 上执行 `GWT-002` 管理页旅程并产生环境证据；现有 direct `spec_ref` 不得回退。
