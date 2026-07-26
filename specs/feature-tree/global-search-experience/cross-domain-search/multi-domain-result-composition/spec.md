# L3 Story：搜索结果不只是“查出来” (`multi-domain-result-composition`)

> 所属能力：[`cross-domain-search`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望联想页提供快速直达、独立网络结果页编排 assistant 与内容分类结果，并在局部失败时保留可用结果，从而看懂结果、准确进入目标且不会陷入持续等待。

## 2. 范围与非目标

### In Scope

- 本地分段与云实体并行、部分失败和终态映射。
- 正式结果页 canonical `POST /search` 单请求。
- 3 秒慢提示、6 秒取消、supersede/dispose 与旧内容保留。

### Out of Scope

- 搜索索引和生产部署。
- 新的 request profile 或第二套 outcome 状态体系。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多域结果并行结算且等待必有出口

- 输入“钱”可预览并打开发布态“东钱湖”实体主页。
- 全页同一 request scope 同时只有一个主 indicator，任何路径均停止等待。

<a id="req-002"></a>
### REQ-002 点击联系人/聊天记录直达会话、点击网络结果进入独立结果页、点击结果卡片进入内容或引用对象的统一跳转语义

- 点击联系人/聊天记录直达会话、点击网络结果进入独立结果页、点击结果卡片进入内容或引用对象的统一跳转语义。
- 联系人和聊天记录的“更多”只能做当前页内联展开，不能跳到新的中间列表页。
- 跨 Circle 对象的聚合分区显示“讨论”，消息 group 显示“群聊”，Circle 对象显示“圈子”。
- 结果模型必须可类型化，不允许长期停留在松散 `Map` 拼装层。
- 任何 query/tab generation 被替换、超时或页面销毁时都必须让旧结果失效，并通过真实 cancellation signal 终止可见网络请求；`Future.timeout` 不作为 transport cancellation。
- `page_lifecycle_state` 复用 `waitMode`、`durationMs` 与 `phase=slow/timeout/cancelled/partial`，禁止记录原始搜索词。

## 4. 契约引用

- canonical：`quwoquan_service/services/search-service/contracts/search/search_query/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多域结果并行结算且等待必有出口

- GIVEN 用户输入 query，本地域与云域响应时延或失败情况不同。
- WHEN 联想页或正式结果页执行搜索，随后发生完成、部分失败、超时、query 替换或 dispose。
- THEN 本地结果先展示，云实体只在“搜索网络结果”段局部等待。
- THEN 正式结果每个 generation 只调用一次 canonical `/search`。
- THEN 3 秒只在空白阻塞时显示一次提示；6 秒真实取消 transport 并进入可重试终态。
- THEN empty、partial、timeout、failure 分开映射；旧 completion 不得回写。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
