# L2 规格：realtime-call — 实时音视频通话

> **层级**：L2_business_capability（隶属 L1 `chat-conversation`）
> **规格状态**：specified
> **商用状态**：partial；不得因本地契约或页面存在而标记 ready
> **契约真相源**：`quwoquan_service/contracts/metadata/rtc/**`
> **增量记录**：`specs/changelog/CR-20260719-121-rtc-realtime-commercial-closure.yaml`

## 0. Spec Entry

- **AppRoot Journey / Scenario**：`message-social-connection` 的实时行动，以及
  `intersection-action-to-companionship` 中经关系门禁后的通话行动；RTC 不另造第二套关系旅程。
- **L1_domain_service**：`chat-conversation`。
- **L2_business_capability**：`realtime-call`。
- **L3_story**：`one-to-one-call`、`group-call`、`call-experience`、
  `media-infrastructure`，以及同目录下四个收敛 Story 节点。
- **验收意图**：L2 用 SIT；L3 用 GWT / contract；面向设备的完整来电与通话流程回链 AppRoot UAT。
- **测试证据**：`local_contract`、`api_integration`、`user_acceptance`。真实媒体、离线来电、
  弱网 QoE 与发布准出不能由 Widget 或 fake media 替代。
- **用户价值**：在合法关系或会话上下文中可靠发起、接听和结束 1v1 / 多人音视频通话，
  网络异常时可恢复，结束后回到原会话并留下可理解的通话记录。

当前真实阻断：

1. iOS/Android 的 DeviceRegistration、APNs/FCM provider、PushKit/全屏意图桥、
   `ring/cancel` 同一 deliveryKey 撤销与安全令牌存储已落地；仍缺受控凭据下后台、锁屏、
   被系统终止真机的 provider receipt、设备 readback 与到达 P95。Web 本期只支持前台
   realtime 站内来电。
2. `rtc_media_qoe` emitter、hourly rollup、SLS/LiveKit 告警、24 小时查询 Facade、
   Product Portal 回读与本地告警 readback 已落地，但 Gamma/Prod 尚无真实 series 和演练。
3. Gamma full cold-start 与 LiveKit 运行制品仍被缺失的受控
   `product_telemetry_sls/gamma.env` 凭据 fail-closed。

## 1. 一句话定义

为 1v1 与最多 32 人的社交通话提供单轨 CallSession 生命周期、LiveKit 媒体连接、
realtime-gateway 实时事件、关系门禁、通话中控制、屏幕共享、弱网恢复和会话内
`system_call_log` 回流。

## 2. 本期范围与明确非目标

### 2.1 In Scope

- 1v1 `audio` / `video` 通话：发起、振铃、接听、拒绝、取消、媒体建连、挂断和超时。
- 多人通话：邀请、加入、离开、最多 32 人、最后一人离开结束。
- 媒体控制：静音、摄像头开关、同一时刻一人屏幕共享。
- 通话体验：连接中、振铃、通话中、重连、弱网、结束；App 内 PiP / 通话条回流。
- 在线信令：CallSession 领域事件经 realtime-gateway 单通道按用户投递。
- 离线来电：仓内实现已闭环，真实 provider/设备/发布证据仍是商用阻断；不得以本地
  payload、模拟器或原生编译冒充真机到达。
- 通话历史：`CallEnded` 投影为关联 Conversation 的 `system_call_log` Message。
- 关系与信任：发起前做关系门禁；来电与入会前消费最小信任证据。

### 2.2 Out of Scope / Deferred

- 通话录制、LiveKit Egress、录制文件、录制 URL 与录制事件。
- E2EE 本期承诺。未来若重新立项，必须新增 metadata 对象/operation、隐私、密钥生命周期、
  三层测试与独立 CR；不得恢复旧占位字段或旧 Phase 文案。
- 独立通话历史聚合页。`ListCalls` 保留对象查询合同，当前用户主形态是会话内
  `system_call_log`。
- 呼叫链接入会、PSTN、直播推流、实时字幕/翻译、虚拟背景、超过 32 人的大型会议。
- 以 P2P 作为 SFU 的临时 fallback；当前媒体路径统一为 LiveKit SFU。

## 3. Canonical 业务对象

### 3.1 CallSession 聚合根

