# 语音消息 设计方案

## 设计动因

spec.md 要求实现语音消息端到端闭环（录音→上传→发送→推送→接收→播放），覆盖弱网、离线、并发等边界场景。核心设计挑战：消息模型如何可扩展地支持多媒体类型、弱网条件下如何保证可靠性、端侧如何管理录音/播放/缓存的生命周期。

## 上游输入评审

- spec.md 功能范围 12 条明确，约束完整（弱网/并发/实时/部署）
- acceptance.yaml A1-A12 全部可测量，T1-T4 金字塔覆盖
- 依赖 runtime-media 已在并行设计中
- 无阻断项

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 差距 |
|------|------|--------|------|
| 微信 | 按住/松手/上滑取消；气泡宽度正比时长；听筒切换 | AMR/Silk 编码(用 AAC)；60s 限制(用 120s) | 交互范式可直接对标 |
| Telegram | 精美波形动画；速度调节 | 圆形语音消息外观 | 波形参考，速度后续 |
| Discord | 实时波形渲染 | 过于复杂的渲染 | 参考其波形算法 |
| WhatsApp | 离线队列+自动重传 | 端到端加密复杂度 | 离线策略参考 |

## 方案对比

### 方案对比 1：消息媒体模型

#### 方案 A：仅用 mediaUrl + metadata（松散 object）

在现有 `mediaUrl`（单字符串）和 `metadata`（任意 JSON）中存储所有媒体信息。

**优点**：零 metadata 变更，立即可用
**缺点**：无类型约束，端云解析逻辑散落各处；`mediaUrl` 语义模糊（图片 URL？视频 URL？音频 URL？）；多图场景无法扩展
**适用条件**：极度紧急的原型验证

#### 方案 B：新增结构化 media 字段（选定）

Message 实体新增 `media`（object, NULLABLE）字段，约定 schema（url/mimeType/durationMs/waveform/width/height/fileSizeBytes/codec/fileName/thumbnailUrl/items[]）。保留 `mediaUrl` 向后兼容。

**优点**：类型化、可扩展、端云一致；支持多图（items[]）；单字段包含全部媒体元数据
**缺点**：需 metadata 变更 + codegen；需处理向后兼容（旧客户端仅有 mediaUrl）
**适用条件**：需要长期维护的多媒体消息系统

### 方案对比 2：实时推送

#### 方案 A：HTTP 轮询（Phase 1 选定）

使用现有 `syncMessages(lastSeq)` 做增量同步，轮询间隔 5 秒。

**优点**：零基础设施依赖，即刻可用
**缺点**：接收延迟 ≤8 秒（含轮询间隔）；耗电；带宽浪费
**适用条件**：realtime-gateway 未就绪期间的降级方案

#### 方案 B：WebSocket 实时推送（Phase 2 目标）

通过 realtime-gateway WebSocket 推送 MessageSent 事件。

**优点**：延迟 <500ms；省电；省带宽
**缺点**：依赖 realtime-gateway（未实现）；需维护长连接
**适用条件**：realtime-gateway 就绪后

### 方案对比 3：录音引擎

#### 方案 A：`record` 包（选定）

Flutter 社区 `record` 包，支持 AAC/WAV 编码，iOS/Android 双端。

**优点**：轻量、API 简洁、AAC 原生支持、主动维护
**缺点**：波形数据需自行采集（通过 amplitude 回调）
**适用条件**：标准录音需求

#### 方案 B：`flutter_sound` 包

更全面的音频处理框架。

**优点**：功能更丰富（录音+播放+格式转换一体）
**缺点**：包体积大、API 复杂、维护不够活跃
**适用条件**：需要复杂音频处理的场景

## 选型决策

