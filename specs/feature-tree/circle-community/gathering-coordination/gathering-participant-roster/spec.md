# L3 Story：Gathering 参与者名单 (`gathering-participant-roster`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为想响应一次 Gathering 的用户，
我希望通过公开加入、申请或邀请获得唯一、清晰、可恢复的 Participation 结果，并知道席位、重大变更和可见名单，
从而无需理解多套成员对象，也不会因为参与而被自动建立关系。

## 2. 范围与非目标

### In Scope

- root-owned GatheringParticipation 的邀请待响应、申请待审批、有效参与与关闭语义。
- 公开加入、申请/审批、邀请/接受、退出、移除、恢复、重大变更确认、出席与容量裁决。
- Host/Organizer 与 Participation 的席位/权限分离，以及 Roster、计数、AvailabilityWatch 和隐私展示口径。
- 邀请事实经 Circle 事务 outbox 可靠投影到 Notification 既有 AppMessage 收件箱，并由消息卡 action 回到 Circle typed operation。

### Out of Scope

- Gathering lifecycle、Revision 与 Outcome，由 [`gathering-lifecycle`](../gathering-lifecycle/spec.md) 负责。
- 群会话成员同步，由 [`gathering-conversation-binding`](../gathering-conversation-binding/spec.md) 负责。
- Persona Follow/mutual、CircleMembership 与 ConversationMembership；这些对象不能充当 Participation。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每位 Persona 每场活动只有一条 Participation

- 邀请待响应、申请待审批、有效参与与已关闭必须由同一 root-owned Participation 表达；每个 Persona/Gathering 组合不得出现第二当前记录。
- 公开加入、申请、审批、邀请、接受、拒绝、退出、移除与恢复必须使用语义明确的 owner operation；禁止通用 SetStatus。

<a id="req-002"></a>
### REQ-002 准入来源与 Host 决策保持可区分

- 开放策略可直接形成有效 Participation，审批策略先形成待审批申请，邀请策略先形成待响应邀请；申请通过与邀请接受都直接进入有效参与，不再增加 mandatory match/intent。
- Reject 与 Remove、Withdraw 与 Leave、邀请撤销与参与撤权必须保持不同业务语义和审计结果。

<a id="req-003"></a>
### REQ-003 容量不得被并发越过

- 占用席位只由有效 Participation 与未过期邀请保留派生；待审批申请不占席，Organizer 若未实际参加不占席。
- 并发 Join/Approve/Accept 必须在 Gathering 与 Participation owner 版本边界内裁决，永不超员；重复意图重放原结果。
- 满员后拒绝新响应；开场前退出/移除释放席位并可重开，开场后关闭普通准入且不补招。

<a id="req-004"></a>
### REQ-004 重大变更、退出与重新响应可恢复

- 每条有效 Participation 对重大 GatheringRevision 分别确认；拒绝或逾期按 owner policy 关闭、释放席位并撤销访问，不能把沉默当同意。
- 普通退出可在准入重新开放时按 owner policy再次响应；Host 移除需要显式恢复，安全移除在该 Gathering 内禁止重入。

<a id="req-005"></a>
### REQ-005 名单、计数、申请答案与关系隐私

- Roster 与计数由 Participation 派生，不作为独立可写事实；未加入者只看到 disclosure 允许的数量或公开选择，不能读取申请答案、联系方式或完整名单。
- 申请答案只对有权 Organizer 可见并按 owner retention 删除；Report legal hold 只能通过所属治理合同延长。
- Participation、ConversationMembership、CircleMembership、Follow 与 mutual 相互独立；加入、到场、完成不自动改变关系。

<a id="req-006"></a>
### REQ-006 Host 权力、安全移除与参与者权利

- Host 可审批、拒绝、邀请与移除，但不能绕过容量、读取不必要敏感资料、静默更改重大承诺或无审计移除。
- 被移除者保留裁剪通知、举报与申诉入口；Block、Report 或安全移除优先收敛 room、文件、计划和精确地点权限。

<a id="req-007"></a>
### REQ-007 服务本地契约引用边界

- 字段、operation、event、error、metric 与恢复语义只引用所属服务 contracts；本节点不得复制 DTO/wire 定义。

<a id="req-008"></a>
### REQ-008 邀请消息闭环不转移 Participation 所有权

