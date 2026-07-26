# L2 Design：圈子协作工具 (`circle-collaboration-tools`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以圈子或组织主页内的群为协作单元，统一交流、资料与公告”需要 `circle-group-chat-binding-sync` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以圈子或组织主页内的群为协作单元，统一交流、资料与公告。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`circle-group-chat-binding-sync`](./circle-group-chat-binding-sync/spec.md)：Circle HTTP create -> Redis Stream -> Chat Mongo -> reverse Stream -> Circle Mongo 的真实 API integration 通过。

## 3. 端云与数据流

- 上游能力：[`circle-community`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 CircleGroup 拥有协作单元，Conversation 只拥有消息会话
- 决策：CircleGroup 拥有协作单元，Conversation 只拥有消息会话。
- 理由：以圈子或组织主页内的群为协作单元，统一交流、资料与公告。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`circle-group-chat-binding-sync`](./circle-group-chat-binding-sync/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- feature flag、观测、SLO 验证与回滚方案。
- consumer group pending 数、reclaim 次数、DLQ 率和 source-event replay 率必须进入 health、Prometheus 与告警。
- CircleGroup 创建至 `conversationId` 回写 P95 ≤ 3 秒。
- 成员 active/left/removed/role_changed 至 Chat 名册收敛 P95 ≤ 3 秒。
