# realtime-call L2 设计

> **层级**：L2_business_capability design
> **契约真相源**：`quwoquan_service/contracts/metadata/rtc/**`
> **实现/变更证据**：`specs/changelog/CR-20260719-121-rtc-realtime-commercial-closure.yaml`
> **设计状态**：已收敛主线；商用准出仍为 partial

## 1. 设计目标

在不复制关系、消息、realtime 或媒体基础设施真相的前提下，建立一条可审计的通话主线：

```text
合法入口
  -> typed CallSession Facet
  -> rtc-service 聚合命令
  -> LiveKit Room / token
  -> realtime-gateway 单通道事件
  -> App 媒体连接与状态展示
  -> CallEnded durable event
  -> chat Conversation system_call_log
```

设计必须同时满足：

- CallSession 是唯一写聚合；CallParticipant 只能经聚合行为修改。
- `callType` 在端云 wire 中只使用 `audio | video`。
- 页面展示态不反向污染领域状态机。
- 在线事件只走 realtime-gateway；不保留 RTC 私有 WebSocket 或临时迁移分支。
- App 生产组合只依赖对象级 typed Facet 与 Remote adapter。
- 通话历史首先属于关联 Conversation，而不是新建独立历史产品面。
- 离线来电与媒体 QoE 未形成真实证据时，设计保持 blocked，不用声明或占位告警伪装完成。

## 2. 已冻结的关键决策

| 决策 | 选定方案 | 原因 |
|---|---|---|
| 聚合边界 | `CallSession` aggregate root + `CallParticipant` owned entity | 生命周期、人数上限、媒体控制与结束事实需要强一致 |
| 信令投递 | rtc-service outbox；CallRinging 先入 durable stream，由 notification 以 per-persona/device presence 协调 realtime-first + ACK-gated push | 复用可信 ticket/auth_ack，同时避免在线/离线竞态与无条件双投递 |
| 媒体路径 | LiveKit SFU + TURN | 1v1/多人使用同一媒体路径，避免双路径切换 |
| Token | Initiate/Answer/Join 响应直接下发短期 token 与配置化 `livekitUrl` | 绑定 room/participant/grants，避免额外 token 查询与地址硬编码 |
| App 边界 | lifecycle / participant / media / screen-share / query 五个细粒度 Facet | 单 Facet ≤10 方法，production Remote-only |
| 并发 | 服务端 version CAS + command receipt + 有限重放 | 客户端不掌握聚合版本，纯竞态可重放，业务冲突结构化返回 |
| 历史 | `CallEnded` → chat `system_call_log` | 用户在发起通话的会话中理解和回流；独立聚合页 deferred |
| 关系/交集 | 发起前关系门禁；来电/入会前最小信任证据 | 交集不授权，也不占据通话主舞台 |
| 离线来电 | 仓内实现已闭环，真实 provider/真机证据 partial | DeviceRegistration、APNs/FCM、native callback 与 cancel push 已实现；真实凭据和设备 readback 仍阻断 |
| QoE | metadata-first emitter → rollup/recording series → query Facade/Portal/alert | emitter、rollup、权威查询面与本地 readback 已落地；真实 series 前不准发布 |

通话录制、媒体文件产物和本期端到端加密不在当前对象图与 operation 集中；若未来立项，
必须从新的 metadata/acceptance/CR 开始，不恢复旧字段、旧接口或旧 Phase 路线。

## 3. 聚合与状态设计

### 3.1 CallSession

```text
initiated -> ringing -> connecting -> in_call -> ended
```

状态推进：

1. `InitiateCall` 创建聚合、参与者与 LiveKit Room，写 `initiated/ringing` 事实。
2. `AnswerCall` / `JoinCall` 把目标参与者推进到 `connecting` 并返回媒体凭据。
3. LiveKit 首个可用媒体建立后，端侧调用 `ReportMediaConnected`。
4. 至少两名参与者为 `connected` 时，会话进入 `in_call` 并记录 `startedAt`。
5. `RejectCall`、`CancelCall`、`HangupCall`、最后一人 `LeaveCall` 或超时进入 `ended`。

`endReason` 唯一枚举：

```text
normal | cancelled | rejected | no_answer | error | timeout | last_leave
```

`ended` 为终态；重复 answer/join/leave/hangup 使用 actor-scoped receipt 返回首次结果或
目标态 no-op，不再次发布状态推进事件。

### 3.2 CallParticipant

