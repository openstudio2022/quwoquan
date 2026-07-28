# L2 Business Capability：曝光治理 (`exposure-governance`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

推荐曝光治理的商用成熟度能力：served/impressed 双轨、疲劳、频控、动态预算、复活、活跃度自适应与曝光健康。

## 2. 范围与非目标

### In Scope

- served/impressed 双轨和跨页、跨会话去重规格。
- 作者、标签、话题和 near-dup 频控规格。
- 动态曝光预算、分级流量池和 bandit 先验规格。
- 内容生命周期复活与活跃度自适应规格。
- 曝光健康 SLI、容量与回滚策略。
- 行为事件分桶字段：feedRequestId/channelId/vertical/recallPath/rankingVersion/reasonVersion/intersectionSourceRef/intersectionClass。

### Out of Scope

- P1/P2 的动态预算、生命周期复活、协同召回和模型容量按各自 Story 推进。
- 深度排序模型平台轨。
- 交集 affinity 异步模型化与四主页真实数据 api_integration/user_acceptance。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-007`](../../spec.md#scn-007)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：推荐曝光治理的商用成熟度能力：served/impressed 双轨、疲劳、频控、动态预算、复活、活跃度自适应与曝光健康，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`activity-adaptive-exposure`](./activity-adaptive-exposure/spec.md)：按用户活跃度调整曝光窗口、探索比、复活比和频控强度，不突破全局安全边界。
- [`content-lifecycle-resurfacing`](./content-lifecycle-resurfacing/spec.md)：`retired` 内容不得因复活源绕过合规准入。
- [`cross-session-fatigue-memory`](./cross-session-fatigue-memory/spec.md)：过滤路径用 membership 点查或近似结构，禁止长窗口全量 `SMembers`。
- [`dimension-frequency-and-neardup`](./dimension-frequency-and-neardup/spec.md)：定义“维度频控与近重复”的可观察主路径、失败语义及父能力交接。
- [`dynamic-exposure-budget`](./dynamic-exposure-budget/spec.md)：按内容池质量和反馈动态分配曝光预算，同时保留探索下限、总预算与回滚边界。
- [`exposure-observability-capacity`](./exposure-observability-capacity/spec.md)：定义“曝光可观测性容量”的可观察主路径、失败语义及父能力交接。
- [`ops-intervention-and-policy-ejection`](./ops-intervention-and-policy-ejection/spec.md)：所有干预必须可审计，可过期，可回滚。
- [`served-dedup-write-behind`](./served-dedup-write-behind/spec.md)：召回/过滤阶段下推 served exclude，过滤用候选集 `SISMEMBER` 批量点查或短 Bloom，禁止长窗口全量 `SMembers` 回读。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 曝光治理商用成熟度 SIT

- 七态状态分离（served/visible/impressed/dwell/interaction/negative/training_sample），短窗口下发去重和真实曝光疲劳分别有契约定义。
- 曝光记忆与过滤不依赖长窗口全量 SMembers，served/impressed 按 user+day 分桶、negative 用户级，容量有 cardinality budget。
- 端侧反馈上报统一通道、分级采样、clientEventId 幂等与 feedRequestId 归因闭环，细则归 feed-orchestration-recommendation/feedback-ingestion-sampling。
- 动态曝光预算、生命周期复活与活跃度自适应均通过 metadata-first 前置清单约束，不形成第二套推荐引擎。
- 曝光健康 SLI 与 `recommendation_slo.yaml` 同名；P0 emitter 已 measured，P1/P2 无 emitter 告警保持前置标注。
- 运营干预与违规/下架剔除有审计、过期、回滚和 SLO 口径。
- `feed-orchestration-recommendation` 只引用 exposure-governance 的能力边界，不再拥有独立曝光预算或生命周期真相源。

<a id="req-002"></a>
### REQ-002 反馈状态七态分离：`served`（下发）/`visible`（进入视窗）/`impressed`（达可见面积+停留阈值）/`dwell`（停留）/`interaction`（互动）/`negative`（负反馈）/`training_sample`（云侧派生），只能派生不能互替，详见 design.md

- 反馈状态七态分离：`served`（下发）/`visible`（进入视窗）/`impressed`（达可见面积+停留阈值）/`dwell`（停留）/`interaction`（互动）/`negative`（负反馈）/`training_sample`（云侧派生），只能派生不能互替，详见 design.md。
- 曝光记忆与过滤满足商用并发 / 容量 / 实时性：禁止长窗口全量 `SMembers` 回读，过滤走 membership 点查或近似结构。
- 端侧上报抗冲击：统一通道、分级上报、采样合并、幂等与归因闭环，降低云侧上行流量冲击。
- 端侧上报抗冲击的能力边界引用（统一通道 / 采样 / 幂等 / 归因，细则归 feed-orchestration-recommendation/feedback-ingestion-sampling）。
- P0 已实现状态分离、去全量化过滤、端侧统一上报、云侧 FeedbackIngestor 与基础观测；P1/P2 的动态预算、生命周期复活、协同召回和模型容量仍按各自 Story 推进。
- 作者、标签、话题和 near-dup 频控不会导致空 feed，必须有降级和保底。
- discovery/recommend 首刷仅因 served/impressed 长期曝光记忆耗尽时，可对同一批真实候选执行一次受控回退；该回退只放宽长期 exposure，不得绕过 explicit negative、隐藏作者/类型、双向 block、safety、published 或 hydration 检查。
- 当前会话短窗口去重、强负反馈或合规过滤导致无可用候选时不得强行重复下发；必须返回父能力定义的 canonical failure。有效 continuation 的自然末尾不触发 exposure 回退。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 曝光治理商用成熟度 SIT

- GIVEN 执行“曝光治理商用成熟度”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“曝光治理商用成熟度”对应动作。
- THEN 七态状态分离（served/visible/impressed/dwell/interaction/negative/training_sample），短窗口下发去重和真实曝光疲劳分别有契约定义。
- THEN 曝光记忆与过滤不依赖长窗口全量 SMembers，served/impressed 按 user+day 分桶、negative 用户级，容量有 cardinality budget。
- THEN 端侧反馈上报统一通道、分级采样、clientEventId 幂等与 feedRequestId 归因闭环，细则归 feed-orchestration-recommendation/feedback-ingestion-sampling。
- THEN 动态曝光预算、生命周期复活与活跃度自适应均通过 metadata-first 前置清单约束，不形成第二套推荐引擎。
- THEN 曝光健康 SLI 与 `recommendation_slo.yaml` 同名；P0 emitter 已 measured，P1/P2 无 emitter 告警保持前置标注。
- THEN 运营干预与违规/下架剔除有审计、过期、回滚和 SLO 口径。
- THEN `feed-orchestration-recommendation` 只引用 exposure-governance 的能力边界，不再拥有独立曝光预算或生命周期真相源。
- THEN discovery/recommend 首刷因长期 exposure 耗尽时只放宽 served/impressed 历史，并继续执行 negative/block/safety/published/hydration 硬过滤；continuation end 不做回退。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 曝光治理商用成熟度 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：七态状态分离（served/visible/impressed/dwell/interaction/negative/training_sample），短窗口下发去重和真实曝光疲劳分别有契约定义。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
