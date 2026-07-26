# L2 Design：实时音视频通话 (`realtime-call`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：1v1 与多人通话共享 `CallSession/CallParticipant` 状态机、realtime-gateway 信令、LiveKit 媒体、离线投递和会话记录边界。

## 1. 背景、目标与非目标

- 设计目标：让用户在满足关系与成员权限时发起、接听、拒绝、取消和结束 1v1 或不超过 32 人的实时音视频通话，并通过同一 `CallSession/CallParticipant` 状态机、realtime-gateway 信令、LiveKit 媒体和会话记录获得可恢复结果。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`call-experience`](./call-experience/spec.md)：connecting/ringing/waitingPeer/inCall/reconnecting/weakNetwork/peerNoAnswer/peerLeft/ended 全覆盖。
- [`group-call`](./group-call/spec.md)：join/leave/limit/last_leave 与重复命令在真实 Mongo/Redis 集成中闭环。
- [`media-infrastructure`](./media-infrastructure/spec.md)：Room、mediaAccess、auth_ack、wire type、ReportMediaConnected 与状态机有端云证据。
- [`one-to-one-call`](./one-to-one-call/spec.md)：AnswerCall 成功与媒体 connected 被明确区分，至少两人 connected 后才进入 in_call。

## 3. 端云与数据流

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 信令状态与媒体连接状态分离并以服务端通话会话收敛
- 决策：信令状态与媒体连接状态分离并以服务端通话会话收敛。
- 理由：信令、媒体与会话记录必须绑定同一权威通话状态，才能避免多端竞态和伪连接终态。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`call-experience`](./call-experience/spec.md)、[`group-call`](./group-call/spec.md)、[`media-infrastructure`](./media-infrastructure/spec.md)、[`one-to-one-call`](./one-to-one-call/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 离线来电与媒体 QoE 未形成真实证据时，设计保持 blocked，不用声明或占位告警伪装完成。
- 具体编码层、FEC/NACK 等属于 LiveKit/runtime 配置能力；未有受控运行证据时不在产品规格中。
- SLS 告警消费 `connection_lost`，LiveKit 告警只消费官方。
- 完成告警触发、通知、恢复与 prod `gray_initial` 回滚演练。
- 离线来电采用 `Integration attempt + result outbox -> Redis Stream -> Notification attempt inbox -> per-device timeline` 单轨；`external_accepted`、provider result、presentation ACK 不得互相代写。
- B10 operator readback 仅携带 call/device/session 摘要和 receipt reference；hosted release receipt 必须由 `prod-hosted` service-plane 原子 CAS 提交并回读验签，本机 release-state 只是可删除缓存。