```text
invited -> ringing -> connecting -> connected -> left
                          \-> timeout
```

- owned identity 为 `userId`。
- `inviteStatus` 独立表达 `pending/ringing/accepted/declined/expired/cancelled`。
- `isMuted` / `isCameraOn` 是 CallSession 拥有的媒体控制投影。
- LiveKit track、active speaker、瞬时网络质量属于端侧运行态，不写回聚合字段。
- display name、avatar、关系文案由 named reader 组合，不进入 authoritative CallSession。

### 3.3 屏幕共享

- `StartScreenShare` / `StopScreenShare` 都是 CallSession command。
- 聚合保证同一时刻最多一个 `screenShareUserId`。
- LiveKit publish/unpublish screen track 是 command 成功后的媒体动作；媒体动作失败必须回写
  结构化失败或补偿，不能只改页面本地状态。
- iOS/Android/Web/OHOS 的采集能力差异经 `PlatformCapabilities` 与平台防腐层处理。

## 4. 服务端结构

当前目标结构：

```text
services/rtc-service/
├── cmd/api/main.go
├── internal/
│   ├── domain/call_session/
│   │   ├── model/
│   │   └── ports/
│   ├── application/
│   │   ├── call_orchestrator.go
│   │   └── call_outbox_relay.go
│   ├── adapters/
│   │   ├── http/
│   │   └── mq/
│   └── infrastructure/
│       ├── persistence/
│       └── livekit/
└── tests/
    ├── local_contract/
    └── api_integration/
```

边界：

- domain/application 不 import Mongo、Redis、LiveKit SDK 或 HTTP adapter。
- CallSession store 同一 Mongo transaction 提交 state CAS、command receipt 与 outbox。
- realtime 发布失败由 durable outbox relay 补偿；不得在 HTTP request 内把事件投递成功当作
  聚合提交条件。
- relationship capability 通过外部 port 查询，beta/gamma/prod 缺依赖时 fail-fast。
- GetCall/ListCalls 经 named reader + typed Slice；非参与者读取 fail-closed。
- LiveKit Room key、token 和地址只由 infrastructure adapter 生成/解析。

## 5. App 结构

```text
pure contracts generated client
  -> lib/cloud/remote/rtc/call_session/
       lifecycle / participant / media / screen-share / query adapters
  -> lib/application/... typed ports
  -> lib/ui/rtc providers
  -> incoming / outgoing / voice / video / participant picker pages
```

生产依赖图要求：

- production composition 只装配 Remote typed Facet。
- Alpha fixture 由独立 `quwoquan_cloud_mock` 包注入。
- UI 不构造 path、operationId、auth header、decoder context 或 LiveKit URL。
- UI 不依赖动态 Map、聚合仓储接口、运行时数据源模式或 debug 模拟分支。
- Remote 失败必须保留 `RuntimeFailure`；不能返回 fixture、空成功或本地合成 CallSession。

端侧状态分为三层：

1. **领域快照**：CallSession / CallParticipant DTO。
2. **媒体运行态**：LiveKit participants、tracks、speaker、connection state。
3. **展示态**：connecting、ringing、waitingPeer、inCall、reconnecting、weakNetwork、
   peerNoAnswer、peerLeft、ended，由前两层纯派生。

三层不能互相覆盖：例如 LiveKit track 暂缺不能把服务端 CallSession 写成 ended，页面展示
reconnecting 也不能新增领域状态枚举。

## 6. 在线信令设计

### 6.1 凭据

```text
App Bearer
  -> IssueConnectionTicket
  -> one-time ticket
  -> realtime WebSocket/LongPoll upgrade
  -> server auth_ack
  -> trusted per-persona/device subscriptions
```

- ticket 短期、一次性消费，长期凭据不进入 URL。
- 服务端从可信 principal 派生用户与 topics，客户端不能自报 userId/topics。
- 重放、过期、伪造和跨用户订阅均 fail-closed。

### 6.2 RTC 事件

rtc-service 通过 outbox 发布 canonical 事件：

- `CallInitiated`
- `CallRinging`
- `CallAnswered`
- `CallConnected`
- `CallEnded`
- `ParticipantJoined`
- `ParticipantLeft`
- `ScreenShareStarted`
- `ScreenShareStopped`

