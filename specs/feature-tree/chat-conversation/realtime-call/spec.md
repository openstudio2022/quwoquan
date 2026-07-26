# L2 Business Capability：实时音视频通话 (`realtime-call`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让用户在满足关系与成员权限时发起、接听、拒绝、取消和结束 1v1 或不超过 32 人的实时音视频通话，并通过同一 `CallSession/CallParticipant` 状态机、realtime-gateway 信令、LiveKit 媒体和会话记录获得可恢复结果。

## 2. 范围与非目标

### In Scope

- 1v1 与多人通话状态机、端云协同、异常路径
- realtime-gateway 在线事件、三端离线来电平台能力矩阵与权限降级
- 关系门禁，以及来电/入会前的信任两态（认识 / 可能不认识）提示
- 错误码/文案统一语义与权限卡片
- LiveKit 远端参与者/轨道到 UI 的实时绑定
- CallEnded 到关联 Conversation system_call_log 的 durable 投影
- PiP 挂断、屏幕共享与媒体 QoE 商用准出

### Out of Scope

- 超过 32 人会议、PSTN、直播推流、实时字幕
- 通话录制、媒体录制文件与端到端媒体加密
- 独立通话历史聚合页（当前主形态为会话 system_call_log）

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-016`](../../spec.md#scn-016)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：1v1 与多人通话的状态结果、媒体连接结果、离线来电投递结果和会话 `system_call_log`。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`call-experience`](./call-experience/spec.md)：connecting/ringing/waitingPeer/inCall/reconnecting/weakNetwork/peerNoAnswer/peerLeft/ended 全覆盖。
- [`group-call`](./group-call/spec.md)：join/leave/limit/last_leave 与重复命令在真实 Mongo/Redis 集成中闭环。
- [`media-infrastructure`](./media-infrastructure/spec.md)：Room、mediaAccess、auth_ack、wire type、ReportMediaConnected 与状态机有端云证据。
- [`one-to-one-call`](./one-to-one-call/spec.md)：AnswerCall 成功与媒体 connected 被明确区分，至少两人 connected 后才进入 in_call。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 入口清晰度与关系门禁

- 1v1 输入区仅互相关注显示语音/视频入口；非互相关注显示可解释教育卡而非空白。
- 群聊输入区进入选人页，≤8 默认全选、>8 默认空选，可切换当前会话/互相关注/其他群。
- 用户主页按关系态展示消息/语音/视频或仅打招呼，入口只读 relationship-capability 能力位。

<a id="req-002"></a>
### REQ-002 呼出/来电/通话全过程态闭环

- 发起→呼出（可取消）→振铃（接听/拒绝/30s 超时）→建连→通话→挂断收尾完整可达。
- 通话页覆盖连接中/振铃/单人等待/通话中/对方未接/已离开/重连中/弱网/已结束全部过程态。
- 通话结束后在关联会话插入通话记录消息。

<a id="req-003"></a>
### REQ-003 多人房间、通话中加人与信任两态提示

- Join/Leave/Invite 全路径可用
- 32 人上限返回 call_full
- 最后一人离开结束房间。
- 通话中加人只经 InviteToCall 修改 CallSession owned participant；未建 metadata operation 的呼叫链接不得被页面伪装为可用能力。
- 参与者按 认识/可能不认识 两态展示来源标签或风险提示；新人为“可能不认识”时在会成员收到轻量横幅。

<a id="req-004"></a>
### REQ-004 三端来电唤醒与权限降级

- iOS 后台/锁屏经 PushKit 唤醒并立即上报 CallKit；Android 经 FCM 高优先级+全屏意图唤醒，14+ 权限不可用降级 heads-up。
- Web M2 仅支持前台 realtime 站内来电；后台 Web Push/Service Worker 明确 deferred， 不伪装成已实现能力。
- 平台判断只读 PlatformCapabilities（incomingCallUi/webPushIncomingCall/realtimeCommunication），无裸平台判断。

<a id="req-005"></a>
### REQ-005 events.yaml 的 client_ws_type 经 codegen 生成 Go 映射，orchestrator 推送使用 wire type（call.ringing 等）

- events.yaml 的 client_ws_type 经 codegen 生成 Go 映射，orchestrator 推送使用 wire type（call.ringing 等）。
- Dart parseRtcWsPayload 与 Go 推送 type 对齐；来电/参与者事件可被端侧解析。
- LiveKit 远端 participants/tracks 实时同步到 callParticipantsProvider，视频格渲染真实 VideoTrack。
- RTC 不建立私有信令连接；所有在线 call/participant/screen_share 事件只由 realtime-gateway 的可信 ticket/auth_ack 连接投递。

<a id="req-006"></a>
### REQ-006 错误与权限统一语义

- 通话错误走 errors.yaml→codegen，端侧用 RtcErrorCode.fromCode(...).toDisplayMessage(l10n)，含 not_mutual/blocked。
- 麦克风/摄像头/通知/全屏来电/Web 通知权限统一权限卡片，永久拒绝显示去设置并提供仅语音降级。
- 无裸异常字符串与硬编码中文/REC 文案。

<a id="req-007"></a>
### REQ-007 全局通话条、PiP 与后台恢复

- IncomingCallCoordinator/ActiveCallBar/PipCallOverlay 挂载到 app shell 唯一入口。
- 通话中返回其他页面出现顶部通话条/PiP，点击回流通话页；后台返回可恢复通话。
- 翻转摄像头调用 SFU switchCamera，音频输出调用 setSpeakerOn，按钮真实生效。
- PiP 中挂断执行 canonical HangupCall/LeaveCall，云端进入 ended/left 后浮层与导航只收尾一次。

<a id="req-008"></a>
### REQ-008 屏幕共享生命周期、互斥与平台降级

- StartScreenShare/StopScreenShare 只经 CallScreenShareCommandFacet 修改 CallSession。
- 同时仅一名 screenShareUserId；冲突返回 RTC.USER.screen_share_conflict。
- LiveKit screen track 发布/停止与聚合状态一致，权限或平台能力缺失时结构化降级。

<a id="req-009"></a>
### REQ-009 RTC 媒体 QoE 黄金指标与发布 readback

- rtc_media_qoe 有生产 emitter、去重终态与有界维度，且不会把 callId/userId 放进 Prometheus label。
- SLS/local rollup 同源产出有效媒体接通率、接听到媒体可用 P95、非预期媒体中断率。
- dashboard/alert 只消费已查询到的真实 series，并完成 Gamma 与 prod gray 触发/恢复演练。

<a id="req-010"></a>
### REQ-010 离线来电必须由真实 provider、设备和发布证据准出，不得以本地通知或固定成功代替

- 离线来电必须由真实 provider、设备和发布证据准出，不得以本地通知或固定成功代替。
- 端到端媒体加密不在现行范围；建立该能力前必须先定义 metadata 对象/operation、隐私和密钥生命周期。
- 以 P2P 作为 SFU 的临时 fallback；当前媒体路径统一为 LiveKit SFU。
- 30 秒未接的 1v1 呼叫以 `no_answer` 结束；系统超时与业务无应答不得混写。
- `Persona`：命令 actor；1v1 发起者必须通过关系门禁且未被拉黑。
- UI 只消费 relationship capability；不能自行用在线状态、共同标签或交集分数授权。
- rtc-service 必须最终复核 trusted persona、1v1 关系与 block 状态。
- 网络恢复不得创建第二个 CallSession；重复命令由 receipt 幂等。
- 回滚触发以三项黄金指标、崩溃/ANR、离线来电到达和服务可用性为准；阈值必须有真实 series。
- RTC 功能开关只能控制入口/rollout，不得在同一生产二进制切 Mock/Remote 或恢复私有信令。

## 6. 契约与依赖

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 入口清晰度与关系门禁

- GIVEN 执行“入口清晰度与关系门禁”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“入口清晰度与关系门禁”对应动作。
- THEN 1v1 输入区仅互相关注显示语音/视频入口；非互相关注显示可解释教育卡而非空白。
- THEN 群聊输入区进入选人页，≤8 默认全选、>8 默认空选，可切换当前会话/互相关注/其他群。
- THEN 用户主页按关系态展示消息/语音/视频或仅打招呼，入口只读 relationship-capability 能力位。

<a id="sit-002"></a>
### SIT-002 呼出/来电/通话全过程态闭环

- GIVEN 执行“呼出/来电/通话全过程态闭环”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“呼出/来电/通话全过程态闭环”对应动作。
- THEN 发起→呼出（可取消）→振铃（接听/拒绝/30s 超时）→建连→通话→挂断收尾完整可达。
- THEN 通话页覆盖连接中/振铃/单人等待/通话中/对方未接/已离开/重连中/弱网/已结束全部过程态。
- THEN 通话结束后在关联会话插入通话记录消息。

<a id="sit-003"></a>
### SIT-003 多人房间、通话中加人与信任两态提示

- GIVEN 执行“多人房间、通话中加人与信任两态提示”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“多人房间、通话中加人与信任两态提示”对应动作。
- THEN Join/Leave/Invite 全路径可用
- AND 32 人上限返回 call_full
- AND 最后一人离开结束房间。
- THEN 通话中加人只经 InviteToCall 修改 CallSession owned participant；未建 metadata operation 的呼叫链接不得被页面伪装为可用能力。
- THEN 参与者按 认识/可能不认识 两态展示来源标签或风险提示；新人为“可能不认识”时在会成员收到轻量横幅。

<a id="sit-004"></a>
### SIT-004 三端来电唤醒与权限降级

- GIVEN 执行“三端来电唤醒与权限降级”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“三端来电唤醒与权限降级”对应动作。
- THEN iOS 后台/锁屏经 PushKit 唤醒并立即上报 CallKit；Android 经 FCM 高优先级+全屏意图唤醒，14+ 权限不可用降级 heads-up。
- THEN Web M2 仅支持前台 realtime 站内来电；后台 Web Push/Service Worker 明确 deferred， 不伪装成已实现能力。
- THEN 平台判断只读 PlatformCapabilities（incomingCallUi/webPushIncomingCall/realtimeCommunication），无裸平台判断。

<a id="sit-005"></a>
### SIT-005 realtime-gateway 单通道 wire type 端云一致与参与者绑定

- GIVEN 执行“realtime gateway 单通道 wire type 端云一致与参与者绑定”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“realtime gateway 单通道 wire type 端云一致与参与者绑定”对应动作。
- THEN events.yaml 的 client_ws_type 经 codegen 生成 Go 映射，orchestrator 推送使用 wire type（call.ringing 等）。
- THEN Dart parseRtcWsPayload 与 Go 推送 type 对齐；来电/参与者事件可被端侧解析。
- THEN LiveKit 远端 participants/tracks 实时同步到 callParticipantsProvider，视频格渲染真实 VideoTrack。
- THEN RTC 不建立私有信令连接；所有在线 call/participant/screen_share 事件只由 realtime-gateway 的可信 ticket/auth_ack 连接投递。

<a id="sit-006"></a>
### SIT-006 错误与权限统一语义

- GIVEN 执行“错误与权限统一语义”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“错误与权限统一语义”对应动作。
- THEN 通话错误走 errors.yaml→codegen，端侧用 RtcErrorCode.fromCode(...).toDisplayMessage(l10n)，含 not_mutual/blocked。
- THEN 麦克风/摄像头/通知/全屏来电/Web 通知权限统一权限卡片，永久拒绝显示去设置并提供仅语音降级。
- THEN 无裸异常字符串与硬编码中文/REC 文案。

<a id="sit-007"></a>
### SIT-007 全局通话条、PiP 与后台恢复

- GIVEN 执行“全局通话条、PiP 与后台恢复”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“全局通话条、PiP 与后台恢复”对应动作。
- THEN IncomingCallCoordinator/ActiveCallBar/PipCallOverlay 挂载到 app shell 唯一入口。
- THEN 通话中返回其他页面出现顶部通话条/PiP，点击回流通话页；后台返回可恢复通话。
- THEN 翻转摄像头调用 SFU switchCamera，音频输出调用 setSpeakerOn，按钮真实生效。
- THEN PiP 中挂断执行 canonical HangupCall/LeaveCall，云端进入 ended/left 后浮层与导航只收尾一次。

<a id="sit-008"></a>
### SIT-008 屏幕共享生命周期、互斥与平台降级

- GIVEN 执行“屏幕共享生命周期、互斥与平台降级”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“屏幕共享生命周期、互斥与平台降级”对应动作。
- THEN StartScreenShare/StopScreenShare 只经 CallScreenShareCommandFacet 修改 CallSession。
- THEN 同时仅一名 screenShareUserId；冲突返回 RTC.USER.screen_share_conflict。
- THEN LiveKit screen track 发布/停止与聚合状态一致，权限或平台能力缺失时结构化降级。

<a id="sit-009"></a>
### SIT-009 RTC 媒体 QoE 黄金指标与发布 readback

- GIVEN 执行“RTC 媒体 QoE 黄金指标与发布 readback”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“RTC 媒体 QoE 黄金指标与发布 readback”对应动作。
- THEN rtc_media_qoe 有生产 emitter、去重终态与有界维度，且不会把 callId/userId 放进 Prometheus label。
- THEN SLS/local rollup 同源产出有效媒体接通率、接听到媒体可用 P95、非预期媒体中断率。
- THEN dashboard/alert 只消费已查询到的真实 series，并完成 Gamma 与 prod gray 触发/恢复演练。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 入口清晰度与关系门禁

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：1v1 输入区仅互相关注显示语音/视频入口；非互相关注显示可解释教育卡而非空白。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 呼出/来电/通话全过程态闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：发起→呼出（可取消）→振铃（接听/拒绝/30s 超时）→建连→通话→挂断收尾完整可达。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 多人房间、通话中加人与信任两态提示

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：Join/Leave/Invite 全路径可用
- 32 人上限返回 call_full
- 最后一人离开结束房间。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 三端来电唤醒与权限降级

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：iOS 后台/锁屏经 PushKit 唤醒并立即上报 CallKit；Android 经 FCM 高优先级+全屏意图唤醒，14+ 权限不可用降级 heads-up。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 realtime-gateway 单通道 wire type 端云一致与参与者绑定

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：events.yaml 的 client_ws_type 经 codegen 生成 Go 映射，orchestrator 推送使用 wire type（call.ringing 等）。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 错误与权限统一语义

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：通话错误走 errors.yaml→codegen，端侧用 RtcErrorCode.fromCode(...).toDisplayMessage(l10n)，含 not_mutual/blocked。
- 完成判定：`SIT-006` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-007"></a>
### OPEN-007 全局通话条、PiP 与后台恢复

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：IncomingCallCoordinator/ActiveCallBar/PipCallOverlay 挂载到 app shell 唯一入口。
- 完成判定：`SIT-007` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-008"></a>
### OPEN-008 屏幕共享生命周期、互斥与平台降级

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：StartScreenShare/StopScreenShare 只经 CallScreenShareCommandFacet 修改 CallSession。
- 完成判定：`SIT-008` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-009"></a>
### OPEN-009 RTC 媒体 QoE 黄金指标与发布 readback

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：rtc_media_qoe 有生产 emitter、去重终态与有界维度，且不会把 callId/userId 放进 Prometheus label。
- 完成判定：`SIT-009` 对应行为满足且真实测试 `spec_ref` 有效
