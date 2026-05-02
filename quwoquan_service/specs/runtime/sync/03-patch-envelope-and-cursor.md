# Patch Envelope 与 Cursor

## 1. 标准 patch

建议结构：

```json
{
  "syncSeq": 12345,
  "type": "conversation.avatar.updated",
  "entityType": "conversation",
  "entityId": "c_100",
  "occurredAt": "2026-04-23T12:00:00Z",
  "schemaVersion": "1.0",
  "payload": {}
}
```

## 2. cursor 规则

客户端持有：

- `lastConsumedSyncSeq`

服务端增量接口输入：

- `afterSeq`
- `limit`

## 3. 设计要求

- `syncSeq` 必须严格单调递增
- 同一个 patch 重放不能造成副作用
- payload 要尽量小，但足以驱动本地更新

## 4. payload 示例

### 4.1 群头像更新

```json
{
  "conversationId": "c_100",
  "avatarUrl": "https://avatar-cdn.example.com/...",
  "groupAvatarVersion": 18
}
```

### 4.2 用户头像更新

```json
{
  "userId": "u_1",
  "avatarUrl": "https://cdn.example.com/...",
  "avatarVersion": 12
}
```
