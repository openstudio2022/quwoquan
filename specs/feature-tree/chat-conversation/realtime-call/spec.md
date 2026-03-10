# L2 规格：realtime-call — 实时音视频通话

> **层级**：L2_feature（隶属 L1 `chat-conversation`）
> **状态**：specified
> **依赖**：`gateway-orchestrator-foundation/realtime-gateway`（信令推送通道）

## 0. 一句话定义（P1）

面向趣聊 1v1 聊天与群聊用户，解决缺乏实时语音/视频通话能力的问题，实现 1v1 + 多人（上限 32 人，对标 FaceTime）音视频通话端到端闭环，支持录制、屏幕共享，对标 FaceTime / 微信 / Teams 一流体验。

## 1. 背景与动机

趣聊当前仅有文本/图片/视频/语音消息（store-and-forward），无任何实时双向通信能力。语音消息（voice-message）正在独立设计，属于「异步留言」模式，与实时通话互补、不互替。

实时音视频通话是社交 App 的核心功能（微信日均通话量超 5 亿次），缺乏此能力严重影响用户留存和通信完整性。

### 1.1 与语音消息的关系

| 维度 | 语音消息 (voice-message) | 实时通话 (realtime-call) |
|------|------------------------|------------------------|
| 交互模式 | 异步：录→发→存→下载→播 | 同步：双向实时流 |
| 时延 | 秒~分钟级 | < 200ms |
| 离线支持 | 支持（下载后播放） | 不支持（必须双方在线） |
| 存储 | 音频文件持久化 (OSS) | 无存储（可选录制） |
| domain | chat | rtc（新建） |
| 服务 | chat-service | rtc-service（新建） |
| 端侧模块 | lib/ui/chat/ (消息气泡) | lib/ui/rtc/（独立模块） |

两者共存，互不替代。

### 1.2 业界对标

| 能力 | FaceTime | 微信 | Teams | 趣聊目标 |
|------|----------|------|-------|---------|
| 媒体架构 | SFU | SFU + 自研 WAVE | SFU | SFU (LiveKit 自部署) |
| 1v1 策略 | P2P 优先 | P2P→SFU | SFU | SFU 统一（Phase 2 可加 P2P） |
| 多人上限 | **32 人** | 9 人 | 1000 人 | **32 人（对标 FaceTime）** |
| 编解码 | H.264/HEVC | 自研+H.264 | H.264/VP9 | H.264/VP8/VP9 (Simulcast) |
| E2EE | Insertable Streams | 无 | 有 | **Phase 4** |
| 弱网对抗 | SVC+FEC | 服务端QoS | Simulcast | **Simulcast+NACK+PLI+FEC** |
| 录制 | 无 | 无 | 云录制 | **支持（LiveKit Egress）** |
| 屏幕共享 | 有 | 有 | 有 | **支持** |
| 来电唤醒 | 系统原生 | CallKit | Push | **CallKit / Android FullScreen** |
| 网格布局 | 动态网格 | 固定网格 | Gallery+Speaker | **动态网格+演讲者双视图** |
| 画中画 | 有 | 有 | 有 | **支持** |

## 2. 目标用户

- 趣聊 1v1 聊天用户（日活主体）
- 群聊参与者（≤32 人多人通话）
- 圈子成员（发起圈子通话）

## 3. 功能范围

### 3.1 In-Scope（分 4 Phase 交付）