| 主题 | 当前 metadata 合同 |
|---|---|
| 标识 | wire 使用 `callId`；存储源为 Mongo `_id` |
| 类型 | `callType = audio | video` |
| 状态 | `initiated | ringing | connecting | in_call | ended` |
| 关联 | `conversationId?`、`circleId?`、`initiatorId`、`initiatorRingtoneId?` |
| 媒体房间 | `roomId` 由 rtc-service 的 LiveKit port 管理；客户端不得硬编码地址 |
| 人数 | `maxParticipants`，上限 32；`participantCount` |
| 屏幕共享 | `isScreenSharing`、`screenShareUserId?` |
| 结束事实 | `endReason?`、`durationMs?`、`startedAt?`、`endedAt?` |
| 并发 | 服务端加载 version 做内部 CAS；公开请求不携带 version |
| 幂等 | actor-scoped command receipt；同一意图达到目标态时持久化 no-op receipt |

CallSession 生命周期唯一为：

```text
initiated -> ringing -> connecting -> in_call -> ended
```

- `ReportMediaConnected` 把参与者推进到 `connected`；至少两人 connected 后会话进入
  `in_call` 并写 `startedAt`。
- `ended` 是终态。
- `endReason` 只允许
  `normal | cancelled | rejected | no_answer | error | timeout | last_leave`。
- 30 秒未接的 1v1 呼叫以 `no_answer` 结束；系统超时与业务无应答不得混写。

### 3.2 CallParticipant owned entity

CallParticipant 是 CallSession 内嵌 owned entity，不得建立独立 Store、Repository、Facade
或跨上下文写入口。

| 字段 | 当前合同 |
|---|---|
| 身份/角色 | `userId`；`role = initiator | invitee` |
| 媒体状态 | `isMuted`、`isCameraOn` |
| 生命周期 | `status = invited | ringing | connecting | connected | left | timeout` |
| 邀请状态 | `inviteStatus = pending | ringing | accepted | declined | expired | cancelled` |
| 邀请来源 | `invitedBy?` |
| 时间 | `joinedAt?`、`leftAt?` |

昵称、头像、来源标签和信任提示不是聚合权威状态：来电首帧使用 `CallRinging` 的最小快照，
通话中展示由端侧组合 user/chat named reader 与 LiveKit 运行态。

### 3.3 关系与相邻对象

- `Conversation`：发起上下文和通话结束后的 `system_call_log` 承载者。
- `Circle`：可作为多人通话来源引用，不拥有 CallSession。
- `Persona`：命令 actor；1v1 发起者必须通过关系门禁且未被拉黑。
- realtime `Connection`：一次性 ticket、`auth_ack`、heartbeat、lease/fencing；只承载投递，
  不能替代关系授权。
- LiveKit Room / TURN：外部媒体能力，由 rtc-service port 管理，不成为 App 写对象。

## 4. Canonical Operation 与响应

路径、方法、Facet、错误码和 SLO 只来自
`contracts/metadata/rtc/call_session/service.yaml`。

| Facet | Operation |
|---|---|
| `CallLifecycleCommandFacet` | `InitiateCall`、`AnswerCall`、`RejectCall`、`CancelCall`、`HangupCall` |
| `CallParticipantCommandFacet` | `JoinCall`、`LeaveCall`、`InviteToCall`、`ReportMediaConnected` |
| `CallMediaControlCommandFacet` | `ToggleMute`、`ToggleCamera` |
| `CallScreenShareCommandFacet` | `StartScreenShare`、`StopScreenShare` |
| `CallQueryFacet` | `GetCall`、`ListCalls` |

关键约束：

- `InitiateCall`、`AnswerCall`、`JoinCall` 在响应中直接返回短期 LiveKit token 与
  `livekitUrl`；不设置独立 token 查询 operation。
- 屏幕共享使用
  `POST /rtc/calls/{callId}/screen-share/start|stop`；不存在旧的无动作后缀路径。
- RTC 不提供私有 WebSocket endpoint。CallRinging、CallAnswered、CallConnected、CallEnded、
  ParticipantJoined/Left、ScreenShareStarted/Stopped 均经 realtime-gateway 单通道投递。
- App 生产组合只依赖五个 typed Facet 的 Remote adapter；不使用聚合仓储接口、
  production Mock、运行时数据源切换或失败后本地合成成功。
- Alpha 替身只允许由 `quwoquan_cloud_mock` 的 immutable fixture bundle 注入。

## 5. 端到端数据流

### 5.1 发起到媒体建连

