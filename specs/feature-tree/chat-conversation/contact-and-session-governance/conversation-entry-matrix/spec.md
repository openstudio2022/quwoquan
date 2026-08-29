# L3 Story：会话入口矩阵 (`conversation-entry-matrix`)

> 所属能力：[`contact-and-session-governance`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为准备发起会话或通话的用户，
我希望在互关、非互关和任一方拉黑状态下只看到并执行被允许的联系入口，
从而不会绕过关系与安全门禁进入错误会话。

## 2. 范围与非目标

### In Scope

- “会话入口矩阵”的输入、可观察主路径、失败语义以及与父能力的交接。
- 群对象拉黑。
- 额外关系等级。
- 打招呼请求箱内部状态机。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 会话入口矩阵

- 拉黑级联与三处服务端门禁均有真实存储/API 证据。

<a id="req-002"></a>
### REQ-002 拉黑级联并阻断全部直接联系入口

- 拉黑级联与三处服务端门禁均有真实存储/API 证据。

<a id="req-003"></a>
### REQ-003 正式会话与一对一通话入口不可绕过

- CreateConversation、SendMessage 与 RTC 三个服务端边界均覆盖正反例。

<a id="req-004"></a>
### REQ-004 关系、会话、消息与 RTC 错误语义单轨

- 能力位和 relationship/blocked 错误从 metadata 生成，端云不维护第二套判断表。

<a id="req-005"></a>
### REQ-005 非 mutual 且无 replied GreetingRequest 时，普通建会话必须返回 greeting_required

- 非 mutual 且无 replied GreetingRequest 时，普通建会话必须返回 `greeting_required`。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/operations.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- canonical：`quwoquan_service/services/rtc-service/contracts/rtc/call_session/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 会话入口矩阵

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“会话入口矩阵”对应的公开行为。
- THEN 拉黑级联与三处服务端门禁均有真实存储/API 证据。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`contact-and-session-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 拉黑后 GreetingRequest 级联失败尚未可靠收敛

- 类型：`risk`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Persona 关系拉黑已成功但 pending GreetingRequest 失效失败时，调用可能丢弃级联错误并返回成功；同一幂等请求重放又可能在关系聚合 no-op 后提前返回，导致用户看到已拉黑而请求箱仍保留可操作请求。成功路径测试只证明级联入口，不足以证明 durable cascade、补偿或父级 `SIT-002` 闭合。
- 完成判定：`GWT-001.t1` 与 `GWT-001.t2` 由真实存储/API 证据证明——级联成功时关系、请求箱与联系入口一致收敛；级联失败时返回 canonical failure 或进入可恢复补偿，重试或对账最终收敛且不产生伪成功事实。
- 依赖：明确 PersonaRelationship 与 GreetingRequest 跨存储事务或事件补偿边界，并补齐失败、重放与恢复证据。
