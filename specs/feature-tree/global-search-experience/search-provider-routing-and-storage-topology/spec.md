# L2 Feature: search-provider-routing-and-storage-topology

## 节点定位

- `L1_domain_service`: `global-search-experience`
- `L2_business_capability`: `search-provider-routing-and-storage-topology`

该节点负责冻结统一搜索 contract、对象 taxonomy、provider routing、fallback 规则、本地搜索生命周期与云侧搜索读模型弹性拓扑。它不直接定义用户可见页面，而是为 `cross-domain-search-journey` 与后续页面内搜索 / picker 搜索提供统一真相源。

## 背景与动机

现有全局搜索虽然已经有统一入口和 Journey，但仍缺少一层明确的搜索治理基线：

1. 页面层看到的是统一体验，底层却仍暴露多个分域方法名，长期会回到第二套接口语义。
2. 聊天对象、本地搜索、`circle.group` fallback 与远端对象之间缺少统一执行策略。
3. 云侧搜索如何承接高并发与成本控制没有冻结，容易继续退回“直接扫业务主集合”的临时实现。

## 子场景拆分

本 L2 冻结 7 个 `L3_story`：

| L3 | 职责 |
|---|---|
| `canonical-search-contract` | 统一 `search(request)`、`mode=suggest|result`、统一结果 envelope |
| `search-object-taxonomy-and-provider-registry` | searchable object taxonomy 与 provider registry |
| `search-execution-routing-policy` | `local_only / remote_only / hybrid_remote_fallback_local` 执行策略 |
| `circle-group-hybrid-fallback-contract` | `circle.group` 云优先 / 本地 fallback 合约 |
| `local-search-lifecycle-and-account-isolation` | 本地聊天搜索生命周期与子账号隔离 |
| `search-storage-topology-and-elasticity` | 云侧搜索读模型、读写分离、多读切片与弹性 |
| `search-risky-config-gray-release` | search-service 与写侧 ES/Redis 高风险配置的 release version、灰度、回滚与门禁 |

## 能力边界

本 L2 负责：

- 页面与业务层唯一 canonical 搜索接口。
- 供页面与 AI agent 共用的 tool-facing canonical 搜索接口。
- 搜索建议与正式结果共用同一接口，仅通过 `mode` 区分。
- 以单一 `query` 为主输入的 web-search-like 检索语义。
- searchable object 的统一命名、字段归属与 provider 注册。
- `local_only / remote_only / hybrid_remote_fallback_local` 的执行规则。
- `circle.group` 的 fallback typed contract。
- 本地聊天搜索生命周期、账号隔离与删除同步规则。
- 云侧搜索读模型、读写分离、多读切片、每切片独立弹性与未来统一读库替换边界。
- AI 模型可生成的条件边界：`objectTypes`、filters、sort hints、limit、launchContext。
- `web.document` 与趣我圈内部对象共用同一检索接口。

本 L2 不负责：

- 业务写模型存储迁移（ES 仅作派生搜索读库，本期由独立 `search-service` 承载，详见下方 2026-06-15 决定）。
- 低存储设备的阈值与自动淘汰策略。
- assistant runtime / skill / prompt 编排逻辑；但 tool-facing search schema 本身在本 L2 范围内。

## 2026-06-15 架构决定：独立 search-service + 专用 ES 集群

凡与下文“具体搜索引擎不在本期实施”“未来统一高性能读库”等表述冲突处，以本节为准：

- 本期落地**专用 ES/OpenSearch 集群**为统一搜索读库（`quwoquan_objects` 索引），并新建**独立可部署 `search-service`** 承载 canonical `search(request)` 的云侧统一入口 `POST /v1/search` 与 `POST /v1/search/feedback`。
- 召回后端 ES 主 + native 透明回退；canonical contract 与 object taxonomy 保持不变，ES 仅替换读侧实现。
- 各域 remote searchable object 改为 indexer 数据源灌入统一索引；`gateway`（seed-box 反向代理）新增 `/v1/search` 前缀路由指向 `search-service`。

## 约束

