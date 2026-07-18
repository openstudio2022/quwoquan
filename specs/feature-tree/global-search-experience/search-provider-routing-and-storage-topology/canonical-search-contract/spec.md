# L3 Scenario: canonical-search-contract

## 节点定位

- `L1_domain_service`: `global-search-experience`
- `L2_business_capability`: `search-provider-routing-and-storage-topology`
- `L3_story`: `canonical-search-contract`

## 背景与动机

搜索建议与正式结果如果继续拆成两套产品接口，页面层很快就会重新长出第二套搜索语义；如果 contract 设计得过重过复杂，AI 也无法像调用 web search 一样稳定拆题与检索。该 Scenario 用来冻结唯一 canonical 搜索 contract。

## 功能范围

- 统一 `search(request)` 作为页面与业务层唯一入口。
- 统一 `search(request)` 作为页面与 AI agent 检索 tool 的共用入口。
- `suggest` 与 `result` 共享同一接口，只通过 `mode` 区分。
- 统一 `SearchRequest / SearchResponse / SearchSection / SearchHit` envelope。
- AI 模型可生成 typed 查询条件，但必须落在 schema 允许范围内。
- contract 必须保持 web-search-like 的 query-first 结构，支持 `web.document` 与趣我圈对象统一召回。

## 2026-06-16 商用 response 字段（已落地，纳入正式 contract）

canonical `SearchResponse` / `SearchHit` 已扩展以下商用字段（真相源 `contracts/metadata/_shared/search_contract.yaml`，R-S02/R-S07）：

| 字段 | 层级 | 语义 |
|---|---|---|
| `requestId` | response | 单次检索请求标识，贯穿日志 / 反馈 / 排序归因 |
| `rankingVersion` | response | 排序版本（如 `search-v1`），用于灰度与回放 |
| `experimentBucket` | response | AB 切桶（`control` / `term_heat`），一致性哈希稳定切桶 |
| `relatedTerms` | response | 服务端 `queryheat` 计算的相关搜索词（端侧不再硬编码拼词） |
| `rankReasons` | hit | 排序原因（透明化），首条可作展示理由 |
| `rankPosition` | hit | 分页后 1-based 排序位次 |
| `coverWidth` / `coverHeight` | hit | 真实封面尺寸，结果页 masonry 按真实宽高比排布 |
| `connectionState` | hit | 连接态闭集，驱动已连接区 / 发现区 / 交集分组（端侧不推断） |
| `intersectionReason` | hit | 交集理由（`primaryText` 等），端侧只读展示、不二次拼装 |

App `result` 阶段统一消费 canonical `search(request)` 响应，**不再消费分域搜索接口**（各域 `/.../search` 退化为 indexer 数据源 / 内部回退）。

## Out of Scope

- 具体排序算法。
- 具体 provider 实现。
- 复杂布尔 DSL、脚本排序表达式与图查询语言。

## 约束

- 不允许新增“建议专用接口”。
- 不允许页面层直接消费分域搜索接口；App `result` 阶段只消费 canonical `search(request)` 响应。
- 不允许为 AI agent 维护独立的第二套搜索接口。
- 不允许把一次查询设计成过深的嵌套结构；应优先支持 AI 多次小查询，而不是单次巨大复杂表达式。
- 商用字段（`rankReasons / rankPosition / relatedTerms` 等）只在服务端产出，端侧只读消费，不得客户端合成形成第二真相源。

## 验收重点

1. 建议与正式结果是否共用同一接口。
2. 页面与业务层是否真正只看到一个 contract。
3. AI 是否能像使用 web search 一样，用一个关键词串加少量条件完成主题拆分式检索。
