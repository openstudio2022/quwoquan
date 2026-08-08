# L3 Story：会话偏好即时生效与记忆可撤销 (`session-preference-memory-control`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣助理的用户，我希望结构化助手偏好的即时注入、可见、遗忘和撤销恢复，从而获得连续、可控制且可追溯的助理结果。

## 2. 范围与非目标

### In Scope

- session preference injection
- long-term preference management
- owner-scoped revoke and restore

### Out of Scope

- vector memory
- implicit personality inference
- 需用户显式确认的长期记忆与长会话压缩，归 [`long-term-memory-compaction`](../long-term-memory-compaction/spec.md)

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 会话偏好立即影响下一次回答

- 用户选择的结构化会话偏好必须从下一次 Run 起生效，不得改写原始问题或泄漏到其他会话。

<a id="req-002"></a>
### REQ-002 用户遗忘偏好并撤销恢复

- 用户遗忘偏好后，列表和运行时召回必须立即排除该偏好；撤销窗口内恢复后重新纳入，非 owner 不可见。

<a id="req-003"></a>
### REQ-003 助手管理页只以 production Remote 真相管理偏好

- `assistant.management` 初次进入、手动重试和每次设置、遗忘、恢复后的刷新都必须读取 `assistant.AssistantPreference` owner 的 production Remote 结果；页面不得用本地默认值、乐观切换或 fixture 冒充已保存状态。
- mutation 只有在 typed 结果返回且后续列表读取收敛时才形成用户可见成功；未知结果、存储不可用、恢复窗口过期或 owner 校验失败时必须保留最后一次已确认列表和用户意图，并提供重新读取或重试入口。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_preference/operations.yaml`
- page：`assistant.management`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 会话偏好立即影响下一次回答

- GIVEN 用户已有一个可续接的 `AssistantSession`
- WHEN 用户选择结构化重新生成风格并继续提问
- THEN 下一次 Run 的模型请求收到同一 `AssistantSession` 的 session preference
- THEN 用户原始问题不被拼接风格前缀
- THEN 其他 `AssistantSession` 不继承该 session preference

<a id="gwt-002"></a>
### GWT-002 用户遗忘偏好并撤销恢复

- GIVEN 管理页展示 owner 的 active AssistantPreference
- WHEN 用户遗忘一个助手偏好并在撤销窗口内恢复
- THEN 遗忘后列表和运行时召回立即排除该偏好
- THEN 恢复后列表和运行时召回重新包含该偏好
- THEN 非 owner 始终得到 not-found

<a id="gwt-003"></a>
### GWT-003 助手管理页完成 production Remote 设置、遗忘、恢复与收敛读取

- GIVEN 已认证 owner 从 `assistant.management` 打开 production Remote 返回的 active 与可撤销偏好列表。
- WHEN 用户设置一个偏好、遗忘该偏好、在有效窗口内恢复，并在每次 mutation 后重新读取列表。
- THEN typed mutation 结果与重新读取的 canonical 列表一致，遗忘后不再进入 active 列表，恢复后重新进入 active 列表。
- AND 加载或 mutation 失败、结果未知、恢复窗口过期或 owner 不匹配时，页面保留最后一次已确认列表与待处理意图，提供明确重试或重新读取，不显示本地伪成功、伪空态或其他 owner 的偏好。

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
- 准出影响：`block`
- 影响或价值：尚缺 `assistant.management` 在同一候选上的 production Remote user_acceptance runner、失败恢复执行，以及 Android 实机与 iPhone 实机 `ReadinessResultBundle`；现有服务 local contract、Mongo API integration 与 App Remote facade 只证明设置、列表、遗忘、恢复、not-found 和 owner 隔离，不能以 fixture、Widget-only 测试或本地 facade 替代上述证据。
- 完成判定：`GWT-002`、`GWT-003` 具有对象 local_contract、真实 api_integration 与 Flutter user_acceptance 直接 `spec_ref`；绑定同一 commit、ContractGraph、candidate、production Remote composition 和环境 Provider 的 Android 实机与 iPhone 实机 `ReadinessResultBundle` 均为 passed，缺任一端、动态 skip 或非同候选结果均继续阻断。
- 依赖：可用受管环境、真实 owner 身份、同候选 App/Service artifact 与 Android/iPhone 物理设备。
