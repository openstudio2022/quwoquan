# L2 特性：learning-event-feedback-injection

## 功能说明
- 统一学习事件上报、反馈聚合与运行时上下文注入链路。
- 将反馈数据转为可复用特征，支撑助手效果持续优化。

## 约束
- 事件 schema 必须统一并具备版本兼容策略。
- 反馈注入只能读取通过策略校验的数据，不得直接拼接原始未校验字段。

## 与父/子节点关系

- 父节点：`assistant-run-learning` L1
- 子节点：
  - `learning-event-ingestion`：统一学习事件与评分卡上报、落库标准、与统一事件体系桥接
  - `feedback-aggregation`：反馈聚合与分布统计
  - `feedback-context-injection`：反馈特征注入运行时上下文
- 与运营反馈基础设施的横向关系：
  - 通过 `product-ops-growth/event-ingestion-and-analytics` 共享统一事件字典、schema 治理、实验与分析维度

## 相关文档

- [`learning-event-ingestion/spec.md`](./learning-event-ingestion/spec.md)
- [`learning-event-ingestion--interactionevent-scorecard-schema/spec.md`](./learning-event-ingestion--interactionevent-scorecard-schema/spec.md)
- [`plan.yaml`](./plan.yaml)

## 验收标准
- A1：事件上报、聚合、注入链路可用且数据完整。
- A5：反馈闭环可执行并可复盘。
- A8：事件与注入链路的自动化测试覆盖完整。
