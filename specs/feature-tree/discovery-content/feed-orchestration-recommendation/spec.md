# L2 特性：feed-orchestration-recommendation

## 功能说明

`feed-orchestration-recommendation` 是发现内容域的推荐编排主能力，负责把内容供给、用户反馈、时间衰减与交集解释统一编排为首页 feed 体验。运行时引擎能力归属 `runtime/runtime-recommendation`；本节点只定义业务编排、端云契约、体验和验收。

核心目标：

- 内容：四类内容（article/moment/photo/video）与数据工程冷启动内容进入同一 feed 契约，禁止 UI 或 mock 复制第二套业务列表。
- 用户：曝光、点击、停留、点赞、收藏、评论、关注、不感兴趣、举报等行为经 BehaviorRepository 上报，并回流 HotPath/FeedbackRecorder。
- 时间：首屏、翻页、刷新、续接、曝光窗口、疲劳窗口与内容新鲜度按统一 cursor/session 语义解释。
- 交集：feed 卡片、交集 spotlight、对象主页和我的交集收件箱都只消费服务端 `IntersectionReason.primaryText` 与同源交集字段，禁止本地拼装第二套交集理由。

## 本轮基线范围（2026-06-16）

2026-06-24 非深排 P0 已进入实现：质量分投影消费、物化协同召回读取、旅行垂类路由、精品流式路由、候选级交集融合和 primaryText-only 解释进入主链路；长期深排平台仍不进入本轮。

### In Scope

- 四维规格：内容 × 用户 × 时间 × 交集在召回、排序、去重、反馈、评估中的落点。
- 质量分冷启动：UGC、BulkImport、数据工程 importer 同口径投影 `qualityScore/recScore/contentVertical/supplySource/semanticMentionCoverage/mediaCompleteness`，读路径只消费投影结果。
- 非深度协同召回：只读 `rm_collaborative_i2i/u2i` 物化表，`recallPath=collab_i2i/collab_u2i`，支持 `disable_collaborative_recall_sources` 回滚。
- 旅行垂类：`subCategory=travel` 归一为 `vertical=travel_photography`，召回和 fallback 都不得混入非旅行内容。
- 精品流式：`type=premium|similar|featured|immersive|精品` 归一为 `FeedSimilar + premium_stream`，使用 premium preset 和质量分/交集融合；全局 featured 精品池未写入前不启用 PremiumPoolSource。
- P0+ 观测归因闭环：feed 下发、App 行为上报、content-service raw event、learning context 和 Prometheus 分桶指标统一携带 `feedRequestId/channelId/contentVertical/supplySource/recallPath/rankingVersion/reasonVersion/intersectionSourceRef/intersectionClass`，支持按首页、旅行、精品、UGC、数据工程、召回路径和交集类别评价效果。
- 流式 feed 体验：下拉刷新 vs 续接、触底加载、没有更多、新内容提示、已读位点、空/错/降级/加载四态、推荐理由展示。
- 负反馈即时抑制：不感兴趣、减少此类、屏蔽作者进入 behavior → HotPath negative/hidden 语义，并只影响未来窗口。
- 曝光治理集成规格：served/impressed 双轨、跨页/跨会话去重、疲劳时间衰减、动态曝光预算与复活通道的业务所有权已迁出到平级 L2 `discovery-content/exposure-governance`；本节点只定义 feed 如何消费该能力边界。
- 北极星与业务 KPI：人均有效消费时长、次日留存、内容完成率、互动率、负反馈率、重复曝光率、内容覆盖率。
- SIT / GWT / contract 验收与 三层测试 证据矩阵。

### Out of Scope

- 深度排序模型平台轨（MMoE/PLE/ESMM、双塔 ANN、IPS 反事实训练）。
- 协同过滤离线物化作业与 replay 评估脚本。
- 同步 `/v1/score` 塞进 feed 读路径。
- Thompson Sampling、内容生命周期复活、Bloom/Cuckoo/Count-Min 等海量阶段曝光基础设施实现。
- UGC 媒体上传、审核准入等 Phase 1 业务实现。

## 端云边界

- `GET /v1/content/feed` 是内容 feed 读取入口；`sort=recommend`、cursor、sessionId、feedRequestId 必须保持端云一致。
- `POST /v1/content/behaviors` 是行为回流入口；新增行为字段与 action 必须 metadata-first；端侧统一上报通道、分级采样、clientEventId 幂等与 feedRequestId 归因见 L3 `feedback-ingestion-sampling`。
- 推荐排序运行时只通过 `runtime/recommendation` 引擎与 `recommendation/rec_model/policy.yaml`（或其 codegen 产物）消费策略，禁止在 UI、Repository 或 intersection 另起 ranker。
- 曝光记忆、动态曝光预算、生命周期复活、活跃度自适应和曝光健康指标的唯一业务能力归属为 `discovery-content/exposure-governance`。
- 页面、route、surface 与 operation 均来自 metadata/codegen；新增流式 feed 页面能力需同步 page-horizontal-quality 与 metadata-driven UI 清单。

## 验收标准

