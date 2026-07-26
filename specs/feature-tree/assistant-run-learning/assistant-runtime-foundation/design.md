# L2 Design：助手运行时基础 (`assistant-runtime-foundation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询”需要 `assistant-object-runtime` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`assistant-object-runtime`](./assistant-object-runtime/spec.md)：服务重启后必须能按 owner 读取会话与运行；敏感操作在 consent 缺失、撤销或存储不可用时必须拒绝执行。

## 3. 端云与数据流

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 对象状态、幂等回执与 outbox 原子提交
- 决策：对象状态、幂等回执与 outbox 原子提交。
- 理由：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`assistant-object-runtime`](./assistant-object-runtime/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 记录 commit 冲突、幂等命中、outbox 延迟、consent 拒绝和 resume 结果。
- 日志只记录对象 ID、版本和错误码，不记录 prompt、token 或私密画像正文。
