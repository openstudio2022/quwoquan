# L3 Story：动态曝光预算 (`dynamic-exposure-budget`)

> 所属能力：[`exposure-governance`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望按内容池质量和反馈动态分配曝光预算，同时保留探索下限、总预算与回滚边界，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “动态曝光预算”的输入、可观察主路径、失败语义以及与父能力的交接。
- 流量池状态、bandit 先验、reward 与晋级/淘汰阈值。
- 动态预算指标、AB 分桶和回滚层。
- P1 先实现基于 recpolicy 的分级流量池曝光份额约束；真实 Thompson Sampling 与预算存储留给后续 `rm_exposure_state` 物化增强。
- 深度排序模型和 IPS 训练不进入本 Story。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 动态曝光预算

- 按内容池质量和反馈动态分配曝光预算，同时保留探索下限、总预算与回滚边界。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 动态曝光预算

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“动态曝光预算”对应的公开行为。
- THEN 按内容池质量和反馈动态分配曝光预算，同时保留探索下限、总预算与回滚边界。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`exposure-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 动态曝光预算 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“动态曝光预算”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
