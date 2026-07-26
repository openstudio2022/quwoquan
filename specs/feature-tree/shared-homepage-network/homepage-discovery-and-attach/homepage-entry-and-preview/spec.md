# L3 Story：从搜索结果、内容卡、关注频道、交集导航进入主页详情并保留原上下文 (`homepage-entry-and-preview`)

> 所属能力：[`homepage-discovery-and-attach`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望从搜索结果、内容卡、关注频道、交集导航进入主页详情并保留原上下文，从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- 搜索/feed 对象卡/关注频道/沉浸浏览器实体提及/交集导航进入 homepageDetail。
- 预览摘要（HomepageSummary initialSummary）先渲染，详情数据到达后替换。
- 返回后原搜索或发布上下文保留。

### Out of Scope

- 主页完整内容与口碑消费（homepage-review-and-content-journey）。
- 主页搜索候选本身（homepage-search-and-picker）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多入口进入主页详情且预览到详情无跳变

- 入口断裂为零：六类入口全部可达 homepageDetail 且埋点带 referralSource。

<a id="req-002"></a>
### REQ-002 主页入口和返回路径必须可预期

- 主页入口和返回路径必须可预期。
- 预览信息必须足以支持用户做“是否进入详情”的判断。
- 进入详情后不能丢失原上下文。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多入口进入主页详情且预览到详情无跳变

- GIVEN 已发布主页可经 /homepages/{id} 访问，入口携带 referralSource 与可选 initialSummary。
- WHEN 用户从搜索结果、feed 对象卡、关注频道或交集导航点击进入。
- THEN 详情页按 referralSource 上报曝光（trackEntityPageView），加载失败展示结构化错误态并可重试。
- THEN initialSummary 先呈现基础信息，bundle 到达后无信息架构跳变。
- THEN 返回（pop）后原上下文（搜索词/feed 位置）保留。

## 6. 依赖

- 前置要求：[`homepage-discovery-and-attach`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多入口进入主页详情且预览到详情无跳变

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：入口断裂为零：六类入口全部可达 homepageDetail 且埋点带 referralSource。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
