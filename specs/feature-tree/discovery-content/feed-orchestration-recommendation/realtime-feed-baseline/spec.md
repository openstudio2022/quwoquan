# L3 场景：realtime-feed-baseline（实时推荐流商用基线）

## 功能说明

为首页精选、作品沉浸式和发现流提供 TikTok 式实时推荐体验。用户滑动后，推荐流秒级响应停留、滑走、点赞、收藏、不感兴趣和关注行为，下一屏内容即时调整。

核心链路：App 行为上报 -> Redis HotPath session 信号 -> 多路召回 -> PreRank -> RuleScorer/CascadeScorer -> Rerank -> Feed 响应。

## 约束

- `content_feed` 为第一场景，不混入圈子推荐、好友推荐、广告竞价、搜索排序。
- Feed P95 < 200ms（含模型 < 250ms），P99 < 400ms。
- Feed 空结果率 < 0.1%，同 session 跨页重复率 < 1%。
- 模型超时回退率 < 5%（CascadeScorer 50ms 超时 fallback RuleScorer）。
- 行为上报到 HotPath 生效延迟 < 100ms（BufferedHotPath 50ms flush + Redis RTT）。
- 冷启动用户（0 行为）首页非空内容 >= 20 条。
- RuleScorer 为默认安全底座，任何模型上线必须支持一键回退到规则。

## 范围

### In Scope

- 内容 Feed（首页精选 / 沉浸式作品流 / 发现流）
- 多路召回（Tag / Hot / Author / Explore / Mongo / PostRepo 保底）
- QualityPreRanker + RuleScorer + CascadeScorer(模型灰度)
- 重排（类型多样性 + 作者频控 + 同标签去重 + 探索注入 + 冷启动保量）
- 端上行为闭环（impression / click / dwell / skip / comment / follow / dislike / share）
- 统一 sessionId / feedRequestId 归因
- 数据工程 release -> 服务端 bulk import 标签/实体/内容
- Redis HotPath session 信号（tag weights / exposed / negative / realtime interest）
- 离线训练（SampleJoiner -> LightGBM -> evaluate -> ModelRegistry -> 灰度推理）
- A/B 实验（rec_scoring_weights 权重桶 + rec_model_vs_rule 模型桶）
- 观测（PipelineMetrics + 小时/天级 CTR/互动/负反馈/留存指标）

### Out of Scope

- 重型序列深度模型、多推理服务拆分
- 广告竞价、搜索排序
- 圈子内推荐、好友推荐
- App 直连推荐模型服务（始终经 content-service 代理）

## 依赖

- `feed-orchestration-recommendation` L2（Engine / HotPath / Scorer / Rerank 基础设施）
- `content-service-contract-foundation`（Post / Behavior / Reaction 契约）
- `recommendation-platform/rec-model-service`（Python 推理 API）
- `recommendation-platform/rec-model-training`（训练管线）
- `quwoquan_data`（标签 / 实体 / 内容 release）

## 验收重点

- A1：多路召回可按配额混排，无单源故障导致空结果
- A2：RuleScorer 增强后，无模型也能产出个性化 feed
- A3：端上所有行为事件带 sessionId/feedRequestId/position，闭环到 HotPath
- A4：dislike 后该内容不再出现，dwell 高的标签下次召回排前
- A5：训练管线可端到端跑通，模型晋级有 AUC/GAUC 门禁
- A6：CascadeScorer 灰度开启后 feed 质量不降（CTR 不降、负反馈不升）
- A7：数据工程 release 可导入服务端，标签/实体进入召回和特征
- A8：灰度回滚演练通过，model 回退到 rule 可在 1min 内完成
