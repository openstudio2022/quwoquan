# 消息交互体验增强 设计方案

## 设计动因

spec.md 指出趣聊消息交互存在 5 个体验缺口：引用回复无 UI、@提及无高亮、语音无听筒/倍速、会话列表数据源不统一、InboxService 未暴露 HTTP。本设计解决这些 P1 级体验问题，对齐微信商用基线。

## 上游输入评审

- **spec.md**：F1~F5 清晰，约束完备
- **acceptance.yaml**：E-A1~E-A12 可测量
- **阻断项**：无。`replyToMessageId` 和 `mentions` 字段已在 fields.yaml 中定义，metadata 无需变更
- **补充项**：InboxService HTTP 路由需新增到 service.yaml（已在 realtime-push metadata 任务中合并处理）

## 方案对比

### 方案对比 1：引用回复气泡布局

#### 方案 A：气泡内嵌引用块（选定）

在消息气泡 Widget 内部顶部嵌入引用块（灰色背景 + 蓝色竖线 + 被引用消息摘要）。

**优点**：与微信/Telegram 一致的成熟交互；引用上下文和消息内容在同一视觉单元；信息密度高
**缺点**：气泡高度增加；需处理引用块中不同消息类型的缩略展示

#### 方案 B：独立引用指示器（消息外）

在消息气泡上方显示一个小型引用链接（如 "回复 @张三"），点击跳转。

**优点**：不影响气泡高度
**缺点**：引用上下文与消息割裂；信息密度低；非主流交互模式

**选定方案 A**。理由：微信/Telegram 已验证该模式的用户认知成本最低。

### 方案对比 2：@提及文本渲染

#### 方案 A：TextSpan 富文本（选定）

使用 `Text.rich(TextSpan(...))` 将 `@用户名` 渲染为蓝色 `WidgetSpan`/`TextSpan`，支持点击事件。

**优点**：Flutter 原生方案，性能好；可精确控制颜色和点击区域；与 `SelectableText.rich()` 兼容
**缺点**：需解析消息文本中的 `@` 位置并映射到 `mentions` 数组

#### 方案 B：Markdown 风格替换

将 `@用户名` 替换为 Markdown 链接 `[@用户名](user://userId)` 后用 `flutter_markdown` 渲染。

**优点**：渲染逻辑简单
**缺点**：引入 Markdown 渲染器到普通文本消息，性能开销大；气泡样式难以统一

**选定方案 A**。理由：性能更优，与现有文本气泡兼容。

### 方案对比 3：距离传感器库

#### 方案 A：`proximity_sensor` + `audio_session`（选定）

`proximity_sensor` 监听距离传感器事件，`audio_session`（已依赖）切换音频输出路由。

**优点**：`audio_session` 已在 voice-message 中使用；`proximity_sensor` 轻量且专注
**缺点**：需在播放时激活传感器监听，非播放时停止（节省电量）

#### 方案 B：`sensors_plus` 套件

使用 Flutter 社区的 `sensors_plus` 获取距离传感器数据。

**优点**：功能全（加速度/陀螺仪/距离等）
**缺点**：包体积更大（包含不需要的传感器）；距离传感器 API 在某些 Android 设备上不稳定

**选定方案 A**。

## 选型决策

| 决策 | 选定 | 理由 |
|------|------|------|
| 引用回复布局 | 气泡内嵌引用块 | 微信/Telegram 验证的成熟模式 |
| @提及渲染 | TextSpan 富文本 | 原生性能，与现有气泡兼容 |
| 距离传感器 | `proximity_sensor` | 轻量专注 |
| 音频输出切换 | `audio_session`（已有） | 无需新增依赖 |
| 倍速播放 | `just_audio.setSpeed()`（已有） | 无需新增依赖 |

## 关键设计决策

### KD-1: 引用回复 Widget 结构（已定）

```dart
class QuoteReplyBlock extends StatelessWidget {
    final MessageDto? quotedMessage;  // 被引用消息（可能为 null = 已删除）

    // 布局：
    // ┌─────────────────────────────────────┐
    // │ 🔵│ 张三                             │ ← 蓝色竖线 + 被引用者名称
    // │   │ 消息摘要文本（截断80字）...       │ ← 摘要（按类型展示）
    // ├─────────────────────────────────────┤
    // │ 当前消息内容                          │ ← 正常气泡内容
    // └─────────────────────────────────────┘
}
```

摘要按类型展示：
| 类型 | 摘要格式 |
|------|---------|
| text | 文字截断 80 字 |
| image | `[图片]` + 缩略图 |
| audio | `[语音] 0:15` |
| video | `[视频]` + 缩略图 |
| file | `[文件] xxx.pdf` |
| 已删除/撤回 | `原消息已删除`（灰色） |

