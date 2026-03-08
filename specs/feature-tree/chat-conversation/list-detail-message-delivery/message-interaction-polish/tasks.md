# 消息交互体验增强 任务清单

> **顺序原则**：引用回复（最高用户价值）→ @提及 → 语音增强 → 数据源统一/Inbox

## 当前交付任务

### Story 1：引用回复（quote-reply-display）（E-A1, E-A2, E-A3）

- [ ] Q1: [Red] 编写 QuoteReplyBlock Widget 测试（T2，各消息类型摘要渲染、已删除消息处理）
- [ ] Q2: [Red] 编写输入栏引用预览 Widget 测试（T2，长按→回复→预览块显示→关闭）
- [ ] Q3: [Green] 创建 `QuoteReplyBlock` Widget（蓝色竖线 + 被引用者名称 + 类型化摘要）
- [ ] Q4: [Green] 在 `chat_message_bubble.dart` 中检测 `replyToMessageId`，有值时在气泡顶部嵌入 `QuoteReplyBlock`
- [ ] Q5: [Green] 获取被引用消息内容（从 ChatMessageNotifier 的消息列表中查找，或调用 API）
- [ ] Q6: [Green] 实现引用块点击跳转（滚动到被引用消息 + 高亮闪烁 2 次）
- [ ] Q7: [Green] 长按消息上下文菜单增加「回复」选项
- [ ] Q8: [Green] 输入栏引用预览组件（显示被回复消息摘要 + 关闭按钮）
- [ ] Q9: [Green] 发送时携带 `replyToMessageId` 到 `ChatMessageNotifier.sendMessage()`
- [ ] Q10: [Refactor] `verify_dart_semantic.py` 无新增硬编码

### Story 2：@提及（mention-highlight-and-picker）（E-A4, E-A5）

- [ ] M1: [Red] 编写 @提及 TextSpan 解析单元测试（T2，蓝色高亮、混合文本、@所有人）
- [ ] M2: [Red] 编写 MentionMemberPicker Widget 测试（T2，弹出/搜索/选择/插入）
- [ ] M3: [Green] 实现 `parseMentions()` 函数（文本 + mentions 数组 → List<InlineSpan>）
- [ ] M4: [Green] 在文本消息气泡中使用 `Text.rich()` 渲染带 @高亮的文本
- [ ] M5: [Green] 实现 @高亮点击（`GestureRecognizer` → 导航到用户主页）
- [ ] M6: [Green] 创建 `MentionMemberPicker`（底部弹出 ListView + 搜索过滤 + 群成员数据源）
- [ ] M7: [Green] 输入框 `@` 字符检测 → 弹出选择器 → 选中后插入蓝色 @用户名
- [ ] M8: [Green] 发送时解析输入框中的 @标记 → 填充 `mentions` 数组
- [ ] M9: [Green] @所有人（`__all__`）仅群主/管理员可触发
- [ ] M10: [Refactor] `verify_dart_semantic.py` 无新增硬编码

### Story 3：语音听筒/扬声器 + 倍速（voice-earpiece-and-speed）（E-A6, E-A7, E-A8, E-A9）

- [ ] V1: [依赖] 添加 `proximity_sensor` 到 pubspec.yaml
- [ ] V2: [Red] 编写距离传感器切换单元测试（T2，贴耳→听筒、远离→扬声器）
- [ ] V3: [Red] 编写倍速按钮 Widget 测试（T2，循环切换 1x→1.5x→2x→0.5x→1x）
- [ ] V4: [Green] 实现 `VoicePlaybackController`（距离传感器监听 + audio_session 切换）
- [ ] V5: [Green] 播放时激活传感器，停止时取消（省电）
- [ ] V6: [Green] 语音气泡长按菜单增加「听筒播放/扬声器播放」
- [ ] V7: [Green] 播放模式偏好持久化（SharedPreferences）
- [ ] V8: [Green] VoiceMessageBubble 播放态增加倍速标签按钮
- [ ] V9: [Green] 倍速切换调用 `just_audio.setSpeed()`（实时变速，不变调）
- [ ] V10: [Green] 倍速偏好 per-session 记忆（切换会话后重置 1x）

### Story 4：数据源统一 + InboxService（inbox-data-source-unification）（E-A10, E-A11）

- [ ] D1: [Red] 编写 ChatPage 数据源一致性 Widget 测试（T2，Mock/Remote 下列表内容一致）
- [ ] D2: [Red] 编写 InboxService HTTP 契约测试（T1，GET /v1/chat/inbox 返回正确结构）
- [ ] D3: [Green] 云侧：InboxService 挂载 `GET /v1/chat/inbox` HTTP 路由（cursor 分页，≤50 条）
- [ ] D4: [Green] 端侧：ChatPage 移除对 `appContentRepository` 的调用，统一使用 `chatRepositoryProvider`
- [ ] D5: [Green] 端侧：`ChatRepository.listConversations()` Remote 实现切换到调用 `/v1/chat/inbox`
- [ ] D6: [Green] 会话排序：`lastMessage.timestamp` 降序 + 置顶优先
- [ ] D7: [Refactor] 验证 Mock/Remote 切换无异常

### Phase 5：集成测试

- [ ] T1: [T3] 引用回复端云联调：sendMessage(replyToMessageId) → syncMessages → 引用块展示
- [ ] T2: [T3] @提及端云联调：sendMessage(mentions) → syncMessages → 蓝色高亮展示
- [ ] T3: [T3] Inbox API 端云联调：GET /v1/chat/inbox → 会话列表正确展示
- [ ] T4: [综合] 全量运行 `flutter test test/cloud/chat/ test/ui/chat/`，确保无回归

## 搁置任务（带规划）

- [ ] S1: 消息反应（Emoji 回复/点赞）（重启条件：社交互动增强迭代）
- [ ] S2: 消息转发（单条/合并）（重启条件：消息转发特性启动）
- [ ] S3: 连续语音播放（播完自动播下一条）（重启条件：用户反馈需求增长）
- [ ] S4: @提及推送增强（被 @ 时专属推送通道）（重启条件：notification-service 支持后）

## 未来演进任务

- [ ] E1: 语音转文字 ASR（供应商对接）
- [ ] E2: 自定义表情包系统（独立 L3 特性）
- [ ] E3: 消息搜索（端侧 SQLite FTS5，依赖本地持久化）