| 决策 | 选定 | 理由 |
|------|------|------|
| 消息媒体模型 | **方案 B：结构化 media 字段** | 长期可维护、可扩展、类型安全 |
| 实时推送 | **Phase 1: 方案 A（HTTP 轮询），Phase 2: 方案 B（WebSocket）** | 不阻塞在 realtime-gateway 上 |
| 录音引擎 | **方案 A：record 包** | 轻量、AAC 原生、社区活跃 |
| 播放引擎 | **just_audio** | 流式播放、进度回调、速度控制、iOS/Android |
| 音频会话 | **audio_session** | 听筒/扬声器切换、中断管理 |

## 关键设计决策

### KD-1: Message.media Schema（已定）

```json
{
  "url": "https://cdn.../abc.m4a",
  "mediaId": "mid_xxx",
  "mimeType": "audio/aac",
  "fileSizeBytes": 38400,
  "durationMs": 5200,
  "waveform": [0.3, 0.7, 0.5, ...],
  "codec": "aac",
  "thumbnailUrl": null,
  "width": null,
  "height": null,
  "fileName": null,
  "items": null
}
```

按消息类型使用不同字段组合：
- `audio`: url, mimeType, durationMs, waveform, codec, fileSizeBytes
- `image`: url, mimeType, width, height, thumbnailUrl, fileSizeBytes
- `video`: url, mimeType, width, height, durationMs, thumbnailUrl, fileSizeBytes
- `file`: url, mimeType, fileSizeBytes, fileName

### KD-2: 向后兼容策略（已定）

- 发送时同时写入 `mediaUrl`（=media.url）和 `media` 对象
- 旧客户端读 `mediaUrl` 可展示占位（如 "[语音消息]"）
- 新客户端优先读 `media` 对象，fallback 到 `mediaUrl`

### KD-3: MessageType 枚举扩展（已定）

```yaml
MessageType: [text, image, video, audio, file, card, system, assistant_reply]
```

新增 `audio`（语音消息）和 `file`（文件消息预留）。

### KD-4: 录音交互状态机（已定）

```
                         ┌─────────────┐
                         │    Idle      │
                         └──────┬──────┘
                                │ longPress
                         ┌──────▼──────┐
                    ┌────│  Recording   │────┐
                    │    └──────┬──────┘    │
                    │           │            │
               swipeUp     release      timeout(120s)
                    │           │            │
             ┌──────▼──┐ ┌─────▼─────┐ ┌───▼───────┐
             │Cancelled │ │ Uploading │ │ Uploading │
             └──────────┘ └─────┬─────┘ └───┬───────┘
                                │            │
                           ┌────▼────────────▼────┐
                           │       Sending         │
                           └────────┬──────────────┘
                                    │
                              ┌─────▼─────┐
                              │    Sent    │
                              └───────────┘
```

recording < 1s + release → 丢弃（Toast "录音时间太短"）

### KD-5: 语音气泡宽度算法（已定）

```dart
double bubbleWidth(int durationMs, double screenWidth) {
  const minRatio = 0.25;
  const maxRatio = 0.70;
  const minDuration = 1000;
  const maxDuration = 120000;
  final ratio = minRatio + (maxRatio - minRatio) *
      ((durationMs - minDuration).clamp(0, maxDuration - minDuration) /
       (maxDuration - minDuration));
  return screenWidth * ratio;
}
```

### KD-6: 波形数据采集（已定）

- 录音时每 50ms 采集一次振幅（record 包 `onAmplitudeChanged`）
- 录音结束后下采样为 50-100 个数据点（取决于时长）
- 归一化到 [0.0, 1.0] 范围
- 存入 `media.waveform` 数组

### KD-7: 播放器生命周期管理（已定）

- 全局单例 `VoicePlayerManager`（Riverpod Provider）
- 维护当前播放的 messageId + AudioPlayer 实例
- 点击新语音：停止旧播放 → 下载/缓存 → 开始新播放
- 页面退出：自动停止播放
- 来电中断：自动暂停（不自动恢复）

### KD-8: 离线语音队列设计（已定）

