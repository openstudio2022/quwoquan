# L3 Story：feedback-ingestion-sampling

## 功能说明

端侧推荐反馈上报的统一通道、状态分级、采样合并、幂等与归因闭环。把当前 `ContentBehaviorTracker`（5s 批量）与 `ContentEngagementTracker`（即时单发）双通道合并为单一 `BehaviorReporter`，消除 impression/dwell 重复上报与 behaviors/ops 双写，按七态闭集分级上报，在保证反馈实时性的同时降低对云侧服务的流量冲击。

## 范围

- 统一上报通道 `BehaviorReporter`：单一出口，消除双通道重复上报与 behaviors/ops 双写。
- 可见性判定：`impressed` 必须达「可见面积 + 停留」阈值，`visible` 仅本地或低采样，替换「build 即曝光」。
- 端侧聚合采样：同一 `feedRequestId` 内按 (contentId, action) 合并；`dwell` 离开/切走/翻页时聚合，<1s 丢弃；弱信号按 recpolicy 采样率丢弃或合并。
- 分级通道：`negative`/`interaction` 即时（客户端令牌桶限流 + 幂等），`impression`/`dwell`/`visible` 批量合并。
- 幂等：每事件 `clientEventId`，云侧据此去重。
- 归因闭环：曝光携带 `feedRequestId`，点击复用同一 id（禁止重生），打通召回↔曝光↔互动漏斗。
- 弱网背压：本地短队列 + TTL，溢出优先保 `negative`/`interaction`，丢弱信号。

## 非目标

- P0 不实现离线训练样本生成、长期本地持久队列或平台级事件总线；端侧统一上报和云侧 ingest 抗冲击已在 P0 最小集落地。
- 不引入 `training_sample` 端侧声明（训练样本仅云侧派生）。
- 行为入口的云侧抗冲击（批量上限/限流/背压/InflightLimiter）归 `runtime-recommendation` 与 content-service。

## 验收标准

- A1：端侧只有一个 `BehaviorReporter` 出口，impression/dwell 不再双通道重复上报，behaviors/ops 不双写。
- A2：`impressed` 达「可见面积 + 停留」阈值才上报；`visible` 仅本地或低采样；阈值来自 recpolicy。
- A3：弱信号采样合并，强 `negative`/`interaction` 即时；`dwell` 离开聚合不按 tick。
- A4：每事件带 `clientEventId`，云侧幂等去重；`feedRequestId` 在曝光与点击一致。
- A5：弱网时本地短队列 + TTL，优先保强信号；端侧上报不对云侧构成流量冲击。
