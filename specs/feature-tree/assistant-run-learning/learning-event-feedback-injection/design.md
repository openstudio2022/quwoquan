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
- App 先把 `AppendAssistantLearningFact` command 写入 account/persona/device 分区的加密 pending-confirmation outbox；只有服务端返回同一 `eventId` 且 `payloadDigest` 一致的 receipt 后才删除。
- assistant-service 在同一 Mongo transaction 内提交 canonical fact、durable receipt、严格递增 append sequence 与脱敏 outbox event；原始文本不得进入 outbox 或投影。
- canonical projector 按 append sequence 消费唯一事实流，并在同一 transaction 内提交 persona-scoped projection、projection receipt 与 generation watermark；唯一 projection definition 以其 canonical contract 的严格 SHA-256 digest 标识。
- 每次重建写入独立 shadow generation；只有 shadow 追平 canonical fact stream 后才在同一 transaction 原子切换 active generation 并清理全部非 active generation，读取方不观察半完成重建或长期并存的旧投影。
- Run 创建时先冻结 immutable policy release，再按当前 owner consent、最小样本与字段 allowlist 读取 persona-scoped projection；结果连同 consent、definition digest 与 watermark 证据冻结到 Run。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 学习事实只追加写入并由单轨可重建投影聚合
- 决策：`AssistantLearningFact` 只通过 `AppendAssistantLearningFact` 追加写入，并由唯一 canonical definition 的可重建投影聚合；`generationId` 只表示一次原子重建运行，不表示模型或契约版本。
- 理由：统一学习事件上报、反馈聚合与运行时上下文注入链路。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`feedback-aggregation`](./feedback-aggregation/spec.md)、[`feedback-context-injection`](./feedback-context-injection/spec.md)、[`learning-event-ingestion`](./learning-event-ingestion/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 反馈上下文以 consent 与 immutable policy 双重授权
- 决策：模型只接收当前 account/persona 的脱敏聚合摘要；policy release 冻结允许的 signal、metric、reason、窗口与最小样本，Run 同时冻结 consent identity、projection definition 与 source watermark。
- 理由：用户同意决定“能否使用”，不可变 policy 决定“允许使用什么”；两者缺一不可，且执行期不能因 rollout 或投影更新发生漂移。
- 被否决方案：直接拼接原始反馈、读取 account 下其他 persona、在模型 bridge 临时过滤、或 consent/reader 失败时使用旧缓存。
- 约束与影响：opt-out、reader 失败、样本不足、owner 不匹配都产生明确 no-injection decision；不得本地合成或回退旧画像。
- 关联要求：`REQ-002`
- 影响 Story：[`feedback-context-injection`](./feedback-context-injection/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、CAS 冲突、definition digest 不一致或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、旧 definition 文档、双读双写或页面本地写副本；definition digest 不一致时只能从 canonical facts 重建后原子切换。

## 6. 质量与观测

- 记录 operation、终态、延迟与 canonical error；特有阈值由 spec 和运行配置约束。
