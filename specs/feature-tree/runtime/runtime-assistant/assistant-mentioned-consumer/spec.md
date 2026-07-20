# L3 特性：assistant-mentioned-consumer

## 功能说明
- 消费 chat 域可靠事件流 `events.chat.assistant_mentions`：群聊 @小趣 后拉取会话窗口消息做话题理解，代小趣成员回帖。

## 约束
- 必须走 Redis Stream consumer group（含 DLQ `events.chat.assistant_mentions.dlq`），不得只依赖 realtime Pub/Sub。
- 回帖前必须校验小趣仍是会话成员；成员被移除后事件按 ack-and-drop 处理。
- 回复经 chat-service SendMessage 发出，不新增第二消息通道。

## 验收标准
- A1：@小趣 事件消费→话题理解→会话内回复链路可用。
- A2：消费失败进入 DLQ 且可重放；成员移除后不再回帖。
- A7：consumer 与 chat 集成契约测试可复跑。
