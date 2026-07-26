# L2 Design：主页发现与挂载 (`homepage-discovery-and-attach`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让用户发现具体事物的主页，并在发布内容时以单一引用把内容挂接到该主页”需要 `homepage-attach-in-publish-flow`、`homepage-entry-and-preview`、`homepage-search-and-picker`、`missing-homepage-suggestion-and-review` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让用户发现具体事物的主页，并在发布内容时以单一引用把内容挂接到该主页。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`homepage-attach-in-publish-flow`](./homepage-attach-in-publish-flow/spec.md)：两个入口产生的挂载字段与回流聚合语义一致。
- [`homepage-entry-and-preview`](./homepage-entry-and-preview/spec.md)：入口断裂为零：六类入口全部可达 homepageDetail 且埋点带 referralSource。
- [`homepage-search-and-picker`](./homepage-search-and-picker/spec.md)：picker 页 loading/error/empty/populated 四态齐备且选择结果可回填。
- [`missing-homepage-suggestion-and-review`](./missing-homepage-suggestion-and-review/spec.md)：幂等接收用户建议，并保证候选在审核发布前不可公开发现。

## 3. 端云与数据流

- 上游能力：[`shared-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 内容域写主页引用，主页域异步聚合内容回流
- 决策：内容域写主页引用，主页域异步聚合内容回流。
- 理由：让用户发现具体事物的主页，并在发布内容时以单一引用把内容挂接到该主页。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`homepage-attach-in-publish-flow`](./homepage-attach-in-publish-flow/spec.md)、[`homepage-entry-and-preview`](./homepage-entry-and-preview/spec.md)、[`homepage-search-and-picker`](./homepage-search-and-picker/spec.md)、[`missing-homepage-suggestion-and-review`](./missing-homepage-suggestion-and-review/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- feature flag、观测、SLO 验证与回滚方案。
