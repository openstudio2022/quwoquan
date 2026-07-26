# L3 Story：media-infrastructure — RTC 媒体基础设施 (`media-infrastructure`)

> 所属能力：[`realtime-call`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，我希望MediaRoomProvider/mediaAccess、当前 LiveKit adapter、TURN、realtime-gateway 事件、离线来电与 RTC media QoE 运行准出，从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- server-issued mediaAccess(accessToken)、App 环境包连接地址与 ReportMediaConnected
- realtime-gateway call/participant/screen_share wire
- PushKit/FCM 商用来电链与 Web 前台 realtime 降级
- QoE emitter、rollup、dashboard/alert 与灰度 readback
- Room/token/TURN/32 人容量
- Gamma-local 设备媒体与 prod-hosted gray_initial
- QoE series、告警与回滚 receipt

### Out of Scope

- 通话录制媒体管道、端到端媒体加密和 P2P 双路径
- 录制媒体管道、端到端媒体加密和 fake media 准出

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 media-infrastructure — RTC 媒体基础设施

- Room、mediaAccess、auth_ack、wire type、ReportMediaConnected 与状态机有端云证据。

<a id="req-002"></a>
### REQ-002 离线来电 provider 与平台唤醒

- provider receipt、设备回调、来电 UI、Answer/Reject 与真实设备 readback 闭环。

<a id="req-003"></a>
### REQ-003 媒体 QoE 黄金指标可查询并驱动灰度

- emitter、去重、rollup、series、dashboard/alert、Gamma/Prod readback 与恢复演练齐全。

<a id="req-004"></a>
### REQ-004 媒体建连后必须调用 `ReportMediaConnected`，使 Participant/CallSession 状态可审计

- 媒体建连后必须调用 `ReportMediaConnected`，使 Participant/CallSession 状态可审计。
- 本地合同锁定取消/未接分母、重连恢复、`connection_lost` wire 值和禁止

<a id="req-005"></a>
### REQ-005 真实运行制品与 QoE 证据满足四环境准出

- Alpha/Beta/Gamma/Prod 各自证据完整，且真实触发→通知→恢复→回滚链通过。

<a id="req-006"></a>
### REQ-006 32 人容量、TURN fallback、网络切换与 reconnect 必须由真实运行制品验证

- 32 人容量、TURN fallback、网络切换与 reconnect 必须由真实运行制品验证。
- 回滚条件必须消费已存在的 series，不允许以文档阈值替代采集。

## 4. 契约引用

- canonical：`rtc/rtc/call_session/object.yaml`
- canonical：`rtc/rtc/call_session/events.yaml`
- canonical：`rtc/rtc/call_session/operations.yaml#ReportMediaConnected`
- canonical：`rtc/rtc/call_session/events.yaml#CallRinging`
- canonical：`ops/product_ops/event_record/event_catalog.yaml#rtc_media_qoe`
- canonical：`rtc/rtc/call_session/object.yaml#livekit_integration`
- canonical：`rtc/rtc/call_session/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Room/mediaAccess 与 realtime-gateway 单通道对齐

- GIVEN 合法 persona 发起或接听 CallSession。
- WHEN rtc-service 通过 MediaRoomProvider 创建 Room、签发 mediaAccess 并发布 CallRinging/CallConnected/CallEnded。
- THEN App 从响应消费 mediaAccess，在线事件只经可信 realtime connection 投递并按 client_ws_type 解析。

<a id="gwt-002"></a>
### GWT-002 离线来电 provider 与平台唤醒

- GIVEN 被叫离线/后台/锁屏/被系统终止，且设备注册有效。
- WHEN CallRinging 进入平台 push provider。
- THEN iOS/Android 按 capability 唤醒或明确降级；Web 仅以前台 realtime 站内来电承载， 过期/重复/cancelled call 不重复响铃。

<a id="gwt-003"></a>
### GWT-003 媒体 QoE 黄金指标可查询并驱动灰度

- GIVEN audio/video 通话在强网、弱网、重连与异常中断场景运行。
- WHEN App/LiveKit adapter 结算 rtc_media_qoe，rollup 与观测栈处理该事实。
- THEN 可查询有效媒体接通率、接听到媒体可用 P95、非预期媒体中断率，并按低基数维度下钻。

<a id="gwt-004"></a>
### GWT-004 真实运行制品与 QoE 证据满足四环境准出

- GIVEN rtc-service、LiveKit、coturn、realtime-gateway 与观测栈按环境拓扑装配。
- WHEN 执行 Beta API、Gamma 设备/弱网、Prod gray canary 与回滚演练。
- THEN artifact/config digest、Room/token、TURN、32 人边界、重连、三项 QoE 指标与告警回执可追踪。

## 6. 依赖

- 前置要求：[`realtime-call`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Room/mediaAccess 与 realtime-gateway 单通道对齐

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Room、mediaAccess、auth_ack、wire type、ReportMediaConnected 与状态机有端云证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 离线来电 provider 与平台唤醒

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：provider receipt、设备回调、来电 UI、Answer/Reject 与真实设备 readback 闭环。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 媒体 QoE 黄金指标可查询并驱动灰度

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少 emitter、去重、rollup、series、dashboard/alert、gamma/prod readback 与恢复演练的同版本完整证据。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 真实运行制品与 QoE 证据满足四环境准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Alpha/Beta/Gamma/Prod 各自证据完整，且真实触发→通知→恢复→回滚链通过。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效
