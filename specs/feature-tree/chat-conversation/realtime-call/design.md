# 实时音视频通话 设计方案

## 设计动因

spec.md 定义了 32 人实时音视频通话端到端闭环，且在本轮 PRD 中新增了“关系门禁 + 会话入口迁移 + 群聊治理边界”约束，核心设计挑战变为：
- 信令协议与 realtime-gateway 的关系
- LiveKit SFU 自部署与 rtc-service 的职责边界
- 32 人 Simulcast 带宽/CPU/内存预算
- 7 种动态网格布局算法（对标 FaceTime）
- 弱网 6 级对抗与自适应降质策略
- 呼叫状态机的端云一致性
- 来电推送（在线 WS + 离线 VoIP Push + 锁屏 CallKit）
- 录制 (Egress) 与屏幕共享的生命周期管理
- 灰度发布自动回滚门禁
- 1v1 通话的关系门禁（仅互相关注开放）
- 聊天页 AppBar 去通话按钮后，输入区 `+` 面板如何承载语音/视频入口
- 通话中添加人的双链路（直接邀请 / 链接入会）
- 群邀请仅保留响铃邀请模式，前台/后台/锁屏如何统一唤醒语义
- 发起方呼叫铃声如何在 1v1 / 群邀请 / 跨群拉人场景保持一致
- 趣聊品牌蓝如何替换现有“顶部绿色通话条”等记录视觉语义
- 本地调试剧本如何支持“模拟来电 / 5 秒自动接通 / 手动接通”而不污染正式路径

## 上游输入评审

- spec.md 已扩展到 F23 并新增 §12 商用上线 UX 基线、§13 来电平台能力矩阵、§14 信任与隐私提示
- acceptance.yaml 由模板化 SIT 重写为可执行 SIT/GWT/contract + 三层测试 结构（不再以“A1~A56”固定编号描述，避免与磁盘条目漂移）
- 前置依赖 realtime-gateway 已有完整 spec（L2），可并行或串行推进
- 前置依赖 `contact-and-session-governance` 已明确请求箱、互相关注、能力位真相源
- **无阻断项**

> 诚信修订（商用上线基线）：此前本文档曾声称“acceptance.yaml 已扩展到 A56”，但实际 acceptance 仅为模板化 SIT，属规格漂移。本轮已将 acceptance 重写为可验收条目，并以 §9 验收重点 + acceptance.yaml 为唯一真相源；任何“N 条/A56”式计数描述均已废弃。

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 当前差距 |
|------|------|--------|---------|
| FaceTime | 32人动态网格+发言人白色高亮+PiP+P2P→SFU 平滑升级 | 封闭生态绑定 | 网格布局算法需自研，对标其视觉语义 |
| 微信 WAVE | 服务端 QoS 反馈环+渐进式降质+极致弱网保活 | 私有编解码器 | QoS 反馈用 LiveKit 内置 TWCC/REMB 替代 |
| Teams | Simulcast 智能流选择（仅转发可见窗口）+Gallery/Speaker 双视图 | 千人规模 | 智能流选择依赖 LiveKit 的 adaptive subscription |
| LiveKit | Go SFU+Flutter SDK+Egress 录制+E2EE+分布式 Redis | 全托管模式 | 开源自部署，呼叫管理层完全自建 |

## 方案对比

### 对比 1：信令通道

#### 方案 A：复用 realtime-gateway（选定）

来电推送、通话状态变更通过 realtime-gateway 的 WebSocket topic 机制投递。rtc-service 发布领域事件 → Redis Pub/Sub → realtime-gateway → topic `rtc/call/{callId}` → 端侧。

**优点**：统一连接管理、复用在线感知和离线降级逻辑、架构一致
**缺点**：依赖 realtime-gateway 先行就绪
**适用条件**：realtime-gateway 核心能力（G1~G4）已实现

#### 方案 B：rtc-service 内建独立 WS

rtc-service 自建 `/rtc/signal` WebSocket 端点，独立维护信令连接。

**优点**：无外部依赖，可立即开工
**缺点**：连接管理/心跳/重连/在线感知全部重复建设；端侧需维护两条 WS；运维复杂度翻倍
**适用条件**：realtime-gateway 无法先行的应急方案

**降级策略**：若 realtime-gateway 延期，Phase 1 可临时使用方案 B 的最小实现（仅来电推送），Phase 2 迁移到方案 A。

### 对比 2：SFU 引擎

#### 方案 A：LiveKit 自部署（选定）

Apache 2.0 开源 Go SFU，自部署到自有 K8s 集群。

**优点**：生产就绪（3000人/节点基准）、Flutter SDK 官方维护、内置 Simulcast/录制/E2EE/屏幕共享、分布式 Redis 路由
**缺点**：引入外部依赖（但开源可 fork）；版本升级需跟进社区
**适用条件**：需要快速上线且长期可维护的 SFU

#### 方案 B：裸 Pion ion-sfu 自研

基于 Pion 的 ion-sfu（已归档）fork 后自行维护。

**优点**：完全可控、无第三方
**缺点**：已归档无人维护；无 Flutter SDK（需自建 3~6 月）；无录制/屏幕共享/E2EE；Simulcast 需自调优；总工时 12~18 月
**适用条件**：超大规模且需深度定制（不适用于 0→1）

### 对比 3：1v1 媒体策略

#### 方案 A：统一 SFU（选定）

所有通话统一走 SFU 转发，包括 1v1。

**优点**：架构简单一致、1v1→多人无缝升级、录制/监控统一、服务端可插入降噪/混流
**缺点**：1v1 场景多一跳延迟（+20~50ms）
**适用条件**：延迟要求 < 200ms p95 可满足

#### 方案 B：P2P 优先 → SFU 降级

1v1 先尝试 P2P 直连，TURN 穿透失败或多人时升级到 SFU。

**优点**：1v1 延迟更低（-20~50ms）、节省 SFU 带宽
**缺点**：两套媒体路径维护成本高；P2P→SFU 切换有短暂中断；录制需端侧实现
**适用条件**：DAU > 100K 且 SFU 带宽成本过高时再演进

### 对比 4：32 人网格布局

#### 方案 A：FaceTime 式动态等分（选定）

按参与者数量动态切换 7 种网格配置，所有瓦片等大小，发言人白色高亮边框。

**优点**：实现简洁、布局可预期、对标 FaceTime 用户认知、可翻页/滚动
**缺点**：发言人不放大（通过高亮区分）
**适用条件**：≤32 人社交场景

#### 方案 B：微信式固定网格 + 动态大小

发言人瓦片放大，其他缩小，布局动态变化。

**优点**：发言人突出
**缺点**：布局跳动影响认知稳定性、实现复杂、32 人时放大无意义
**适用条件**：≤9 人小群

## 修订记录

### REV-1（2026-03-08）：信令通道方案降级

**背景**：realtime-gateway 当前 0 个 Go 源文件，不具备先行条件。原 KD-2 端到端时序完全依赖 realtime-gateway WS 推送来电通知，实际无法执行。

