# L2 Business Capability：趣聊体验优化 — 聊天入口/对话页/对话设置全面打磨 (`chat-experience-optimization`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一趣聊入口、会话详情与群聊管理的交互和状态

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“趣聊体验优化 — 聊天入口/对话页/对话设置全面打磨”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-008`](../../spec.md#scn-008)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：统一趣聊入口、会话详情与群聊管理的交互和状态。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`chat-detail-avatar-display`](./chat-detail-avatar-display/spec.md)：展示对方的版本化头像，点击可进入用户主页，缓存加载不得阻塞会话打开。
- [`chat-group-admin-govern`](./chat-group-admin-govern/spec.md)：确认弹窗必须屏幕上下左右居中。
- [`chat-list-local-cache`](./chat-list-local-cache/spec.md)：会话对象缓存遵守 runtime-client-foundation 的本地缓存规则，只从 chat-service canonical Conversation projection 派生且不维护对象策略台账。
- [`chat-list-ui-polish`](./chat-list-ui-polish/spec.md)：`@我` 和 `未读` 的角标数量来自同一模型，并在阅读后按统一规则递减。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 chat experience optimization 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“统一趣聊入口、会话详情与群聊管理的交互和状态”所定义的业务结果；失败终态必须可区分且不得伪造成功。

## 6. 契约与依赖

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 chat experience optimization 能力 SIT

- GIVEN 执行“chat experience optimization 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“chat experience optimization 能力”对应动作。
- THEN 直属 Story 共同交付“统一趣聊入口、会话详情与群聊管理的交互和状态”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 chat experience optimization 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：统一趣聊入口、会话详情与群聊管理的交互和状态。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 chat 域空态与骨架未对齐 design system 标准组件

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 chat 域页面对 `AppEmptyState` 与 `AppSkeleton` 标准组件的接入，
  涉及 Inbox 列表、会话页、设置页、成员搜索、公告与转发面板。当前空态为手写
  `Text`/图标组合，加载态无骨架屏、只有 `AppRequestFeedback`，与 design system
  新组件不一致，跨页面空态视觉与语义漂移。
- 完成判定：`SIT-001` 所述交互与状态在空态与加载态上同样成立——chat 域主表面空态
  经 `AppEmptyState`、列表加载经 `AppSkeleton` 呈现，并有对应 widget 测试
  `spec_ref`。
