# L4 Story：sfu-deployment-contract — LiveKit SFU + coturn 部署契约

> **层级**：L4_story（隶属 L3 `media-infrastructure`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call/media-infrastructure`

## 定位

LiveKit SFU + coturn 部署契约的可验收交付：32 人基准性能、弱网/断网恢复、灰度 prod 5%→100% 无回滚。

## 职责边界

- 性能：500 并发 InitiateCall p99 < 200ms，32 人满房 SFU CPU < 85%
- 弱网：100kbps 音频保持 ≥ 60s，Simulcast 自动降质
- 断网恢复：ICE restart，重连成功率 ≥ 95%
- 灰度：prod 5%→20%→50%→100% 各阶段无回滚，7 项门禁指标
- 对应 L2 `realtime-call` acceptance A28~A31、A40~A43

## 与父节点关系

- 父节点 `realtime-call/spec.md` §4.5 技术架构、§6.4 并发性能、§6.5 部署拓扑与灰度策略
- 父节点 `media-infrastructure/spec.md` 定义 SFU/TURN 基建职责
- 详细规格与验收标准见 L2 `realtime-call/spec.md` 及 `realtime-call/acceptance.yaml`。
