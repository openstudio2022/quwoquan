# L3 Story：group-call — 2～32 人多人通话 (`group-call`)

> 所属能力：[`realtime-call`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，我希望2～32 人 CallSession 的直接邀请、加入、离开、上限、信任证据与结束语义，从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- InviteToCall/JoinCall/LeaveCall/ReportMediaConnected
- CallParticipant owned entity 与 32 人边界
- realtime-gateway 参与者事件
- 来电/入会前 known/possibly_unknown 提示
- participantCount/maxParticipants
- inviteStatus/participant status
- last_leave 与 participant realtime events

### Out of Scope

- 呼叫链接入会、主持人审批、超过 32 人会议
- 独立 CallParticipant Store/Facade
- 链接入会、独立 participant resource、页面视觉

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多人加入、离开与 32 人边界

- join/leave/limit/last_leave 与重复命令在真实 Mongo/Redis 集成中闭环。

<a id="req-002"></a>
### REQ-002 直接邀请与最小信任证据

- 邀请、接受/拒绝/过期和信任提示均消费同一 CallSession/event 输出。

<a id="req-003"></a>
### REQ-003 当前 metadata 没有呼叫链接签发/解析 operation

- 当前 metadata 没有呼叫链接签发/解析 operation；页面不得展示假链接入会能力。

<a id="req-004"></a>
### REQ-004 多人参与者集合与事件保持一致

- 32/33 人、重复 join/leave、最后一人离开和越权负例全部有真实 store 证据。

## 4. 契约引用

- canonical：`rtc/rtc/call_session/operations.yaml#JoinCall`
- canonical：`rtc/rtc/call_session/operations.yaml#LeaveCall`
- canonical：`rtc/rtc/call_session/fields.yaml#CallParticipant`
- canonical：`rtc/rtc/call_session/operations.yaml#InviteToCall`
- canonical：`rtc/rtc/call_session/fields.yaml#CallInviteStatus`
- canonical：`rtc/rtc/call_session/fields.yaml#TrustRelation`
- canonical：`rtc/rtc/call_session/object.yaml#members`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多人加入、离开与 32 人边界

- GIVEN 已存在一个未结束的多人 audio/video CallSession。
- WHEN 被邀请人加入、成员离开、第 33 人尝试加入、最后一人离开。
- THEN participantCount 与 owned participants 一致
- AND 第 33 人收到 call_full
- AND 最后一人离开写 ended/last_leave。

<a id="gwt-002"></a>
### GWT-002 直接邀请与最小信任证据

- GIVEN 当前参与者可从合法会话/关系候选中选择 invitee。
- WHEN 调用 InviteToCall 邀请 known 或 possibly_unknown 成员。
- THEN inviteStatus、invitedBy 与 realtime 事件一致；来电/入会前展示来源和必要风险提示。

<a id="gwt-003"></a>
### GWT-003 多人参与者集合与事件保持一致

- GIVEN CallSession 未结束且当前 actor 是合法参与者。
- WHEN actor 邀请成员，成员加入/离开，或并发命令命中人数上限。
- THEN owned participants、participantCount、inviteStatus、receipt/outbox 与 realtime payload 一致。

## 6. 依赖

- 前置要求：[`realtime-call`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
