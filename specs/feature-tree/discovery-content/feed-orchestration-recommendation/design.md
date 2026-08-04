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
- [`premium-stream-recommendation`](./premium-stream-recommendation/spec.md)：product-ops 精品准入、Recommendation 候选投影/排序窗口与 Content 权限 hydration/交付的边界可组合验收。
- [`quality-score-cold-start`](./quality-score-cold-start/spec.md)：在缺少用户行为时以内容质量分和受控先验排序，并在反馈到达后逐步让位于个性化信号。
- [`ranking-calibration`](./ranking-calibration/spec.md)：以点击、完成和负反馈校准排序分，使预测分与真实结果在声明窗口内对齐。
- [`realtime-feed-baseline`](./realtime-feed-baseline/spec.md)：统一 sessionId / feedRequestId 归因。
- [`streaming-feed-performance`](./streaming-feed-performance/spec.md)：统一服务端查询预算、App 长滚动窗口、媒体预热、弱网恢复与 typed 性能证据。
- [`time-decay-contextual-ranking`](./time-decay-contextual-ranking/spec.md)：按时间衰减、时段、季节和事件上下文调整候选分数，同时保持策略版本可解释。
- [`travel-vertical-recommendation`](./travel-vertical-recommendation/spec.md)：推荐召回、fallback 和交集理由通道均使用同一 channel/vertical 口径。
- [`unified-items-cursor`](./unified-items-cursor/spec.md)：feed 查询快照遵守 runtime-client-foundation 的本地缓存规则，只从 content-service canonical Post/cursor contract 派生且不维护对象策略台账。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 四类内容共用候选编排并保留类型特有策略
- 决策：四类内容由 recommendation-service 的单一 Python CandidateIndex/FeatureProfile/RankedRecommendationWindow 编排并保留类型特有策略；Content 只做 Post 权限 hydration、FeedDeliveryPage 与公开响应。
- 理由：发现流推荐编排的端云行为、流式体验、交集解释、曝光治理集成边界与推荐 SLO 基线。
- 被否决方案：由 Content Go、调用方、页面或脚本复制候选/特征/交集/排序状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`collaborative-recall`](./collaborative-recall/spec.md)、[`feed-fallback-degrade`](./feed-fallback-degrade/spec.md)、[`feedback-ingestion-sampling`](./feedback-ingestion-sampling/spec.md)、[`interest-onboarding-prior`](./interest-onboarding-prior/spec.md)、[`personalized-ranking`](./personalized-ranking/spec.md)、[`premium-stream-recommendation`](./premium-stream-recommendation/spec.md)、[`quality-score-cold-start`](./quality-score-cold-start/spec.md)、[`ranking-calibration`](./ranking-calibration/spec.md)、[`realtime-feed-baseline`](./realtime-feed-baseline/spec.md)、[`streaming-feed-performance`](./streaming-feed-performance/spec.md)、[`time-decay-contextual-ranking`](./time-decay-contextual-ranking/spec.md)、[`travel-vertical-recommendation`](./travel-vertical-recommendation/spec.md)、[`unified-items-cursor`](./unified-items-cursor/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 性能预算由各资源 owner 强制，由 feed Story 组合验收
- 决策：content-service 拥有 feed cursor、query/index、projection、active supply 与服务端并发预算。App 拥有请求 generation、列表窗口、渲染、本地缓存与媒体资源生命周期。runtime、gateway 与 product-ops 分别拥有弹性、统一入口与 typed telemetry，本 L2 只组合端到端验收。
- 理由：把所有优化放进 feed controller 会复制缓存、限流、视频和监控真相源，且无法独立证明各资源退出。
- 被否决方案：仅扩大 `cacheExtent`、只移除 analytics denylist、只添加内存 Map，或在端侧解析 cursor 来补偿服务端问题。
- 约束与影响：每个预算都必须同时有配置真相源、终态、typed 观测、超限恢复与直接测试；真机、四环境或 Provider 证据缺失时保持 `GATE_BLOCK`。
- 关联要求：`REQ-003`
- 影响 Story：本决策约束 [`streaming-feed-performance`](./streaming-feed-performance/spec.md) 的端到端性能组合。
- 关联验收：`SIT-002`

<a id="dec-003"></a>
### DEC-003 推荐续页只读取不可变 RankedFeedWindow
- 决策：推荐域在首刷完成最终排序后，把同一次 feedRequest 的有序结果、训练快照、归因及 actor/session/route/release/candidate/policy/model/feature/ranking 来源绑定为 Redis `RankedFeedWindow`。content-service 只用 AEAD cursor 携带 `(windowId, afterOrdinal, afterContentId, expiresAt)`，续页不得重新召回或读取 live score。`RankedFeedWindow` 与 `FeedDeliveryPage` 都使用固定 quota shard 的 canonical `rec:ranked_feed_window:*` / `rec:feed_delivery_page:*` value/index/metadata，由同槽 Lua 原子执行 owner 淘汰和全族 live key/live payload byte 准入。key、payload 与 cursor 均不设置协议版本前缀或 schema-version 信封。
- 理由：最终顺序会同时受多召回源、请求期特征、模型、运营策略、多样性和频控影响，Mongo score 或 `_id` keyset 无法保证翻页无重复、无漏项。
- 被否决方案：续页 live recompute、把当前 Mongo 排序当推荐 keyset、端侧解析推荐状态、无字节/主体/全族基数上限的随机 Redis key、每 owner 独占 slot、依赖 `maxmemory`、动态 Lua key、无界 scan、mutable quota counter、版本化 key/payload/cursor、双读或兼容 shim。
- 约束与影响：窗口 TTL 为 10 分钟且不因读取续期，单窗口未压缩 JSON 不超过 2 MiB、最多 300 项、同 canonical 配额主体最多 8 个活跃窗口。具名/已验证设备流量的主体是命名空间化 actor，无身份公开流量的主体是命名空间化 session，禁止全局匿名 fallback actor 造成跨游客淘汰。RankedFeedWindow 默认 256 shard * (128 value / 128 MiB)，全族最多 32768 value / 32 GiB live payload。FeedDeliveryPage 默认 256 shard * (512 value / 32 MiB)，全族最多 131072 value / 8 GiB live payload，每 scope 保留 400 页。序列化先执行 content/user/tag/entity owner 单字段 byte/count 门，再按条目累计聚合 wire bytes，超限立即 fail-closed，不先物化无界整窗 JSON，也不通过截断条目或业务字段伪造成功。Adapter 只读取 shard cap + 1 个索引成员，Lua 只访问显式 `EVAL KEYS` 并从有界 index/metadata 精确重算用量。owner 超限只淘汰自身，shard 超限只拒绝 contender。商用 HotPath 构造期必须要求 Redis pipeline capability，session、硬排除、曝光过滤和 relaxed exposure 均只走同一 pipeline，不保留顺序/并行兼容回退。生产必须以单候选制受控发布并验证 cursor 刷新、告警 readback 与回滚。默认冻结深度仍须由长滚动产品验收决定，代码硬上限本身不代表环境容量已通过。
- 关联要求：`REQ-001`
- 影响 Story：本决策约束该 Story 的推荐续页路径。
- 关联验收：`SIT-002`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；feed 首屏、翻页、滚动帧、视频 TTFF/rebuffer/seek、缓存、ANR 与内存压力必须从 product-ops catalog 的 typed event 派生，且分子、分母、低基数维度、采样、保留、SLO 与告警同源。
- 清洁帧、缓存命中和成功终态不得被丢弃，否则不能作为比率分母。任何没有真实采样、空脚本或仅源码文本断言的性能门禁均失败。
