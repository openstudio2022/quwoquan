# design：analytics-metric-dictionary

## 设计目标

为统一事件模型提供稳定的指标层抽象，避免出现：

- 端侧事件名与运营报表名不一致；
- 推荐、Assistant、运营对同一行为给出不同分子/分母；
- 分享、实体、社交等跨域场景无法共用同一维度。

## 设计原则

1. **指标先于看板**：先定义口径，再允许 dashboard / 训练 / 实验消费。
2. **指标先于实现**：即使现阶段 `AnalyticsService` 仍为 stub，字典也先冻结为目标态真相源。
3. **公共维度共享**：`pageVisitId / surfaceId / experimentBucket / userIdHash` 为跨域下钻基础。
4. **业务维度按域扩展**：内容、社交、实体、学习等仅在公共维度之上补充，不重写公共语义。

## 指标结构

每个指标条目至少包含：

- `metricId`
- `metricName`
- `metricDomain`
- `description`
- `numerator`
- `denominator`
- `eventBindings`
- `dimensions`
- `defaultAggregation`
- `samplingPolicy`
- `trainingEligibility`
- `experimentCompatibility`
- `retentionClass`

## 关键映射

- `page_open_rate / page_return_duration_ms` 绑定 page access 事件；
- `content_ctr / content_dwell_seconds / completion_rate` 绑定 behavior 与播放器事件；
- `message_delivery_rate / first_reply_latency_ms` 绑定 social 事件；
- `share_open_back_rate / entity_click_rate` 绑定 share/entity 事件；
- `assistant_scorecard_completeness / feedback_injection_hit_rate` 绑定 learning 事件。

## 与实现的衔接

- `page_access_log_util.dart` 现有 `open/return` 事件可直接映射体验域指标；
- `content_behavior_tracker.dart` 现有 `impression/click/dwell/dislike/share` 是行为域最先落地的事件绑定；
- `assistant_learning_service.dart` 现有 scorecard 维度可直接映射 learning 域指标；
- chat/rtc/share/entity 相关指标允许先冻结字典，再在 `/dev` 阶段补事件接入。

## 演进规则

- 新增指标先补字典，再补 schema，再进入 dashboard/模型/实验；
- 删除指标必须先标废弃版本与兼容期；
- 指标口径变化必须记录到 CR，并回填 acceptance/evidence。

## 未来演进

- 后续可将指标字典 metadata 化，生成 dashboard 配置、训练特征映射与事件校验代码；
- 在本 baseline 阶段先以文档形式冻结，不阻塞现有 serving 路径。
