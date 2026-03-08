# L4 Story：multi-party-room-contract — 2~32 人多人房间管理契约

> **层级**：L4_story（隶属 L3 `group-call`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call/group-call`

## 定位

2~32 人多人房间管理契约的可验收交付：Join/Leave/Invite 操作、32 人上限校验、最后一人离开自动结束。

## 职责边界

- 房间操作：JoinCall、LeaveCall、InviteToCall
- 32 人上限：超出拒绝加入并返回错误码
- 事件：call.participant_joined、call.ended（最后一人离开）
- 对应 L2 `realtime-call` acceptance A22~A24、A29、A34

## 与父节点关系

- 父节点 `realtime-call/spec.md` §4.1 CallSession、§4.4 API 端点、§6.2 业务约束（32 人上限）
- 父节点 `group-call/spec.md` 定义多人通话职责
- 详细规格与验收标准见 L2 `realtime-call/spec.md` 及 `realtime-call/acceptance.yaml`。
