# L3 Story：call-experience — 通话过程与控制体验

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；视觉/设备验收 pending

## 最小价值

用户在呼出、来电、建连、通话、重连和结束全过程都能理解当前状态，媒体控制真实生效，
返回其他页面后可通过 PiP/通话条回流或正确挂断。

## 页面与展示态

- `incoming_call_page.dart`：来源、最小信任证据、接听/拒绝/过期。
- `outgoing_call_page.dart`：振铃、取消、忙线、无应答。
- `voice_call_page.dart`：静音、音频输出、重连、后台恢复。
- `video_call_page.dart`：真实 VideoTrack、摄像头、PiP、屏幕共享。
- `call_participant_picker_page.dart`：候选、上限、邀请结果。

展示态只从 CallSession + LiveKit 运行态派生：

```text
connecting | ringing | waitingPeer | inCall | reconnecting |
weakNetwork | peerNoAnswer | peerLeft | ended
```

这些不是新的领域状态。

## 交互合同

- 静音/摄像头状态经 typed media Facet 与 LiveKit 同步，不只改本地图标。
- PiP/通话条点击回到 canonical 通话页。
- PiP 挂断调用 `HangupCall`；多人仅离开自己时调用 `LeaveCall`。
- 屏幕共享调用 `StartScreenShare` / `StopScreenShare`，冲突显示结构化错误。
- 网络中断显示 reconnecting，不以黑屏或自动退出掩盖；恢复不得创建新 CallSession。
- 平台能力只读 `PlatformCapabilities`；不在业务层判断 iOS/Android/Web/OHOS。

## 交集边界

通话页不展示交集模块。只有来电/预入会与新成员进入时，按
`known | possibly_unknown` 提供必要来源/隐私提示。

## Out of Scope

- 通话录制与录制提示。
- 仅为测试存在的 debug 来电/自动接通分支。
- 未有真实 track、屏幕采集或系统回调时宣称设备能力已通过。

## 验收

核心未完成证据为 PiP hangup、屏幕共享、离线来电和媒体 QoE；测试路径见本节点及 L2
`acceptance.yaml`，状态保持 pending/partial。
