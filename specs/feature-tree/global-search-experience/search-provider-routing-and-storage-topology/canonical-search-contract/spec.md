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
- 请求过滤词汇单轨：`objectTypes` 只使用 canonical 对象词汇（`content.post` / `user.profile` / `entity.homepage` / `circle.circle` / `circle.group` / `location.place`），`contentTypes` 只使用 `article` / `image` / `video`；App、api-edge GraphQL 读接口与 assistant retrieval 共用同一词汇。
- 商用 response 字段 requestId/experimentBucket/relatedTerms/rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason。
- 搜索实验 assignment unit 只使用可信登录主体或匿名稳定 `X-Session-Id`；禁止空主体默认为 control，也禁止用逐请求 requestId 重分桶。
- 未投影或未激活实验策略时，搜索可按显式 control 语义降级；该 control 语义必须拥有稳定策略摘要并与候选、查询、筛选和主体共同绑定分页 cursor，不得因命中超过首屏而退化为 `SEARCH.USER.invalid_argument`。
- Search runtime 必须从受管部署入口接收当前 immutable candidate digest；不得以空候选身份签发分页 cursor，也不得仅在单页查询中形成假绿。
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
- Data Post 只能由 Content durable outbox 的 canonical Post lifecycle 进入搜索文档，并且必须匹配当前 active Data release；公开 UGC 经同一 lifecycle 进入，更新后重建文档、删除后移除。禁止 Data 或环境部署直接 seed 搜索索引。
- release verify 必须经 canonical `POST /search` 精确证明 Manifest 中每个 Data Post 和平台虚拟 Persona 可查询；仅证明 importer 成功不能作为 Search 就绪证据。
- User/Persona 公共资料只通过 `UserProfileSearchProjectionRequested` durable event 进入 Search；事件必须自包含公开快照，SearchIndexView 以 eventId inbox 与 profileVersion watermark 幂等消费、独占 Provider upsert/delete，失败不得前移 checkpoint，禁止 User 直写搜索 Provider 或 Search 回读 User 数据库。

<a id="req-004"></a>
### REQ-004 请求过滤词汇单轨（objectTypes + contentTypes）

- `search(request)` 的 `objectTypes` 取值域是 canonical 对象词汇：`content.post` / `user.profile` / `entity.homepage` / `circle.circle` / `circle.group` / `location.place`；`contentTypes` 取值域是 `article` / `image` / `video`，仅当过滤范围含 `content.post` 时生效。
- 内部召回 target（`article/photo/video/user/entity/circle/group/location`）是 search-service 的实现细节，由 `objectTypes × contentTypes` 在服务端单点压平推导；target 词汇不得出现在任何对外 wire、GraphQL schema、App enum 或 assistant tool 参数中。
- App `RemoteSearchPageRepository`、api-edge `SearchPage` executor、search-service 请求校验与 assistant retrieval 四处的词汇必须同源，任一处偏离即门禁 BLOCK；禁止在链路中间做第二套词汇翻译表。
- 携带合法 `objectTypes`/`contentTypes` 的请求不得被 `SEARCH.USER.invalid_argument` 拒绝；携带 target 词汇或未登记词汇的请求必须结构化拒绝，不得静默回退默认召回域。

## 4. 契约引用

