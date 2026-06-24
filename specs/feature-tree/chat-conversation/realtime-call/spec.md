# L2 规格：realtime-call — 实时音视频通话

> **层级**：L2_business_capability（隶属 L1 `chat-conversation`）
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
| F18 | 关系门禁与主页入口 | P2 | 1v1 通话仅对 `mutual + !blocked` 开放；主页按关注状态与拉黑门禁展示不同动作 |
| F19 | 会话更多功能入口重构 | P2 | 通话入口从 ChatDetail AppBar 下沉到输入区 `+` 面板 |
| F20 | 多人选人规则 | P2 | 群聊发起多人通话时，默认来源为当前会话；`<=8 人默认全选，>8 人默认不选`，并可切换互相关注/其他群选人 |
| F21 | 通话中加人与链接入会 | P2 | 通话中支持主动邀请当前会话成员、互相关注或其他群成员，并支持分享呼叫链接加入 |
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
| ① 用户主页（互相关注且未拉黑） | 用户资料页操作栏 | `消息 / 视频 / 语音` 三按钮等宽展示 | P2 |
| ② 1v1 会话输入区 `+` | ChatDetailPage 输入区更多功能 | 仅 `mutual + !blocked` 会话显示 `语音通话 / 视频通话` | P2 |
| ③ 群聊会话输入区 `+` | ChatDetailPage(group) 输入区更多功能 | 发起语音/视频通话并进入成员选择页，默认从当前会话成员起选，可切换互相关注用户/其他群 | P2 |
| ④ 通话中邀请 | Voice/VideoCallPage 顶部或控制栏固定入口 | 主动邀请当前会话成员、互相关注用户或其他群成员加入当前通话 | P2 |
| ⑤ 通话中分享链接 | Voice/VideoCallPage 邀请二级面板 | 复制/分享呼叫链接，对方点击入会 | P2 |
| ⑥ 圈子详情 | CircleDetailPage 操作栏 | 发起圈子通话，选择成员 | P2 |
| ⑦ 来电推送（被叫） | 系统级 | iOS CallKit / Android FullScreen Intent；群邀请统一为响铃邀请 | P1 |
| ⑧ 通话记录 | ChatPage Tab 或记录 | 查看通话记录，点击回拨 | P3 |

### 5.1 入口门禁规则

- ChatDetail AppBar 保持简洁，不承载语音/视频直达按钮。
- 1v1 语音/视频入口仅在 `mutual + !blocked` 状态下显示；`mutual` 只是互相关注的派生状态，不命名为新的关系等级。
- `关注用户` 只能先打招呼，不能直接发起语音/视频通话。
- 打招呼未被回复前，不进入普通聊天列表，因此也不存在会话内通话入口。
- 对方回复后建立正式会话，但若尚未互相关注，仍不显示语音/视频入口。
- 群聊发起多人通话时：
  - `<= 8 人`：默认全选（除自己）
  - `> 8 人`：默认不选，由用户主动选择
- 多人选人页固定提供三类来源：`当前会话`、`互相关注`、`其他群`。
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
- 1v1 实时通话仅对 `mutual + !blocked` 开放；单向关注不解锁实时通话
- `mutual` 仅表示互相关注状态，失去互相关注或任一方向拉黑后应即时收回 1v1 通话入口
- 正式会话建立并不等同于可实时通话；未互相关注时仍仅允许异步消息
- 通话中添加人需同时支持两条链路：
  - 主动邀请当前会话成员、互相关注用户或其他群成员
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
| 弱网通话保持率 | 100kbps 下音频通话不断 ≥ 60s | api_integration 弱网模拟 |
| 自动降质时延 | 检测到丢包 → 切换质量 ≤ 2s | api_integration SFU 日志 |
| ICE 重连成功率 | 断网 10s 内恢复 → 重连成功 ≥ 95% | user_acceptance 灰度监控 |
| 音频优先保障 | 极弱网下音频 MOS ≥ 3.0 | api_integration 质量评估 |

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
| 音频端到端延迟 p95 | ≤ 150ms | ≤ 200ms | user_acceptance 灰度实测 |
| 视频端到端延迟 p95 | ≤ 200ms | ≤ 350ms | user_acceptance 灰度实测 |
| 信令延迟（发起→来电通知） | ≤ 1s | ≤ 2s | api_integration 端云集成 |
| ICE 建连时间 p95 | ≤ 2s | ≤ 3s | api_integration |
| 通话状态同步延迟 | ≤ 500ms | ≤ 1s | api_integration |
| 参与者加入可见延迟 | — | ≤ 2s | user_acceptance |

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
| G5b | integration | 全量 | `local_contract/api_integration` 全量 + `user_acceptance` Patrol | 回滚镜像 |
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
- 直播推流
- 实时字幕/翻译