| 编号 | 功能 | Phase | 说明 |
|------|------|-------|------|
| F1 | 1v1 语音通话 | P1 | 发起→呼叫→接听→通话→挂断完整生命周期 |
| F2 | 1v1 视频通话 | P1 | 同上 + 视频流 + 前后摄像头切换 |
| F3 | 来电推送 | P1 | 在线 WS 推送 + 离线 VoIP Push (CallKit/Android) |
| F4 | 通话控制 | P1 | 静音/关摄像头/翻转/扬声器/挂断 |
| F5 | 通话记录消息 | P1 | 通话结束→chat 会话插入系统消息 "[语音通话 03:42]" |
| F6 | 多人语音通话 | P2 | 2~32 人，中途邀请/加入/离开 |
| F7 | 多人视频通话 | P2 | 动态网格视图 (Grid) + 演讲者视图 (Speaker) 双模切换 |
| F8 | 参与者管理 | P2 | 参与者列表、状态显示、中途邀请更多人 |
| F9 | 群聊/圈子入口 | P2 | 从群聊详情页/圈子页发起多人通话 |
| F10 | 画中画 (PiP) | P3 | App 内 PiP 浮窗 + 系统级 PiP |
| F11 | 顶部通话条 | P3 | 返回其他页面时顶部蓝色通话条，视觉主色与趣聊品牌蓝统一 |
| F12 | 弱网自适应 | P3 | Simulcast 动态降质 + 网络质量指示 |
| F13 | 音频路由 | P3 | 扬声器/听筒/蓝牙自动检测与切换 |
| F14 | 通话录制 | P4 | 服务端录制 (LiveKit Egress)，存储到 OSS |
| F15 | 屏幕共享 | P4 | 发起者共享屏幕，其他参与者观看 |
| F16 | E2EE | P4 | Insertable Streams 端到端加密 |
| F17 | AI 降噪 | P4 | RNNoise 实时降噪 |
| F18 | 关系门禁与主页入口 | P2 | 1v1 通话仅对同好开放；密友仅作为同好子态展示快捷语义，主页按五态关系展示不同动作 |
| F19 | 会话更多功能入口重构 | P2 | 通话入口从 ChatDetail AppBar 下沉到输入区 `+` 面板 |
| F20 | 多人选人规则 | P2 | 群聊发起多人通话时，默认来源为当前会话；`<=8 人默认全选，>8 人默认不选`，并可切换同好/其他群选人 |
| F21 | 通话中加人与链接入会 | P2 | 通话中支持主动邀请当前会话成员、同好或其他群成员，并支持分享呼叫链接加入 |
| F22 | 群邀请响铃模式 | P2 | 群语音/视频邀请统一为响铃邀请，不提供静默邀请或仅消息通知模式 |
| F23 | 发起方呼叫铃声 | P2 | 来电铃声支持趣聊官方铃声库；若发起方配置专属呼叫铃声，则优先替换默认铃声，群聊固定以原始发起方为铃声来源 |

### 3.2 Out-of-Scope

- PSTN 电话拨入/拨出
- 虚拟背景（Phase 5+）
- 直播推流 (RTMP Egress)
- 通话中实时字幕/翻译
- Web 端通话
- 超过 32 人的大型会议
- 打招呼请求箱本身的对象建模（由 `contact-and-session-governance` 承担）
- 举报群能力

## 4. 业务对象模型

### 4.1 CallSession 聚合根（新建）

| 字段 | 类型 | 说明 |
|------|------|------|
| callId | string (ULID) | 通话唯一标识 |
| type | enum: voice/video | 通话类型 |
| status | enum | INITIATED→RINGING→CONNECTING→IN_CALL→ENDED |
| initiatorId | string | 发起者 userId |
| roomId | string | LiveKit Room ID |
| maxParticipants | int | 上限 32 |
| participants[] | embedded | 参与者数组 |
| endReason | enum | NORMAL/CANCELLED/REJECTED/TIMEOUT/ERROR/NO_ANSWER |
| duration | int | 通话时长（秒） |
| recording | object? | 录制信息 {enabled, egressId, url} |
| screenSharing | object? | 屏幕共享 {userId, startedAt} |
| sourceConversationId | string? | 来源聊天会话 ID |
| sourceCircleId | string? | 来源圈子 ID |
| createdAt | datetime | 创建时间 |
| endedAt | datetime? | 结束时间 |

### 4.2 CallParticipant 值对象（新建）

