# 语音消息 任务列表

## 当前交付任务

### metadata 变更
- [x] M1: [metadata] `_shared/types.yaml` — MessageType 枚举新增 `audio` 和 `file`
- [x] M2: [metadata] `messages/conversation/fields.yaml` — Message 实体新增 `media` 字段（type: object, NULLABLE）
- [x] M3: [metadata] `messages/conversation/service.yaml` — SendMessage writable_fields 新增 `media`
- [x] M4: [metadata] `messages/conversation/events.yaml` — MessageSent payload_fields 新增 `mediaUrl` 和 `media`

### codegen
- [x] C1: [codegen] `make verify-metadata` 通过
- [x] C2: [codegen] `make codegen` 通过 — 云侧 Message struct 含 media 字段，MessageType 含 Audio
- [x] C3: [codegen] `make codegen-app` 通过 — 端侧 MessageDto 含 media 字段

### 云侧业务逻辑
- [x] G1: [Go] chat-service handleSendMessage 支持 type=audio + media 字段写入
- [x] G2: [Go] chat-service MessageSent 事件 payload 包含 mediaUrl + media
- [x] G3: [Go] chat-service sendMessage 契约测试新增 audio 变体

### 端侧录音与发送（voice-record-and-send Story）
- [x] D1: [Dart] pubspec.yaml 新增依赖：record, just_audio, audio_session, connectivity_plus
- [x] D2: [Dart] 创建 `lib/ui/chat/widgets/voice/voice_recorder.dart` — 录音引擎封装（AAC/16kHz/波形采集）
- [x] D3: [Dart] 创建 `lib/ui/chat/widgets/voice/voice_record_overlay.dart` — 录音交互 UI（按住/松手/上滑取消/计时/波形）
- [x] D4: [Dart] 更新 `chat_detail_page.dart` — 替换现有 ASR 录音为真正语音消息流程
- [x] D5: [Dart] 创建 `lib/ui/chat/providers/voice_send_provider.dart` — 录音→上传→发送状态管理
- [x] D6: [Dart] 创建 `lib/ui/chat/providers/voice_offline_queue.dart` — Hive 离线队列 + 网络恢复自动重传
- [x] D7: [Dart] 更新 `SendMessageRequest` — 新增 media 字段
- [x] D8: [Dart] 更新 `ChatMessageNotifier` — 支持 type=audio 乐观插入

### 端侧播放与缓存（voice-playback-and-cache Story）
- [x] D9: [Dart] 创建 `lib/ui/chat/providers/voice_player_manager.dart` — 全局播放器单例（just_audio + audio_session）
- [x] D10: [Dart] 创建 `lib/ui/chat/widgets/message/voice_message_bubble.dart` — 语音气泡（播放按钮+波形+时长+进度+状态）
- [x] D11: [Dart] 创建 `lib/ui/chat/widgets/message/voice_waveform_painter.dart` — 波形 CustomPaint（静态/动画/进度色彩填充）
- [x] D12: [Dart] 更新 `chat_message_bubble.dart` — type=audio 路由到 VoiceMessageBubble
- [x] D13: [Dart] 在 `app_providers.dart` 注册 voicePlayerManagerProvider

### 测试
- [x] T1: [测试-T1] MessageType audio codegen 验证（Go + Dart 双端）
- [x] T2: [测试-T1] Message.media 字段 codegen 验证
- [x] T12: [测试-T3] 云侧 sendMessage audio 契约测试（请求含 type=audio + media，响应含 seq）

## 搁置任务（不在本次交付范围）

- [ ] T3: [测试-T1] verify_dart_semantic.py 无新增硬编码违规（重启条件：语义审计脚本修复后）
- [ ] T4: [测试-T2] voice_recorder 单元测试 AAC 输出/波形采集/时长限制/最短录音丢弃（重启条件：T2 测试基础设施就绪后）
- [ ] T5: [测试-T2] voice_record_overlay Widget 测试 长按/松手/上滑取消/计时器（重启条件：Widget 测试基础设施就绪后）
- [ ] T6: [测试-T2] voice_send_provider 单元测试 录音→上传→发送状态流转（重启条件：T2 测试基础设施就绪后）
- [ ] T7: [测试-T2] voice_offline_queue 单元测试 入队/出队/FIFO/容量/网络恢复触发（重启条件：T2 测试基础设施就绪后）
- [ ] T8: [测试-T2] voice_player_manager 单元测试 播放/暂停/停止/互斥/中断恢复（重启条件：T2 测试基础设施就绪后）
- [ ] T9: [测试-T2] voice_message_bubble Widget 测试 渲染/宽度正比/状态/红点（重启条件：Widget 测试基础设施就绪后）
- [ ] T10: [测试-T2] voice_waveform_painter 测试 灰色/动画/进度填充/repaint boundary（重启条件：Widget 测试基础设施就绪后）
- [ ] T11: [测试-T2] MediaDownloadCache 单元测试 缓存命中/LRU/下载失败（重启条件：T2 测试基础设施就绪后）
- [ ] T13: [测试-T3] 端云集成：录音上传→sendMessage→syncMessages 获取到 audio 消息（重启条件：integration 环境就绪后）
- [ ] T14: [测试-T3] 弱网集成：100kbps 限速下上传重试成功（重启条件：integration 环境就绪后）
- [ ] T15: [测试-T4] 端到端旅程：录音→发送→接收→播放完整闭环（重启条件：E2E 测试环境就绪后）
- [ ] T16: [测试-T4] 弱网旅程：断网录音→恢复→自动上传→最终送达（重启条件：E2E 测试环境就绪后）
- [ ] T17: [测试-T4] 灰度部署验证 integration 全量 → prod 分阶段（重启条件：deploy 阶段）
- [ ] 语音消息转发（重启条件：社交功能迭代时）
- [ ] 群聊语音消息推送优化（重启条件：realtime-gateway 就绪后）

## 未来演进任务

- [ ] WebSocket 实时推送接入（对应 design 未来演进 1，触发条件：realtime-gateway 就绪）
- [ ] 变速播放 0.5x/1.5x/2x（对应 design 未来演进 2）
- [ ] 连续播放（对应 design 未来演进 3）
- [ ] 语音转文字 ASR（对应 design 未来演进 4，触发条件：ASR 供应商对接）
- [ ] 贴耳切换听筒（对应 design 未来演进 5）
- [ ] 多图消息（对应 design 未来演进 6）
- [ ] 视频消息（对应 design 未来演进 7）
