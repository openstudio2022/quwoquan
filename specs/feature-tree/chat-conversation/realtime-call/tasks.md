# Tasks: realtime-call — Gap-Closing（商用补齐）

> **状态**：Dev 进行中（REV-1/REV-2 设计修订后，全量功能补齐）
> **顺序**：metadata → codegen → 业务逻辑 → 测试（强制）
> **目标**：达到微信/FaceTime 级商用发布门槛

## 已完成基线（保留）

以下为前一轮已交付的设计/骨架资产，不再重复：

- [x] metadata 全套（fields/aggregate/service/events/errors/storage）
- [x] rtc-service DDD 骨架（domain + application + adapters + infrastructure）
- [x] 端侧 UI 壳（OutgoingCall/IncomingCall/VoiceCall/VideoCall + 控件）
- [x] RtcRepository 三层模式（Abstract + Mock + Remote）
- [x] 部署 Kustomize 三环境（rtc-service + livekit-sfu + coturn）
- [x] T1 契约测试（DTO/错误码/Mock round-trip）
- [x] T2 UI 组件测试（网格/PiP/控制栏/质量指示器）
- [x] T3 服务端契约测试（生命周期/房间管理/事件发布）

## Gap-Closing Phase GA — 门禁修复（先决条件）

- [x] GA-1: rtc-service 健康检查路径对齐（新增 /livez + /startupz，或统一 deployment 探针到 /healthz）
- [x] GA-2: rtc-service 纳入 Makefile test-contract + gate.sh L2 + service_pipeline.yml
- [x] GA-3: AnswerCall 契约统一 — handler 返回 {session, token, roomId}（REV-2）

## Gap-Closing Phase GB — 媒体打通（MVP 核心）

- [x] GB-1: pubspec.yaml 引入 livekit_client + flutter_callkit_incoming
- [x] GB-2: 新建 lib/cloud/rtc/livekit_room_service.dart — Room.connect() / disconnect / 事件监听
- [x] GB-3: ParticipantTile 集成 LiveKit VideoTrackRenderer 替换占位图标
- [x] GB-4: VoiceCallPage / VideoCallPage 在 answerCall / joinCall 后自动连接 LiveKit Room
- [x] GB-5: CallSessionNotifier 集成 LiveKitRoomService — initiate/answer/hangup 时管理 Room 生命周期
- [x] GB-6: 通话发起入口 — ChatDetailPage AppBar 语音/视频按钮 + UserProfilePage 操作栏

## Gap-Closing Phase GC — 信令与来电

- [x] GC-1: rtc-service 新增 /v1/rtc/signal WS 端点 — 来电推送 + 通话状态同步（REV-1 降级方案）
- [x] GC-2: 端侧 lib/cloud/rtc/rtc_signaling_client.dart — WS 连接 + 心跳 + 重连
- [x] GC-3: flutter_callkit_incoming 集成 — iOS CallKit + Android FullScreen Intent
- [x] GC-4: 来电流程打通 — WS 收到 call.ringing → CallKit/IncomingCallPage → answerCall → LiveKit Room

## Gap-Closing Phase GD — 质量与弱网

- [x] GD-1: CallQualityIndicator 接入 LiveKit ConnectionQuality 回调（替换固定值）
- [x] GD-2: Simulcast 层自适应 — L0~L5 策略实现，绑定 Room.onConnectionQualityChanged
- [x] GD-3: ICE restart 断线重连 — Room.onDisconnected → 自动重连 + UI 提示
- [x] GD-4: 网络切换（WiFi↔蜂窝）— connectivity_plus 监听 → Room.reconnect

## Gap-Closing Phase GE — 高级能力落地

- [x] GE-1: LiveKit Egress 录制 — rtc-service 调用 LiveKit Egress API（StartCompositeEgress）
- [x] GE-2: 屏幕共享 — 端侧 LocalParticipant.publishScreenShare (ReplayKit/MediaProjection)
- [x] GE-3: active_call_service.dart 修复 — _startTimer() 实际调用 + 去除重复 _stopTimer()

## Gap-Closing Phase GF — 门禁验证与补充测试

- [ ] GF-1: T1 补充 — LiveKitRoomService 单元测试 + RtcSignalingClient 单元测试
- [ ] GF-2: T2 补充 — ParticipantTile 真实视频渲染测试 + CallKit 集成测试
- [ ] GF-3: T3 补充 — rtc-service WS 信令端点契约测试 + AnswerCall 新响应格式测试
- [ ] GF-4: make gate 全量通过（rtc-service 已纳入）
- [ ] GF-5: flutter test 端侧全量通过