### KD-2: @提及解析算法（已定）

```dart
List<InlineSpan> parseMentions(String text, List<String> mentions) {
    // 1. 用正则匹配 text 中所有 @xxx 片段
    // 2. 对每个匹配，检查 mentions 数组中是否有对应 userId
    // 3. 有 → 蓝色 TextSpan + GestureRecognizer（点击跳转用户主页）
    // 4. 无 → 普通 TextSpan
    // 5. @所有人（__all__）→ 蓝色，无点击事件
}
```

### KD-3: @成员选择器（已定）

```dart
class MentionMemberPicker extends StatelessWidget {
    // 触发：输入框检测到 '@' 字符
    // UI：从底部弹出的 ListView（最近联系人 ≤50 + 搜索过滤）
    // 选择后：插入 "@用户名 " 到输入框（蓝色文本 + 尾部空格）
    // 数据源：ChatRepository.listMembers(conversationId)
}
```

### KD-4: 语音听筒/扬声器切换（已定）

```dart
class VoicePlaybackController {
    ProximitySensorSubscription? _proxSub;
    AudioOutputMode _preferredMode = AudioOutputMode.speaker;

    void onPlayStart() {
        // 激活传感器监听
        _proxSub = ProximitySensor.events.listen((close) {
            if (close) _switchToEarpiece();
            else _switchToSpeaker();
        });
    }

    void onPlayStop() {
        // 停止传感器（省电）
        _proxSub?.cancel();
    }

    void _switchToEarpiece() {
        AudioSession.instance.then((s) =>
            s.setCategory(AudioSessionCategory.playAndRecord,
                          mode: AudioSessionMode.voiceChat));
    }
}
```

偏好持久化到 `SharedPreferences`（key: `voice_playback_mode`）。

### KD-5: 倍速控制 UI（已定）

```dart
// 在 VoiceMessageBubble 播放状态下显示倍速按钮
// 点击循环：1x → 1.5x → 2x → 0.5x → 1x
// 使用 just_audio 的 player.setSpeed(speed)
// 倍速偏好存储在 ChatMessageNotifier 中（per-session）
```

### KD-6: 数据源统一迁移策略（已定）

```dart
// 迁移前：ChatPage 混用 ChatRepository + appContentRepository
// 迁移后：统一使用 chatRepositoryProvider

// 步骤：
// 1. 确认 ChatRepository.listConversations() 返回与 appContentRepository 相同的数据结构
// 2. 移除 ChatPage 中对 appContentRepository 的调用
// 3. 切换到 chatRepositoryProvider（已注册）
// 4. 验证 Mock/Remote 模式下列表内容一致
```

## TDD / ATDD 策略

1. **E-A1~A3 先行**：先写引用回复 Widget 测试（T2），验证气泡内引用块渲染
2. **E-A4~A5 TDD**：先写 @提及 Widget 测试，验证蓝色高亮和选择器
3. **E-A6~A9**：语音增强测试（听筒切换、倍速）
4. **E-A10~A11**：数据源和 Inbox 集成测试

## Story 与测试层映射

| L4 Story | T1 契约 | T2 模块 | T3 集成 | T4 旅程 |
|----------|---------|---------|---------|---------|
| quote-reply-display | replyToMessageId 序列化 | 引用块 Widget + 输入栏引用预览 | SendMessage(replyTo)+Sync 联调 | 回复→接收→点击跳转旅程 |
| mention-highlight-and-picker | mentions 数组序列化 | @高亮 TextSpan + 成员选择器 | SendMessage(mentions)+Sync 联调 | @成员→接收→高亮可见旅程 |
| voice-earpiece-and-speed | — | 传感器切换 + 倍速按钮 Widget | — | 贴耳播放→远离恢复旅程 |
| inbox-data-source-unification | Inbox HTTP 契约 | ChatPage 数据源 Widget | Inbox API 端云联调 | 会话列表一致性旅程 |

## 实时性与弱网设计

本特性不涉及核心实时链路变更。引用回复和 @提及的实时展示依赖 `realtime-push-and-offline-sync` 提供的 WebSocket 推送通道。

## 灰度发布与回滚设计

- **Phase 1**: integration 全量（E-A1~E-A11 全部 implemented）
- **Phase 2**: prod 10%→50%→100%
- **回滚条件**：引用回复渲染崩溃率 >0.1% 或语音播放异常率 >1%

## 未来演进

| 演进项 | 触发条件 |
|--------|---------|
| 消息反应（Emoji 回复/点赞） | 社交互动增强迭代 |
| 消息转发（单条/合并） | 消息转发特性启动 |
| 连续语音播放 | 用户反馈需求 |
| 语音转文字（ASR） | 供应商对接 |
