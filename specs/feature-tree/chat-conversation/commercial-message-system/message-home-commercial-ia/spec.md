# L3 Story：消息首页商用信息架构 (`message-home-commercial-ia`)

> 所属能力：[`commercial-message-system`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为查看消息的用户，
我希望在消息首页查看会话、互动、请求等真实数据并进入对应详情，
从而从一个稳定入口处理所有消息与通知。

## 2. 范围与非目标

### In Scope

- “消息首页商用信息架构”的输入、可观察主路径、失败语义以及与父能力的交接。
- 消息首页五类筛选的数据来源细节。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 消息首页商用信息架构

- 页面入口和首页数据消费继续由消息域 metadata 真相源驱动。

<a id="req-002"></a>
### REQ-002 消息首页 IA 绑定消息 metadata 契约

- 页面入口和首页数据消费继续由消息域 metadata 真相源驱动。

## 4. 契约引用

- canonical：`specs/feature-tree/chat-conversation/commercial-message-system/spec.md`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 消息首页商用信息架构

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“消息首页商用信息架构”对应的公开行为。
- THEN 页面入口和首页数据消费继续由消息域 metadata 真相源驱动。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`commercial-message-system`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 消息页作为独立一级状态成立

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：商用消息首页 IA 在消息模块内可稳定进入和展示。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 消息首页 IA 绑定消息 metadata 契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：页面入口和首页数据消费继续由消息域 metadata 真相源驱动。
- 完成判定：页面入口和首页数据消费继续由消息域 metadata 真相源驱动。