| 字段 | 类型 | 说明 |
|------|------|------|
| userId | string | 用户 ID |
| role | enum: initiator/invitee | 角色 |
| status | enum | INVITED→RINGING→CONNECTED→LEFT→REJECTED→TIMEOUT |
| joinedAt | datetime? | 加入时间 |
| leftAt | datetime? | 离开时间 |
| media | object | {audioEnabled, videoEnabled, screenSharing} |

### 4.3 领域事件

| 事件 | 触发 | 消费方 |
|------|------|--------|
| call.initiated | 发起通话 | realtime-gateway（来电推送） |
| call.answered | 接听 | rtc-service（房间 Token） |
| call.rejected | 拒绝 | rtc-service（通知发起方） |
| call.ended | 通话结束 | chat-service（插入通话记录消息） |
| call.participant_joined | 新人加入 | rtc-service（更新房间） |
| call.participant_left | 离开 | rtc-service（检查是否结束通话） |
| call.recording_started | 开始录制 | 通知参与者 |
| call.screen_share_started | 开始屏幕共享 | 端侧（切换布局） |

### 4.4 API 端点

| 操作 | 方法 | 路径 |
|------|------|------|
| InitiateCall | POST | /v1/rtc/calls |
| GetCall | GET | /v1/rtc/calls/{callId} |
| AnswerCall | POST | /v1/rtc/calls/{callId}/answer |
| RejectCall | POST | /v1/rtc/calls/{callId}/reject |
| HangupCall | POST | /v1/rtc/calls/{callId}/hangup |
| JoinCall | POST | /v1/rtc/calls/{callId}/join |
| LeaveCall | POST | /v1/rtc/calls/{callId}/leave |
| InviteToCall | POST | /v1/rtc/calls/{callId}/invite |
| GetRtcToken | GET | /v1/rtc/calls/{callId}/token |
| StartRecording | POST | /v1/rtc/calls/{callId}/recording |
| StopRecording | DELETE | /v1/rtc/calls/{callId}/recording |
| StartScreenShare | POST | /v1/rtc/calls/{callId}/screen-share |
| StopScreenShare | DELETE | /v1/rtc/calls/{callId}/screen-share |
| ListCallHistory | GET | /v1/rtc/calls |
| **WS 信令** | — | /v1/rtc/signal |

### 4.5 技术架构选型：LiveKit 自部署

LiveKit 是 Apache 2.0 开源的 Go 语言 SFU 引擎（基于 Pion WebRTC），定位为**自部署的媒体基础设施**，类比 PostgreSQL 之于存储——我们选用它不是外部服务依赖，而是基础设施选型。

- 完全自部署，数据留在自有机房
- 开源可 fork，可针对趣聊定制
- 内置 Simulcast、录制 (Egress)、屏幕共享、E2EE
- 官方 Flutter SDK (`livekit_client`)
- 分布式 Redis 路由（水平扩展）
- 基准测试：单节点支持 3000+ 人

呼叫管理（rtc-service）、信令协议、端侧 UI、业务流程 100% 自建。

## 5. 入口体系

| 入口 | 位置 | 行为 | Phase |
|------|------|------|-------|
| ① 用户主页（同好/密友） | 用户资料页操作栏 | `消息 / 视频 / 语音` 三按钮等宽展示 | P2 |
| ② 1v1 会话输入区 `+` | ChatDetailPage 输入区更多功能 | 仅同好会话显示 `语音通话 / 视频通话` | P2 |
| ③ 群聊会话输入区 `+` | ChatDetailPage(group) 输入区更多功能 | 发起语音/视频通话并进入成员选择页，默认从当前会话成员起选，可切换同好/其他群 | P2 |
| ④ 通话中邀请 | Voice/VideoCallPage 顶部或控制栏固定入口 | 主动邀请当前会话成员、同好或其他群成员加入当前通话 | P2 |
| ⑤ 通话中分享链接 | Voice/VideoCallPage 邀请二级面板 | 复制/分享呼叫链接，对方点击入会 | P2 |
| ⑥ 圈子详情 | CircleDetailPage 操作栏 | 发起圈子通话，选择成员 | P2 |
| ⑦ 来电推送（被叫） | 系统级 | iOS CallKit / Android FullScreen Intent；群邀请统一为响铃邀请 | P1 |
| ⑧ 通话记录 | ChatPage Tab 或历史 | 查看通话记录，点击回拨 | P3 |