**决策变更**：
- **Phase 1（MVP）**：rtc-service 内建最小 WS 信令端点 `/rtc/signal`，仅承担来电推送和通话状态同步。离线唤醒通过 FCM/APNs VoIP Push。
- **Phase 2（演进）**：realtime-gateway 就绪后，迁移信令到统一通道，rtc-service WS 下线。

**降级范围**：仅信令投递路径变更，呼叫状态机（KD-1）、SFU 选型、媒体策略、布局算法等决策不变。

### REV-2（2026-03-08）：AnswerCall 契约统一

**背景**：`service.yaml` 定义 AnswerCall 返回 `[token, roomId]`，但实现仅返回 session。

**决策变更**：AnswerCall 统一返回 `{session, token, roomId}`，接听方无需再调 JoinCall 获取 token。

### REV-3（2026-03-10）：入口与门禁重构

**背景**：原设计默认把 1v1/群聊通话入口放在 ChatDetail AppBar，与本轮 PRD 冻结的“AppBar 保持简洁、通话入口下沉到输入区 `+` 面板、1v1 仅互相关注开放”发生冲突。

**决策变更**：
- 1v1/群聊 ChatDetail AppBar 不再承载语音/视频直达按钮
- 1v1 通话入口迁移到输入区 `+` 面板，且仅在 `互相关注` 关系下显示；`互相关注` 仅保留子态快捷语义
- 群聊通话入口迁移到输入区 `+` 面板
- 通话中加人支持“直接邀请联系人/成员”和“生成呼叫链接入会”两条链路
- 群聊选人规则固化为：`<= 8 人默认全选，> 8 人默认不选`

### REV-4（2026-03-10）：群邀请响铃、铃声归属与品牌蓝统一

**背景**：本轮 PRD 进一步冻结了多人通话与来电体验规则：群邀请没有“静默加入”或“仅消息通知”模式，统一走响铃邀请；铃声优先使用发起方专属呼叫铃声；群通话后续加人不改变铃声归属；顶部通话条与来电语义统一切换到趣聊品牌蓝。

**决策变更**：
- 群语音/视频邀请仅支持响铃邀请，前台走应用内全屏来电页，后台/锁屏走 CallKit / FullScreen Intent
- 来电铃声仅支持趣聊官方铃声库，不支持用户上传、本地导入或第三方 URL
- 若发起方配置专属呼叫铃声，则 1v1、群邀请、跨群拉人场景均优先使用发起方铃声
- 群通话铃声固定归属原始发起方（initiator），不随后续邀请链变化
- 顶部通话条从绿色语义切换为趣聊品牌蓝，并与来电通知、呼出页保持统一视觉系统
- 开发态补充“模拟来电”“5 秒自动接通”“手动接通/拒接/超时”本地调试入口

### REV-5（商用上线基线）：三端来电矩阵、信任两态、可靠性收口

**背景**：商用上线评审发现来电入口未按平台拆分、通话页过程态缺失、LiveKit 参与者未绑定 UI、WS 事件 type 端云漂移、全局协调器未挂载、错误/权限文案硬编码。

**决策变更**：

- 来电分三端能力矩阵（见 spec §13）：iOS PushKit+CallKit（收到即上报来电）、Android FCM 高优先级+`USE_FULL_SCREEN_INTENT` 全屏意图（含 Android 14+ 特殊权限与降级）、Web Push+Service Worker+Notification（PWA 安装后，前台站内弹窗）。平台判断收口到 `PlatformCapabilities`（`incomingCallUi`/`webPushIncomingCall`/`realtimeCommunication`），业务层不裸用 `Platform.is*`/`kIsWeb`。
- 信任两态（见 spec §14）：参与者标注 `认识/可信` 与 `可能不认识`，由 metadata 字段驱动；来电页与通话中加人提示消费该字段。
- WS wire type：events.yaml 的 `client_ws_type` 必须经 codegen 生成 Go 端映射，orchestrator `publishEvent` 推送时使用 wire type（如 `call.ringing`），与 Dart `parseRtcWsPayload` 对齐；禁止把 domain 常量当 wire type。
- 参与者绑定：`call_session_provider` 订阅 `LiveKitRoomService` 的 participant/track/speaker/quality 事件，实时写入 `callParticipantsProvider`；通话页渲染真实 `VideoTrack`。
- 设备控制真实生效：翻转摄像头调用 `LiveKitRoomService.switchCamera()`，音频输出调用 `setSpeakerOn()`。
- 生命周期收口：`IncomingCallCoordinator`/`ActiveCallBar`/`PipCallOverlay` 挂载到 app shell 唯一入口，覆盖来电、返回通话、PiP、后台恢复。
- 错误/权限：错误码走 `errors.yaml`→codegen（补 `not_mutual`/`blocked` 端侧枚举），文案走 `UITextConstants`/l10n，权限走统一权限卡片与降级路径。

**降级范围**：UX/可靠性/平台矩阵层变更，呼叫状态机（KD-1）、SFU 选型、媒体策略、布局算法不变。

### REV-6（/plan-next 自检：对标微信/FaceTime 商用收口）

**背景**：S0–S3、S7 端云根因（信令对齐、参与者/轨道绑定、设备控制、错误码端云贯通、信任两态字段）已落地。`/plan-next` 多角色自检发现两类商用阻断缺口必须先收口，才能继续 FaceTime 级体验增强。

**GATE_BLOCK 处置项**：

- **B1 全局挂载未接线（致命）→ 已收口**：删除 `incoming_call_coordinator.dart` 中 `throw UnimplementedError` 的 `goRouterProvider` 占位，`incomingCallCoordinatorProvider` 改为直接 `ref.read(appRouterProvider)`，CallKit 接听跳转改用 `AppRoutePaths.rtcIncoming(callId:)`（消除硬编码路径）。`MainAppShell` 作为路由就绪后的唯一常驻外壳：`initState` 与 auth 翻转监听里统一调 `_syncIncomingCallCoordinator()`，依据登录态唯一启停协调器（启停决策抽为纯函数 `resolveIncomingCallSync`，幂等、登录 start/登出 stop/切换先停后启）；并在外壳 `Stack` 顶部挂 `ActiveCallBar`（点击回流 `rtcVideo/rtcVoice`）、最上层挂 `PipCallOverlay`（回流/挂断）。同时修复协调器 `stop()/dispose()` 在 Riverpod 生命周期内 `ref.read` 的越界 bug（缓存信令客户端引用）与 `callEnded` 订阅泄漏。证据：`active_call_shell_mount_test.dart`（协调器装配不抛、启停幂等五态、来电条/PiP 唯一挂载与回流）。
- **B2 acceptance↔实现脱节（诚信）→ 已收口**：`acceptance.yaml` 7 个 SIT 的 `recorded` 全部回填为磁盘真实存在的测试（picker widget、Go lifecycle/room contract、signaling wire/payload、`rtc_errors`、shell mount/bar/pip），`status` 由 `pending` 改为 `partial`（SIT4 三端来电平台矩阵尚无测试，保持 `pending`）；`planned` 仅保留确未落地项（chat 入口、provider 生命周期、trust badge、Go ws wire-type、permission card、controls device、平台能力位）。`verify_acceptance_standard.sh` 通过。

