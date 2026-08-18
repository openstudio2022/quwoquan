# L3 Story：精品流式推荐 (`premium-stream-recommendation`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望精品/沉浸式内容流的非深排 P0 路由、质量准入边界与 primaryText 解释契约，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- premium/similar/featured/immersive/精品 路由到 FeedSimilar + premium_stream。
- 视频书是首页顶部文本分类 Tab，固定紧跟“推荐”；移动与 Web 搜索/主工具栏不保留视频书 action、独立壳目的地或专用入口图标。
- 视频书是首页顶部文本分类 Tab，固定紧跟“推荐”；移动与 Web 搜索/主工具栏不保留视频书 action、独立壳目的地或专用入口图标。
- premium preset、质量分和交集融合排序。
- 精品解释标题与 primaryText-only 呈现。
- product-ops 全局精品池写入前置：global scope、质量准入、审计、过期、回滚和下架剔除。
- `RecommendationCandidateIndexView` 消费精品池事件、`RankedRecommendationWindow` 以 `premium_pool` recall path 统一过滤和排序，Content 只对返回的 Post ID 做当前权限 hydration 与交付。

### Out of Scope

- 未经 recommendation-service 候选投影重建、排序窗口和 Content 当前权限 hydration 验收的精品召回上线启用。
- 同步 scorer 调用。
- 深排平台、双塔 ANN、IPS/Thompson。
- 第二套标签、实体、解释或 App 本地精品列表。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 精品流式体验路由与解释契约

- 精品流必须统一路由、排序与解释；全局精品必须先经 product-ops 写入并由 Recommendation 消费 typed event，候选投影或排序窗口未闭合时不得返回伪精品结果。
- 首页频道 metadata 必须包含 `recommend → featured` 邻接不变量；远程覆盖缺失、重复或重排任一项时整份覆盖 fail-closed 到发布默认，不由 UI 本地补插第二份 Tab。
- `featured` Tab 复用现有沉浸 viewer 和 `premium_stream` 数据语义，不走普通首页 feed、不新建独立业务列表。compact/regular/expanded 仅允许视觉布局差异，供给、route、错误和归因保持同源。
- 首页频道 metadata 必须包含 `recommend → featured` 邻接不变量；远程覆盖缺失、重复或重排任一项时整份覆盖 fail-closed 到发布默认，不由 UI 本地补插第二份 Tab。
- `featured` Tab 复用现有沉浸 viewer 和 `premium_stream` 数据语义，不走普通首页 feed、不新建独立业务列表。compact/regular/expanded 仅允许视觉布局差异，供给、route、错误和归因保持同源。
- premium_stream/similar 首刷必须读取当前环境 canonical active release snapshot；健康零 active release 或同 release eligible playable-video 计数为零时返回 canonical 成功空结果，依赖读取/绑定/硬过滤/召回/scorer/hydration 故障返回 `CONTENT.SYSTEM.required_dependency_unavailable`。任何成功空态都不能替代发布门要求的当前 release 非空可播放视频精品。

<a id="req-002"></a>
### REQ-002 精品池全局召回读路径闭环

- product-ops 写入、回滚、过期、下架状态经 typed event 投影到 recommendation-service 拥有的 `RecommendationCandidateIndexView`。
- Recommendation 的精品候选读路径不同步调用 product-ops、质量模型、数据工程任务或 `/score`。
- premium_pool 候选与其他召回源共享负反馈、下架、过期、频控、near-dup、作者屏蔽和类型屏蔽过滤。
- 精品候选策略回滚时，精品流只能使用当前 canonical policy 允许的通用候选，不得切换到圈内精选或 Content 本地排序副轨。
- premium_pool 分桶进入 replay、AB、看板和告警归因。

<a id="req-003"></a>
### REQ-003 product-ops 全局精品池必须投影到 RecommendationCandidateIndexView，并由 RankedRecommendationWindow 以 RecallPath=premium_pool 统一排序

