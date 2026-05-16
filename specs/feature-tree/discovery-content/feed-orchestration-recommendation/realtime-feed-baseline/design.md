# realtime-feed-baseline 设计

## 设计决策

### D1：特征分四层，标签与推荐特征职责分离

数据工程标签体系（Topic/Audience/Format/Entity）是推荐特征的重要语义输入，但不把所有推荐特征并入标签体系。推荐侧通过 Feature Registry 定义四层特征：

1. **实时在线（Redis HotPath，TTL 30min）**：session_tag_weights / exposed_set / negative_set / realtime_interest
2. **近线（MongoDB rm_recommend_feature，事件驱动 upsert）**：tagAffinities / authorAffinities / engagementRate / totalLikes / totalFavorites / totalShares
3. **离线（训练侧 feature_registry，daily batch）**：engagement_rate_7d / quality_score / content_type_preference / entity_affinity / geo_preference
4. **数据工程静态语义（release import）**：post.tags[] / post.entityRefs[] / entity.tagRefs[] / tag.group / tag.dimension

### D2：多路召回按配额混排，按 surfaceId 路由

在 content-service main.go 注入多个 CandidateSource：

| 召回源 | 配额 | 策略 |
|---|---|---|
| TagRecallSource | 30% | rm_discovery_feed 按 session tag 权重召回 |
| HotRecallSource | 20% | 48h 热度排序 |
| AuthorRecallSource | 15% | 关注作者最新内容 |
| ExploreRecallSource | 10% | $sample 随机 |
| MongoCandidateSource | 15% | 综合 recScore 排序 |
| PostRepositorySource | 10% | 保底回退 |

每路 limit = request.Limit * 3，总候选量控制 200-500，PreRank 截断到 200。

### D3：CascadeScorer 分层回退

RuleScorer（增强版）为默认安全底座。通过 experiments 的 rec_model_vs_rule 分桶灰度开启 RemoteModelScorer。CascadeScorer 50ms 超时自动回退，日志记录 rec.model.cascade_fallback。

### D4：端上 sessionId/feedRequestId 统一归因

新增 feed_session_provider.dart 管理 feedSessionId（UUID，30min 无活动重建）。每次 GetFeed 生成唯一 feedRequestId。所有行为事件回带这两个 ID 用于 session 级推荐和训练样本归因。

### D5：Rerank 增强策略

- 同 top-3 标签去重：连续 3 条不得共享 top 标签
- 探索注入：每 5 条至少 1 条来自 explore_recall 路径
- 冷启动保量：新内容（< 24h）至少占结果 10%
- 现有类型多样性和作者频控保留

### D6：离线训练多目标 + 晋级门禁

SampleJoiner 多目标 label：click/dwell_s/like/favorite/share/comment/dislike。
负样本：曝光但 10s 内无正向行为。
train.py 至少 15+ 特征，time-split validation，AUC/GAUC/NDCG@20。
晋级门禁：新模型 AUC > production + 0.005 且 NDCG@20 不降。

### D7：SessionCache 主动失效

BehaviorService.ProcessBatch 成功后调用 SessionCache.Invalidate，避免 2s 旧态窗口。

## metadata 变更

### behaviors.yaml 扩展

BehaviorEventInput 新增字段：
- feedRequestId (string)
- position (int)
- recallPath (string)
- modelVersion (string)
- recScore (float64)
- surfaceId (string)
- entityRefs ([]string)

新增 action：skip / comment / follow

### service.yaml 扩展

GET /v1/content/feed 新增 query_params：sessionId / feedRequestId / surfaceId

### feature_registry.yaml 扩展

user_features：tagAffinities / authorAffinities / engagementRate / totalLikes / totalFavorites / totalShares / totalEvents
context_features：requestHour / requestDayOfWeek / surfaceId / sessionDuration

## 灰度与回滚

- Phase 3（无模型）：RuleScorer 增强全量上线
- Phase 4（有模型）：rec_model_vs_rule 实验 80% control(rule) / 20% model
- 回滚：config 中 rec_model_service.enabled: false 一键关闭，1min 内生效
- 观测：feed P95/P99、model timeout 率、CTR、负反馈率、曝光去重率
