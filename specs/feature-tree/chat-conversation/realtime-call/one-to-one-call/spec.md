# L3 Story：one-to-one-call — 1v1 实时通话 (`one-to-one-call`)

> 所属能力：[`realtime-call`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，我希望互相关注门禁下的 1v1 audio/video 通话、媒体 connected、异常收尾、离线来电与会话通话记录，从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- Initiate/Answer/Reject/Cancel/Hangup/ReportMediaConnected
- no_answer、忙线、重复命令与接听/取消竞态
- realtime-gateway 在线来电与三端离线来电计划
- CallEnded 到 Conversation system_call_log
- initiated/ringing/connecting/in_call/ended
- no_answer、命名结束意图与 ended 终态
- ReportMediaConnected、actor-scoped receipt、BOLA

### Out of Scope

- 多人房间
- 通话录制、端到端媒体加密和独立通话历史页
- 离线 Push provider、页面视觉、媒体 QoE rollup

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 合法关系发起并以媒体 connected 进入通话

- AnswerCall 成功与媒体 connected 被明确区分，至少两人 connected 后才进入 in_call。

<a id="req-002"></a>
### REQ-002 拒绝、取消、无应答与会话记录一致收尾

- 四种收尾、重复命令、取消/接听竞态和 chat durable projection 均可验证。

<a id="req-003"></a>
### REQ-003 后台、锁屏与被终止状态的离线来电

- provider、设备注册、平台回调、接听/拒绝与真实设备 readback 全链通过。

<a id="req-004"></a>
### REQ-004 媒体传输可用后调用 `ReportMediaConnected`

- 媒体传输可用后调用 `ReportMediaConnected`；不能把 AnswerCall 成功等同媒体已接通。
- 离线 Push 是商用必需但当前未实现，不能用在线事件或本地通知冒充。
- Conversation 存在、在线 presence 或交集分数都不能放宽门禁。

<a id="req-005"></a>
### REQ-005 AnswerCall、ReportMediaConnected 与 no_answer 严格分离

- 状态、startedAt、participant status 与 endReason 在真实 store 中一致。

<a id="req-006"></a>
### REQ-006 CAS、幂等 receipt 与 outbox 原子提交

- state、receipt、outbox 同 transaction，并通过非参与者与重放负例。

<a id="req-007"></a>
### REQ-007 事件在线投递统一走 realtime-gateway；媒体连接由 LiveKit 负责

- 事件在线投递统一走 realtime-gateway；媒体连接由 LiveKit 负责。

## 4. 契约引用

- canonical：`rtc/rtc/call_session/operations.yaml#InitiateCall`
- canonical：`rtc/rtc/call_session/operations.yaml#AnswerCall`
- canonical：`rtc/rtc/call_session/operations.yaml#ReportMediaConnected`
- canonical：`rtc/rtc/call_session/operations.yaml#RejectCall`
- canonical：`rtc/rtc/call_session/operations.yaml#CancelCall`
- canonical：`rtc/rtc/call_session/operations.yaml#HangupCall`
- canonical：`rtc/rtc/call_session/events.yaml#CallEnded`
- canonical：`rtc/rtc/call_session/events.yaml#CallRinging`
- canonical：`rtc/rtc/call_session/fields.yaml#CallStatus`
- canonical：`rtc/rtc/call_session/object.yaml#business_rules`
- canonical：`rtc/rtc/call_session/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 合法关系发起并以媒体 connected 进入通话

- GIVEN 双方互相关注且未拉黑，被叫可接听。
- WHEN 主叫发起 video 通话，被叫 AnswerCall 后 LiveKit 媒体可用并上报 ReportMediaConnected。
- THEN callType 为 video，状态依次收敛到 initiated/ringing/connecting/in_call，双方渲染真实媒体。

<a id="gwt-002"></a>
### GWT-002 拒绝、取消、无应答与会话记录一致收尾

- GIVEN CallSession 处于 initiated 或 ringing。
- WHEN 被叫拒绝、主叫取消、30 秒未接，或通话中一方挂断。
- THEN 聚合进入 ended，endReason 分别为 rejected/cancelled/no_answer/normal，并只投影一条 system_call_log。

<a id="gwt-003"></a>
### GWT-003 后台、锁屏与被终止状态的离线来电

- GIVEN 被叫不在线或 App 在后台/锁屏/被系统终止，设备已完成合法 push 注册。
- WHEN rtc-service 发布未过期的 CallRinging。
- THEN iOS/Android/Web 按 capability 使用 PushKit/FCM/Web Push 唤醒或明确降级，重复/过期 payload 不重复响铃。

<a id="gwt-004"></a>
### GWT-004 AnswerCall、ReportMediaConnected 与 no_answer 严格分离

- GIVEN 一个合法的 audio 或 video CallSession 已发起。
- WHEN 被叫接听并建立媒体，或 30 秒未接。
- THEN 接听只推进 connecting
- AND 媒体上报后才进入 in_call
- AND 未接进入 ended/no_answer。

<a id="gwt-005"></a>
### GWT-005 CAS、幂等 receipt 与 outbox 原子提交

- GIVEN 同一 actor 对同一 CallSession 并发或重复发送命名 command。
- WHEN Mongo CAS 发生纯竞态、同 key 重放或目标态已满足。
- THEN 服务端有限重载重放
- AND 同 key 返回首次结果
- AND no-op receipt 不递增 version
- AND outbox 不重复。

## 6. 依赖

- 前置要求：[`realtime-call`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 合法关系发起并以媒体 connected 进入通话

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：AnswerCall 成功与媒体 connected 被明确区分，至少两人 connected 后才进入 in_call。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 拒绝、取消、无应答与会话记录一致收尾

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：四种收尾、重复命令、取消/接听竞态和 chat durable projection 均可验证。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 AnswerCall、ReportMediaConnected 与 no_answer 严格分离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：状态、startedAt、participant status 与 endReason 在真实 store 中一致。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 CAS、幂等 receipt 与 outbox 原子提交

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：state、receipt、outbox 同 transaction，并通过非参与者与重放负例。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效
