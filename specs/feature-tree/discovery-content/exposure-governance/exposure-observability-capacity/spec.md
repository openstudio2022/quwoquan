# L3 Story：exposure-observability-capacity

## 功能说明

曝光治理必须可观测、可容量估算、可告警和可回滚。该 Story 冻结重复曝光率、覆盖率、曝光基尼、复活率、各池 CTR、写放大和容量策略。

## 范围

- 曝光健康 SLI：repeat exposure、coverage、gini、resurfaced exposure、dynamic budget share、frequency cap、near-dup。
- 状态写入量 SLI：served/visible/impressed/dwell/interaction/negative 各自写入量与过滤命中率。
- 容量与抗冲击 SLI：Redis 单请求 payload bytes、SMembers fallback 使用率、HotPath buffer drop（`rec_hotpath_dropped_total`）、行为入口 ingest QPS 与 `ingest_dropped_total`。
- 容量策略：中小规模使用 day bucket；海量阶段可切 Rolling Bloom/Cuckoo、Count-Min Sketch 或精确 Sorted Set；过滤路径不依赖长窗口全量 `SMembers`。
- 告警：重复曝光、空 feed、模型 fallback、曝光集中、违规下架剔除延迟、缓冲/ingest 丢弃。
- 回滚层：关闭动态预算、关闭复活源、关闭协同召回、回退 hot/new。

## 非目标

- P0 不实现 P1/P2 的曝光基尼、覆盖率、生命周期复活、策略下架剔除延迟等高级 emitter；这些告警继续标注为预置。
- 不以 local-gamma 模拟性能替代真集群容量结论。

## 验收标准

- A1：所有 SLI 名称以 `recommendation_slo.yaml` 为真相源。
- A2：告警阈值与 SLO objective 对齐；无 emitter 的告警必须标注 emitter 前置，不假装已修复。
- A3：容量方案按规模分层，不提前引入复杂结构；过滤路径不依赖长窗口全量 `SMembers`，有 payload/alloc 上限报告。
- A4：每个成熟能力都有关闭或降级路径。
- A5：状态写入量、ingest QPS、buffer/ingest drop 可观测（`rec_hotpath_dropped_total`、`ingest_dropped_total`）。
