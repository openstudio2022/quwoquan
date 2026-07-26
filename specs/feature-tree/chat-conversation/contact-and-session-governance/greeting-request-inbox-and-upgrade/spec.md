# L3 Story：打招呼请求收件箱与升级 (`greeting-request-inbox-and-upgrade`)

> 所属能力：[`contact-and-session-governance`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为希望联系非互关对象的用户，
我希望发送打招呼请求，让接收方在请求箱查看并以回复幂等升级为正式会话，
从而在不自动改变关注关系的情况下安全建立对话。

## 2. 范围与非目标

### In Scope

- “打招呼请求收件箱与升级”的输入、可观察主路径、失败语义以及与父能力的交接。
- 自动创建关注关系。
- 正式会话消息收发。
- 外部 push provider。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 打招呼请求收件箱与升级

- 会话升级、幂等与关注状态不变均有 API 集成证据。

<a id="req-002"></a>
### REQ-002 回复请求幂等升级正式会话

- 会话升级、幂等与关注状态不变均有 API 集成证据。

<a id="req-003"></a>
### REQ-003 请求箱与会话升级使用单轨 metadata 契约

- GreetingRequest 状态、错误、事件和 promotedConversationId 由 metadata/codegen 单轨生成。

<a id="req-004"></a>
### REQ-004 错误：统一消费 metadata 生成的 GreetingRequest 与 Conversation 错误语义

- 错误：统一消费 metadata 生成的 GreetingRequest 与 Conversation 错误语义。
- pending 唯一性、幂等重放、拉黑级联、频控与状态迁移不可绕过。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/greeting_request/errors.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 打招呼请求收件箱与升级

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“打招呼请求收件箱与升级”对应的公开行为。
- THEN 会话升级、幂等与关注状态不变均有 API 集成证据。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`contact-and-session-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
