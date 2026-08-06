# L3 Story：活动群聊目标引用与协作治理 (`trip-placement-collaboration`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为 Host、参与者或领队，我希望活动群聊与小趣始终明确正在查看或修改的 Gathering/Plan，并在上下文含多个候选时先让我选择，从而避免改错计划或借聊天成员身份越权。

## 2. 范围与非目标

### In Scope

- activity room/Board/card 中的 canonical Gathering/Plan reference。
- 多 Gathering/Plan 上下文的候选解析、用户消歧与零写入边界。
- GatheringParticipation/Organizer authority 到计划写权限、Chat ConversationMembership 到 room access 的 owner 分离。
- legacy TripMembership/TripPlanPlacement 到当前 Participation/authority 与 Board/card reference 的历史 crosswalk。

### Out of Scope

- Chat/Circle/Gathering 成员真相、关系等级或有偿组织服务。
- 独立 Travel Placement/Membership 写对象、普通群成员自动参与、Travel App 挂载界面或兼容 Reader。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 目标引用与写权限必须显式且来源可追溯

- 每个 activity Board 固定绑定其 Gathering，并通过 canonical reference 打开可选 Plan；消息、卡片或 Assistant context 可以引用其他 Gathering/Plan，但不得改变 Board 绑定。
- Assistant 或 App 只有在目标 Gathering/Plan 唯一且仍可见时才能执行 owner command；否则必须列出有权候选并等待用户消歧，期间零写入。
- Plan proposal/commit 在执行时重验 GatheringParticipation 或 Organizer authority；Chat ConversationMembership 只授予 room access，不得复制或反推参与/计划权限。
- legacy Placement/Membership 仅通过签名 crosswalk 解释迁移来源，不是当前 route、Reader、Writer 或权限输入。

## 4. 契约引用

- current owner：Circle `GatheringParticipation`、Organizer authority 与 `GatheringPlan` canonical reference；Chat `ConversationMembership`、Board/card projection。
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/operations.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- historical crosswalk：`TripMembership -> GatheringParticipation/Organizer authority`，`TripPlanPlacement -> activity Board/card canonical Gathering/Plan reference`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多目标上下文不会误路由写入

- GIVEN 一个用户可访问多个旅行 Gathering，当前会话消息或 Assistant context 同时引用两个 Plan，用户未显式选择目标。
- WHEN 用户要求“小趣把晚餐改到八点”。
- THEN 系统返回可理解且经过 viewer 权限裁剪的 Gathering/Plan 候选并等待选择，所有 current Revision 均不变化。
- AND 用户选定后只对目标 Plan 重验 Participation/Organizer authority 与 revision；其他 Gathering/Plan 不产生 command、event 或 Board 变化。

## 6. 依赖

- 前置要求：Conversation/Gathering/Plan typed reference、Board binding 和主体权限可读。
- 上游事实：activity room/Board context、消息/卡片 canonical reference、owner authority event 与用户选择。
- 下游结果：Assistant routing context、GatheringPlan command reachability 与 typed object card。
- 父级设计：`DEC-001`、`DEC-002`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Board 目标引用与跨域消歧尚未贯通

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Chat Board/card production Remote、Circle authority event、Assistant Context Reader 与 App 消歧交互的统一接线；当前不能用已删除的 Travel Placement 页面或对象代替。跨服务 API integration 与 Android/iPhone UAT 均未闭合。
- 完成判定：`GWT-001` 由 Circle/Chat/Assistant local_contract、真实跨域 api_integration 与 Android/iPhone user_acceptance 直接覆盖；重复事件、重连和进程恢复后仍只修改明确目标，越权与误路由写入为零。
- 依赖：`gathering-conversation-binding`、Chat Board contracts/Remote、Circle authority source event 与 Assistant Context Reader。