- 产品与页面层只允许调用 canonical `search(request)`。
- AI agent 只能通过与页面同源的 canonical contract 调用检索，不允许维护第二套 agent-only 搜索接口。
- 所有 searchable object 必须注册到统一 taxonomy，不允许再以产品接口名作为长期真相源。
- 聊天对象固定为 `local_only`。
- `circle.group` 固定为 `hybrid_remote_fallback_local`。
- 云侧搜索读路径必须与业务写路径分离。
- 多读切片必须支持独立副本数、独立缓存、独立限流与独立弹性。
- 未来统一高性能搜索读库只允许替换 read model，不改变 canonical contract。
- AI 模型生成的条件必须满足 typed schema、allowlist 与资源上限，不能下推为自由表达式执行。
- canonical contract 必须保持 query-first 和扁平条件结构，不引入复杂布尔嵌套 DSL，优先支持 AI 多次主题拆分调用。

## 角色分工

- `global-search-experience`: 定义统一搜索治理口径。
- `cross-domain-search-journey`: 消费本 L2 提供的 contract 与 execution policy。
- `messages`: 提供本地聊天 snapshot / sync 真相源。
- `content / circle / entity / integration`: 提供 remote searchable object 的域契约，并作为统一 ES 索引的 indexer 数据源。
- `search-service`: 装配 ES 主 + native 回退后端，承载统一 `POST /v1/search` / `POST /v1/search/feedback`，运行统一 indexer 灌数到 `quwoquan_objects`。
- `gateway / orchestrator / platform`: 提供云侧路由代理（`/v1/search` 指向 search-service）、缓存、限流与观测基础设施。

## 数据生命周期合同

- 本地聊天搜索索引登出不清空，但必须账号隔离。
- 本地消息索引删除与撤回必须同步删索引。
- 云端消息 TTL 与端侧长期保留可以不一致。
- 云侧搜索读模型是派生数据，可按重建 / 回放恢复，不承担业务主存储真相源责任。

## 非功能目标

- `suggest` 高 QPS 路径默认 lexical-only。
- 单个 remote provider 故障不阻塞整个搜索页面。
- 云侧搜索流量不得长期依赖扫描主业务集合。
- 读模型可按 objectType 水平扩展，控制成本。
- tool-facing 搜索接口必须保持幂等、只读、可审计与可限流，支持 agent 高并发调用。
- 同一 agent 回答过程可对 `web.document` 与趣我圈对象执行多轮小查询，接口不得因结构过深而显著增加模型拆解成本。

## 商用化三引擎阻断登记（2026-06）

当前三引擎规划把本能力从“统一搜索壳层”提升为“站内搜索 + 小趣按需检索 + 站外 SEO 引流”的共同基础。本节点登记以下 `GATE_BLOCK`，不得在未回填证据前宣称商用上线：

1. 站内搜索不得继续以 `ListPublished/ListCircles/内存 map + strings.Contains` 作为主路径；本期必须有共享搜索核心、相关性排序、敏感 query 阻断和 provider 统一 envelope。
2. 小趣不得维护 `web_search/search/app_search` 第二套 fake 搜索真相源；assistant 工具必须桥接 canonical `search(request)`，并返回 typed citation provenance。
3. `web.document` 不是旁路能力，而是 canonical search 的一个 provider；站内业务对象与网页检索必须进入同一聚合、排序、引用结构。
4. 标签与实体不能只停留在对象页解释；必须进入 query expansion、召回补充、排序原因、零结果回退与小趣 citation rank。
5. 公开 SEO 引流必须由 `public-content-web-entry` 提供可索引 HTML、robots/sitemap、canonical/OG/JSON-LD，不能只生成 App 端 HTTPS 分享链接。

## LLM 按需检索接口约束

面向小趣和其他 LLM agent 的检索接口必须符合以下最小合同：

- 唯一工具名为 canonical `search`；`web_search` 与 `app_search` 只能作为兼容 alias 或 provider scope，不得返回独立 fake schema。
- 请求必须以 `query` 为主输入，可选 `mode`、`objectTypes`、`limit`、`queryVariants`、`searchPlans` 与 allowlist filters。
- 响应必须包含 `hits/citations/degradeSignals/provenance`，其中每个 hit 至少包含 `objectType/objectId/title/snippet/score/sourceDomain/visibility/reasons/evidence`。
- provider 注册范围本期至少覆盖 `web.document/content.post/entity.homepage/user.profile/chat.message/circle.group/circle.circle/tag`；未实现 provider 必须返回结构化 degrade signal。
- 私有对象（如 `chat.message`、private content）只能在授权用户上下文内检索，绝不进入公开 SEO 或跨用户 web 聚合。

