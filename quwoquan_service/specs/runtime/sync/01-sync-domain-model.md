# Sync 领域模型

## 1. 基础对象

### 1.1 UserSyncStream

面向用户的一条单调递增同步流，是客户端拉取增量 patch 的统一来源。

### 1.2 UserSyncSeq

每个用户拥有独立的单调递增 `syncSeq`，用于：

- 有序消费
- gap fill
- 游标恢复

### 1.3 Patch

一次最小变化单元，例如：

- `message.created`
- `conversation.avatar.updated`

### 1.4 Cursor

客户端上报的已消费位置，用于增量拉取。

## 2. 模型关系

- 一个用户对应一条 `UserSyncStream`
- 一条流包含多个 `Patch`
- 每个 `Patch` 有一个全局于该用户流内的 `syncSeq`

## 3. 建模原则

- patch 必须最小化
- 只传变化，不传全量对象
- patch 可重放
- patch 必须具备幂等消费能力
