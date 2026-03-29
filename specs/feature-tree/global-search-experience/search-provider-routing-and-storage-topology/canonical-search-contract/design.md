# canonical-search-contract 设计方案

## 方案对比

### 方案 A：建议和正式结果分两套接口

缺点：

- 页面层需要记两套 contract。
- object taxonomy、埋点和 observability 容易分裂。

### 方案 B：统一 `search(request)` + `mode` + query-first 结构

优点：

- 页面与业务层只有一个入口。
- 统一 envelope、埋点和错误模型。
- 更接近 web search，便于 AI 用关键词串拆分主题并多轮调用。

## 选型决策

**选定方案：方案 B**

## 关键设计决策

- `SearchRequest` 至少包含：`query`、`mode`、`objectTypes`、`simpleFilters`、`sortHints`、`launchContext`、`limit`。
- `query` 是主输入，语义尽量接近 web search 的关键词串。
- `SearchRequest` 必须可序列化为 AI agent tool schema，便于模型生成 `query`、`objectTypes`、typed filters、sort hints 与 limit。
- `SearchResponse` 至少包含：`sections`、`degradeSignals`、`resolvedProviders`。
- `suggest` 与 `result` 都返回 typed `SearchHit`，只是在 section 组织上不同。
- 同一 contract 必须可覆盖 `web.document` 与趣我圈内部对象。
- 设计上优先支持 AI 发起多次简单查询，不支持深层布尔嵌套 DSL、脚本排序或自由表达式。

## metadata / codegen 方案

- `_shared/search/search_contract.yaml`
- `search_contract.yaml` 生成 App / cloud client / AI agent tool 共用 schema
- schema 默认暴露 query-first 字段，不生成复杂 query language

## TDD / ATDD 策略

- `T1_schema`：contract schema
- `T2_module_interaction`：页面与 agent tool 消费统一接口
- `T4_release_rehearsal`：AI 主题拆分后多轮 query-first tool 调用验证
