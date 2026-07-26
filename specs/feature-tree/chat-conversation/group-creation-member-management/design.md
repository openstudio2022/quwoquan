# L2 Design：群聊创建与成员管理 (`group-creation-member-management`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环”需要 `group-candidate-source-orchestration`、`group-create-flow`、`group-member-roster-version-sync`、`group-settings`、`member-add-remove-policy` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`group-candidate-source-orchestration`](./group-candidate-source-orchestration/spec.md)：Mock 与 Remote 候选行为一致且有端云证据。
- [`group-create-flow`](./group-create-flow/spec.md)：api_integration 覆盖成功、非互关、屏蔽、重复请求、边界容量与 outbox。
- [`group-member-roster-version-sync`](./group-member-roster-version-sync/spec.md)：`membersRosterRevision` 与 `updatedAt` 只能由 chat-service 在成员表成功变更后更新。
- [`group-settings`](./group-settings/spec.md)：群设置中显示的成员入口必须可追溯到具体用户对象，方便后续举报/拉黑下沉。
- [`member-add-remove-policy`](./member-add-remove-policy/spec.md)：圈子绑定默认群（`group + circleId`）：跟随圈子绑定关系，不能单独进入 `dissolved`。

## 3. 端云与数据流

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 数据层需要真实群聊、真实圈子与互关关系的统一候选源
- 决策：数据层需要真实群聊、真实圈子与互关关系的统一候选源。
- 理由：私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`group-candidate-source-orchestration`](./group-candidate-source-orchestration/spec.md)、[`group-create-flow`](./group-create-flow/spec.md)、[`group-member-roster-version-sync`](./group-member-roster-version-sync/spec.md)、[`group-settings`](./group-settings/spec.md)、[`member-add-remove-policy`](./member-add-remove-policy/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 对外实时主事件：**`ConversationRosterUpdated`**，合并窗口 **50–100ms**（可配置），窗口内多条变更合并为 **一条** 推送，payload 携带最新 `membersRosterRevision`、`updatedAt`、`aspects`。
- feature flag、观测、SLO 验证与回滚方案。