### 5.1 入口门禁规则

- ChatDetail AppBar 保持简洁，不承载语音/视频直达按钮。
- 1v1 语音/视频入口仅在 `同好` 关系下显示；`密友` 仅作为 `同好` 的快捷语义子态，不额外放宽门禁。
- `关注用户` 只能先打招呼，不能直接发起语音/视频通话。
- 打招呼未被回复前，不进入普通聊天列表，因此也不存在会话内通话入口。
- 对方回复后建立正式会话，但若尚未升级为同好，仍不显示语音/视频入口。
- 群聊发起多人通话时：
  - `<= 8 人`：默认全选（除自己）
  - `> 8 人`：默认不选，由用户主动选择
- 多人选人页固定提供三类来源：`当前会话`、`同好`、`其他群`。
- 跨群拉人不要求先加入当前群，只要求被邀请人加入本次通话。
- 群语音/视频邀请统一为响铃邀请，不提供静默邀请或仅消息通知模式。

## 6. 约束

### 6.1 技术约束

- metadata 变更必须走 `metadata → verify → codegen` 流程
- rtc-service 遵从 DDD 四层结构 + runtime 统一约束
- 端侧 UI 在 `lib/ui/rtc/` 下，禁止 `lib/features/`
- 端侧必须使用 `AppTypography`/`AppSpacing`/`AppColors`，禁止硬编码视觉字面量
- 端侧通过 `rtcRepositoryProvider` 访问 Repository，禁止直接实例化
- Remote 实现使用 `CloudRuntimeConfig.gatewayBaseUrl` + `CloudRequestHeaders`
- 错误码由 `errors.yaml` 驱动，云侧无硬编码 user_message，端侧无硬编码 code
- rtc-service / livekit-sfu / coturn 三者必须独立部署
- LiveKit Room Token 有效期 ≤ 24h，支持 refresh
- 通话与来电视觉主色统一使用趣聊品牌蓝，不复用微信式绿色语义

### 6.2 业务约束

- 多人通话上限 32 人（对标 FaceTime），超出拒绝加入并返回错误码
- 通话超时 30s 无应答 → 自动结束
- 同一用户同时只能参与 1 个通话
- 录制需全体参与者知情（UI 提示 + 录制图标）
- 屏幕共享同时只允许 1 人
- 1v1 实时通话仅对 `同好` 开放；`关注用户` 不解锁实时通话
- `同好 = 互关`，失去互关后应即时收回 1v1 通话入口
- `密友 ⊂ 同好`，失去同好后自动失去密友带来的通话快捷语义
- 正式会话建立并不等同于可实时通话；未升级为同好时仍仅允许异步消息
- 通话中添加人需同时支持两条链路：
  - 主动邀请当前会话成员、同好或其他群成员
  - 生成并分享呼叫链接入会
- 被邀请人加入当前通话不要求先加入当前群；群成员关系与通话参与关系解耦
- 群邀请只有响铃邀请一种模式，发起后前台/后台/锁屏均按来电处理
- 来电铃声仅支持趣聊官方铃声库，不支持用户上传、本地导入或第三方音频 URL
- 若发起方配置专属呼叫铃声，则 1v1 与群邀请均优先使用发起方铃声；未配置时回退趣聊默认铃声
- 群邀请铃声始终归属原始发起方（initiator），不随后续邀请链变化
- 群聊设置页不承担“举报群”“拉黑群聊”能力；群内治理动作下沉到成员与消息对象

### 6.3 弱网体验约束

