# L3 Story：premium-stream-recommendation

## 功能说明

`premium-stream-recommendation` 负责精品/沉浸式内容流的非深排 P0 路由与解释呈现：精品流走 `FeedSimilar` 场景和 `premium_stream` surface，消费 premium 预设、质量分、交集 fact/affinity 融合与统一曝光治理。

## 范围

- `type=premium|similar|featured|immersive|精品` 归一为 `FeedType=similar`、`Surface=premium_stream`。
- 排序使用 policy.yaml `scenarioRouting.similar: premium`，强调质量、完成/停留和相关性。
- 精品详情解释标题为“与你相关的线索”，主句只读 `IntersectionReason.primaryText`；`secondaryText` 仅作为详情辅助。
- 未完成 product-ops 全局 featured/质量准入写入前，不启用或宣称全站精品池召回成熟。

## 非目标

- 不把圈内精选误当全站精品。
- 不新增同步 scorer 调用。
- 不引入深排平台、双塔 ANN 或 IPS/Thompson 闭环。

## 验收标准

- A1：精品请求下传 `FeedType=similar` 与 `Surface=premium_stream`。
- A2：精品排序只消费 policy.yaml、qualityScore、交集候选特征和已有行为特征。
- A3：首页/精品解释都不显示“推荐理由”泛标签；无 `primaryText` 时不占位。
- A4：PremiumPoolSource 启用前必须证明 product-ops 全局 featured/质量准入、审计、过期和回滚。