## 2026-06-16 商用闭环：架构落地、dev 工作包与上线准出

本节是搜索商用化主链路的落地真相源（架构 + dev 工作包 + 上线准出），与上文 `2026-06-15 架构决定`、`非功能目标`、`迁移灰度回滚` 融合，不另起第二套规划。

### 已落地架构（search-service + ES + Redis）

```text
App / assistant tool
        │ canonical search(request)  (mode=suggest|result)
        ▼
   gateway(/v1/search*) ──► search-service(18095)
        │                         │ runtime/search.Retrieve（唯一跨类型排序真相源）
        │                         ▼
        │                  FallbackBackend(Primary=ES, Fallback=native)
        │                         │
        │             quwoquan_objects(ES)  ◄── 各域 indexer(content/entity/circle/user/location.place)
        ▼
   feedback/queryLog ──► feedbackstore(Mongo, TTL) ──► queryheat ──► rm_search_term_heat(TTL 86400)
        │                                                              │ 结果页排序(R-S07，已闭环)
        └──► Redis Stream events.search.recommendation_signals ──► content-service consumer
                 ──► rm_recommend_feature ──► FeatureStore ──► RuleScorer（推荐 Feed 排序，R-S07-5）
```

- 召回：ES 主 + native 透明回退；ES 故障整体降级 native，不阻塞主路径。
- 反馈/热力：`FeedbackSink / QueryLogSink` 落 Mongo（TTL），`queryheat` 派生 `rm_search_term_heat`(TTL 86400)，term-heat 既排序结果页、又经 Redis 注入推荐 Feed。
- 排序透明化：`rankReasons / rankPosition / rankingVersion / experimentBucket` 进响应信封，AB 一致性哈希稳定切桶（control / term_heat）。

### /dev 工作包登记与状态（单一真相源：本表 + docs/outstanding_risks_backlog.md）

> 协调结论：App 实现项 WP-C / WP-D 已与并发 intersection 重构会话协调后落地（location 命中改为单源消费 `entity.homepage` 顶卡 + `location.place` 已连接地点，不再依赖第三方 `integration.location_poi`）；提交时按已迁移 canonical run evidence（`release_diff_manifest.md`）的 SHARED 桶拆分，勿覆盖 intersection 行。WP-B 的降级横幅/曝光/`referralSource`/`feedRequestId` local_contract 已覆盖，归因链 user_acceptance 随 WP-G journey 补。

