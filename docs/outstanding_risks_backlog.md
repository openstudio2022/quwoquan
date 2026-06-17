# 遗留事项与风险待办清单（Outstanding Risks Backlog）

> 单一真相源。每次会话起手式必须先审视本清单未解决项；新风险需先向用户复述并获得确认后登记；问题解决后必须打勾并补证据，避免遗漏。

## 使用规则

- 每条遗留事项使用 `- [ ]` / `- [x]` 复选框维护。
- `状态` 字段必须明确写为 `待办`、`进行中` 或 `已解决（日期 + 证据）`。
- 新增事项时，必须补齐 `区域`、`原因`、`影响`、`涉及文件`。
- 标记已解决时，必须写清验证证据，例如测试、门禁、截图、回放、日志或发布记录。
- 发现新风险但未经用户确认，不得直接登记为正式事项。

## 模板

- [ ] R-XXX 标题
  - 区域: App / Service / Data / Ops / Portal
  - 域: `<domain>`
  - 原因: ...
  - 影响: ...
  - 涉及文件: `path/to/file`
  - 状态: 待办

## 搜索体验（Search）

- [x] R-001 搜索结果封面宽高比仍按内容类型固定，缺少真实封面尺寸驱动
  - 区域: App
  - 域: `search`
  - 原因: `PostSearchItemView` 当前不提供封面 `width/height`，结果页只能按图片 `1:1`、视频 `16:9` 给定基础比例，再依赖 `PostPreviewCard` 的 `9/16~16/9` clamp 防止长图或横幅无限长。
  - 影响: 结果流虽然已消除无限长与大留白，但卡片瀑布流仍无法按真实素材比例排布，视觉表达受限。
  - 方案: R-S06 在 remote 模式由 `RemoteSearchRepository` 透传云侧 `coverWidth/coverHeight`，结果页 masonry 卡片用真实宽高比排布（仍保留 `9/16~16/9` clamp 防长图无限长）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`、`quwoquan_app/lib/core/services/remote_search_repository.dart`
  - 状态: 已解决（2026-06-16；remote 模式云侧封面尺寸驱动，随 R-S06；mock 模式仍按内容类型基础比例，属本地预览态）

- [x] R-002 搜索结果降级横幅仍是死逻辑
  - 区域: App
  - 域: `search`
  - 原因: `_buildDegradeBanner()` 恒返回 `null`，`withDegradeBanner()` 目前不会渲染任何降级提示。
  - 影响: 远端降级或能力受限时，`degradeSignals` 无法向用户表达，存在可观测与体验缺口。
  - 方案: 结果页聚合各分域 `SearchResponse.degradeSignals`；有可见结果时不遮挡媒体流，无结果时展示 typed 降级横幅（消息来自 signal.message）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
  - 证据: `_mergeDegradeSignals` + `_hasRenderableResultsForActiveTab` + `_buildDegradeBanner`；widget 测试 `degrade signal 不压过媒体结果` / `degrade signal 在无结果时展示降级横幅` 通过。
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 状态: 已解决（2026-06-16）

- [x] R-003 交集 Tab 的关系理由与互动数据仍依赖确定性 mock 和本地回退拼装
  - 区域: App
  - 域: `search`
  - 原因: 当前仍通过 `_deterministicCount`、`_fallbackConnectionCardModels()`、`_fallbackDiscoverCardModels()` 等逻辑合成交集理由、点赞数、评论数和回退内容。
  - 影响: `beta/gamma/remote` 环境若不补齐真实交集数据契约，端云展示与本地 alpha 行为会不一致。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
  - 方案: WP-C 收口——交集分组唯一真相源改为云侧 `connectionState` 闭集（connected / unconnected / intersection_lead），交集句严格只读 `intersectionReason.primaryText`，无 primaryText 不展示；删除 `_deterministicCount`、`_fallbackConnectionCardModels`、`_fallbackDiscoverCardModels`、`_friendActionLabel`、`_knownIntersectionEntity`、`_discoverContentReason`。
  - 证据: `rg` 确认上述符号在 `search_network_results_page.dart` 全部移除；新增 `_IntersectionContractSearchRepository` 契约测试断言 connectionState 分组 + 只读 primaryText + 无违禁词；`flutter test test/ui/search/pages/search_network_results_page_widget_test.dart` 10/10 通过。
  - 状态: 已解决（2026-06-16）

- [x] R-004 相关搜索词仍由客户端硬编码生成
  - 区域: App
  - 域: `search`
  - 原因: `_relatedSearchTerms()` 直接拼接 `$query 攻略`、`$query 拍照机位`、`$query 交集` 等词条，尚未接入 metadata 或服务端推荐来源。
  - 影响: 相关搜索结果不具备真实推荐语义，也会形成第二真相源风险。
  - 方案: R-S06 在 remote 模式优先消费云侧 `relatedTerms`（缺失才回退端侧派生）；R-S07 在 search-service 由 `queryheat` 真实计算并经 handler 写入响应（实际内容取决于 `rm_search_term_heat` 热力读模型是否接 Mongo）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`、`quwoquan_app/lib/core/services/remote_search_repository.dart`、`quwoquan_service/services/search-service/internal/application/queryheat/`
  - 状态: 已解决（2026-06-16；remote 模式接云侧 relatedTerms + 服务端 queryheat 计算，随 R-S06/R-S07；mock 模式回退端侧派生属本地预览态）

- [x] R-005 搜索默认页 inspiration 数据生产与消费不一致
  - 区域: App
  - 域: `search`
  - 原因: 默认页当前只消费 `guessKeywords`、`hotCircles`、`hotLocations`，但 `search_coordinator.dart` 仍持续 hydrate `inspiration.people` 与“今日交集” chips，之前相关死 UI 已被删除。
  - 影响: 存在无人消费的数据生产与维护成本，容易误导后续开发继续沿用旧结构。
  - 涉及文件: `quwoquan_app/lib/ui/search/providers/search_coordinator.dart`
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 证据: coordinator 不再写入 `people`；`flutter test test/ui/search/pages/global_search_page_widget_test.dart` 9/9 通过。
  - 状态: 已解决（2026-06-16）

- [x] R-006 搜索 mock 仓库仍残留旧术语禁用词
  - 区域: App
  - 域: `search`
  - 原因: 搜索 UI 范围内已清理“共同兴趣 / 同趣的人 / 共同圈子 / 交集发现流”，但 mock 仓库仍有残留词汇。
  - 影响: 后续若该 mock 数据重新进入展示路径，会回归旧术语并造成文案不一致。
  - 方案: `search_repository.dart` 用户 snippet 由「共同兴趣相关」改为「推荐关注」。
  - 涉及文件: `quwoquan_app/lib/core/services/search_repository.dart`
  - 证据: `rg '共同兴趣' quwoquan_app/lib/core/services/search_repository.dart` 无命中；`flutter test test/ui/search/search_repository_test.dart` 通过。
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 状态: 已解决（2026-06-16）

- [x] R-007 搜索结果页与默认页的行为埋点、停留、归因链仍需专门核实
  - 区域: App
  - 域: `search`
  - 原因: 本轮主要解决 UI/布局与技术债问题，尚未逐项核对搜索默认页、结果页在曝光、停留、`referralSource`、`feedRequestId` 等方面是否满足全链路要求。
  - 影响: 搜索漏斗、推荐归因链和运营观测可能存在断点。
  - 方案: `global_search_page` / `search_network_results_page` 进入时 `trackImpression`（`ReferralSource.search` + `feedRequestId`），离开 `dispose` 时 `trackDwell`；tracker 引用在 init 帧缓存避免 dispose 后读 ref。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/global_search_page.dart`、`quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
  - 证据: 两页 widget 测试全绿（9 + 11）；contentId=`global_search`/`search_network_results`，tags 含 entrySurfaceId 与 tab/query。
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」），并归入 cross-domain-search-journey SIT 的埋点归因链验收。
  - 状态: 已解决（2026-06-16；T2 widget 通过，T4 journey 仍待 WP-G 准出一并补录）

