# L3 Story：主页记录/讨论聚合 Tab 消费挂载内容与问答预览 (`homepage-content-and-question-aggregation`)

> 所属能力：[`homepage-review-and-content`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望主页记录/讨论聚合 Tab 消费挂载内容与问答预览，并可跳转内容消费，从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- HomepageUIConfig 驱动的一级 Tab（记录/讨论/兴趣圈）与记录流二级过滤。
- contentPreview/questionPreview 投影消费与点击进入 workBrowser。
- 点击埋点携带 referralSource=entityPage 与 feedRequestId。

### Out of Scope

- 发布写入（homepage-contextual-publish-entry）。
- 评论树本身（content 域）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 用户在主页浏览挂载记录并进入消费

- 记录/讨论聚合四态齐备且点击回流埋点在。

<a id="req-002"></a>
### REQ-002 问答和内容必须可区分，但都属于主页聚合面

- 问答和内容必须可区分，但都属于主页聚合面。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/ui_config.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/projections/homepage_content_preview.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户在主页浏览挂载记录并进入消费

- GIVEN 已发布主页带 contentPreview/questionPreview 投影（fixture 或真实挂载回流）。
- WHEN 用户切换 Tab、按类型过滤并点击一条记录。
- THEN Tab 结构来自 HomepageUIConfig codegen，不由页面硬编码。
- THEN 点击经 contentBehaviorTracker 上报后进入 workBrowser 且上下文保留。
- THEN 无内容时展示可恢复空态，不制造假记录。

## 6. 依赖

- 前置要求：[`homepage-review-and-content`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 用户在主页浏览挂载记录并进入消费

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：记录/讨论聚合四态齐备且点击回流埋点在。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