- product-ops 全局精品池必须经 `PremiumPoolEntry` typed event 投影到 recommendation-service 拥有的 `RecommendationCandidateIndexView`；`RankedRecommendationWindow` 只读本服务候选投影并以 `RecallPath=premium_pool` 进入统一过滤与排序，不得同步调用 product-ops、质量模型、数据工程任务或 `/score`。
- 精品召回启用前必须证明 product-ops 全局质量准入、审计、过期、回滚和下架剔除，并完成 Recommendation 候选投影重建、排序窗口与 Content hydration 验收。
- `premium_pool` 候选必须与其他召回源共享负反馈、下架、过期、频控、near-dup、作者屏蔽和类型屏蔽过滤；回滚后只能使用当前 canonical policy 允许的通用候选，不退回圈内精选或 Content 本地排序。
- `rm_premium_pool` 无 eligible 投影、投影过期、回滚、下架或质量准入失败时必须 fail closed，不能退回圈内 featured、普通 `Post.Featured` 或 App 本地列表。
- `rm_premium_pool` 读取链健康且首刷确实无 eligible 候选时返回 canonical 成功空结果；投影读取、资格判定或同 release hydration 链异常仍 fail closed。
- active supply 的 premium playable-video 计数必须复用 Recommendation 候选投影的 global/active/eligible/approved/quality/expiry/takedown 资格谓词，并进一步证明同一内容 ID 在 Recommendation 候选索引与 Content 权威 Post 中均属于当前 `qwq_data` release 与 active lifecycle；Post 必须是 published/public/approved 的 `work + video` 且具有非空 video URL 与正时长。

## 4. 契约引用

- canonical：`specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_candidate_index_view/projections/premium_candidate_projection.yaml`
- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 精品流式体验路由与解释契约

- GIVEN 用户进入精品/沉浸式内容流，内容具备质量分和交集理由。
- WHEN content-service 请求推荐引擎，App 展示精品详情解释。
- THEN 推荐场景为 similar/premium_stream，App 标题展示“与你相关的线索”，主句只显示 primaryText。
- AND 首页顶部“视频书”文本 Tab 紧跟“推荐”，选择后挂载同源沉浸 viewer；移动/Web 工具栏、独立 shell destination 与专用视频书入口图标均不存在。
- AND 首页顶部“视频书”文本 Tab 紧跟“推荐”，选择后挂载同源沉浸 viewer；移动/Web 工具栏、独立 shell destination 与专用视频书入口图标均不存在。

<a id="gwt-002"></a>
### GWT-002 精品池全局召回读路径闭环

- GIVEN product-ops 已写入 global scope、qualityAdmission=approved、未过期且未下架的精品条目。
- GIVEN recommendation-service 已消费精品池事件并重建候选投影，Content 拥有 Post 当前 published/approved/visible 事实。
- WHEN 用户进入 premium_stream/similar 精品流。
- THEN recommendation-service 从本地 `RecommendationCandidateIndexView` 装配 `RecallPath=premium_pool` 候选并交给 `RankedRecommendationWindow` 统一过滤和排序。
- THEN Content 只对返回 Post ID 做当前权限 hydration、页面交付和交付曝光事实回传。
- AND 健康零 eligible 视频返回 canonical 成功空结果；依赖异常返回 canonical failure 及闭集 `failureStage`。商业准出另行强制至少一条通过 release-bound supply、负反馈/隐藏/拉黑、published/safety、playable-video 与 same-release hydration 检查的当前 canonical release 视频。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 精品流式体验路由与解释契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺同一真实候选下路由、排序、解释、product-ops 准入和失效恢复的组合 `api_integration / user_acceptance` 证据；已有直接 `spec_ref` 锁定发布模式下非空精品供给与空结果信封。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 精品池全局召回读路径闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺真实 event stream 上的写入、回滚、过期、下架重建对账，以及 `RankedRecommendationWindow` 到 Content hydration/交付的组合 `api_integration / user_acceptance` 证据；Recommendation 已有 `PremiumPoolEntry` durable consumer 与候选投影的本地合同证据。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
