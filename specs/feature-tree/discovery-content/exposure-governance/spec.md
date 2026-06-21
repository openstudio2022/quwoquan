# L2 特性：exposure-governance

## 功能说明

`exposure-governance` 是发现内容域的曝光治理主能力，负责把“下发去重、真实曝光疲劳、动态曝光预算、内容生命周期复活、活跃度自适应和曝光健康观测”统一成商用推荐体验的单一业务能力。

本能力与 `feed-orchestration-recommendation` 平级：

- `feed-orchestration-recommendation` 负责首页 feed 编排、流式体验、端云行为回流和交集理由消费。
- `exposure-governance` 负责曝光记忆、曝光预算、生命周期、复活和曝光健康 SLI。
- `runtime/runtime-recommendation` 提供 HotPath、MMR、UCB、bandit、缓存与存储接口原语，不拥有页面 IA 或业务口径。

## 商用目标

- 同一用户在可配置窗口内不重复看到同一内容或近重复内容。
- 反馈状态七态分离：`served`（下发）/`visible`（进入视窗）/`impressed`（达可见面积+停留阈值）/`dwell`（停留）/`interaction`（互动）/`negative`（负反馈）/`training_sample`（云侧派生），只能派生不能互替，详见 design.md。
- 曝光记忆与过滤满足商用并发 / 容量 / 实时性：禁止长窗口全量 `SMembers` 回读，过滤走 membership 点查或近似结构。
- 端侧上报抗冲击：统一通道、分级上报、采样合并、幂等与归因闭环，降低云侧上行流量冲击。
- 优质内容随反馈获得更多曝光预算，低质或负反馈内容被降级或淘汰。
- 优质老内容可被季节、事件、社交、常青或二次分发触发复活。
- 曝光分布受覆盖率与基尼约束，避免赢家通吃。

## 范围

### In Scope

- served/impressed/visible/dwell/interaction/negative/training_sample 七态分离与短窗口翻页去重。
- 曝光记忆去全量化：membership 点查 / 短 Bloom / day bucket / cardinality budget（运行时边界由 runtime-recommendation 提供）。
- 端侧上报抗冲击的能力边界引用（统一通道 / 采样 / 幂等 / 归因，细则归 feed-orchestration-recommendation/feedback-ingestion-sampling）。
- per-user 跨会话疲劳记忆与时间衰减。
- 作者、标签、话题频控与 near-dup 去重。
- 动态曝光预算：分级流量池赛马、bandit 先验和晋级/淘汰阈值。
- 内容生命周期状态机与复活召回。
- 活跃度自适应：新用户、活跃用户、沉默回流用户的窗口、探索比和复活比。
- 曝光健康 SLI：重复曝光率、覆盖率、曝光基尼、复活率、各池 CTR。

### Out of Scope

- 深度排序模型平台轨（MMoE/PLE/ESMM、双塔 ANN、IPS）。
- P0 已实现状态分离、去全量化过滤、端侧统一上报、云侧 FeedbackIngestor 与基础观测；P1/P2 的动态预算、生命周期复活、协同召回和模型容量仍按各自 Story 推进。
- 交集 affinity 概率分模型化、四主页真实数据 api_integration/user_acceptance、精品池全局运营写入能力，按各自 backlog 单独推进。

## Metadata-First 约束

后续实现前必须先声明：

- Redis key：`rec:served:{<userId>}:{<yyyyMMdd>}`、`rec:impressed:{<userId>}:{<yyyyMMdd>}`、`rec:freq:{<userId>}:{dimension}:{<yyyyMMdd>}`、`rec:near_dup:{<userId>}:{<yyyyMMdd>}`、`rec:exposure_budget:{contentId}`。
- recpolicy：曝光窗口、疲劳半衰期、频控阈值、near-dup 阈值、bandit 先验、流量池阈值、复活配额、校准因子。
- 读模型：`rm_exposure_state` 承载内容生命周期状态、曝光预算、复活触发器与统计窗口。
- 指标：所有曝光健康指标以 `recommendation_slo.yaml` 为真相源。

## 验收标准

- A1：同 session 跨页重复率低于 1%，cursor 候选变化时不扩大跳过/重复。
- A2：served 与 impressed 语义分离，served 只负责短窗口翻页去重，impressed 负责疲劳、训练与长期体验。
- A3：跨会话已看内容按时间衰减降权或过滤，强负反馈仍优先过滤未来窗口。
- A4：作者、标签、话题和 near-dup 频控不会导致空 feed，必须有降级和保底。
- A5：动态曝光预算能表达“少量试投、反馈达标晋级、负反馈淘汰”的状态机。
- A6：复活召回不绕过去重与合规准入，且可解释复活触发器。
- A7：曝光健康 SLI 与告警引用 `recommendation_slo.yaml` 同名指标。
- A8：P0 的 local_contract 已登记为 recorded；api_integration/user_acceptance 以 local-gamma 和旅程压测补齐，P1/P2 实现测试仍登记为 planned。
- A9：曝光记忆与过滤路径不依赖长窗口全量 `SMembers`，容量按规模分层并有 cardinality budget。
- A10：七态状态分离，`served`/`visible` 不作训练样本，`training_sample` 仅云侧派生；端侧上报有采样、幂等与归因闭环。
