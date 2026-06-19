# 搜索端到端热路径分段 profiling（local-gamma）

> 方法：逐段实测 + 代码确认同步/异步边界。被测 local-gamma（单节点 ES）。
> 目的：定位用户感知延迟归属，区分“在路径上”与“异步侧路”，并指明高并发瓶颈段。

## 用户请求路径（result 云侧检索）

```
App result 请求 → Caddy 网关 → search-service(parse+retrieve+rerank+relatedTerms) → ES
                                          ├─(异步) query log → Mongo
                                          └─(异步, best-effort) Redis Stream → content-service → rm_recommend_feature → Feed
```

## 分段实测（warm，单连接，顺序）

| 段 | 实测 | 证据 | 在用户路径? |
|---|---|---|---|
| App suggest（本地） | 不经网络 | 本地 cache/store，debounce；代码：suggest 本地优先 | 是（但非云侧） |
| ES 查询执行 | `took` 8–24ms（warm），首查 244ms（cold） | 直查 `:19430 _search`；`_stats` 平均 65ms（含 cold/重词） | 是（主成本段） |
| search-service 处理开销 | 总 ~30ms − ES ~10ms ≈ 10–20ms | 直连 `:19280` warm 28–35ms | 是 |
| 网关（Caddy reverse_proxy） | ~1–5ms（可忽略） | `:19000` warm 30–37ms ≈ 直连 | 是 |
| **用户感知（cloud, warm）** | **~30ms 直连 / ~30–37ms 经网关** | — | — |
| query log 写 Mongo | 不计入 | 代码：detached goroutine + 5s timeout（`logQueryAsync`） | 否（异步） |
| relatedTerms 读 Mongo | 含在 search-service 处理段内 | `decorator.Decorate` 同步调用 → **在路径上** | 是（已加缓存卸载） |
| Redis 信号发布 | 不计入 | best-effort publish | 否（异步） |
| content-service 消费 / Feed 特征 | 不计入 | Stream 消费异步 | 否（异步） |

## 结论

1. **warm 单飞延迟健康（~30ms）**：ES 执行 + 轻量 rerank + 网关转发，端到端 ~30ms，网关开销可忽略。
2. **唯一高并发瓶颈是单节点 ES**（见 `search_load_analysis.md`）：并发上升后 ES 排队 → 命中 ES 请求超时（~800ms 边界）→ 503 `upstream_unavailable`。这是单节点环境上限，需真集群多节点 + 副本扩读吞吐（R-S06-S-1）。
3. **relatedTerms 的 Mongo 读在用户路径上**：每次 result 检索都同步读一次 `rm_search_term_heat`。本轮新增 `CachedTermHeat`（TTL 热点缓存）把热点 query 的该读卸载为“每键每 TTL 一次”，降低 Mongo 在高并发下的放大；容器重建后可由 `search_retrieve_related_terms_cache_total{result=hit}` 观测命中率。
4. **异步侧路不污染用户延迟**：query log（detached + 超时）、Redis 信号发布（best-effort）、content-service 消费、Feed 特征读取均在用户路径之外，慢/失败不拖垮搜索结果——符合背压优先设计。

## 高并发优化落点（按收益）

| 优先级 | 落点 | 状态 |
|---|---|---|
| P0 | 多节点 ES + 副本扩读吞吐（消除单点饱和） | 真集群待校准（R-S06-S-1） |
| P0 | in-flight 背压 shed（防止慢 ES 拖垮实例） | 已实现 `InflightLimiter`+中间件（单测绿） |
| P1 | relatedTerms 热点缓存（卸载 Mongo） | 已实现 `CachedTermHeat`（单测绿） |
| P1 | ES query 成本受控（size/timeout/track_total_hits、禁深分页/无界 wildcard） | query_builder 已受控；真集群压测复核 |
| P2 | 热点 query 结果级缓存 / ES request cache | 真集群校准命中率后再开 |
```
