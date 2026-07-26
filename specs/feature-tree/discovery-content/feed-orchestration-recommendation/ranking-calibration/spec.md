# L3 Story：排序校准 (`ranking-calibration`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望以点击、完成和负反馈校准排序分，使预测分与真实结果在声明窗口内对齐，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “排序校准”的输入、可观察主路径、失败语义以及与父能力的交接。
- 规则分、模型分、质量分、交集分的校准口径。
- scorer_variant/channel/segment 维度版本化。
- calibration error 指标。
- 本 Story 不包含校准训练或在线重打分实现。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 排序校准

- 以点击、完成和负反馈校准排序分，使预测分与真实结果在声明窗口内对齐。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 排序校准

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“排序校准”对应的公开行为。
- THEN 以点击、完成和负反馈校准排序分，使预测分与真实结果在声明窗口内对齐。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 排序校准 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“排序校准”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