#### 弱网对抗机制

| 机制 | 说明 | 触发条件 |
|------|------|---------|
| Simulcast 三层 | 720p / 360p / 180p 三层编码，SFU 按接收方带宽选择 | 始终开启 |
| 动态降质 | 高→中→低→仅音频 | 丢包率 > 5% 或 RTT > 300ms |
| NACK+PLI | 丢包重传 + 关键帧请求 | 检测到丢包 |
| FEC | 前向纠错（冗余包） | 丢包率 > 2% 时自动启用 |
| Jitter Buffer | 自适应抖动缓冲 50~200ms | 始终开启 |
| 音频优先 | 带宽不足时优先保障音频 | 带宽 < 100kbps |

#### 弱网场景 × 用户体验

| 场景 | 网络条件 | 视频策略 | 音频策略 | UI 表现 |
|------|---------|---------|---------|---------|
| 强网 | ≥ 2Mbps, RTT < 50ms | 720p 满帧 | 高质量 | 无指示 |
| 一般 | 500k~2M, RTT 50~150ms | 360p | 正常 | 🟡 黄色指示 |
| 弱网 | 100k~500k, RTT 150~300ms | 180p 低帧率 | 正常 | 🟠 橙色指示 |
| 极弱 | < 100kbps, RTT > 300ms | 关闭视频 | 保持通话 | 🔴 红色 + "网络不佳" |
| 断网 | 0 | 冻结画面 | 静音 | "连接中断，正在重连..." |
| 恢复 | 断网→恢复 | ICE restart | 自动恢复 | 自动重连，< 5s |

#### 弱网量化指标

| 指标 | 要求 | 验证方式 |
|------|------|---------|
| 弱网通话保持率 | 100kbps 下音频通话不断 ≥ 60s | T3 弱网模拟 |
| 自动降质时延 | 检测到丢包 → 切换质量 ≤ 2s | T3 SFU 日志 |
| ICE 重连成功率 | 断网 10s 内恢复 → 重连成功 ≥ 95% | T4 灰度监控 |
| 音频优先保障 | 极弱网下音频 MOS ≥ 3.0 | T3 质量评估 |

### 6.4 并发性能约束

#### 云侧性能

| 指标 | 要求 | 说明 |
|------|------|------|
| InitiateCall TPS | ≥ 500/s | 含房间创建 + Token 签发 |
| AnswerCall TPS | ≥ 500/s | 含 Token 签发 |
| 信令 WS 并发连接 | ≥ 10K/node | SDP/ICE 交换通道 |
| 信令消息吞吐 | ≥ 50K msg/s/node | 含心跳 |
| SFU 单节点并发房间 | ≥ 100 (32人/房) | LiveKit 基准 3000 人/节点 |
| SFU 32 人房间带宽 | ~96 Mbps (上行) | 32人×3层 Simulcast |
| 呼叫状态查询 p99 | < 20ms | Redis 缓存 |
| 通话记录写入 p99 | < 50ms | MongoDB |

#### 端侧性能

| 指标 | 要求 | 说明 |
|------|------|------|
| 通话建立时间（强网） | ≤ 3s | 发起到双方通话 |
| 通话建立时间（一般网） | ≤ 5s | |
| 来电推送到达（在线） | ≤ 1s | WS 通道 |
| 来电推送到达（离线） | ≤ 5s | VoIP Push |
| 视频渲染帧率 | ≥ 24fps (1v1), ≥ 15fps (32人) | |
| 音视频端到端延迟 | ≤ 200ms (p95) | ICE + SFU 转发 |
| CPU 占用（1v1 视频） | ≤ 30% | 中端设备 |
| CPU 占用（32人视频） | ≤ 70% | 中端设备 |
| 内存占用增量 | ≤ 200MB (32人视频) | |
| 电池消耗 | ≤ 15%/小时 (视频) | |
| 通话页 FPS | ≥ 60fps | 控制栏/动效流畅 |

#### 实时性约束