**对标差距（FaceTime/微信级，纳入新规划而非阻断）**：

- 来电全屏含视频自预览、接听前麦克风/摄像头预检；通话中下滑/返回缩为系统级浮窗（PiP）回流。
- 网络中断优雅降级横幅与自动重连提示；通话记录消息回插会话。
- 三端来电真实唤醒链路（S6）与权限统一卡片仍待端到端打通。

**降级范围**：不改状态机/SFU/媒体策略；仅补接线、过程态、平台唤醒与测试证据。

### REV-7（GATE_BLOCK 解除后的 S5/S6/FaceTime 收口）

**S5 过程态闭环**：新增展示态 `CallStage`（connecting/ringing/waitingPeer/inCall/reconnecting/weakNetwork/peerNoAnswer/peerLeft/ended），由纯函数 `resolveCallStage(status, connectedPeerCount, isReconnecting, isWeakNetwork, endReason)` **单一派生**（不污染 `CallStatus` 状态机，遵 R24）。`CallSessionState` 增 `isReconnecting`，provider 在建连前置 `CallStatus.connecting`、媒体连通置 `inCall`、监听 `LiveKitRoomService.connectionState` 的 `reconnecting` 翻转标记（`_endCallState` 中移除监听防泄漏）。新增 `CallStageBanner` 统一渲染过程态文案（弱网/重连为 caution 黄底，其余暗底），video/voice 页各挂一处；文案全部入 `UITextConstants`。证据：`call_session_provider_lifecycle_test.dart`（过程态派生 9 例 + 分类语义 + 横幅显隐/文案映射，14 例全绿）。

**S6 三端来电唤醒 + 能力位 + 权限卡片**：`PlatformCapabilities` 增 `webPushIncomingCall`（web=true，其余 false）；纯函数 `resolveIncomingCallChannel(caps)` 由能力位单一派生来电通道 `nativeCallKit | webPushInApp | inAppOnly | unsupported`（RTC 不可用最高优先级置 unsupported，原生来电屏优先于 Web Push，遵 R-XP1/R-XP2 无裸平台判断）。协调器 `start()` 按通道分支：native 走 CallKit，web/inApp 直接路由站内来电页，unsupported 不建监听（与入口能力位一致降级）。新增统一权限预检 `CallPermissionGuard`（麦克风硬门槛、视频缺摄像头降级仅语音），权限卡片复用 `UiErrorSemantic(permissionRequired)` + 去设置（不另起 RTC 专用提示，遵 R31/R18）；`IncomingCallPage` 接听前置预检并修正硬编码 `/rtc/video|voice` 为 `AppRoutePaths`。证据：`platform_capabilities_incoming_call_test.dart`、`incoming_call_coordinator_test.dart`、`call_permission_card_test.dart`（SIT4 解除 pending、SIT6 回填）。

**FaceTime 级体验**：PiP 浮窗手势（拖拽 + 贴边吸附 + 点击回流 + 长按挂断）与弱网降级横幅（S5 weakNetwork 态）已具备，无需重复实现。新增纯函数 `CallSummary.describe(duration, endReason, connected)` 统一结束摘要（已接通显示时长，未接通按原因显示），为后续通话记录回插预备同一文案口径。证据：`call_summary_test.dart`。

**仍待契约（诚实记录，不强行落地）**：**通话记录回插会话** 依赖 chat `call` 消息类型契约（`contracts/metadata/chat/.../fields.yaml` 的 message `type` 扩展 + 发送链路），属跨域 metadata-first 变更，未在本次范围内打通；当前仅落地端侧 `CallSummary` 文案基座，SIT2 该 done_when 保持未勾。三端来电的真实推送链路（PushKit/FCM full-screen/Web Push Service Worker）仍为 native/web 工程接入项，能力位与端侧分支已就绪。

## 选型决策

| 决策 | 选定 | 理由 |
|------|------|------|
| 信令通道 | **Phase 1: rtc-service 内建 WS（REV-1）；Phase 2: 迁移到 realtime-gateway** | realtime-gateway 未就绪，先用最小 WS 打通来电推送 |
| SFU 引擎 | **方案 A：LiveKit 自部署** | 生产就绪、Flutter SDK、Egress/E2EE 内置、开源可 fork |
| 1v1 媒体策略 | **方案 A：统一 SFU** | 架构简单一致、满足 ≤200ms 延迟、录制统一 |
| 网格布局 | **方案 A：FaceTime 式动态等分** | 对标一流体验、布局稳定可预期、32 人可扩展 |
| 播放引擎（端侧） | **livekit_client (Flutter)** | LiveKit 官方 Flutter SDK，内置 WebRTC 管理 |
| 来电组件（端侧） | **flutter_callkit_incoming** | iOS CallKit + Android FullScreen 统一 |
| 1v1 通话门禁 | **互相关注能力位前置** | `互相关注 = 互关`；互相关注仅作为互相关注子态语义，不额外放宽门禁 |
| 聊天页通话入口 | **输入区 `+` 面板** | AppBar 保持简洁，会话动作集中在 composer |
| 多人入会补充链路 | **直接邀请 + 呼叫链接** | 兼顾熟人拉人和会中扩散 |
| 群邀请模式 | **仅响铃邀请** | 保持微信/FaceTime 式“有人在呼叫你”的强提醒语义 |
| 铃声策略 | **发起方铃声优先 + 官方铃声库限定** | 强化“谁在呼叫我”的关系感知，同时控制版权/审核/音量标准 |
| 顶部通话条视觉 | **趣聊品牌蓝** | 与 App 主品牌一致，不沿用微信式绿色 |

## 关键设计决策

### KD-1: 呼叫状态机（已定）

```
                     发起方                                    接收方
                       │                                        │
                  ┌────▼────┐                                   │
                  │  IDLE   │                                   │
                  └────┬────┘                                   │
                       │ initiate_call                          │
                  ┌────▼────┐    call.initiated            ┌────▼────┐
                  │INITIATED│────────────────────────────▶ │ RINGING │
                  └────┬────┘                               └────┬────┘
                       │                                         │
              ┌────────┼────────┐                    ┌───────────┼──────────┐
              │        │        │                    │           │          │
         30s timeout cancel   answer              reject      answer    30s timeout
              │        │        │                    │           │          │
         ┌────▼──┐ ┌───▼───┐ ┌─▼──────────┐   ┌───▼───┐  ┌───▼────────┐ ┌──▼────┐
         │ ENDED │ │ ENDED │ │ CONNECTING │   │ ENDED │  │ CONNECTING │ │ ENDED │
         │(NO_   │ │(CANCEL│ └───┬────────┘   │(REJECT│  └───┬────────┘ │(NO_   │
         │ANSWER)│ │LED)   │     │ICE+DTLS    │ED)    │      │ICE+DTLS  │ANSWER)│
         └───────┘ └───────┘ ┌───▼───┐        └───────┘  ┌───▼───┐     └───────┘
                             │IN_CALL│◄═══ 媒体流 ═══════▶│IN_CALL│
                             └───┬───┘                    └───┬───┘
                                 │ hangup/error/last_leave    │
                             ┌───▼───┐                    ┌───▼───┐
                             │ ENDED │                    │ ENDED │
                             │(NORMAL│                    │(NORMAL│
                             └───────┘                    └───────┘
```

