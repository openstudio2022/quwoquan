# L2 Design：小趣统一体验 (`world-class-trinity-experience-baseline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验”需要 `session-preference-memory-control` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`session-preference-memory-control`](./session-preference-memory-control/spec.md)：服务与 App local_contract 通过。

## 3. 端云与数据流

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 小趣采用统一 Agent 主线与 Skill 中心
- 决策：小趣采用统一 Agent 主线与 Skill 中心。
- 理由：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`session-preference-memory-control`](./session-preference-memory-control/spec.md)
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
