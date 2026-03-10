# 语音录制与发送 任务列表

> L4 Story 工程执行清单。引用 L3 `voice-message` tasks.md 任务编号。

## 当前交付任务

### metadata + codegen（共享，此 Story 驱动）
- [x] M1-M4: metadata 变更（types/fields/service/events）
- [x] C1-C3: codegen（verify + Go + Dart）

### 云侧
- [x] G1: chat-service sendMessage 支持 type=audio + media 写入
- [x] G2: MessageSent 事件 payload 含 mediaUrl + media
- [x] G3: sendMessage audio 契约测试

### 端侧
- [x] D1: pubspec.yaml 新增依赖（record, just_audio, audio_session, connectivity_plus）
- [x] D2: voice_recorder.dart（录音引擎封装）
- [x] D3: voice_record_overlay.dart（录音交互 UI）
- [x] D4: chat_detail_page.dart 集成语音录音
- [x] D5: voice_send_provider.dart（录音→上传→发送状态管理）
- [x] D6: voice_offline_queue.dart（Hive 离线队列）
- [x] D7: SendMessageRequest 新增 media 字段
- [x] D8: ChatMessageNotifier 支持 audio 乐观插入

### 测试
- [x] T1-T2: [T1] codegen 验证
- [x] T12: [T3] 云侧 sendMessage audio 契约测试

## 搁置任务

- [ ] T4-T7: [T2] 录音引擎 + 交互 Widget + 发送 Provider + 离线队列单测（重启条件：T2 测试基础设施就绪后）
- [ ] T13-T14: [T3] 端云集成 + 弱网集成（重启条件：integration 环境就绪后）
- [ ] T15-T16: [T4] 发送旅程 + 弱网旅程（重启条件：E2E 测试环境就绪后）

见 L3 tasks.md。

## 未来演进任务

见 L3 tasks.md。
