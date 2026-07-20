# L3 Story：call-ui-interaction — 通话 UI 交互合同

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；验收 pending

## 最小价值

通话页面把 canonical CallSession 状态、LiveKit 媒体运行态与用户操作稳定组合为可理解、
可恢复、可无障碍操作的界面。

## Contract

- 视频格只渲染真实 LiveKit `VideoTrack`；无 track、关摄像头和弱网有明确占位语义。
- 发言人、网络质量和布局是瞬时展示态，不写入 CallParticipant authoritative fields。
- 控制栏的静音、摄像头、邀请、音频输出、屏幕共享、挂断都触发真实能力或 typed command。
- 返回其他页面后只保留一个 ActiveCall/PiP 投影；点击回流，挂断后幂等销毁。
- Incoming/Outgoing 页面区分接听、拒绝、取消、忙线、无应答与过期。
- 权限失败使用 RuntimeFailure/统一权限卡片；视频缺摄像头可在能力允许时降级 audio。
- `callType` UI 映射只消费 `audio/video`。

## 关键负例

- PiP 关闭浮层但云端仍在通话。
- 控制按钮只改变本地 state。
- 连接中或重连中渲染黑屏且无说明。
- 在通话舞台常驻交集/共同关系信息。
- 以 Widget fake track 证明真机媒体已通过。

## 验收

至少需要 local_contract 的展示态/控制/PiP hangup、api_integration 的 screen-share/终态，
以及 Gamma 设备页面 UAT。缺任何一层不得标 completed。
