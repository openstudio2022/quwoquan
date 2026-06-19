# 搜索高并发压测分析（local-gamma 基线）

> 工具：`quwoquan_service/scripts/search/search_load_benchmark.py`（stdlib-only，固定随机种子，可重复）。
> 目标值：`search_slo.yaml#load_model`。被测：local-gamma `search-service`（host `:19280`），**单节点 ES**。
> 重要：**local-gamma 单节点 ES 不代表生产容量**；本报告是工具落地 + 瓶颈定位 + 基线，不是商用 GO 依据。
> 商用 GO 必须在真集群/prod-sim 多节点 ES 复跑（R-S06-S-1 仍为发布阻断）。

## 运行档位

| 档位 | 并发 | 每场景时长 | 报告 |
|---|---|---|---|
| baseline | 6 | 6s | `search_load_all_20260616T082933Z.json` |
| mid | 30 | 8s | `search_load_all_20260616T082705Z.json`（分类细化前） |
| saturation | 40 | 6s | `search_load_all_20260616T083047Z.json` |

## 关键结果

### baseline（并发 6，非饱和）

| 场景 | RPS | ok_p95(ms) | error_rate | upstream_unavailable | 判定 |
|---|---|---|---|---|---|
| result_cold | 39.8 | 250.6 | 0.000 | 0 | GO |
| mixed | 46.2 | 261.0 | 0.000 | 0 | GO |
| result_warm | 33.0 | 443.3 | 0.030 | 6 | NO-GO |
| suggest_warm | 32.2 | 270.8 | 0.062 | 12 | NO-GO |
| suggest_cold | 35.8 | 248.4 | 0.014 | 3 | NO-GO |
| feedback | 1187 | 9.6 | 0.000 | 0（rate_limited 1369） | GO |

### saturation（并发 40）

| 场景 | RPS | ok_p95(ms) | error_rate | upstream_unavailable | rate_limited | 判定 |
|---|---|---|---|---|---|---|
| result_warm | 59.7 | 770.7 | 0.687 | 246 | 0 | NO-GO |
| result_cold | 69.0 | 795.6 | 0.263 | 109 | 0 | NO-GO |
| suggest_warm | 77.3 | 759.3 | 0.304 | 141 | 0 | NO-GO |
| suggest_cold | 56.2 | 755.7 | 0.742 | 250 | 0 | NO-GO |
| mixed | 87.5 | 787.6 | 0.114 | 60 | 0 | NO-GO |
| feedback | 2919.7 | 29.4 | 0.000 | 0 | 11518 | GO |

## 瓶颈定位

1. **单节点 ES 是 result/suggest 的硬瓶颈**：并发从 6→40，ES-bound 查询的 `upstream_unavailable`（503，ES 检索失败/超时）从个位数飙到 26%–74%，且成功请求 p95 被钉在 ~760–800ms（ES 请求超时边界）。这是单节点 ES 在并发随机读 + 评分下的饱和，不是 search-service 逻辑缺陷。
2. **feedback 路径不经 ES，可扩到全局限流上限**：feedback p95 ≤30ms，吞吐被 `RateLimiter(1000/s)` 主动 shed（429）控制在上限，无 ES 压力。证明非 ES 路径与全局限流背压按预期工作。
3. **热点 query 比长尾更重**：`成都/火锅` 命中大量文档需评分，比长尾 cold query 更慢更易触发 ES 超时——与业界“高频词更贵”一致，正式 result 必须靠缓存 + 受控 query 成本兜底。
4. **search-service 自身未成为瓶颈**：本轮被测为旧构建（in-flight 限流/相关词缓存尚未进容器）；瓶颈先在 ES 暴露。新背压代码（`InflightLimiter`、`CachedTermHeat`）已由单测证明行为，容器重建后复跑可观测 `backpressure_shed` 与缓存命中。

## 结论与发布判定

- **local-gamma 单节点 ES 下，result/suggest 高并发 NO-GO**：这是预期的环境上限（单节点、amd64 模拟、replicas=1）。
- **不得据此宣称商用高并发达成**。商用 GO 的前置条件：在真集群/prod-sim 多节点 ES（按 `search-storage-topology-and-elasticity/spec.md#容量校准` 的 shard/replica/page-cache/refresh 推荐）复跑本工具，result peak 档满足 `server p95 ≤ 400ms、error ≤ 0.005、degrade ≤ 0.05`，并回填 measured 容量阈值，关闭 R-S06-S-1。
- **可重复性**：固定种子 + 有限 user/session 集合保证负载序列稳定；工具区分 ok / rate_limited / backpressure_shed / upstream_unavailable，便于真集群复跑对比。

## 复跑命令

```bash
# 单场景
python3 quwoquan_service/scripts/search/search_load_benchmark.py \
  --base-url http://127.0.0.1:19280 --scenario result_warm --duration-sec 30 --concurrency 50
# 全场景
python3 quwoquan_service/scripts/search/search_load_benchmark.py --scenario all --duration-sec 20 --concurrency 40
```