**多人通话扩展**：不使用 INVITE→RINGING 双边协商，改为「加入房间」模型：

```
IDLE → JOIN_ROOM → CONNECTING → IN_CALL → LEAVE → ENDED
```

发起者创建房间后，被邀请人收到来电通知可选择加入（JoinCall）。

**超时处理**：
- 1v1：30s 无应答 → NO_ANSWER
- 多人邀请：60s 无应答 → 个人标记 TIMEOUT，通话继续

### KD-2: 端到端调用时序（已定）

```
发起方A          rtc-service        LiveKit SFU       realtime-gw        接收方B
  │                  │                  │                  │                │
  │ POST /rtc/    │                  │                  │                │
  │ calls            │                  │                  │                │
  │─────────────────▶│                  │                  │                │
  │                  │ CreateRoom       │                  │                │
  │                  │─────────────────▶│                  │                │
  │                  │◀─────────────────│ roomId           │                │
  │                  │                  │                  │                │
  │                  │ GenToken(A)      │                  │                │
  │                  │                  │                  │                │
  │                  │ call.initiated ──────────────────▶│                │
  │                  │                  │               │ WS push         │
  │◀─────────────────│ {callId,roomId,  │               │ (在线)          │
  │  token_A}        │                  │               │──────────────▶│
  │                  │                  │               │ 或 VoIP Push   │
  │ Connect SFU      │                  │               │ (离线)          │
  │══════════════════════════════════▶│               │                │
  │                  │                  │               │                │
  │                  │                  │               │  IncomingCall  │
  │                  │                  │               │  Page / CallKit│
  │                  │                  │               │                │
  │                  │◀─────────────────────────────────────────────────│
  │                  │ POST .../answer  │               │                │
  │                  │ GenToken(B)      │               │                │
  │                  │─────────────────────────────────────────────────▶│
  │                  │  {token_B}       │               │                │
  │                  │                  │               │                │
  │                  │                  │◀═════════════════════════════│
  │                  │                  │  Connect SFU (B)             │
  │◄═══════════════════════════════════▶◄═════════════════════════════▶│
  │                双向音视频流 (SRTP over DTLS)                        │
```

### KD-3: 云侧服务分层（已定）

```
services/rtc-service/
├── cmd/api/main.go                          # 标准启动
├── internal/
│   ├── domain/call_session/
│   │   ├── model/call_session.go            # [codegen] CallSession 聚合根
│   │   ├── model/participant.go             # [codegen] Participant 值对象
│   │   ├── repository/repository.go         # [codegen] Repository 接口
│   │   ├── event/events.go                  # [codegen] 8 个领域事件
│   │   └── call_session_service.go          # [手写] 呼叫状态机核心逻辑
│   ├── application/
│   │   ├── call_orchestrator.go             # 发起/接听/挂断/超时 编排
│   │   ├── room_service.go                  # LiveKit Room 生命周期
│   │   └── token_service.go                 # LiveKit JWT Token 签发
│   ├── adapters/
│   │   ├── http/
│   │   │   ├── call_handler.go              # 14 REST API handler
│   │   │   └── generated_routes.go          # [codegen] 路由表
│   │   └── mq/
│   │       └── call_event_publisher.go      # 事件发布
│   └── infrastructure/
│       ├── persistence/
│       │   └── mongo_call_store.go          # MongoDB CallSession 存储
│       ├── cache/
│       │   └── call_state_cache.go          # Redis 通话状态缓存
│       └── livekit/
│           ├── room_adapter.go              # LiveKit Go Server SDK 封装
│           └── token_generator.go           # JWT Token 生成
├── tests/
│   ├── call_lifecycle_contract_test.go      # 呼叫状态机全覆盖
│   ├── room_management_contract_test.go     # 多人房间管理
│   ├── event_publish_contract_test.go       # 8 事件发布
│   └── benchmark_test.go                   # 500 并发基准
├── configs/config.yaml
├── go.mod
└── Makefile
```

### KD-4: 端侧模块架构（已定）

```
lib/ui/rtc/                               # 独立 UI 域
├── pages/
│   ├── outgoing_call_page.dart            # 呼出等待页
│   ├── incoming_call_page.dart            # 来电接听页
│   ├── voice_call_page.dart               # 语音通话中
│   ├── video_call_page.dart               # 视频通话中
│   └── call_participant_picker_page.dart  # 多人通话选人
├── providers/
│   ├── call_session_provider.dart         # 通话状态 Notifier
│   ├── call_participants_provider.dart    # 参与者列表
│   ├── media_device_provider.dart         # 摄像头/麦/扬声器
│   └── call_timer_provider.dart           # 通话时长
├── widgets/
│   ├── call_controls_bar.dart             # 底部 6 按钮控制栏
│   ├── video_grid_layout.dart             # 7 种动态网格
│   ├── speaker_highlight_layout.dart      # 演讲者视图
│   ├── participant_tile.dart              # 单人视频瓦片
│   ├── caller_avatar_pulse.dart           # 呼叫中脉冲动效
│   ├── call_duration_badge.dart           # 时长显示
│   ├── pip_call_overlay.dart              # App 内 PiP 浮窗
│   ├── call_quality_indicator.dart        # 网络质量指示
│   ├── participant_list_sheet.dart        # 参与者管理面板
│   └── active_call_bar.dart              # 顶部蓝色通话条
└── models/
    ├── call_state.dart                    # 通话状态枚举
    ├── call_participant.dart              # 参与者视图模型
    └── call_layout_mode.dart             # Grid / Speaker 枚举

lib/cloud/services/rtc/
├── rtc_repository.dart                    # Abstract + Mock + Remote
└── mock/rtc_mock_data.dart

lib/cloud/rtc/models/
├── call_session_dto.dart
├── call_participant_dto.dart
└── rtc_token_dto.dart

lib/cloud/runtime/generated/rtc/
├── rtc_errors.g.dart                      # [codegen]
└── rtc_metadata.g.dart                    # [codegen]

lib/core/services/
└── active_call_service.dart               # 全局通话状态（PiP/来电覆盖/后台保活）
```

### KD-5: 7 种动态网格布局算法（已定，对标 FaceTime）

```dart
GridConfig gridConfigFor(int count) {
  if (count <= 1) return GridConfig(rows: 1, cols: 1);
  if (count == 2) return GridConfig(rows: 1, cols: 2);        // 1×2
  if (count == 3) return GridConfig(rows: 2, cols: 2, gap: 1); // 2×2 缺一
  if (count == 4) return GridConfig(rows: 2, cols: 2);         // 2×2
  if (count <= 6) return GridConfig(rows: 2, cols: 3);         // 2×3
  if (count <= 9) return GridConfig(rows: 3, cols: 3);         // 3×3
  if (count <= 16) return GridConfig(rows: 4, cols: 4);        // 4×4
  return GridConfig(rows: 4, cols: 4, overflow: true);         // 4×4 + 翻页
}
```

