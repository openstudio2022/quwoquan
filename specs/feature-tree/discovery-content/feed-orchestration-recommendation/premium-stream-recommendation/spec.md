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
- premium preset、质量分和交集融合排序。
- 精品解释标题与 primaryText-only 呈现。
- product-ops 全局精品池写入前置：global scope、质量准入、审计、过期、回滚和下架剔除。
- P1d-2 content-service 精品池投影读取、PremiumPoolSource 场景门控、premium_pool recall path 和统一过滤。

### Out of Scope

- 未经 content-service 投影读取验收的 PremiumPoolSource 上线启用。
- 同步 scorer 调用。
- 深排平台、双塔 ANN、IPS/Thompson。
- 第二套标签、实体、解释或 App 本地精品列表。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 精品流式体验路由与解释契约

- 精品流必须统一路由、排序与解释；全局精品必须先经 product-ops 写入，未启用 PremiumPoolSource 时不得返回伪精品结果。

<a id="req-002"></a>
### REQ-002 精品池全局召回读路径闭环

- product-ops 写入、回滚、过期、下架状态可投影到 content-service 推荐读模型。
- PremiumPoolSource 不同步调用 product-ops、质量模型、数据工程任务或 /score。
- premium_pool 候选与其他召回源共享负反馈、下架、过期、频控、near-dup、作者屏蔽和类型屏蔽过滤。
- disable_premium_pool_source 回滚开关生效时，精品流退回 premium preset + 通用候选，不退回圈内精选。
- premium_pool 分桶进入 replay、AB、看板和告警归因。

<a id="req-003"></a>
### REQ-003 product-ops 全局精品池必须投影到 content-service 推荐读模型；PremiumPoolSource 只读该投影并以 RecallPath=premium_pool 进入 Engine，读路径不得同步调用 product-ops、质量模型、数据工程任务或 /score

- product-ops 全局精品池必须投影到 content-service 推荐读模型；`PremiumPoolSource` 只读该投影并以 `RecallPath=premium_pool` 进入 Engine，读路径不得同步调用 product-ops、质量模型、数据工程任务或 `/score`。
- PremiumPoolSource 启用前必须证明 product-ops 全局 featured/质量准入、审计、过期、回滚和下架剔除，并完成 content-service 投影读取。
- `premium_pool` 候选必须与其他召回源共享负反馈、下架、过期、频控、near-dup、作者屏蔽和类型屏蔽过滤；回滚开关 `disable_premium_pool_source` 生效时精品流退回 premium preset + 通用候选，不退回圈内精选。
- `rm_premium_pool` 无 eligible 投影、投影过期、回滚、下架或质量准入失败时必须 fail closed，不能退回圈内 featured、普通 `Post.Featured` 或 App 本地列表。

## 4. 契约引用

- canonical：`specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/projections/premium_pool_projection.yaml`
- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 精品流式体验路由与解释契约

- GIVEN 用户进入精品/沉浸式内容流，内容具备质量分和交集理由。
- WHEN content-service 请求推荐引擎，App 展示精品详情解释。
- THEN 推荐场景为 similar/premium_stream，App 标题展示“与你相关的线索”，主句只显示 primaryText。

<a id="gwt-002"></a>
### GWT-002 精品池全局召回读路径闭环

- GIVEN product-ops 已写入 global scope、qualityAdmission=approved、未过期且未下架的精品条目。
- GIVEN content-service 拥有内容 published/approved/visible 与推荐质量分投影。
- WHEN 用户进入 premium_stream/similar 精品流。
- THEN content-service 只读本地精品池推荐投影，装配 RecallPath=premium_pool 候选并交给 Engine 统一过滤、排序和曝光治理。

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
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：路由、排序、解释、product-ops 全局精品写入前置和未启用 PremiumPoolSource 的边界均可测试。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 精品池全局召回读路径闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：product-ops 写入、回滚、过期、下架状态可投影到 content-service 推荐读模型。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
