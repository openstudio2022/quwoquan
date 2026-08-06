# L3 Story：Gathering 会话绑定 (`gathering-conversation-binding`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-003](../design.md#dec-003)、[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为已经有效参与一次 Gathering 的用户，
我希望加入后默认进入本次活动群聊，并从顶部看板查看公告、时间地点、计划、日历、任务与文件，
从而无需再拉群、交换联系方式或学习独立 Workspace。

## 2. 范围与非目标

### In Scope

- Publish 前确保唯一 contextual activity room 与 Circle-owned binding state。
- Participation/Organizer authority 到 Chat membership/access 的可靠投影、默认消息入口与撤权。
- BoardCard/BoardView 对 Circle、Chat 与可选能力公开投影的 typed 组合，以及绑定会话内消息、公告、文件索引和通话复用。

### Out of Scope

- Conversation、ConversationMembership、Message、Announcement、已读、附件索引与通话信令，由 `chat-conversation` 负责。
- 参与者审批与容量，由 [`gathering-participant-roster`](../gathering-participant-roster/spec.md) 负责。
- Gathering lifecycle、Revision、Outcome 与 Plan 写状态；Board 不拥有这些事实。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Publish 前绑定唯一活动群聊

- 每个 Gathering 恰有一个 Chat contextual Conversation；Circle 只拥有 conversation reference 与 binding state，不拥有 ConversationMembership、Message 或 Announcement。
- Chat 的 room ensure 必须幂等并在 Publish 前 ready；失败时 Gathering 保持草稿，不公开、不接受响应，也不回退普通建群。

<a id="req-002"></a>
### REQ-002 有效参与后活动群聊成为默认主场

- 只有有效 GatheringParticipation 或未撤销 Organizer authority 可获得相应 participant/admin membership；待审批申请、邀请待响应与 AvailabilityWatch 不得进入。
- 邀请待响应者只在 Notification 的 AppMessage 收件箱看到 disclosure-safe typed 邀请；接受/拒绝回到 Circle owner operation，接受提交前不得读取活动群消息、名单或 after_join 精确地点。
- 有效参与者再次打开任何活动入口默认进入活动群聊；公开未加入、待审批或访问已撤销者进入裁剪后的 Gathering 详情。
- Participation 已成功但 access projection 尚未收敛时显示可恢复等待态并幂等重放，不撤销 owner 成功、不伪造可访问。

<a id="req-003"></a>
### REQ-003 membership 是访问投影而非 Participation 真相

- active/closed Participation 与 Organizer grant/revoke 通过 durable outbox/inbox 投影 membership；Chat membership 不得反向创建 Participation、占席或改变 Gathering。
- 退出、移除、Block、安全退出、取消或权限撤销后，room、文件、计划和精确地点访问必须在 SLO 内收敛；重放事件不得产生重复 membership。

<a id="req-004"></a>
### REQ-004 Board 是同一活动群聊内的可重建读模型

- 活动群聊顶部固定呈现 BoardCard，BoardView 组合 Circle 的 Gathering/Participation/Plan、Chat 的 Announcement/AssetIndex 与可选 Calendar/Map 状态。
- Board 不拥有写状态；结构化时间/地点/取消/Outcome 由 Circle 改变并投影 system card，自由公告/置顶/已读/发言策略和文件索引由 Chat 改变。
- 缺少可选能力时隐藏对应区域或结构化 unavailable；不得建立 WorkspaceManifest、模块安装聚合、第二消息流或第二文件存储。

<a id="req-005"></a>
### REQ-005 活动群聊复用 Chat 消息、文件与实时通话

- 图片、视频与文件继续是 Message/Media owner 的事实，活动文件页只读 Chat 索引；群通话复用绑定会话既有能力，不新建语音房聚合或行动键。
- 取消后 access mode、完成后的回顾窗口与最终只读策略由 canonical contracts 决定；Circle lifecycle 不复制 Chat posting 状态。

<a id="req-006"></a>
### REQ-006 普通群聊与活动群聊并列不合并

- C 位“发起群聊”只创建普通 Conversation，不创建 Gathering；“发起活动”自动 provision contextual room。已有普通会话可作为活动来源，但原成员必须成功响应后才进入活动群聊。
- capacity=2 仍使用两人活动群聊，不复用普通 direct；ConversationMembership 不自动建立 mutual。

<a id="req-007"></a>
### REQ-007 服务本地契约引用边界

- 字段、operation、route、surface、event、error、metric 与恢复语义只引用所属服务 contracts 或跨服务 metadata；本节点不得复制 DTO/wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/fields.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/events.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/fields.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 room-ready Publish 与有效参与后默认进入群聊

- GIVEN 一个尚未发布的 Gathering，Chat room ensure 首次失败后恢复，且一名受邀者尚无 room access。
- WHEN Host 重试发布，受邀者从 Notification typed 邀请调用 Circle accept，另一参与者经申请审批成为有效 Participation 并打开活动。
- THEN room ensure 幂等只产生一个 contextual Conversation，Publish 只在 binding ready 后成功，参与者在 access ready 后默认进入消息。
- AND 邀请待响应与待审批者都不能进入或读取群内容，群通话复用 Chat，Participation 与关系事实不由 Notification 或 membership 反向改变。

<a id="gwt-002"></a>
### GWT-002 Board 同源组合且撤权可靠收敛

- GIVEN 有效参与者在 Board 中看到 Circle 结构化活动事实、Chat Announcement/AssetIndex 和可选 Plan/Calendar。
- WHEN Host 更新活动、发布公告，随后参与者退出或被安全移除，投影期间发生重复事件与进程重启。
- THEN Board 各区域只由 owner 事实更新且可重建，重复事件不产生重复 membership/announcement。
- AND 退出/移除后写权限与敏感访问在 SLO 内撤销，用户回落裁剪详情，仍保留通知/举报/申诉入口。

<a id="gwt-003"></a>
### GWT-003 发起活动与发起群聊保持并列

- GIVEN 用户从 C 位或已有普通会话分别选择发起活动和发起群聊。
- WHEN 两条路径完成。
- THEN 发起活动创建 Gathering 及其唯一 contextual room，发起群聊只创建普通 Conversation。
- AND 普通会话成员未响应 Gathering 前不进入活动群聊，capacity=2 也不复用 direct。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-003](../design.md#dec-003)、[L2 DEC-005](../design.md#dec-005)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 活动群聊、Board 与访问投影尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Publish 前唯一 contextual room、Participation/Organizer 双投影、默认消息入口、Board typed projection、Announcement/AssetIndex、取消/完成 access mode、退出/Block/安全移除撤权、普通群聊并列语义与 App 消息可靠性验收。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 在 local_contract、真实 api_integration、杀进程/重连/重复事件与跨域 user_acceptance 中通过；未授权 room access、重复 room/membership、Workspace 第二真相和 direct 复用为零。
- 依赖：父 L2 `OPEN-003`、Chat message reliability、后续 route/surface/Board contracts 与 production Remote App。
