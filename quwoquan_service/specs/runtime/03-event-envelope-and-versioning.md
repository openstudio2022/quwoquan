# 事件 Envelope 与版本治理

## 1. 目标

统一跨服务事件的基础结构，降低以下问题：

- 事件难以追踪
- 重复消费难以识别
- schema 演进无规则
- 线上问题难以定位

## 2. 标准 envelope

推荐统一结构：

```json
{
  "eventId": "evt_xxx",
  "eventType": "UserAvatarUpdated",
  "schemaVersion": "1.0",
  "producer": "user-service",
  "aggregateType": "User",
  "aggregateId": "u_123",
  "occurredAt": "2026-04-23T12:00:00Z",
  "traceId": "tr_xxx",
  "dedupKey": "user-avatar-u_123-v12",
  "payload": {}
}
```

## 3. 字段约束

- `eventId`：全局唯一
- `schemaVersion`：显式版本号
- `traceId`：贯穿请求链路
- `dedupKey`：消费者幂等依据
- `payload`：事件业务内容

## 4. 版本治理

### 4.1 向后兼容优先

- 新增字段优先采用可选字段
- 移除字段必须经历弃用期
- 破坏性变更必须提升主版本

### 4.2 版本写法

- `1.0`：首发稳定版本
- `1.1`：新增向后兼容字段
- `2.0`：破坏性变更

## 5. 幂等规则

消费者必须基于 `dedupKey` 或 `eventId` 做幂等处理，尤其是：

- 群头像重算任务
- 同步流 patch 投递
- 用户头像变更广播

## 6. 推荐首批标准事件

- `UserAvatarUpdated`
- `ConversationAvatarUpdated`
- `MemberJoined`
- `MemberLeft`
- `ConversationRosterUpdated`
- `MessageSent`
- `MessageRecalled`
- `ReadReceiptSent`

## 7. runtime 责任

runtime 负责：

- envelope 基类
- trace / dedup 辅助能力
- schemaVersion 约束

业务服务负责：

- 事件何时产生
- payload 具体字段
- 事件语义
