# 投递语义

## 1. 目标

明确 realtime 的可靠性语义，避免误把在线通知当作最终同步来源。

## 2. 语义定义

- WebSocket hint：至少一次提示，允许重复
- Push hint：尽力而为，不保证顺序
- 最终一致：由 sync cursor 补齐

## 3. 客户端要求

- 重复 hint 不应造成重复副作用
- 收到 hint 后应按 cursor 拉增量
- 未收到 hint 也必须支持启动补拉
