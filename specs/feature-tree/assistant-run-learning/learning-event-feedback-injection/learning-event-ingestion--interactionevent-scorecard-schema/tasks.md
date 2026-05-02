# 开发任务：interactionevent-scorecard-schema

## 阶段 0：schema 冻结
- [ ] 冻结 InteractionEvent、Scorecard、trainingEligible、字段分级与 scorecard 类型集合
- [ ] 明确原始文本、摘要/哈希、PII/SENSITIVE 的边界

## 阶段 1：幂等与去重
- [ ] 冻结 folded 节点 `ingestion-dedup-and-idempotency` 的判重键、重放与补数规则
- [ ] 建立 eventId + eventVersion / scorecardId 的校验策略

## 阶段 2：metadata / validator
- [ ] 建立 schema validator、样例 payload 与契约断言
- [ ] 若走 metadata 驱动，补齐对应 schema 定义与生成

## 阶段 3：测试与 gate
- [ ] contract：schema 字段、字段等级、兼容策略
- [ ] integration：重试、补数、去重、回放场景
- [ ] gate 验证

## 当前交付任务
- [ ] Migrated current node: `ingestion-dedup-and-idempotency` (from `assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/interactionevent-scorecard-schema/ingestion-dedup-and-idempotency`)
