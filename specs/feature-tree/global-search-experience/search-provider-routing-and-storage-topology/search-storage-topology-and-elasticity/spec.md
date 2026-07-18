# L3 Scenario: search-storage-topology-and-elasticity

## 节点定位

- `L1_domain_service`: `global-search-experience`
- `L2_business_capability`: `search-provider-routing-and-storage-topology`
- `L3_story`: `search-storage-topology-and-elasticity`

## 背景与动机

统一搜索最终能否扛住增长，取决于云侧搜索读路径是否具备独立扩展能力。本 Scenario 用来冻结读写分离、多读切片和未来统一读库的边界。

## 功能范围

- 冻结业务写模型与搜索读模型分离。
- 冻结多读切片与每切片独立弹性。
- 冻结缓存、限流、熔断与部分降级的基础原则。
- 冻结未来统一高性能搜索读库的替换边界。

## Out of Scope

- 业务主存储向 ES 迁移（ES 仅作派生搜索读库）。
- 向量/语义召回在最高 QPS 的 suggest 路径默认开启（hybrid kNN 为可选升级）。

## 2026-06-15 架构决定（取代下文阶段二边界）

本节为最新冻结决定，凡与下文“本期不新增统一 `/search`”“不指定搜索引擎产品”冲突处一律以本节为准：

- 统一搜索读库本期落地为**专用 ES/OpenSearch 集群**，索引 `quwoquan_objects`，作为派生读模型。
- 新建**独立可部署 `search-service`** 承载统一 `POST /search`（`mode=suggest|result`）与 `POST /search/feedback`，单趟 `runtime/search.Retrieve` 跨类型排序。
- 召回后端 **ES 主 + native 透明回退**（`FallbackBackend`）；ES 故障整体降级 native。
- 各域（content/entity/circle/user/integration）经统一 indexer 灌入同一 ES 索引；原各域 `/.../search` 只读路由收敛为 indexer 数据源/内部回退。
- 读模型仍是派生数据，可重建/回放；多读切片按 objectType / query class 拆分仍适用于 ES 分片与副本弹性。

## 本阶段交付边界

- 收口统一 `search-service` + ES 集群的搜索读路径护栏、metadata 对齐、请求头审计与验证证据。
- 各域作为 indexer 数据源/内部回退的只读路径（保留，不再是 App 主路径）：
  - `content.post`：`GET /content/posts/search`
  - `circle.circle`：`GET /circles/search`
  - `circle.group`：`GET /circles/{circleId}/groups/search`
  - `entity.homepage`：`GET /homepages/search`、`GET /homepages/{homepageId}/shell`、`GET /homepages/{homepageId}/review-summary`、`GET /homepages/{homepageId}/related-groups`
  - `integration.location_poi`：`GET /integration/location/search`、`GET /integration/location/nearby`
- App 主搜索路径走统一 `POST /search`（search-service + ES）；私有对象（`chat.*`）仍 `local_only`，绝不上云。

## 约束

- 搜索读请求不得长期依赖扫描业务主集合。
- 读模型是派生数据，不承担业务主真相源。
- 多读切片按 objectType 或 query class 拆分，支持独立扩缩容。

## 读路径护栏

1. 所有搜索读请求必须走 metadata 定义的只读 API 路径，端侧 Repository 只能通过 codegen path builder 调用。
2. 所有搜索读请求必须注入 `CloudRequestHeaders` 生成的 page / surface / operation header，用于审计、限流与问题定位。
3. `content / circle / homepage / location` 的搜索结果只允许返回搜索视图或 read shell，不允许把写模型 DTO 当作长期搜索读模型契约。
4. 单个 reader slice 故障时允许按 objectType fail-closed，并通过 typed degrade signal 暴露给统一 `SearchRepository` 与 assistant。
5. assistant `search` tool 复用同一组只读 provider，资源边界由 query-first schema、allowlist 与读侧 header 审计共同约束。

## 2026-06-16 落地证据（纳入正式规格）

以下已落地事实纳入本 Scenario 正式规格（证据见 `docs/outstanding_risks_backlog.md`）：

