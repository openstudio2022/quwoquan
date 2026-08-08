# L2 Business Capability：群聊创建与成员管理 (`group-creation-member-management`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环。

## 2. 范围与非目标

### In Scope

- 三来源选人、原子建群、成员添加/移除/主动退出
- owner/admin/member 权限矩阵、群主转让、管理员与公告设置
- 1000 user 成员上限、relationship gate、结构化错误与 Inbox 回流

### Out of Scope

- 圈子与 CircleGroup 自身生命周期
- 企业组织通讯录、邀请链接、二维码入群与入群审批；当前发布不展示相应入口或治理开关，也不创建无调用方的 `JoinRequest` 对象。

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-013`](../../spec.md#scn-013)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-008 / SCN-014`](../../spec.md#scn-014)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`group-candidate-source-orchestration`](./group-candidate-source-orchestration/spec.md)：Mock 与 Remote 候选行为一致且有端云证据。
- [`group-create-flow`](./group-create-flow/spec.md)：api_integration 覆盖成功、非互关、屏蔽、重复请求、边界容量与 outbox。
- [`group-member-roster-version-sync`](./group-member-roster-version-sync/spec.md)：`membersRosterRevision` 与 `updatedAt` 只能由 chat-service 在成员表成功变更后更新。
- [`group-settings`](./group-settings/spec.md)：群设置中显示的成员入口必须可追溯到具体用户对象，方便后续举报/拉黑下沉。
- [`member-add-remove-policy`](./member-add-remove-policy/spec.md)：圈子绑定默认群（`group + circleId`）：跟随圈子绑定关系，不能单独进入 `dissolved`。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 群创建与成员治理能力 SIT

- 三来源候选只经 chat-service 权威 Reader 输出，App 不自行拼装 Inbox、Circle 和关系数据。
- CreateConversation/AddMembers/RemoveMember/LeaveConversation/TransferOwnership 权限与生命周期组合可验证。
- 创建或治理成功后 Conversation、Membership、GroupHome/Inbox 投影与 outbox 一致，失败无部分提交。
- beta/gamma API 与 gamma_local UAT 均有可重复执行证据；prod 只执行只读与受控 smoke。

<a id="req-002"></a>
### REQ-002 私建群可解散；圈子群不可解散，生命周期绑定圈子

- 私建群可解散；圈子群不可解散，生命周期绑定圈子
- 群聊最大人数统一冻结为 `1000`
- 圈子来源必须来自“消息列表可达且我的圈子中存在、并已有 `conversationId` 绑定”的真实圈子
- 所有群会话统一使用 `group` 类型；圈子发起/绑定的默认群通过 `circleId` 标识，而不是独立 `circle` 会话类型
- 私建群允许解散；圈子群禁止解散，危险操作入口必须隐藏
- `route / surface / operation / request context` 必须来自 metadata，禁止继续复用 `chatAddMembers` 旧语义
- 建群失败必须停留在当前页并保留已选成员，便于用户重试
- 发布层仅允许整版发布回退，不在产品内保留“旧发起群聊页”兼容入口

## 6. 契约与依赖

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 群创建与成员治理能力 SIT

- GIVEN 执行“群创建与成员治理能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“群创建与成员治理能力”对应动作。
- THEN 三来源候选只经 chat-service 权威 Reader 输出，App 不自行拼装 Inbox、Circle 和关系数据。
- THEN CreateConversation/AddMembers/RemoveMember/LeaveConversation/TransferOwnership 权限与生命周期组合可验证。
- THEN 创建或治理成功后 Conversation、Membership、GroupHome/Inbox 投影与 outbox 一致，失败无部分提交。
- THEN beta/gamma API 与 gamma_local UAT 均有可重复执行证据；prod 只执行只读与受控 smoke。

## 8. 开放事项

<a id="open-002"></a>
### OPEN-002 群聊四环境端到端证据未闭环（metadata blocked 未解除）

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：群聊四环境端到端证据未闭环（metadata blocked 未解除）
- 完成判定：`SIT-001` 的可观察验收在 alpha/beta/gamma/prod 四环境端到端通过，metadata blocked 解除。

<a id="open-003"></a>
### OPEN-003 群创建与成员治理能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：三来源候选只经 chat-service 权威 Reader 输出，App 不自行拼装 Inbox、Circle 和关系数据。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
