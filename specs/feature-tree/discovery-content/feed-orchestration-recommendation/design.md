# L2 Design：内容流编排推荐 (`feed-orchestration-recommendation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“发现流推荐编排的端云行为、流式体验、交集解释、曝光治理集成边界与推荐 SLO 基线”需要 `collaborative-recall`、`feed-fallback-degrade`、`feedback-ingestion-sampling`、`interest-onboarding-prior`、`personalized-ranking`、`premium-stream-recommendation`、`quality-score-cold-start`、`ranking-calibration`、`realtime-feed-baseline`、`time-decay-contextual-ranking`、`travel-vertical-recommendation`、`unified-items-cursor` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：发现流推荐编排的端云行为、流式体验、交集解释、曝光治理集成边界与推荐 SLO 基线。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`collaborative-recall`](./collaborative-recall/spec.md)：从符合隐私和最小样本约束的 itemCF、Swing 与 u2i 信号生成候选并保留召回理由。
- [`feed-fallback-degrade`](./feed-fallback-degrade/spec.md)：定义“内容流回退降级”的可观察主路径、失败语义及父能力交接。
- [`feedback-ingestion-sampling`](./feedback-ingestion-sampling/spec.md)：统一上报通道 `BehaviorReporter`：单一出口，消除双通道重复上报与 behaviors/ops 双写。
- [`interest-onboarding-prior`](./interest-onboarding-prior/spec.md)：定义“兴趣引导先验”的可观察主路径、失败语义及父能力交接。
- [`personalized-ranking`](./personalized-ranking/spec.md)：定义“个性化排序”的可观察主路径、失败语义及父能力交接。
- [`premium-stream-recommendation`](./premium-stream-recommendation/spec.md)：路由、排序、解释、product-ops 全局精品写入前置和未启用 PremiumPoolSource 的边界均可测试。
- [`quality-score-cold-start`](./quality-score-cold-start/spec.md)：在缺少用户行为时以内容质量分和受控先验排序，并在反馈到达后逐步让位于个性化信号。
- [`ranking-calibration`](./ranking-calibration/spec.md)：以点击、完成和负反馈校准排序分，使预测分与真实结果在声明窗口内对齐。
- [`realtime-feed-baseline`](./realtime-feed-baseline/spec.md)：统一 sessionId / feedRequestId 归因。
- [`time-decay-contextual-ranking`](./time-decay-contextual-ranking/spec.md)：按时间衰减、时段、季节和事件上下文调整候选分数，同时保持策略版本可解释。
- [`travel-vertical-recommendation`](./travel-vertical-recommendation/spec.md)：推荐召回、fallback 和交集理由通道均使用同一 channel/vertical 口径。
- [`unified-items-cursor`](./unified-items-cursor/spec.md)：feed 查询快照必须遵守 `runtime-client-foundation/local-cache-architecture`，对象策略以 `object-cache-policy.yaml` 中 `QuerySnapshot` 为准。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 四类内容共用候选编排并保留类型特有策略
- 决策：四类内容共用候选编排并保留类型特有策略。
- 理由：发现流推荐编排的端云行为、流式体验、交集解释、曝光治理集成边界与推荐 SLO 基线。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`collaborative-recall`](./collaborative-recall/spec.md)、[`feed-fallback-degrade`](./feed-fallback-degrade/spec.md)、[`feedback-ingestion-sampling`](./feedback-ingestion-sampling/spec.md)、[`interest-onboarding-prior`](./interest-onboarding-prior/spec.md)、[`personalized-ranking`](./personalized-ranking/spec.md)、[`premium-stream-recommendation`](./premium-stream-recommendation/spec.md)、[`quality-score-cold-start`](./quality-score-cold-start/spec.md)、[`ranking-calibration`](./ranking-calibration/spec.md)、[`realtime-feed-baseline`](./realtime-feed-baseline/spec.md)、[`time-decay-contextual-ranking`](./time-decay-contextual-ranking/spec.md)、[`travel-vertical-recommendation`](./travel-vertical-recommendation/spec.md)、[`unified-items-cursor`](./unified-items-cursor/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。