| 指标 | 1v1 | 多人(32) | 验证方式 |
|------|-----|---------|---------|
| 音频端到端延迟 p95 | ≤ 150ms | ≤ 200ms | T4 灰度实测 |
| 视频端到端延迟 p95 | ≤ 200ms | ≤ 350ms | T4 灰度实测 |
| 信令延迟（发起→来电通知） | ≤ 1s | ≤ 2s | T3 端云集成 |
| ICE 建连时间 p95 | ≤ 2s | ≤ 3s | T3 |
| 通话状态同步延迟 | ≤ 500ms | ≤ 1s | T3 |
| 参与者加入可见延迟 | — | ≤ 2s | T4 |

### 6.5 部署约束

#### 部署拓扑

```yaml
environments:
  dev:
    rtc-service:
      domains: [rtc]
    livekit-sfu:
      domains: [media]
    coturn:
      domains: [turn]
  integration:
    seed-box:
      domains: [content, integration, chat, user, circle,
                assistant, gateway, orchestrator]
    rtc-service:
      domains: [rtc]
    livekit-sfu:
      domains: [media]
    coturn:
      domains: [turn]
  prod:
    rtc-service:
      domains: [rtc]
    livekit-sfu:
      domains: [media]
    coturn:
      domains: [turn]
```

rtc-service / livekit-sfu / coturn 在所有环境独立部署。

#### 灰度发布策略

| 阶段 | 环境 | 策略 | 验证 | 回滚条件 |
|------|------|------|------|---------|
| G5a | dev | 全量 | 契约测试 + 手动验证 | git revert |
| G5b | integration | 全量 | L1~L3 全量 + L4 Patrol | 回滚镜像 |
| G5c | prod 5% | 按 userId hash | 监控 7 项指标 | 自动回滚 |
| G5d | prod 20% | 扩大 hash | 同上 + 7天稳定性 | 自动回滚 |
| G5e | prod 50% | 扩大 hash | 同上 + 成本核算 | 自动回滚 |
| G5f | prod 100% | 全量 | 持续监控 | — |

**灰度自动回滚门禁**：

| 指标 | 阈值 | 触发 |
|------|------|------|
| 通话建立成功率 | < 98% | 自动回滚 |
| 音视频端到端延迟 p95 | > 400ms | 告警，> 600ms 回滚 |
| 通话中断率（非主动挂断） | > 2% | 自动回滚 |
| 端侧崩溃率 | > 0.1% | 自动回滚 |
| SFU 节点 CPU | > 85% | 自动扩容，> 95% 回滚 |

#### 容量规划

| 场景 | DAU | 并发通话 | SFU 节点 | TURN 带宽 |
|------|-----|---------|---------|----------|
| 初期 | 10K | ~100 | 1 (8C16G) | 1 Gbps |
| 中期 | 100K | ~1000 | 4 (8C16G) | 10 Gbps |
| 远期 | 1M | ~10K | 16 (16C32G) | 40 Gbps |

## 7. 适用范围与约束

### 7.1 适用场景

- 趣聊 1v1 私聊/群聊/圈子中的实时语音/视频通话
- 2~32 人多人通话（对标 FaceTime）
- iOS 15+ / Android API 26+
- 录制与屏幕共享

### 7.2 不适用场景

- 超过 32 人的大型会议
- PSTN 电话互通
- Web 端通话
- 直播推流
- 实时字幕/翻译

### 7.3 前置条件

- **realtime-gateway WebSocket 基础能力就绪**（信令推送通道，独立评估为前置依赖）
- **user-service 在线状态可查询**（推送策略判断）
- **LiveKit SFU + coturn 部署就绪**（媒体基础设施）

### 7.4 realtime-gateway 前置评估

