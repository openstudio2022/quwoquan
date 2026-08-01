# L3 Story：搜索存储拓扑与弹性 (`search-storage-topology-and-elasticity`)

> 所属能力：[`search-provider-routing-and-storage-topology`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望云侧搜索读写分离、多读切片弹性与 search-service + ES 落地验收；含 stackctl gamma 端到端冒烟与三项长稳缺口，从而找到可理解并可继续操作的结果。

## 2. 范围与非目标

### In Scope

- 业务写模型与搜索读模型分离；读模型派生、可重建/回放。
- 各域 indexer 灌入统一 ES 索引 quwoquan_objects；多读切片按 objectType/query class 弹性。
- search-service + ES 端到端：stackctl package/up/health/verify + 网关 /search 冒烟。

### Out of Scope

- 业务主存储向 ES 迁移。
- 向量/语义召回在最高 QPS suggest 路径默认开启。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 读写分离 + 多读切片灌数（各域 indexer → quwoquan_objects，ES 主 + native 回退）

- 搜索读请求只走 metadata 只读 API + 注入 CloudRequestHeaders 审计；多读切片按 objectType 独立弹性。

<a id="req-002"></a>
### REQ-002 search-service + ES 端到端冒烟（stackctl gamma：package/up/health/verify + /search 200 + feedback 202）

- 搜索 api_integration 必须通过真实 search-service、Elasticsearch 与网关链路证明 `/search` 返回 200、`/search/feedback` 返回 202，并把运行证据写入可删除的 `.qwq_output`。

<a id="req-003"></a>
### REQ-003 真集群高并发容量、稳定性与可重复性准出

- 真集群必须在声明容量下保持长稳运行与结果可重复；压测证据只保存在运行产物中。

<a id="req-004"></a>
### REQ-004 搜索词热力、相关搜索词与推荐 Feed 排序闭环

- 搜索 → 推荐特征 → Feed 排序消费链路有 local_contract/api_integration 证据；运营报告包含请求量、错误率、degrade、cache、AB bucket、特征 freshness。

<a id="req-005"></a>
### REQ-005 搜索派生读库保持可替换边界

- 搜索派生读库只能在 canonical contract 后替换，不得改变业务写模型或调用方对象语义。
- 统一搜索读库采用**专用 ES/OpenSearch 集群**，索引 `quwoquan_objects`，作为派生读模型。
- 新建**独立可部署 `search-service`** 承载统一 `POST /search`（`mode=suggest|result`）与 `POST /search/feedback`，单趟 `runtime/search.Retrieve` 跨类型排序。
- 各域（content/entity/circle/user/integration）经统一 indexer 灌入同一 ES 索引；原各域 `/.../search` 只读路由收敛为 indexer 数据源/内部回退。
- 收口统一 `search-service` + ES 集群的搜索读路径护栏、metadata 对齐、请求头审计与验证证据。
- App 主搜索路径走统一 `POST /search`（search-service + ES）；私有对象（`chat.*`）仍 `local_only`，绝不上云。
- 搜索读请求不得长期依赖扫描业务主集合。
- **各域灌数**：`content.post / entity.homepage / circle.circle / circle.group / user.profile` 经各域写时 `Projector` + `Backfill` 灌入统一 ES 索引 `quwoquan_objects`；第一方地点对象 `location.place` 由 content 域 `place_snapshots` 派生，复用 geo 维度并与 `entity.homepage` 互斥单源。搜索读模型可重建，各域写模型仍是唯一写真相源。
- **根 Go module 可复现**：search-service 与其余服务统一消费 `quwoquan_service/go.mod` 与 `quwoquan_service/go.sum`，独立二进制从根 package path 构建；单模块门禁阻断嵌套 module。
- 该报告固定写入 `r_s06_s1_closed_by_local_gamma=false`：local 只能证明方法学、单节点稳定性、基本背压/退化和重复查询不跳变，不能关闭真集群 measured 容量阻断。

## 4. 契约引用

- canonical：`contracts/metadata/_shared/search_objects.yaml`
- canonical：`contracts/metadata/_shared/search_contract.yaml`
- canonical：`quwoquan_service/services/search-service/observability/slo/search_slo.yaml`
- canonical：`quwoquan_service/services/search-service/contracts/search/search_request_fact/storage.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/redis_keyspace.yaml`
- canonical：`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/feature_registry.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 读写分离 + 多读切片灌数（各域 indexer → quwoquan_objects，ES 主 + native 回退）

- GIVEN 各域写时 Projector + Backfill 已就绪；search-service 装配 FallbackBackend(Primary=ES, Fallback=native)。
- WHEN 各域发布/更新/下线事件触发写时投影，或 backfill 全量重建灌入 quwoquan_objects。
- THEN content.post/entity.homepage/circle.circle/circle.group/user.profile + location.place 进统一索引，读路径零扫描业务主集合。
- THEN ES 故障整体降级 native，不阻塞主写/读路径；读模型可重建/回放。

<a id="gwt-002"></a>
### GWT-002 search-service + ES 端到端冒烟（stackctl gamma：package/up/health/verify + /search 200 + feedback 202）

- GIVEN local-gamma 已通过 stackctl 实例化 search-service（容器 search-service:18095，ES quwoquan_objects）。
- WHEN stackctl package --env gamma --include-services
- AND up --env gamma --skip-app（含 backfill）
- AND health --target gamma-local --scope full
- AND verify --env gamma --kind all --profile release。
- WHEN 经 Caddy 网关 POST /search 与 POST /search/feedback。
- THEN up 阶段 quwoquan_objects backfill 完成（total/indexed），places 投影完成
- AND health 全 healthy（search-service -> 200）
- AND verify 全 checks passed。
- THEN /search 返回 200，信封含 requestId/experimentBucket 与 hit 级 rankReasons/rankPosition；/search/feedback 返回 202 accepted。

<a id="gwt-003"></a>
### GWT-003 真集群高并发容量、稳定性与可重复性准出

- GIVEN search_slo.yaml#load_model 已定义 suggest/result/feedback/indexing 的 baseline/peak/spike 目标。
- GIVEN search-service 已具备 in-flight 背压、timeout、热点 relatedTerms cache、ES stable sort/tie-break 与 AB sticky。
- WHEN 在 prod-sim 或原生 ES/OpenSearch 真集群执行 warm/cold cache、热点/长尾、混合读写、backfill 并发、ES restart、Redis delay、突刺与长稳压测。
- WHEN 在多副本环境对同 viewer/session/query/filter 连续重复查询，覆盖 refresh、replica 切换与 cold/warm cache。
- THEN 回填 measured RPS/P95/P99、错误率、degrade rate、cache hit、ES heap/GC/threadpool queue、Redis lag、index freshness、饱和点与扩容阈值。
- THEN TopN objectType+objectId 序列在同一派生读模型快照与实验分桶下不跳变；合法变化可由真实索引发布摘要与请求归因解释。
- THEN 未达 SLO 自动 NO-GO，不得用 local-gamma 单节点结果替代。

<a id="gwt-004"></a>
### GWT-004 搜索词热力、相关搜索词与推荐 Feed 排序闭环

- GIVEN /search query log、/search/feedback、queryheat、Redis Stream、content-service consumer、FeatureStore 与 RuleScorer 已装配。
- WHEN 用户搜索并点击结果，search-service 记录 query/feedback，queryheat 生成 relatedTerms/termHeat，搜索信号发布到 Redis，content-service 消费并写入 rm_recommend_feature。
- THEN 搜索结果页排序可消费 termHeat 并输出 rankReasons/experimentBucket。
- THEN 推荐 Feed scorer 可读取 searchTermAffinity/searchTermHeat/searchTopObjectAffinity 并影响候选得分。
- THEN AB bucket 可按 control/term_heat 查询；线上收益显著性作为发布后观察项。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真集群高并发容量、稳定性与可重复性准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少真集群容量、长稳与重复性实测时，搜索服务不能获得生产准出。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