> 修订（商用上线基线）：Web 端从“不适用”调整为“适用但能力降级”。Web 支持站内前台来电、Web Push 后台唤醒（PWA 安装到主屏后）、加入既有通话；不提供系统原生来电界面。详见 §12 商用上线 UX 基线与 §13 来电平台能力矩阵。鸿蒙按 `14-cross-platform-portability` 走能力位降级，不阻塞本轮主路径。

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

### local_contract 契约与静态层

- DTO 契约：CallSession / CallParticipant / RtcToken 全字段解析
- 错误码契约：RtcErrorCode round-trip + fromCode + httpStatus
- Repository 契约：14 方法 Mock 与 Abstract 一致
- metadata 一致性：fields.yaml → codegen → Go/Dart 零偏差

### local_contract 模块与交互层

- 通话 UI：OutgoingCall / IncomingCall / VoiceCall / VideoCall 四页面
- 控制栏：静音/关摄像头/翻转/邀请/扬声器/挂断 六按钮
- 网格布局：2~32 人动态自适应（7 种网格配置）
- 演讲者视图：大画面+底部缩略行+发言人高亮
- 参与者管理面板：状态显示+中途邀请
- CallKit/Android 来电 UI

### api_integration 端云集成层

- 通话生命周期：Initiate/Answer/Reject/Hangup/Timeout 全状态机
- 多人房间：Join/Leave/Invite + 32 人上限
- 事件发布：8 个领域事件 → chat-service 通话记录
- 录制：Egress 启动 + OSS 存储
- 屏幕共享：端到端流传输
- 基准性能：500 并发 p99、32 人房间 SFU 负载
- 弱网：100kbps 音频保持、ICE 重连

### user_acceptance 端到端旅程层

- 完整旅程：1v1 语音/视频、多人加入/离开、来电接听/拒绝/超时
- PiP + 蓝色通话条
- 屏幕共享旅程
- 灰度 prod 5%→20%→50%→100% 无回滚
- 延迟/中断率/建连率灰度实测

详细可执行验收项见 `acceptance.yaml`（按 SIT/GWT/contract + 三层测试 结构组织，不再以“固定 N 条”计数描述，避免与实际条目漂移）。

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

## 12. 商用上线 UX 基线（对标微信/小红书/FaceTime）

> 本章是“商用可上线”的强制 UX 验收基线，覆盖入口清晰度、过程态完整性、错误/权限提示语、可靠性。每条都映射到 `acceptance.yaml` 的 GWT/contract，并落到 三层测试 证据。

### 12.1 入口清晰度（可解释、不分叉）

| 入口 | 展示规则 | 看不到入口时的解释 |
|------|---------|-------------------|
| 1v1 会话输入区 `+` | 仅 `mutual + !blocked` 显示语音/视频 | 非互相关注显示“互相关注后可发起语音和视频通话”教育卡（结构化文案，非硬编码） |
| 群聊输入区 `+` | 进入成员选择页，`<=8` 默认全选，`>8` 默认空选 | 群已满/无可邀请成员时显示空态说明 |
| 用户主页操作栏 | 互相关注显示 `消息/语音/视频` 三动作等宽 | 关注/陌生只显示打招呼或关注，不显示通话入口 |
| 通话中邀请 | 控制栏固定“邀请”，二级面板选当前会话/互相关注/其他群 | 房间满显示“通话人数已达上限” |
| 分享链接入会 | 链接含来源、过期、风险提示与加入确认页 | 链接过期/无效显示结构化错误 |

入口门禁只读 `relationship-capability` 能力位（`canStartVoiceCall`/`canStartVideoCall`），UI 禁止自写关系判断。

### 12.2 通话页过程态（FaceTime/微信级）

通话页必须覆盖全部过程态，禁止只有“占位头像”：

| 状态 | 触发 | UI 表现 |
|------|------|---------|
| 连接中 | 发起/接听后媒体未建连 | “正在连接…” + 骨架/呼吸态 |
| 振铃中（呼出） | 对方未接 | 对方头像脉冲 + “等待接听” + 取消按钮 |
| 单人等待 | 多人房仅自己 | “等待其他人加入” + 邀请入口前置 |
| 通话中 | 媒体已建连 | 动态网格/演讲者视图 + 真实视频流 |
| 对方未接 | 30s 超时 | “对方未接听” → 自动收尾 |
| 已离开 | 某成员离开 | 该格淡出 + “xx 已离开”轻提示 |
| 重连中 | 网络抖动 | 顶部“连接中断，正在重连…”，画面冻结而非黑屏 |
| 弱网 | 质量下降 | 黄/橙/红质量指示 + 必要时降级到音频 |
| 已结束 | 挂断/最后一人离开 | 收尾动画 → 退出或回到会话并插入通话记录 |

