# L3 Story：media-infrastructure — RTC 媒体基础设施

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；商用运行证据 pending

## 最小价值

rtc-service 可通过受控媒体房间传输能力创建房间并签发短期凭据；当前 LiveKit/TURN 仅作为
infrastructure adapter。App 能在网络变化下建立、恢复和结束媒体连接，运营能以真实 QoE
指标决定灰度与回滚。

## 职责边界

- 媒体 Room 与 CallSession 一一映射。
- rtc-service 通过 `MediaRoomProvider` 创建/删除 Room、签发绑定 room/participant/grants 的
  media access；vendor 实现仅位于 infrastructure adapter。
- App 环境包将受控连接地址注入平台媒体 adapter；operation 仅返回
  `mediaAccess.accessToken`，不透传 endpoint 或 vendor 专有字段。
- coturn 负责 NAT 穿透；realtime-gateway 负责业务事件投递，两者不混用。
- 媒体建连后必须调用 `ReportMediaConnected`，使 Participant/CallSession 状态可审计。
- 屏幕共享使用 LiveKit screen track + CallSession start/stop command。
- 32 人上限需同时通过聚合边界与真实 SFU 容量验证。

## 可观测

现有 rtc-service HTTP RED 不能替代媒体质量。当前已落地：

- App `RtcMediaQoeTracker` 在一次通话内只结算一个低基数终态；
- `rtc_qoe` mergeable hourly rollup 与 SLS 三项黄金指标告警；
- LiveKit 6789 scrape，以及官方 `livekit_packet_loss_percent_bucket` /
  `livekit_quality_score_bucket` 媒体面告警；
- 本地合同锁定取消/未接分母、重连恢复、`connection_lost` wire 值和禁止
  callId/userId 标签。

真实 SLS series、可执行查询面板、Gamma/prod 弱网 readback 与触发/恢复/回滚演练尚未
完成；在这些证据可查询前不能把静态配置当作发布准出。

一级指标固定为：

1. 有效媒体接通率；
2. 接听/加入到媒体可用 P95；
3. 非预期媒体中断率。

## Out of Scope

- 通话录制、录制文件与相关媒体管道。
- 本期 E2EE 承诺。
- P2P 临时 fallback 或 RTC 私有信令。

## 验收

需覆盖 Room/mediaAccess accessToken、环境包连接地址、TURN、timeout/connected、screen share、弱网/重连、QoE emitter/rollup、
Gamma 真实媒体与 prod gray readback。受控 SLS Secret 缺失时保持 blocked。