**2 人**：左右等分，全屏宽。
```
┌──────┬──────┐
│  A   │  B   │
└──────┴──────┘
```

**3 人**：2×2 网格，右下空。
```
┌──────┬──────┐
│  A   │  B   │
├──────┼──────┤
│  C   │      │
└──────┴──────┘
```

**4 人**：2×2 等分。
```
┌──────┬──────┐
│  A   │  B   │
├──────┼──────┤
│  C   │  D   │
└──────┴──────┘
```

**5~6 人**：2×3。
```
┌────┬────┬────┐
│  A │  B │  C │
├────┼────┼────┤
│  D │  E │(F) │
└────┴────┴────┘
```

**7~9 人**：3×3。
```
┌────┬────┬────┐
│  A │  B │  C │
├────┼────┼────┤
│  D │  E │  F │
├────┼────┼────┤
│  G │  H │(I) │
└────┴────┴────┘
```

**10~16 人**：4×4。
```
┌───┬───┬───┬───┐
│ A │ B │ C │ D │
├───┼───┼───┼───┤
│ E │ F │ G │ H │
├───┼───┼───┼───┤
│ I │ J │ K │ L │
├───┼───┼───┼───┤
│ M │ N │ O │(P)│
└───┴───┴───┴───┘
```

**17~32 人**：4×4 翻页模式，底部分页指示器。
- 第 1 页：16 人（4×4）
- 第 2 页：剩余 1~16 人
- 左右滑动切换页
- 当前发言人所在页优先显示

**发言人高亮**（全视图通用）：
- 检测 Audio Level（LiveKit `audioLevel` 事件，RFC6464）
- 当前发言人瓦片：白色发光边框（2px glow, `AppColors.primary`）
- 切换延迟：发言持续 >500ms 才切换，避免频繁跳动
- 最近发言人最多 1 个（avoid 多人同时高亮混乱）

### KD-6: 演讲者视图（已定，对标 Teams）

```
┌────────────────────────────────────────────────┐
│                                                │
│          当前发言人大画面（70% 高度）             │
│          自动切换（延迟 500ms 防抖）              │
│                                                │
├────────────────────────────────────────────────┤
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ··· │
│ │  A  │ │  B  │ │  C  │ │  D  │ │  E  │     │ ← 30% 高度
│ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘     │   横向滚动
└────────────────────────────────────────────────┘
```

- 大画面：发言人全宽、70% 高度
- 底部：缩略行横向滚动，每个 80×80pt
- 发言人在底部行也有瓦片，但加白色边框
- 点击底部瓦片 → 强制切换大画面到该用户（锁定模式，再次点击解除）

**网格 ↔ 演讲者切换**：
- 双指捏合手势（pinch）：Grid → Speaker / Speaker → Grid
- 右上角视图切换按钮（备选交互）
- 默认：≤4 人为 Grid，≥5 人为 Speaker（用户可覆盖偏好）

### KD-7: 通话控制栏交互（已定）

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐│
│  │ 🔇   │  │ 📷   │  │ 🔄   │  │ ➕   │  │ 📱   │  │ 🔴   ││
│  │ 静音  │  │ 摄像  │  │ 翻转  │  │ 邀请  │  │ 扬声  │  │ 挂断  ││
│  │      │  │ 头    │  │ 摄像  │  │ 更多  │  │ 器   │  │      ││
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘│
│                                                              │
│  点击：toggle 状态                                            │
│  背景：开启=白底黑图标  关闭=透明底白图标                        │
│  挂断：红色背景，始终显示                                       │
│  长按扬声器：弹出路由选项（听筒/扬声器/蓝牙）                    │
│  语音通话：隐藏「摄像头」「翻转」，显示「开启视频」               │
│                                                              │
│  隐藏行为：3s 无操作 → 控制栏淡出；点击屏幕 → 重新显示           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### KD-8: 来电交互设计（已定，对标 FaceTime/微信）

**App 前台来电**：全屏 IncomingCallPage
```
┌──────────────────────────────┐
│                              │
│       ┌────────────┐         │
│       │            │         │
│       │  发起方头像  │         │
│       │  (脉冲动效)  │         │
│       │            │         │
│       └────────────┘         │
│                              │
│       张三 邀请你视频通话      │
│                              │
│                              │
│   ┌──────────┐ ┌──────────┐ │
│   │  🔴 拒绝  │ │  🟢 接听  │ │
│   └──────────┘ └──────────┘ │
│                              │
│  上滑接听（备选手势交互）      │
│                              │
└──────────────────────────────┘
```

**App 后台/锁屏来电**：
- iOS：CallKit 原生来电界面（系统级，与电话来电一致）
- Android：FullScreen Intent → 系统覆盖来电页面
- 杀死状态：VoIP Push 唤醒 → CallKit/FullScreen Intent

**呼出等待页**（OutgoingCallPage）：
```
┌──────────────────────────────┐
│                              │
│       ┌────────────┐         │
│       │            │         │
│       │  对方头像    │         │
│       │  (脉冲动效)  │         │
│       │            │         │
│       └────────────┘         │
│                              │
│       正在呼叫 张三...        │
│       00:05                  │
│                              │
│          ┌──────────┐        │
│          │  🔴 取消  │        │
│          └──────────┘        │
│                              │
└──────────────────────────────┘
```

### KD-9: 画中画 (PiP) 设计（已定）

**App 内 PiP**：
- 触发：通话中按系统返回键 / 导航到其他页面
- 浮窗大小：120×160pt（可拖动到屏幕四角）
- 内容：1v1 显示对方画面；多人显示当前发言人
- 点击：返回通话全屏页面
- 关闭：长按 → 确认挂断

**系统级 PiP**：
- 触发：App 切到后台
- iOS：`AVPictureInPictureController`（需视频通话）
- Android：`enterPictureInPictureMode`（API 26+）
- 语音通话切后台：不显示 PiP，仅顶部蓝色通话条

**顶部蓝色通话条**：
```
┌──────────────────────────────────────────┐
│ 🔵 通话中  02:34  点击返回               │  ← 品牌蓝背景，高 28pt
└──────────────────────────────────────────┘
```
- 固定在状态栏下方
- 显示通话时长实时计时
- 点击返回通话全屏

### KD-9A: 来电唤醒与铃声策略（已定）

**唤醒分层**：
- 前台：直接展示应用内全屏来电页（IncomingCallPage 语义），不先落普通通知
- 后台 / 锁屏：iOS 走 CallKit，Android 走 FullScreen Intent
- 系统级唤醒失败：退化到高优先级来电通知，点击后进入来电页

**邀请模式**：
- 1v1：响铃邀请
- 群语音 / 群视频：同样统一为响铃邀请
- 不提供静默加入或仅消息通知模式

**铃声策略**：
- 铃声资源仅来自趣聊官方铃声库
- 若发起方配置专属呼叫铃声，则优先使用发起方铃声
- 若发起方未配置或系统环境不支持，则回退趣聊默认铃声，再回退系统默认来电铃声
- 群通话始终以原始发起方（initiator）作为铃声来源，不随后续邀请链变化

