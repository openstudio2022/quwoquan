# L3 Story：小趣搜索结果 Handoff (`xiaoqu-entry-handoff`)

> 所属能力：[`cross-domain-search`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望在独立网络结果页进入“小趣搜”，获得带真实站内对象或公开网页引用的 assistant 搜索结果，从而理解答案来源并继续打开目标对象。

## 2. 范围与非目标

### In Scope

- 小趣自然语言 query 到 canonical search request 的转换。
- web.document 与站内对象统一聚合、引用和降级。
- `StartAssistantRun` 的 `search` 意图在同一 Run 生命周期中输出真实 citation provenance。
- page/object rich context 参与 retrieval 与 citation rank。

### Out of Scope

- LLM 自由执行未登记 provider。
- 未授权聊天消息跨用户检索。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 小趣通过统一 LLM search tool 获得网页与站内对象检索结果

- `StartAssistantRun` 的 `search` 意图不得返回固定 spec/knowledge 占位 citation。
- tool_coordinator 测试能证明 web_search/app_search/search 走 canonical_search provider。
- 小趣结果页可以打开真实站内对象或公开 web citation。

<a id="req-002"></a>
### REQ-002 小趣搜使用 typed contract 返回真实结果

- `小趣搜` 必须通过 `AssistantRunIntent.search` 与 `StartAssistantRun` 的 typed contract 返回真实结果，不得新增独立搜索模型执行 operation，也不能在 runtime 做字符串语义分流。
- 借鉴微信搜索中的独立 AI / 网络结果入口心智，但统一收口为网络结果页中的 `小趣搜` tab。

## 4. 契约引用

- canonical：`specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_contract.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_objects.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 小趣通过统一 LLM search tool 获得网页与站内对象检索结果

- GIVEN 用户在小趣或全局搜索“小趣搜”输入自然语言 query，请求以 `AssistantRunIntent.search` 进入唯一 Run 入口。
- GIVEN canonical search registry 已注册 web.document、content.post、entity.homepage、circle.group、chat.message 等对象类型。
- WHEN 小趣生成 searchPlans/queryVariants 并调用 search 工具。
- THEN web_search 能力作为 web.document provider 接入 canonical search，而不是独立 fake adapter。
- THEN app_search/search/web_search 的工具输出采用同一 hits/citations/provenance envelope。
- THEN 返回 citation 至少包含 objectType、objectId、title、snippet、sourceDomain、score。
- THEN 未实现或不可访问 provider 返回 degrade signal，不阻断其他 provider 结果。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 小趣搜索真实 provider 聚合与可执行验收尚未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺真实 `canonical_search` provider 聚合、部分 provider 不可用时的结构化 degrade、citation readback 以及直接引用本节点 GWT 的 `api_integration / user_acceptance` 证据；`AssistantRunIntent.search`、`StartAssistantRun` 与引用视图已有 canonical source contract。
- 在该唯一 Run operation 的 provider degrade envelope、真实 citation readback 和直接 `spec_ref` 测试闭合前，
  不得把现有 UI 替身测试提升为本 GWT 已通过，也不得以非生产 provider substitute 冒充真实网页来源。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
