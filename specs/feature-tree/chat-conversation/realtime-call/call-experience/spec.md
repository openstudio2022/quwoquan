# L3 Story：call-experience — 通话过程与控制体验 (`call-experience`)

> 所属能力：[`realtime-call`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-016`](../../../spec.md#scn-016)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，我希望五个 RTC 页面、真实媒体展示、过程态、控制、PiP hangup、屏幕共享与恢复体验，从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- CallSession + LiveKit 派生展示态
- 真实 VideoTrack/音频控制与 RuntimeFailure
- ActiveCallBar/PiP 回流及云端挂断
- 屏幕共享 start/stop、互斥与平台降级
- 过程态、真实媒体、错误恢复
- 控制栏、PiP/通话条、屏幕共享

### Out of Scope

- 通话录制 UI、交集常驻模块、debug 模拟主链
- 录制 UI、交集常驻展示、debug 模拟路径

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 真实媒体与全过程态可理解

- connecting/ringing/waitingPeer/inCall/reconnecting/weakNetwork/peerNoAnswer/peerLeft/ended 全覆盖。

<a id="req-002"></a>
### REQ-002 PiP/通话条回流与挂断收尾

- 导航、云端状态、CallEnded 与浮层生命周期在竞态下不重复或残留。

<a id="req-003"></a>
### REQ-003 屏幕共享开始、互斥、停止与平台降级

- command、媒体 track、页面与平台权限四层同源。

<a id="req-004"></a>
### REQ-004 网络中断显示 reconnecting，不以黑屏或自动退出掩盖

- 网络中断显示 reconnecting，不以黑屏或自动退出掩盖；恢复不得创建新 CallSession。

<a id="req-005"></a>
### REQ-005 控制真实生效且 PiP 挂断完成云端收尾

- 本地状态、媒体运行态、云端状态与导航无分叉。

<a id="req-006"></a>
### REQ-006 屏幕共享 UI 与聚合/媒体一致

- 开始、停止、互斥、离开与恢复路径均有三层证据。

<a id="req-007"></a>
### REQ-007 权限失败使用 RuntimeFailure/统一权限卡片

- 权限失败使用 RuntimeFailure/统一权限卡片；视频缺摄像头可在能力允许时降级 audio。

## 4. 契约引用

- canonical：`rtc/rtc/call_session/fields.yaml#CallStatus`
- canonical：`rtc/rtc/call_session/events.yaml`
- canonical：`rtc/rtc/call_session/operations.yaml#HangupCall`
- canonical：`rtc/rtc/call_session/operations.yaml#LeaveCall`
- canonical：`rtc/rtc/call_session/operations.yaml#StartScreenShare`
- canonical：`rtc/rtc/call_session/operations.yaml#StopScreenShare`
- canonical：`rtc/rtc/call_session/events.yaml#ScreenShareStarted`
- canonical：`rtc/rtc/call_session/events.yaml#ScreenShareStopped`
- canonical：`rtc/rtc/call_session/operations.yaml#ToggleMute`
- canonical：`rtc/rtc/call_session/operations.yaml#ToggleCamera`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 真实媒体与全过程态可理解

- GIVEN audio/video 通话正在振铃、建连、通话、弱网、重连或结束。
- WHEN CallSession 状态或 LiveKit participants/tracks/connection state 变化。
- THEN 页面派生正确 stage，真实 track 可见；无 track、弱网、重连与结束均有明确反馈。

<a id="gwt-002"></a>
### GWT-002 PiP/通话条回流与挂断收尾

- GIVEN 用户在进行中的通话里返回其他页面，ActiveCallBar/PiP 已显示。
- WHEN 用户点击回流，或从 PiP 发起挂断。
- THEN 回流到 canonical 通话页；挂断调用 HangupCall/LeaveCall 并等待云端终态后幂等关闭浮层。

<a id="gwt-003"></a>
### GWT-003 屏幕共享开始、互斥、停止与平台降级

- GIVEN CallSession 已 in_call，平台 screen capture capability 可用或明确不可用。
- WHEN 参与者开始/停止共享，另一参与者并发开始，或用户拒绝采集权限。
- THEN CallSession screen-share 字段与 LiveKit track 一致
- AND 并发冲突结构化失败
- AND 无能力时安全降级。

<a id="gwt-004"></a>
### GWT-004 控制真实生效且 PiP 挂断完成云端收尾

- GIVEN 用户处于 audio/video 通话中并可在页面与 PiP/通话条之间切换。
- WHEN 用户静音、切摄像头/音频输出、回流或从 PiP 挂断。
- THEN LiveKit/typed Facet 收到真实动作，页面只消费权威结果，CallEnded 后全局投影幂等销毁。

<a id="gwt-005"></a>
### GWT-005 屏幕共享 UI 与聚合/媒体一致

- GIVEN 通话进行中，平台能力与权限状态已知。
- WHEN 用户开始或停止共享，或发生并发共享/权限拒绝。
- THEN UI 等待 typed command 与 LiveKit track 的真实结果，冲突/无能力显示结构化反馈。

## 6. 依赖

- 前置要求：[`realtime-call`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实媒体与全过程态可理解

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：connecting/ringing/waitingPeer/inCall/reconnecting/weakNetwork/peerNoAnswer/peerLeft/ended 全覆盖。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 PiP/通话条回流与挂断收尾

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：导航、云端状态、CallEnded 与浮层生命周期在竞态下不重复或残留。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 屏幕共享开始、互斥、停止与平台降级

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：command、媒体 track、页面与平台权限四层同源。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 控制真实生效且 PiP 挂断完成云端收尾

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：本地状态、媒体运行态、云端状态与导航无分叉。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 屏幕共享 UI 与聚合/媒体一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：开始、停止、互斥、离开与恢复路径均有三层证据。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效