- A1：首屏、翻页、刷新、续接路径可执行，cursor 连续推进，用户回滚已看内容时 feed 不抖动。
- A2：同 session 跨页不重复；served/impressed 语义分离，端侧真实曝光继续作为训练与疲劳信号。
- A3：强负反馈只影响未来窗口，下一批推荐中同内容/作者/类型/标签明显下降或被过滤。
- A4：无行为新用户有非空冷启动内容，首刷可由兴趣 onboarding 或默认探索保底支撑。
- A5：交集理由只读服务端 `IntersectionReason.primaryText`；首页不显示“推荐理由”标签和旧交集图标，无 `primaryText` 不占位。
- A6：推荐 SLO/KPI 可观测：延迟、空 feed、fallback、重复曝光率、CTR、停留、完成率、负反馈率；P0+ 归因指标必须能按 `channel/vertical/supply_source/recall_path/ranking_version/reason_version/intersection_class` 分桶。
- A7：metadata/OpenAPI/codegen/Redis key/recpolicy 与端云实现一致。
- A8：三层测试 证据矩阵可形成，已存在测试登记到 `acceptance.yaml`，长期能力只登记为 planned 或 out_of_scope。

## 首页交集与多形态信息流改版（V8）

### 目标

首页从“所有频道复用同一个微博式 feed 组件”升级为“频道意图驱动的多形态信息流”：

- `关注` 保持单列关系流，强调作者、时间、正文、互动与关系信任。
- `精品` 保持侵入式消费体验，承载高完成度作品、视频和长文阅读入口。
- `推荐 / 校园 / 旅行 / 摄影` 在手机端采用双列发现流，提高浏览密度和主动选择效率。
- `科技 / 汽车` 与校园、旅行、摄影一致，手机端统一双列发现流；文章、长评、口碑等强解释内容通过详情页与对象页承接，而不是在首页单独切一套 full-span 主布局。
- `交集` 从顶部孤立横滑 rail 升级为 full-span 解释模块 + 卡片内轻量理由 + 对象/实体主页承接。

### 体验规则

- 手机 `<600px`：推荐、校园、旅行、摄影默认 2 列；关注固定 1 列；精品走侵入式。
- 平板/宽屏：按响应式列数扩展，但交集 spotlight、文章大卡、口碑/问答等模块跨全部列。
- 双列卡只展示封面、标题/短正文、作者小信息和一行交集理由；完整正文、复杂行动与解释放到详情页、对象页或 full-span 模块。
- 同一个 `PostBaseDto` / `ContentSurfaceView` / `IntersectionReason` 支持单列、双列、侵入式、对象页承接四类展示；禁止为双列新建第二套业务列表。

### 交集闭环

- Feed item 的 `intersectionReasons` 是首页交集模块和卡片内理由的唯一来源。
- 对象对直打的 `shared-tags` 继续映射为 `IntersectionReason`，由对象/实体主页 `ObjectIntersectionCard` 承接。
- 用户在交集模块点击关注、加入圈子、加联系人时，必须回流 `intersectionDimension` 和 `intersectionTagRefs`，支撑 `intersection_conversion_rate` 下钻。
- 小趣入口消费 `intersectionRefs / objectType / actionTargetId`，用于解释“为什么推荐给你”，端侧不本地拼装交集文案。

## 关注页对象列表与未读变化（V9）

### 目标

关注频道是登录态主页，不只是“关注内容 feed”。进入关注频道后，顶部先展示用户关注的人、圈子和地点/事物主页列表，类似早期 stories 的横向浏览效率，但前台不使用 stories 这个概念。

### 访问规则

- 未登录时，关注频道整体不可查看，包括顶部关注对象列表和下方关注 feed。
- 点击“关注”tab、左右滑进入关注、深链 `/following` 都必须走 `AuthGateReason.followingFeed`。
- 登录后才能加载关注对象列表和关注 feed。

### 顶部关注对象列表

- 前台模块名：`关注动态`。
- 端侧组件名：`FollowingSubjectStrip`。
- 单项模型：`FollowingSubjectItem`。
- 支持对象类型：`user`、`circle`、`homepage`。
- 展示形态：横向头像/封面列表，名称 1 行；用户用头像，圈子/地点和事物主页用封面或 fallback 图标。
- 点击对象后进入对应主页：用户主页、圈子详情、地点和事物主页。

### 上次访问后变化红点

- 小红点只表示“该对象自你上次进入后有变化”，不是消息未读。
- 云侧返回 `lastVisitedAt`、`latestChangedAt`、`unreadChangeCount`、`hasUnreadChanges`。
- 端侧看到 `hasUnreadChanges=true` 时在头像右上角显示红点。
- 用户点击对象并成功进入主页后，端侧调用 `MarkFollowingSubjectVisited`；本地可乐观隐藏红点，下一次刷新以云侧为准。

### 提示语

- 登录标题：`登录后查看关注`
- 短提示：`登录后查看你关注的人、圈子和地点动态`
- 登录页副文案：`登录后会同步你的关注列表，并提示上次访问后的新变化。`
- 空态标题：`还没有关注的人、圈子或地点`
- 空态副文案：`去推荐、校园、旅行里关注感兴趣的对象，回来这里查看它们的新动态。`

### 端云契约

- 新增 `user/following_subject` metadata，归属 user 域，聚合用户关注对象读模型。
- `ListFollowingSubjects` 返回用户、圈子、地点和事物主页三类对象。
- `MarkFollowingSubjectVisited` 写入当前 viewer 对目标对象的 `lastVisitedAt`。
- 变化水位 `latestChangedAt` 由对象域写入或投影，关注域只维护 viewer 维度访问水位。
- 如果某类对象的 follow 能力尚未完全可写，不能在 UI 本地伪造列表；必须由 seed/mock repository 与远端契约同形提供。