- **R-S05a~e 各域灌数**：`content.post / entity.homepage / circle.circle / circle.group / user.profile` 经各域写时 `Projector` + `Backfill` 灌入统一 ES 索引 `quwoquan_objects`；新增第一方地点对象 `location.place`（content 域 `place_snapshots` 派生读模型，复用 geo 维度，与 `entity.homepage` 互斥单源）。读模型仍是派生数据，posts / 各域写模型为唯一写真相源。
- **R-S06 App 接线**：`RemoteSearchRepository` 走 `CloudHttpClient` + codegen path 调 `/search`，按 `appDataSourceModeProvider` 切换；读路径护栏（metadata path + header 审计）成立。
- **R-S07 反馈/热力/排序**：`feedbackstore`(Mongo, TTL) + `queryheat` 派生 `rm_search_term_heat`(TTL 86400) + 排序透明化信封；多读切片原则在 ES 分片/副本弹性上落地。
- **R-S07-5 推荐信号注入**：search → Redis Stream `events.search.recommendation_signals` → content-service consumer → `rm_recommend_feature`（代码 local_contract 通过）。
- **R-S06-S 端到端冒烟**：stackctl 实例化 search-service 进 local-gamma（ES-enabled，`quwoquan_objects` backfill），网关 `/search` 200、`/search/feedback` 202，证据已迁移 canonical run evidence（`search_smoke_report.json`）与 `QWQ_OUTPUT_ROOT/env/gamma/runs/**`。
- **R-S06-S-3 根 Go module 可复现**：search-service 与其余服务统一消费 `quwoquan_service/go.mod/go.sum`，独立二进制从根 package path 构建；`verify_go_single_module.py` 阻断嵌套 module，搜索构建与完整测试已绿。

## 未完成风险（弹性/长稳缺口，登记为后续 /dev）

1. **真集群性能差异（R-S06-S-1 / WP-E）**：local-gamma 在 Apple Silicon/Colima 下用 `linux/amd64` 模拟 ES，冷启动与 `_bulk` 性能不代表真实 ES/OpenSearch 集群；真集群需用原生镜像/托管集群重新校准 batch 与启动 SLA。
2. **写时投影长稳（R-S06-S-2 / WP-E）**：写时投影器常驻增量同步、ES 重启后索引一致性与补偿恢复尚未做长稳 api_integration。

### 未完成项任务化（backlog 对齐，不另建第二清单）

| Backlog | 任务 | 完成条件 | 验收证据 |
|---|---|---|---|
| R-S06-S-1 | 真集群/prod-sim 原生 ES/OpenSearch 容量校准 | 回填 measured RPS/P95/P99、饱和点、最大稳定 RPS、推荐 shard/replica/节点规格、refresh/bulk/circuit 阈值；多副本 `preference` 验证 TopN 不跳变 | `QWQ_OUTPUT_ROOT/env/repo/runs/search-load/**` 真集群报告、`search_slo.yaml` 回填、`stackctl verify --env prod --kind all --tier all` |
| R-S06-S-2 | 写时增量 + backfill 幂等长稳 | content/entity/circle/user/location publish/update/unpublish 触发索引收敛；backfill rerun count/hash 不漂移；ES restart 后恢复 SLA 达标 | api_integration soak 报告、`search_index_restart_recovery_t3.json` 扩展、projector/backfill tests |

## 容量校准（capacity calibration / R-S06-S-1）

> 真相源：本节方法学 + `configs/observability/search_slo.yaml#load_model`（目标值）+ `QWQ_OUTPUT_ROOT/env/repo/runs/search-load/**`（压测实测）+ `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/*search*`（local 证据）。
> 业界搜索容量共识（吸收 Elastic/OpenSearch 官方实践），用于真集群/prod-sim 校准；local-gamma 单节点模拟不能代表生产，measured 值必须在真集群回填。

### 校准方法学

1. 固定 `load_model` 四类流量（suggest/result/feedback/indexing），按 baseline→peak→spike 三档加压，找到单实例与单 ES 数据节点的饱和点（CPU、search threadpool queue、heap、GC、磁盘 IO）。
2. 反推最低商用容量：`实例数 × 单实例 RPS ≥ peak RPS`，`ES 数据节点数 × 单节点查询吞吐 ≥ peak result RPS`，并留 ≥30% 余量。
3. 扩容触发阈值：search threadpool queue 持续 > 阈值、heap > 75%、result P95 接近 SLO、circuit open rate 上升任一即扩。

