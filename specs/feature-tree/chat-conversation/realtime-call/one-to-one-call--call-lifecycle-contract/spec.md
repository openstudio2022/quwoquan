# L3 Story：call-lifecycle-contract — CallSession 生命周期合同

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；验收 pending
> **父能力**：`chat-conversation/realtime-call`

## 最小价值

CallSession 在并发、重复命令与媒体延迟下仍按同一服务端状态机收敛，App 不需要提交版本或
猜测媒体已连接。

## Contract

- 聚合状态：`initiated | ringing | connecting | in_call | ended`。
- 参与者状态：`invited | ringing | connecting | connected | left | timeout`。
- 结束原因：
  `normal | cancelled | rejected | no_answer | error | timeout | last_leave`。
- `InitiateCall` 创建聚合；同 actor 活跃通话由唯一约束防止双呼。
- `AnswerCall` 只推进到 connecting；`ReportMediaConnected` 才记录媒体 connected，
  至少两人 connected 后进入 in_call。
- `RejectCall`、`CancelCall`、`HangupCall` 与最后一人 `LeaveCall` 使用各自命名意图。
- state CAS、command receipt 与 outbox 在同一 Mongo transaction 提交。
- 重复 idempotency key 返回首次结果；目标态已满足时持久化 no-op receipt 且不递增 version。
- `ended` 后不再发生业务状态推进。

## 边界

- wire `callType` 只使用 `audio/video`。
- token 由 Initiate/Answer/Join 响应直接返回。
- 事件在线投递统一走 realtime-gateway；媒体连接由 LiveKit 负责。
- 本 Story 不包含离线 Push provider、页面视觉或媒体 QoE 汇总，但需要向对应 Story 暴露
  可验证的状态终点。

## 验收

重点验证 answer 与 connected 分离、30 秒 no_answer、取消/接听竞态、重复命令、BOLA、
receipt/outbox 原子性。测试路径见本节点 `acceptance.yaml`；未有 recorded 证据时保持 pending。
