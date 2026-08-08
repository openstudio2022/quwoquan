# L3 Story：群聊首页会话信息契约 (`group-home-chat-info-contract`)

> 所属能力：[`commercial-message-system`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为参与群聊的用户，
我希望在群聊天页与聊天信息页看到同一群名称、头像、成员和治理状态，
从而从任一入口理解并管理同一个群。

## 2. 范围与非目标

### In Scope

- “群聊首页会话信息契约”的输入、可观察主路径、失败语义以及与父能力的交接。
- 群治理底层实现细节。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 群聊首页会话信息契约

- 群聊天页和聊天信息页都能从同一 GroupHome metadata / DTO 来源取数。

<a id="req-002"></a>
### REQ-002 GroupHome 事实源作为聊天与信息页唯一契约来源

- 群聊天页和聊天信息页都能从同一 GroupHome metadata / DTO 来源取数。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 群聊首页会话信息契约

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“群聊首页会话信息契约”对应的公开行为。
- THEN 群聊天页和聊天信息页都能从同一 GroupHome metadata / DTO 来源取数。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`commercial-message-system`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 群聊天页与聊天信息页读取同一 GroupHome 真相源

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：群聊天页和聊天信息页的主渲染都绑定到同一 GroupHome 契约。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
