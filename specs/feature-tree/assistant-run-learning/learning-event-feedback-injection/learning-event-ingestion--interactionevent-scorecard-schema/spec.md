# L4 特性：interactionevent-scorecard-schema

## 功能说明

细化 InteractionEvent 与 Scorecard 的 schema、字段分级、训练资格、版本兼容，以及折叠子节点 `ingestion-dedup-and-idempotency` 的治理要求。

## InteractionEvent schema 要求

### 主键与上下文
- `eventId`
- `eventVersion`
- `runId`
- `traceId`
- `sessionId`
- `pageVisitId`
- `requestId`
- `surfaceId`
- `routeId`
- `experimentBucket`
- `createdAt`

### 行为与反馈字段
- `domainId`
- `pageType`
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

### 文本与敏感字段
- `queryText`、`answerText`、`correctionText` 等原始文本不得直接进入公开聚合层；
- 公开分析层只能持有脱敏摘要、长度特征、标签或哈希等受控表示；
- 是否可进入训练必须由 `trainingEligible` 与字段分级共同决定。

## Scorecard schema 要求

### 通用字段
- `scorecardId`
- `eventId`
- `scorecardType`
- `score`
- `confidence`
- `reasonCodes`
- `evidenceRefs`
- `trainingEligible`
- `createdAt`

### 标准 scorecard 类型
- `answer_relevance`
- `answer_correctness`
- `answer_completeness`
- `evidence_grounding`
- `domain_fitness`
- `response_speed_satisfaction`
- `interaction_friction`
- `followup_burden`
- `personalization_fit`
- `privacy_comfort`
- `safety_compliance`
- `trust_confidence`

## 字段分级与训练资格

- `PUBLIC_AGGREGATE`：可进入聚合分析；
- `INTERNAL_OPERATIONAL`：仅内部排障与回放；
- `SENSITIVE`：需脱敏或缩短保留期；
- `PII_RESTRICTED`：仅受控链路可见，不得进入公开分析与默认训练。

训练资格规则：
- `trainingEligible = true` 仅表示事件/评分卡可参与训练候选，不代表所有字段都可训练；
- `PII_RESTRICTED` 字段默认不可训练；
- `privacy_comfort`、`safety_compliance` 等负向 scorecard 可进入策略回滚与 guardrail，不必直接进入生成模型训练。

## Folded current node `ingestion-dedup-and-idempotency`

### 功能说明
- InteractionEvent 与 Scorecard 必须具备稳定幂等键、去重窗口与补数兼容策略。

### 约束
- 同一 `eventId + eventVersion` 重放不得重复计数；
- 同一 `scorecardId` 重报不得重复进入训练样本；
- 端侧本地缓存重试、网络重放、批量补数必须保持口径一致。

### 验收标准
- A1：幂等、去重、补数与回放规则可执行；
- A7：schema 校验与契约测试覆盖 InteractionEvent/Scorecard/Idempotency；
- A8：学习事件可稳定进入统一事件与反馈基础设施。
