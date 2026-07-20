# learning-event-feedback-injection 设计

## 设计动因

助手若不能从反馈中改进就只是无状态问答机。本 L2 以 append-only 事实为唯一学习输入：`AssistantInteractionEvent`（赞/踩/复制/分享/纠错/打断等）与 `AssistantScorecardFact`（run 终态自评 + 指标评分），投影出 `rm_assistant_learning_profile` 学习画像，反哺入口个性化、建议动作与回答上下文。

## 数据流

```
端侧反馈 UI ──ReportInteractionEvent──> assistant_interaction_events (Mongo, append-only)
run 终态自评 ──ReportScorecard(internal)──> scorecards (Mongo, append-only)
      └────投影────> rm_assistant_learning_profile（计数/指标聚合/最近反馈）
                        ├──> GetEntryPersonalization（欢迎语/chips 个性化）
                        ├──> GetSuggestedActions（低分指标下钻建议）
                        └──> GetLearningOpsSummary（运营只读摘要）
```

学习画像只用于推荐与运营聚合，不作为用户可见、可召回的“记忆”事实。用户显式偏好由
`AssistantPreferenceFact` 单独承载，并通过设置、遗忘、恢复及 Run 快照闭环，避免把
交互事件或评分卡摘要误当作可控记忆。

## 关键决策

- 幂等：eventId 唯一 + Redis dedup（7d）；批量上报部分成功语义（每条独立 ack）。
- 事实不可变：学习画像是投影，可随时重建；纠错不修改原事件，追加新事实。
- 注入边界：反馈只影响 prompt 上下文与个性化展示，不直接改写回答事实；`AssistantRunCompleted` 事件回流推荐引擎作质量信号。
- 隐私：事件文本字段 SENSITIVE 分类，log_policy metadata_only；画像仅 owner 与 operator scope 可读。

## 非功能

- 上报 p95 300ms；投影延迟秒级（同步 upsert）；dedup 键 TTL 与 metadata storage.yaml 声明一致。
