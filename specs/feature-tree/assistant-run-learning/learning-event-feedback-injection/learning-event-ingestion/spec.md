# L3 特性：learning-event-ingestion

## 功能说明

定义 Assistant 学习事件与评分卡上报入口、落库标准、统一事件桥接规则，以及与推荐/运营反馈基础设施的关系。

本节点是 `assistant-run-learning` 与 `product-ops-growth/event-ingestion-and-analytics` 的桥接层：

- 对上承接端侧 `InteractionEvent / Scorecard`；
- 对下映射到统一 EventEnvelope、学习特征投影与运营分析视图；
- 对侧与推荐热路径、实验、反馈注入共享字段与幂等语义。

## 输入

### 端侧来源
- `quwoquan_app/lib/assistant/learning/domain/assistant_learning_service.dart`
- `quwoquan_app/lib/assistant/learning/domain/assistant_learning_models.dart`
- `quwoquan_app/lib/assistant/sync/assistant_sync.dart`

### 云侧契约
- `POST /v1/assistant/learning/events`
- `POST /v1/assistant/learning/scorecards`

## 输出

1. 统一 EventEnvelope 中的 `learning` 域事件；
2. 学习特征投影与反馈注入输入；
3. 运营/实验消费视图；
4. 审计与回放可用的明细记录。

## 统一桥接规则

### InteractionEvent
必须映射：
- `eventId`
- `runId`
- `traceId`
- `sessionId`
- `pageVisitId`（若存在）
- `domainId`
- `pageType`
- `queryTextDigest`（不得直接以原始敏感文本进入公开分析层）
- `durationMs`
- `explicitThumb`
- `explicitReasonCodes`
- `copiedAnswer`
- `sharedAnswer`
- `favoritedAnswer`
- `regeneratedAnswer`
- `styleAdjusted`
- `modelSwitched`
- `referenceOpened`
- `interrupted`
- `feedbackTargetMessageId`
- `createdAt`

### Scorecard
必须映射：
- `scorecardType`
- `score`
- `reasonCodes`
- `confidence`
- `evidenceRefs`
- `trainingEligible`
- `createdAt`

## 与统一事件体系的关系

- `InteractionEvent` 与 `Scorecard` 进入统一 `learning` 域，不再作为 Assistant 独有的孤立上报体系长期存在。
- `pageVisitId / surfaceId / routeId / experimentBucket` 必须在可用时进入学习事件 context，支撑页面、策略、实验与体验分析。
- 需要训练的字段与仅可统计字段必须显式分离，遵守字段分级与 `trainingEligible` 语义。

## 幂等、去重与完整性

- 每个 InteractionEvent 与 Scorecard 必须拥有稳定幂等键。
- 端侧重试与云侧重放不得重复计入同一训练样本或统计样本。
- 事件上报成功率、字段完整性与策略注入命中率必须可复盘。

## 约束

- 事件必须支持幂等与去重；字段策略遵从 metadata。
- 明文 PII、敏感 query、原始对话内容不得直接进入公开分析宽表。
- Assistant 学习事件与推荐/运营事件必须共享 experimentBucket 与公共 context 语义。

## 验收标准

- A1：InteractionEvent 与 Scorecard 上报入口、落库标准、桥接规则完整定义。
- A4：学习事件可同时服务于反馈注入、运营分析与实验复盘。
- A6：字段分级、trainingEligible 与敏感文本处理明确。
- A7：学习事件 schema 与统一事件 metadata 一致。
- A8：为 `/baseline` 与后续 `/dev` 提供可执行的桥接基线。