| 工作包 | 目标 | 主要文件 | 验收证据 | 关联 backlog | 状态 |
|---|---|---|---|---|---|
| WP-B App 体验收口 | 降级横幅由 `degradeSignals` 真实驱动；默认页 inspiration 生产/消费一致；mock 仓库旧术语清理；曝光/停留/`referralSource`/`feedRequestId` 归因链补齐 | `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`、`.../global_search_page.dart`、`.../providers/search_coordinator.dart`、`quwoquan_app/lib/core/services/search_repository.dart` | local_contract widget（降级横幅渲染、空/错/降级态）+ user_acceptance journey（埋点归因链） | R-002 / R-005 / R-006 / R-007 | 🟡 部分：local_contract 已绿；归因链 user_acceptance 待 WP-G |
| WP-C 交集合流 | 交集 Tab 去本地拼装，单源消费云侧 `connectionState + intersectionReason.primaryText`；与并发 intersection 会话协调 | `quwoquan_app/lib/ui/search/**`、`quwoquan_app/lib/components/object_page/**` | local_contract widget（交集 Tab 单源 primaryText）+ contract（search_contract/search_objects） | R-003 / R-IX06 / R-IX07 | ✅ 已完成：顶卡=entity.homepage、已连接地点=location.place 单源，local_contract 绿 |
| WP-D location 落地 | `location.place` 命中后落地页 / route 归属：临时地点卡 vs 「提升为 entity.homepage」引导；metadata-first 定义 route_id/surface_id | `contracts/metadata/_shared/*`、`quwoquan_app/lib/ui/{search,entity}/**` | local_contract contract（route/surface metadata）+ local_contract widget | R-S05e-1 | ✅ 已完成：locationPlaceLanding route/surface + 落地卡 + 提升 CTA，local_contract 绿 |
| WP-E 索引长稳 | 写时投影器常驻增量、ES 重启后一致性与补偿恢复长稳；真集群 batch / 启动 SLA 重校准；单一根 Go module 构建门禁常驻 | `quwoquan_service/services/content-service/internal/infrastructure/{searchindex,placeindex}/**`、`quwoquan_service/runtime/search/es/**`、`quwoquan_service/services/search-service/deploy/Dockerfile`、`quwoquan_service/go.mod`/`go.sum` | api_integration 长稳（增量 / 重启恢复 / backfill 一致）+ 根 module CI 构建可复现 | R-S06-S-1 / R-S06-S-2 | 🔴 阻断：真集群/长稳未闭合；根 module 已闭合 |
| WP-F 推荐信号 api_integration | 真实 Redis + search-service & content-service 双服务端到端，证明 `events.search.recommendation_signals → rm_recommend_feature → RuleScorer` 注入推荐 Feed | `quwoquan_service/services/search-service/**`、`.../content-service/internal/infrastructure/recommendation/**`、`runtime/redis/**` | api_integration 集成（真实 Redis 双服务冒烟）+ stackctl verify | R-S07-5 | ✅ 已完成：真实 Redis 双服务 api_integration 绿，证据已迁移 canonical run evidence（`search_signal_t3_report.json`） |
| WP-G 上线准出 | 三层测试 证据矩阵齐全、stackctl gamma/prod-sim 准出、SLO/告警/AB/回滚演练、高并发负载模型与可重复性、商用上线门槛 | `quwoquan_ops/cli/stackctl.py`、`configs/observability/search_slo.yaml`、`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`、本 spec | api_integration stackctl verify + user_acceptance UAT + 回滚演练记录 + 高并发压测 + 可重复性 golden | R-IX07 / R-S06-S-1/2 | 🟡 部分：高并发 SLO/负载模型已冻结（`search_slo.yaml#load_model`）、背压(in-flight shed)/热点缓存已实现+单测、可重复性已冻结（稳定全序+AB 粘性+golden diff 0 跳变）、压测/profiling 证据落盘、user_acceptance 跨域 journey 已 recorded（`cross_domain_search_journey_test.dart`）、故障/回滚演练已 recorded（已迁移 canonical run evidence：`search_rollback_rehearsal.md`、`search_rollback_rehearsal_report.json`）；根 Go module 已闭合；**仍阻断**：prod-sim、真集群 measured 容量（R-S06-S-1） |

### `/plan-review` 商用缺口台账（2026-06-16）

本台账来自设计师 / 产品 / 架构 / 代码评审 / 测试质量 / 运维运营 / 自动化多角色复审。每项必须落入本表或 backlog，不允许悬空。

| ID | 不符合项 / 风险 | 角色视角 | 处置 | 对应任务 / 验收 |
|---|---|---|---|---|
| PR-SR-01 | 两阶段对象边界需要从实现事实升级为硬规格：suggest 可见本地对象，result 最终页只可见云侧对象 | 产品 / UX / 架构 | 本轮补齐 | L1「商用完整功能规格」A；`cross_domain_search_journey_test.dart` negative finder；acceptance SIT1 |
| PR-SR-02 | 本地 suggest 与云侧 result 的“过程合并”容易被误解为数据混排 | 代码评审 / 测试 | 本轮补齐 | 明确“UI 旅程衔接但最终结果集不混合”；user_acceptance journey 断言本地对象不进 result |
| PR-SR-03 | 高并发规格不能只写 P95；需覆盖 shard/replica/cache/refresh/bulk/circuit/Redis lag/index freshness | 架构 / 运维 | 纳入 R-S06-S-1，发布前阻断 | `search_slo.yaml#load_model` + `search-storage-topology-and-elasticity#容量校准` + 真集群 measured api_integration |
| PR-SR-04 | 搜索准确性需可解释、可复现、可运营，不只“返回结果” | 产品 / 测试 / 运营 | 本轮补齐 | `rankReasons/rankPosition/matchedTerms/evidence/rankingVersion/experimentBucket`；repeatability golden；真集群 preference 验收 |
| PR-SR-05 | 搜索词热力和推荐排序闭环需写清 local_contract/api_integration/AB 证据，不得只停留在投影 | 推荐 / 运营 | 本轮补齐 | WP-F 已 completed；线上 AB 收益为发布后观察项；acceptance 增加 searchTermAffinity scorer 消费证据 |
| PR-SR-06 | search-service 曾使用独立 module，依赖图和容器构建无法由根门禁统一证明 | 自动化 / 运维 | 已收口为唯一根 Go module，服务保持独立二进制与部署单元 | `verify_go_single_module.py` + `verify_search_service_module.sh --with-tests` + `make build` |
| PR-SR-07 | 写时增量与 backfill 幂等长稳未闭合 | 运维 / 测试 | 纳入 R-S06-S-2，长稳 /dev | publish/update/unpublish 投影 soak、backfill rerun count/hash、ES restart recovery |