- [x] R-008 搜索结果页内容空集与实体置顶仍保留硬编码 demo 回退
  - 区域: App
  - 域: `search`
  - 原因: 远端内容为空时 `_fallbackContentItemsForQuery()` 仍返回带外链图与编造点赞数的演示内容；`_entityTopResult()` 对 `厦门大学` 等保留硬编码实体卡与 `26.8万关注 · 1.2万内容` 伪 meta。属 `lib/ui` 域名假数据，违反 mock 隔离（R15/R30）。
  - 影响: beta/gamma/prod 若服务端无结果，端会展示编造内容与伪统计，形成第二真相源并误导验收；与交集消费收口（R-003 已解决）不同，属一般搜索 demo 残留。
  - 方案: 删除 `_fallbackContentItemsForQuery` 与硬编码实体 fallback；实体 meta 只读 hit payload 计数；空集走真实空态（与 R-002 降级横幅协同）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`、`quwoquan_app/test/ui/search/pages/global_search_page_widget_test.dart`
  - 证据: fallback 符号已删除；`flutter test test/ui/search/pages/search_network_results_page_widget_test.dart` 11/11 通过。
  - 状态: 已解决（2026-06-16）

## 搜索端云一体（专用 ES/OpenSearch + search-service）

> 架构决定：专用 ES/OpenSearch 集群 + 复用 `runtime/search/es` 库 + 新建可部署 `search-service`（`FallbackBackend(Primary=ES, Fallback=native)`）。真相源 CR：`specs/changelog/CR-20260615-037-search-dedicated-es-service-landing.yaml`。
>
> ⚠️ **版本控制状态（2026-06-16 复审）**：本节绝大多数搜索增量代码仍处 **git untracked**，尚未纳入版本控制——包括整个 `quwoquan_service/services/search-service/`（含 go.mod/go.sum）、`quwoquan_service/contracts/metadata/search/`、`quwoquan_service/runtime/search/es/*`、各域 `*_search_projection.go` 与 `internal/infrastructure/searchindex/`、`content-service` 的 `search_signal_consumer.go`、App 端 `remote_search_repository.dart` 与 `generated/search/*.g.dart`、`deploy/service/search-service/`、对应 CR/spec。功能链路本地已验证可用，但**「已解决」状态仅代表功能就绪**；本轮按用户选择 `git_scope: verify_only` 不做提交，版本落盘（git add/commit）归属用户。在干净检出上运行 CI/全量 gate 须先由用户提交这些文件。不另建第二份清单，仅在此注明。

### 已落地（cloud backend，2026-06-16，已验证）

- [x] R-S01 真实 ES 客户端 + 装配（ES primary / native fallback）
  - 区域: Service
  - 域: `search`
  - 证据: `quwoquan_service/runtime/search/es/{http_client,index_schema,assembly,indexer}.go` 与对应 `*_test.go`；`go test ./runtime/search/...` 全绿（含 ES httptest、lossless round-trip、outage fallback）。
  - 状态: 已解决（2026-06-16；`go test ./runtime/search/...` ok）
- [x] R-S02 search 域 metadata-first（query/feedback 日志 + _shared/search_contract 字段扩展）
  - 区域: Service
  - 域: `search`
  - 证据: `quwoquan_service/contracts/metadata/search/query/{aggregate,fields,events,storage,service}.yaml`；`_shared/search_contract.yaml` 增 `relatedTerms/rankingVersion/requestId/rankReasons/coverWidth/coverHeight`；`make verify-metadata` 绿。
  - 状态: 已解决（2026-06-16；verify-metadata 通过）
- [x] R-S03 可部署 search-service（/v1/search、/v1/search/feedback、/healthz、/metrics）
  - 区域: Service
  - 域: `search`
  - 证据: `quwoquan_service/services/search-service/**`；`go build/vet/test ./...` 全绿；真实启动冒烟：health 200 / search 200（含 requestId+rankingVersion+provenance）/ 空 query 400 / feedback 202 / metrics 200；ES-down+native fallback 退化 200、纯 ES 无 fallback 诚实 503。
  - 状态: 已解决（2026-06-16；contract test + 本地 boot 冒烟）
- [x] R-S04 部署登记（六 manifest + 端口槽 + 四环境 ES config 段）
  - 区域: Ops
  - 域: `search`
  - 证据: `process_domain_mapping`/`process_domain_plane_mapping`/`module_package_mapping`/`reliable_task_module_catalog`/`workload_topology_inventory`/`local_env_port_manifest` 均登记 `search-service`(domain=`search`，planned standalone-workload，beta=gamma=prod 一致)；全部部署门禁验证器绿（deployment_domain_mapping/workload_topology/module_package/reliable_task_catalog/permission_scope/gamma-local↔prod consistency+isomorphism/prod_plane_access_isolation/runtime_packaging/service_config_layout/service_env_contract/deploy_kustomization/engineering_directory/opsx_ff_8services）。
  - 状态: 已解决（2026-06-16；部署验证器全绿）

### 待办（端云接线，闭环 R-001/R-003/R-004）

- R-S05 各域 → `es.Indexer` 单一索引灌数管线（按域拆分；content/entity/circle/user/location）
  - 区域: Service / Data
  - 域: `search`
  - 原因: 当前 search-service 召回链路就绪，但生产侧索引尚未灌数；alpha 走 native，beta/gamma/prod 的 ES 索引需各域投影写入后才有真实结果。
  - 影响: 未灌数前 `/v1/search` 在 ES 模式返回空，端到端结果不可用。
  - 机制基线（content 切片确立，后续各域复用）: 共享投影函数（域内 application 层，与该域 native CandidateSource 同源） + infrastructure 写时 `Projector`（实现各服务 `application.Projector`，按 publish/update/visibility-change upsert、unpublish/delete/ineligible delete，失败只结构化告警不阻塞主写路径，挂在已有 projector fan-out 末位） + `Backfill`（`EnsureIndex`→列全量→共享投影→`Writer.Bulk` 批量）+ `es:` config 段（`SEARCH_ES_*` 注入、disabled=no-op）。
  - [x] R-S05a content 域灌数（`content.search_index_worker` 落地）
    - 区域: Service
    - 域: `content` → `search`
    - 证据: 共享投影 `application.ProjectPostToSearchDocument`（`post_retrieve.go`，与 `PostCandidateSource` 同源）；写时投影器 `services/content-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`；装配进 `cmd/api/main.go`（fan-out 末位 + `es:` 五环境 config + `SEARCH_ES_*` 注入 + boot EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt`（本切片文件为空）/`go vet ./services/content-service/... ./runtime/search/...`/`go test ./services/content-service/... ./runtime/search/...` 全绿；alpha（es disabled）真实 boot 冒烟主路径不受影响；`verify_reliable_task_catalog` + `verify_module_package_mapping` 绿（模块早已声明，无需新增 manifest）。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05b entity 域灌数（entity.homepage → 同一 `searchindex` 机制 + 共享投影）
    - 区域: Service
    - 域: `entity` → `search`
    - 证据: 共享投影 `application.ProjectHomepageToSearchDocument`（`homepage_search_projection.go`，与 `SearchHomepages` native 召回同源；anchor 字段 `entityId/entityName`，objectType `entity.homepage`→target `entity`）；写时投影器 `services/entity-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`（实现新引入的 `application.Projector`，发布/认领更新 upsert、下线/失格 delete，ES 故障只告警不阻塞，mutation 内 deferred-emit 释放锁后再投影）；装配进 `cmd/api/main.go`（`WithProjector` 末位 + `es:` 五环境 config + `SEARCH_ES_*` 注入 + EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt` 本切片文件全 clean；`go vet`/`go test ./...`（entity 独立 module）+ `runtime/search` 全绿。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05c circle 域灌数（circle.circle / circle.group）
    - 区域: Service
    - 域: `circle` → `search`
    - 证据: 共享投影 `application.ProjectCircleToSearchDocument` + `CircleSearchEligible` + `circleSearchCategoryID`（`circle_search_projection.go`，`SearchCircles` 重构为同源消费，删除死代码 `asStringSlice`）；写时投影器 `services/circle-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`（实现 `repository.EventPublisher`：`CircleCreated/CircleUpdated` reconcile、`CircleArchived` delete、其余忽略；读回经 `CircleReader`；ES 故障只告警不阻塞；backfill 走 `CircleStore.List` 游标分页）；装配进 `cmd/api/main.go`（`WithEventPublisher` + `es:` 五环境 config + `SEARCH_ES_*` 注入 + EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt` 全 clean；`go vet`/`go test ./services/circle-service/... ./runtime/search/...` 全绿（含 `tests` 集成包）。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05d user 域灌数（user.profile）
    - 区域: Service
    - 域: `user` → `search`
    - 证据: 新建共享投影 `application.ProjectUserProfileToSearchDocument` + `UserProfileSearchEligible`（`user_search_projection.go`，objectType `user.profile`→target `user`；昵称→Title、bio→Summary、`IdentityTags` 经 `parsePgTextArray`→Tags、粉丝+作品数→Popularity、anchor 字段 `authorId/authorName/authorDisplayName`；合格集=accountState active 且 status active）；写时投影器 `services/user-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`（实现 `application.UserEventPublisher`，`UserProfileUpdated/UserAvatarUpdated/UserRegistered` 读回 reconcile、失格/缺失 delete、读回错误不误删、ES 故障不阻塞；`ComposePublisher` 把 MQ 主发布器与 search 投影器组合——主发布器错误透传、search best-effort）；backfill 经新增 `PgProfileStore.ListProfilesForIndex`（keyset 分页、26 列完整扫描含 identity_tags）；装配进 `cmd/api/main.go`（ES 启用时组合到 `userEventPublisher` 末位 + `es:` 六环境 config + `SEARCH_ES_*` 注入 + EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt` 本切片文件全 clean（`cmd/api/main.go` 仅预存 Integration struct tag 错位未动）；`go vet ./services/user-service/... ./runtime/search/...` 绿；`go test` 中 `searchindex`/`application`/`cmd/api` 等包全绿。`tests` 集成包有 18 个失败，已用 HEAD 基线（stash 我的改动后复跑）证明为**预存**（real-Postgres 契约测试因 `identity_tags` 列 NULL 无法扫入 `*string`、迁移计数 15 vs 16、登录路由 404 等，均与本切片无关），我的改动零新增失败。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05e location 成为统一检索第一方对象 —— 已解决（保留 geo 维度 + 叠加 location.place target）
    - 区域: Service / Data / App
    - 域: `content`(第一方地点快照) → `search`
    - 事项: location 对象要在 `/v1/search` 出真实结果，需在 `runtime/search` 检索契约新增 `TargetLocation`/`ObjectTypeLocation`，并联动 `AllTargets`/`TargetForDocument`/`ObjectTypesForTargets`、search-service `DefaultResultTargets`、metadata `_shared/search_objects.yaml`、App 端 target 枚举。
    - 方案（用户拍板 force_target）: 保留并复用并发会话已落地的**跨对象 geo 维度**（`GeoNear`/`RetrieveFilters.Near`/`RetrieveHit.Geo/DistanceKm/PlaceName`/`nearMatch`/`Document.Geo`/ES geo mapping），仅做**加性**扩展，不删改其语义；叠加一类复用该维度的第一方对象 target `location.place`。改写 `search_objects.yaml` 原“location 不是 target、第一方地点即 entity.homepage”不变量为：geo 是跨对象维度（保留）+ `location.place` 是复用该维度的第一方对象，仅覆盖“被内容引用但未绑定 `canonicalEntityId`/`primaryHomepageId` 的自由文本地点”；已绑定者由 entity.homepage 承载（同一地点只出现一次，单一真相源）。
    - 单一真相源: 地点绑定 canonicalEntity（成为 entity.homepage）→ `DerivePlaceRef` 不再产出该 ref，其 location.place 在失去最后一篇自由文本引用后被删除；geo 机制只有一套。
    - 灌数实现: content-service 新增第一方地点快照存储 `place_snapshots`（派生读模型，posts 为唯一写真相源，按引用集去重）；`placeindex.{store,projector,backfill}` 写时增量维护 + 全量重建；共享投影 `application.ProjectPlaceToSearchDocument` + 身份函数 `CanonicalPlaceID`（normalize(locationName)+粗 geohash，不用第三方 poiId）；DDD 分层：ES 只在 `infrastructure/placeindex`。
    - 证据: metadata `make verify-metadata` 绿；`make codegen-app` 重生 `search_registry.g.dart`（`SearchObjectType.locationPlace`/`RetrieveTarget.location`/section locations/ai_target location→location.place）且幂等；Go `gofmt -l` clean、`go vet`、`go test -count=1 ./runtime/search/...`、`./services/content-service/internal/{application,infrastructure/placeindex}/...`、search-service `./tests/...` 全绿；content-service cmd（api/search-backfill）build OK；alpha ES-disabled 路径 nil-safe（place projector 仅在 `searchBuilt.Client != nil` 构造，`Project` 守 `a.place != nil`）；App 端 `dart analyze`（search 范围）clean，全量 analyze 的 80 条 error 全部属于并发会话 intersection 重构（与本任务无关，见剩余风险）。spec/acceptance/CR 见 `search-object-taxonomy-and-provider-registry/{spec.md,acceptance.yaml}` 与 `specs/changelog/CR-20260616-038-location-first-party-search-object.yaml`。
    - 状态: 已解决（2026-06-16）
    - 衍生待办: location.place 落地页（detail/route）归属与渲染已定（见 R-S05e-1，2026-06-16 WP-D 落地：临时地点卡 + 提升为 entity.homepage CTA）；gamma ES 灌数后 `/v1/search` 召回 location.place 的 T3 集成随 search-service 集成补录。
  - [x] R-S05e-1 location.place 落地页归属与渲染（衍生自 R-S05e）
    - 区域: App / Service
    - 域: `search` / `entity`
    - 事项: location.place 命中后点击进入的 detail/route 未定；需明确其落地页是临时地点卡还是“提升为 entity.homepage”的引导入口，并定义 route_id/surface_id（metadata-first，禁止 UI 硬编码）。
    - 影响: 当前 location.place 可被检索召回，但点击落地体验未定义；不阻塞召回主链路。
    - 方案（WP-D，已采纳计划推荐）: 落地为**临时地点卡 + “提升为实体主页”引导 CTA**，符合 spec 单一真相源（未提升=location.place、已提升=entity.homepage）。命中详情来自搜索结果 payload，经 `LocationPlaceLandingPageRouteExtra` 透传，落地页本身**无独立后端 operation**；提升动作复用 `suggestHomepage` surface。
    - 实现: metadata-first 在 `_shared/app_routes.yaml`（`locationPlaceLanding` `/locations/{placeId}`）+ `_shared/ui_surfaces.yaml`（surface `locationPlaceLanding` owner=search、`operation_ids: []`）定义；`make codegen-app` 重生 `app_route_paths.g.dart`（`AppRoutePaths.locationPlaceLanding`）+ `app_ui_surfaces.g.dart`（`AppUiSurfaces.locationPlaceLanding`）；新页 `lib/ui/search/pages/location_place_landing_page.dart` + router wiring；`search_network_results_page` 交集已连接地点改走 `_IntersectionTargetType.locationPlace` → 落地页（不再误导 homepage 详情）。
    - 证据: `make verify-metadata` 绿；`make codegen-app` 幂等重生路由/surface 常量；新页 + 改动文件 `flutter analyze` 0 issues；`flutter test test/ui/search/pages/location_place_landing_page_widget_test.dart` 3 用例全绿（渲染名称/地址/临时徽标/CTA、CTA 跳 suggestHomepage 带地点名、JourneyEventTracker enter 曝光 + promote_click 上报）；页面横向质量矩阵 + `metadata_driven_ui_gap_inventory.yaml` 已登记。
    - 状态: 已解决（2026-06-16，代码 untracked 待用户提交）
- [x] R-S06 App 接 `/v1/search`（RemoteSearchRepository + provider 模式切换 + 结果页读云侧字段）
  - 区域: App
  - 域: `search`
  - 方案: 新增 `quwoquan_app/lib/core/services/remote_search_repository.dart`：result 模式 POST `CloudRuntimeConfig.gatewayBaseUrl + SearchApiMetadata.searchQueryPath`，统一走 `CloudHttpClient.postJsonObject`（codegen path/operation/surface 常量、零硬编码 URL/path、无裸 http.Client、无自建重试、错误经 `CloudException`/`runtimeFailure` 结构化）；objectTypes 复用 `RetrieveRequest.fromSearchRequest().targets` 单源映射并剔除 chat（避免误发本地命名空间对象）；解析 `RetrieveResponse` 透传 `rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason/relatedTerms`（`SearchHit`/`SearchResponse` 仅按 `RetrieveToolContract` 契约最小加性补承载字段）。`searchRepositoryProvider` 按 `appDataSourceModeProvider` 切换（remote→Remote、mock→本地扇出 composite）。结果页 `search_network_results_page.dart` 仅改「全部/媒体/相关搜索」消费区（masonry 用云侧 `coverWidth/coverHeight` 真实宽高比、`rankPosition` 排序、`rankReasons` 首条作理由、`relatedTerms` 优先于端侧派生），未触碰 intersection tab 任何符号。网关：`deploy/local-gamma/Caddyfile` 两块各加 `@api_search /v1/search*`→`search-service:18095`；seed-box 加 `SEARCH_UPSTREAM_HOST/PORT` 透传。
  - 证据: scoped `dart analyze`（search_repository / remote_search_repository / retrieve_request / search_hit_payload / search_coordinator / search_network_results_page 共 6 文件）= 0 error / 0 warning（仅全仓同款 `prefer_initializing_formals` info）；部署验证器全绿（deployment_domain_mapping / workload_topology / module_package / gamma-local↔prod consistency / topology_regression）。受并发 intersection 重构外部阻塞，App 全量 `flutter analyze/test` 暂不可跑（错误全在 object_intersection，0 条涉及 search），T2 widget / T3 集成待 intersection 合流后补（见 R-IX07）。
  - 状态: 已解决（2026-06-16；scoped analyze + 部署验证器；端到端 /v1/search 真实冒烟见衍生待办 3）
  - 衍生待办: (1) remote 模式实体顶卡/location 仍请求旧 `integration.location_poi`（不映射任何云 target），需切 `entity.homepage`/`location.place`——因改动与 intersection 共享的 `_locationResults`，待并发 intersection 重构合流后协调（与 R-IX06 联动）；(2) 云侧 `relatedTerms` 填充已由 R-S07 在 search-service handler 落地（早前 R-S06 观测到的“未填充”系 R-S07 改动前旧 handler，现已闭合）；(3) local-gamma 运行栈未实例化 search-service → 见衍生待办 3（已发起环境 worker）。
- [x] R-S07 反馈/relevance 闭环 + 搜索词热力（query_popularity/cooccurrence/trending）注入排序
  - 区域: Service / Data
  - 域: `search`
  - 方案: search-service `internal/application` 定义 `FeedbackSink`/`QueryLogSink` 端口 + 强类型 `QueryLog`/`FeedbackEvent`，`infrastructure/feedbackstore` 落 `storage.yaml` 的 Mongo 集合（建 TTL+查找索引，`searchRequestId` upsert）；`/v1/search` 命中后 `handler.go` 旁路 best-effort 记 `SearchQueryLogged`（不阻断主路径、无空 catch）；`/v1/search/feedback` 落反馈。搜索词热力：`application/queryheat`（归一化/去重/时间衰减/CTR 加权）产出 `TermHeat` + `RelatedTerms`，`infrastructure/queryheatstore` 周期 `Rebuild` upsert 派生读模型 `rm_search_term_heat`（TTL 86400s，metadata 声明 + 合约测试断言代码常量逐字一致）。排序透明化：`runtime/search/retrieve.go` 给 `RetrieveHit` 加 `RankReasons/RankPosition`（`rankAndMerge` 统一累积、分页后 1-based 编号、`RetrieveHitMap` 同源），`application/ranking.go` 按 AB 分桶决定 term-heat 加权重排并重编号，`handler.go` 写 `relatedTerms/rankingVersion/experimentBucket` 信封。SLO/指标/告警/AB：`searchmetrics`（promauto histogram 分位数 + 计数，标签含 experiment_bucket）、`configs/observability/search_slo.yaml`、`deploy/monitoring/alerts/quwoquan_alerts.yaml`（quwoquan_search 组）、`application/experiments.go`（一致性哈希稳定切桶 control/term_heat）。
  - 证据: `make verify-metadata` ✓；`gofmt -l` clean；`go vet ./runtime/search/...` OK；`go test -count=1`：search-service `application`/`application/queryheat`/`tests`（含 envelope + TTL 合约）✓、`runtime/search` + `runtime/search/es` ✓、`assistant-service .../tool`（RetrieveHitMap 消费者向后兼容）✓；SLO/告警 YAML `yaml.safe_load` OK。
  - 状态: 已解决（2026-06-16；verify-metadata + go test + 合约测试）
  - 衍生待办: 见 R-S07-5（搜索词信号注入在线推荐 Feed 排序，平台级跨服务增量，已 backlog 化）。
- [x] R-S07-5 搜索词信号注入在线推荐 Feed 排序（衍生自 R-S07，平台级跨服务增量）
  - 区域: Service / Data
  - 域: `search` → `recommendation`/`content`
  - 事项: 让 R-S07 产出的搜索词热力/相关性（`rm_search_term_heat` + `SearchQueryLogged`）参与**推荐首页 Feed**排序（非搜索结果页——结果页排序已用 term-heat 闭环）。
  - 原因: 需新建 `search-service → content-service` 跨服务事件传输（Redis 发布端 + content-service 订阅 + `RecommendFeatureProjector` 消费 + `feature_registry` 注册搜索特征 + `recpolicy` 因子 + `RuleScorer`）；半成品落地会形成无消费者的死特征（违反 R24/R26 零技术债红线）。本项已按独立平台增量闭环。
  - 影响: 已由搜索查询/term-heat 信号经 Redis Stream 发布到 content-service，投影进推荐特征宽表，并被 FeatureStore 与 RuleScorer 真实消费；推荐 Feed 可消费搜索会话信号，搜索结果页排序仍沿用 R-S07 term-heat 闭环。
  - 涉及文件: `quwoquan_service/services/search-service/**`（Redis 发布）、`quwoquan_service/services/content-service/internal/infrastructure/recommendation/**`、`quwoquan_service/scripts/ml/feature_registry.yaml`、`quwoquan_service/runtime/recpolicy/**`、`quwoquan_service/runtime/redis/**`。
  - 证据: `make verify-metadata`、`make verify-ml-features`、`python3 scripts/verify/verify_redis_keyspace.py`；`go test`/`go vet` 覆盖 search-service、content-service 推荐投影、`runtime/recommendation`、`runtime/recpolicy`、`runtime/redis`；Redis routes 与 `rec_policy_baseline.gen.go` 已重新生成。
  - 真实 T3 证据（2026-06-16 local-gamma 复验，补齐双服务端到端）: 先清理 `db0` 手工 XADD orphan（误判根因），再带 `X-User-Id: fixture_user_current` 冒烟 `POST :19280/v1/search`（成都火锅/九寨沟/鼓浪屿）。**发布**：`db1` stream `events.search.recommendation_signals` XLEN 2→5（+3，每次 result 检索一条）；**消费**：consumer group `content-service` `pending=0, entries-read=5, lag=0`；**投影**：`quwoquan_content.rm_recommend_feature`（userId=fixture_user_current）`userFeatures.searchTermAffinity` 含本轮全部查询词（九寨沟=1.27、成都火锅=1、鼓浪屿=1 等），`searchTermUpdatedAt=2026-06-16T06:27:47.885Z` 与冒烟同刻。证据落盘 `artifacts/local-gamma/search_signal_t3_report.json`。误判纠正：上一轮查 `db0`（只有 orphan）且冒烟未带 `X-User-Id` 导致 `recommend_feature.go` 对空 userId `return nil` skip —— 系**验证方法缺陷，非代码缺陷**。
  - 剩余风险（长稳项）: 真实多分片 OpenSearch + Redis cluster-mode 下的延迟/可靠性差异未压测；`RuleScorer` 实际把 `searchTermAffinity` 计入推荐 Feed 排序的线上 A/B 收益未度量（纳入 WP-F 推荐信号长稳，见 `search-storage-topology-and-elasticity` GWT2 planned）。
  - 状态: 已解决（2026-06-16；T1/T2 + 真实双服务 T3 端到端闭环已证；线上排序收益与真集群差异作长稳项）
- [x] R-S06-S 端到端 `/v1/search` 真实冒烟（衍生待办 3：local-gamma 实例化 search-service）
  - 区域: Ops
  - 域: `search`
  - 事项: local-gamma 实际运行栈已通过 stackctl 实例化 `search-service`（容器 `search-service:18095`，host `19280`，ES `quwoquan_objects`），并经 Caddy 网关完成 `/v1/search` 与 `/v1/search/feedback` 真实冒烟。
  - 影响: 搜索 T3（端云集成）已补齐真实链路证据；`/v1/search` 返回 ES-backed hit 与排序信封，`/v1/search/feedback` 返回 202 accepted。
  - 涉及文件: `deploy/local-gamma/**`、`quwoquan_service/docker-compose.gamma-local.yaml`、`quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh`、local-gamma stackctl 运行栈真相源。
  - 状态: 已解决（2026-06-16；证据：`python3 agent_ops/deploy/stackctl.py package --env gamma --include-services` → `artifacts/stackctl/gamma/20260616T041350Z-package-gamma-local`，含 `service package ready: artifacts/service-env-packages/search-service/gamma`；`python3 agent_ops/deploy/stackctl.py up --env gamma --skip-app` → `artifacts/stackctl/gamma/20260616T041612Z-up-gamma`，backfill `quwoquan_objects total=672 indexed=671 skipped=1` + places `posts=672 referenced=5 places=4`；`python3 agent_ops/deploy/stackctl.py health --target gamma-local --scope full` → `artifacts/stackctl/gamma/20260616T042515Z-health-gamma-local`，15/15 healthy，`search-service -> 200`；`python3 agent_ops/deploy/stackctl.py verify --env gamma --kind all --tier all` → `artifacts/stackctl/gamma/20260616T042741Z-verify-gamma-local`，15 checks passed；真实网关冒烟 `artifacts/local-gamma/search_smoke_report.json`：`POST https://gamma-api.quwoquan-env.test/v1/search` 返回 200、`requestId=search.req.1781584024537428163`、`rankingVersion=search-v1`、`hitsCount=5`、首条 `成都医学院`，`POST /v1/search/feedback` 返回 202 accepted）
  - 独立复核: 另一环境 worker 以 ES-enabled 路径复核 local-gamma，`stackctl up --target gamma-local --skip-app` 13 容器 healthy，`stackctl verify --env gamma --kind all` 10 checks passed；经网关 `POST http://127.0.0.1:19000/v1/search` 返回 200、真实 ES hit=5、`rankingVersion=search-v1`、`experimentBucket=term_heat`、hit 含 `rankReasons/rankPosition`；空 query 返回结构化 400，`/v1/search/feedback` 返回 202。
- [ ] R-S06-S-1 local-gamma ES 模拟环境性能与真集群差异
  - 区域: Ops
  - 域: `search`
  - 原因: Apple Silicon/Colima 下 local ES 使用 `platform: linux/amd64` 模拟以避开 arm64 JVM 初始化期 SIGILL；本地冷启动约 3-4 分钟，单次 `_bulk` 较慢，回填需较小 batch。
  - 影响: 不影响搜索功能正确性，但 local-gamma 启动与回填性能不能代表 CI/真实 ES/OpenSearch 集群；真集群需用原生镜像/托管集群重新校准 batch 与启动 SLA。
  - 涉及文件: `quwoquan_service/docker-compose.gamma-local.yaml`、`quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh`、ES/OpenSearch 部署配置。
  - 本轮交付（方法学 + 目标值，已落盘）: ①冻结高并发负载模型 `search_slo.yaml#load_model`（suggest/result/feedback/indexing 四类，baseline/peak/spike 的 RPS/并发/分位数/错误率/降级率/freshness/Redis lag 目标）；②容量校准方法学 + 按数据规模的 ES 拓扑推荐（shard 10–50GB 避免 oversharding、单节点 replicas=0/生产≥1+≥2 data node、≥半内存留 page cache、refresh 30s、bulk 校准、query cost guard）写入 `search-storage-topology-and-elasticity/spec.md#容量校准`；③local 证据：单节点 1shard/1replica 永久 yellow（replica unassigned）属模拟工件。
  - local-gamma 验证入口（2026-06-17 补齐）: `python3 quwoquan_service/scripts/search/verify_search_local_gamma_capacity.py` 聚合 stackctl gamma verify、ES health/index/shards/threadpool、小型 warm/cold/mixed/feedback 并发压测、单节点 repeatability、故障/回滚证据存在性，报告 `artifacts/local-gamma/search_r_s06_s1_local_gamma_report.json`。该报告固定声明 `r_s06_s1_closed_by_local_gamma=false`，只证明 local-gamma 方法学与单节点稳定性，不替代真集群 measured。
  - 未闭合（真实缺口，需真集群）: measured RPS/P95/P99、饱和点、最大稳定 RPS、推荐 shard/replica/节点规格与 refresh/bulk/circuit 实测阈值必须在真集群/prod-sim 原生 ES/OpenSearch 回填；本环境无真集群，属发布前阻断。压测/profiling 证据见 `artifacts/search-load/search_load_analysis.md` 与 `artifacts/search-load/search_e2e_hotpath_profile.md`（local 单节点 ES 为唯一瓶颈，result/suggest 高并发 NO-GO）。
  - 可重复性多副本兜底（并入本项）: 跨副本 `_score` 漂移需 ES `preference`（viewer/session/query 稳定派生路由）兜底；需通过 Searcher 透传查询参数实现，local 单节点无副本无法验证，随真集群里程碑实现验收。local 单节点重复查询已 0 跳变（`artifacts/local-gamma/search_repeatability_golden_diff.json`），稳定排序/AB 粘性已由单测闭环。
  - 纳入规划: WP-E 索引长稳（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」与 `search-storage-topology-and-elasticity` GWT2 planned）。
  - 状态: 待办（负载模型/容量方法学/拓扑推荐已冻结；真集群 measured 值与饱和点未采集 → 阻断）
- [ ] R-S06-S-2 搜索索引写时增量与 ES 重启恢复长稳验证
  - 区域: Service / Ops
  - 域: `search` / `content`
  - 原因: 本轮 T3 已证明起栈 host 端 backfill 后 `/v1/search` 可返回真实 ES hit；但 `content.search_index_worker` 写时投影器的常驻增量同步、ES 重启后索引一致性与补偿恢复尚未做长稳 T3。
  - 影响: 不影响当前搜索冒烟与静态门禁，但长期运行、内容更新、ES 重启或索引重建后的数据一致性仍缺运行证据。
  - 涉及文件: `quwoquan_service/services/content-service/internal/infrastructure/searchindex/**`、`quwoquan_service/services/content-service/internal/infrastructure/placeindex/**`、`quwoquan_service/runtime/search/es/**`、local-gamma stackctl 健康/回填脚本。
  - 部分证据（2026-06-16 ES 重启恢复 T3 已补）: 在运行中的 local-gamma 上 `docker restart elasticsearch`，ES 约 108s 恢复；索引 `quwoquan_objects` 文档数 **675→675 持久**；重启后经 search-service `/v1/search?q=成都` 恢复到与基线**完全一致的 TopN**（首条 `成都医学院`、5 命中、零降级信号）；count 与文档化 backfill（671 indexed + 4 places ≈ 675）一致。证据落盘 `artifacts/local-gamma/search_index_restart_recovery_t3.json`。单节点 + replicas=1 → cluster 永久 yellow（replica unassigned）属 local-gamma 单节点模拟工件（生产用 ≥2 data node + replicas≥1 转 green），非缺陷。
  - 部分证据（2026-06-16 故障/回滚演练补充）: `quwoquan_service/scripts/search/search_rollback_rehearsal.py` 在 gamma-local 对 ES/Redis/search-service 三类故障注入 + 回滚到已知良好态。**ES 宕机** → search-service fail-closed 返回 typed `503 SEARCH.MIDDLEWARE.unavailable`（`nature:transient`+用户文案，3.5ms 快速失败不挂起），ES 重启（~105s）后检索恢复一致 TopN；**Redis 失败** → 检索主路径仍 200/5 命中（信号发布 best-effort 不阻塞），content-service 消费侧保持 healthy，重启 6.1s 恢复；**search-service 不可用** → 受控连接拒绝（非超时挂起），重启回滚 6.1s 后 healthz 200 + 检索恢复；演练后 `stackctl health --target gamma-local --scope service` 8/8 healthy。证据落盘 `artifacts/local-gamma/search_rollback_rehearsal_report.json` + `artifacts/stackctl/gamma/search_rollback_rehearsal.md`。
  - 未闭合（保持待办）: ①写时增量长稳——内容 publish/update/下线触发常驻投影器的增量同步与持续 soak（需 content-service 写路径鉴权 + 长时运行）；②backfill 幂等再跑收敛同一 count；③真集群恢复 SLA 与 green（归 R-S06-S-1）。
  - 纳入规划: WP-E 索引长稳（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」与 `search-storage-topology-and-elasticity` GWT2 planned）。
  - 状态: 待办（ES 重启恢复 + 索引持久 + 搜索恢复分项已证；写时增量长稳/backfill 幂等再跑/真集群恢复仍缺运行证据）
- [ ] R-S06-S-3 search-service 独立 Go module 依赖图可复现性
  - 区域: Service / Ops
  - 域: `search`
  - 原因: `search-service` 是独立 Go module，容器构建依赖 `services/search-service/go.mod` 与 `go.sum` 的完整依赖图；排障中曾出现 `missing go.sum entry`，需确保新模块依赖锁文件纳入版本控制并由 CI 验证。
  - 影响: 若依赖图未被稳定提交，新环境或 CI 容器构建可能因缺失 `go.sum` 条目失败，影响 search-service 可复现构建。
  - 涉及文件: `quwoquan_service/services/search-service/go.mod`、`quwoquan_service/services/search-service/go.sum`、`deploy/service/search-service/Dockerfile`。
  - 已验证（代码就绪）: `go mod tidy && go test ./...`（search-service module）本地 exit 0；本轮复验 `go vet ./...`、`go build ./...`、`go test ./...`（search-service module）全 exit 0，依赖图可在本地重现解析（go.sum 142 行；`go mod verify` 仅对 local replace 目标 `quwoquan_service` 报 missing ziphash 属正常，非缺口）。
  - 未闭合（真实缺口）: `git ls-files quwoquan_service/services/search-service/go.mod go.sum` 为空 —— go.mod/go.sum 及整个 `services/search-service/` **仍是 git untracked**，并未纳入版本控制。上一轮「go.sum 已纳入版本控制」属状态虚报，本轮已纠正。CI 在干净检出上仍会因缺失锁文件失败。
  - CI 门禁（本轮新增收口工具）: `bash quwoquan_service/scripts/search/verify_search_service_module.sh [--with-tests]` —— 以「干净检出视角」断言 go.mod/go.sum/cmd/api/main.go/Dockerfile 必须 git-tracked，并 `go build ./...` 验证依赖图可解析。当前因 untracked **故意 RED**（=真实阻断信号）；用户提交后自动转 GREEN，本项即可闭合。
  - 收口动作（归属用户）: 由用户 git add/commit `services/search-service/`（含 go.mod/go.sum/Dockerfile）后，重跑上述门禁转绿，本项方可标记已解决；提交动作不在本轮 verify_only 范围内。
  - 纳入规划: WP-E 索引长稳（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 状态: 待办（代码就绪、依赖图本地可重现、CI 门禁已就位；待用户将 search-service 纳入版本控制后门禁转绿即闭合）

## 灵魂交集统一（端云，intersection-unification）

> 真相源 spec：`specs/feature-tree/object-homepage-network/intersection-unified-experience/`。WP-0/WP-1/WP-2 + WP-3（UCB 探索 + MMR 多样性）+ WP-4（交集特征回流 + ranking-signal-fusion 单点注入）已在主线完成（见各自单测/契约/verify 证据）。以下为我（代理）在授权下登记的、需独立或平台级会话推进的剩余事项，均附正确设计，杜绝在读路径或主线塞入错误耦合。

- [ ] R-IX01 AffinityReasons 概率分通道改由模型分驱动（异步物化，禁止读路径同步 RPC）
  - 区域: Service / Data
  - 域: `recommendation` → `content`
  - 原因: 当前 `MongoIntersectionSource.AffinityReasons` 用「圈子热看 / 关注的人在看」启发式按近度返回内容，未经 `/v1/score` 模型打分；`affinityIntersectionScore` 特征字段尚未真实填充。
  - 正确设计: 不得在 summary/list/feed 读路径同步调用 `/v1/score`（会破坏 WP-2 确立的事实读模型零打分、并对读路径引入模型服务硬依赖与尾延迟）。应由异步评分作业（或 challenger/shadow 离线管线）对 affinity 候选打分后，把 `affinityIntersectionScore` 与排序写入 `rm_viewer_object_intersection` 的 affinity 段，读路径仍零计算消费。
  - 已收口（2026-06-16 WP-F 不变量固化）: 读路径「零同步打分 + affinity 分数直出不重算」已固化为契约测试 `quwoquan_service/services/content-service/internal/application/intersection_readpath_invariant_test.go::TestIntersectionService_ReadPathZeroSynchronousScoring`——断言 `Feed` 对 `FactReasons/AffinityReasons` 各恰好拉取一次（无 per-candidate 重复打分循环）、不触达 `ObjectReasons`，预物化 `Strength`/`modelReasonBucket` 原样直出；`Summary/List` 只走事实通道。`IntersectionSource` 接口方法签名本身不含 scorer 参数，从类型层面保证读路径无模型服务硬依赖。该不变量防止未来回归到把 `/v1/score` 拉进读路径的错误设计。
  - 影响: 未做异步物化前概率分通道仍是启发式近度排序，`affinityIntersectionScore` 恒为 0；事实通道（已回流）不受影响，融合与排序主链路安全。读路径零同步打分已被契约测试锁定，异步评分作业落地后只需写 affinity 段即可，读路径无需改动。
  - 涉及文件: `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_source.go`、`viewer_object_intersection_store.go`、`runtime/recommendation/scorer.go`(RemoteModelScorer)、`internal/application/intersection_readpath_invariant_test.go`(不变量契约)、异步评分作业。
  - 状态: 待办（读路径零同步打分不变量已固化为契约测试；剩余为异步评分作业把模型分写入 affinity 段——平台级会话）
- [ ] R-IX02 viewer×object 关系交集 per-candidate 信号物化（P1 kind + 关系级精排融合的前置）
  - 区域: Service
  - 域: `recommendation` → `content`
  - 原因: 现有读模型/特征回流是 viewer 级聚合；真正「这条候选的作者是我与某对象的共同关注 / 来自我与好友共访实体」的 per-candidate 关系交集信号缺一个按社交图谱预计算的关系投影。WP-2 的 P1 kind（sharedFollowees/coVisitedEntity 等逐对象事实）与「关系级」精排融合都依赖它。
  - 正确设计: 新增按 viewer 预计算的关系交集投影（或扩展 `rm_viewer_object_intersection` 存逐 object 的关系事实），由社交图谱 + 共访/共评事件增量维护；读路径零计算消费；精排可在候选侧读取该 per-candidate 关系强度。
  - 影响: 未做前 P1 关系类 kind 仅在 ObjectReasons（单对象主页）可得，feed/list 的关系级 per-candidate 融合用 viewer 级揭示偏好近似（已交付，安全但非逐候选关系事实）。
  - 涉及文件: `quwoquan_service/contracts/metadata/recommendation/rec_model/projections/`、`services/content-service/internal/infrastructure/recommendation/`、`runtime/recommendation/scorer.go`。
  - 状态: 待办
- [ ] R-IX03 深度排序模型平台轨（MMoE/PLE/ESMM 多任务、双塔 ANN 在线服务、Thompson/IPS 反事实闭环）
  - 区域: Service / Data
  - 域: `recommendation`
  - 原因: 业界大厂精排的多任务深度模型、双塔向量召回在线服务、bandit reward 闭环与 IPS 去偏训练，是多周/多月平台工程，非单会话可闭环。
  - 现状安全基线: 多目标 LightGBM + champion/challenger + shadow 评估 + 晋升门禁 已是生产安全基线；WP-3 已补 UCB 曝光感知探索（去偏 + 冷启动，确定性可复现）与 MMR 多样性重排（policy 可选）。
  - 影响: 不阻塞主链路；为持续优化的长期能力上限。
  - 涉及文件: `quwoquan_service/services/rec-model-service/**`、`runtime/recommendation/**`、`scripts/ml/**`。
  - 状态: 待办
- [ ] R-IX04 精品池召回源（featured / 高完成率内容专用候选通道）——前置缺失：无 featuring 写入能力
  - 区域: Service / Data / Ops
  - 域: `content` → `recommendation`
  - 原因: WP-5 已在排序侧落地场景路由 + premium 预设（弱化纯热度、强化完成/停留/相关性，homepage/similar 场景启用），但召回侧尚无「精品池」专用候选通道。
  - 关键前置（2026-06-16 核实）: `Post.Featured`/`FeaturedAt` 字段在 `post.go` 已声明；本轮已补 circle-service 圈内动态精选写入（`FeatureCirclePost` 更新 `posts.featured/featuredAt`），但这只是圈子 feed 管理能力，不等同于 product-ops/编辑体系的全局「精品池」准入能力。若现在直接把普通 `featured` 字段当作全局精品池唯一来源，仍会把圈内运营动作与全站精选召回混为一谈，形成第二语义债。
  - 正确顺序: 先落地 product-ops「全局精选/编辑加权」写入能力（admin 标记 featured scope 或由完成率/质量分作业派生），再在 `rm_discovery_feed`（或 `rm_premium_pool`）投影补 featured scope + 质量分，最后建 `PremiumPoolSource`（按场景自门控，RecallPath=`premium_pool`，装配 engine sources 末位）。
  - 影响: 未做前精品场景的「优中选优」由排序侧 premium 预设承担（已上线，数据驱动）；召回候选仍是通用池。不阻塞主链路。
  - 涉及文件: `services/product-ops-service/**`(featuring 写入)、`services/content-service/internal/infrastructure/recommendation/`、`contracts/metadata/.../projections/`。
  - 状态: 待办（前置 featuring 能力缺失；现在建池=死基础设施，故正确决策是先补前置而非先建池）
- [ ] R-IX05 四主页云侧真实数据 + DDD 收口（WP-6，客户端+跨服务，字段漂移已收口）
  - 区域: App / Service
  - 域: `entity` / `circle` / `user`
  - 原因: 实体/人物/圈子/我的四主页的「云侧真实内容拉取」尚未全部脱离 seed/mock：实体主页需脱硬编码 seed 真实拉 content；用户/我的主页 `AuthorImpact` 与圈子主页 `CircleImpact` 需要 T3/T4 证明真实读路径。
  - 已收口（2026-06-16）: 客户端交集/四主页切片的破坏性字段漂移已修复：`IntersectionReason` 消费方从旧 `displayText/label/sharedCount` 迁到 `primaryText/connectionSummary/totalPointCount`；删除已删 `ObjectIntersection*` import 与孤儿二源 mapper `tag_intersection_mapper.dart`；`CircleImpactItem`/`AuthorImpactItem` UI 与 Mock 改读 `primaryText`；Go 侧 `CircleImpact`、`AuthorImpact`、entity fallback reason 输出字段对齐到 `primaryText/totalPointCount`。圈子 feed 管理的 `PinCirclePost`/`FeatureCirclePost` 已从 NO-OP 改为通过 `FeedStore` 持久化更新 `posts.pinned/pinnedAt`、`posts.featured/featuredAt`，并发布 `CirclePostPinned`/`CirclePostFeatured` 事件。`PostCount` 已从 seed-only 改为真实跨服务事件回写：content-service `PostPublished/PostDeleted/PostSettingsUpdated` payload 携带 `circleIds` 与 `addedCircleIds/removedCircleIds`，circle-service 订阅 Redis `events.content.*` 并按 published 状态门控增减 `circles.postCount`、同步失效缓存。`WeeklyActiveCount` 已从 seed-only 改为行为驱动窗口回写：`ReportBehavior` 对已加入成员刷新 `CircleMember.LastActiveAt`，按 `lastActiveAt >= now-7d` 重新计数后写 `circles.weeklyActiveCount`，不使用 `$inc`。`CircleImpact`/`AuthorImpact` 结论句已抽到共享 `runtime/impact`，服务只下发 `primaryText`，端不再拼装。验证：`go build ./services/content-service/... ./services/circle-service/... ./runtime/impact`、`go build ./...`（entity-service）、`go test ./runtime/impact ./services/content-service/internal/application/... ./services/content-service/tests ./services/circle-service/...`、`go test ./internal/application/...`（entity-service）、`go run ./tools/verify_metadata/ contracts/metadata` 均绿；`flutter analyze lib/` 无 error（剩余为既有 warning/info）。
  - 现状: 服务端推荐/交集引擎（WP-0~5）已完成并验证，为这些主页提供统一 Explain（`primaryText`/`connectionSummary`/affinity 标签）与场景路由（homepage→premium）。实体/用户/我的主页结构已具备 Remote path + provider + 契约 DTO；圈子主页的字段对齐、Pin/Feature、PostCount、WeeklyActive、CircleImpact 结论句均已接入真实写/解释路径。剩余主要是 beta/gamma/prod 真数据灌入与 T3/T4 端到端验收。
  - 影响: 编译级字段漂移不再阻塞；四主页在 beta/gamma/prod 仍可能展示 seed/mock 派生数据，需各域服务真实数据与 impact 回写后才能端到端闭环。
  - 涉及文件: `quwoquan_app/lib/ui/{entity,circle,user}/**`、`services/{entity,circle,user}-service/**`、`contracts/metadata/{social/circle,content/post}/projections/*impact*`。
  - 衍生待办（2026-06-16 gamma-local 实测）: `docker-compose.gamma-local.yaml` 当前只含 content/chat/user/assistant/product-ops/tag/search/rec-model 服务，**不含 `entity-service` 与 `circle-service`**；经网关 `/v1/homepages/*` 返回 404「local-gamma mirror route is not ready」，故四主页 detail（`/v1/homepages/{id}/object-page-bundle`）与圈子 impact（`/v1/circles/{id}/impact`）的 gamma-local T3 暂不可冒烟。content 交集 GET 路由（`/v1/content/intersections/object|summary`、`/v1/content/intersections`）已在运行栈内并强制 viewer 鉴权；populated 交集分组（connectionState / intersectionReason.primaryText）需网关可识别的真实 token + 已 seed 的 viewer 关系，当前匿名探测返回「需要登录」。证据：`artifacts/local-gamma/search_intersection_smoke.json`（`/v1/search` 200 ES-backed 杭州西湖、`/v1/content/feed` 200、`/v1/content/feed/intersections` 200 空、交集 GET 路由 viewer 鉴权）。要闭合：把 entity/circle-service 纳入 gamma-local compose + 网关路由 + seed viewer 关系后补 T3。本轮（gamma 远端退役真相源收敛，2026-06-16）：按「gamma 已取消远端、合入 local-gamma mirror + prod 生产灰度」口径，`deploy/shared/environment_topology_manifest.yaml` 的 `gamma` 块（publicBases/hostAllowlist/artifactPolicy.allowLocalHosts/distribution/forbiddenHostTokens）与 `quwoquan_app/configs/gamma/app_runtime.yaml`、`quwoquan_service/services/chat-service/configs/gamma/config.yaml` 已从远端 `118.31.239.122:1900x` 收敛为本地 `127.0.0.1:1900x`，并重打包 git 纳管的 gamma app/service env artifact（chat/platform-ops/product-ops，残留远端 IP 归零），与文档既定口径（`environment_matrix.md`、`prod_plane_access_isolation.yaml`、environment-ops SKILL）一致。证据：`verify_environment_topology_manifest`/`verify_gamma_local_prod_isomorphism`/`verify_env_artifact_isolation`/`verify_prod_package_purity` + `content_media_url_test`(8/8) + `verify_retired_terms_zero`/`verify_concept_naming` 全绿。结论：entity/circle 的接入目标明确为 **local-gamma compose**（非远端 gamma），真实远端集成由 **prod gray-initial** rollout stage 承接。
  - 状态: 待办（字段漂移、客户端编译断点、Pin/Feature 持久化、PostCount 跨服务回写、WeeklyActive 窗口回写、Impact Explain 归一已解决；剩余为 gamma-local entity/circle 拓扑接入 + 真实数据灌入 + viewer 鉴权 seed + 端到端验收）
- [ ] R-IX06 搜索六场景端侧收口 + 术语退场关注者（WP-7，客户端，部分由 R-S06/R-S07 覆盖）
  - 区域: App
  - 域: `search` / `user`
  - 原因: 搜索 hit 真实 `connectionState` 闭集 + `intersectionReason` 子集、搜索交集 Tab 去本地拼装、实体页双交集源收口单源、术语「关注者」退场为「粉丝/关注/成员」、交集 G2 单句，均为端侧文案/装配收口。
  - 现状: 搜索云侧读模型/接线已在 R-S05/R-S06/R-S07 详细跟踪；服务端交集理由闭集（kind §5.4 + connectionState）已由 WP-0~2/WP-4 在云侧统一。端侧搜索交集 Tab 的本地拼装去除已收口（见 R-003 已解决）：交集分组唯一真相源改为云侧 `connectionState` 闭集，交集句严格只读 `intersectionReason.primaryText`，无 primaryText 不展示，删除 `_deterministicCount`/`_fallbackConnectionCardModels`/`_fallbackDiscoverCardModels`/`_friendActionLabel`/`_knownIntersectionEntity`/`_discoverContentReason`，并补 `_IntersectionContractSearchRepository` 契约测试（10/10 green）。术语退场为「粉丝/关注/成员」在 user/circle/entity widgets 切片内同步。
  - 影响: 搜索结果页交集理由/连接态的客户端合成已去除（第二真相源风险闭合）；剩余 R-008 跟踪的一般搜索 demo 回退（空集 fallback、硬编码实体置顶）与术语退场逐页核对。
  - 涉及文件: `quwoquan_app/lib/ui/search/**`、`quwoquan_app/lib/components/object_page/**`、`quwoquan_app/lib/ui/{user,circle,entity}/widgets/*`（术语）。
  - 状态: 待办（搜索交集 Tab 本地拼装去除已解决 R-003；剩余术语逐页核对 + R-008 一般 demo 回退 + R-S06/R-S07 端云读模型联动）
- [ ] R-IX07 交集统一端到端验收：T3/T4 + 观测/SLO/灰度 + 全量 make gate（WP-8）
  - 区域: App / Service / Ops
  - 域: `recommendation` / `search` / 多域
  - 原因: 服务端推荐/交集引擎（WP-0~5）的 T1（契约/静态）与 T2（模块/单测）证据已绿（content-service 全量 `go test`、`runtime/recommendation`、`runtime/recpolicy`、`verify-metadata`、`verify-ml-features`）。端云一体 T3（端云集成）、T4（用户旅程）、`make codegen-app` + 全量 `make gate` 需在客户端切片（R-IX05/R-IX06）与各域服务一并落地后统一验收。
  - 已收口（2026-06-16 WP-E 观测）: 交集业务 SLI 漏斗指标已落地——`intersection_feed_candidates_total{channel,class,rank_state}`、`intersection_feed_filtered_total{channel,reason}`、`intersection_cooldown_exposure_reported_total`、`intersection_inbox_visit_total{dimension}`、`intersection_inbox_filtered_total{reason}`（DDD-clean：recorder 接口在 application、Prometheus 实现在 `infrastructure/intersectionmetrics`、main.go 注入），funnel 发射有单测 `intersection_metrics_test.go`。HTTP 延迟/错误/可用性走 `runtime/observability` http_server_* 中间件按 route 过滤。SLO 声明 `configs/observability/intersection_slo.yaml`（P95/可用性/重复曝光率/保鲜过滤率/展示完备率/事实占比/清零量 + 三级回滚分层），告警组 `deploy/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_intersection`（4 条）。端侧曝光/点击/转化归因字段在 `content_behavior_tracker.dart` + `intersection_attribution_test.dart`（T2 绿）。
  - 影响: 观测/SLO/告警/回滚分层已定义并有真实指标源；剩余 gamma 真实采样需 R-IX05 拓扑/鉴权 seed；T4 用户旅程与全量 `make gate` 待客户端切片合流。
  - 本轮 gate 实测（2026-06-16 三 scope 复跑）: **三 scope gate 全绿** —— `bash agent_ops/gate/gate_repo.sh --scope service` → `[gate] OK`（`/tmp/gate_service_next.log`）；`--scope data` → `[gate] OK`（`agent-tools` 输出末行 `[gate] OK`），本轮修复 `quwoquan_data/tests/verify/test_directory_evidence_gate.py` 两个 happy-path fixture（`test_gate_entity_homepage_writes_review_sidecars`、`test_gate_passes_clean_object`）补齐实体主页 `2.quality/quality_analysis.json` + 百科底稿 + asset `sourceRef/sourceAssetRef/termsUrl`，与本轮收紧的 `build/homepage.py` 实体主页证据校验（quality sidecar + 图片权利链）对齐，`directory evidence gate tests passed (18)`；`--scope app` → `[gate] OK` / `APP_GATE_EXIT=0`（`/tmp/gate_app_next.log`）。**此前 R-IX07 把全量 `make gate` 阻断归因到仓库级术语门禁的描述已失效**：`python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py` → `OK`、`python3 quwoquan_app/scripts/runtime/verify_concept_naming.py` → `[concept-naming] OK`，两处此前红灯均已转绿（上一轮 allowlist + 改词收口）。**全量 `make gate` 已绿**：`make gate`（部署/拓扑验证器 + global increment + agent context + 三 scope + portal 构建）→ `[gate] OK` / `FULL_GATE_EXIT=0`（`/tmp/gate_full_next.log`，4945 行；日志内两处 `download Gate FAILED`/`task run FAILED` 系负路径测试 `test_handle_download_blocks_unsafe_images_before_persist` 等的预期断言输出，非真实门禁失败）。
  - 涉及文件: `specs/feature-tree/object-homepage-network/intersection-unified-experience/acceptance.yaml`、`specs/feature-tree/global-search-experience/.../acceptance.yaml`、各域 T3/T4 测试、`quwoquan_data/tests/verify/test_directory_evidence_gate.py`、`quwoquan_data/scripts/build/homepage.py`、`quwoquan_service/services/content-service/configs/observability/intersection_slo.yaml`、`deploy/monitoring/alerts/quwoquan_alerts.yaml`。
  - 状态: 待办（服务端 T1/T2 与观测/SLO/告警已绿；app/service/data 三 scope gate 与仓库级术语门禁均绿；剩余为端到端 T3/T4（gamma entity/circle 拓扑 + viewer 鉴权 seed）与 T4 用户旅程，详见 R-IX05/gamma-homepages 与 intersection-t4 工作包）