### ES/OpenSearch 拓扑推荐（按数据规模）

| 维度 | 当前（`quwoquan_objects` ≈ 675 docs，单节点 local） | 10× / 商用初期 | 业界依据 |
|---|---|---|---|
| primary shards | 1（数据量远小于单 shard 10–50GB 上限，避免 oversharding） | 1–2（单 shard 控制在 10–50GB） | 多数搜索命中多 shard、单 shard 单 CPU thread；过多小 shard 耗尽 search threadpool |
| replicas | local 单节点 = 0 更佳（现 =1 致永久 yellow，replica unassigned）；生产 ≥1 | ≥1（HA + 读吞吐） | 副本提升并发读吞吐与可用性，但过多副本增缓存/资源压力 |
| data nodes | 1（local） | ≥2（承载副本 + 读吞吐） | 副本需 ≥2 节点才能分配 |
| filesystem cache | — | ≥ 一半节点内存留给 OS page cache，SSD | filesystem cache 是搜索性能核心，勿把 heap 调到过大 |
| heap | — | ≤ 31GB 且 ≤ 物理内存一半 | 堆与 page cache 平衡 |
| refresh_interval | 默认 1s | 可见性允许时调高到 30s；backfill 期临时延长 + 降副本，完成后恢复 | 提高 refresh 显著提升写吞吐 |
| bulk batch | backfill ~1000 docs/批 | 按节点压测校准 | 过大 bulk 触发 429/排队 |
| query cost guard | allowlist、limit、timeout、track_total_hits 受控 | 同左 + 热点 query cache | 禁默认昂贵 fuzziness/深分页/脚本排序/大聚合 |

### 查询与索引成本硬护栏

| 护栏 | 商用要求 | 测试/观测 |
|---|---|---|
| Query DSL | 只允许 metadata allowlist 的 objectTypes/filter/limit；`track_total_hits=false`；禁止无界 wildcard、脚本排序、深分页、大聚合、默认昂贵 fuzziness | query_builder 单测 + runtime/search contract |
| Timeout / backpressure | search-service、ES client、Mongo queryheat、Redis publish 都必须有 timeout；in-flight 满返回受控 503/429 | InflightLimiter 单测 + metrics `search_retrieve_load_shed_total/search_retrieve_inflight` |
| Cache | App suggest cache、relatedTerms cache、热点 query cache、ES request/query cache、filesystem cache 分层；cache hit 可观测 | `search_retrieve_related_terms_cache_total`、load benchmark warm/cold 对比 |
| Bulk / refresh | backfill 期 bulk batch、replica、refresh_interval 可调；完成后恢复生产设置 | backfill 报告 + index freshness 指标 |
| Redis signal | publish best-effort，不反压主搜索；consumer lag broker-side 可查询 | Redis stream group lag / DLQ / `search_signal_t3_report.json` |

### 本轮 local 校准证据（不代表生产）

- 单节点 ES `quwoquan_objects`：1 shard / 1 replica → cluster 永久 **yellow**（replica unassigned，active_shards 50%）；搜索读不受影响。生产应 ≥2 data node + replicas≥1 转 green，或单节点部署显式 replicas=0。
- ES 重启恢复 ≈108s（amd64 模拟），索引文档数持久（675→675），搜索恢复一致 TopN（见已迁移 canonical run evidence：`search_index_restart_recovery_t3.json`）。
- `python3 quwoquan_service/scripts/search/verify_search_local_gamma_capacity.py` 是 R-S06-S-1 的 **local-gamma 可验证入口**：聚合 stackctl gamma verify、ES health/index/shards/threadpool、小型 warm/cold/mixed/feedback 并发压测、单节点 repeatability、故障/回滚证据存在性，报告为已迁移 canonical run evidence（`search_r_s06_s1_local_gamma_report.json`）。
- 该报告固定写入 `r_s06_s1_closed_by_local_gamma=false`：local 只能证明方法学、单节点稳定性、基本背压/退化和重复查询不跳变，不能关闭真集群 measured 容量阻断。

### 未闭合（R-S06-S-1 BLOCK，需真集群）

