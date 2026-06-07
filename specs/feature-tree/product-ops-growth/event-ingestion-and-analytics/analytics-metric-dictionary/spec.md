# L3 特性：analytics-metric-dictionary

## 功能说明

定义全链路埋点与反馈基础设施的统一指标字典，作为产品体验、用户行为、持续运营、在线学习与实验分析的唯一口径源。

字典覆盖全 App 域，并支持从领域服务 -> 页面表面 -> 内容/实体 -> 事件 -> 实验桶的下钻。

### 指标域

1. `experience`
   - 页面 `open / return`
   - 冷启动时长
   - 首帧时间
   - 页面错误率
   - 降级触发率
2. `qoe`
   - 视频首帧、解码失败率、卡顿率、播放进度分布
   - RTC 接通率、掉线率、弱网重试率
3. `behavior`
   - impression、有效曝光、click、dwell、scrollDepth、completion、replay
   - like/comment/favorite/share/dislike/report
4. `social`
   - 消息发送成功率、送达率、已读率、首回复时延、会话深度
5. `share`
   - 分享发起率、渠道分布、回流打开率、分享转化率
6. `entity`
   - 实体曝光率、实体点击率、绑定位置点击分布、实体转化结果
7. `learning`
   - InteractionEvent 上报成功率、Scorecard 完整率、反馈注入命中率、训练资格覆盖率
8. `experiment`
   - variant 覆盖率、uplift、回滚影响、收益/风险差异
9. `ops`
   - 漏斗完成率、留存、回流、类目/创作者/实体质量、策略收益

## 统一维度标准

### 公共维度
- `sessionId`
- `pageVisitId`
- `traceId`
- `requestId`
- `surfaceId`
- `routeId`
- `operationId`
- `requestId`
- `experimentBucket`
- `userIdHash`
- `appVersion`
- `platform`
- `networkClass`
- `occurredAt`

### 业务维度
- 内容：`contentId`、`contentType`、`authorId`、`circleId`
- 社交：`conversationId`、`messageId`、`rtcSessionId`
- 实体：`entityType`、`entityId`、`bindPosition`
- 学习：`runId`、`traceId`、`scorecardType`、`feedbackTarget`
- 交集：`intersectionDimension`（identity/location/content/interest/relationship 五维之一）、`intersectionTagRef`（路径制 tagRef，唯一真相源 `quwoquan_data/publish/v1/tags`）

## 指标定义原则

- 同一指标只能有一个主口径，不允许 dashboard、推荐、Assistant、BI 各自维护第二套定义。
- 指标必须声明：
  - 指标域；
  - 分子/分母；
  - 采样规则；
  - 默认时间粒度；
  - 支持的下钻维度；
  - 是否可用于训练/实验；
  - 数据延迟与 freshness 预期。
- 页级指标优先复用 `pageVisitId`；内容级指标优先复用 `contentId`；实体级指标优先复用 `entityType/entityId`。

## 对标吸收映射

- 微信：`messageDeliveryRate`、`messageReadRate`、`firstReplyLatencyMs`、`conversationDepth`
- 字节：`videoFirstFrameMs`、`completionRate`、`replayRate`、`negativeFeedbackRate`
- 今日头条：`effectiveImpressionRate`、`ctr`、`readingDepth`、`refreshQuality`
- 小红书：`shareOpenBackRate`、`entityExposureRate`、`entityClickRate`、`shareConversionRate`

## 约束

- 指标字典必须与 `event-schema-governance` 的字段与 envelope 兼容。
- 新增指标不得绕过字典直接进入 dashboard 或模型特征表。
- 用户可见体验指标与训练指标共享口径，但可有不同聚合层。
- 指标名称、分组与含义必须稳定，版本升级必须记录兼容策略。

## 五栏小趣 L1-L4 指标口径

本节冻结“五栏全局小趣”收口后的四层指标唯一口径，供 App 埋点、服务端 RED 指标、product-ops 汇总和 ops-portal 看板共同消费。

| 层级 | 主口径 | 核心指标 | 必带维度 |
| --- | --- | --- | --- |
| L1 产品结果 | 用户是否形成“遇见同趣”的核心旅程 | `five_tab_journey_completion_rate`、`xiaoqu_entry_to_reply_rate`、`campus_or_travel_homepage_open_rate`、`circle_join_rate` | `surfaceId`、`routeId`、`feedRequestId`、`primaryDomain` |
| L2 业务质量 | 内容、圈子、主页、消息是否形成闭环 | `featured_ctr`、`circle_scenario_ctr`、`homepage_content_attach_rate`、`xiaoqu_comment_accept_rate`、`message_delivery_clickback_rate` | `feedType`、`circleId`、`homepageId`、`topicId`、`conversationId` |
| L3 系统健康 | 端云请求和推荐链路是否稳定 | `api_red_requests_total`、`api_red_error_rate`、`api_red_duration_p95_ms`、`recommendation_recall_hit_rate`、`assistant_reply_latency_p95_ms` | `service`、`operationId`、`runtimeEnv`、`statusCode` |
| L4 基础设施 | 存储、队列、网关、监控是否支撑 beta 验证 | `gateway_up`、`ops_portal_up`、`product_ops_up`、`queue_lag_seconds`、`redis_latency_p95_ms`、`mongo_latency_p95_ms` | `component`、`region`、`runtimeEnv`、`instanceId` |