**本地调试剧本**：
- 开发态提供“模拟来电”入口，验证前台 / 后台 / 锁屏三类来电唤醒
- 呼出等待页提供“5 秒自动接通”开关和“手动接通 / 拒接 / 超时”调试按钮
- 调试入口仅在开发态可见，不进入正式用户主链路

### KD-10: 弱网自适应策略（已定，对标微信 WAVE QoS 反馈环）

```
端侧采集                    SFU 调控                     端侧自适应
┌─────────┐               ┌─────────────────────┐       ┌─────────────┐
│ RTT     │──────────────▶│ TWCC 拥塞控制        │──────▶│ 动态切换     │
│ 丢包率   │               │ REMB 带宽估计        │       │ Simulcast   │
│ 抖动    │               │ Simulcast 层选择     │       │ 接收层       │
│ 带宽    │               │ 音频优先保障         │       │             │
└─────────┘               └─────────────────────┘       └──────┬──────┘
                                                               │
                                                        ┌──────▼──────┐
                                                        │ UI 质量指示  │
                                                        │ 🟢🟡🟠🔴    │
                                                        └─────────────┘
```

**6 级对抗机制**：

| 级别 | 触发条件 | 动作 | UI |
|------|---------|------|-----|
| L0 正常 | RTT<50ms, 丢包<1% | 720p Simulcast 高层 | 无指示 |
| L1 轻微 | RTT 50~150ms, 丢包 1~3% | 切到 360p 中层 | 🟡 |
| L2 弱网 | RTT 150~300ms, 丢包 3~5% | 切到 180p 低层 + 降帧率到 15fps | 🟠 |
| L3 极弱 | RTT>300ms 或 丢包>5% | 关闭视频，仅音频 | 🔴 "网络不佳" |
| L4 断网 | 连续 3s 无包 | 冻结画面 + 静音 + ICE restart | 🔴 "连接中断" |
| L5 恢复 | ICE restart 成功 | 恢复到 L2 → 逐级恢复到 L0 | 🟠→🟡→🟢 |

**恢复策略**：断网恢复后不立即跳到 L0，先恢复到 L2（180p），稳定 5s 后升到 L1（360p），再稳定 5s 升到 L0（720p），避免弱网反复切换。

### KD-11: 录制设计（已定）

- 使用 LiveKit Egress 组件（Composite 模式：合成所有参与者画面为单视频）
- 录制由发起方或管理员触发（POST .../recording）
- 录制开始 → 全体参与者收到 `call.recording_started` 事件
- 端侧显示红色录制指示 REC 🔴
- 通话结束 → Egress 输出文件上传到 OSS → URL 写入 CallSession.recording
- 录制格式：H.264 + AAC → MP4
- 存储策略：30 天保留（可配置），到期自动清理

### KD-12: 屏幕共享设计（已定）

- 同时只允许 1 人共享屏幕
- 发起：POST .../screen-share → LiveKit publishTrack(screenShare)
- 其他参与者收到 `call.screen_share_started` 事件
- 端侧自动切换为演讲者视图，大画面显示共享屏幕
- 共享者本人看到自己共享内容的预览 + 停止按钮
- 停止共享 → 恢复摄像头画面 → 回到之前的布局模式
- iOS：ReplayKit 系统级屏幕采集
- Android：MediaProjection API

### KD-13: 1v1 关系门禁（已定）

RTC 能力不再仅由“会话存在”决定，而由 `contact-and-session-governance` 输出的能力位决定：

| 关系层级 | 是否可消息 | 是否可语音 | 是否可视频 |
|----------|-----------|-----------|-----------|
| 陌生用户 | 否 | 否 | 否 |
| 关注用户 | 打招呼后等待回复 | 否 | 否 |
| 已回复未互相关注 | 是 | 否 | 否 |
| 互相关注 | 是 | 是 | 是 |
| 互相关注 | 是 | 是 | 是 |

云侧规则：

- `InitiateCall` / `InviteToCall` 在 user/chat 侧能力位校验后发起
- rtc-service 仍做最终复核，避免端侧绕过
- block、allowStrangerMsg、非互关、请求箱未升级等都映射为结构化错误码

端侧规则：

- 主页、会话 `+` 面板、会中邀请都消费同一份 `canStartVoiceCall/canStartVideoCall`
- 正式会话但尚未互关时，显示“加互相关注”关系条，而不是显示通话按钮

### KD-14: 聊天页入口迁移（已定）

聊天页动作分层：

1. AppBar：导航、标题、会话设置
2. 输入区 `+` 面板：发送/互动/发起动作

因此 RTC 入口迁移为：

- 1v1 会话：输入区 `+` 面板显示 `语音通话 / 视频通话`
- 群聊会话：输入区 `+` 面板显示 `发起语音通话 / 发起视频通话`
- AppBar 不再承载通话按钮

这与现有 `CustomizableChatInputBar` 的扩展面板形态一致，可复用而不需要新建第三套入口容器。

### KD-15: 多人选人与通话中加人（已定）

#### 群聊发起多人通话

- `<= 8 人`：默认全选（除自己）
- `> 8 人`：默认不选，由用户主动勾选
- 选择页支持搜索、单选、多选、全不选、恢复默认

#### 通话中加人

提供两条链路：

1. **直接邀请**
   - 从当前群成员、会话成员、联系人中选择
   - 适合熟人局

2. **呼叫链接入会**
   - 生成短时有效链接
   - 可分享到个人会话或群聊
   - 对方点击后进入预入会页，再执行 `JoinCall`

当前阶段链接治理约束：

- 有效期受 CallSession 生命周期约束
- 会话结束后链接失效
- 后续若需要主持人审批，再在下一阶段扩展

### KD-16: 灰度发布策略（已定）

```
Phase 1: dev 全量
├── make gate 全部通过
├── 手动验证：1v1 语音/视频 + 来电 + 挂断 + 超时
└── 通过 → 进入 integration

Phase 2: integration 全量
├── local_contract~api_integration 全量自动化测试通过
├── 32 人基准测试（SFU CPU <85%, 延迟 p95 <350ms）
├── 弱网模拟（100kbps 音频不断 ≥60s, ICE 重连 ≥95%）
├── 持续 48h 无 P0
└── 通过 → 进入 prod 灰度

Phase 3: prod 5%（userId hash）
├── 自动监控门禁（5 项指标 × 24h）：
│   建连率 ≥98% | 延迟 p95 ≤400ms | 中断率 ≤2%
│   崩溃率 ≤0.1% | SFU CPU ≤85%
├── 任一超标 → 自动回滚
└── 24h 达标 → 扩大

Phase 4: prod 20% → 7 天观察
Phase 5: prod 50% → 7 天观察
Phase 6: prod 100% 全量放开
```

## 适用场景与约束

- **适用**：趣聊 1v1 + ≤32 人群聊/圈子实时通话
- **约束**：统一 SFU 模式 1v1 多一跳延迟（+20~50ms），≤200ms p95 可满足；32 人满房 SFU 单节点带宽 ~96Mbps（可接受）
- **局限**：不含 P2P 优化（未来演进）、不含 Web 端、不含超 32 人

