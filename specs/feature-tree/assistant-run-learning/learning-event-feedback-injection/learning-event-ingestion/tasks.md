# 开发任务：learning-event-ingestion

## 阶段 0：契约冻结
- [ ] 冻结 InteractionEvent / Scorecard 与统一事件体系的桥接规则
- [ ] 明确 eventId、pageVisitId、surfaceId、routeId、experimentBucket 的接入要求

## 阶段 1：metadata / codegen
- [ ] 补齐 assistant learning events / scorecards metadata
- [ ] 对齐 storage、projection、error/schema 与 codegen 产物
- [ ] 执行 metadata verify/codegen

## 阶段 2：实现
- [ ] 实现云侧 ingestion handler / service / persistence / projection
- [ ] 实现端侧 remote sync adapter 与批量重试/幂等
- [ ] 与统一事件 reporter 对接

## 阶段 3：测试与 gate
- [ ] unit/contract：字段完整性、幂等、兼容性
- [ ] integration：ingestion -> projection -> feedback injection
- [ ] gate 验证
