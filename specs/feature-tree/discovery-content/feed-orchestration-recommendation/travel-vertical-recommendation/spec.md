# L3 Story：旅行垂类推荐 (`travel-vertical-recommendation`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望旅行频道 vertical=travel_photography 的召回、排序、fallback 与观测契约，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- subCategory/type 归一为 travel_photography。
- 旅行垂类过滤覆盖推荐召回与 repository fallback。
- channelId/vertical/recallPath 分桶观测。

### Out of Scope

- 旅行专用深排模型。
- 第二套旅行 feed API。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 旅行频道只返回合格旅行垂类内容

- 推荐召回、fallback 和交集理由通道均使用同一 channel/vertical 口径。

<a id="req-002"></a>
### REQ-002 Tag/Hot/Explore/Author/Mongo/PostRepo/Social/Collaborative/Vector 召回必须遵守 vertical 过滤或在候选回传后过滤

- Tag/Hot/Explore/Author/Mongo/PostRepo/Social/Collaborative/Vector 召回必须遵守 vertical 过滤或在候选回传后过滤。
- repository fallback 不得混入非旅行内容。
- 协同召回、社交召回和向量召回不得绕过旅行垂类过滤。

## 4. 契约引用

- canonical：`specs/feature-tree/discovery-content/feed-orchestration-recommendation/travel-vertical-recommendation/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 旅行频道只返回合格旅行垂类内容

- GIVEN 用户请求首页旅行频道，系统存在旅行和非旅行内容。
- WHEN content-service 调用推荐引擎并在召回不足时进入 fallback。
- THEN 推荐请求携带 Vertical=travel_photography，响应不混入非旅行内容。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 旅行频道只返回合格旅行垂类内容

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：推荐召回、fallback 和交集理由通道均使用同一 channel/vertical 口径。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
