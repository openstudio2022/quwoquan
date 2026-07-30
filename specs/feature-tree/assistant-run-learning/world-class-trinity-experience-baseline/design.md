# L2 Design：小趣统一体验 (`world-class-trinity-experience-baseline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验”需要 `session-preference-memory-control` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`context-assembly-slot-filling`](./context-assembly-slot-filling/spec.md)：装配授权后的上下文与槽位状态，是本能力的入口。
- [`long-term-memory-compaction`](./long-term-memory-compaction/spec.md)：向装配提供事实型长期记忆与压缩后的会话历史。
- [`session-preference-memory-control`](./session-preference-memory-control/spec.md)：向装配提供结构化文风偏好。
- [`skill-progressive-disclosure-routing`](./skill-progressive-disclosure-routing/spec.md)：在策略允许集合内确定该次运行的领域技能与其工具策略。
- [`planner-aggregation-orchestration`](./planner-aggregation-orchestration/spec.md)：消费装配结果与技能策略，决定下一步动作并裁决答案边界。
- [`tool-fabric-runtime`](./tool-fabric-runtime/spec.md)：为编排执行工具调用并返回受预算与恢复策略约束的观察。
- [`native-tool-calling-model-routing`](./native-tool-calling-model-routing/spec.md)：为编排提供模型档位与原生工具调用协议。
- [`trajectory-replay-evaluation-gate`](./trajectory-replay-evaluation-gate/spec.md)：消费上述各 Story 的公开运行结果，以版本化回放语料持续验证完整 Agent 轨迹。

## 3. 端云与数据流

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 小趣采用统一 Agent 主线、Skill 中心与轨迹回放准入
- 决策：小趣采用统一 Agent 主线与 Skill 中心；提示、策略或技能目录变更必须通过同一主线的版本化轨迹回放后才能合入。
- 理由：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`context-assembly-slot-filling`](./context-assembly-slot-filling/spec.md)、[`long-term-memory-compaction`](./long-term-memory-compaction/spec.md)、[`session-preference-memory-control`](./session-preference-memory-control/spec.md)、[`skill-progressive-disclosure-routing`](./skill-progressive-disclosure-routing/spec.md)、[`planner-aggregation-orchestration`](./planner-aggregation-orchestration/spec.md)、[`tool-fabric-runtime`](./tool-fabric-runtime/spec.md)、[`native-tool-calling-model-routing`](./native-tool-calling-model-routing/spec.md)、[`trajectory-replay-evaluation-gate`](./trajectory-replay-evaluation-gate/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 最终有利于多端统一、集中运维和可观测。
- 信息不足且无法安全假设时，必须请求澄清。
- 协议版本、结构化决策、工具观测、子代理运行摘要。
- `slot_contract`
