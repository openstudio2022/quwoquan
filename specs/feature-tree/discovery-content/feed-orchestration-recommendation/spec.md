# L2 Business Capability：内容流编排推荐 (`feed-orchestration-recommendation`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

发现流推荐编排的端云行为、流式体验、交集解释、曝光治理集成边界与推荐 SLO 基线。

## 2. 范围与非目标

### In Scope

- 首页 feed 首屏、翻页、刷新、续接、四态与推荐理由展示规格。
- 端侧行为回流到推荐 HotPath/FeedbackRecorder 的契约与测试。
- 交集理由同源消费、发现流多形态布局、关注对象列表与曝光/点击归因。
- 非深排 P0：质量分投影消费、协同物化召回读取、旅行垂类和精品流式路由。
- served/impressed 双轨、跨页去重、负反馈即时抑制和曝光健康 SLI 的集成边界；曝光治理策略所有权归属 `discovery-content/exposure-governance`。

### Out of Scope

- 深度排序模型平台轨（MMoE/PLE/ESMM、双塔 ANN、IPS）。
- 协同过滤离线物化作业和 replay 评估脚本。
- Thompson Sampling、生命周期复活、Bloom/Cuckoo/Count-Min 等海量曝光基础设施实现。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-007`](../../spec.md#scn-007)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：发现流推荐编排的端云行为、流式体验、交集解释、曝光治理集成边界与推荐 SLO 基线，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`collaborative-recall`](./collaborative-recall/spec.md)：从符合隐私和最小样本约束的 itemCF、Swing 与 u2i 信号生成候选并保留召回理由。
- [`feed-fallback-degrade`](./feed-fallback-degrade/spec.md)：定义“内容流回退降级”的可观察主路径、失败语义及父能力交接。
- [`feedback-ingestion-sampling`](./feedback-ingestion-sampling/spec.md)：统一上报通道 `BehaviorReporter`：单一出口，消除双通道重复上报与 behaviors/ops 双写。
- [`interest-onboarding-prior`](./interest-onboarding-prior/spec.md)：定义“兴趣引导先验”的可观察主路径、失败语义及父能力交接。
- [`personalized-ranking`](./personalized-ranking/spec.md)：定义“个性化排序”的可观察主路径、失败语义及父能力交接。
- [`premium-stream-recommendation`](./premium-stream-recommendation/spec.md)：统一精品流的路由、排序与解释；全局精品先经 product-ops 写入并由 Recommendation 候选投影与排序窗口处理，Content 只做当前权限 hydration 与交付。
- [`quality-score-cold-start`](./quality-score-cold-start/spec.md)：在缺少用户行为时以内容质量分和受控先验排序，并在反馈到达后逐步让位于个性化信号。
- [`ranking-calibration`](./ranking-calibration/spec.md)：以点击、完成和负反馈校准排序分，使预测分与真实结果在声明窗口内对齐。
- [`realtime-feed-baseline`](./realtime-feed-baseline/spec.md)：统一 sessionId / feedRequestId 归因。
- [`streaming-feed-performance`](./streaming-feed-performance/spec.md)：统一首屏、长滚动、弱网、峰值、长会话与视频书的有界资源、恢复终态和 typed 性能证据。
- [`time-decay-contextual-ranking`](./time-decay-contextual-ranking/spec.md)：按时间衰减、时段、季节和事件上下文调整候选分数，同时保持策略版本可解释。
- [`travel-vertical-recommendation`](./travel-vertical-recommendation/spec.md)：推荐召回、fallback 和交集理由通道均使用同一 channel/vertical 口径。
- [`unified-items-cursor`](./unified-items-cursor/spec.md)：feed 查询快照遵守 runtime-client-foundation 的本地缓存规则，只从 content-service canonical Post/cursor contract 派生且不维护对象策略台账。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 首页推荐流端云编排 SIT

- Feed 首屏、翻页、刷新与续接语义清晰，端侧只透传 cursor，不解析 token。
- 首页频道按 metadata layout policy 呈现：关注单列、精品侵入式、推荐/校园/旅行/摄影手机双列发现流，文章/口碑/强交集解释可 full-span。
- 同一个 PostBaseDto / ContentSurfaceView / IntersectionReason 支持单列、双列、侵入式和对象页承接，不新增第二套首页业务列表。
- 交集模块从 feed intersectionReasons 或 tag-service shared-tags 同源派生，用户行动回流 intersectionDimension / intersectionTagRefs。
- 关注频道登录后展示关注对象顶部列表，覆盖用户、圈子、地点和事物主页；上次访问后变化以红点提示，点击对象并进入主页后可消红点。
- 行为上报（impression/click/dwell/like/favorite/share/dislike/report）可进入统一行为契约，强负反馈只影响未来窗口。
- 端侧反馈经单一 BehaviorReporter 通道分级上报（强信号即时、弱信号采样合并），clientEventId 幂等、feedRequestId 归因闭环，不双通道重复上报。
- 推荐 SLO/KPI 有真相源，至少覆盖 feed 延迟、空结果率、fallback 率、重复曝光率、CTR、停留、完成率与负反馈率。

<a id="req-002"></a>
### REQ-002 内容：四类内容（article/moment/photo/video）与数据工程冷启动内容进入同一 feed 契约，禁止 UI 或 mock 复制第二套业务列表

- 内容：四类内容（article/moment/photo/video）与数据工程冷启动内容进入同一 feed 契约，禁止 UI 或 mock 复制第二套业务列表。
- 时间：首屏、翻页、刷新、续接、曝光窗口、疲劳窗口与内容新鲜度按统一 cursor/session 语义解释。
- 交集：feed 卡片、交集 spotlight、对象主页和我的交集收件箱都只消费服务端 `IntersectionReason.primaryText` 与同源交集字段，禁止本地拼装第二套交集理由。
- 旅行垂类：`subCategory=travel` 归一为 `vertical=travel_photography`，召回和 fallback 都不得混入非旅行内容。
- P0+ 观测归因闭环：feed 下发、App 行为上报、content-service raw event、learning context 和 Prometheus 分桶指标统一携带 `feedRequestId/channelId/contentVertical/supplySource/recallPath/policyDigest/intersectionSourceRef/intersectionClass`，支持按首页、旅行、精品、UGC、数据工程、召回路径、唯一策略摘要和交集类别评价效果。
- `GET /content/feed` 是内容 feed 读取入口；`sort=recommend`、cursor、sessionId、feedRequestId 必须保持端云一致。
- `POST /content/behaviors` 是行为回流入口
- 新增行为字段与 action 必须 metadata-first
- 端侧统一上报通道、分级采样、clientEventId 幂等与 feedRequestId 归因见 L3 `feedback-ingestion-sampling`。
- 推荐排序运行时只通过 recommendation-service 的 CandidateIndex、FeatureProfile、RankedRecommendationWindow 与 active ModelRelease 消费策略；Content 只调用 generated ranked-page transport 并做 Post 权限 hydration，禁止在 Go、UI、Repository 或 intersection 另起 ranker。
- 推荐 SLO/KPI 可观测：延迟、空 feed、fallback、重复曝光率、CTR、停留、完成率、负反馈率；P0+ 归因指标必须能按 `channel/vertical/supply_source/recall_path/policy_digest/intersection_class` 分桶。
- `科技 / 汽车` 与校园、旅行、摄影一致，手机端统一双列发现流；文章、长评、口碑等强解释内容通过详情页与对象页承接，而不是在首页单独切一套 full-span 主布局。

<a id="req-003"></a>
### REQ-003 首页流式性能与可用性端云闭环

- 首屏、翻页、刷新、视频准备、弱网恢复与长会话必须共用 canonical feed/media/cache/runtime-governance 契约，不在 UI 、Repository 或环境装配中建立第二真相源。
- 服务端 query 放大、数据库扫描、并发、缓存与依赖时间，以及 App 列表窗口、图片字节、视频解码槽位和长会话集合均须有明确上限与可观测退出路径。
- 性能验收只使用 typed telemetry、真实 Remote composition、对象级 typed double 与受控真机/环境证据；不以源码 grep、空门禁、fixture 或无分母的样本代替可用性证明。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 首页推荐流端云编排 SIT

- GIVEN 执行“首页推荐流端云编排”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“首页推荐流端云编排”对应动作。
- THEN Feed 首屏、翻页、刷新与续接语义清晰，端侧只透传 cursor，不解析 token。
- THEN 首页频道按 metadata layout policy 呈现：关注单列、精品侵入式、推荐/校园/旅行/摄影手机双列发现流，文章/口碑/强交集解释可 full-span。
- THEN 同一个 PostBaseDto / ContentSurfaceView / IntersectionReason 支持单列、双列、侵入式和对象页承接，不新增第二套首页业务列表。
- THEN 交集模块从 feed intersectionReasons 或 tag-service shared-tags 同源派生，用户行动回流 intersectionDimension / intersectionTagRefs。
- THEN 关注频道登录后展示关注对象顶部列表，覆盖用户、圈子、地点和事物主页；上次访问后变化以红点提示，点击对象并进入主页后可消红点。
- THEN 行为上报（impression/click/dwell/like/favorite/share/dislike/report）可进入统一行为契约，强负反馈只影响未来窗口。
- THEN 端侧反馈经单一 BehaviorReporter 通道分级上报（强信号即时、弱信号采样合并），clientEventId 幂等、feedRequestId 归因闭环，不双通道重复上报。
- THEN 推荐 SLO/KPI 有真相源，至少覆盖 feed 延迟、空结果率、fallback 率、重复曝光率、CTR、停留、完成率与负反馈率。

<a id="sit-002"></a>
### SIT-002 首页流式性能与可用性 SIT

- GIVEN 首页在正常网络、受控弱网、并发峰值、持续滚动与长会话中消费真实 Remote feed 与 media。
- WHEN 用户首刷、翻页、跨频道、打开视频书、切集、前后台恢复或离线重入。
- THEN 请求、状态、内存、磁盘、图片和视频资源全部有界，取消或过期 generation 不回写，已有内容不被分页失败遮挡。
- AND 依赖故障在声明预算内返回 canonical failure 或明确允许的缓存/降级结果，不无限等待、重试放大或伪造成功。
- AND typed telemetry 能以分母还原首屏、滚动、视频 QoE、缓存、ANR/卡顿与内存压力，并与 SLO/告警同源。
