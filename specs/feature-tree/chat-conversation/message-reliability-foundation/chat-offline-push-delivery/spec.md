# L3 Story：会话离线推送投递 (`chat-offline-push-delivery`)

> 所属能力：[`message-reliability-foundation`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)

> 设计归属：[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为离线或未打开应用的用户，
我希望别人发给我的消息能通过设备推送到达，并且点开就直接进入那条消息所在的会话，
从而不必反复打开应用轮询是否有人找我。

## 2. 范围与非目标

### In Scope

- 会话消息事件到通知投递作业的幂等投影。
- 推送投递终态的真实性：未确认与已送达必须可区分。
- 打开推送后的会话直达与未读收敛。

### Out of Scope

- 站内互动通知列表，由 `commercial-message-system` 的 `interaction-notification-inbox` 负责。
- provider 端点注册与失效回收，由 `notification-service` 既有边界负责。
- 在线实时投递，由 [`realtime-push-and-offline-sync`](../realtime-push-and-offline-sync/spec.md) 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 会话事件经幂等投影进入投递作业

- 同一条消息事件重复投影必须最多产生一个投递作业；重放与补偿不得产生重复推送。

<a id="req-002"></a>
### REQ-002 投递终态必须真实

- 只有 provider 回执确认才允许标记为已送达；未回执必须保留未确认态，不得写成已送达。
- provider 不可用必须表达为投递未确认并进入既有退避重试，不得静默丢弃。

<a id="req-003"></a>
### REQ-003 打开推送直达会话且未读收敛

- 用户点击推送后必须直达该消息所在会话；进入会话后该会话未读计数必须收敛。
- 应用在前台且该会话已打开时不得重复弹出设备推送。

<a id="req-004"></a>
### REQ-004 推送载荷最小化

- 推送载荷不得携带正文以外的关系事实或交集事实；投递记录不得保留正文。

<a id="req-005"></a>
### REQ-005 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification_delivery_job/fields.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification_delivery_job/operations.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 离线设备收到真实推送并直达会话

- GIVEN 接收方设备离线且已登记有效推送端点。
- WHEN 发送方在该会话发送一条消息。
- THEN 接收方设备收到由真实 provider 投递的推送，点击后直达该会话且未读收敛。
- AND 同一条消息不产生重复推送。

<a id="gwt-002"></a>
### GWT-002 provider 未回执时终态保持未确认

- GIVEN provider 接受了投递请求但未返回送达回执。
- WHEN 投递作业到达终态判定点。
- THEN 投递记录保持未确认态并进入既有退避重试。
- AND 不得标记为已送达。

## 6. 依赖

- 前置要求：[`message-reliability-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-003](../design.md#dec-003)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 chat 事件尚未接入通知投递

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前通知服务不消费任何会话事件，离线用户既收不到设备推送也没有投递记录，消息可达性在离线场景下为零。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
- 依赖：父能力 `OPEN-001` 的受控凭据
