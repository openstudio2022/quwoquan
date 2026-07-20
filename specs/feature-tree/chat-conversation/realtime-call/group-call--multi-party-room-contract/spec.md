# L3 Story：multi-party-room-contract — 多人房间聚合合同

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；验收 pending

## 最小价值

CallSession 在并发邀请、加入、离开与达到上限时，保持 owned participant 集合、人数计数、
邀请状态和结束事实一致。

## Contract

- `InviteToCall(inviteeIds)` 只能由现有参与者调用，新增/更新 owned participant。
- `JoinCall` 返回 CallSession、LiveKit token 与 `livekitUrl`，重复 join 幂等。
- `LeaveCall` 不等价于 HangupCall；仍有参与者时会话继续。
- participantCount 不超过 maxParticipants，且 maxParticipants 不超过 32。
- 最后一人离开写 `status=ended`、`endReason=last_leave`。
- 参与者加入/离开与结束事件从 CallSession outbox 发布，经 realtime-gateway 投递。
- 非参与者、被拉黑、已结束和满房请求 fail-closed，且不产生状态写入或事件。

## 边界

- 没有独立 CallParticipant Repository、Store 或 HTTP 资源。
- 没有链接入会 operation；若未来需要，先建立短期凭据、权限、过期与审计合同。
- 页面候选来源与信任提示是 read composition，不进入聚合 authoritative fields。

## 验收

覆盖 32/33 人边界、重复 join/leave、最后一人离开、并发邀请、事件 payload 与越权负例；
见本节点 `acceptance.yaml`。
