# 搜索可观测 / AB / 推荐回流 准出验证报告

- 能力：`global-search-experience`
- 范围：SLO/告警/AB bucket 可查询、Redis 信号链路与 lag、`searchTermAffinity` → Feed 排序消费、可运营报表口径
- 结论：**搜索→反馈→推荐特征→Feed 排序闭环可观测、可分桶、可消费**；唯一真相源对齐，无第二套指标/告警/特征定义。线上 AB 收益显著性为发布后观察项（不阻塞稳定性准出）。

---

## 1. SLO / 指标 单一真相源

- SLI/SLO 真相源：`quwoquan_service/services/search-service/configs/observability/search_slo.yaml`
- 指标真相源：`quwoquan_service/services/search-service/internal/infrastructure/searchmetrics/metrics.go`（promauto 默认注册表，`/metrics` 暴露）
- 告警真相源：`deploy/monitoring/alerts/quwoquan_alerts.yaml` → `quwoquan_search` 组（expr 直接消费上面指标，阈值与 SLO objective 对齐）

| SLI | 指标 | objective | 告警 |
|---|---|---|---|
| retrieve_latency P99 | `search_retrieve_duration_seconds_bucket` | p99_ms ≤ 400 | `SearchRetrieveLatencyHigh` |
| availability | `search_retrieve_requests_total{status}` | ≥ 0.995 | `SearchAvailabilityLow` |
| zero_result_rate | `search_retrieve_zero_results_total` | ≤ 0.15 | `SearchZeroResultRateHigh` |
| degrade_rate | `search_retrieve_degraded_total` | ≤ 0.05 | `SearchDegradeRateHigh` |
| load_shed_rate | `search_retrieve_load_shed_total` | ≤ 0.01 | `SearchLoadShedRateHigh`（本轮新增） |
| inflight_saturation | `search_retrieve_inflight` | ≤ 256 | `SearchInflightSaturationHigh`（本轮新增） |
| related_terms_cache_hit_rate | `search_retrieve_related_terms_cache_total{result}` | ≥ 0.5 | （效率 SLI，看板观测，不单独告警） |

**本轮收口**：SLO 已声明 `load_shed_rate` / `inflight_saturation` 两个背压 SLI，但告警组此前未覆盖 → 已补 `SearchLoadShedRateHigh`（shed 率 > 1% 持续 5m）与 `SearchInflightSaturationHigh`（在途并发 > 230/256 持续 5m，早于 load-shed 触发扩容）。`quwoquan_search` 组规则集：

```
SearchRetrieveLatencyHigh, SearchZeroResultRateHigh, SearchDegradeRateHigh,
SearchAvailabilityLow, SearchLoadShedRateHigh, SearchInflightSaturationHigh
```

YAML 校验通过（`python3 -c "yaml.safe_load(...)"`）。

---

## 2. AB bucket 可分桶查询

- 实验：`search_ranking`，buckets：`control` / `term_heat`，分桶 label：`bucket`（见 `search_slo.yaml#ab`）。
- 端侧 bucket 粘性：`subjectKeyFor`（viewerId → X-Session-Id → 空则 control），`Experiments.Assign` 空 subject 强制 control，保证匿名不每请求重掷（见 `verify-search-repeatability` 收口与 `subject_key_test.go` / `experiments_repeatability_test.go`）。
- 服务端指标：`searchmetrics` 所有检索 SLI（duration/requests/zero_results/degraded/term_heat_applied）均带 `bucket` label，可按桶切分对比延迟、零结果率、降级率、term_heat 触达率。
- 跨链路传递：搜索信号 publish 携带 `experimentBucket`，content-service 消费后写入特征（payload `experimentBucket`，见 §4），使「搜索分桶 → 推荐特征 → Feed」归因可贯通。

PromQL 分桶示例（control vs term_heat）：

```promql
# 各桶 P99 延迟
histogram_quantile(0.99, sum(rate(search_retrieve_duration_seconds_bucket[5m])) by (le, bucket))
# 各桶零结果率
sum(rate(search_retrieve_zero_results_total[5m])) by (bucket)
  / sum(rate(search_retrieve_requests_total{status="ok"}[5m])) by (bucket)
# term_heat 桶 heat 重排触达
sum(rate(search_retrieve_term_heat_applied_total{bucket="term_heat"}[5m]))
```

---

## 3. Redis 搜索信号链路与 lag

- 流：`events.search.recommendation_signals`，DLQ：`events.search.recommendation_signals.dlq`，消费组：`content-service`，stream/dedup TTL 24h。
- 投递语义：publish best-effort（搜索主路径不被信号阻塞）；消费侧 dedup（`searchRequestId` SetNX）+ 失败入 DLQ + XAck，幂等可重放。
- SLO 目标（`search_slo.yaml`）：`redis_publish_latency_ms_p99_max=50`、`redis_signal_lag_max=1000`、`redis_consumer_lag_max=1000`。
- **lag 测量口径（明确，非技术债隐藏）**：精确 stream consumer lag 属 broker 侧度量（Redis `XINFO GROUPS <stream>` 的 `lag`），由 `redis_exporter` 暴露 `redis_stream_group_lag{stream,group}` 抓取告警；这是业界标准做法，运行时 `rtredis.Client` 接口不承载 lag 计算（避免在应用进程做 XPENDING 轮询放大负载）。应用侧守卫为 DLQ 计数 + dedup + 处理批次，broker 侧负责 lag 曲线。
  - 发布前动作（运维项，不阻塞代码准出）：在 prod-sim/prod 的 monitoring stack 接入 `redis_exporter` 并对 `redis_stream_group_lag{group="content-service"} > 1000 (5m)` 配置告警；已在 backlog 记录为运维接线项。