### 刷新后任务清单（进入后续 `/baseline` 或 `/dev` 的唯一清单）

1. **双阶段搜索合同固化**
   - 内容：metadata/code/test 均断言 `suggest` 本地对象即时、`result` 只含云侧对象；本地命中不进入最终结果页。
   - 测试：`cross_domain_search_journey_test.dart`、`global_search_page_widget_test.dart`、`search_network_results_page_widget_test.dart`。
   - 门禁：`verify_metadata_driven_ui_gate.py`、`verify_ui_mock_isolation.py`、`verify_page_matrix_scan_complete.py`。
   - 状态：已完成，作为回归门禁常驻。
2. **准确性与可重复性硬门槛**
   - 内容：稳定全序、ES stable sort/tie-break、AB sticky、repeatability golden；真集群多副本 `preference` 兜底验证。
   - 测试：`runtime/search/sort_stable_test.go`、`services/search-service/internal/application/*experiments*test.go`、已迁移 canonical run evidence（`search_repeatability_golden_diff.json`）；真集群新增 api_integration。
   - 关联 backlog：R-S06-S-1（多副本 / true cluster）。
   - 状态：local 已完成，真集群待办。
3. **高并发与弹性 measured 准出**
   - 内容：在 prod-sim / 原生 ES/OpenSearch 跑 baseline/peak/spike、warm/cold cache、热点/长尾、混合读写、ES restart、Redis delay、backfill 并发；回填 RPS/P95/P99/错误率/degrade/cache hit/threadpool/heap/GC/Redis lag。
   - 测试：`QWQ_OUTPUT_ROOT/env/repo/runs/search-load/**` + 真集群 report；`stackctl verify --env gamma|prod --kind all --tier all`。
   - 关联 backlog：R-S06-S-1。
   - 状态：发布前阻断。
4. **写时增量 / backfill 幂等长稳**
   - 内容：content/entity/circle/user/location 的 publish/update/unpublish 写时投影 soak，backfill rerun 收敛同一 count/hash，ES restart recovery SLA。
   - 测试：领域 projector/backfill tests + local/prod-sim api_integration 长稳报告。
   - 关联 backlog：R-S06-S-2。
   - 状态：待办。
5. **搜索词热力与推荐闭环运营化**
   - 内容：query log / feedback / queryheat / relatedTerms / searchTermAffinity → Feed scorer 的 local_contract/api_integration 证据常驻；AB bucket 大盘和收益观察。
   - 测试：`search_signal_consumer_test.go`、`runtime/recommendation/*scorer*test.go`、已迁移 canonical run evidence（`search_signal_t3_report.json`）、`QWQ_OUTPUT_ROOT/env/repo/runs/search-obs/search_observability_ab_recommendation_report.md`。
   - 关联 backlog：R-S07-5 线上收益观察项。
   - 状态：链路完成，收益观察。
6. **发布打包 / CI 干净检出可复现**
   - 内容：所有服务统一消费 `quwoquan_service/go.mod/go.sum`，从根 package path 构建独立二进制；search-service 的 deploy/release config 继续遵守版本与灰度合同。
   - 测试：`verify_go_single_module.py`、`verify_search_service_module.sh --with-tests`、`verify_config_pr_policy.sh`、`gate_repo.sh --scope service`。
   - 关联 backlog：R-S06-S-3。
   - 状态：根 module 与搜索构建测试已完成；release config 由通用配置门禁持续验证。

### 上线准出（证据矩阵 + 门槛）