布局：顶部显示来源（来自哪个会话/群）、时长、网络质量、录制/共享提示与信任摘要；中部 1/2/3-4/5-9/10-16/17-25/26-32 动态网格 + 演讲者视图；底部控制栏固定 静音/摄像头/翻转/邀请/音频输出/挂断，按钮必须真实生效（翻转调用 SFU `switchCamera`，音频输出调用 `setSpeakerOn`）。

### 12.3 完整交互路径（无遗漏）

发起→呼出（可取消）→对方振铃（可接听/拒绝/超时）→建连→通话→（加人/静音/翻转/共享/录制）→（返回 PiP/顶部通话条回流）→离开/挂断→收尾。多人“离开”只让自己退出，最后一人离开才结束房间；忙线（已在通话中又来电）必须提示“正在通话中”，不静默吞掉。

### 12.4 错误/权限提示语（统一语义、不吓人）

- 全部走 `error-permission-display-semantics`：阻塞性用内联卡片+重试，次要失败用轻量反馈；禁止裸异常字符串（如 `answerCall: empty session`）与硬编码中文/`REC`。
- 错误码来自 `errors.yaml` → codegen；端侧用 `RtcErrorCode.fromCode(...).toDisplayMessage(l10n)`。
- 权限（麦克风、摄像头、通知、全屏来电、Web 通知）统一权限卡片：图标+主文案+副文案+主操作（去设置/重试），永久拒绝显示“去设置”，并给降级路径（如“可先转为仅语音”）。

### 12.5 可靠性

- LiveKit 远端 participants/tracks 必须实时同步到 `callParticipantsProvider`，视频格渲染真实 `VideoTrack`。
- WS 事件 type 端云统一使用 `client_ws_type`（如 `call.ringing`），由 codegen 生成映射，禁止把 Go domain 常量直接当 wire type。
- `IncomingCallCoordinator`/`ActiveCallBar`/`PipCallOverlay` 必须挂载到 app shell 唯一入口。

## 13. 来电平台能力矩阵（重点）

“能把人叫起来”依赖系统能力，三端实现不同，分别定义并各自验收。业务层只读 `PlatformCapabilities`（`incomingCallUi`/`webPushIncomingCall`/`realtimeCommunication`），禁止裸 `Platform.is*`/`kIsWeb`（遵 `14-cross-platform-portability`）。

| 平台 | 前台 | 后台/锁屏/退出 | 关键权限与限制 | 降级 |
|------|------|----------------|----------------|------|
| iOS | 应用内全屏来电页（实时信令） | APNs VoIP Push（PushKit）唤醒，回调内必须立即 `CallKit.reportNewIncomingCall`，否则系统终止 App/停投 VoIP Push | `UIBackgroundModes: voip,audio`、麦克风/摄像头用途描述；接听后再请求媒体权限 | 无 CallKit 能力时退化为普通通知（User Notifications） |
| Android | 应用内全屏来电页 | FCM 高优先级消息 + 高优先级通知通道 + `USE_FULL_SCREEN_INTENT` 全屏意图来电页 | Android 14+ 全屏意图为特殊权限，需声明通话核心功能；`POST_NOTIFICATIONS` 通知权限 | 全屏意图不可用时降级 heads-up 通知，并提供设置引导 |
| Web | 站内来电弹窗 + 标题闪烁 + 铃声，不弹原生来电界面 | Web Push + Service Worker + Notification，点击通知打开/聚焦通话页再建 WebRTC | 必须 HTTPS；iOS Safari 需 PWA 安装到主屏后才有 Web Push；权限请求必须用户手势触发 | 未安装 PWA 时提示“添加到主屏幕后可接收网页来电”或 App 下载引导 |

权限提示口径：不在冷启动索权；首次进入聊天/通话设置时引导“开启通话提醒，锁屏/后台也能收到来电”；接听后再请求麦克风/摄像头，被拒走权限卡片并提供仅语音降级；OEM 后台限制导致漏接时弱提示，不强行引导关省电。

## 14. 信任与隐私提示（基础两态）

