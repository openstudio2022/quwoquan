# L3 Story：标准搜索契约 (`canonical-search-contract`)

> 所属能力：[`search-provider-routing-and-storage-topology`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望 App 与小趣通过同一 search request/response 契约获得可分类、可分页且错误明确的结果，从而找到可理解并可继续操作的对象。

## 2. 范围与非目标

### In Scope

- 单一 search(request) contract，suggest/result 仅以 mode 区分。
- 商用 response 字段 requestId/rankingVersion/experimentBucket/relatedTerms/rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason。
- App RemoteSearchRepository + RetrieveRequest 映射；assistant search tool 桥接 canonical。
- 错误响应经 CloudException/runtimeFailure 结构化。

### Out of Scope

- 具体排序算法与 provider 实现。
- 复杂布尔 DSL / 脚本排序 / 图查询表达式。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 唯一 canonical contract + 商用 response 字段（metadata/codegen 对齐）

- 页面与业务层只看到一个 contract，商用字段以 metadata 为唯一真相源。

<a id="req-002"></a>
### REQ-002 App result 只消费 canonical 响应（RemoteSearchRepository + RetrieveRequest 映射 + 错误响应）

- App result 阶段唯一消费 canonical search(request) 响应。

<a id="req-003"></a>
### REQ-003 统一 search(request) 作为页面与业务层唯一入口

- 统一 `search(request)` 作为页面与业务层唯一入口。
- 统一 `search(request)` 作为页面与 AI agent 检索 tool 的共用入口。
- 统一 `SearchRequest / SearchResponse / SearchSection / SearchHit` envelope。
- AI 模型可生成 typed 查询条件，但必须落在 schema 允许范围内。
- contract 必须保持 web-search-like 的 query-first 结构，支持 `web.document` 与趣我圈对象统一召回。
- 商用字段（`rankReasons / rankPosition / relatedTerms` 等）只在服务端产出，端侧只读消费，不得客户端合成形成第二真相源。

## 4. 契约引用

- canonical：`contracts/metadata/_shared/search_contract.yaml`
- canonical：`contracts/metadata/_shared/search_objects.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 唯一 canonical contract + 商用 response 字段（metadata/codegen 对齐）

- GIVEN _shared/search_contract.yaml 已登记商用字段且 make verify-metadata 绿。
- GIVEN codegen 产物 search_registry.g.dart 与 metadata 一致且幂等。
- WHEN 调用 search(request) 以 mode=suggest|result 区分，返回统一 envelope。
- THEN response 含 requestId/rankingVersion/experimentBucket/relatedTerms；hit 含 rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason。
- THEN suggest 与 result 共用同一接口，无第二套建议专用接口。

<a id="gwt-002"></a>
### GWT-002 App result 只消费 canonical 响应（RemoteSearchRepository + RetrieveRequest 映射 + 错误响应）

- GIVEN alpha/beta/gamma/prod composition 中 searchRepositoryProvider 只返回 RemoteSearchRepository；搜索 typed double 仅存在测试树。
- GIVEN RetrieveRequest.fromSearchRequest() 单源映射 targets 并剔除 chat 本地命名空间对象。
- WHEN result 阶段 POST /search（CloudHttpClient + codegen path），解析 RetrieveResponse。
- THEN App 透传 rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason/relatedTerms，不再消费分域搜索接口。
- THEN 错误经 CloudException/runtimeFailure 结构化，不吞异常、不暴露原始异常字符串。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
