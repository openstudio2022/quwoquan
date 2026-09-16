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
- 曝光、点击、停留、分享与显式负反馈经统一行为契约回流；关注和点赞的业务成功只消费各 owner 的已确认持久事实，不能由端侧批量行为 tracker 再上报为第二业务事实。点击归因可以保留，但不代替成功事实。
- Post 级收藏已退役，不恢复 favorite 行为、按钮或推荐贡献；实体想去等独立意图不被改称 Post 收藏，现有合法历史按所属保留合同处理。
- 端侧行为经单一 BehaviorReporter 分级上报（强信号即时、弱信号采样合并），幂等与合法曝光归因闭环；显式负反馈影响未来窗口，不把取赞当作负反馈。当前 block/权限收缩仍须交付前安全过滤，不受排序冻结豁免。
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

<a id="req-004"></a>
### REQ-004 已确认互动与稳定窗口、当前资格分层交付

- Feed 只组合各 owner 的已确认人物关系、Reaction 与独立统计结果；端侧按钮/命令状态与统计新鲜度正交，计数落后不延长已确认命令，不补发写入，也不从本地点击推断热度已进入评分。
- 普通流的关注是请求期软特征，following 按所属关注类型当前资格硬过滤；点赞、取赞与新增关注只影响下一次明确刷新或新窗口。旧窗口固定期限、原序续页，不因每次互动重新排序。
- 取关后的 following 候选、屏蔽与失权内容在交付前由当前 owner 资格过滤，只移除不重排；不能安全续接时显式返回 canonical 窗口失效并新首刷，不以旧窗口、缓存或旧 cursor 放行。
- 新 following 窗口的因果追齐只接受受信确认结果关联的最近实际关系事件；no-op 增加的仲裁版本没有对应事件时不等待它，首次关系空态须有权威证明且只终结该关系因果要求，不能据单 Pair 空态推断整个关注流为空。未追齐、读取失败与完整查询范围的健康空关注流严格区分，等待、批量与引用大小有界。
- 推荐事实、取赞当前贡献撤销和实际 scorer 消费归 [runtime-recommendation REQ-003](../../runtime/runtime-recommendation/spec.md#req-003)、[REQ-004](../../runtime/runtime-recommendation/spec.md#req-004)；本能力只验收交付行为，不建立第二画像、热度或关系写入方。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层 [DEC-003](./design.md#dec-003) 与 [runtime-recommendation DEC-004](../../runtime/runtime-recommendation/design.md#dec-004) 的稳定窗口、因果追齐与当前资格边界。
- 业务来源：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/`、`quwoquan_service/services/user-service/contracts/relationship/subject_follow/`、`quwoquan_service/services/content-service/contracts/content/content_reaction/`；Feed/行为入口只引用 Content `post/` 与 `content_behavior_fact/` canonical contracts，窗口协议只引用 Recommendation `ranked_recommendation_window/`。不得将 tracker 的载荷当作第二套命令或成功事实。

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
- THEN 曝光、点击、停留、分享与显式负反馈按统一行为契约进入单一 BehaviorReporter；关注/点赞成功只来自 owning durable fact，批量 tracker 与 UI 归因不再次建立业务成功或重复偏好。
- THEN Post 收藏保持退役，独立实体意图不被改称收藏；取赞撤当前贡献而非负反馈，合法历史按合同保留。排序信号只影响未来窗口，当前权限收缩始终在交付前过滤。
- THEN 推荐 SLO/KPI 有真相源，至少覆盖 feed 延迟、空结果率、fallback 率、重复曝光率、CTR、停留、完成率与负反馈率。

<a id="sit-002"></a>
### SIT-002 首页流式性能与可用性 SIT

- GIVEN 首页在正常网络、受控弱网、并发峰值、持续滚动与长会话中消费真实 Remote feed 与 media。
- WHEN 用户首刷、翻页、跨频道、打开视频书、切集、前后台恢复或离线重入。
- THEN 请求、状态、内存、磁盘、图片和视频资源全部有界，取消或过期 generation 不回写，已有内容不被分页失败遮挡。
- AND 依赖故障在声明预算内返回 canonical failure 或明确允许的缓存/降级结果，不无限等待、重试放大或伪造成功。
- AND typed telemetry 能以分母还原首屏、滚动、视频 QoE、缓存、ANR/卡顿与内存压力，并与 SLO/告警同源。

<a id="sit-003"></a>
### SIT-003 confirmed 互动到新窗口、旧窗续页与当前权限交付

- GIVEN 真实 Feed/详情已有稳定窗口，用户关注与点赞由 owning command 确认，统计或关系投影可被受控延迟。
- WHEN 用户点赞、取赞、关注、取关后继续翻页、明确刷新，并发生屏蔽或内容权限收缩。
- THEN 批量行为上报不另造关注/点赞成功，按钮按确认事实收敛，统计未追齐不重发命令；Post 收藏入口与 favorite 贡献保持退役。
- AND 普通流只在新窗口消费软特征，following 只下发当前合格对象；旧窗口相对顺序不变，只移除失权条目或显式失效，cursor 不偷换排序。
- AND 因果新首刷只等待可信实际事件，无事件 no-op 和权威空态可终结；未追齐/依赖失败不伪装为没有关注，当前权限失败不得被旧窗口放行。
- 证据层：local_contract 验证 tracker/状态/续页时序；api_integration 关联真实 command receipt、自动 worker、窗口及安全 reader；user_acceptance 以 Android/iPhone 真实 App 操作与同事实读回证明交付，不以 UI 改变或 HTTP 成功代替。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 content 库 rm_discovery_feed 双写待收敛单轨

- 类型：`risk`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：content 库的 `rm_discovery_feed`（`releaseimport.UpsertDiscoveryFeed` 与在线 `DiscoveryFeedProjector` 双写）当前无任何在线读方；feed 读路径已单轨经 recommendation-service 候选投影与 RankedRecommendationWindow，残留双写构成第二真相源回归风险。裁决为收敛单轨：删除 content 侧双写与 `projections/discovery_feed.yaml` 声明，读写真相统一归 recommendation-platform REQ-001。删除前置条件：四环境存量集合处置方案、release importer 字节幂等回归、冷启动候选供给证明只依赖 `PostPublished` outbox → `events.content.post_lifecycle` 链路。
- 识别现场：`705e1b8` 已删除 release importer 侧的 `UpsertDiscoveryFeedWithOptions` 调用，本次退役只完成了写入侧。
- 识别现场：`releaseimport/runtime.go` 的 `UpsertReleaseState` 仍把 `readback.counts.discoveryPosts` 映射到永不写入的 `counts["feedUpserted"]`，环境侧回读恒为 `null`。
- 识别现场：`release_readiness.py` 与 `app_preflight_readiness.py` 仍以 `discoveryPosts` 非零作为环境准入判据，alpha 实测 `postsUpserted=5` 而 `discoveryPosts=null`，`contentBindingState` 因此无法进入 `bound`。
- 识别现场：上述悬空引用属于本次退役的收尾范围，随读写真相收敛一并清除，不单独立项。
- 完成判定：`SIT-001` 在 content-service 不再写 `rm_discovery_feed` 的前提下仍然成立。投影契约声明与 importer 写入同步删除，release readback/readiness 不再引用退役的 `discoveryPosts/feedUpserted`，而以 canonical Post/recommendation identity 判定 bound。Alpha/Beta/Gamma 对同一 `releaseId + manifestDigest` 的 import、activation、readback 均进入 `contentBindingState=bound`，首页 Remote UAT 读到同一 identity。无合格 release 时保持 typed blocker 或 `no_active_release`，不得以普通空列表通过。

<a id="open-002"></a>
### OPEN-002 confirmed 互动与窗口交付尚缺端云同候选证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[REQ-004](./spec.md#req-004) 与修订的 [SIT-001](./spec.md#sit-001) 不再接受 tracker 上报点赞/关注成功或旧 favorite 行为；独立统计、因果追齐、no-op 空态与当前安全过滤尚无当前候选的完整端云证据。现有稳定窗口或局部行为测试不能代替。
- 完成判定：[SIT-003](./spec.md#sit-003) 以及 [SIT-001](./spec.md#sit-001) 的行为回流修订有同候选真实测试与完整 `spec_ref`，分别提供本地、真实 Remote/自动 worker 与双物理设备的读回证据。新增 source/因果/统计 wire 完成 owning authoring 和生成后才允许对应实现准入；未运行、skip、无设备或依赖不可用时保持阻断。
- 依赖：[runtime-recommendation OPEN-002](../../runtime/runtime-recommendation/spec.md#open-002)、User 人物关系和 SubjectFollow 资格、Content Reaction 与 Post 当前安全读面；不扩成本层私有画像或第二命令通道。
