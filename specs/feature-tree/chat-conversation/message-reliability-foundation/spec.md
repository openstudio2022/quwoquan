# L2 Business Capability：消息可靠性地基 (`message-reliability-foundation`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：`本层 design.md`

## 1. 能力目标

让消息在冷启动、离线、断连、杀进程与弱网下仍然可读、可达、不丢、不重、不乱序，并让会话的首帧、滚动与发送延迟受声明预算约束。本能力是消息域一切差异化体验的承载前提：没有可靠的时间线，交集与助手进入会话只会放大不可用面。

## 2. 范围与非目标

### In Scope

- 消息时间线的本地权威副本、水合顺序与缓存来源可区分性。
- 历史消息的游标分页与顺序稳定性。
- 传输恢复语义、持久事件流与断连期间的缺口补齐。
- 离线设备推送投递与打开推送后的会话直达和未读收敛。
- 会话运行时的性能预算声明与门禁接线。

### Out of Scope

- 会话来源建模、消息类型渲染与富媒体行为，由 [`list-detail-message-delivery`](../list-detail-message-delivery/spec.md) 负责。
- 会话列表（而非消息时间线）的本地缓存，由 [`chat-experience-optimization`](../chat-experience-optimization/spec.md) 的 `chat-list-local-cache` 负责。
- 交集、助手与可行动对象进入消息的差异化体验；本能力只保证其所依赖的时间线可靠性。

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-012`](../../spec.md#scn-012)
  - 本能力接收：会话标识、本地已持有的最大 seq 与传输状态。
  - 本能力处理：先水合本地时间线再后台刷新，按 seq 游标补齐缺口。
  - 本能力输出：一份无缺号、无重复、按 seq 稳定排序的会话时间线。
  - 失败时终态：区分「本地命中且离线」与「远端失败」，不以空列表冒充已读完。
- [`JNY-007 / SCN-016`](../../spec.md#scn-016)
  - 本能力接收：离线期间产生的会话事件。
  - 本能力处理：经持久事件流与推送投递通道到达设备。
  - 本能力输出：设备可见推送，打开后直达对应会话且未读收敛。
  - 失败时终态：投递失败保留未确认态，不得写成已送达。

## 4. Story

- [`message-timeline-local-persistence`](./message-timeline-local-persistence/spec.md)：冷启动与离线打开会话可读最近历史。
- [`message-paging-and-ordering`](./message-paging-and-ordering/spec.md)：向上翻阅历史连续、不重复、不遗漏、不回退。
- [`realtime-push-and-offline-sync`](./realtime-push-and-offline-sync/spec.md)：在线即时收到消息，断连重连后按游标补齐缺口。
- [`chat-offline-push-delivery`](./chat-offline-push-delivery/spec.md)：离线设备收到真实推送并可打开到会话。
- [`message-runtime-performance-budget`](./message-runtime-performance-budget/spec.md)：会话首帧、滚动与发送延迟受声明预算约束。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 本地时间线是唯一权威本地副本

- 会话打开必须先水合本地时间线再发起远端刷新；本地为空且远端失败时必须呈现可重试的失败态，不得以空列表冒充「没有消息」。
- 消息本地存储必须唯一：不得在既有 chat 本地库之外新建第二个消息存储，否则搜索与时间线成为两份消息真相。
- 缓存读取结果必须可区分本地命中、后台刷新中、离线只读与本地待发四种来源，端侧展示据此分流。

<a id="req-002"></a>
### REQ-002 顺序与幂等由 seq 与 clientMsgId 共同保证

- 消息排序必须以服务端 seq 为唯一依据，不得以时间戳排序。
- 同一 `clientMsgId` 在弱网重试、杀进程重启与推送回灌下最多落一条。
- 分页与实时插入必须收敛到同一条插入链路，不得为翻页与推送各维护一套合并逻辑。

<a id="req-003"></a>
### REQ-003 传输恢复必须是真实事件而非约定

- 传输层恢复必须发出可被端侧消费的恢复事件；不得保留无人发出的恢复分支或无人调用的补洞入口。
- 恢复后必须以端侧已持有的最大 seq 为起点向服务端补齐缺口，补齐结果与实时推送经同一去重路径合并。

<a id="req-004"></a>
### REQ-004 离线可达不得伪造终态

- 会话事件必须落持久流后再投递，断连期间产生的事件在重连或推送通道上至少投递一次。
- 推送投递的未确认态不得写成已送达；只有 provider 回执确认才允许标记送达。

<a id="req-005"></a>
### REQ-005 性能预算是声明的，不是事后测量的

- 会话首帧、长列表滚动 jank 比、发送到气泡确认延迟必须有声明阈值并进入门禁；阈值来源必须唯一，服务端复用所属 `operations.yaml` 的 `slo.latency_p95_ms`。
- 端侧预算文件必须复用既有预算文件形状与既有门禁脚本，不得新造并行格式或并行脚本。

<a id="req-006"></a>
### REQ-006 服务本地契约引用边界

- 跨边界字段、operation、事件与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 6. 契约与依赖

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 读取事实：会话成员关系与消息 seq 水位。
- 写入事实：本地时间线副本、同步游标与推送投递记录。
- operation / event / surface：`quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml`、`quwoquan_service/services/realtime-gateway/contracts/realtime/connection/operations.yaml`、`quwoquan_service/services/notification-service/contracts/notification_delivery/notification_delivery_job/operations.yaml`
- 一致性要求：本地副本与服务端以 seq 收敛；投递语义为至少一次加端侧幂等去重。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 冷启动与离线可读

- GIVEN 设备曾同步过某会话且当前处于飞行模式。
- WHEN 用户冷启动应用并打开该会话。
- THEN 时间线由本地副本水合并按 seq 有序展示，来源标记为离线只读。
- AND 恢复网络后后台刷新补齐增量，不产生重复条目也不回退已读位置。

<a id="sit-002"></a>
### SIT-002 断连期间不丢消息且重连补洞

- GIVEN 双方在同一会话中，一侧断网。
- WHEN 断网期间对端连续发送多条消息，随后断网侧恢复连接。
- THEN 恢复侧按已持有的最大 seq 补齐缺口，最终序列无缺号、无重复且按 seq 有序。
- AND 补齐失败时呈现可重试失败态，不得以静默截断冒充完整。

<a id="sit-003"></a>
### SIT-003 离线推送直达会话且未读收敛

- GIVEN 接收方设备离线且已登记有效推送端点。
- WHEN 发送方在该会话发送消息。
- THEN 接收方设备收到由真实 provider 投递的推送，打开后直达该会话且该会话未读收敛。
- AND provider 未回执时投递记录保持未确认态，不得标记为已送达。

## 8. 开放事项

<a id="open-002"></a>
### OPEN-002 冷启动与离线可读剩跨进程读回与增量收敛证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 `SIT-001` 的两段端到端证据：真实持久库跨进程冷启动读回（飞行模式打开会话）、
  恢复网络后后台刷新补齐增量不产生重复条目也不回退已读位置。时间线本地落盘
  （水合→刷新→写回，四态来源可区分并驱动展示）与历史
  keyset 分页（滚动触发、有序无重复、终止判定、失败保留内容）已实现并有
  local_contract 证据，详见
  [`message-timeline-local-persistence` OPEN-001](./message-timeline-local-persistence/spec.md#open-001)
  与 [`message-paging-and-ordering` OPEN-001](./message-paging-and-ordering/spec.md#open-001)。
- 完成判定：`SIT-001` 的 2 条 THEN 组全部具备子句级 `spec_ref`（`sit-001.t1..t2`）绑定的真实测试证据，其中冷启动读回必须来自真实持久库跨进程用例，不接受内存 double。

<a id="open-003"></a>
### OPEN-003 断连补洞链路尚未成立

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前会话事件只做即时广播且长轮询无游标，断连期间的消息永久丢失。恢复分支与补洞入口都存在但不可达。群分发串行且首个失败中断整批。
- 完成判定：`SIT-002` 的 2 条 THEN 组全部具备子句级 `spec_ref`（`sit-002.t1..t2`）绑定的真实测试证据，且断言覆盖断连游标补洞可达与群分发单点失败不中断整批。

<a id="open-001"></a>
### OPEN-001 离线推送验收受控凭据阻断

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`chat-offline-push-delivery` 复用与 `media-infrastructure/OPEN-002` 同一条 APNs/FCM 受控凭据通道，缺 Gamma/Prod 凭据与双真机 readback 时 `SIT-003` 无法取得真实投递证据。禁止以本地通知或 fixture 关闭该验收。
- 完成判定：`SIT-003` 由真实 provider 回执与双真机 readback 证明
- 依赖：`realtime-call/media-infrastructure` 的受控凭据申请
