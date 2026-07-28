# L2 Design：主页评价与内容聚合 (`homepage-review-and-content`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让用户围绕共享主页完成理解、比较、浏览内容、查看评价与继续贡献内容”需要 `homepage-content-and-question-aggregation`、`homepage-contextual-publish-entry`、`homepage-overview-and-module-shell`、`homepage-review-read-and-score-summary` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让用户围绕共享主页完成理解、比较、浏览内容、查看评价与继续贡献内容。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`homepage-content-and-question-aggregation`](./homepage-content-and-question-aggregation/spec.md)：记录/讨论聚合四态齐备且点击回流埋点在。
- [`homepage-contextual-publish-entry`](./homepage-contextual-publish-entry/spec.md)：主页内入口与全局创作入口产出同一挂载语义。
- [`homepage-overview-and-module-shell`](./homepage-overview-and-module-shell/spec.md)：用户可见文案禁止出现“实体”，按具体类型或对象名表达，例如 `大学 · 北京海淀`、`认识清华大学`、`大家在聊清华大学`；兜底使用“这个主页”。
- [`homepage-review-read-and-score-summary`](./homepage-review-read-and-score-summary/spec.md)：五个 operation（create/update/delete/list/mine）在四环境 Remote 与 local_contract typed double 行为同构且全部 per-op commercial ready。

## 3. 端云与数据流

- 上游能力：[`shared-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 主页必须是 read-first，而不是 feed-first
- 决策：主页必须是 read-first，而不是 feed-first。
- 理由：让用户围绕共享主页完成理解、比较、浏览内容、查看评价与继续贡献内容。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`homepage-content-and-question-aggregation`](./homepage-content-and-question-aggregation/spec.md)、[`homepage-contextual-publish-entry`](./homepage-contextual-publish-entry/spec.md)、[`homepage-overview-and-module-shell`](./homepage-overview-and-module-shell/spec.md)、[`homepage-review-read-and-score-summary`](./homepage-review-read-and-score-summary/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- feature flag、观测、SLO 验证与回滚方案。
