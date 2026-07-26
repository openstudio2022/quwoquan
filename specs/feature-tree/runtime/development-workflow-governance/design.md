# L2 Design：开发流程治理 (`development-workflow-governance`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收”需要 `directory-native-sdd` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`directory-native-sdd`](./directory-native-sdd/spec.md)：工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 的仓库执行约束。
- 下游能力：仓库内所有业务节点、metadata、代码和测试。
- 读取事实：目录、Markdown、metadata、测试 `spec_ref` 与 Git diff。
- 写入事实：只修改正式规格、设计、metadata、代码和测试；派生结果写入 `.qwq_output`。
- 一致性要求：README 模板、命令和 gate 必须同步更新。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 目录结构和父子 spec 构成唯一特性树
- 决策：目录结构和父子 spec 构成唯一特性树。
- 理由：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`directory-native-sdd`](./directory-native-sdd/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 门禁必须可重复、输出精确文件和原因，并在仓库规模下保持秒级目录扫描。
- 报告记录节点数、规格/设计数、问题分类和未归属变更，不记录敏感内容。
