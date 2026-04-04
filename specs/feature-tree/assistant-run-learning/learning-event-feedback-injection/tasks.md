# 开发任务：learning-event-feedback-injection

## 阶段 0：规格与桥接冻结
- [ ] 冻结 learning-event-ingestion、interactionevent-scorecard-schema、plan.yaml 与 CR 关系
- [ ] 对齐与 `event-ingestion-and-analytics` 的共享字段、experimentBucket 与 trainingEligible 语义

## 阶段 1：metadata 对齐
- [ ] 补齐 assistant learning 相关 metadata、错误码、字段分级与 storage/projection
- [ ] 执行 `make -C quwoquan_service verify-metadata`
- [ ] 执行 `make codegen`
- [ ] 执行 `make codegen-app`

## 阶段 2：端侧 sync 与上报
- [ ] 将 `localMock/cloudStub` 迁移到真实 remote sync adapter
- [ ] 打通 InteractionEvent / Scorecard 上报、重试与幂等键
- [ ] 接入统一 reporter / event envelope

## 阶段 3：聚合与注入
- [ ] 实现学习事件落库与聚合
- [ ] 实现反馈上下文注入与策略消费
- [ ] 确保可被运营/实验视图复盘

## 阶段 4：测试与 gate
- [ ] mock/unit/contract/integration/uat 分层测试
- [ ] 验证隐私字段、训练资格、回滚与补数场景
- [ ] gate 验证
