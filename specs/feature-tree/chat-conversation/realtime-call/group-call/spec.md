# L3 规格：group-call — 2~32 人多人通话

> **层级**：L3_subfeature（隶属 L2 `realtime-call`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call`

## 定位

2~32 人多人语音/视频通话（对标 FaceTime 32 人上限），含中途邀请/加入/离开、成员管理、群聊/圈子入口集成。

## 职责边界

- 覆盖 Phase 2 全部功能（F6~F9）
- 多人房间管理：JoinCall/LeaveCall/InviteToCall
- 32 人上限校验（超出拒绝 + 错误码）
- 最后一人离开→通话自动结束

## 与父/子节点关系

- 父节点 `realtime-call` 定义全局约束（32 人上限、Simulcast 策略）
- 子节点 `multi-party-room-contract`（L4 Story）承载多人房间管理契约

详细规格见父节点 `realtime-call/spec.md` §3.1 Phase 2。