### SLO 基线

- L1：T4 旅程 `首页精品 -> 圈子校园 -> 北京大学主页 -> 评论 @小趣 -> 消息承接 -> ops 可见` 完成率 beta ≥ 90%。
- L2：推荐 surface `featured / circle / campus / travel / homepage_detail / search_xiaoqu` 均必须上报曝光、点击、CTR 和停留；缺任一维度视为看板不可发布。
- L3：核心 API RED p95 < 800ms，错误率 < 1%；assistant 评论回复 p95 < 5s；recommendation recall hit rate ≥ 95%。
- L4：`gateway / product-ops / ops-portal / observability` beta health check 可用率 ≥ 99%，队列延迟 p95 < 30s。

### 埋点事件覆盖

- 底栏切换：`app.bottom_tab.switch`，维度 `fromTab / toTab / routeId`。
- Surface 展示：`surface.view`，维度 `surfaceId / routeId / pageVisitId`。
- Feed 曝光：`feed.impression`，维度 `feedRequestId / feedType / surfaceId / itemId / rank`。
- 实体主页打开：`homepage.open`，维度 `homepageId / homepageType / sourceSurface`。
- 问小趣：`xiaoqu.open`，维度 `assistantOpenContext / routeId / surfaceId`。
- 评论/群聊 `@小趣`：`xiaoqu.mention.triggered`，维度 `postId / commentId / conversationId / circleId / homepageId`。
- 创作绑定实体：`content.homepage.attach`，维度 `postId / homepageId / bindPosition`。

## 交集转化北极星指标（S6 增长商业化）

「交集」是全 App 北极星。本节冻结交集转化漏斗的唯一口径，供推荐回流、ops 看板、实验分析共同消费。交集行动在 `content/post/behaviors.yaml` 以三个独立 `BehaviorAction` 区分，使漏斗可按动作类型切分：

| 主口径 | 指标 | 分子 / 分母 | 下钻维度 | 说明 |
| --- | --- | --- | --- | --- |
| 新增可解释交集 | `explainable_intersection_count` | 计数：携带 `intersectionDimension` 曝光的交集卡/理由数 | `intersectionDimension`、`intersectionTagRef`、`surfaceId` | 交集解释层供给侧 |
| 交集转化率（北极星） | `intersection_conversion_rate` | 交集行动数（follow + join_circle + add_contact）/ 新增可解释交集数 | `intersectionDimension`、`intersectionTagRef`、`action` | 唯一北极星，按维度/动作下钻 |
| 关注转化 | `intersection_follow_rate` | `follow`（带 intersectionDimension）/ 新增可解释交集数 | `intersectionDimension`、`intersectionTagRef` | 三类行动之一：关注人 |
| 进圈转化 | `intersection_join_circle_rate` | `join_circle` / 新增可解释交集数 | `intersectionDimension`、`circleId` | 三类行动之一：进圈子 |
| 加联系人转化 | `intersection_add_contact_rate` | `add_contact` / 新增可解释交集数 | `intersectionDimension`、`authorId` | 三类行动之一：加联系人 |

- 采样规则：全量；默认时间粒度按日（`DailyMetricsStore` `intersection` 维度累计）。
- 服务端口径：`content-service` `BehaviorService.ProcessBatch` 对带 `intersectionDimension` 的信号按维度累计 `intersection` 日指标；推荐 HotPath 消费 `BehaviorSignal.IntersectionDimension/IntersectionTagRefs` 做交集回流。
- 数据延迟：交集转化日指标 freshness ≤ 1 日；实时回流随 HotPath 同步。
- 训练/实验：可用于实验桶切分（`product-ops-growth/experiment-bucketing-and-rollout`），按 `intersectionDimension` 评估交集策略 uplift。

## 验收标准

- A1：体验/行为/QoE/社交/分享/实体/学习/实验/运营九大指标域完整登记。
- A3：支持从领域到页面到内容/实体/实验桶的下钻分析。
- A4：推荐、Assistant、运营可基于同一指标口径消费数据。
- A7：新增指标必须经过字典治理与版本评审。
- A8：形成可支撑 baseline 的指标词典与维度标准文档。
- A9：交集转化北极星 `intersection_conversion_rate` 可按 `intersectionDimension` / `action` 下钻；三类交集行动（follow/join_circle/add_contact）端云字段一致且可区分漏斗。
