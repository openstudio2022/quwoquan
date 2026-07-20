# L3 Story：group-call — 2～32 人多人通话

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；商用验收 pending/partial
> **真相源**：`contracts/metadata/rtc/call_session/**`

## 最小价值

用户从合法 Conversation/Circle 上下文发起 `audio` 或 `video` 多人通话，被邀请人可加入，
参与者可离开或继续邀请，聚合始终保持 32 人上限与确定的结束语义。

## Canonical 合同

- CallParticipant 是 CallSession owned entity，不存在独立参与者 Store/Facade。
- 多人行为只使用 `InviteToCall`、`JoinCall`、`LeaveCall`、`ReportMediaConnected`。
- 第 33 人加入返回 `RTC.USER.call_full`。
- `LeaveCall` 只让当前参与者离开；最后一人离开才以 `last_leave` 结束 CallSession。
- `inviteStatus` 使用
  `pending | ringing | accepted | declined | expired | cancelled`。
- `ParticipantStatus` 使用
  `invited | ringing | connecting | connected | left | timeout`。
- 邀请与参与者事件经 realtime-gateway per-user channel 投递。
- 当前 metadata 没有呼叫链接签发/解析 operation；页面不得展示假链接入会能力。

## 信任与交集

- 候选资格由关系/会话能力与服务端权限决定，不由交集分数决定。
- `known | possibly_unknown` 仅用于邀请/来电/入会前的来源和隐私提示。
- 新成员进入时可显示一次轻量风险提示；通话页不常驻共同兴趣或共同关系列表。

## Out of Scope

- 超过 32 人的会议、主持人审批、链接入会、录制。
- 独立 Participant command/query 边界。
- 用 Circle/Conversation membership 直接写 CallSession 文档。

## 验收

以本节点 `acceptance.yaml` 的 join/leave/limit、invite/trust 与 screen-share 协同 GWT 为准。
真实多人媒体与设备证据未 recorded 前保持 pending。
