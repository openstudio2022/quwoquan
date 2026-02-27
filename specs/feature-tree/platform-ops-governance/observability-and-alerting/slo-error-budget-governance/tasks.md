# 开发任务：slo-error-budget-governance

## 当前交付任务（门禁闭环）

### Wave 1 — 门禁模型

- [x] S1 定义配置发布门禁指标与预算模型
- [x] S2 实现按配置版本打标签的指标采集
- [x] S3 实现阶段判定器（continue/pause/rollback）

### Wave 2 — 发布联动与演练

- [x] S4 对接灰度发布与回滚流程
- [x] S5 完成故障注入演练测试
- [x] S6 输出门禁阈值与回滚触发策略文档（deliver 必备）
  - `deploy/config-release/slo_thresholds.yaml`
  - `deploy/config-release/runbook.md`

## 搁置任务（带规划）

- [ ] S7 预算阈值自动学习（按历史波动动态调整）
  - 搁置原因：先使用固定阈值保证可解释性

## 未来演进任务

- [ ] S8 统一跨服务预算联动（全链路预算）