## Gap-Closing Phase GG — 关系门禁与入口迁移

- [ ] GG-1: metadata 对齐 — rtc/call_session errors 增加关系门禁错误码
- [ ] GG-2: 前端移除 ChatDetailPage AppBar 的语音/视频通话按钮
- [ ] GG-3: 1v1 输入区 `+` 面板承载 `语音通话 / 视频通话`
- [ ] GG-4: 群聊输入区 `+` 面板承载 `发起语音通话 / 发起视频通话`
- [ ] GG-5: 接入 `contact-and-session-governance` 能力位，只有同好显示 1v1 音视频入口（密友仅为同好子态语义）
- [ ] GG-6: 正式会话但未互关时，展示 `加同好` 关系条，不展示音视频入口

## Gap-Closing Phase GH — 多人选择与通话中加人

- [ ] GH-1: 群聊发起多人通话选人规则接入 `<=8 默认全选，>8 默认不选`
- [ ] GH-2: 选人页补齐来源切换（当前会话 / 同好 / 其他群）、搜索、全不选、恢复默认
- [ ] GH-3: 通话中邀请成员链路接入当前会话成员 / 同好 / 其他群成员三类来源
- [ ] GH-4: 新增呼叫链接入会 API 与端侧分享链路
- [ ] GH-5: 跨群拉人加入当前通话时，不要求先加入当前群；补齐服务端权限校验与端侧提示
- [ ] GH-6: 链接失效与会话结束回收规则验证

## Gap-Closing Phase GI — 关系门禁验证

- [ ] GI-1: T1 — RtcErrorCode 增加 `blocked/not_same_interest/...` round-trip 测试
- [ ] GI-2: T2 — AppBar 简洁化与输入区面板入口回归
- [ ] GI-3: T2 — 同好/密友主页三按钮矩阵回归
- [ ] GI-4: T3 — 打招呼未回复前无会话入口、回复后未同好无 RTC、加同好后解锁 RTC
- [ ] GI-5: T4 — 通话中邀请与链接入会旅程

## Gap-Closing Phase GJ — 来电唤醒与铃声策略

- [ ] GJ-1: metadata 对齐 — user 域新增呼叫铃声与来电偏好（官方铃声库、是否启用发起方铃声）
- [ ] GJ-2: codegen — 生成端侧铃声偏好 DTO / Repository 与错误码
- [ ] GJ-3: CallKit / FullScreen Intent 接入发起方铃声解析，优先使用发起方专属呼叫铃声，失败回退默认铃声
- [ ] GJ-4: 群邀请模式收敛为“仅响铃邀请”，移除静默邀请分支与占位文案
- [ ] GJ-5: 群通话铃声固定归属 initiator，不随后续邀请链变化
- [ ] GJ-6: 官方铃声库资产清单、试听与设置页接入（发起方设置自己的呼叫铃声，被叫设置默认铃声）

## Gap-Closing Phase GK — 本地调试剧本与蓝色视觉统一

- [ ] GK-1: 开发态新增“模拟来电”入口，支持语音 / 视频、前台 / 后台 / 锁屏调试
- [ ] GK-2: OutgoingCallPage 开发态新增“5 秒自动接通”开关与“手动接通 / 拒接 / 超时”调试按钮
- [ ] GK-3: VoiceCallPage / VideoCallPage 补齐固定的“加人”和“成员列表”入口，避免当前仅媒体布局
- [ ] GK-4: active_call_bar、IncomingCallPage、OutgoingCallPage 与群邀请页统一切换到趣聊品牌蓝
- [ ] GK-5: T2 / T4 回归 —— 蓝色通话条、响铃邀请、发起方铃声、本地调试剧本

## 搁置任务（带规划）

| 任务 | 搁置原因 | 重启条件 | 承接节点 |
|------|---------|---------|---------|
| P2P 优先 (1v1) | SFU 统一架构更简单 | DAU > 100K 且 SFU 成本超预算 | realtime-call/one-to-one-call |
| Web 端通话 | 当前仅移动端 | Web 端产品规划确定 | 新建 L3 web-call |
| PSTN 电话互通 | 需运营商合作 | 业务需求明确 + 合作方就绪 | 新建 L3 pstn-bridge |
| realtime-gateway 迁移 | 当前无实现 | realtime-gateway 核心能力就绪 | gateway-orchestrator-foundation |
| E2EE | P4 远期 | Phase 1~3 商用稳定后 | realtime-call |
| AI 降噪 | P4 远期 | Phase 1~3 商用稳定后 | realtime-call |
