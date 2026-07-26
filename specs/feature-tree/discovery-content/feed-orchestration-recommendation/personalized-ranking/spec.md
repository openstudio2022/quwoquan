# L3 Story：个性化排序 (`personalized-ranking`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望端侧不得解析 token，仅做透传和存储，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “个性化排序”的输入、可观察主路径、失败语义以及与父能力的交接。
- sort=recommend 首屏与翻页路径。
- cursor 透传、不解析、连续推进。
- 强反馈过滤未来窗口，弱反馈影响未来重排。
- 端侧已看窗口回滚稳定。
- 协同召回、排序校准、时间衰减与上下文化排序的商用成熟度规格。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 个性化排序

- “个性化排序”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 端侧不得解析 token，仅做透传和存储

- 端侧不得解析 token，仅做透传和存储。

<a id="req-003"></a>
### REQ-003 排序策略、特征与解释一致

- policy.yaml、feature_registry、ContentCandidate、RuleScorer 和 App 解释显示均对齐。

<a id="req-004"></a>
### REQ-004 契约与字段策略必须与 metadata 保持一致

- 契约与字段策略必须与 metadata 保持一致。
- 本 Story 禁止新增 intersection-only ranker，也不把 `/score` 同步塞进 feed 读路径。
- `affinityIntersectionScore` 没有 `intersectionConfidenceLabel` 时不得参与候选级融合。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_contract.yaml`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/feature_registry.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 个性化排序

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“个性化排序”对应的公开行为。
- THEN 通过父能力公开契约交付“个性化排序”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
