# L3 特性：event-schema-governance

## 功能说明

定义统一事件 envelope、字段分级、版本兼容、幂等/去重、采样与背压规则，作为全链路埋点与反馈基础设施的 schema 真相源。

## EventEnvelope 规范

### 必填字段
- `eventId`
- `eventType`
- `eventName`
- `eventVersion`
- `occurredAt`
- `producer`
- `priority`
- `context`
- `payload`

### context 必须支持的公共字段
- `sessionId`
- `journeyId`
- `pageVisitId`
- `surfaceId`
- `routeId`
- `operationId`
- `requestId`
- `experimentBucket`
- `userIdHash`
- `appVersion`
- `platform`
- `networkClass`

### business / feedback 扩展字段
- `contentId / contentType / authorId / circleId`
- `conversationId / messageId / rtcSessionId`
- `entityType / entityId / bindPosition`
- `runId / traceId / scorecardType / trainingEligible / labelSource`

## 字段分级

- `PUBLIC_AGGREGATE`：可进入聚合报表与常规 dashboard。
- `INTERNAL_OPERATIONAL`：仅供内部排障、审计或高权限分析使用。
- `SENSITIVE`：需脱敏、限制保留或禁止进入训练。
- `PII_RESTRICTED`：不得直接进入公开分析宽表，仅可在受控链路中使用。

## 幂等与去重

- `eventId + eventVersion` 为统一幂等键。
- 客户端重试不得改写 `eventId`。
- 曝光等高频事件允许同时存在：
  - 客户端轻量去重（session/window 级）；
  - 服务端 event 级幂等；
  - Redis 状态级去重。
- `learning` 事件与 `scorecard` 必须具备明确的 `feedbackTarget` 与判重键。

## 版本兼容

- 同一事件语义升级时，只允许：
  1. 向后兼容新增字段；
  2. 保持旧字段语义不变；
  3. 通过 `eventVersion` 与消费兼容策略共存。
- 不允许直接复用旧 `eventName` 改写字段含义。
- schema 变更必须同步更新指标字典、acceptance 与 CR。

## 采样、优先级与背压

- `P0`：关键交易、关键学习、关键错误与回滚事件；全量保留。
- `P1`：核心体验与行为事件；默认全量或低采样。
- `P2`：探索性、诊断性或高频细粒度事件；允许采样与优先丢弃。
- 背压时保序原则：优先保 `P0`，再保 `P1`，最后舍弃 `P2`。

## 生命周期与保留

- 明细在线可查：默认 `7~90d`，按事件域配置。
- 聚合结果：默认 `1~3y`。
- 冷归档：对象存储长期保留，受法务与成本策略约束。
- `SENSITIVE/PII_RESTRICTED` 字段保留期不得高于同域普通字段。

## 约束

- 所有进入统一反馈应用、运营分析、实验评估与训练的事件，必须符合本 schema。
- 不允许 page access、behavior、Assistant learning、visit、analytics 继续长期维护独立 envelope。
- surface/route/operation/experiment 等上下文必须与 metadata 驱动语义保持一致。

## 验收标准

- A1：统一 envelope、字段分级、优先级、保留策略可覆盖全域事件。
- A5：灰度、回滚、兼容升级规则明确。
- A6：PII/SENSITIVE 分级与脱敏规则明确。
- A7：事件版本、幂等与 schema 演进规则形成单一真相源。
- A8：为 baseline 与后续 `/dev` 提供可验证的 schema 基线。