- Circle 在邀请、接受、拒绝、撤回和 Gathering 取消的 owner 事务中写入 outbox；Notification 的 `AppMessage` 是消息主战场的最小既有卡片边界，只保存可重建投影，Chat 不拥有或修改 Participation。
- `GatheringInvitationChanged` 只携带 canonical gathering、inviter/recipient、Purpose 摘要、按未加入 viewer 裁剪的 schedule/place、Participation version、过期时间与 accept/decline action intent；禁止携带 conversationId、群消息、参与名单、申请答案或 after_join 精确地点。
- action intent 必须映射到 Circle `AcceptGatheringInvitation` / `DeclineGatheringInvitation` typed operation，并由 authenticated recipient、Gathering version 与 Participation version 联合门禁；非收件人、已撤回、已过期或已取消后的点击返回 canonical failure。
- Notification 按 gatheringId+recipient 唯一折叠并以 Participation version/terminal precedence 抵御重放与乱序；邀请接受后仍由既有 membership projection 授予 room access，不能在消息投影阶段提前入群。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/errors.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/fields.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/object.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 三种准入来源共享一条 Participation 且不超员

- GIVEN 一个剩余席位有限且同时存在公开加入、待审批申请和未过期邀请的 Gathering。
- WHEN 多个 Persona 并发 Join/Approve/Accept，其中包含同一 Persona 的重复意图。
- THEN 有效参与与邀请保留总数不超过容量，每位 Persona 只有一条 Participation，重复请求重放原结果。
- AND 待审批申请不占席，超出容量返回 canonical 满员结果且不产生 room access。

<a id="gwt-002"></a>
### GWT-002 重大变更、退出/移除和关系保持独立

- GIVEN 一个已有有效参与者的 Gathering 发生重大变更，其中一人接受、一人拒绝、一人被 Host 移除。
- WHEN owner 提交确认结果并投影 room access。
- THEN 接受者保持有效，拒绝者按 policy 退出并释放席位，被移除者获得不同原因、裁剪通知与申诉入口。
- AND 三人的 Follow/mutual/CircleMembership 不因 Participation 变化被自动创建或删除。

<a id="gwt-003"></a>
### GWT-003 安全移除即时撤权且不可重入

- GIVEN 有效参与者触发 Block/Report 与安全移除。
- WHEN Circle 提交安全关闭并向下游投影撤权。
- THEN room、文件、计划和精确地点访问在 SLO 内收敛，历史证据仅按审计策略裁剪只读。
- AND 该 Persona 不能在同一 Gathering 重新加入，普通 Host 恢复操作也不得绕过安全决定。

<a id="gwt-004"></a>
### GWT-004 准入控制按时间、版本与容量派生且不可绕过

- GIVEN 一个尚未开场、具有明确准入截止时间与 AdmissionControl 版本的 Gathering。
- WHEN Host 暂停或恢复准入，或请求发生在截止、满员与开场边界。
- THEN 暂停与恢复同时校验 Gathering 和 AdmissionControl 版本，陈旧版本被拒绝，满员状态不会因恢复被伪装成可加入。
- AND 到达准入截止或开场后保持关闭，普通 Resume 不能重新打开。

<a id="gwt-005"></a>
### GWT-005 容量切片只由真实占席派生并随释放重开

- GIVEN 同时存在有效参与、未过期与已过期邀请、待审批申请和未实际参与的 Organizer。
- WHEN 查询容量、下调容量或有效参与者在开场前退出。
- THEN 只有有效参与和未过期邀请占席，容量不得降到已占席以下，重大容量变更只要求有效参与者确认。
- AND 席位释放后准入按当前策略派生重开，不创建或改写 AvailabilityWatch 等第二套 waitlist 事实。

<a id="gwt-006"></a>
### GWT-006 邀请消息可靠投影并由 Circle 执行动作

- GIVEN Host 邀请一名尚无 Gathering room access 的 Persona，披露策略将精确时间或地点设为 after_join。
- WHEN Circle 提交邀请并重复投递同一 outbox 事件，随后发生接受、拒绝、撤回、过期或 Gathering 取消。
- THEN Notification 主消息收件箱只出现一张 typed 邀请卡，未泄露群内容、名单或 after_join 精确信息，重放不重复，终态或过期后 action 被移除。
- AND 只有收件人能以卡片携带的 owner versions 调用 Circle accept/decline；接受后 Participation 先成为 active，再由 membership projection 入群，取消后点击返回 canonical invitation inactive。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-004](../design.md#dec-004)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Participation、容量、安全撤权与邀请消息目标合同未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 App generated accept/decline、名单/审批/退出交互与真实账号 Remote UAT，以及重大变更确认、出席和跨域撤权的最终准出证据；root-owned Participation、seat hold、Organizer 席位分离、安全不可重入及邀请 outbox 到 Notification AppMessage 的幂等投影已有 local_contract/api_integration 证据。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003`、`GWT-004`、`GWT-005`、`GWT-006` 对应跨域 user_acceptance 通过；App 只调用 generated typed operation，邀请重放只保留一张卡、终态 action 不复活、接受前不授予 room access，且超员、同人多记录、半加入、未授权申请答案、自动 mutual 与撤权超时为零。
- 依赖：父 L2 `OPEN-001`、`OPEN-003`，批准后的 App ContractGraph handoff，以及后续真实账号 Remote UAT。
