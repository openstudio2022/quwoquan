# Topic 路由与订阅

## 1. 目标

统一 realtime 的 topic 命名与订阅规则。

## 2. 推荐 topic

- `user:{userId}`
- `conversation:{conversationId}`
- `badge:{userId}`

## 3. 路由原则

- 用户级变化优先走 `user:{userId}`
- 会话内活跃态可订阅 `conversation:{conversationId}`
- badge 单独拆 topic，避免噪声

## 4. 订阅策略

- 默认连接建立后订阅 `user:{userId}`
- 进入聊天页后增订阅 `conversation:{conversationId}`
- 离开聊天页取消会话级订阅
