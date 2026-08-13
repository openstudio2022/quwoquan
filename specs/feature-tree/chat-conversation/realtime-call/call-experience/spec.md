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
- 美颜、背景虚化等视频画面处理（本地预览镜像不属于画面处理，见 GWT-012）

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

<a id="gwt-006"></a>
### GWT-006 通话期间屏幕常亮且收尾必然释放

- GIVEN 用户处于活跃通话中，设备屏幕常亮能力经 platform gateway 暴露。
- WHEN 通话开始、被最小化为 PiP/通话条，或经挂断、对端结束、notifier 回收任一路径收尾。
- THEN 活跃期间（含 PiP 最小化）保持常亮
- AND 任一收尾路径都释放常亮，不让设备停留在常亮态耗电。

<a id="gwt-007"></a>
### GWT-007 通话核心动作可经读屏语义寻址

- GIVEN 用户在来电页、通话控制条或 PiP 浮窗上使用读屏。
- WHEN 读屏遍历接听、拒接、挂断、静音、摄像头、翻转、共享、邀请、扬声器与 PiP 回流入口。
- THEN 每个动作都以 button 语义节点暴露稳定 label 并可被激活，不存在只有裸 `GestureDetector` 与视觉文本的入口。

<a id="gwt-008"></a>
### GWT-008 通话中来电不篡夺活跃通话

- GIVEN 用户已处于活跃通话中。
- WHEN 收到属于另一通话的新 `call.ringing`，或收到同一通话的重复 `call.ringing`。
- THEN 新来电降级为第二来电轻提示并照常 ACK，不改写活跃 CallSession 状态机、不导航覆盖通话页。
- AND 同一通话的重复 ringing 不重复提示。
- AND 空闲态收到来电时仍按原有 seed 首帧并进入来电页。

<a id="gwt-009"></a>
### GWT-009 音频会话激活与系统中断处理

- GIVEN 通话媒体已连通，平台音频会话与路由能力经 gateway 暴露。
- WHEN 通话建立或收尾，系统中断 began/ended 到达，或耳机拔出触发 becomingNoisy。
- THEN 媒体连通时以通话配置激活音频会话，收尾时释放。
- AND 中断 began 本地静音采集，ended 声明 shouldResume 时恢复采集，但用户主动静音的不得被擅自取消。
- AND becomingNoisy 时从扬声器切回听筒防止外放，已是听筒态则不重复切换。

<a id="gwt-010"></a>
### GWT-010 通话结局归因可区分且各终止路径互不混淆

- GIVEN 一通处于振铃或已接通状态的通话，结局埋点经 recorder 上报。
- WHEN 通话经本端接听后挂断、本端拒接、主叫取消，或服务端下发 `no_answer` / `error` 收尾信令而结束。
- THEN 本端主动路径分别归因为 `completed`、`rejected`、`cancelled`，拒接不得归因为 cancelled。
- AND 服务端 `no_answer` 归因为 `no_answer`，与主叫主动取消保持可区分。
- AND 服务端 `error` 归因为 `failed`，不得与正常收尾合并。

<a id="gwt-011"></a>
### GWT-011 通话时长展示在跨小时边界不丢位

- GIVEN 通话计时器持有已进行时长。
- WHEN 时长跨越秒、分与小时边界。
- THEN 未满 1 小时按 `MM:SS` 呈现，满 1 小时起按 `HH:MM:SS` 呈现，61 分钟不得丢弃小时位。
- AND 计时器状态的展示文本与统一格式化函数同源，不存在第二套格式化实现。
- AND 通话条对超过 1 小时的通话渲染 `HH:MM:SS`。

<a id="gwt-012"></a>
### GWT-012 本地前摄预览镜像且远端画面不镜像

- GIVEN 通话渲染本地预览或远端参与者画面，摄像头位姿由设备状态给出。
- WHEN 本地使用前置或后置摄像头，或渲染远端参与者，或在通话中翻转摄像头。
- THEN 本地前置摄像头预览水平镜像，翻转到后置后回到非镜像。
- AND 远端参与者画面在任何摄像头位姿下都不镜像。
- AND 镜像决策以单一函数为真相源，翻转往返后结论保持一致，渲染侧不得各自判断。

## 6. 依赖

- 前置要求：[`realtime-call`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 群邀完整 UI journey 测试

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺一条端到端 widget journey：邀请参与者从控制条入口到 picker 提交、roster 更新目前只有分段对象级测试。
- 目标：控制条邀请入口 → 联系人 picker → InviteToCall 提交 → roster 断言的单条 journey 测试。
- 完成判定：journey 测试绿且 `spec_ref` 绑定 GWT-004。

<a id="open-002"></a>
### OPEN-002 视频网格动态重排断言

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：缺参与者加入/离开时视频网格列数与 tile 尺寸重排的行为断言，重排回归只能靠人工发现。
- 目标：对 2/4/6+ 人网格断言列数与 active speaker 排序。
- 完成判定：网格重排测试绿并绑定 GWT-001。

<a id="open-003"></a>
### OPEN-003 通话页性能预算

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚无通话页（尤其视频网格与 PiP 动画）的帧时间/掉帧率预算与量测手段，商用性能回归缺防线。
- 目标：为 rtcVoice/rtcVideo surface 声明帧预算并接入既有性能量测通道。
- 完成判定：`GWT-001` 对应通话页在声明的帧预算断言下保持绿，量测接入 gate/CI。

<a id="open-004"></a>
### OPEN-004 QoE 发射端到端集成断言

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺经真实 reporter 管道（采样、九字段上下文、outbox）的 `rtc_media_qoe` 端到端集成断言；对象级发射测试已覆盖。
- 目标：api_integration 层验证 QoE 事件从通话收尾到 outbox 落盘的完整链路。
- 完成判定：`GWT-004` 收尾路径的 QoE 发射经真实 reporter 管道断言绿，并与 L2 `OPEN-009` 环境证据对齐。

<a id="open-005"></a>
### OPEN-005 宽屏 expanded 断点适配

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚未为 wide/expanded 断点（Web/桌面/平板横屏）声明通话页布局，宽屏沿用手机纵向布局体验未达最优；不阻塞移动端商用。
- 目标：按 `AppSpacing` 断点 token 为通话页与网格声明 expanded 布局。
- 完成判定：`GWT-001` 在 expanded 断点下的布局行为测试绿（断点 token 单一来源）。

<a id="open-006"></a>
### OPEN-006 蓝牙音频路由选择 UI

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：缺蓝牙设备枚举与手动切换 UI；v1 已裁决最小集——音频会话配置 `allowBluetooth`，系统自动跟随蓝牙设备，App 内 `AudioOutput` 仅暴露听筒/扬声器。
- 目标：路由枚举扩展 bluetooth 选项并接入音频输出 picker。
- 完成判定：`GWT-009` 扩展蓝牙路由子句且切换行为测试绿、真机验证。

<a id="open-007"></a>
### OPEN-007 真机音频中断与 CallKit 双通话验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺双端真机对系统电话打断、CallKit 系统面接听第二通、蜂窝/VoIP 抢占实际表现的验收（依赖 L2 `OPEN-004` 的设备与凭据前置）；GWT-008/GWT-009 的对象级行为已测。
- 目标：iOS/Android 真机完成中断矩阵（系统来电、闹钟、其他 VoIP App）与 CallKit 双通话行为记录。
- 完成判定：真机验收记录回填且 GWT-008/GWT-009 无行为偏差。
