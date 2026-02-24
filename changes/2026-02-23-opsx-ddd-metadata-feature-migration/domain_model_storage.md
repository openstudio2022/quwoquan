# 领域模型、接口契约与物理存储设计

## 1) 横切服务领域模型

### product-ops

- `InteractionEvent`（Entity）
  - `eventId`、`eventName`、`eventAt`、`userId`、`pageId`、`traceId`、`payload`
- `ExperimentBucket`（Entity）
  - `experimentId`、`bucketId`、`subjectKey`、`version`、`assignedAt`
- `FeedbackLoopState`（Aggregate）
  - `targetType`、`targetId`、`collectStatus`、`evaluateStatus`、`releaseStatus`、`rollbackFlag`

### platform-ops

- `ConfigReleaseRecord`（Entity）
  - `releaseId`、`scope`、`configKey`、`version`、`operatorId`、`rollbackTo`
- `AlertPolicy`（Entity）
  - `policyId`、`metric`、`threshold`、`window`、`severity`
- `ReliabilityGuard`（Value Object）
  - `timeoutMs`、`retryMax`、`circuitThreshold`、`rateLimitQps`

## 2) 领域服务模型（首批迁移）

### chat-service

- `Conversation`（Aggregate）
  - `conversationId`、`type`、`participantIds`、`settings`、`lastMessageId`
- `Message`（Entity）
  - `messageId`、`conversationId`、`senderId`、`content`、`sentAt`、`status`

### content-service

- `FeedItem`（Entity）
  - `itemId`、`itemType`、`score`、`postRef`
- `FeedCursor`（Value Object）
  - `nextCursor`、`watermark`

## 3) 接口契约（关键）

- `GET /v1/chat/conversations` -> `{ items: ConversationSummary[], nextCursor: string }`
- `GET /v1/chat/conversations/{conversationId}/messages` -> `{ items: MessageDTO[], nextCursor: string }`
- `GET /v1/orch/discovery/feed` -> `{ items: FeedItemDTO[], nextCursor: string }`
- `POST /v1/product-ops/events` -> `{ accepted: boolean, requestId: string }`
- `GET /v1/product-ops/experiments/bucket` -> `{ experimentId, bucketId, version }`

错误响应统一 `ErrorResponse`，并携带 `requestId` 与 `traceId`。

## 4) 物理存储映射

### MongoDB（主）

- `chat_conversations`
- `chat_messages`
- `ops_interaction_events`
- `ops_feedback_loop_states`
- `content_feed_items`

### PostgreSQL（辅）

- `identity_accounts`（强一致身份）
- `experiment_rollout_rules`（实验规则约束）
- `config_release_audit`（配置发布审计）

### Redis（缓存与幂等）

- `chat:conv:{conversationId}:latest_cursor`
- `feed:discovery:{userId}:cursor`
- `idem:{service}:{idempotency_key}`

## 5) 元数据策略（字段级）

- `Message.content` -> `SENSITIVE` + `log_policy=mask`
- `Conversation.participantIds` -> `PII` + `log_policy=mask`
- `InteractionEvent.traceId` -> `PUBLIC` + `log_policy=allow`
- `FeedItem.score` -> `PUBLIC` + `observe_metric=true`

