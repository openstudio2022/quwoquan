# 开发任务：assistant-stream-and-chat-push

- [ ] 实现：助手流式输出 — QA Runner 回调 SSEServer.Push(userId, chunk)
- [ ] 实现：assistant.chunk 事件类型（events.yaml 登记）
- [ ] 实现：聊天消息推送 — Change Stream 监听 messages → Push 给 recipient
- [ ] 实现：message.sent 事件映射与路由
- [ ] 实现：动态更新推送 — Change Stream 监听 posts/feed → 按订阅路由
- [ ] 测试：助手流式输出端到端测试
- [ ] 测试：聊天消息推送端到端测试
- [ ] gate：集成到 make gate