wire type 只使用 `events.yaml#client_ws_type`，例如 `call.ringing`；Go domain event 名不得直接
泄漏到 wire。普通 RTC 状态事件经 realtime-gateway 投递到目标参与者的 per-persona
channel；CallRinging 先进入 durable stream，由 notification-service 按设备 presence
发布 realtime，App 的统一 event handler 再分发到 RTC event bus。

realtime-gateway 不承载 CallSession 状态，也不决定关系权限。

## 7. 离线来电设计边界

目标链：

```text
CallRinging
  -> durable events.rtc.call_ringing
  -> NotificationDeliveryJob per endpoint
  -> device presence
  -> online realtime dispatch -> presentation ACK (750ms)
  -> offline / ACK timeout -> APNs VoIP / FCM high priority
  -> native callback + deliveryKey/expiry guard
  -> incoming call UI
  -> AnswerCall / RejectCall
```

平台行为：

- iOS：PushKit 收到后按平台时限上报 CallKit；媒体权限在接听阶段处理。
- Android：FCM high-priority + full-screen intent；Android 14+ 无权限时降级 heads-up。
- Web：M2 仅支持前台 realtime 站内来电；Web Push/Service Worker deferred，不伪装成已实现。
- OHOS：通过 capability profile；无实现时结构化不可用，不在业务层判断平台。

当前 `events.yaml#push_policy` 冻结 payload、deliveryKey、过期与目标通道。
DeviceRegistration、APNs/FCM provider、endpoint 加密存储/解密、presentation ACK、native
callback，以及 `ring/cancel` 共用 deliveryKey 的迟到来电撤销均已实现并通过 local/API/
native compile。真实 APNs/FCM 凭据下后台、锁屏、被杀唤醒、receipt/readback 与到达 P95
尚未取得，因此 R-RTC01 保持 partial。

## 8. 媒体、弱网与 PiP

### 8.1 LiveKit

- 每个 CallSession 对应一个 LiveKit Room。
- Initiate/Answer/Join 响应下发 token 与 `livekitUrl`。
- 端侧连接后订阅真实 tracks；视频格无 track 时展示可解释状态，不渲染假画面。
- 网络切换使用 LiveKit reconnect/ICE restart 能力；恢复不能新建 CallSession。

### 8.2 弱网

UI 只消费有界网络质量与连接态：

- 弱网先降视频层，优先保留音频。
- reconnecting 时冻结最后可用画面并显示恢复状态，禁止黑屏假死。
- 恢复成功后调用/保持 `ReportMediaConnected` 幂等语义。
- 超时、恢复失败和上游不可用映射到 RuntimeFailure 与明确终态。

具体编码层、FEC/NACK 等属于 LiveKit/runtime 配置能力；未有受控运行证据时不在产品规格中
声称已达到固定弱网效果。

### 8.3 PiP 与通话条

- App 内 PiP/通话条是同一 active call 的投影，不创建第二会话状态。
- 点击回流 canonical 通话页。
- PiP 挂断必须执行 `HangupCall`；多人仅自己退出时执行 `LeaveCall`。
- 页面关闭、系统返回、后台恢复与云端 `CallEnded` 竞态必须幂等收敛到一个结束结果。

## 9. 通话历史

`CallEnded` 同时承担：

1. 向参与者发送实时结束事件；
2. 写入 durable stream；
3. 由 chat-service 幂等投影一条 `Message(type=system_call_log)`。

消息内容从 CallEnded 的 `callType/endReason/durationMs/startedAt/endedAt` 生成。App 只渲染
typed system message，不拼装第二份历史模型。`ListCalls` 保留查询合同供运维/未来产品裁决，
当前不建设独立历史聚合页。

## 10. 关系门禁、信任与交集

### 10.1 授权

- 1v1 `InitiateCall` 需要 trusted persona、mutual relationship 且双方未 block。
- UI 只读关系 capability 决定入口；服务端再次复核。
- Presence、交集分数、共同标签、是否同群都不能替代授权。

### 10.2 信任证据

`TrustRelation = known | possibly_unknown` 用于来电/入会前风险判断：

- known：联系人、互相关注、当前会话/群内可信来源。
- possibly_unknown：其他群来源或缺少直接关系的参与者。

信任证据只在来电页、预入会和新成员加入时必要展示。通话舞台不常驻共同兴趣、共同关注、
交集列表或推荐理由；这样既避免泄露，也避免遮挡媒体主任务。

## 11. 可观测设计

### 11.1 已有