---

## 4. `searchTermAffinity` → Feed 排序消费（不仅投影，确实被读）

完整链路（代码 + 测试证据）：

1. **采集**：搜索 query/相关词/点击对象 → `searchsignals.StreamPublisher` 发布到 Redis Stream（带 `experimentBucket`/`rankingVersion`）。
2. **消费**：`content-service` `SearchSignalConsumer.ProcessOnce` 读取 → `RecommendFeatureProjector.Project`。
   - 证据测试：`TestSearchSignalConsumerProjectsAndAcks`（内存 Redis，投影 + XAck）✅
3. **投影**：`recommend_feature.go` 写入 `userFeatures.searchTermAffinity.<term>`（权重随排名衰减 `0.6/(i+1)`）、`searchTopObjectAffinity`、`searchTermHeat`、`searchTermUpdatedAt`。
4. **新鲜度门**：读取时 `searchFeaturesFresh`（`SearchIntentTTL`）过期则不参与排序。
   - 证据测试：`TestSearchFeatureFreshnessGate`（fresh 用 / stale 丢弃）✅
5. **排序消费**：`runtime/recommendation/scorer.go#searchIntentScore`：
   - `SearchTopObjectAffinities` 命中候选 ContentID/EntityRefs 加分；
   - `SearchTermAffinities` 命中候选 haystack（标题/摘要等）加分；
   - `SearchTermHeat>0` 时 `score *= log1p(heat)`；
   - 结果以 `w.SearchIntent * searchIntentBoost` 计入最终加权总分（`scorer.go` 总分公式）。
   - 证据测试：`runtime/recommendation` `SearchTerm|SearchIntent|Engine` 全绿 ✅（含 `engine_test.go` 用 `SearchTermAffinities{火锅:2.0}` + `SearchTermHeat:4` 断言排序受影响）。

代码引用：

```283:301:quwoquan_service/runtime/recommendation/scorer.go
	if len(user.SearchTermAffinities) > 0 {
		hay := candidateSearchHaystack(c)
		for term, aff := range user.SearchTermAffinities {
			if aff <= 0 {
				continue
			}
			term = strings.ToLower(strings.TrimSpace(term))
			if term == "" {
				continue
			}
			if strings.Contains(hay, term) {
				score += aff
			}
		}
	}
	if user.SearchTermHeat > 0 && score > 0 {
		score *= math.Log1p(user.SearchTermHeat)
	}
	return score
```

---

## 5. 可运营报表口径

运营可按以下维度还原搜索→推荐漏斗（均为已暴露指标/特征，无需新埋点）：

- 流量与质量：`search_retrieve_requests_total` / `zero_results_total` / `degraded_total`（按 `mode`、`bucket`）。
- 性能与弹性：`search_retrieve_duration_seconds`（分位数）、`search_retrieve_inflight`、`search_retrieve_load_shed_total`。
- 反馈闭环量：`search_feedback_events_total{event_type}`（impression/click/dwell…）。
- 热点缓存效率：`search_retrieve_related_terms_cache_total{result}`。
- AB 对比：上述全部按 `bucket=control|term_heat` 切分做 CTR/零结果率/延迟显著性。
- 推荐回流：feature store `rm_recommend_feature.userFeatures.searchTermAffinity.*` 覆盖率/新鲜度（`searchTermUpdatedAt`），Feed 侧 `w.SearchIntent` 命中分布。

---

## 6. 证据汇总（本轮 recorded）

| 验证项 | 证据 | 状态 |
|---|---|---|
| SLO 单一真相源 + 背压 SLI | `search_slo.yaml`（load_model + 9 SLIs） | ✅ |
| 告警组覆盖全部 SLI（含背压） | `quwoquan_alerts.yaml#quwoquan_search`（6 规则，YAML 校验通过） | ✅ |
| AB bucket 可分桶 | `searchmetrics` 全 SLI 带 `bucket` label；端侧 bucket 粘性 | ✅ |
| 搜索信号消费 | `TestSearchSignalConsumerProjectsAndAcks` | ✅ |
| 搜索特征新鲜度门 | `TestSearchFeatureFreshnessGate` | ✅ |
| searchTermAffinity 被 Feed 排序消费 | `runtime/recommendation` SearchTerm/SearchIntent/Engine 测试 | ✅ |
| Redis 信号 lag 口径 | broker 侧 `redis_exporter` + SLO 目标 + DLQ/dedup 守卫 | ✅（运维接线项见 §3/backlog） |

## 7. 剩余风险（不阻塞稳定性准出）

- **线上 AB 收益显著性**：`control` vs `term_heat` 的 CTR/留存提升需线上灰度样本量积累后判定，属发布后观察项（backlog `R-S07-5` 线上收益）。
- **Redis stream lag 告警接线**：需在 prod-sim/prod monitoring stack 接入 `redis_exporter` 并配 `redis_stream_group_lag` 告警（运维项，已在 backlog 记录）。