避免多人视频通话的隐私风险，本轮先做两态，字段进 metadata（富信息预留）：

| 信任态 | 适用对象 | UI |
|--------|---------|----|
| 认识/可信 | 联系人、互相关注、当前会话/群成员 | 展示来源标签（如“来自当前群聊”），正常入会 |
| 可能不认识 | 其他群成员、链接加入者、无共同关系者 | 进入前风险提示“你可能不认识 TA，注意保护隐私，避免展示敏感信息” |
| 异常（不入会） | 被拉黑、房间已满、已结束、非授权链接 | 结构化错误（errors.yaml 驱动），拒绝入会 |

- 通话中有“可能不认识”的新人加入时，在会成员收到可感知轻量横幅。
- 被邀请人来电页必须展示：发起人、来源会话/群、当前在会人数、是否包含“可能不认识”的人、摄像头/麦克风默认状态。
- 富信息（共同关注数量、共同群列表）字段在 metadata 预留，本轮 UI 不强制展示。

## 15. 商用上线验证与交付（测试路径 + 门禁 + UAT 剧本）

验收以 `acceptance.yaml`（L2 SIT + 四个 L3 Story GWT）为唯一计数真相源；本节给出测试路径与门禁命令落点。

### 15.1 分层测试与计划文件

- local_contract（契约/静态）：
  - `quwoquan_service` `go run ./tools/verify_metadata/ contracts/metadata`（rtc fields/events/types 一致，已通过）。
  - `ws_event_wire_type_contract_test.go`（已落地：domain event→`client_ws_type` 映射不漂移）。
  - codegen hash 比对（`make gate`），DTO/error/WS+推送 payload 契约。
- local_contract（模块/交互）：
  - `chat_conversation_page_call_entry_test.dart`、`call_participant_picker_page_test.dart`（入口显隐与解释）。
  - `call_session_provider_lifecycle_test.dart`（过程态机）、`video_call_page_states_test.dart`、`video_grid_layout_test.dart`（LiveKit fake track 渲染）。
  - `participant_trust_badge_test.dart`（信任两态）、`call_controls_bar_device_test.dart`（翻转/音频输出真实调用 SFU）、`call_permission_card_test.dart`、`rtc_error_code_test.dart`、`rtc_signaling_wire_type_test.dart`、`platform_capabilities_incoming_call_test.dart`、`active_call_shell_mount_test.dart`。
- api_integration（端云集成）：
  - `call_lifecycle_contract_test.go`、`multi_party_room_contract_test.go`、`incoming_push_payload_contract_test.go`（与 Dart Mock 行为对齐）。
- user_acceptance（端到端旅程，真机/Patrol 或手工 UAT）：
  - 三端来电（iOS CallKit / Android 全屏意图 / Web Push）后台/锁屏唤醒；权限拒绝降级；1v1 视频；群聊 3 人；通话中加“可能不认识”的人提示；返回 PiP；成员离开；弱网降级。

### 15.2 门禁命令

```bash
# 规格/验收结构
bash agent_ops/scaffold/verify_acceptance_standard.sh
bash agent_ops/scaffold/verify_feature_tree_refactor.sh
# 云侧 metadata + 契约
cd quwoquan_service && go run ./tools/verify_metadata/ contracts/metadata
cd quwoquan_service && go test ./services/rtc-service/...
# 端侧分析 + 页面横向质量 + 全量门禁
cd quwoquan_app && flutter analyze lib/ui/rtc lib/cloud/rtc
make gate
```

### 15.3 发布前 UAT 剧本（手工，对标微信）

1. iOS 真机退到后台/锁屏 → 对方发起视频 → CallKit 全屏来电 → 接听进入通话页看到双方真实画面。
2. Android 真机锁屏 → FCM 高优先级 → 全屏意图来电页；在 14+ 关闭全屏意图权限 → 验证降级 heads-up + 设置引导。
3. Web PWA 安装到主屏 → 关闭标签页 → 收到 Web Push 通知 → 点击进会；未安装时验证“添加到主屏幕”引导。
4. 通话中邀请一名“可能不认识”的群外成员 → 在会成员看到轻量横幅 → 被邀请人来电页看到来源与风险提示。
5. 通话中拒绝麦克风/摄像头权限 → 权限卡片 + 仅语音降级；翻转摄像头与切扬声器实测生效。
6. 通话中返回其他页面 → 顶部通话条/PiP → 点击回流；多人“离开”仅自己退出，最后一人离开结束房间。
7. 弱网（限速）→ 质量指示变化 + 自动降级到音频 + ICE 重连恢复。