## 元数据唯一源分层

| 主题 | 唯一真相源 | 消费位置 | 说明 |
|------|-----------|---------|------|
| 通话状态机 / 通话快照 | `rtc/call_session/fields.yaml` + `events.yaml` | rtc-service / app DTO / signaling payload | `initiatorRingtoneId` 在 CallSession 创建时快照，保证群通话后续加人仍沿用原始发起方铃声 |
| 1v1 关系门禁 | `user/follow_edge/service.yaml` 的 capability API | 用户主页、ChatDetail 输入区、rtc-service 校验 | `互相关注 = 互关`；不允许业务代码自行维护第二份关系判断表 |
| 发起方铃声资料 | `user/user_profile/fields.yaml` 中 `Persona.callerRingtoneId` | 子账号设置页、rtc-service 发起通话时读取 | 发起通话主体是子账号，因此铃声归属到 Persona，而非 Owner 级 UserProfile |
| 被叫来电偏好 | `user/user_profile/fields.yaml` 中 `UserSetting` 来电字段 + `service.yaml` 的 `Get/UpdateCallSettings` | 来电设置页、notification-service、CallKit/FullScreen 解析 | 包含默认铃声、是否允许发起方铃声覆盖、群邀请是否响铃、是否振动 |
| 官方铃声库目录 | 端侧内置资产清单（后续 `assets/rtc/` 资产 manifest） | 设置页列表、来电播放解析、本地试听 | 不走用户上传，不走远端 URL，不在 UI 或业务代码中硬编码散落字符串 |
| 路由 / page path | 现有 `AppRoutePaths.rtc*` + 既有 router metadata 产物 | `app_router.dart` / 页面跳转 | 本轮不新增业务路由模板，不新增 route override 表 |

**约束**：
- 不新增“静默邀请”“仅消息通知”之类代码开关，群邀请模式在产品规则上固定为“仅响铃邀请”
- 不在 UI / Repository / CallKit 适配层手写铃声业务规则；铃声解析顺序由 `Persona + UserSetting + 官方资产目录` 三方共同决定
- 不为官方铃声库额外新建独立聚合；第一阶段视为端侧受控资产目录，服务端仅保存 ringtoneId

## TDD / ATDD 策略

- **ATDD 基线**：以 `acceptance.yaml` 新增的 A52~A56 为本轮体验补齐的主驱动，先定义“响铃邀请 / 发起方铃声 / 跨群拉人 / 蓝色通话条 / 本地调试剧本”的验收证据，再进入实现
- **TDD 顺序**：
  1. metadata Red：新增 `Persona.callerRingtoneId`、`UserSetting` 来电偏好、`CallSession.initiatorRingtoneId` 后先跑 `make verify-metadata`
  2. codegen Red：`make codegen && make codegen-app` 失败即先修元数据，不直接手改生成物
  3. app/service Red：先补 DTO / Repository / 错误码 / 页面测试骨架，再实现业务逻辑
  4. Green：打通 user-service 设置、rtc-service 快照与 CallKit/FullScreen 解析
  5. Refactor：统一蓝色视觉、清理记录绿色语义和调试开关泄漏
- **本轮新增优先失败测试**：
  - local_contract：来电偏好 DTO / 错误码 / `initiatorRingtoneId` round-trip
  - local_contract：Incoming/Outgoing/ActiveCallBar 的品牌蓝与开发态入口显示约束
  - api_integration：rtc-service 发起通话时快照 initiator 铃声、群邀请保持 initiator 归属
  - user_acceptance：前台 / 后台 / 锁屏来电旅程，发起方铃声覆盖与默认铃声回退

## 角色职责与多重防护网

- **产品**：冻结群邀请仅响铃、蓝色品牌主色、互相关注门禁、多来源选人和铃声归属规则
- **架构**：决定 ringtoneId 的 metadata 承载位、CallSession 快照策略、CallKit/FullScreen 唤醒分层与灰度指标
- **开发**：按 `metadata → codegen → Red → Green → Refactor` 实施，禁止绕过 metadata 手写接口常量
- **测试**：覆盖 三层测试，特别是锁屏唤醒、群邀请铃声归属、跨群拉人和开发态调试剧本隔离
- **发布**：分阶段灰度，新增监控“来电唤醒成功率”“发起方铃声解析成功率”“默认铃声回退率”
- **防护网**：
  - 需求防漏：A52~A56 覆盖本轮新增体验规则
  - 方案防偏：CallSession 快照 initiatorRingtoneId，避免邀请链改变铃声来源
  - 测试防回归：开发态入口必须仅在 debug 构建可见
  - 发布防事故：铃声解析失败统一回退默认铃声，不阻断接听

## 实时性与弱网设计

- **一致性模型**：
  - 来电铃声来源采用“发起时快照”模型：`InitiateCall` 时读取发起方 `callerRingtoneId` 并写入 `CallSession.initiatorRingtoneId`
  - 后续 `InviteToCall`、重放来电、离线 Push 统一消费快照值，避免因发起方中途改铃声造成同一通话前后不一致
- **顺序性**：
  - `CallInitiated` 先于 `CallRinging`
  - notification-service / realtime-gateway 推送时必须优先使用 `CallSession.initiatorRingtoneId`
- **幂等与重试**：
  - 铃声解析失败不影响来电主流程，按“发起方铃声 → 默认铃声 → 系统铃声”降级
  - CallKit / FullScreen Intent 若指定铃声失败，必须自动回退，不重试阻塞主线程
- **断线恢复**：
  - 重连期间不重复弹出新的响铃 UI，除非是新的 `callId`
  - 本地调试剧本的“5 秒自动接通”只作用于 debug 构建，不参与正式信令逻辑
- **弱网降级**：
  - 响铃阶段 payload 保持极小，仅携带 `callId/callType/initiatorId/initiatorRingtoneId` 等必要字段
  - 弱网或离线场景优先保证来电提示和接听成功，不以加载大头像/附加信息阻塞响铃

## 并发性能与容量设计

- `initiatorRingtoneId` 采用通话创建时一次读取 + 会话内快照，避免每次邀请 / 推送都回查 user-service
- user-service 的来电偏好读取走 `UserSetting` 主键查询 + 现有缓存，不引入新热点维表
- notification-service 只消费 ringtoneId，不下发完整媒体资源；铃声资源由端侧本地资产目录解析
- 官方铃声库第一阶段保持小规模受控集合（例如 8~16 个），避免端侧资产膨胀和平台适配复杂度
- 观测指标新增：
  - `incoming_call_wake_success_rate`
  - `caller_ringtone_override_hit_rate`
  - `caller_ringtone_fallback_rate`
  - `group_call_ring_delivery_latency`

## 灰度发布与回滚设计

- **灰度步进**：沿用 KD-16 的 dev → integration → prod 5% → 20% → 50% → 100%
- **新增观测项**：
  - 发起方铃声命中率 ≥ 95%
  - 默认铃声回退率 ≤ 5%
  - 来电唤醒成功率（前台 / 后台 / 锁屏分层）≥ 98%
  - 群邀请接听成功率与现有 1v1 基线相比无显著回退
