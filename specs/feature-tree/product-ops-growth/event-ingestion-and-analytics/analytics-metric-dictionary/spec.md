# L3 特性：analytics-metric-dictionary

## 功能说明

定义产品日志、推荐反馈和服务 RED 指标的统一口径与来源边界。产品日志只覆盖页面、启动、关键动作、
性能和异常；推荐/社交/Assistant 等业务事实继续由各自 metadata 与指标提供，不塞入产品日志信封。

App 体验一级黄金指标的机器真相源为
`quwoquan_service/contracts/metadata/ops/event_record/golden_metric_catalog.yaml`；本文解释语义，
Dashboard、告警和 Portal 不得复制其分子、分母、目标值或下钻维度。

### 指标域

1. `experience`
   - 页面 `open / return`
   - 冷启动时长
   - 首帧时间
   - 页面错误率
   - 降级触发率
   - `ops_startup_phase_total`、启动阶段耗时 histogram、`attempt_started → first_frame → shell` 漏斗、
     未终态 attempt、离线补传延迟与本地 journal 溢出率
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

### 产品日志公共维度

- `logType`
- `eventType`
- `sessionId`（仅三天 raw、高权限精确查询，不进入 Prometheus label）
- `pageName`
- `occurredAt`
- `deviceManufacturer`
- `deviceModel`
- `appVersion`
- `networkClass`

`operationId/errorCode/httpStatus/durationMs` 等只在目录允许的具体事件中作为强类型扩展，
不属于所有事件的公共维度。

### 业务维度
- 内容：`contentId`、`contentType`、`authorId`、`circleId`
- 社交：`conversationId`、`messageId`、`rtcSessionId`
- 实体：`entityType`、`entityId`、`bindPosition`
- 学习：`runId`、`traceId`、`scorecardType`、`feedbackTarget`
- 交集：`intersectionDimension`（identity/location/content/interest/relationship 五维之一）、`intersectionTagRef`（路径制 tagRef，唯一真相源 `quwoquan_data/control_plane/governance/taxonomy`）

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
- 产品日志页级指标只使用目录生成的 `pageName/sessionId`；内容级、实体级与推荐指标分别复用其业务契约中的 `contentId`、`entityType/entityId` 与 attribution 字段，不把这些字段塞回公共日志信封。

## 对标吸收映射

- 微信：`messageDeliveryRate`、`messageReadRate`、`firstReplyLatencyMs`、`conversationDepth`
- 字节：`videoFirstFrameMs`、`completionRate`、`replayRate`、`negativeFeedbackRate`
- 今日头条：`effectiveImpressionRate`、`ctr`、`readingDepth`、`refreshQuality`
- 小红书：`shareOpenBackRate`、`entityExposureRate`、`entityClickRate`、`shareConversionRate`

## 约束

- 指标字典必须与 `event_catalog.yaml` 和各领域业务 metadata 同源；不得把 BehaviorSignal 伪装成 Ops 事件。
- 新增指标不得绕过字典直接进入 dashboard 或模型特征表。
- 每个关键业务最多登记 3 个一级黄金指标；二级指标只能用于定位一级指标。机器门必须校验
  source event、value field、freshness、SLO target 和高基数维度禁用。
- 用户可见体验指标与训练指标共享口径，但可有不同聚合层。
- 指标名称、分组与含义必须稳定；当前未上线阶段采用单轨替换，不维护事件版本兼容信封。
- 启动指标的低基数标签只允许 `phase`、`outcome`、`platform`、`runtime_env` 与
  `recovery_surface`；`attemptId`、eventId、设备/账号标识和原始错误不得成为指标标签。

### App 体验三项一级黄金指标

1. `app_anr_rate`：发生 `app_anr_outcome(result=detected)` 的去重会话 /
   `app_startup` 会话，目标 `< 0.47%`。
2. `page_first_usable_p95_ms`：`page_first_usable.durationMs` 的 P95，内容、空态和错误态均
   进入分布，目标 `≤ 2000ms`。
3. `page_error_recovery_rate`：`page_error_outcome(result=recovered)` /
   `page_error_outcome(result=shown)`，目标 `≥ 80%`。

三项 freshness 均为 300 秒；允许按 `pageName/appVersion/networkClass` 及各事件的受控低基数
扩展下钻，禁止 `sessionId/requestId/traceId/callStack/correlationHash` 成为指标维度。

## 五栏小趣 L1-L4 指标口径

本节冻结“五栏全局小趣”收口后的四层指标口径。每层必须读取下表声明的真实来源；“统一口径”不表示所有指标统一写入 `/ops/events`。

