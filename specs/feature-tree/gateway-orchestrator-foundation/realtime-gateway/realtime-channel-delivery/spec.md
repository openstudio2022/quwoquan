# L3 Story：实时连接与渠道投递 (`realtime-channel-delivery`)

> 所属能力：[实时网关](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为等待消息或来电的用户，我希望在线事件即时到达、离线通知可靠转交，并在连接恢复后补齐缺口，从而不会因网关节点切换丢失关键事件。

## 2. 范围与非目标

### In Scope

- 统一 WebSocket 连接、Redis 在线状态和外部 ChannelAdapter 投递边界。
- 连接断开后的续接、离线 handoff 与可观察失败终态。

### Out of Scope

- 消息、通话或通知业务对象的事实所有权。

## 3. 行为要求

### REQ-001 多节点实时投递

- 连接状态必须由 Redis 支撑多节点查询；网关只消费 owner 事件，不直接写业务 MongoDB。
- 外部渠道不可用时必须保留可重试或死信事实，不得返回固定成功。
- WebSocket 只消费 query 中的一次性连接 ticket；ticket 签发和升级均只执行一次，
  失败后必须重新签发，禁止重放同一 ticket 或由传输层自动重试。
- Long-poll 只接受与当前连接主体一致的 Bearer 身份，并在声明的有界 hold/timeout
  内返回事件或无内容终态。
- 自适应传输配置是公开只读事实；健康、就绪与指标端点只属于内部基础设施探针，
  readiness 依赖失败必须返回 canonical typed failure，不得暴露自造状态错误体。

### REQ-002 UserAccount 安全终态闭环

- HTTP access-token 中间件、ticket 签发/消费和连接挂载必须使用同一受限服务凭据的
  `AccountSecurityAuthority`，在有界超时内 fail-closed；closed、suspended、
  未知或旧 `authEpoch` 一律不得建立或继续实时会话。
- 网关必须 durable 消费 `user.UserAccountClosed`、`user.UserSuspended` 和
  `user.UserRestored`：closed/suspended 先持久化 Redis admission fence，再清除
  该账户的待消费 ticket、租约、presence 和会话索引，并跨节点 relay 踢出进程内连接。
  同一 eventId 重放不得重复产生会话副作用。
- 跨节点 relay 订阅中断时，节点必须自动重连，并在重连期间使 readiness 失败；同步
  authority 与 durable admission fence 仍持续拒绝不安全会话，不能以过期 relay
  订阅或定时复核替代即时踢线通道。
- restore 只接受更高 `authEpoch`，不得恢复旧 ticket 或旧连接；新 epoch 仍须经同步
  authority 复核后才可建立连接。
- consumer 重试、DLQ、日志和指标不得保留 `accountId`、persona、payload、ticket 或
  原始错误；DLQ 只保存不可逆摘要、受控类别和 source stream 坐标，恢复从原 PEL 重放。

## 4. 契约引用

- connection：`quwoquan_service/services/realtime-gateway/contracts/realtime/connection/operations.yaml`
- push：`quwoquan_service/services/integration-service/contracts/external_integration/push_delivery/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 节点切换后可靠续接

- GIVEN 用户连接在一个 realtime-gateway 节点，在线状态已写入 Redis。
- WHEN 该连接中断并在另一节点恢复，同时存在未确认事件。
- THEN 网关按公开序列补齐未确认事件；离线渠道失败产生可重试终态而不是固定成功。

<a id="gwt-002"></a>
### GWT-002 账户终态即时断连且不可复活

- GIVEN 同一账户在多个 realtime-gateway 节点有 WebSocket/Long-poll 或待消费 ticket。
- WHEN 网关收到 `UserAccountClosed` 或 `UserSuspended`（含至少一次重放）。
- THEN 所有节点拒绝旧 ticket/epoch、关闭活跃连接，Redis 中不遗留该账户的 lease 或
  presence，重复事件仅产生一次连接关闭；authority 不可用时也不得放行。
- WHEN 随后收到更高 epoch 的 `UserRestored`。
- THEN 旧连接和 ticket 仍不可用，只有携带新 epoch 且被 authority 判定 active 的
  新连接可以建立。

## 6. 依赖

- 前置要求：可信实时鉴权、Redis 与 ChannelAdapter binding。
- 上游事实：owner 服务发布的 typed event，以及
  `user.UserAccountClosed` / `user.UserSuspended` / `user.UserRestored`。
- 下游结果：在线帧、离线投递任务或明确失败。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 真实渠道与多节点证据

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仓库已有 WebSocket/Redis 多节点语义与 APNs/FCM 协议实现，但本地模拟不能证明生产渠道回执、真实设备送达与跨实例连接恢复。
- 完成判定：`GWT-001` 在 `prod-hosted` 至少两个 realtime-gateway 实例及真实 APNs/FCM 设备渠道完成断线续接、跨实例投递、离线 handoff 和失败恢复，并有直接 `spec_ref`。
- 依赖：APNs/FCM 正式凭据、生产签名 App、真实设备与 `prod-hosted` 多实例发布权限。
