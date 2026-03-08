# L3 规格：media-infrastructure — 媒体基础设施

> **层级**：L3_subfeature（隶属 L2 `realtime-call`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call`

## 定位

SFU/TURN/录制基础设施的部署与验证：LiveKit SFU 自部署、coturn TURN 服务、Egress 录制管道、灰度发布。

## 职责边界

- 覆盖 Phase 0 + Phase 4 基建（I1~I4、F14 录制、F15 屏幕共享）
- LiveKit SFU 自部署 + 32 人满房基准测试
- coturn TURN 服务 + NAT 穿透验证
- LiveKit Egress 录制 → OSS 存储
- 部署拓扑：rtc-service / livekit-sfu / coturn 独立部署
- 灰度策略：prod 5%→20%→50%→100% + 自动回滚门禁

## 与父/子节点关系

- 父节点 `realtime-call` 定义容量规划和灰度门禁阈值
- 子节点 `sfu-deployment-contract`（L4 Story）承载 SFU 部署的可验收交付

详细规格见父节点 `realtime-call/spec.md` §4.5、§6.5。