- rtc-service HTTP 路由延迟与错误率由 runtime middleware 暴露。
- `rtc_call_outcome` 记录通话结果、时长和参与人数。
- `realtime_connect_result` 记录 WebSocket/LongPoll 建连结果。
- Prometheus 已有 rtc 命令路由 P95 与 InitiateCall 错误率规则。

### 11.2 RTC media QoE

本地实现已完成：

1. `event_catalog.yaml` 冻结 `rtc_media_qoe` 的低基数字段；
2. App `RtcMediaQoeTracker` 对同一通话只结算一次，重连恢复不误记异常终态；
3. 接听前取消/未接即使本地已连接 SFU 仍归为 `abandoned`，SLS 分子与分母同时排除；
4. `rtc_qoe` Scheduled SQL 使用 mergeable fixed histogram，并保留 freshness 水位；
5. SLS 告警消费 `connection_lost`，LiveKit 告警只消费官方
   `livekit_packet_loss_percent_bucket` / `livekit_quality_score_bucket`。

剩余顺序：

1. 通过受控 Gamma SLS 取得真实 raw/rollup series；
2. 建立可执行的 QoE 查询面板，而不是 Grafana 文本占位；
3. 真机执行强网、弱网、重连、异常中断场景；
4. 完成告警触发、通知、恢复与 prod `gray_initial` 回滚演练。

不得直接对不存在的 `rtc_*_qoe` series 写 PromQL，也不得把静态规则加载成功当作 readback。

## 12. 测试设计

| 证据层 | 主对象 | 必须补齐 |
|---|---|---|
| `local_contract` | 状态机规则、wire、Facet parity、权限/页面派生、PiP 操作 | timeout/connected、屏幕共享互斥、PiP hangup、QoE 去重 |
| `api_integration` | 真实 Mongo/Redis、receipt/outbox、LiveKit adapter、chat projection | timeout/connected、screen share、offline push provider contract、QoE rollup |
| `user_acceptance` | 真实页面、设备、媒体、后台与发布 | 离线来电、PiP hangup、屏幕共享、弱网/QoE、prod gray |

现有 Call lifecycle、room management、relationship gate、system_call_log 与两条 RTC UAT
继续作为已存在的支撑证据；L2/L3 acceptance 在新增场景没有 recorded report 前保持
`partial/pending`。

## 13. 四环境设计与准出

- **Alpha**：pure contracts + isolated mock package；验证确定性状态与错误，不访问云。
- **Beta**：Remote generated client + rtc-service + Mongo/Redis + LiveKit adapter + chat projector。
- **Gamma-local**：真实设备、真实媒体、离线/后台/锁屏、网络切换、PiP、屏幕共享和 QoE 原始证据。
- **Prod-hosted gray-initial**：真实 provider、SLS/Prometheus readback、告警/ack/resolved、
  canary 与回滚 receipt。

当前 Gamma full workload 因缺失受控 product telemetry SLS secret fail-closed。该阻断是
正确安全行为，不能通过禁用 telemetry、注入占位 Secret 或跳过 release verify 绕过。

## 14. 被淘汰路线

- RTC 自建第二条信令连接或“先临时、后迁移”的双轨。
- 端侧聚合仓储接口、production Mock、运行时 Mock/Remote 开关。
- 单独 token 查询、客户端拼 LiveKit 地址、客户端自报身份/topics。
- `voice` 作为 callType；canonical 值只有 `audio/video`。
- 独立通话记录页作为当前主入口。
- 用交集模块占据通话页，或用交集/presence 放宽关系门禁。
- 在没有 emitter/rollup 的情况下补 RTC QoE 告警。

## 15. 当前 Exit Review

- **规格达成**：单通道、聚合、typed Facet、状态机、history projection 与交集边界已收敛。
- **测试证据**：现有 local/API/UAT 可定位，但 timeout/connected、offline push、
  screen share 与 media QoE 的真实设备/环境证据仍需 planned 转 recorded；本地 QoE
  状态机、rollup 和规则合同已 recorded。
- **E2E**：Gamma/Prod 尚未准出。
- **产品/UX**：五个页面有承载，真实视觉与设备矩阵未达到 P4 证明。
- **运营观测**：服务 RED、端侧 QoE emitter、SLS rollup/alert、RTC 专属查询 Facade 与
  Product Portal 24 小时窗口已落；Gamma/Prod 真实 series、异常场景 readback 与演练缺失。
- **剩余风险**：R-RTC01、R-RTC02，以及受控 SLS secret 阻断。