```text
App typed Facet
  -> rtc-service operation guard + trusted persona
  -> relationship gate / active-call uniqueness
  -> Mongo transaction: CallSession + command receipt + outbox
  -> LiveKit Room / short-lived token
  -> CallRinging event
  -> realtime-gateway online delivery
  -> callee AnswerCall / JoinCall
  -> LiveKit media connected
  -> ReportMediaConnected
  -> CallConnected / CallSession.in_call
```

realtime-gateway 只投递可信服务端事件；SDP/ICE 等媒体协商由 LiveKit SDK/服务完成，
不恢复 RTC 私有 WebSocket。

### 5.2 离线来电

`events.yaml` 的 M2 policy 覆盖 iOS VoIP Push 与 Android FCM high-priority/full-screen
intent。DeviceRegistration、provider dispatch/receipt、平台回调、展示 ACK、过期/重复
去重以及 `ring/cancel` 可靠撤销已实现并有 local/API/native compile 证据；真实 APNs/FCM
凭据、后台/锁屏/被杀真机 readback 未闭合前，离线来电仍保持 partial。Web Push/Service
Worker 不属于 M2；Web 仅在前台 realtime 连接存在时展示站内来电。

### 5.3 结束与历史

```text
Hangup / Leave(last participant) / Reject / Cancel / Timeout
  -> CallSession.ended + CallEnded outbox
  -> realtime-gateway 通知参与者
  -> durable stream
  -> chat-service 幂等投影
  -> Conversation Message(type=system_call_log)
  -> App 气泡展示并可从合法入口回拨
```

不得恢复独立 previous call DTO、客户端拼接记录或旧类型别名；`callType` 永远为
`audio | video`，消息类型为 `system_call_log`。

## 6. 入口、关系门禁与交集策略

### 6.1 入口

- 1v1：会话输入区动作面板或 Persona 主页合法动作。
- 多人：群会话/圈子上下文进入参与者选择页，再调用 `InitiateCall` / `InviteToCall`。
- 通话中：控制栏邀请、静音、摄像头、屏幕共享、离开/挂断。
- 通话历史：关联会话中的 `system_call_log`；独立聚合页 deferred。

### 6.2 关系门禁

- UI 只消费 relationship capability；不能自行用在线状态、共同标签或交集分数授权。
- rtc-service 必须最终复核 trusted persona、1v1 关系与 block 状态。
- `RTC.USER.not_mutual`、`RTC.USER.blocked` 等错误由 metadata/codegen 提供结构化恢复语义。
- Conversation 存在不等于可以发起 1v1 通话；在线 presence 也不等于授权。

### 6.3 交集只做信任证据

RTC 与交集的交点只有两处：

1. **发起前**：关系门禁决定能否行动；交集事实不能放宽门禁。
2. **来电/入会前**：`known | possibly_unknown` 与来源标签帮助用户判断是否接听或展示敏感画面。

通话页不机械展示共同兴趣、共同关注数量、交集列表或推荐理由。建连后页面只保留参与者、
媒体、网络与安全状态；信任风险只在新成员进入等必要时刻轻量提示。

## 7. 页面承载与过程态

| 页面 | 主要职责 | 商用要求 |
|---|---|---|
| `incoming_call_page.dart` | 来电首帧、来源/信任、接听/拒绝/过期 | 离线 Push 未完成前不能标 P4 |
| `outgoing_call_page.dart` | 振铃、取消、忙线、无应答 | CancelCall 与 timeout 竞态以服务端为准 |
| `voice_call_page.dart` | 音频路由、静音、重连、结束 | 后台音频与结构化降级 |
| `video_call_page.dart` | 视频格、摄像头、PiP、屏幕共享 | 真实 track；无黑屏假成功 |
| `call_participant_picker_page.dart` | 候选、上限、邀请结果 | 只经 CallSession command 修改 owned entity |

UI 至少覆盖 `connecting / ringing / waiting peer / in call / reconnecting / weak network /
peer no answer / peer left / ended`。展示态是端侧对 canonical 状态与媒体状态的派生，
不得反向扩充 CallSession 状态枚举。

PiP/通话条必须支持点击回流；PiP 挂断必须调用 `HangupCall` 或多人 `LeaveCall` 的正确语义，
不能只关闭浮层。

## 8. 非功能与黄金指标

### 8.1 服务合同

- command SLO：P95 300ms、availability 99.9%（以各 operation metadata 为准）。
- query SLO：P95 500ms、availability 99.9%。
- LiveKit token 绑定 roomId、participantId 与 grants，由服务端配置地址并短期签发。
- 32 人是聚合与媒体共同上限；第 33 人返回 `RTC.USER.call_full`。
- 网络恢复不得创建第二个 CallSession；重复命令由 receipt 幂等。

