# L3 Story：premium-stream-recommendation

## 功能说明

`premium-stream-recommendation` 负责精品/沉浸式内容流的非深排 P0 路由与解释呈现：精品流走 `FeedSimilar` 场景和 `premium_stream` surface，消费 premium 预设、质量分、交集 fact/affinity 融合与统一曝光治理。

## 范围

- `type=premium|similar|featured|immersive|精品` 归一为 `FeedType=similar`、`Surface=premium_stream`。
- 排序使用 policy.yaml `scenarioRouting.similar: premium`，强调质量、完成/停留和相关性。
- 精品详情解释标题为“与你相关的线索”，主句只读 `IntersectionReason.primaryText`；`secondaryText` 仅作为详情辅助。
- product-ops 全局精品池写入需具备 global scope、质量准入、审计、过期、回滚和下架剔除；content-service 未接入投影/召回前，不启用或宣称全站精品池召回成熟。
- P1d-2 下一轮目标：product-ops 全局精品池投影到 content-service 推荐读模型，`PremiumPoolSource` 只读该投影并以 `RecallPath=premium_pool` 进入 Engine；读路径不得同步调用 product-ops、质量模型、数据工程任务或 `/score`。
- 2026-06-25 continue-dev 开发切片已启动：新增 `rm_premium_pool` projection metadata、fail-closed 投影字段构造、product-ops `PremiumPoolEntry*` 事件发布、content-service `PremiumPoolProjector`/`PremiumPoolEventConsumer`、`PremiumPoolSource` 场景门控、content-service 接线和 `disable_premium_pool_source` 回滚开关。该切片只证明本地契约、事件投影语义与读路径边界，真实跨服务 api_integration 与 Gamma/UAT 仍未完成。

## 非目标

- 不把圈内精选误当全站精品。
- 不新增同步 scorer 调用。
- 不引入深排平台、双塔 ANN 或 IPS/Thompson 闭环。
- 不新增第二套标签、实体、解释或 App 本地精品列表。

## 验收标准

- A1：精品请求下传 `FeedType=similar` 与 `Surface=premium_stream`。
- A2：精品排序只消费 policy.yaml、qualityScore、交集候选特征和已有行为特征。
- A3：首页/精品解释都不显示“推荐理由”泛标签；无 `primaryText` 时不占位。
- A4：PremiumPoolSource 启用前必须证明 product-ops 全局 featured/质量准入、审计、过期、回滚和下架剔除，并完成 content-service 投影读取。
- A5：`premium_pool` 候选必须与其他召回源共享负反馈、下架、过期、频控、near-dup、作者屏蔽和类型屏蔽过滤；回滚开关 `disable_premium_pool_source` 生效时精品流退回 premium preset + 通用候选，不退回圈内精选。
- A6：`rm_premium_pool` 无 eligible 投影、投影过期、回滚、下架或质量准入失败时必须 fail closed，不能退回圈内 featured、普通 `Post.Featured` 或 App 本地列表。
