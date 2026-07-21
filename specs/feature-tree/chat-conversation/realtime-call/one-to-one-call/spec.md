# L3 Story：one-to-one-call — 1v1 实时通话

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；商用验收 pending/partial
> **真相源**：`contracts/metadata/rtc/call_session/**`

## 最小价值

互相关注且未拉黑的双方可从合法入口发起 `audio` 或 `video` 通话，完成
发起→振铃→接听/拒绝/取消/无应答→媒体建连→挂断，并在关联 Conversation 中看到
`system_call_log`。

## Canonical 合同

- CallSession 状态只允许
  `initiated -> ringing -> connecting -> in_call -> ended`。
- `callType` 只允许 `audio | video`，不接受其他别名。
- 发起/接听分别调用 `InitiateCall` / `AnswerCall`；响应直接携带 provider-neutral
  `mediaAccess(accessToken)`，连接地址仅由 App 环境包注入平台媒体 adapter。
- 媒体传输可用后调用 `ReportMediaConnected`；不能把 AnswerCall 成功等同媒体已接通。
- 拒绝、取消、挂断分别调用 `RejectCall`、`CancelCall`、`HangupCall`。
- 30 秒无应答写 `endReason=no_answer`；`timeout` 保留给系统超时语义。
- 在线 CallRinging/CallEnded 只经 realtime-gateway 单通道投递。
- 离线 Push 是商用必需但当前未实现，不能用在线事件或本地通知冒充。
- CallEnded durable event 由 chat-service 幂等投影为 `system_call_log`。

## 关系与交集

- UI 只消费 relationship capability 决定入口，rtc-service 最终复核。
- Conversation 存在、在线 presence 或交集分数都不能放宽门禁。
- 来电页可展示 `known | possibly_unknown` 与来源作为接听信任证据；通话中不机械展示交集。

## Out of Scope

- 多人房间行为（归 `group-call`）。
- 通话录制、本期 E2EE、独立通话历史聚合页。
- RTC 私有信令连接、聚合 Repository 或 production Mock。

## 验收

以本节点 `acceptance.yaml` 的 GWT 为准；真实媒体接通、timeout/connected、离线来电与
Conversation 回流必须分别有可定位的三层证据，缺失时保持 pending。
