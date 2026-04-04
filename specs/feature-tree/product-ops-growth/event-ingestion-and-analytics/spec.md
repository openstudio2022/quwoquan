# L2 特性：event-ingestion-and-analytics

## 背景与动机

当前仓库已形成 4 条并行但未完全打通的事件链路：

1. 页级访问与性能日志：`quwoquan_app/lib/app/navigation/page_access_log_util.dart` 与 `quwoquan_app/lib/assistant/observability/logging/app_log_service.dart` 已提供 `open / return / perf` 与 `sessionId / journeyId / pageVisitId` 等上下文，但主要写入本地 JSONL。
2. 内容行为与推荐热链路：`quwoquan_app/lib/core/trackers/content_behavior_tracker.dart` → `quwoquan_service/services/content-service/internal/application/behavior_service.go` → `quwoquan_service/runtime/recommendation/hotpath.go`，已能把 `impression / click / dwell / dislike / share` 等信号写入 Redis 热状态。
3. Assistant 学习链路：端侧 `assistant_learning_service.dart` 已有 InteractionEvent / Scorecard 模型，云侧 `assistant_run/service.yaml` 也已定义 `POST /v1/assistant/learning/events` 与 `POST /v1/assistant/learning/scorecards`，但端侧同步仍停留在 `localMock / cloudStub`。
4. 访问记录与体验标签：本地 visit recorder 与 page context 已可形成 returning/frequent 等语义，但未形成统一上云与分析闭环。

这导致产品体验评估、用户行为分析、持续运营、实验评估、在线学习与策略注入分散在多条口径中，缺少统一事件字典、统一反馈应用入口与云侧冷热分层存储。

本 L2 baseline 的目标，是冻结一套能覆盖全 App 域的统一事件与反馈基础设施规格，为后续 `/dev` 的 metadata/codegen/实现提供单一真相源。

## 目标用户与消费者

### 目标用户

- App 最终用户：获得更稳定、更相关、更低摩擦的产品体验。
- 运营与产品分析团队：获得可持续、可复盘的体验与行为指标体系。
- 推荐与分发团队：获得可用于在线重排与离线调优的行为/负反馈/实体点击信号。
- Assistant 团队：获得可进入评分卡、反馈注入、策略灰度与回滚的学习事件。

### 直接消费者

- `app`
- `platform-ops`
- `recommendation-engine`
- `assistant-service`

## In Scope

1. 冻结全 App 域统一事件模型：`experience`、`behavior`、`qoe`、`social`、`share`、`entity`、`learning`、`experiment`、`ops`。
2. 冻结统一维度模型：`sessionId`、`journeyId`、`pageVisitId`、`surfaceId`、`routeId`、`operationId`、`requestId`、`userIdHash`、`contentId`、`entityType/entityId`、`conversationId`、`messageId`、`experimentBucket`、`appVersion`、`platform`、`networkClass`。
3. 冻结竞品对标吸收口径：微信即时消息、字节短视频播放、今日头条内容推荐、小红书分享与实体点击。
4. 冻结三条反馈应用链路：
   - 推荐热路径与在线重排；
   - Assistant 学习、评分卡与反馈注入；
   - 运营看板、实验分析、类目/实体/创作者分析。
5. 冻结云侧冷热分层：Redis 热状态、事件总线、OLAP 明细分析、对象存储冷归档、Mongo/关系维表 serving。
6. 冻结治理策略：幂等/去重、采样、背压、优先级、生命周期、脱敏、灰度、回滚、T1~T4 证据矩阵。

## Out of Scope

- 一次性把所有页内细粒度控件点击全部落地；baseline 仅冻结 schema、优先级与入口。
- 一次性实现完整模型训练平台、特征平台或统一 BI 系统；baseline 仅冻结职责边界与目标态。
- 直接替换现有 Mongo read model 或 Redis serving 路径；允许并行演进。
- 在本 L2 内直接承诺全部业务域的最终 dashboard 版式；仅冻结指标字典与下钻维度。

## 对标输入与吸收结论

### 微信（即时消息 / 实时沟通）

吸收：
- 送达、已读、首回复时延、会话深度、弱网重试、通话接通率与稳定性，必须成为 `social` / `qoe` 域标准指标。
- 聊天与 RTC 事件必须支持 `conversationId / messageId / rtcSessionId` 维度下钻。

不借鉴：
- 以超级应用为前提的大而全埋点扩展面，不作为本阶段范围。