| 层级 | 主口径 | 核心指标 | 真实来源 |
| --- | --- | --- | --- |
| L1 产品结果 | 用户是否形成“遇见同趣”的核心旅程 | `five_tab_journey_completion_rate`、`xiaoqu_entry_to_reply_rate`、`campus_or_travel_homepage_open_rate`、`circle_join_rate` | 页面产品事件小时聚合 + 各领域业务事实，按服务端门面组合，不做 App 胖事件 |
| L2 业务质量 | 内容、圈子、主页、消息是否形成闭环 | `featured_ctr`、`circle_scenario_ctr`、`homepage_content_attach_rate`、`xiaoqu_comment_accept_rate`、`message_delivery_clickback_rate` | `/content/behaviors`、内容事务 outbox、消息/Assistant 领域指标 |
| L3 系统健康 | 端云请求和推荐链路是否稳定 | `api_red_requests_total`、`api_red_error_rate`、`api_red_duration_p95_ms`、`recommendation_recall_hit_rate`、`assistant_reply_latency_p95_ms` | Prometheus RED 与 recommendation attribution 指标；禁止从产品事件反推 |
| L4 基础设施 | 存储、网关、监控是否支撑 beta 验证 | `gateway_up`、`ops_portal_up`、`product_ops_up`、`redis_latency_p95_ms`、`mongo_latency_p95_ms` | 基础设施 exporter 与服务 health；产品日志链路不新增消息队列 |

### SLO 基线

- L1：user_acceptance 旅程 `首页精品 -> 圈子校园 -> 北京大学主页 -> 评论 @小趣 -> 消息承接 -> ops 可见` 完成率 beta ≥ 90%。
- L2：推荐 surface `featured / circle / campus / travel / homepage_detail / search_xiaoqu` 均必须通过 `BehaviorReporter` 上报曝光、点击与停留，由服务端归因指标计算 CTR；缺既有 behavior attribution 维度视为看板不可发布。
- L3：核心 API RED p95 < 800ms，错误率 < 1%；assistant 评论回复 p95 < 5s；recommendation recall hit rate ≥ 95%。
- L4：`gateway / product-ops / ops-portal / observability` beta health check 可用率 ≥ 99%，队列延迟 p95 < 30s。

### 信号覆盖与入口边界

- 底栏和内部导航只更新生成的 `AppPageContextStore`，页面变化产生目录登记的 `page_open/page_return`；不额外维护 route/surface 公共字段。
- Feed/Surface 的曝光、点击、停留和负反馈只经 `BehaviorReporter → /content/behaviors`，使用 `behaviors.yaml` 的既有强类型归因字段。
- like/comment/report 等专用命令由 content-service 事务 outbox 投影一次 canonical `BehaviorSignal`，App 不补发第二条。
- 实体主页、问小趣、`@小趣` 和创作绑定实体的业务标识由各自领域事件与指标承载；如需页面趋势，只关联 `pageName` 聚合，不扩张产品日志公共信封。

### App 端观测职责边界

- `AppPageContextStore + AppTelemetryRecorder` 是页面打开、路由首帧、首个可用终态和停留的唯一通道。仅
  `app_pages.yaml` 中 `collect_page_access: true` 的页面产生 `page_open/page_return`；
  `page_first_usable` 由同一 visit 的明确 content/empty/error 终态结算。页面 Widget 禁止再用
  `JourneyEventTracker` 手工发送 `enter/exit`，避免同一次访问被双计。
- `JourneyEventTracker` 只记录没有推荐反馈语义的关键产品动作，例如保存资料、发起联系、
  拉黑、扫码入口和提交结果；失败必须携带 canonical `failReasonCode`，不得把页面曝光包装成
  `product_action`。
- `ContentBehaviorTracker` 只记录会进入推荐归因/反馈回流的内容与交集行为，例如合格曝光、
  点击、停留、负反馈和交集证据行动；页面生命周期与普通设置动作不得进入该通道。
- `PageLifecycleObservability`（底层 `AnalyticsService`）只记录加载、刷新、分页、媒体和错误等
  技术状态，供页面可靠性诊断；它不能替代 `page_open/page_return`，也不能生成推荐反馈。
- 同一用户动作只能有一个业务事实生产者：like/comment/report 等事务命令由服务端 outbox
  投影 canonical `BehaviorSignal` 时，App 不再经任一 tracker 补发同义事件。

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

- A1：页面/启动/性能/异常指标与推荐业务指标分别声明真实来源，不混用日志入口。
- A3：产品日志支持页面/版本/设备/网络下钻；推荐指标支持既有 attribution 维度下钻。
- A4：Portal 通过 product-ops 查询产品日志，通过真实 Prometheus/业务投影读取推荐指标。
- A7：新增指标必须经过字典、事件目录或领域 metadata 的单轨评审。
- A8：形成可支撑 baseline 的指标词典与维度标准文档。
- A9：交集转化北极星 `intersection_conversion_rate` 可按 `intersectionDimension` / `action` 下钻；三类交集行动（follow/join_circle/add_contact）端云字段一致且可区分漏斗。
