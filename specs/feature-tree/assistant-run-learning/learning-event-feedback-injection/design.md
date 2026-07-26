# L2 Design：学习事件反馈注入 (`learning-event-feedback-injection`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一学习事件上报、反馈聚合与运行时上下文注入链路”需要 `feedback-aggregation`、`feedback-context-injection`、`learning-event-ingestion` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：统一学习事件上报、反馈聚合与运行时上下文注入链路。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`feedback-aggregation`](./feedback-aggregation/spec.md)：定义“反馈聚合”的可观察主路径、失败语义及父能力交接。
- [`feedback-context-injection`](./feedback-context-injection/spec.md)：定义“反馈上下文注入”的可观察主路径、失败语义及父能力交接。
- [`learning-event-ingestion`](./learning-event-ingestion/spec.md)：`queryTextDigest`（不得直接以原始敏感文本进入公开分析层）。

## 3. 端云与数据流

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 学习事件只追加写入并由可重建投影聚合
- 决策：学习事件只追加写入并由可重建投影聚合。
- 理由：统一学习事件上报、反馈聚合与运行时上下文注入链路。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`feedback-aggregation`](./feedback-aggregation/spec.md)、[`feedback-context-injection`](./feedback-context-injection/spec.md)、[`learning-event-ingestion`](./learning-event-ingestion/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 记录 operation、终态、延迟与 canonical error；特有阈值由 spec 和运行配置约束。