| 层 | 验收意图 | 主证据 | 现状 |
|---|---|---|---|
| local_contract contract/static | GWT/contract | `runtime/search/*_test.go`、`make verify-metadata`、`search-service tests/*_contract_test.go` | 已绿 |
| local_contract module | SIT/GWT | `search-service application/*_test.go`、`quwoquan_app/test/ui/search/**` | 服务侧绿；App 全量受 intersection 重构外部阻塞 |
| api_integration integration | SIT | stackctl gamma：package/up/health/verify + 已迁移 canonical run evidence（`search_smoke_report.json`，`/v1/search` 200、`/v1/search/feedback` 202） | gamma 真实冒烟已绿；推荐信号真实 Redis 双服务 api_integration 已绿（WP-F，已迁移 canonical run evidence：`search_signal_t3_report.json`）；真集群/长稳待 WP-E |
| user_acceptance journey | UAT | 搜索 Journey 端到端（埋点 / 降级 / 弱网 / 权限 / 可重复性） | 🟢 已 recorded：`cross_domain_search_journey_test.dart`（suggest 本地两阶段、result 云侧固定 Tab、本地对象不进 result、最近搜索水合、单域降级不阻塞整页、整页错误态可重试、默认页/结果页 `referralSource=search`+`feedRequestId` 归因链）；高并发负载模型/背压/缓存/可重复性已冻结并有证据（`QWQ_OUTPUT_ROOT/env/repo/runs/search-load/**`、已迁移 canonical run evidence：`search_repeatability_golden_diff.json`）；故障/回滚演练已迁移 canonical run evidence（`search_rollback_rehearsal.md`） |

商用上线门槛（全部满足方可宣称商用上线）：

1. local_contract/local_contract/api_integration 全绿（推荐信号真实 Redis 双服务 api_integration 已绿，WP-F）；跨域搜索 user_acceptance journey 补齐（WP-G）。
2. stackctl `verify --env gamma --kind all --tier all` 与 prod-sim（`prod` rollout gray-initial）准出通过。
3. SLO（`suggest` 即时、`result` P95 ≤ 1.5s、单域降级不阻塞）、告警（`quwoquan_search` 组）、AB 切桶（control / term_heat）可观测且大盘按桶切分。
4. 高并发负载模型与 SLO 冻结（suggest/result/feedback/indexing 四类流量），可重复压测覆盖 warm/cold/突刺/混合读写/ES 重启，未达 SLO 即 NO-GO。
5. 搜索结果可重复性冻结：稳定 sort tie-break、AB bucket sticky、重复查询 golden diff，同一查询不无故跳变。
6. 回滚演练记录：search-service 不可用或时延持续超标时，整版回退旧搜索实现或 `prod` rollback，演练有据。**gamma-local 故障/回滚演练已 recorded**（已迁移 canonical run evidence：`search_rollback_rehearsal.md`，ES 宕机→typed 503 fail-fast→重启恢复、Redis 失败→best-effort 不阻塞、search-service 不可用→重启回滚 6.1s 恢复，演练后 8/8 healthy）；真集群 image/config rollout 回滚由 `stackctl deploy --target prod-hosted` 驱动，属 R-S06-S-1 长稳项。
7. 真集群（非 local-gamma 模拟）性能重校准完成（R-S06-S-1），索引写时增量 / 重启恢复长稳通过（R-S06-S-2）；search-service 已由唯一根 Go module 的 CI 构建与测试门禁覆盖（R-S06-S-3）。

## 迁移、灰度与回滚要求

- 本次 baseline 不要求立刻迁移到统一高性能读库（ES 仅作派生搜索读库，业务写模型不迁移）。
- 若新 contract 或 routing 有问题，整版回退到旧搜索实现，而不是重新暴露第二套产品接口。
- 灰度由应用市场分发 + 端侧上下文 + 云侧策略控制；生产灰度是 `prod` rollout stage（gray-initial），不存在 `prod-gray` 独立包。
- 回滚粒度：search-service 进程回退 / `prod` rollback；ES 不可用时由 `FallbackBackend` 自动降级 native，不需人工切流。

## 验收重点

1. 页面与业务层是否真正只有一个 canonical 搜索接口。
2. 本地 / 远端 / fallback 执行策略是否有唯一真相源。
3. 云侧搜索拓扑是否明确禁止“扫描业务主集合”成为长期方案。
