# L3 Story：曝光可观测性容量 (`exposure-observability-capacity`)

> 所属能力：[`exposure-governance`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望告警阈值与 SLO objective 对齐；无 emitter 的告警必须标注 emitter 前置，不假装已修复，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “曝光可观测性容量”的输入、可观察主路径、失败语义以及与父能力的交接。
- 曝光健康 SLI 和告警阈值。
- 容量策略分层。
- 回滚层与降级路径。
- P0 不实现曝光基尼、覆盖率、生命周期复活、策略下架剔除延迟等 P1/P2 高级 emitter。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 曝光可观测性容量

- “曝光可观测性容量”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 告警阈值与 SLO objective 对齐；无 emitter 的告警必须标注 emitter 前置，不假装已修复

- 告警阈值与 SLO objective 对齐；无 emitter 的告警必须标注 emitter 前置，不假装已修复。
- feed 终态使用 `recommendation_feed_terminal_total{request_class,outcome,failure_stage}`；三项 label 均为闭集，禁止写入 user/content/request/source 自由值。
- `request_class=initial_recommend` 的成功空结果必须为零；canonical failure 按 bounded `failure_stage` 告警。`following` 健康空与 `continuation` 自然结束只计 `outcome=empty`，不伪造为 failure。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`
- canonical：`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 曝光可观测性容量

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“曝光可观测性容量”对应的公开行为。
- THEN 通过父能力公开契约交付“曝光可观测性容量”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。
- AND feed 终态 metric 能分辨 initial recommend、following、continuation、browse 以及 success/degraded/empty/failure，且不存在高基数 label。

## 6. 依赖

- 前置要求：[`exposure-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
