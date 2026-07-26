# L3 Story：商用远端单轨消息系统 (`commercial-remote-only-message-system`)

> 所属能力：[`commercial-message-system`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，
我希望只基于真实账号、会话和通知事实完成消息主路径，远端失败时显示可恢复错误而不注入 Mock，
从而信任消息列表、未读状态和发送结果。

## 2. 范围与非目标

### In Scope

- “商用远端单轨消息系统”的输入、可观察主路径、失败语义以及与父能力的交接。
- alpha/test fixture 的开发态组织方式。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 商用远端单轨消息系统

- 商用主路径的消息、通知和交集消费继续由 metadata 与真实服务契约驱动。

<a id="req-002"></a>
### REQ-002 商用消息体系 Remote-only 契约保持单一真相源

- 商用主路径的消息、通知和交集消费继续由 metadata 与真实服务契约驱动。

## 4. 契约引用

- canonical：`specs/feature-tree/chat-conversation/commercial-message-system/spec.md`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 商用远端单轨消息系统

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“商用远端单轨消息系统”对应的公开行为。
- THEN 商用主路径的消息、通知和交集消费继续由 metadata 与真实服务契约驱动。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`commercial-message-system`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 商用消息体系主路径只消费 Remote 与真实持久化事实

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：商用消息体系主路径的正式渲染不再依赖 Mock、prototype 和退役字段。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 商用消息体系 Remote-only 契约保持单一真相源

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：商用主路径的消息、通知和交集消费继续由 metadata 与真实服务契约驱动。
- 完成判定：商用主路径的消息、通知和交集消费继续由 metadata 与真实服务契约驱动。