### 8.2 RTC 一级黄金指标（最多 3 个）

| 指标 | 定义 | 目标口径 | 当前证据 |
|---|---|---|---|
| 有效媒体接通率 | accepted/joined 的合法尝试中，至少两名参与者进入 connected 并使会话 `in_call` 的比例 | 商用门槛建议 ≥98%，需在 rollout 前冻结 | emitter、abandoned 排除与 raw/rollup 查询已闭环；缺 Gamma/Prod 真实样本 |
| 接听到媒体可用 P95 | Answer/Join 成功到 `ReportMediaConnected` 的时长 | 强网建议 ≤3s；按 audio/video、网络等级、版本下钻 | emitter + `rtc_qoe` hourly rollup + SLS alert 已落；缺 Gamma readback |
| 非预期媒体中断率 | 已 `in_call` 会话中非用户主动、非正常结束的中断比例 | 建议 ≤2%；重连成功率/次数作为二级诊断 | `connection_lost` 终态、rollup 与 SLS/LiveKit alert 已落；缺真实 series |

Prometheus 现同时抓取 rtc-service RED 与 LiveKit 原生 packet/quality 指标；SLS 消费
`rtc_media_qoe` 端侧终态。两者语义不同，不能互相替代；在 Gamma 真实 series/readback
完成前，告警合同仍不能作为发布通过证据。

## 9. 四环境准出

| 环境 | 必须证明 | 当前判断 |
|---|---|---|
| Alpha | metadata/codegen、typed Facet parity、状态/错误/权限 Widget、realtime payload、无 production Mock 可达 | 可作为契约证据；不能证明真实媒体与离线来电 |
| Beta | Remote generated client、真实 rtc-service Mongo/Redis、关系门禁、receipt/outbox、chat `system_call_log` 投影、LiveKit adapter | partial；按每次环境报告判定 |
| Gamma-local | Android/iOS 设备上的接听/挂断、timeout/connected、网络切换、PiP 挂断、屏幕共享、离线来电、媒体 QoE 原始证据 | blocked：受控 SLS secret 缺失；当前仅有 iOS 模拟器，不能替代离线 Push 真机 |
| Prod-hosted gray-initial | 不可变制品、真实 Push provider、SLS/Prometheus readback、三项黄金指标、告警演练、回滚 receipt | pending；不得提前标 ready |

## 10. 验收与计划测试

L2 `acceptance.yaml` 保持 `partial`，并显式规划：

- timeout / connected 状态机；
- iOS/Android 离线来电、展示 ACK、过期/重复去重；Web 前台站内来电降级；
- PiP 内挂断后的云端终态与导航收尾；
- 屏幕共享 start/stop、互斥、权限与平台降级；
- RTC media QoE emitter、rollup、readback 与阈值；
- Gamma / Prod 受控 SLS 与 LiveKit 运行证据。

已有测试文件只能证明其实际断言，不得用“文件存在”推导上述未覆盖项已通过。

## 11. 发布、灰度与回滚

- 发布顺序：Alpha contract → Beta Remote/API → Gamma-local 设备矩阵 →
  Prod gray-initial；没有 `prod-gray` 环境。
- 回滚触发以三项黄金指标、崩溃/ANR、离线来电到达和服务可用性为准；阈值必须有真实 series。
- RTC 功能开关只能控制入口/rollout，不得在同一生产二进制切 Mock/Remote 或恢复私有信令。
- 未具备离线来电时必须诚实标记能力不可用，不能用在线 WS 或本地通知冒充。

## 12. 剩余风险

- `R-CLOUD01`：可信实时鉴权只差受控 Gamma/Prod 运行证据，不能与本规格新增风险重复计算。
- `R-OBJ-002`：页面曝光/停留与通话结果已覆盖，但不包含媒体 QoE 黄金指标。
- `R-RTC01`：仓内 Push 全链已实现；真实 APNs/FCM 凭据、真机后台/锁屏/被杀 readback、
  到达 P95 与取消竞态发布制品仍缺失。
- `R-RTC02`：emitter、rollup、权威查询 Facade、Portal 与告警合同已落地；Gamma/Prod
  真实 series、弱网/重连/异常中断与发布回滚演练仍缺失。
- Gamma SLS secret 是当前真实环境阻断；注入 Secret 前不得宣称 full cold-start、LiveKit 或
  release verify 已通过。
