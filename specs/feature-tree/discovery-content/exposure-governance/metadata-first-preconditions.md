# Metadata-First Preconditions: exposure-governance

本文件冻结曝光治理与商用成熟度相关实现的 metadata-first 前置清单。本轮只声明，不改 codegen，不实现业务逻辑。

## Redis Keyspace

后续实现前必须先登记到 `quwoquan_service/contracts/metadata/_shared/redis_keyspace.yaml`：

| Key pattern | Type | TTL | 语义 |
| --- | --- | --- | --- |
| `rec:served:{<userId>}:{<yyyyMMdd>}` | set / bloom | 1-3 天 | 服务端下发记忆，短窗口翻页去重；不等同真实曝光 |
| `rec:impressed:{<userId>}:{<yyyyMMdd>}` | set / zset / bloom | 7-30 天 | 端侧真实曝光，疲劳、训练和曝光健康使用 |
| `rec:negative:{<userId>}` | set / bloom | 7-30 天 | 用户级强负反馈过滤（修复当前绑 sessionId 的跨会话失效），与 hidden_authors/types 同级 |
| `rec:freq:{<userId>}:{dimension}:{<yyyyMMdd>}` | hash / cms | 1-7 天 | 作者、标签、话题、内容类型频控 |
| `rec:near_dup:{<userId>}:{<yyyyMMdd>}` | set / bloom | 1-7 天 | near-dup 签名窗口 |
| `rec:exposure_budget:{contentId}` | hash | 7-30 天 | 动态曝光预算、bandit alpha/beta、流量池状态 |
| `rec:resurface_triggers:{contentId}` | hash | 7-90 天 | 生命周期复活触发器和最近触发时间 |

### 容量与去全量化约束

- `served` / `impressed` / `freq` / `near_dup` 一律 `user+day` 分桶，避免单 key 无限增长。
- 过滤路径只允许对召回候选做 `SISMEMBER` 批量点查或短 Bloom，禁止长窗口全量 `SMembers` 回读后转 map。
- 每个 key 必须声明 cardinality budget（成员上限）与近似结构（Bloom/Cuckoo/CMS）的误报率预算；超预算切 rolling 结构或分桶 ZSET。
- `rec:negative` 用户级、跨会话保持，与 `rec:hidden_authors` / `rec:hidden_types` 对齐，不再绑 sessionId。

## Recpolicy Factors

后续实现前必须进入 `quwoquan_service/contracts/metadata/recommendation/rec_model/policy.yaml` 或其 codegen 产物：

- `servedWindowTtlSeconds`
- `impressedWindowTtlSeconds`
- `fatigueHalfLifeHours`
- `authorFrequencyCap`
- `tagFrequencyCap`
- `topicFrequencyCap`
- `nearDupThreshold`
- `dynamicExposurePriorAlpha`
- `dynamicExposurePriorBeta`
- `dynamicExposurePromotionThreshold`
- `dynamicExposureRetireThreshold`
- `resurfaceQuotaRatio`
- `resurfaceSeasonalBoost`
- `activitySegmentExploreRatio`
- `activitySegmentResurfaceRatio`
- `rankingCalibrationVersion`
- `timeDecayStatsHalfLifeHours`

端云抗冲击与采样（feedback-ingestion-sampling / FeedbackIngestor 实现前置）：

- `visibleSampleRate`：visible 弱信号采样率（或仅本地）。
- `impressionAreaThreshold`：判定 impressed 的最小可见面积比例。
- `impressionDwellThresholdMs`：判定 impressed 的最小停留时间。
- `dwellMinReportMs`：dwell 上报下限，低于则丢弃。
- `behaviorBatchMaxSize` / `behaviorBatchWindowMs`：弱信号批量上限与窗口。
- `ingestRateLimitPerUserPerSecond` / `ingestRateLimitPerIpPerSecond`：行为入口分级限流（替换全局 1000/s）。
- `ingestInflightLimit`：行为入口在途上限（InflightLimiter）。
- `clientEventIdWindowMs`：clientEventId 幂等窗口。
- `bloomCardinalityBudget` / `bloomFalsePositiveRate`：曝光记忆 Bloom 容量与误报预算。

## Read Models

后续实现前必须先在 metadata/projection 中声明：

### `rm_exposure_state`

建议字段：

- `contentId`
- `lifecycleState`
- `exposurePool`
- `budgetAlpha`
- `budgetBeta`
- `servedCountWindow`
- `impressedCountWindow`
- `positiveRewardWindow`
- `negativeRewardWindow`
- `resurfaceTriggers`
- `lastResurfacedAt`
- `updatedAt`

## Behavior / Training Semantics

七态闭集（详见 design.md）：`served` / `visible` / `impressed` / `dwell` / `interaction` / `negative` / `training_sample`。

- `served` 只能作为下发去重和曝光健康输入，不作为训练正样本。
- `visible` 端侧弱信号，仅本地或低采样，不作训练样本。
- `impressed` 是端侧真实曝光（达可见面积 + 停留阈值），可进入疲劳、训练和曝光健康。
- `dwell` 离开 / 切走 / 翻页聚合一次，<1s 丢弃，不按 tick 上报。
- `interaction` / `negative` 强信号低延迟上报，`negative` 优先级最高。
- `training_sample` 仅云侧由以上派生，端侧禁止直接声明正负样本。
- 行为 wire schema 必须先 metadata-first 声明：`clientEventId`（幂等去重）、`feedRequestId`（曝光必带且点击复用同一 id）、`impressed` 可见性阈值字段、状态枚举（served/visible/impressed/dwell/interaction/negative）。
- 显式标签反馈需先决定归属：并入 `POST /content/behaviors`，或正式废弃旧 `POST /tag/feedback` 契约。
- `hide_author` / `hide_content_type` 已完成 H2；后续必须保持强负反馈优先级高于疲劳与动态预算。

## AB Segmentation

`recommendation_slo.yaml#ab.segmentation_labels` 已冻结以下切分：

- `channel`
- `user_segment`
- `recall_path`
- `scorer_variant`
- `exposure_pool`
- `lifecycle_state`
- `activity_segment`
- `experiment_bucket`

后续实现不得在业务代码中自造分桶标签。