- **自动回滚条件**：
  - 指定铃声导致 CallKit / FullScreen Intent 唤起失败率异常升高
  - debug 入口误出现在 release 构建
  - 群邀请因响铃策略变更导致通知投诉或拒接率异常
- **人工回滚兜底**：
  - 关闭“允许发起方铃声覆盖”服务端开关，仅保留默认铃声
  - 保持群邀请仍为响铃模式，但在极端情况下退回默认铃声策略，不回退唤醒模式

## Story 与测试层映射

| L4 Story | local_contract 契约 | local_contract 模块 | api_integration 集成 | user_acceptance 旅程 |
|----------|---------|---------|---------|---------|
| call-lifecycle-contract | DTO/Error/Repository codegen 契约 | OutgoingCall+IncomingCall+VoiceCall+VideoCall 页面 | 全状态机+事件发布+超时+来电推送 | 1v1 语音/视频/来电/拒绝/超时旅程 |
| multi-party-room-contract | 同上（多人字段扩展） | 网格布局+演讲者视图+参与者面板 | Join/Leave/Invite+32人上限+SFU 基准 | 多人加入/离开旅程+群聊/圈子入口 |
| call-ui-interaction | 视觉语义合规 | 控制栏+PiP+通话条+质量指示+音频路由 | 弱网 Simulcast 降质+ICE 重连 | PiP 旅程+屏幕共享旅程 |
| sfu-deployment-contract | metadata 零偏差 | — | 500 并发基准+32人满房基准+弱网模拟 | 灰度 5%→100%+延迟+中断率+崩溃率 |

## 与关系治理特性的协作

| 特性 | 本设计消费 | 本设计输出 |
|------|-----------|-----------|
| contact-and-session-governance | `relationState`、`canStartVoiceCall`、`canStartVideoCall`、请求箱/正式会话边界 | 1v1 通话门禁与错误码、会话内加互相关注后的入口解锁 |
| group-settings | 群设置不承载发起/治理动作 | 群聊通话入口固定为输入区 `+` 面板 |

## 未来演进

1. **P2P 优先模式**（触发：DAU > 100K 且 SFU 带宽成本超预算）—— 1v1 先尝试 P2P，失败回退 SFU
2. **SFU 多节点分级**（触发：跨区域用户占比 >30%）—— Master SFU + 区域 Sub SFU
3. **虚拟背景 + AI 美颜**（触发：Phase 4 完成后）—— 端侧 ML 模型 + GPU 推理
4. **直播推流**（触发：圈子活动需求）—— LiveKit RTMP Egress
5. **实时字幕/翻译**（触发：国际化需求）—— ASR + NMT 管道
6. **Web 端通话**（触发：Web 产品规划确定）—— WebRTC 浏览器兼容 + 独立信令
7. **超 32 人大型会议**（触发：企业/教育场景）—— SFU 分级 + 仅音频 + 举手发言

## 存量带规划任务

- P2P 优先模式：需端侧 ICE 全流程 + 媒体路径切换逻辑（重启条件：SFU 成本超预算）
- Web 端通话：需 WebRTC 浏览器兼容层 + 独立 Web SDK（重启条件：Web 产品规划确定）
- PSTN 电话互通：需运营商合作 + SIP 网关（重启条件：业务需求明确 + 合作方就绪）

## 商用上线实现拆解（REV-5 落地顺序）

本节是 `/dev` 阶段的实现真相源，按依赖顺序排列，每项可独立验证。已完成项标注 [done]。

### S0 端云信令对齐（已落地）

- [done] Go application 层新增 `signal_wire_type.go`：domain event 常量 → events.yaml `client_ws_type` 薄映射；`call_orchestrator.publishEvent` WS 推送使用 wire type（`call.ringing` 等），事件存储仍用 domain 名。
- [done] `signal_wire_type_test.go` 契约测试断言映射与 events.yaml 完全一致，禁止漂移。
- 后续可选：把该映射纳入 Go codegen（消费 events.yaml `client_ws_type`），届时删除手写表并保留契约测试。

### S1 metadata → codegen（前置）

- [done] fields.yaml 新增 `displayName/avatarUrl/trustRelation/sourceLabel/isKnownContact/mutualContext/inviteStatus/invitedBy/connectionQuality/isSpeaking`；`_shared/types.yaml` 注册 `TrustRelation/CallInviteStatus/ConnectionQuality`；events.yaml CallRinging 补三端推送负载契约。
- 待执行：`make codegen` / `make codegen-app` 重生成 Go struct 与 Dart DTO；`make verify-metadata` 已通过。

### S2 参与者与轨道绑定（端侧根因修复）

- `LiveKitRoomService` 已提供 `remoteParticipants`/`localParticipant`/`onParticipantsChanged`/`activeSpeaker`/`connectionQuality`。
- `CallParticipant` VM 增加可空 LiveKit `VideoTrack` 引用与 `connectionQuality`/`trustRelation` 字段（不进 `==`/`hashCode` 的内容比较，仅用于渲染）。
- `call_session_provider._connectToLiveKit` 的 `onParticipantsChanged.listen` 把 LiveKit 远端+本地 participant 与已订阅 track 同步进 `callParticipantsProvider`（合并 DTO 元信息与实时媒体态），`activeSpeaker` 写入 `activeSpeakerId`。
- `participant_tile` 渲染真实 `VideoTrackRenderer`；无 track/关摄像头时显示头像占位与弱网/静音角标。

### S3 设备控制接真实 SFU

- `CallControlsBar` 翻转摄像头改调 `LiveKitRoomService.switchCamera()`，音频输出改调 `setSpeakerOn()`，移除只改本地态的旁路；静音/摄像头沿用 provider→LiveKit 既有链路。

### S4 全局挂载与生命周期

- app shell 唯一入口（`web_main_app_shell` / 对应原生 shell）override `goRouterProvider` 并在登录态启动 `IncomingCallCoordinator`；挂载 `ActiveCallBar`（顶部通话条）与 `PipCallOverlay`（返回 PiP），覆盖来电、返回回流、后台恢复。

### S5 通话页过程态与选人页重做

- `video_call_page` 补连接中/振铃/单人等待/对方未接/已离开/重连中/弱网/已结束过程态与空态；顶部信息条含来源/时长/质量/信任摘要。
- `call_participant_picker_page` 补来源切换说明、信任风险徽标、邀请预览、超员/重复/部分失败反馈；硬编码中文迁 `UITextConstants`/l10n。

### S6 来电三端与权限

- iOS PushKit+CallKit（收到即上报来电）、Android FCM 高优先级+全屏意图（含 14+ 权限降级）、Web Push+Service Worker+Notification 点击进会。
- `PlatformCapabilities` 补 `incomingCallUi`/`webPushIncomingCall`/`realtimeCommunication`，UI 只读能力位；权限统一权限卡片与仅语音降级。

### S7 错误码/文案治理

- Dart `RtcErrorCode` 补 `not_mutual`/`blocked`（metadata→codegen）；`'answerCall: empty session'`/`REC`/教育文案改结构化错误与 `UITextConstants`/l10n。
