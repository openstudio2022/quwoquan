# L3 Scenario: canonical-search-contract

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_feature`: `search-provider-routing-and-storage-topology`
- `L3_scenario`: `canonical-search-contract`

## 背景与动机

搜索建议与正式结果如果继续拆成两套产品接口，页面层很快就会重新长出第二套搜索语义；如果 contract 设计得过重过复杂，AI 也无法像调用 web search 一样稳定拆题与检索。该 Scenario 用来冻结唯一 canonical 搜索 contract。

## 功能范围

- 统一 `search(request)` 作为页面与业务层唯一入口。
- 统一 `search(request)` 作为页面与 AI agent 检索 tool 的共用入口。
- `suggest` 与 `result` 共享同一接口，只通过 `mode` 区分。
- 统一 `SearchRequest / SearchResponse / SearchSection / SearchHit` envelope。
- AI 模型可生成 typed 查询条件，但必须落在 schema 允许范围内。
- contract 必须保持 web-search-like 的 query-first 结构，支持 `web.document` 与趣我圈对象统一召回。

## Out of Scope

- 具体排序算法。
- 具体 provider 实现。
- 复杂布尔 DSL、脚本排序表达式与图查询语言。

## 约束

- 不允许新增“建议专用接口”。
- 不允许页面层直接消费分域搜索接口。
- 不允许为 AI agent 维护独立的第二套搜索接口。
- 不允许把一次查询设计成过深的嵌套结构；应优先支持 AI 多次小查询，而不是单次巨大复杂表达式。

## 验收重点

1. 建议与正式结果是否共用同一接口。
2. 页面与业务层是否真正只看到一个 contract。
3. AI 是否能像使用 web search 一样，用一个关键词串加少量条件完成主题拆分式检索。
