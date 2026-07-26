# L3 Story：主页评价读写与评分摘要聚合 (`homepage-review-read-and-score-summary`)

> 所属能力：[`homepage-review-and-content`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望主页评价读写全链与评分摘要真实聚合（HomepageReview 独立聚合 + Homepage 摘要投影），从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- 发表/编辑/删除我的评价（1-5 星 + 正文 + 亮点标签）
- 评价 keyset 列表与我的评价预填（含软删复活）
- 摘要卡真实均分/评分数/亮点标签（review tagRefs 频次聚合）

### Out of Scope

- 维度分评价（B6 裁决砍除）
- 评价治理（举报/下架，归 Ops portal 后续批次）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 用户发表评价后列表与评分摘要真实收敛

- 五个 operation（create/update/delete/list/mine）在 alpha mock 与 remote 行为同构且全部 per-op commercial ready。

<a id="req-002"></a>
### REQ-002 评分摘要必须与真实口碑聚合保持一致

- 评分摘要必须与真实口碑聚合保持一致。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage_review/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage_review/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户发表评价后列表与评分摘要真实收敛

- GIVEN 已登录 persona 打开已发布主页详情页的口碑子 tab。
- WHEN 用户经写评价 sheet 提交 1-5 星、正文与亮点标签；随后编辑或删除该评价。
- THEN 评价出现在列表且"我的评价"支持编辑/删除；同一 persona 对同一主页只有一条记录。
- THEN 摘要（均分/评分数/亮点标签）由服务端对 active 评价真实聚合，删除后同步回退。
- THEN 网络重试经 Idempotency-Key 幂等重放，不产生重复评价；非作者修改被结构化拒绝。

## 6. 依赖

- 前置要求：[`homepage-review-and-content`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
