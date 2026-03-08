# 实时音视频通话 设计方案

## 设计动因

spec.md 定义了 32 人实时音视频通话端到端闭环，核心设计挑战：
- 信令协议与 realtime-gateway 的关系
- LiveKit SFU 自部署与 rtc-service 的职责边界
- 32 人 Simulcast 带宽/CPU/内存预算
- 7 种动态网格布局算法（对标 FaceTime）
- 弱网 6 级对抗与自适应降质策略
- 呼叫状态机的端云一致性
- 来电推送（在线 WS + 离线 VoIP Push + 锁屏 CallKit）
- 录制 (Egress) 与屏幕共享的生命周期管理
- 灰度发布自动回滚门禁

## 上游输入评审

- spec.md 功能 17 条（F1~F17 分 4 Phase），约束覆盖弱网/并发/实时/部署，完整可执行
- acceptance.yaml A1~A43 全部可测量，T1~T4 金字塔覆盖
- 前置依赖 realtime-gateway 已有完整 spec（L2），可并行或串行推进
- **无阻断项**

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

rtc-service 自建 `/v1/rtc/signal` WebSocket 端点，独立维护信令连接。

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
- **Phase 1（MVP）**：rtc-service 内建最小 WS 信令端点 `/v1/rtc/signal`，仅承担来电推送和通话状态同步。离线唤醒通过 FCM/APNs VoIP Push。
- **Phase 2（演进）**：realtime-gateway 就绪后，迁移信令到统一通道，rtc-service WS 下线。

**降级范围**：仅信令投递路径变更，呼叫状态机（KD-1）、SFU 选型、媒体策略、布局算法等决策不变。

### REV-2（2026-03-08）：AnswerCall 契约统一

**背景**：`service.yaml` 定义 AnswerCall 返回 `[token, roomId]`，但实现仅返回 session。

**决策变更**：AnswerCall 统一返回 `{session, token, roomId}`，接听方无需再调 JoinCall 获取 token。

## 选型决策

| 决策 | 选定 | 理由 |
|------|------|------|
| 信令通道 | **Phase 1: rtc-service 内建 WS（REV-1）；Phase 2: 迁移到 realtime-gateway** | realtime-gateway 未就绪，先用最小 WS 打通来电推送 |
| SFU 引擎 | **方案 A：LiveKit 自部署** | 生产就绪、Flutter SDK、Egress/E2EE 内置、开源可 fork |
| 1v1 媒体策略 | **方案 A：统一 SFU** | 架构简单一致、满足 ≤200ms 延迟、录制统一 |
| 网格布局 | **方案 A：FaceTime 式动态等分** | 对标一流体验、布局稳定可预期、32 人可扩展 |
| 播放引擎（端侧） | **livekit_client (Flutter)** | LiveKit 官方 Flutter SDK，内置 WebRTC 管理 |
| 来电组件（端侧） | **flutter_callkit_incoming** | iOS CallKit + Android FullScreen 统一 |

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
  │ POST /v1/rtc/    │                  │                  │                │
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
│   └── active_call_bar.dart              # 顶部绿色通话条
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
- 语音通话切后台：不显示 PiP，仅顶部绿色通话条

**顶部绿色通话条**：
```
┌──────────────────────────────────────────┐
│ 🟢 通话中  02:34  点击返回               │  ← 绿色背景，高 28pt
└──────────────────────────────────────────┘
```
- 固定在状态栏下方
- 显示通话时长实时计时
- 点击返回通话全屏

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

### KD-13: 灰度发布策略（已定）

```
Phase 1: dev 全量
├── make gate 全部通过
├── 手动验证：1v1 语音/视频 + 来电 + 挂断 + 超时
└── 通过 → 进入 integration

Phase 2: integration 全量
├── T1~T3 全量自动化测试通过
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

## Story 与测试层映射

| L4 Story | T1 契约 | T2 模块 | T3 集成 | T4 旅程 |
|----------|---------|---------|---------|---------|
| call-lifecycle-contract | DTO/Error/Repository codegen 契约 | OutgoingCall+IncomingCall+VoiceCall+VideoCall 页面 | 全状态机+事件发布+超时+来电推送 | 1v1 语音/视频/来电/拒绝/超时旅程 |
| multi-party-room-contract | 同上（多人字段扩展） | 网格布局+演讲者视图+参与者面板 | Join/Leave/Invite+32人上限+SFU 基准 | 多人加入/离开旅程+群聊/圈子入口 |
| call-ui-interaction | 视觉语义合规 | 控制栏+PiP+通话条+质量指示+音频路由 | 弱网 Simulcast 降质+ICE 重连 | PiP 旅程+屏幕共享旅程 |
| sfu-deployment-contract | metadata 零偏差 | — | 500 并发基准+32人满房基准+弱网模拟 | 灰度 5%→100%+延迟+中断率+崩溃率 |

## 未来演进

1. **P2P 优先模式**（触发：DAU > 100K 且 SFU 带宽成本超预算）—— 1v1 先尝试 P2P，失败回退 SFU
2. **SFU 多节点分级**（触发：跨区域用户占比 >30%）—— Master SFU + 区域 Sub SFU
3. **虚拟背景 + AI 美颜**（触发：Phase 4 完成后）—— 端侧 ML 模型 + GPU 推理
4. **直播推流**（触发：圈子活动需求）—— LiveKit RTMP Egress
5. **实时字幕/翻译**（触发：国际化需求）—— ASR + NMT 管道
6. **Web 端通话**（触发：Web 产品规划确定）—— WebRTC 浏览器兼容 + 独立信令
7. **超 32 人大型会议**（触发：企业/教育场景）—— SFU 分级 + 仅音频 + 举手发言

## 遗留带规划任务

- P2P 优先模式：需端侧 ICE 全流程 + 媒体路径切换逻辑（重启条件：SFU 成本超预算）
- Web 端通话：需 WebRTC 浏览器兼容层 + 独立 Web SDK（重启条件：Web 产品规划确定）
- PSTN 电话互通：需运营商合作 + SIP 网关（重启条件：业务需求明确 + 合作方就绪）