- canonical：`contracts/metadata/_shared/search_contract.yaml`
- canonical：`contracts/metadata/_shared/search_objects.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 唯一 canonical contract + 商用 response 字段（metadata/codegen 对齐）

- GIVEN _shared/search_contract.yaml 已登记商用字段且 make verify-metadata 绿。
- GIVEN codegen 产物 search_registry.g.dart 与 metadata 一致且幂等。
- WHEN 调用 search(request) 以 mode=suggest|result 区分，返回统一 envelope。
- THEN response 含 requestId/experimentBucket/relatedTerms；hit 含 rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason。
- THEN 登录态从可信 principal 派生 experiment subject；匿名态必须按 SearchRequestFact contract 携带稳定 `X-Session-Id`，缺失时返回 `SEARCH.USER.invalid_argument`。
  实验策略缺失或未激活时返回 `experimentBucket=control`，多页中文查询仍生成绑定 canonical control 摘要的 opaque cursor；策略身份变化后旧 cursor 必须 fail-closed。
- THEN suggest 与 result 共用同一接口，无第二套建议专用接口。
- AND UserProfile/Persona 更新与删除由同一 Search-owned durable consumer 投影；相同 eventId 重放幂等，旧版本不覆盖新版本，Provider 失败保留 pending stream checkpoint。

<a id="gwt-002"></a>
### GWT-002 App result 只消费 canonical 响应（RemoteSearchRepository + RetrieveRequest 映射 + 错误响应）

- GIVEN alpha/beta/gamma/prod composition 中 searchRepositoryProvider 只返回 RemoteSearchRepository；搜索 typed double 仅存在测试树。
- GIVEN RetrieveRequest.fromSearchRequest() 单源映射 targets 并剔除 chat 本地命名空间对象。
- WHEN result 阶段 POST /search（CloudHttpClient + codegen path），解析 RetrieveResponse。
- THEN App 透传 rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason/relatedTerms，不再消费分域搜索接口。
- THEN 错误经 CloudException/runtimeFailure 结构化，不吞异常、不暴露原始异常字符串。

<a id="gwt-003"></a>
### GWT-003 请求过滤词汇单轨端到端生效（objectTypes + contentTypes）

- GIVEN App 结果页任一 Tab 携带 canonical `objectTypes`（如 `content.post`）与可选 `contentTypes`（如 `video`）发起搜索。
- WHEN 请求经 api-edge GraphQL `SearchPage` persisted query 转发到 search-service `POST /search`。
- THEN search-service 接受该词汇并返回 200，结果集只含所选 objectTypes；`contentTypes` 过滤在 `content.post` 命中上生效。
- THEN 携带内部 target 词汇（如 `photo`）或未登记词汇的请求被结构化拒绝：search-service 返回 `SEARCH.USER.invalid_argument`，GraphQL 层由 `SearchPageObjectType`/`SearchPageContentType` 枚举校验拒绝内部词汇上 wire。
- THEN App enum、GraphQL schema 枚举、api-edge 映射与 search-service 校验四处词汇由静态门禁证明同源；api-edge 集成测试的 owner 替身与真实 `POST /search` 校验语义同源，不得再出现替身接受、真实拒绝的分裂。
- THEN 结果投影字段在 wire 上完整：`searchRequestId`、`matchedTerms`、`degradeSignals` 位于 slice 级，`rankPosition`、`contentType`、`rankReason` 位于 item 级。
- THEN 同 viewer/query/filter 的重复执行 TopN `objectRef` 序列一致；翻页 cursor 序列连续无重复，且全栈装配链（网关 `/graphql` → api-edge persisted query → search-service 真进程 → CJK ES）上述行为由环境冒烟 CaseResult 证明。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 词汇单轨的 gamma-local 全栈冒烟证据

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：历史断链（api-edge 翻译 canonical 词汇、search-service 只认内部 target 词汇，携带 objectTypes 的正式搜索 100% 返回 400）已修复：search-service 校验切换为 canonical `objectTypes`+`contentTypes`（`TargetsForCanonicalFilter`），词汇同源由 `verify_search_wire_vocabulary_single_track.py` 门禁与 api-edge↔runtime/search 契约测试（`search_page_owner_vocabulary__local_contract_test.go`）钉死，真实 ES 上 `golden_query_relevance__api_integration_test.go` 证明过滤端到端生效。尚缺 gamma-local 全栈（App→Caddy→api-edge→search-service 真进程）冒烟 CaseResult。
- 完成判定：`GWT-003` 全部子句绑定真实测试 `spec_ref`，且 gamma-local 全栈 `/graphql` SearchPage（含 objectTypes/contentTypes 过滤）冒烟通过。
