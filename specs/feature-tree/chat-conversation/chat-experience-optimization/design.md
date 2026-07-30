# L2 Design：趣聊体验优化 — 聊天入口/对话页/对话设置全面打磨 (`chat-experience-optimization`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一趣聊入口、会话详情与群聊管理的交互和状态”需要 `chat-detail-avatar-display`、`chat-group-admin-govern`、`chat-list-local-cache`、`chat-list-ui-polish` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：统一趣聊入口、会话详情与群聊管理的交互和状态。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`chat-detail-avatar-display`](./chat-detail-avatar-display/spec.md)：展示对方的版本化头像，点击可进入用户主页，缓存加载不得阻塞会话打开。
- [`chat-group-admin-govern`](./chat-group-admin-govern/spec.md)：确认弹窗必须屏幕上下左右居中。
- [`chat-list-local-cache`](./chat-list-local-cache/spec.md)：会话对象缓存遵守 runtime-client-foundation 的本地缓存规则，只从 chat-service canonical Conversation projection 派生且不维护对象策略台账。
- [`chat-list-ui-polish`](./chat-list-ui-polish/spec.md)：`@我` 和 `未读` 的角标数量来自同一模型，并在阅读后按统一规则递减。

## 3. 端云与数据流

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 聊天列表、对话页与群管理页共用远端事实和端侧投影
- 决策：聊天列表、对话页与群管理页共用远端事实和端侧投影。
- 理由：统一趣聊入口、会话详情与群聊管理的交互和状态。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`chat-detail-avatar-display`](./chat-detail-avatar-display/spec.md)、[`chat-group-admin-govern`](./chat-group-admin-govern/spec.md)、[`chat-list-local-cache`](./chat-list-local-cache/spec.md)、[`chat-list-ui-polish`](./chat-list-ui-polish/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。