### 字节跳动（短视频播放 / 实时推荐）

吸收：
- `firstFrame`、`25/50/75/100%` 进度、完播率、复播率、负反馈、滑走位置、实时兴趣更新，必须进入 `behavior/qoe/learning`。
- 曝光与完播不能仅依赖页级停留，必须保留内容级播放器信号。

不借鉴：
- 过于细粒度到帧级的全量埋点；基线只冻结采样与优先级规则。

### 今日头条（推荐流 / 内容消费）

吸收：
- feed impression、CTR、阅读深度、刷新质量、负反馈、多样性、重复曝光率、freshness 必须成为推荐与运营的共同指标。
- 曝光必须区分“渲染曝光”和“有效曝光”，并定义统一口径。

不借鉴：
- 只围绕信息流的单域指标模型；本项目需覆盖聊天、Assistant、设置与实体分享等跨域表面。

### 小红书（内容分享 / 实体点击）

吸收：
- 分享发起、渠道、回流打开、内容中的实体曝光、实体点击、导购/转化链路（如适用）必须进入 `share/entity`。
- 事件必须具备 `entityType / entityId / bindPosition` 维度，支持商品、作者、圈子、主页、POI 等实体。

不借鉴：
- 直接以商业化成交作为所有实体事件的唯一目标；本阶段同时支持兴趣实体与非商业实体。

## 功能说明

### 1. 统一事件模型

所有可进入持续运营、在线学习、实验评估与统计分析的事件，必须收敛到统一 EventEnvelope：

- `eventId`：全局唯一幂等键。
- `eventType`：事件域，如 `experience` / `behavior` / `learning`。
- `eventName`：稳定语义名，如 `page_open`、`content_impression`、`assistant_scorecard_reported`。
- `eventVersion`：事件版本。
- `occurredAt`：事件发生时间。
- `producer`：端侧/服务侧来源。
- `priority`：`P0 / P1 / P2`，决定采样、背压与保留策略。
- `sampleRate`：采样率。
- `context`：会话、路由、surface、request、实验等上下文。
- `business`：内容、实体、会话、消息、操作对象等业务维度。
- `feedback`：反馈强度、正负向、训练资格、标签来源、学习目标。
- `payload`：领域特有字段。

### 2. 指标域与标准口径

#### 2.1 体验与 QoE
- 冷启动时长、首帧时间、页面 `open/return`、崩溃/错误率、卡顿/Jank、媒体解码失败率、降级触发率。

#### 2.2 用户行为
- feed impression、有效曝光、点击、停留、滚动深度、视频进度、完播、复播、点赞、评论、收藏、分享、举报、不感兴趣。

#### 2.3 社交与实时沟通
- 发送成功率、送达率、已读率、首回复时延、会话深度、通话接通率、时长、弱网重试与掉线率。

#### 2.4 分享与实体
- 分享发起、渠道、回流打开、分享转化；实体曝光、实体点击、绑定位置、导购或非导购结果。

#### 2.5 学习与反馈
- InteractionEvent、Scorecard、显式反馈、隐式反馈、策略命中率、反馈注入命中率、在线学习生效时延。

#### 2.6 运营与实验
- 漏斗、留存、回流、实验 uplift、召回/排序收益、多样性、freshness、内容与实体质量。

### 3. 反馈应用能力

#### 3.1 推荐与分发在线学习
- `impression / click / dwell / dislike / share / entity_click / completion` 等信号进入 Redis 热状态。
- 热路径支持实时兴趣更新、去重曝光、负反馈过滤、实体偏好与在线重排。
- 冷路径支持离线聚合与模型/规则调优。

#### 3.2 Assistant 学习
- `InteractionEvent` 与 `Scorecard` 必须进入统一 envelope，并映射到学习标签与策略注入输入。
- 学习事件必须区分显式/隐式反馈、可训练/不可训练、PII/SENSITIVE 字段等级。

#### 3.3 运营系统
- 统一指标字典必须支撑领域 -> 页面 -> 内容/实体 -> 事件 -> 实验桶的多层下钻。
- 运营系统必须能同时查询体验、行为、学习与实验四类结果，而不维护第二套事件语义表。

## 云侧分层存储与数据库职责

### 热路径
- **Redis**：会话级实时信号、曝光去重、负反馈集合、实时兴趣特征、短 TTL 上下文。
- 适用：在线推荐、即时策略命中、会话级实时反馈。