- 真集群/prod-sim 原生（非 Apple Silicon amd64 模拟）ES/OpenSearch 上回填 `load_model` 的 measured RPS/P95/P99、饱和点、最大稳定 RPS、推荐 shard/replica/节点规格、refresh/bulk 校准与 fallback/circuit 触发阈值。本环境无真集群，属发布前阻断项。

## 搜索结果可重复性（同一搜索不跳变）

> 商用品质要求：相同 viewer/session/query/filter 在 warm/cold cache、refresh、副本切换后 TopN 不无故跳变；只有底层数据、`rankingVersion`、`indexVersion` 或实验策略变化才允许变化。

| 机制 | 实现 | 证据 |
|---|---|---|
| 稳定全序 tie-break | `runtime/search.SortHitsStable`：`Score desc → Title asc → Target asc → ObjectID asc`（recall 合并与 search-service `term_heat` 重排共用同一排序真相源，无第二套排序） | `TestSortHitsStableTotalOrderUnderPermutation` |
| ES 候选截断确定性 | `es/query_builder` Build 显式 `sort:[_score desc, objectId asc]` + `track_total_hits:false`，使 top-`size` 截断在多副本/段合并/refresh 后确定 | `query_builder` 单测 + 现有 DSL 断言 |
| AB bucket 粘性 | `subjectKeyFor` 仅用 viewerId/sessionId；匿名无 session 返回空 → `Assign` 强制 `control`，绝不用 per-request id 参与分桶（否则同一 query 每次重掷实验臂） | `TestAssignEmptySubjectIsControlAndSticky`、`TestSubjectKeyForStableIdentityOnly` |
| 重复查询 golden diff | 同 viewer/session/query 连续 25 次，TopN keys + bucket 0 跳变 | 已迁移 canonical run evidence（`search_repeatability_golden_diff.json`） |

**未闭合（scoped 到真集群，非本环境 debt）**：多副本下跨副本 `_score` 漂移（分布式 df 统计差异）需 ES `preference`（按 viewer/session/query 稳定派生，路由到同一副本）兜底；该 preference 需通过 Searcher 透传查询参数实现。local 单节点无副本（replicas unassigned，永久 yellow）无法验证 preference 收益，故列入 R-S06-S-1 真集群里程碑实现并验收，避免在无副本环境提前接入半成品。

## 搜索词热力 / 推荐排序闭环

> 商用目标：用户搜索词不仅影响搜索结果页排序，也能进入推荐 Feed 排序，且具备 AB、可观测与回滚边界。

| 环节 | 合同 | 证据 |
|---|---|---|
| Query log | `/search` 成功后 best-effort 记录 query、viewer/session、requestId、experimentBucket、top hits | search-service handler / feedbackstore tests |
| Feedback | `/search/feedback` 记录点击、曝光、反馈，202 accepted，不阻塞 result | search-service contract test |
| Queryheat | `rm_search_term_heat` TTL 86400，基于次数、点击、共现、时间衰减计算 relatedTerms 与 term heat | queryheat tests + storage TTL contract |
| Result ranking | term-heat 由 RankingDecorator 注入，输出 rankReasons/rankPosition/rankingVersion/experimentBucket | application ranking tests |
| Recommendation | Redis Stream → content-service consumer → `rm_recommend_feature.searchTermAffinity` → FeatureStore → RuleScorer | `search_signal_consumer_test.go`、`runtime/recommendation` tests、已迁移 canonical run evidence（`search_signal_t3_report.json`） |
| AB / Ops | control/term_heat bucket 可查询；线上收益显著性是发布后观察项，不影响稳定性准出 | `QWQ_OUTPUT_ROOT/env/repo/runs/search-obs/search_observability_ab_recommendation_report.md` |

## 验收重点

1. 是否明确了读写分离。
2. 是否明确了多读切片和独立弹性。
3. 是否把未来统一读库限制为 read model 替换，而非主存储迁移承诺。
4. 是否为现有 `content / circle / homepage / location` 读路径补齐了 metadata 对齐与 header 审计证据。
5. 是否把 R-S05~R-S07-5 / R-S06-S 已落地证据纳入正式规格，并把真集群性能、写时投影长稳、go module 可复现三项缺口登记为后续 /dev。
