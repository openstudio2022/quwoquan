# L3 特性：feedback-collection-unification（反馈采集与统一）

## 功能说明

把端侧行为反馈统一归一为大循环可消费的画像与人群信号：

- 行为信号经 `content-service` HotPath 归一，投影到 `rm_recommend_feature.userFeatures`
  （tag/author/四维 affinities、ENER、深度分布等），`InterestDecayJob` 按半衰期衰减
  四维 affinities，解原始 `$inc` 单调增长。
- `InterestProfileAggregator.Recompute` 基于四维 affinities 派生 `interestProfile`
  （topN 兴趣 + 生命周期分层 + 新鲜度衰减），并用 `MatchSegments` 按 `segments.yaml`
  结构化 predicate（AND 语义）匹配人群 `segments`（单一计算源）。
- 派生结果以两路 CQRS 投影分发：
  1. `UserInterestRecomputed` 事件（`repository.DomainEvent` + Redis Pub/Sub）→ user 域
     `rm_user_profile_view.interestProfile/segments`（对外画像单一真相源，供小艺主动）。
  2. `segments` 同步 `$set` 回 `rm_recommend_feature` 顶层 → 供推荐引擎 `FeatureStore`
     直接加载做 policy segment 定向（免重算）。

## 约束

- 人群规则唯一真相源 `segments.yaml`；判定只走 `MatchSegments`，禁止散落 if-else 第二套人群逻辑。
- 对外兴趣画像落 user 域，`rm_recommend_feature.segments` 是同一计算的引擎侧投影，非第二真相源。
- 跨服务事件 payload 字段以 `events.yaml`（`UserInterestRecomputed`）为准；content 生产、user 消费。
- segments 回写为 best-effort：失败只降级本次定向，不阻断事件投影。

## 验收标准

- A1：行为反馈→派生 interestProfile/segments→事件投影 user 域→segments 回写宽表 全链路可验证。
- A4：命中 segment 的画像可被推荐引擎与小艺消费（人群可定向）。
- A7：`recommend_feature.yaml` / `user_profile_view.yaml` / `events.yaml` / `segments.yaml`
  通过 `make verify-metadata`。
- A8：对应自动化测试映射完整（见 acceptance.tests.recorded）。
