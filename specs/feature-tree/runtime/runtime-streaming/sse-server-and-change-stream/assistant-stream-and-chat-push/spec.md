# L4 对象任务：assistant-stream-and-chat-push

## 功能说明
- **助手流式输出**：QA Runner 生成回复时，通过 SSEServer 逐 chunk 推送给对应用户；事件类型 assistant.chunk。
- **聊天消息推送**：message.sent 事件产生后，ChangeStreamWatcher 监听 messages 集合变更，触发 SSEServer.Push 给接收方用户。
- **动态更新推送**：Post 发布后，订阅用户的 SSE 连接收到 feed.updated 推送。

## 实现要点
- **助手流式**：QA Runner 回调 SSEServer.Push(userId, chunk)；chunk 格式与 events.yaml 一致。
- **聊天推送**：Change Stream 监听 messages 集合；insert 事件 → 解析 recipient_id → Push。
- **动态推送**：Change Stream 监听 posts 或 feed 相关集合；按订阅关系路由。

## 约束
- 推送事件类型与 events.yaml 定义一致。
- 按 userId 隔离，不跨用户泄露。

## 验收标准
- A1：助手流式输出 + 聊天消息推送端到端可用。
- A2：推送延迟 < 100ms（本地环境）。
- A8：助手流式 + 聊天推送端到端测试。