### 接入与回放
- **Kafka 兼容总线**：事件削峰、重放、多消费者订阅、准实时聚合。
- 适用：准实时分析、特征生成、策略回放、补数。

### 明细分析
- **ClickHouse 类 OLAP**：事件明细、漏斗、留存、实验对比、内容/实体/页面分析。
- 适用：按天/小时分区的高吞吐写入与低成本聚合扫描。

### 冷归档
- **对象存储 + Parquet**：长期低成本留存、重算、法务保留与归档。

### Serving / Projection
- **Mongo**：保留现有 read model / projection，如 discovery feed 与 recommend feature，不作为统一分析主库。
- **关系型数据库/维表**：实验配置、指标字典、实体目录、告警阈值与运营策略配置。

## 容量、性能与成本假设

### 规划假设
- P0/P1 事件峰值写入：`10k events/s` 以内。
- 推荐热路径有效信号峰值：`2k signals/s` 以内。
- OLAP 明细日新增：压缩前不超过 `500 GB/day`，通过采样、列式压缩与冷热分层控制到可接受成本。
- 冷数据归档保留：明细 `90d` 内可交互查询，`90d+` 进入对象存储；聚合指标保留 `1~3 年`。

### 成本控制原则
- `P0` 关键事件全量；`P1` 准实时事件按域可配置采样；`P2` 探索性事件优先采样与限流。
- 页级与行为事件优先批量发送；客户端队列满时先丢弃 `P2`。
- OLAP 查询默认走预聚合与物化视图，禁止宽表无界扫描成为常态。

## 生命周期、权限与隐私

- 用户标识默认使用 `userIdHash` 或等价脱敏值进入统一分析层；PII 与 SENSITIVE 字段不得直接进入公开分析宽表。
- 事件必须携带字段等级与保留策略，遵守 metadata 字段策略与 `AppLogRedactor` 同类脱敏约束。
- 分享、消息、Assistant 学习事件必须显式定义哪些字段可训练、哪些仅用于统计、哪些仅用于审计。
- 正式发布态默认启用 remote 数据面，不暴露测试入口或 mock 分析通道。

## 迁移、灰度与回滚

- 端侧现有 `page_access`、`behavior`、`analytics stub`、`assistant learning` 四条链路允许在 baseline 后并行迁移，但不得长期维持第二套事件字典。
- 灰度阶段允许：
  - page access 先双写本地日志与统一 gateway；
  - behavior 先补充 `eventId / experimentBucket / entity` 字段再切全量；
  - assistant learning 先接真实云同步，再打开反馈注入。
- 回滚原则：
  - 关闭事件总线消费者或统一 reporter，不影响现有 Redis 热路径与 Mongo serving；
  - 事件 schema 升级必须具备版本兼容或降级处理。

## 非功能目标（SLO/KPI）

- `P0` 事件接入成功率 `>= 99.9%`；`P1` 事件接入成功率 `>= 99.0%`。
- Redis 热路径写入 `P95 < 50ms`。
- page/behavior 事件端到云可见延迟 `P95 < 5min`。
- 推荐在线反馈应用延迟 `P95 < 60s`。
- Assistant 学习事件上报成功率 `>= 99.5%`。
- 关键域页面埋点覆盖率 `100%`；全 App 页面覆盖率 `>= 95%`。

## 与现有规格/代码的关系

- 复用 `runtime/runtime-client-foundation/unified-app-page-access` 作为页级访问与 pageVisit 语义基线。
- 复用 `assistant-run-learning/learning-event-feedback-injection` 作为学习事件与反馈注入能力基线。
- `quwoquan_app/lib/analytics/analytics.dart` 当前为 stub，本 L2 要求其后续要么并入统一 reporter，要么保留 façade 但不得继续独立演进事件字典。
- `quwoquan_service/runtime/recommendation/hotpath.go` 继续作为实时反馈热状态基座；其 TTL、去重、集合与兴趣权重语义进入设计真相源。

## 验收重点

- A1：统一事件模型、指标域与反馈链路覆盖全 App 域。
- A2：对标吸收、SLO/KPI、容量/成本、生命周期、灰度/回滚在 spec 中冻结。
- A4：推荐、Assistant、运营三条反馈应用闭环可复盘。
- A7：metadata/字段分级/事件版本/幂等与去重规则形成统一真相源。
- A8：具备进入 `/baseline` 所需的 `spec.md / design.md / acceptance.yaml / plan.yaml / CR`。
