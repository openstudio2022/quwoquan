# L3 Story：质量评分冷启动 (`quality-score-cold-start`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望在缺少用户行为时以内容质量分和受控先验排序，并在反馈到达后逐步让位于个性化信号，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “质量评分冷启动”的输入、可观察主路径、失败语义以及与父能力的交接。
- 内容质量分来源、异步投影、训练 item 特征字段、质量分覆盖率。
- UGC、BulkImport 与数据工程 importer 同一投影公式。
- 同步质量模型 RPC、深度质量模型。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 质量评分冷启动

- 在缺少用户行为时以内容质量分和受控先验排序，并在反馈到达后逐步让位于个性化信号。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/storage.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 质量评分冷启动

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“质量评分冷启动”对应的公开行为。
- THEN 在缺少用户行为时以内容质量分和受控先验排序，并在反馈到达后逐步让位于个性化信号。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 质量评分冷启动 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“质量评分冷启动”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
