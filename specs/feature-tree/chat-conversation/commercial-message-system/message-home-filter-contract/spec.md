# L3 Story：消息首页筛选契约 (`message-home-filter-contract`)

> 所属能力：[`commercial-message-system`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为查看消息的用户，
我希望按声明的五类筛选查看会话与通知，并让已读变化同步回首页，
从而快速定位目标消息且筛选结果不会互相串位。

## 2. 范围与非目标

### In Scope

- “消息首页筛选契约”的输入、可观察主路径、失败语义以及与父能力的交接。
- 联系首页关系聚合。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 消息首页筛选契约

- 五类筛选、通知 inbox 和已读同步都可映射到 metadata 契约与真实服务投影。

<a id="req-002"></a>
### REQ-002 消息筛选与通知 inbox 契约来源唯一

- 五类筛选、通知 inbox 和已读同步都可映射到 metadata 契约与真实服务投影。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 消息首页筛选契约

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“消息首页筛选契约”对应的公开行为。
- THEN 五类筛选、通知 inbox 和已读同步都可映射到 metadata 契约与真实服务投影。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`commercial-message-system`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 五类消息筛选由真实 inbox 和通知 inbox 驱动

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：五类筛选和已读同步可由真实服务契约稳定支持。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
