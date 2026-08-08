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
- canonical：`quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 消息首页商用信息架构

- GIVEN 已认证用户通过 production Remote composition 打开 `chat.home`，Chat 会话/联系、User GreetingRequest 与 Notification AppMessage 的所属服务均可独立返回结果或 canonical failure。
- WHEN 用户切换消息、联系、打招呼和通知分区，刷新列表并打开会话、成员、打招呼收件箱或通知目标。
- THEN 消息与未读筛选只消费 Chat MessageHome，联系筛选只消费 Chat ContactHome，待处理打招呼只消费 User GreetingRequest，通知与未读数只消费 Notification AppMessage；页面不按标题、本地缓存或跨对象私有状态拼接业务事实。
- AND 任一分区失败只阻断该分区并提供可重试终态，不把错误改写为空列表、不覆盖其他已确认分区；打开目标与已读动作只写对应 owner，恢复后按各自 Remote readback 收敛。

## 6. 依赖

- 前置要求：[`commercial-message-system`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 消息页作为独立一级状态成立

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺同一候选真实账号覆盖四个 owner 分区、跨分区失败隔离、打开目标与已读回读的 production Remote 页面验收；现有 local_contract 或单对象 API 证据不能替代首页 Journey。
- 完成判定：`GWT-001` 的四个分区与失败恢复由 user_acceptance 直接绑定，并取得 Android 与 iPhone physical ResultBundle；任一分区仍靠 fixture、错误转空或缺少 owner readback 时保持 BLOCK。
