# L3 Story：最近搜索和语音输入是搜索首页高频能力 (`recent-search-sync-and-voice-asr`)

> 所属能力：[`cross-domain-search`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望在搜索首页查看、管理并跨端同步最近搜索，同时使用独立的语音输入能力，从而快速复用查询且不会混淆本地记录、远端记录和 assistant 结果。

## 2. 范围与非目标

### In Scope

- search-service /search/recent 四条对象级 operation。
- 登录 Persona 跨请求同步、语义键去重、有界淘汰、单条删除与清空。
- 游客本地缓存与登录后 Remote 真相源合并。

### Out of Scope

- 语音 ASR 输入链路；另由平台语音能力 Story 承载。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 最近搜索跨端同步、语义去重与安全重放

- 本地表现层与真实 Mongo 路径必须使用相同语义去重、receipt 与 owner 隔离规则。

## 4. 契约引用

- canonical：`quwoquan_service/services/search-service/contracts/search/recent_search_state/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 最近搜索跨端同步、语义去重与安全重放

- GIVEN 用户以 Persona 登录并执行搜索。
- GIVEN App 通过 RecentSearchQuery / RecentSearchCommandWriter 访问 search-service。
- WHEN 用户重复搜索同一 scope + facet + normalized query，或重放相同命名意图。
- WHEN 用户删除单条记录或清空指定 scope。
- THEN entryId 由服务端语义键 sha256 派生；客户端不提交版本字段或自造 hashCode。
- THEN 同语义条目只保留一条并置顶，单 scope 最多 12 条。
- THEN version CAS 冲突在服务端有限重放；相同 Idempotency-Key 返回首次 receipt。
- THEN 登录态 Remote 为真相源；游客/离线仅使用本地表现层缓存。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
