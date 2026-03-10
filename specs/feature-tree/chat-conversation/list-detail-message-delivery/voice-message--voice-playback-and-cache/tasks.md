# 语音播放与缓存 任务列表

> L4 Story 工程执行清单。引用 L3 `voice-message` tasks.md 任务编号。

## 当前交付任务

### 端侧
- [x] D9: voice_player_manager.dart（全局播放器单例）
- [x] D10: voice_message_bubble.dart（语音气泡组件）
- [x] D11: voice_waveform_painter.dart（波形 CustomPaint）
- [x] D12: chat_message_bubble.dart type=audio 路由
- [x] D13: Provider 注册（voicePlayerManagerProvider）

### 测试
- [x] T1-T2: [T1] MessageDto/SendMessageRequest audio 契约测试

## 搁置任务

- [ ] T3: [T1] verify_dart_semantic.py 无新增违规（重启条件：语义审计脚本修复后）
- [ ] T8: [T2] voice_player_manager 单测 播放/暂停/互斥/中断（重启条件：T2 测试基础设施就绪后）
- [ ] T9: [T2] voice_message_bubble Widget 测试（重启条件：Widget 测试基础设施就绪后）
- [ ] T10: [T2] voice_waveform_painter 测试（重启条件：Widget 测试基础设施就绪后）
- [ ] T11: [T2] MediaDownloadCache 单测（重启条件：T2 测试基础设施就绪后）
- [ ] T13: [T3] 端云集成 syncMessages audio 播放（重启条件：integration 环境就绪后）
- [ ] T14: [T3] 弱网流式播放集成（重启条件：integration 环境就绪后）
- [ ] T15: [T4] 播放旅程完整闭环（重启条件：E2E 测试环境就绪后）
- [ ] T17: [T4] 灰度部署验证（重启条件：deploy 阶段）

见 L3 tasks.md。

## 未来演进任务

见 L3 tasks.md。
