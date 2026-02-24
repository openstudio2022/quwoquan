# Contracts Delta（contracts-first，必须先完成）

## 云侧 contracts（必需）
- [ ] OpenAPI：
  - `quwoquan_service/contracts/openapi/chat.v1.yaml`（会话/消息统一列表结构）
  - `quwoquan_service/contracts/openapi/orchestrator.v1.yaml`（`/v1/orch/discovery/feed`）
  - `quwoquan_service/contracts/openapi/product_ops.v1.yaml`（events + experiments）
- [ ] 通用 headers/分页/错误：`quwoquan_service/contracts/openapi/common.yaml`
- [ ] endpoint 归因：`quwoquan_service/contracts/endpoint_catalog.md`
- [ ] 错误码：`quwoquan_service/contracts/error_codes.md`（按 `<MODULE>.<KIND>.<REASON>`）
- [ ] 隐私/安全分级：`quwoquan_service/contracts/privacy_and_security.md`

## 端侧契约对齐（必需）
- [ ] RemoteRepository 不允许“猜字段”：对齐 `items/nextCursor` 等统一结构
- [ ] headers 注入：traceId/requestId/pageId/session/device/appVersion（见 `quwoquan_app/lib/cloud/runtime/cloud_request_headers.dart`）

## 元数据契约（必需）

- [ ] `quwoquan_service/contracts/metadata/entity_catalog.yaml`：
  - `Conversation`、`Message`、`InteractionEvent`、`VisitRecord`
- [ ] `quwoquan_service/contracts/metadata/field_policy.yaml`：
  - `Message.content` -> `SENSITIVE + mask`
  - `Conversation.participantIds` -> `PII + mask`
  - `InteractionEvent.traceId` -> `PUBLIC + allow`
- [ ] `quwoquan_service/contracts/metadata/event_catalog.yaml`：
  - `chat.message_sent`
  - `content.feed_loaded`
  - `ops.experiment_bucketed`

## 物理存储设计约束（必需）

- [ ] Mongo collections：
  - `chat_conversations`
  - `chat_messages`
  - `ops_interaction_events`
  - `ops_visit_records`
- [ ] PostgreSQL tables（强一致补充）：
  - `identity_accounts`
  - `experiment_rollout_rules`
  - `config_audit_records`
- [ ] Redis keys：
  - `chat:conv:{id}:latest_cursor`
  - `idem:{service}:{idempotency_key}`