```
Hive Box: 'voice_offline_queue'
Schema:
  - localPath: String          # 本地音频文件路径
  - conversationId: String     # 目标会话
  - clientMsgId: String        # 幂等 ID
  - durationMs: int            # 时长
  - waveform: List<double>     # 波形
  - createdAt: DateTime        # 录音时间
  - status: String             # pending | uploading | failed
  - retryCount: int            # 已重试次数
```

NetworkConnectivity 监听网络恢复 → 取 status=pending/failed(retryCount<3) 的任务 → FIFO 上传+发送。

### KD-9: 弱网策略矩阵（已定）

| 网络状态 | 检测方式 | 上传策略 | 播放策略 | UI 反馈 |
|----------|---------|---------|---------|---------|
| 强网(WiFi/4G) | ConnectivityResult + 带宽估算 | 正常上传 30s 超时 | 流式播放即时起播 | 无特殊提示 |
| 弱网(2G/3G) | 带宽 <200kbps | 超时延长 120s + 重试 3 次 | 流式播放（可能有缓冲等待） | 上传进度条 |
| 极弱网(<50kbps) | 连续 3 次请求 >10s | 上传入离线队列 | 显示下载进度 + 30s 超时 | "网络不佳" 提示 |
| 断网 | ConnectivityResult.none | 入离线队列 | 仅缓存可播 | ⏳ 待发送 |

### KD-10: 灰度发布策略（已定）

```
Phase 1: integration 全量
├── 自动化测试全部通过（A1-A11）
├── 手动冒烟测试：录音/发送/播放/离线恢复
└── 持续 24h 无 P0/P1

Phase 2: prod 灰度 10%
├── 基于 userId hash 选取 10% 用户
├── 监控：audio 消息发送成功率 >99%、播放失败率 <0.5%、ANR 率 <0.1%
├── 持续 24h 达标

Phase 3: prod 灰度 50%
├── 扩大到 50% 用户
├── 同上监控指标
├── 持续 24h 达标

Phase 4: prod 全量 100%
├── 全量放开
├── 回滚条件：任一阶段 audio 发送失败率 >1% 或 ANR >0.1% 自动回滚
```

## 适用场景与约束

- **适用**：趣聊 1v1 私聊和群聊中的语音消息发送与接收
- **约束**：Phase 1 接收延迟受 HTTP 轮询限制（≤8s）；AAC 编码不支持极低码率（<16kbps 不建议）
- **局限**：不含 ASR 转文字、不含变速播放、不含连续播放

## Story 与测试层映射

| Story (L4) | T1 契约 | T2 模块 | T3 集成 | T4 旅程 |
|------------|---------|---------|---------|---------|
| voice-record-and-send | MessageType codegen + media 字段 codegen | 录音引擎+交互 Widget+上传+离线队列 | 强网/弱网发送延迟+可靠性 | 发送旅程+权限 |
| voice-playback-and-cache | 视觉语义合规 | 气泡 Widget+播放引擎+缓存+波形+音频会话 | 起播延迟+弱网流式+断网降级 | 播放旅程+列表性能+灰度 |

## 未来演进

1. **WebSocket 实时推送**（Phase 2）：realtime-gateway 就绪后接入，接收延迟从 ≤8s 降至 <500ms
2. **变速播放**：0.5x/1.5x/2x，just_audio 原生支持，UI 加速度按钮
3. **连续播放**：播完自动播下一条语音，VoicePlayerManager 维护播放队列
4. **语音转文字**：ASR 供应商对接后，发送时可选转文字，存入 `media.transcription`
5. **贴耳切换听筒**：distance sensor 检测，audio_session 路由切换
6. **多图消息**：复用 `media.items[]` 字段，Gallery 气泡
7. **视频消息**：复用 media 字段 + MediaUploadManager，视频气泡 + 播放器

## 遗留带规划任务

- 语音消息转发：需设计转发链路和权限（重启条件：社交功能迭代时）
- 群聊语音消息推送优化：大群 fanout 性能（重启条件：realtime-gateway 就绪后）