realtime-gateway 是本特性的关键前置依赖。推荐路径：先实现 realtime-gateway 核心能力（G1~G4），再建 rtc-service。
- 信令通道复用：来电推送、通话状态同步均通过 realtime-gateway WS 投递
- 在线感知复用：判断 WS 在线推送还是 VoIP Push 离线唤醒
- 若 realtime-gateway 无法先行，rtc-service 可内建临时 WS 信令，后续迁移

## 8. 对标输入与吸收结论

| 对标 | 借鉴点 | 不借鉴点 | 适用边界 |
|------|--------|---------|---------|
| **FaceTime** | 动态网格布局、发言人白色高亮、PiP、32人上限、P2P→SFU 平滑升级 | 封闭生态绑定 | 1v1~32人社交通话 |
| **微信 WAVE** | 服务端 QoS 反馈环、渐进式质量调控、极致弱网优化 | 私有编解码器（投入过大） | 弱网对抗策略、运营指标体系 |
| **Teams** | Simulcast 智能流选择（仅转发可见窗口）、Gallery/Speaker 双视图 | 千人规模架构 | SFU 路由策略、视图切换 |
| **LiveKit** | Go 原生 SFU、Redis 分布式路由、Flutter SDK、Egress 录制、E2EE | 全托管商业模式 | 自建技术栈基座 |

## 9. 验收重点

### T1 契约与静态层

- DTO 契约：CallSession / CallParticipant / RtcToken 全字段解析
- 错误码契约：RtcErrorCode round-trip + fromCode + httpStatus
- Repository 契约：14 方法 Mock 与 Abstract 一致
- metadata 一致性：fields.yaml → codegen → Go/Dart 零偏差

### T2 模块与交互层

- 通话 UI：OutgoingCall / IncomingCall / VoiceCall / VideoCall 四页面
- 控制栏：静音/关摄像头/翻转/邀请/扬声器/挂断 六按钮
- 网格布局：2~32 人动态自适应（7 种网格配置）
- 演讲者视图：大画面+底部缩略行+发言人高亮
- 参与者管理面板：状态显示+中途邀请
- CallKit/Android 来电 UI

### T3 端云集成层

- 通话生命周期：Initiate/Answer/Reject/Hangup/Timeout 全状态机
- 多人房间：Join/Leave/Invite + 32 人上限
- 事件发布：8 个领域事件 → chat-service 通话记录
- 录制：Egress 启动 + OSS 存储
- 屏幕共享：端到端流传输
- 基准性能：500 并发 p99、32 人房间 SFU 负载
- 弱网：100kbps 音频保持、ICE 重连

### T4 端到端旅程层

- 完整旅程：1v1 语音/视频、多人加入/离开、来电接听/拒绝/超时
- PiP + 蓝色通话条
- 屏幕共享旅程
- 灰度 prod 5%→20%→50%→100% 无回滚
- 延迟/中断率/建连率灰度实测

详细 43 条验收标准见 `acceptance.yaml`。

## 10. 子特性结构

| L3 子特性 | 职责 | L4 Story |
|-----------|------|----------|
| one-to-one-call | 1v1 语音/视频通话端到端 | call-lifecycle-contract |
| group-call | 2~32 人多人通话 | multi-party-room-contract |
| call-experience | 通话中 UI/UX 体验 | call-ui-interaction |
| media-infrastructure | SFU/TURN/录制基础设施 | sfu-deployment-contract |

## 11. 跨特性依赖

| 依赖 | 特性节点 | 状态 | 关系 |
|------|---------|------|------|
| realtime-gateway | gateway-orchestrator-foundation/realtime-gateway | specified | 前置：信令推送通道 |
| chat-service | chat-conversation/list-detail-message-delivery | specified | 集成：通话记录消息 |
| contact-and-session-governance | chat-conversation/contact-and-session-governance | specified | 前置：1v1 通话关系门禁、打招呼与正式会话边界 |
| circle-community | circle-community | specified | 集成：圈子通话入口 |
| user-service | user-identity-profile-relationship | specified | 查询：在线状态+联系人 |
| notification-service | — | 已有 | 集成：VoIP Push |
