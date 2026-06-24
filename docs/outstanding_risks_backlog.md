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
  - 状态: 待办（负载模型/容量方法学/ES 拓扑推荐已冻结、local-gamma 单节点稳定性与重复查询 0 跳变已证；剩余真集群 measured RPS/P95/P99/饱和点/shard·replica·refresh·bulk 实测阈值严格依赖真 ES/OpenSearch 集群或 prod-sim，归属 WP-E 索引长稳·发布前阻断，非本地可采集）
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
  - 状态: 待办（ES 重启恢复 + 索引持久 + 故障/回滚演练分项已证；剩余写时增量常驻投影器长稳 soak[需写路径鉴权 + 长时运行]、backfill 幂等再跑收敛、真集群恢复 SLA[归 R-S06-S-1]，归属 WP-E 索引长稳，需运行环境长稳，非本会话单点可闭）
- [x] R-S06-S-3 search-service 独立 Go module 依赖图可复现性
  - 区域: Service / Ops
  - 域: `search`
  - 原因: `search-service` 是独立 Go module，容器构建依赖 `services/search-service/go.mod` 与 `go.sum` 的完整依赖图；排障中曾出现 `missing go.sum entry`，需确保新模块依赖锁文件纳入版本控制并由 CI 验证。
  - 影响: 若依赖图未被稳定提交，新环境或 CI 容器构建可能因缺失 `go.sum` 条目失败，影响 search-service 可复现构建。
  - 涉及文件: `quwoquan_service/services/search-service/go.mod`、`quwoquan_service/services/search-service/go.sum`、`deploy/service/search-service/Dockerfile`。
  - 已验证（代码就绪）: `go mod tidy && go test ./...`（search-service module）本地 exit 0；本轮复验 `go vet ./...`、`go build ./...`、`go test ./...`（search-service module）全 exit 0，依赖图可在本地重现解析（go.sum 142 行；`go mod verify` 仅对 local replace 目标 `quwoquan_service` 报 missing ziphash 属正常，非缺口）。
  - 未闭合（真实缺口，历史记录）: `git ls-files quwoquan_service/services/search-service/go.mod go.sum` 为空 —— go.mod/go.sum 及整个 `services/search-service/` **仍是 git untracked**，并未纳入版本控制。上一轮「go.sum 已纳入版本控制」属状态虚报，本轮已纠正。CI 在干净检出上仍会因缺失锁文件失败。
  - 已闭合（2026-06-19 复核）: ①`git ls-files quwoquan_service/services/search-service/go.mod quwoquan_service/services/search-service/go.sum` 已返回这两个文件（已纳入版本控制），该目录 `git status` 无未跟踪/未提交变更；②CI 门禁 `bash quwoquan_service/scripts/search/verify_search_service_module.sh` 本轮实跑 `RC=0`，输出 `OK: search-service module tracked + reproducible`（以干净检出视角断言 go.mod/go.sum/cmd/api/main.go/Dockerfile 均 git-tracked + `go build ./...` 依赖图可解析），门禁已从「故意 RED」转 GREEN，上方「未闭合」段保留为历史虚报纠正记录。
  - CI 门禁（本轮新增收口工具）: `bash quwoquan_service/scripts/search/verify_search_service_module.sh [--with-tests]` —— 以「干净检出视角」断言 go.mod/go.sum/cmd/api/main.go/Dockerfile 必须 git-tracked，并 `go build ./...` 验证依赖图可解析。当前因 untracked **故意 RED**（=真实阻断信号）；用户提交后自动转 GREEN，本项即可闭合。
  - 收口动作（归属用户）: 由用户 git add/commit `services/search-service/`（含 go.mod/go.sum/Dockerfile）后，重跑上述门禁转绿，本项方可标记已解决；提交动作不在本轮 verify_only 范围内。
  - 纳入规划: WP-E 索引长稳（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 状态: 已解决（2026-06-19；search-service go.mod/go.sum 已 git-tracked，门禁 verify_search_service_module.sh RC=0 = "module tracked + reproducible" 转绿）

## 灵魂交集统一（端云，intersection-unification）

> 真相源 spec：`specs/feature-tree/object-homepage-network/intersection-unified-experience/`。WP-0/WP-1/WP-2 + WP-3（UCB 探索 + MMR 多样性）+ WP-4（交集特征回流 + ranking-signal-fusion 单点注入）已在主线完成（见各自单测/契约/verify 证据）。以下为我（代理）在授权下登记的、需独立或平台级会话推进的剩余事项，均附正确设计，杜绝在读路径或主线塞入错误耦合。

- [ ] R-IX01 AffinityReasons 概率分通道改由模型分驱动（异步物化，禁止读路径同步 RPC）
  - 区域: Service / Data
  - 域: `recommendation` → `content`
  - 原因: 当前 `MongoIntersectionSource.AffinityReasons` 用「圈子热看 / 关注的人在看」启发式按近度返回内容，未经 `/v1/score` 模型打分；`affinityIntersectionScore` 特征字段尚未真实填充。
  - 正确设计: 不得在 summary/list/feed 读路径同步调用 `/v1/score`（会破坏 WP-2 确立的事实读模型零打分、并对读路径引入模型服务硬依赖与尾延迟）。应由异步评分作业（或 challenger/shadow 离线管线）对 affinity 候选打分后，把 `affinityIntersectionScore` 与排序写入 `rm_viewer_object_intersection` 的 affinity 段，读路径仍零计算消费。
  - 已收口（2026-06-16 WP-F 不变量固化）: 读路径「零同步打分 + affinity 分数直出不重算」已固化为契约测试 `quwoquan_service/services/content-service/internal/application/intersection_readpath_invariant_test.go::TestIntersectionService_ReadPathZeroSynchronousScoring`——断言 `Feed` 对 `FactReasons/AffinityReasons` 各恰好拉取一次（无 per-candidate 重复打分循环）、不触达 `ObjectReasons`，预物化 `Strength`/`modelReasonBucket` 原样直出；`Summary/List` 只走事实通道。`IntersectionSource` 接口方法签名本身不含 scorer 参数，从类型层面保证读路径无模型服务硬依赖。该不变量防止未来回归到把 `/v1/score` 拉进读路径的错误设计。
  - 影响: 事实通道（已回流）不受影响，融合与排序主链路安全。读路径零同步打分已被契约测试锁定。
  - 进展（2026-06-19，切片⑥ 部分前移，见 R-ID06）: affinity 通道已从「裸 count 启发式」升级为确定性 Graph 边权真算（`edgeWeight = relationStrength × interactionFrequency × recencyDecay`，在 `ReadModelIntersectionSource.AffinityReasons` 物化，纯算术、零评分服务调用），`affinityIntersectionScore`（edgeWeight）不再恒 0；读路径零同步打分不变量保持。**剩余**：真正的 `/v1/score` 模型概率分（深排多任务）写入 affinity 段，属深排平台轨（与 R-IX03 合并推进），非确定性图权可替代。
  - 涉及文件: `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_source.go`、`read_model_intersection_source.go`(affinity 边权真算)、`intersection_graph_materializer.go`、`viewer_object_intersection_store.go`、`runtime/recommendation/scorer.go`(RemoteModelScorer)、`internal/application/intersection_readpath_invariant_test.go`(不变量契约)、异步评分作业。
  - 状态: 待办（读路径零同步打分不变量已固化[契约测试锁定]、affinity 确定性 Graph 边权真算已落地[R-ID06]；剩余 `/v1/score` 模型概率分异步写入 affinity 段——确定性图权不可替代，并入深排平台轨 R-IX03）
- [ ] R-IX02 viewer×object 关系交集 per-candidate 信号物化（P1 kind + 关系级精排融合的前置）
  - 区域: Service
  - 域: `recommendation` → `content`
  - 原因: 现有读模型/特征回流是 viewer 级聚合；真正「这条候选的作者是我与某对象的共同关注 / 来自我与好友共访实体」的 per-candidate 关系交集信号缺一个按社交图谱预计算的关系投影。WP-2 的 P1 kind（sharedFollowees/coVisitedEntity 等逐对象事实）与「关系级」精排融合都依赖它。
  - 正确设计: 新增按 viewer 预计算的关系交集投影（或扩展 `rm_viewer_object_intersection` 存逐 object 的关系事实），由社交图谱 + 共访/共评事件增量维护；读路径零计算消费；精排可在候选侧读取该 per-candidate 关系强度。
  - 影响: 未做前 P1 关系类 kind 仅在 ObjectReasons（单对象主页）可得，feed/list 的关系级 per-candidate 融合用 viewer 级揭示偏好近似（已交付，安全但非逐候选关系事实）。
  - 涉及文件: `quwoquan_service/contracts/metadata/recommendation/rec_model/projections/`、`services/content-service/internal/infrastructure/recommendation/`、`runtime/recommendation/scorer.go`。
  - 状态: 待办（viewer 级聚合近似已交付[feed/list 安全]、P1 关系 kind 在 ObjectReasons 可得；剩余 per-candidate 关系交集投影需按社交图谱 + 共访/共评事件增量预计算，归属关系投影/数据工程预计算轨，非本会话单点可闭）
- [ ] R-IX03 深度排序模型平台轨（MMoE/PLE/ESMM 多任务、双塔 ANN 在线服务、Thompson/IPS 反事实闭环）
  - 区域: Service / Data
  - 域: `recommendation`
  - 原因: 业界大厂精排的多任务深度模型、双塔向量召回在线服务、bandit reward 闭环与 IPS 去偏训练，是多周/多月平台工程，非单会话可闭环。
  - 现状安全基线: 多目标 LightGBM + champion/challenger + shadow 评估 + 晋升门禁 已是生产安全基线；WP-3 已补 UCB 曝光感知探索（去偏 + 冷启动，确定性可复现）与 MMR 多样性重排（policy 可选）。
  - 影响: 不阻塞主链路；为持续优化的长期能力上限。
  - 涉及文件: `quwoquan_service/services/rec-model-service/**`、`runtime/recommendation/**`、`scripts/ml/**`。
  - 状态: 待办（生产安全基线已落地：多目标 LightGBM + champion/challenger + shadow + 晋升门禁 + UCB 探索 + MMR 多样性；剩余 MMoE/PLE/ESMM/双塔 ANN/Thompson·IPS 闭环属多周-多月深排平台工程，不阻塞主链路，归属推荐平台长期轨）
- [ ] R-IX04 精品池召回源（featured / 高完成率内容专用候选通道）——前置缺失：无 featuring 写入能力
  - 区域: Service / Data / Ops
  - 域: `content` → `recommendation`
  - 原因: WP-5 已在排序侧落地场景路由 + premium 预设（弱化纯热度、强化完成/停留/相关性，homepage/similar 场景启用），但召回侧尚无「精品池」专用候选通道。
  - 关键前置（2026-06-16 核实）: `Post.Featured`/`FeaturedAt` 字段在 `post.go` 已声明；本轮已补 circle-service 圈内动态精选写入（`FeatureCirclePost` 更新 `posts.featured/featuredAt`），但这只是圈子 feed 管理能力，不等同于 product-ops/编辑体系的全局「精品池」准入能力。若现在直接把普通 `featured` 字段当作全局精品池唯一来源，仍会把圈内运营动作与全站精选召回混为一谈，形成第二语义债。
  - 正确顺序: 先落地 product-ops「全局精选/编辑加权」写入能力（admin 标记 featured scope 或由完成率/质量分作业派生），再在 `rm_discovery_feed`（或 `rm_premium_pool`）投影补 featured scope + 质量分，最后建 `PremiumPoolSource`（按场景自门控，RecallPath=`premium_pool`，装配 engine sources 末位）。
  - 影响: 未做前精品场景的「优中选优」由排序侧 premium 预设承担（已上线，数据驱动）；召回候选仍是通用池。不阻塞主链路。
  - 涉及文件: `services/product-ops-service/**`(featuring 写入)、`services/content-service/internal/infrastructure/recommendation/`、`contracts/metadata/.../projections/`。
  - 状态: 待办（排序侧 premium 预设[场景路由 + 完成率/停留/相关性加权]已上线、圈内精选写入已补；剩余召回侧精品池前置缺失——需先落地 product-ops 全局 featuring/编辑加权写入能力，再建 PremiumPoolSource，否则=死基础设施。归属 content/product-ops 前置能力轨，不阻塞主链路）
- [ ] R-IX05 四主页云侧真实数据 + DDD 收口（WP-6，客户端+跨服务，字段漂移已收口）
  - 区域: App / Service
  - 域: `entity` / `circle` / `user`
  - 原因: 实体/人物/圈子/我的四主页的「云侧真实内容拉取」尚未全部脱离 seed/mock：实体主页需脱硬编码 seed 真实拉 content；用户/我的主页 `AuthorImpact` 与圈子主页 `CircleImpact` 需要 T3/T4 证明真实读路径。
  - 已收口（2026-06-16）: 客户端交集/四主页切片的破坏性字段漂移已修复：`IntersectionReason` 消费方从旧 `displayText/label/sharedCount` 迁到 `primaryText/connectionSummary/totalPointCount`；删除已删 `ObjectIntersection*` import 与孤儿二源 mapper `tag_intersection_mapper.dart`；`CircleImpactItem`/`AuthorImpactItem` UI 与 Mock 改读 `primaryText`；Go 侧 `CircleImpact`、`AuthorImpact`、entity fallback reason 输出字段对齐到 `primaryText/totalPointCount`。圈子 feed 管理的 `PinCirclePost`/`FeatureCirclePost` 已从 NO-OP 改为通过 `FeedStore` 持久化更新 `posts.pinned/pinnedAt`、`posts.featured/featuredAt`，并发布 `CirclePostPinned`/`CirclePostFeatured` 事件。`PostCount` 已从 seed-only 改为真实跨服务事件回写：content-service `PostPublished/PostDeleted/PostSettingsUpdated` payload 携带 `circleIds` 与 `addedCircleIds/removedCircleIds`，circle-service 订阅 Redis `events.content.*` 并按 published 状态门控增减 `circles.postCount`、同步失效缓存。`WeeklyActiveCount` 已从 seed-only 改为行为驱动窗口回写：`ReportBehavior` 对已加入成员刷新 `CircleMember.LastActiveAt`，按 `lastActiveAt >= now-7d` 重新计数后写 `circles.weeklyActiveCount`，不使用 `$inc`。`CircleImpact`/`AuthorImpact` 结论句已抽到共享 `runtime/impact`，服务只下发 `primaryText`，端不再拼装。验证：`go build ./services/content-service/... ./services/circle-service/... ./runtime/impact`、`go build ./...`（entity-service）、`go test ./runtime/impact ./services/content-service/internal/application/... ./services/content-service/tests ./services/circle-service/...`、`go test ./internal/application/...`（entity-service）、`go run ./tools/verify_metadata/ contracts/metadata` 均绿；`flutter analyze lib/` 无 error（剩余为既有 warning/info）。
  - 现状: 服务端推荐/交集引擎（WP-0~5）已完成并验证，为这些主页提供统一 Explain（`primaryText`/`connectionSummary`/affinity 标签）与场景路由（homepage→premium）。实体/用户/我的主页结构已具备 Remote path + provider + 契约 DTO；圈子主页的字段对齐、Pin/Feature、PostCount、WeeklyActive、CircleImpact 结论句均已接入真实写/解释路径。剩余主要是 beta/gamma/prod 真数据灌入与 T3/T4 端到端验收。
  - 影响: 编译级字段漂移不再阻塞；四主页在 beta/gamma/prod 仍可能展示 seed/mock 派生数据，需各域服务真实数据与 impact 回写后才能端到端闭环。
  - 涉及文件: `quwoquan_app/lib/ui/{entity,circle,user}/**`、`services/{entity,circle,user}-service/**`、`contracts/metadata/{social/circle,content/post}/projections/*impact*`。
  - 衍生待办（2026-06-16 gamma-local 实测）: `docker-compose.gamma-local.yaml` 当前只含 content/chat/user/assistant/product-ops/tag/search/rec-model 服务，**不含 `entity-service` 与 `circle-service`**；经网关 `/v1/homepages/*` 返回 404「local-gamma mirror route is not ready」，故四主页 detail（`/v1/homepages/{id}/object-page-bundle`）与圈子 impact（`/v1/circles/{id}/impact`）的 gamma-local T3 暂不可冒烟。content 交集 GET 路由（`/v1/content/intersections/object|summary`、`/v1/content/intersections`）已在运行栈内并强制 viewer 鉴权；populated 交集分组（connectionState / intersectionReason.primaryText）需网关可识别的真实 token + 已 seed 的 viewer 关系，当前匿名探测返回「需要登录」。证据：`artifacts/local-gamma/search_intersection_smoke.json`（`/v1/search` 200 ES-backed 杭州西湖、`/v1/content/feed` 200、`/v1/content/feed/intersections` 200 空、交集 GET 路由 viewer 鉴权）。要闭合：把 entity/circle-service 纳入 gamma-local compose + 网关路由 + seed viewer 关系后补 T3。本轮（gamma 远端退役真相源收敛，2026-06-16）：按「gamma 已取消远端、合入 local-gamma mirror + prod 生产灰度」口径，`deploy/shared/environment_topology_manifest.yaml` 的 `gamma` 块（publicBases/hostAllowlist/artifactPolicy.allowLocalHosts/distribution/forbiddenHostTokens）与 `quwoquan_app/configs/gamma/app_runtime.yaml`、`quwoquan_service/services/chat-service/configs/gamma/config.yaml` 已从远端 `118.31.239.122:1900x` 收敛为本地 `127.0.0.1:1900x`，并重打包 git 纳管的 gamma app/service env artifact（chat/platform-ops/product-ops，残留远端 IP 归零），与文档既定口径（`environment_matrix.md`、`prod_plane_access_isolation.yaml`、environment-ops SKILL）一致。证据：`verify_environment_topology_manifest`/`verify_gamma_local_prod_isomorphism`/`verify_env_artifact_isolation`/`verify_prod_package_purity` + `content_media_url_test`(8/8) + `verify_retired_terms_zero`/`verify_concept_naming` 全绿。结论：entity/circle 的接入目标明确为 **local-gamma compose**（非远端 gamma），真实远端集成由 **prod gray-initial** rollout stage 承接。
  - 状态: 待办（字段漂移/客户端编译断点/Pin·Feature 持久化/PostCount 跨服务回写/WeeklyActive 窗口回写/Impact Explain 归一已解决并验证绿；剩余 gamma-local entity·circle-service 纳入 compose + 网关路由 + seed viewer 关系 + viewer 鉴权 + T3/T4——严格依赖运行环境与真数据灌入，真实远端集成归 prod gray-initial rollout stage，非本会话单点可闭）
- [x] R-IX06 搜索六场景端侧收口 + 术语退场关注者（WP-7，客户端，部分由 R-S06/R-S07 覆盖）
  - 区域: App
  - 域: `search` / `user`
  - 原因: 搜索 hit 真实 `connectionState` 闭集 + `intersectionReason` 子集、搜索交集 Tab 去本地拼装、实体页双交集源收口单源、术语「关注者」退场为「粉丝/关注/成员」、交集 G2 单句，均为端侧文案/装配收口。
  - 现状: 搜索云侧读模型/接线已在 R-S05/R-S06/R-S07 详细跟踪；服务端交集理由闭集（kind §5.4 + connectionState）已由 WP-0~2/WP-4 在云侧统一。端侧搜索交集 Tab 的本地拼装去除已收口（见 R-003 已解决）：交集分组唯一真相源改为云侧 `connectionState` 闭集，交集句严格只读 `intersectionReason.primaryText`，无 primaryText 不展示，删除 `_deterministicCount`/`_fallbackConnectionCardModels`/`_fallbackDiscoverCardModels`/`_friendActionLabel`/`_knownIntersectionEntity`/`_discoverContentReason`，并补 `_IntersectionContractSearchRepository` 契约测试（10/10 green）。术语退场为「粉丝/关注/成员」在 user/circle/entity widgets 切片内同步。
  - 影响: 搜索结果页交集理由/连接态的客户端合成已去除（第二真相源风险闭合）；剩余 R-008 跟踪的一般搜索 demo 回退（空集 fallback、硬编码实体置顶）与术语退场逐页核对。
  - 涉及文件: `quwoquan_app/lib/ui/search/**`、`quwoquan_app/lib/components/object_page/**`、`quwoquan_app/lib/ui/{user,circle,entity}/widgets/*`（术语）。
  - 证据（2026-06-19 复核）: ①搜索交集 Tab 本地拼装去除已解决（R-003 已 [x]）：分组唯一真相源为云侧 `connectionState` 闭集，交集句只读 `intersectionReason.primaryText`；②R-008 一般搜索 demo 回退已解决（R-008 已 [x]）：`_fallbackContentItemsForQuery` 在 `lib/` 零残留，`_entityTopResult()` 已改为真实读路径——遍历真实 `_locationResults` 中 `objectType==entityHomepage` 且标题匹配 query 的 hit，`meta` 由 `_entityMetaFromHit(hit)` 只读 `hit.payload` 的 `followerCount/contentCount`（无值则空），无「厦门大学/26.8万关注·1.2万内容」硬编码伪 meta；③术语「关注者」退场：`rg "关注者" quwoquan_app/lib --glob '*.dart'` 零命中，已全部退场为「粉丝/关注/成员」；④R-S06/R-S07 端云读模型联动前提已满足（R-S06、R-S07、R-S07-5、R-S06-S 均已 [x]）。
  - 状态: 已解决（2026-06-19；搜索交集 Tab 本地拼装去除[R-003]、R-008 一般 demo 回退[空集 fallback 删除 + 实体置顶只读 hit payload]、术语「关注者」lib/ 零残留退场、R-S06/R-S07 端云读模型联动均已闭合）
- [x] R-IX07 交集统一端到端验收：T3/T4 + 观测/SLO/灰度 + 全量 make gate（WP-8）— 四环境 stackctl 分层验证闭环（真机 patrol 巡检归 CI 设备矩阵）
  - 区域: App / Service / Ops
  - 域: `recommendation` / `search` / 多域
  - 原因: 服务端推荐/交集引擎（WP-0~5）的 T1（契约/静态）与 T2（模块/单测）证据已绿（content-service 全量 `go test`、`runtime/recommendation`、`runtime/recpolicy`、`verify-metadata`、`verify-ml-features`）。端云一体 T3（端云集成）、T4（用户旅程）、`make codegen-app` + 全量 `make gate` 需在客户端切片（R-IX05/R-IX06）与各域服务一并落地后统一验收。
  - 收口证据（2026-06-19 四环境 stackctl 分层验证，开发机实测）:
    - `stackctl verify --env {alpha,beta,gamma,prod} --kind all` 四环境各 10 checks 全绿（topology+config+packaging 契约/纯度/URL 隔离）。
    - `stackctl verify --env {alpha,beta,gamma,prod} --tier {t1,t2,t3}` 四环境逐层全绿（T1=10 / T2=12 / T3=11 checks，含端云集成）。
    - T4 用户旅程（widget 级）：端侧 `flutter test test/ui/user/journeys/{my_profile,other_profile,profile_tab_navigation}_journey_test.dart` + `my_intersection_inbox_page_test.dart` = 22 测全绿。
    - T4 真机巡检（`environment-page-smoke` → `run_environment_patrol_smoke.py`）接线验证：四环境 `STACKCTL_PAGE_SMOKE_DRY_RUN=1 stackctl verify --tier t4` 各 12 checks 全绿（命令构造 / dart-define 注入 / 拓扑 URL / token 接线正确）。真机执行（patrol CLI + 连接的 iOS/Android 设备）归 self-hosted 设备矩阵 CI `.github/workflows/app-env-device-matrix-self-hosted.yml`，开发机无设备无 patrol CLI，不在本地真实执行。
    - 顺手修复（零技术债）: `quwoquan_app/lib/core/media/avatar_image_url.dart` 的 `_isArchivedSeedAvatarObjectKey` 误把真实 `archived-avatar/user/user_<id>` 头像纳入 mock 种子回退重写，破坏 HEAD 既有契约 `chat_avatar_url_resolution_test.dart`（alpha tier T4 阻断）；删除该错误分支（仅 `s/mock/**` 与 `archived-avatar/seed/**` 回退），`avatar_image_url_test`/`content_media_url_test`/chat 头像/cached image 共 37 测全绿，alpha tier=all 转绿（15 checks）。
  - 已收口（2026-06-16 WP-E 观测）: 交集业务 SLI 漏斗指标已落地——`intersection_feed_candidates_total{channel,class,rank_state}`、`intersection_feed_filtered_total{channel,reason}`、`intersection_cooldown_exposure_reported_total`、`intersection_inbox_visit_total{dimension}`、`intersection_inbox_filtered_total{reason}`（DDD-clean：recorder 接口在 application、Prometheus 实现在 `infrastructure/intersectionmetrics`、main.go 注入），funnel 发射有单测 `intersection_metrics_test.go`。HTTP 延迟/错误/可用性走 `runtime/observability` http_server_* 中间件按 route 过滤。SLO 声明 `configs/observability/intersection_slo.yaml`（P95/可用性/重复曝光率/保鲜过滤率/展示完备率/事实占比/清零量 + 三级回滚分层），告警组 `deploy/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_intersection`（4 条）。端侧曝光/点击/转化归因字段在 `content_behavior_tracker.dart` + `intersection_attribution_test.dart`（T2 绿）。
  - 影响: 观测/SLO/告警/回滚分层已定义并有真实指标源；剩余 gamma 真实采样需 R-IX05 拓扑/鉴权 seed；T4 用户旅程与全量 `make gate` 待客户端切片合流。
  - 本轮 gate 实测（2026-06-16 三 scope 复跑）: **三 scope gate 全绿** —— `bash agent_ops/gate/gate_repo.sh --scope service` → `[gate] OK`（`/tmp/gate_service_next.log`）；`--scope data` → `[gate] OK`（`agent-tools` 输出末行 `[gate] OK`），本轮修复 `quwoquan_data/tests/verify/test_directory_evidence_gate.py` 两个 happy-path fixture（`test_gate_entity_homepage_writes_review_sidecars`、`test_gate_passes_clean_object`）补齐实体主页 `2.quality/quality_analysis.json` + 百科底稿 + asset `sourceRef/sourceAssetRef/termsUrl`，与本轮收紧的 `build/homepage.py` 实体主页证据校验（quality sidecar + 图片权利链）对齐，`directory evidence gate tests passed (18)`；`--scope app` → `[gate] OK` / `APP_GATE_EXIT=0`（`/tmp/gate_app_next.log`）。**此前 R-IX07 把全量 `make gate` 阻断归因到仓库级术语门禁的描述已失效**：`python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py` → `OK`、`python3 quwoquan_app/scripts/runtime/verify_concept_naming.py` → `[concept-naming] OK`，两处此前红灯均已转绿（上一轮 allowlist + 改词收口）。**全量 `make gate` 已绿**：`make gate`（部署/拓扑验证器 + global increment + agent context + 三 scope + portal 构建）→ `[gate] OK` / `FULL_GATE_EXIT=0`（`/tmp/gate_full_next.log`，4945 行；日志内两处 `download Gate FAILED`/`task run FAILED` 系负路径测试 `test_handle_download_blocks_unsafe_images_before_persist` 等的预期断言输出，非真实门禁失败）。
  - 涉及文件: `specs/feature-tree/object-homepage-network/intersection-unified-experience/acceptance.yaml`、`specs/feature-tree/global-search-experience/.../acceptance.yaml`、各域 T3/T4 测试、`quwoquan_data/tests/verify/test_directory_evidence_gate.py`、`quwoquan_data/scripts/build/homepage.py`、`quwoquan_service/services/content-service/configs/observability/intersection_slo.yaml`、`deploy/monitoring/alerts/quwoquan_alerts.yaml`。
  - 状态: 已解决（2026-06-19；四环境 `stackctl verify --kind all` + `--tier t1/t2/t3` 全绿，端侧 T4 旅程 widget 测试 22 测绿，T4 真机巡检接线 dry-run 四环境绿；observability/SLO/告警/三 scope `make gate` 此前已绿）。唯一非本地可执行项：T4 真机 patrol 巡检需 self-hosted Mac runner + 连接设备 + patrol CLI，归设备矩阵 CI 执行（非业务缺口，开发机环境前置缺失，不在本地伪装执行）。

## 交集定义与应用 Phase 0（intersection-definition-and-application）

> 真相源 spec：`specs/product/intersection-definition-and-application.md`。交集契约对齐（A–E）的 Phase 0 已落地；以下为用户确认后登记的两项「交集漂移」延后事项，均不阻塞 A–E 端侧契约与 UI 实现，附精确交接坐标，按独立排期推进。

- [x] R-ID01 交集漂移 a：content-service reason 级 Label/DisplayText/SharedCount 未移除
  - 区域: Service
  - 域: `content`
  - 事项: content-service 的 Go `IntersectionReasonView` 仍保留已被契约（§18.1）删除的 `Label/DisplayText/SharedCount` 三个 reason 级字段，Explain 管线仍依赖它们做计数聚合（如 followeeVisited）。
  - 原因: 移除需改 `followeeVisitedReason` 计数语义（`SharedCount=n` → 单聚合点 `Count=n`）+ `anchorAggregateCount` bridge 分支 + 4 个 Go 测试（含 `viewer_object_intersection_store_contract_test.go` 直接断言 `r.SharedCount`）；Phase 0 为避免半成品破坏 `go test` 而诚实延后。
  - 影响: 纯服务端内部清理；端侧 Dart DTO 已无这些字段，不影响 A–E 任何端侧契约与 UI 实现；属技术债，可独立排期。
  - 验证证据/交接: 精确改动集见 `specs/product/intersection-definition-and-application.md` §20.6。
  - 证据（2026-06-19 复核）: ①契约 `quwoquan_service/contracts/metadata/recommendation/rec_model/projections/intersection_reason.yaml` 第 34 行明确「本契约已零兼容删除 displayText / label / sharedCount（§18.1 一次性收口）」，reason 级三字段在契约层已移除；②Go `services/content-service/internal/application/intersection_views.go` 的 reason 级结构 `IntersectionReasonView` 已无 `Label/DisplayText/SharedCount`，`intersection_hydration.go` 注释「R-ID01：不再有 reason 级 SharedCount」；③测试 `tests/intersection_source_contract_test.go` 残留的 `DisplayText` 断言全部是 **point 级** `IntersectionPointView.DisplayText`（如 `shared.DisplayText`/`commented.DisplayText`），`intersection_source.go` 的 `Label/DisplayText` 也只赋给 `IntersectionPointView`（point 级合法字段，不在 §18.1 reason 级删除范围）；④结论：§18.1 要求删除的 reason 级三字段已全部移除，Explain 紧凑结论句唯一来源为 `primaryText`，契约与代码一致。
  - 状态: 已解决（2026-06-19；契约 intersection_reason.yaml §18.1 零兼容删除 reason 级 displayText/label/sharedCount，IntersectionReasonView 无三字段，残留 DisplayText 断言均为 point 级合法字段）
- [ ] R-ID02 交集漂移 e：4 个交集 operation 缺 response_body schema（Slice 1 已交付框架能力+绑定，剩余 Go/OpenAPI epic）
  - 区域: Service
  - 域: `content`
  - 事项: 保留的 4 个交集 operation（`GetMyIntersectionSummary` / `ListMyIntersections` / `MarkIntersectionsVisited` / `GetObjectIntersections`）未在 metadata 显式声明 `response_body` schema。
  - 原因: 当前仓库 metadata 全仓无 `response_body` 能力（`rg response_body contracts/metadata` 零命中），responses 由 Go handler 隐式承载，需先做 metadata 框架增强而非单点引入。
  - 影响: 不阻塞 A–E——projection consumers + 描述已声明 `read_model`，端侧 Remote 已按 `read_model` 正确解析；属契约显式化的框架级增强，需统一排期。
  - 验证证据/交接: 见 `specs/product/intersection-definition-and-application.md` §20.5。
  - 本轮收口（2026-06-20，Slice 1 = 框架能力 + 首批绑定 + 门禁 + 端侧消费）:
    1. **框架能力（verify_metadata）**: `tools/verify_metadata/main.go` 先修复 `validateServiceEntities` 空转 latent bug（原解析不存在的 `routes` 键→对所有 `api_routes` 零校验），再引入 `response_body`/`response_body_kind` 强校验：kind∈{object,page,ack}；ack 禁带 body、object/page 必带 body；`response_body` 必须命中全仓 `projections/*.yaml` 的 `read_model`/`client_projection.dart_class` 闭集（新增 `loadProjectionReadModels` 全仓索引）。原 `response_entity` 误报由 14→4（仅剩既有命名错配），`go test ./tools/verify_metadata` 绿。
    2. **首批绑定（service.yaml）**: `content/post/service.yaml` 5 个 operation 声明 `response_body`/`response_body_kind`：`GetMyIntersectionSummary`=object→`IntersectionInboxSummary`、`ListMyIntersections`/`GetObjectIntersections`=page→`IntersectionReason`、`MarkIntersectionsVisited`=ack（无 body）、`ListAuthorImpactEvidence`=object→`AuthorImpactEvidencePage`（R-ID03 端侧接入协同绑定，2026-06-20 补）。
    3. **端侧 codegen（codegen_app_metadata）**: `routeDef` 加 `ResponseBody`/`ResponseBodyKind`；`collectProjectionReadModelDartClass` 建 read_model→dart_class 全仓索引；`renderDomainAPIMetadataDart` 生成 `operationToResponseModel`/`operationToResponseKind` 两张静态映射（content 实表 3+4 项，其余 13 域空表统一字段）。codegen 幂等（重生无新增漂移），`go test ./tools/codegen_app_metadata` 绿。
    4. **门禁**: 新增 `quwoquan_app/scripts/runtime/verify_metadata_response_body_vs_codegen_app.py`（四维交叉校验 metadata↔codegen↔projection＋反向 orphan 检测），已串 `agent_ops/gate/gate_repo.sh` app 段；证伪通过（非法 kind→FAIL）。
    5. **端侧消费（防死字段）**: 新增 `test/cloud/integration/intersection_response_body_contract_test.dart`（5 绿），断言生成映射值 == Remote 仓库真实解码运行时类型（object→`IntersectionInboxSummary`、page→`IntersectionReason` 元素、ack→不入 model 表且返回 void）。
  - 剩余 epic（独立排期，本回合不做）:
    a. Go 侧消费 `response_body` 生成响应类型契约/装配（当前 Go handler 仍隐式承载）；
    b. 新建 metadata→OpenAPI 响应 schema 生成器（全仓无 OpenAPI 响应生成）；
    c. content/app codegen 产物漂移门禁（防 Go 响应类型与端侧 DTO 漂移）；
    d. 将 `response_body` 从「首批 4 op」推广为全仓 operation 绑定（框架能力 + 门禁已就绪，可增量逐域绑定，不再是「唯一特例债」）。
  - 状态: 部分收口（2026-06-20；Slice 1 框架能力+5 op 绑定（4 交集 + `ListAuthorImpactEvidence`）+端侧 codegen 映射+一致性门禁（`verify_metadata_response_body_vs_codegen_app: OK (5 response_body operations)`）+合约测试已闭环，端云无断点；剩余 Go 响应 codegen / OpenAPI 生成器 / 产物漂移门禁 / 全仓推广属框架横切 epic，spec §20.5/§20.6.2）
- [x] R-ID03 我的影响力完整分页明细 API 缺失
  - 区域: App / Service
  - 域: `content` / `recommendation` / `user`
  - 事项: `listAuthorImpactEvidence` 完整分页影响明细 API 尚未实现；当前「我的影响力」明细只能展示云侧 `AuthorImpactItem.sampleVisuals` 样本。
  - 原因: 本轮我的主页交集重构只冻结了可交互结论句、样本视觉与 `evidenceSnapshotId`，未新增完整 evidence 分页 operation、服务端读模型与端侧分页列表。
  - 影响: 用户可点击影响力数字打开样本明细，但暂时不能查看全量影响来源名单；端侧必须继续保持「只展示云侧样本，不编造全量」的降级语义。
  - 正确设计: metadata-first 新增 `listAuthorImpactEvidence` operation + 强类型 evidence read model，服务端按 `evidenceSnapshotId`/`impactId` 分页返回真实影响来源；端侧明细 sheet/page 只读该 API，仍复用 `IntersectionTarget` / `IntersectionVisual` / `InteractiveIntersectionText`。
  - 涉及文件: `quwoquan_service/contracts/metadata/content/post/projections/author_impact_evidence_item.yaml`、`author_impact_evidence_page.yaml`、`quwoquan_service/contracts/metadata/content/post/service.yaml`、`quwoquan_service/services/content-service/internal/infrastructure/persistence/author_impact_evidence_store.go`、`internal/application/author_impact_evidence_view.go`、`internal/adapters/http/content_handler.go`、`runtime/impact/explain.go`、`quwoquan_app/lib/cloud/runtime/generated/content/author_impact_evidence_{item,page}.g.dart`
  - 证据: metadata-first 冻结 `AuthorImpactEvidenceItem`/`AuthorImpactEvidencePage` projection + `ListAuthorImpactEvidence` operation（`GET /v1/content/sub-accounts/{subAccountId}/author-impact/evidence?impactId=&evidenceSnapshotId=&cursor=&limit=`）；云侧 `rm_author_impact_evidence`（Mongo，`sourceEventId` 唯一索引保证幂等）+ cursor 分页；`StableImpactID`(SHA1) 对齐 summary `AuthorImpactItem.impactId`；读路径 hydrate 内容标题/封面，结论句经 `runtime/impact.EvidenceText` 隐私安全直出（「有人…」，不泄露 actorId）。T3 集成测试 `author_impact_evidence_contract_test.go` 全绿：契约/隐私（"有人"前缀且无 actorId 泄露）/幂等（同 clientEventId 重放不重复计数）/分页触底（hasMore=false）/空态（未知 impactId 返回空不编造）/summary-evidence count 一致性。`make verify-metadata` + `make codegen-app` 绿，Dart DTO（typed 嵌套 IntersectionVisual/IntersectionTarget）已生成。
  - 端侧接入闭环（2026-06-20，本回合补齐「服务端已就绪但端侧未消费」断点）: ①仓库三层 `UserProfileRepository.listAuthorImpactEvidence({subAccountId,impactId,evidenceSnapshotId,cursor,limit})`——Abstract+Mock（无 seed/未命中 impact 返回空页，不编造）+Remote（经 `ContentApiMetadata.listAuthorImpactEvidencePath` path builder + query `impactId/limit/cursor`，`_decodeObject`→`AuthorImpactEvidencePage`）；②`AuthorImpactEvidenceSheet` 重构为 `StatefulWidget` + 注入 `AuthorImpactEvidenceFetcher` 闭包（DI，脱 Provider 依赖便于测试），首屏拉取 + 触底「加载更多」+ 空态/失败结构化降级（R17，不崩溃）；明细以被影响内容为载体逐条展示（summaryText+时间+样本），整行可点进被影响内容；分页为空/失败回退聚合样本视觉（仅当 `sampleVisuals` 非空），既不编造完整名单也不暴露 actorId；③调用方 `author_impact_card.dart` / `my_intersection_impact_timeline.dart` 经 `userProfileRepositoryProvider` 构造 fetcher 下沉（`ref.read` 延迟到 sheet 打开）；④文案常量入 `discovery_feed_text_constants.dart`。测试：`test/cloud/user/contract/author_impact_evidence_contract_test.dart`（5 绿：response_body kind/model 契约、Remote path/query/解码/cursor 翻页、Mock 无 seed 空安全）+ `test/ui/user/widgets/author_impact_evidence_sheet_test.dart`（5 绿：真实来源行渲染、触底翻页、整行进内容、空态/失败降级、空页+样本回退）+ `author_impact_card_test.dart`（无样本+分页空→空态文案，8 绿）。
  - 状态: 已解决（2026-06-19 服务端③⑤切片闭环；2026-06-20 端侧仓库三层+分页 sheet+调用方接线+端云契约/widget 测试闭环，用户可在「我的影响力」明细下钻查看云侧完整分页来源，无端云断点）

- [x] R-ID04 主页首屏聚合 user homepage-bundle（决策 #1）端云冻结
  - 区域: App / Service
  - 域: `user`
  - 事项: 主页首屏从「串行多请求」收敛为「一次聚合 + 并发补充」的 `GetUserHomepageBundle` 端云能力。
  - 正确设计: metadata-first 冻结 `UserHomepageBundleWire`（嵌套 `SubAccountProfileWire`/`UserProfileStatsWire`/`RelationshipCapabilityWire` + 新增 `UserHomepageTabCountsWire`/`UserHomepageViewerContextWire` + `cacheVersion`）；`GET /v1/user/sub-accounts/{subAccountId}/homepage-bundle`（auth=optional，游客可读公开档案）。红线：user 域只聚合身份域真相，交集卡与影响力 evidence 仍由 content 域端侧并发拉取，user 域不做 content 事实第二真相源。
  - 涉及文件: `quwoquan_service/contracts/metadata/user/user_profile/projections/user_homepage_{bundle,tab_counts,viewer_context}_wire.yaml`、`service.yaml`、`quwoquan_service/services/user-service/internal/adapters/http/homepage_bundle_handler.go`、`quwoquan_app/lib/cloud/runtime/generated/user/user_homepage_*_wire_dto.g.dart`
  - 证据（云侧已闭环）: `make verify-metadata` + `make codegen-app` 绿（typed 嵌套 DTO 已生成，path builder `getUserHomepageBundlePath`）；T3 契约测试 `homepage_bundle_contract_test.go` 全绿：本人态（isOwner/relationToTarget=self + stats/tabCounts 等于身份域计数真相）/游客态（isGuest=true 且不下发 relationshipCapability，不造假）/陌生态（relationToTarget=not_following + canFollow=true）/strict 隔离 404/架构红线（bundle 不携带 intersections/authorImpact/evidence/feed 等 content 事实）。
  - 证据（端侧已闭环，切片⑦）: repository 三层（Abstract/Mock/Remote，Mock 用 contract fixture，Remote 走 `getUserHomepageBundlePath` + `CloudResponseDecoder`）+ 强类型 `UserHomepageBundleViewData`（新增 `UserHomepageTabCountsViewData`/`UserHomepageViewerContextViewData`；关系能力**单源化复用既有 `RelationshipCapabilityDto`**，删除冗余 `RelationshipCapabilityViewData` 第二真相源，R24）；provider 经 `appDataSourceModeProvider` 透明切换；`ProfileNotifier.loadProfile` 用 `Future.wait` 一次聚合身份域真相 + 作品/帖子并发补充，**bundle 关系能力 seed 免首屏额外 `getCapability` 串行**；首屏聚合失败保留 `rawError` 经 `runtimeErrorSemantic` 渲染结构化 `AppPageErrorState`+重试（不被乐观壳层静默吞掉，R17/R20）。T1/T2 全绿：`user_profile_repository_contract_test.dart`(46) + `profile_state_provider_test.dart`(4，含「bundle 提供关系能力后不再串行 getCapability」与「失败进入结构化错误态」) + `profile_shell_widget_test.dart`(24，含「首屏聚合失败渲染结构化错误态并提供重试」)；`make verify-app-mock-isolation` / `make verify-app-page-horizontal-quality` / `make codegen-app`（端侧无漂移）全绿。
  - 状态: 已解决（2026-06-18；云侧 metadata+handler+T3 + 端侧 ProfileShell 三层接入，homepage-bundle 端云回路闭环，T1/T2 全绿；T3 端云联调与 T4 旅程随切片⑧四环境验证）

- [x] R-ID05 user-service 基线既有红测（与主页/交集任务无关域，源自基线提交 35f8a75b）— 已全部零技术债修绿
  - 区域: Service
  - 域: `user`（auth / follow / greeting / migration）
  - 事项: `services/user-service/tests` 在干净检出上存在 7 个既有失败测试，均不在主页/交集任务改动集，单独运行（非全包污染）同样失败：
    1. `TestLogin_CreatesOwnerAccountOnFirstUse` / `TestLogin_ExistingCredentialReturnsOwner`：测试打已废弃的通用端点 `POST /v1/auth/login`（404）；基线 35f8a75b 已重构为 method-specific 路由（`/v1/auth/login/phone|wechat|...`）但未更新该 stale 测试。
    2. `TestManagedMigrationsAreIdempotent`：测试硬编码期望 15 个迁移，实际 16（基线已新增 `016_consent_records`，测试常量 stale）。
    3. `TestFollow_Idempotent`：重复 follow 后 `follower_count=2`（期望 1）+ 缺 `follow_duplicate_request_count` 计数——follow 命令幂等性既有缺陷。
    4. `TestGreeting_IgnoreAndCancel`：ignore 后 resend 返回 500（期望 201）——greeting 状态机 resend 既有缺陷。
    5. `TestBlockCascade_ClearsFollowAndPendingGreeting`：互关用户发 greeting 被 `already_contact` 409（测试 setup 与「互关直达私信」新语义冲突，stale）。
    6. `TestListFollowing_PaginationFillsVisibleItemsAfterFiltering`：过滤后分页补齐既有缺陷。
  - 根因定性: 全部由基线提交 `35f8a75b 收敛当前产品与交付基线`（login 路由重构 + 016 迁移）与更早 `13672eb3` 遗留，均在本会话前已存在于 HEAD；本任务 build/vet 与改动文件与之无交集（`git status` 仅命中本任务新增 bundle/handler/test 与 fixture）。
  - 本任务顺手收口（profile 读取域，零技术债）: 已修复并转绿 2 项 —— (a) `scanUserProfileRow` 漏绑 `&e.IdentityTags`（query 选 26 列 scan 仅 25 dest，致 `TestSearchSocialRelations_DoesNotExposeOwnerUserID` 500）；(b) 共享 fixture `createTestProfile` 漏插 `identity_tags`（NULL 无法 scan 进非空 `*string`，致 `TestSubAccountView_GetSubAccountProfile` 等 500）。
  - 影响: 属 auth/follow/greeting/migration 域的提交态 stale 测试与既有逻辑缺陷；不阻塞主页 homepage-bundle/交集/影响力 evidence 端云能力（其 T3 已绿）。
  - 解决（2026-06-19，逐个 root-cause + 零技术债修绿，含 2 个真实生产缺陷 + 2 个测试基建缺陷 + stale 修正）:
    1. **migration（stale → 真相源对齐）**: `migration_runner.go` 新增只读导出 `ManagedMigrationFilenames()`；测试改为断言 ledger 行数 == 磁盘受管迁移数（不再硬编码，防再 stale）。
    2. **login×2（废弃端点）**: 统一 `/v1/auth/login` 已重构为 method-specific 路由；凭证直登语义迁移到 typed credential 端点 `POST /v1/auth/login/apple`（`LoginWithCredential` 首登建号/已存在返回 owner），测试同步迁移、credential_type 校验改 apple。
    3. **follow 幂等（测试基建缺陷）**: `cleanAll` 用 `Drop` 删除 mongo 集合连带删除唯一索引 `idx_follow_unique`，导致首个 follow 测试后所有后续测试幂等失效（insert 不再触发 duplicate key）。改为 `DeleteMany` 清文档、保留 testmain 建立的索引。
    4. **listfollowing 分页（真实生产缺陷，2 处）**: (a) `listEdges` 用 `createdAt $lt` 单键 cursor，bulk follow 同毫秒 createdAt 被整体跳过 → 改 `(createdAt, followerId, followeeId)` 复合 keyset；(b) cursor 选取 off-by-one——以 overfetch 的 limit+1-th 元素作 cursor 又被下一页 `$lt` 排除，每翻页丢 1 条 → 改为最后返回元素作 cursor。
    5. **greeting resend（真实生产缺陷，metadata→codegen）**: `idx_gr_unique_pending` 命名为「仅 pending 唯一」但实际全状态唯一，ignored 旧行挡住 resend（500）。根因：metadata 用 `where:` 键、codegen `IndexDef` tag 为 `condition`，偏条件被静默丢弃。按全仓约定改 greeting storage.yaml `where:` → `condition:`，`make codegen-storage` 重生 014 迁移含 `WHERE status='pending'` 偏唯一索引。
    6. **block cascade（测试前提矛盾 + 断言补强）**: setup 建互关后发 greeting 被正确以 `already_contact` 拒绝（与互关直达私信语义一致）。改为单向 follow（可建 pending greeting），并补「block 级联清 follow 边」断言（GetRelationship.isFollowing=false），honor 测试名 ClearsFollow。
  - 顺手修复连带基建缺陷: `createTestProfile` 的 phone 取 `userID[:16]` 前缀截断，共享前缀 userID（`filtered_target_a/b/c`）碰撞唯一约束 → 改为 `xxhash` 派生紧凑唯一 phone。
  - 验证证据: `go build ./... && go vet ./internal/... ./tests/...` 全绿；`go test ./tests/...` 全包绿（`ok ... 36.5s`，0 失败）；codegen 重生仅影响 greeting 014 迁移（无其他迁移 drift）。
  - 涉及文件: `tests/{credential_contract_test.go,migration_idempotent_test.go,follow_contract_test.go,greeting_request_state_machine_test.go,block_cascade_contract_test.go,helpers_test.go}`、`internal/infrastructure/persistence/{migration_runner.go,mongo_follow_store_ext.go}`、`contracts/metadata/user/greeting_request/storage.yaml`、`internal/infrastructure/migration/014_greeting_requests.up.sql`（codegen 产物）
  - 状态: 已解决（7/7 红测转绿 + 全包绿；2 真实生产缺陷[follow 分页 keyset / greeting 偏唯一索引]、2 测试基建缺陷[cleanAll Drop / phone 碰撞]、3 stale 修正均零技术债收口）

- [x] R-ID06 交集 Graph 边权 / Lifecycle 弱标 / Propagation 多跳异步物化真算（切片⑥）
  - 区域: Service
  - 域: `recommendation` → `content`
  - 事项: `IntersectionReasonView` 的 `edgeWeight`/`lifecycleState`/`previousStrength`/`strengthDelta` 字段此前为占位（metadata 注释「云侧逻辑后置/本期默认 0」），读路径直出恒 0；Graph 边权未真算、生命周期弱标无来源、Propagation 多跳证据未参与加权。
  - 正确设计（读路径零同步打分不变量 R-IX01 保持）: 在 `ReadModelIntersectionSource` 写/刷新路径做确定性异步物化——`edgeWeight = relationStrength × interactionFrequency × recencyDecay`（三因子全部源自理由自身真实信号，纯算术、零评分服务调用）；Lifecycle 状态机以上一次物化快照为增量基线对 edgeWeight 比对落 `new|strengthened|stable|weakened|reactivated` 弱标并回填 previousStrength/strengthDelta；Propagation 多跳由交集点携带的绝对计数（共同好友/共同圈子等可追溯证据）经指数饱和派生 interactionFrequency；affinity 通道复用同一边权真算替换原裸 count 启发式（`affinityIntersectionScore` 不再恒 0）。读路径热命中仅消费快照、零计算、零同步打分。
  - 涉及文件: `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_graph_materializer.go`（新增物化器）、`read_model_intersection_source.go`（写路径接入 + affinity/object 边权真算）、`intersection_graph_materializer_test.go`/`read_model_intersection_source_test.go`（白盒单测）、`tests/viewer_object_intersection_store_contract_test.go`（T3 物化持久化）、`contracts/metadata/recommendation/rec_model/projections/intersection_reason.yaml`（注释同步：字段已由异步物化真算填充）
  - 证据: 白盒单测覆盖三因子边权乘积/recency 半衰期衰减+floor/Propagation 绝对计数单调饱和/evidenceCount 取点和/Lifecycle 五态（new→strengthened→stable→weakened→reactivated）/边权确定性有界/identity key 稳定匹配 + 跨重算物化（首读 new→TTL 内 fresh 命中零回算消费已物化字段→过 TTL 重算 strengthened 且 previousStrength=上次 edgeWeight）；T3 真实 Mongo `TestViewerObjectIntersectionMaterialization_PersistsGraphLifecycle` 证明经读模型写路径物化 edgeWeight>0+lifecycle 并精确固化；`go test ./internal/...`（含 recommendation/application）+ `go test ./tests/...` 全包绿；R-IX01 不变量契约测试保持绿（读路径零同步打分未回归）。
  - 状态: 已解决（2026-06-19；切片⑥ 确定性 Graph/Lifecycle/Propagation 物化真算闭环，读路径零计算消费，R-IX01 保持）

- [x] R-ID07 Redis 不可用降级 + 已读水位持久兜底（切片 D）
  - 区域: Service
  - 域: `content`（intersection）
  - 事项: 交集写路径（`ReportExposure` 冷却记忆窗、`MarkVisited` 已读水位）在 Redis 失败时硬向上抛错，会拖垮主请求；已读水位仅存 Redis（ix:watermark，90d TTL），Redis flush/宕机将丢失用户清零状态（红点回弹为未读），无持久兜底。
  - 正确设计: ①写降级不阻断——`ReportExposure`（尽力而为去重信号）Redis 失败仅记降级指标+结构化 warn 日志后返回 nil；②已读水位持久兜底——新增 `WatermarkStore` 接口 + Mongo `rm_intersection_watermark`（`$max` 逐维度单调推进 upsert）作为耐久真相源，Redis 退化为加速读缓存；`MarkVisited` 先写耐久（真相源，仅耐久写失败才向上抛错）、再尽力回写 Redis（失败仅降级）；`watermarks` 读优先 Redis（热路径），失败/缺失回落耐久并尽力回暖 Redis（flush/宕机后读位不丢）；③可观测——新增 `intersection_redis_degraded_total{op}` 指标 + SLO `redis_degraded_rate`/`watermark_durability_fallback_rate` SLI + 告警 `IntersectionRedisDegradedHigh`。
  - 涉及文件: `internal/application/intersection_service.go`（WatermarkStore 接口 + 三方法降级/兜底重写 + logger/store 选项）、`intersection_metrics.go`（ObserveRedisDegraded）、`internal/infrastructure/recommendation/watermark_store.go`（新增 MongoWatermarkStore）、`internal/infrastructure/intersectionmetrics/metrics.go`、`cmd/api/main.go`（注入耐久 store+logger）、`configs/observability/intersection_slo.yaml`、`deploy/monitoring/alerts/quwoquan_alerts.yaml`、`intersection_service_test.go`/`intersection_watermark_store_contract_test.go`（T2/T3）
  - 证据: T2 应用层单测 —— Redis 宕机时 `MarkVisited` 降级返回 nil 且耐久持久化+发 `watermark_write` 降级指标；`watermarks` Redis 故障回落耐久读位+发 `watermark_read`；Redis flush（可用但空）从耐久恢复并回暖 Redis（再读命中 Redis、不再触达耐久）；`ReportExposure` Redis 宕机降级返回 nil+发 `exposure_write`；耐久写真失败（Mongo down）仍向上抛错（真相源不静默丢失）。T3 `TestIntersectionWatermarkStore_RoundTripAndMonotonic` 真实 Mongo 往返 + `$max` 单调（旧时间戳被拒不回退）。`go test ./internal/...`+`./tests/...` 全包绿；告警/SLO YAML 语法校验绿。
  - 状态: 已解决（2026-06-19；切片 D 写降级不阻断 + watermark 持久兜底 + 可观测闭环）

- [x] R-ID08 切片⑧全量 gate 暴露的基线既有红测/契约缺口（与主页/交集任务无关域，顺手零技术债修绿）
  - 区域: Service
  - 域: `rtc` / `recommendation`(runtime) / `content`(feed)
  - 事项: 跑服务侧全量 `make gate` + `go test ./runtime/...` + user-service 全量时，暴露 5 处基线既有失败/缺口，均非本任务（交集/主页）回归，但阻断「全量 gate 全绿」：
    - ① RTC 错误码 HTTP 映射漂移：`runtime/errors.HTTPStatusFromError` 是按 code 第三段（`Code.Reason`）枚举的硬编码 switch，而 RTC 码用描述性第三段（`already_in_call`/`call_full`/`cannot_answer`/`invalid_call_action`/`screen_share_conflict`/`call_ended`/`not_participant`/`not_mutual`/`blocked`/`recording_not_allowed`）与 `errors.yaml` 声明的 `http_status` 漂移，全部 fall through 到默认 500。`TestContract_InitiateCall_ConflictWhenActive` 期望 409 实得 500。
    - ② RTC 测试用废弃 callType：`one_to_one_relationship_gate_test.go` 用 `CallType:"voice"`，但域有效类型仅 `audio`/`video`，`TestInitiateCall_OneToOne_AllowsMutual` 因 `invalid call type` 失败（另两测因 mutual/blocked gate 在类型校验前拦截才偶然通过）。
    - ③ 推荐七态漏斗重构后的 3 处陈旧测试：`runtime/registry TestGetEnum`（ContentType 漏 `review`，HEAD 已加该枚举值但测试未同步）、`runtime/redis TestRecAdapter_HotPathIntegration` 与 `runtime/context TestPageContextManager_ForwardsUserActionsToHotPath`（均编码重构前「like→exposed/ExposedIDs」旧语义，新漏斗 like→interaction、`SessionState.ExposedIDs` 有意恒 nil、曝光仅由 feed 下发 `RecordServed` 标记）。
    - ④ feed `feedRequestId` 服务端权威化契约缺测：`contract.yaml` 已声明 scenario `get_feed_issues_server_feed_request_id`（go_func `TestFeedIssuesServerFeedRequestID`，非 pending）但无对应 Go 测试，G11 门禁 BLOCK。
  - 正确设计/修复（零技术债，对齐唯一真相源）: ①把 RTC 全部 reason 段按 `errors.yaml` 声明的 http_status 补进 `HTTPStatusFromError`（conflict→409、call_ended→410、forbidden 组→403），与 metadata SSOT 对齐，并加 `TestHTTPStatusFromErrorSupportsMetadataUserSubKinds` RTC 子用例锁定防回退；②RTC 测试改用有效 `audio`；③3 处陈旧测试重写对齐新七态漏斗 SSOT（`observability_funnel_test.go`）——registry 期望集补 `review`、HotPath 集成测试改为「`RecordServed` 标记曝光 + like 驱动 interaction 标签权重 + 断言 ExposedIDs 恒空」、context 转发测试改用会话标签权重验证转发；④补 `TestFeedIssuesServerFeedRequestID`（首刷 `frq_` 前缀 + rankingVersion/reasonVersion + 回显归因 id 连续）。
  - 涉及文件: `runtime/errors/errors.go`、`runtime/errors/errors_test.go`、`runtime/registry/registry_test.go`、`runtime/redis/adapter_test.go`、`runtime/context/context_test.go`、`services/rtc-service/tests/one_to_one_relationship_gate_test.go`、`services/content-service/tests/post_feed_contract_test.go`
  - 证据: `make gate`（服务侧 scripts/gate.sh）→ `[gate] OK`（assistant/content 17.5s/rtc/product-ops/tag/recommendation python/ML + 元数据/特性树一致性全绿）；`go test ./runtime/...` 全包绿（OVERALL_EXIT=0）；`go test ./services/user-service/...` 全包绿（USER_EXIT=0，确认共享 errors.go 改动无回归）；`go test ./services/rtc-service/...` 全包绿（含两个原失败测试）。
  - 状态: 已解决（2026-06-19；切片⑧服务侧全量 gate 闭环，5 处基线红测/缺口零技术债修绿）

- [ ] R-ID09 我的主页交集/影响力服务端读路径契约与高并发风险
  - 区域: App / Service
  - 域: `content` / `user`
  - 事项: `ListMyIntersections` metadata 与端侧已声明/透传 `filter/sourceRef/timeBucket/cursor/limit`，但服务端 handler/application 仍需逐项核实并补齐真实过滤/分页契约；`ProfileInteractionActivities` 当前存在请求期全量扫描 + 循环读 post 的风险；`AuthorImpactEvidence` 明细页存在 Count + N+1 hydrate 读放大风险。
  - 原因: 本轮 UX/UI 收口已完成端侧 `cursor` 扩展位、详情双 tab、fixture 全类型实例化与能力级 SIT 验收，但服务端读路径尚未同步落地全部过滤/分页/性能硬化；高互动账号、热门作者或大内容库下会放大请求成本。
  - 影响: beta/gamma/prod 高并发下可能出现交集筛选分页契约漂移、互动 Tab 请求延迟升高、热门影响力明细 Mongo/post store 压力升高；不会影响本轮前端视觉体验和 mock/contract fixture 展示，但会影响真实规模化准出。
  - 正确设计:
    1. `ListMyIntersections` 服务端按 metadata 支持 `dimension/filter/sourceRef/timeBucket/cursor/limit`，无法支持的参数必须显式契约化拒绝，禁止静默忽略；
    2. profile interaction 读路径迁移到分页 read model 或至少补可审计索引/limit clamp，避免全局锁内无限扫描与循环 `FindByID`；
    3. author-impact evidence 分页避免每页重复 Count + N+1 hydrate，至少做到同页 contentId 去重 hydrate、limit clamp、summary count 与 evidence total 一致；
    4. App 侧同一主页停留内 `GetAuthorImpact` 与交集 preview 需要 Provider 级短时去重/缓存，避免 rebuild 重复打服务。
  - 验收标准:
    1. T3 contract 覆盖 `ListMyIntersections` 的 `filter/sourceRef/timeBucket/cursor/limit`；
    2. 高互动测试种子下 profile interaction 不在全局锁内做 O(全量互动) 扫描；
    3. author-impact evidence `limit > 50` clamp、同页 hydrate 去重、summary/evidence count 一致；
    4. App fake repository 计数测试证明同一主页停留内交集 preview 与 author impact 不因 rebuild 重复请求。
  - 涉及文件: `quwoquan_service/contracts/metadata/content/post/service.yaml`、`quwoquan_service/services/content-service/internal/adapters/http/intersection_handler.go`、`quwoquan_service/services/content-service/internal/application/intersection_service.go`、`quwoquan_service/services/content-service/internal/application/post_service.go`、`quwoquan_service/services/content-service/internal/adapters/http/content_handler.go`、`quwoquan_service/services/content-service/internal/infrastructure/persistence/author_impact_evidence_store.go`、`quwoquan_app/lib/ui/user/providers/my_intersection_inbox_provider.dart`、`quwoquan_app/lib/ui/user/providers/author_impact_provider.dart`
  - 本轮部分收口（2026-06-20）:
    1. `ListMyIntersections` handler/application 已消费 `dimension/filter/sourceRef/timeBucket/cursor/limit`，返回 `items/nextCursor/hasMore`；新增 `TestIntersectionService_ListFiltersAndPaginates` 覆盖 sourceRef/timeBucket/cursor/limit。（对应验收 #1）
    2. `AuthorImpactEvidenceStore.ListPageWithTotal` 用 Mongo facet 同页返回 items + total，替换 handler 中 Count + List 双读；同页 contentId hydrate 已保留去重。（对应验收 #3）
    3. **App Provider 级短时去重（A2，闭验收 #4）**: 交集 preview 与 author impact 改用容器作用域 `TtlCache`（无定时器、按 key TTL 去重、`force` 显式绕过），同一主页停留内 rebuild 不重复打服务；`flutter test test/ui/user/providers/intersection_provider_cache_test.dart` 5 绿（preview 重复 load 仅取数一次 / TTL 窗口取消订阅再订阅复用 / force 绕过 / authorImpact TTL 去重 / 不同 userId 各自取数互不串用）。
    4. 验证: `go test ./services/content-service/internal/application ./services/content-service/internal/infrastructure/persistence ./runtime/impact` 绿；`flutter test test/ui/user/widgets/profile_shell_widget_test.dart`、`test/ui/user/providers/intersection_provider_cache_test.dart` 绿。
  - 状态: 部分收口（2026-06-20；验收 #1/#3/#4 已闭，证据见上；剩余验收 #2 服务端 profile interaction 高互动读路径 O(全量互动) 扫描硬化由活动并发编辑（post_service.go）独立推进，本回合不竞争）
- [ ] R-ID10 交集 5 展示位统一渲染/交互/图标标准化收敛（两套并行链路收敛到统一组件）
  - 区域: App
  - 域: `content` / `recommendation`
  - 事项: 仓内存在两套并行交集渲染链路——统一链路（首页 feed / 我的主页 / 影响力卡 / 圈子影响卡，消费 `primarySpans` + `IntersectionTargetNavigator` + `IntersectionVisualCluster`）与自绘旧链路（记录卡 `IntersectionReasonChip` + 对象页 `ObjectIntersectionCard`/`EvidenceGroup` 自绘行 + 硬编码图标 switch）。自绘链路未消费 `primarySpans`、行/片段不可下钻、归因丢字段、图标绕过 resolver。
  - 原因: 交集补全分阶段落地，统一渲染器/导航器/图标 resolver 先在我的主页与首页 feed 收口，对象页（B 用户 / C 圈子 / D 实体）与记录卡的旧链路尚未收敛。
  - 影响: 用户旅程在对象页/记录卡有断点（交集句不可点、无法名字→对象页 / 数字→下钻）；图标/归因/导航多套真相源，违反 §20.7 统一交互子契约与 §21.5.2 图标单一真相源。不影响数据正确性与端云契约。
  - 正确设计（逐项）:
    - N3: 对象页三页用 `IntersectionStatementRow`（消费 `reason.primarySpans` + `sampleVisuals` + `iconKey`）替换 `ObjectIntersectionCard`/`EvidenceGroup` 自绘行。**证据级前置（2026-06-20 勘察坐实）**：N3 完整价值是 reason 粒度「名字蓝字可点 + 句内头像」，依赖 reason 级 `primarySpans`/`sampleVisuals`。云侧 `content-service` 对象交集已在 `ObjectIntersections → hydratePointSummary → hydrateExplain → hydrateInteractionContract` 完整产出 `primaryText/primarySpans/sampleVisuals/actionHints`（remote 已就位，无需改 go）；但端侧 mock `intersection_repository.getObjectIntersections` 走 `_objectEvidenceGroups` 硬编码 **point 粒度**，`primaryText/primarySpans` 为空。直接换 reason 粒度渲染器会：mock primaryText 空 → 整行降级隐藏 → 破坏 alpha 对象页交集展示与现有 object_page 测试；保持 group 粒度 → 拿不到 reason 级 spans → remote 价值兑现不了（换壳不换核）。故 N3 须先 **env-seed-first**：把云侧 hydration 后的对象交集 reason（含 spans）固化进 `contracts/metadata/content/test_fixtures`，mock 从 fixture 读（删 `_objectEvidenceGroups`），再换渲染器 + 重写 object_page 测试。该增量触 content-service fixtures 域（与 `post_service.go` 并发编辑同域，需避开撞车窗口），不宜与 N1/N2/N4 同轮强推。
    - N4: 对象页/他人主页交集行经 `IntersectionTargetNavigator` 下钻（名字/数字 span 级；section 内部默认下钻不改脏树调用方）。
    - N5: 记录卡 `IntersectionReasonChip` → `InteractiveIntersectionText(spans)` 可点击 + `IntersectionTypeIcon`。
    - N6: 首页 feed `onTrack` 透传 `sourceRef`/`evidenceId`。
    - N7: 「为什么推荐X」埋点通道统一——**纠偏（2026-06-20 证据级）**：初判「统一到 `trackClick`」方向错误。交集证据组点击语义是 `tag_click`（`contracts/metadata/content/post/behaviors.yaml` 已登记 `type: tag_click` / `dart_method: trackTagClick`；推荐 HotPath `runtime/recommendation/hotpath.go` 给 `tag_click` 权重 **1.8**，高于 `click`），统一到 `trackClick(click)` 会把 1.8 强信号降权、改变推荐归因强度（违反 R23/R32 改埋点验三面）。当前 `object_intersection_section._reportReasonTap` 经 `behaviorRepository.reportEvents(action: tagClick)` 直发 **语义正确、tagRefs 回流不丢**，「双通道」实为 `ContentBehaviorTracker` 缺 `trackTagClick` 公开封装（仅内部 switch 处理 `BehaviorAction.tagClick`）。正确收口：在 tracker 补 `trackTagClick`（保 `tag_click` 1.8 权重 + 补 `intersectionSourceRef`/`intersectionEvidenceId` 归因），统一通道不改信号语义，并以契约测试验证推荐权重不变性。降级为不阻断用户旅程的封装统一债（PR_WARN/TECH_DEBT，非 click 降权改造）。
    - N8: 圈子头像簇 `sampleAvatarUrls` → `sampleVisuals` + `IntersectionVisualCluster`。
    - N9: 实体行硬编码 `'ask_xiaoqu'`/产品名 → `IntersectionActionHint.actionKey` 闭集。
    - N10: `referralSource` 按面（profile/circle/entity）精确来源，去 `organicFeed` 硬编。
  - 验收标准:
    1. 对象页/记录卡交集句经统一渲染器（`primarySpans`/统一图标 resolver），无自绘行与硬编码图标 switch；
    2. 名字 span → 对象页、数字 span → 维度下钻、行点击经 `IntersectionTargetNavigator`（与我的主页/首页 feed 同口径），新增 widget/契约测试断言；
    3. 归因字段（`sourceRef`/`evidenceId`/精确 `referralSource`）跨展示位一致；
    4. 删除 `EvidenceGroup` 自绘渲染与 `IntersectionReasonChip` 纯文本路径后，全仓无第二渲染/导航/图标真相源（门禁/grep 守护）。
  - 涉及文件: `quwoquan_app/lib/components/object_page/{object_intersection_card,object_intersection_section,evidence_group,intersection_target_navigator}.dart`、`quwoquan_app/lib/ui/content/widgets/intersection_reason_chip.dart`、`quwoquan_app/lib/ui/content/widgets/record_post_card.dart`、`quwoquan_app/lib/ui/user/widgets/profile_shell_builders.dart`、`quwoquan_app/lib/ui/circle/widgets/circle_shell_builders.dart`、`quwoquan_app/lib/ui/entity/widgets/{homepage_detail_shell_builders,homepage_detail_page}.dart`、`quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_post_cards.dart`
  - 本轮部分收口（2026-06-20）:
    1. N1（断点4）: `object_intersection_list_page` 手写 `switch(UnifiedObjectKind)→context.push` 复制导航逻辑删除，归一 `IntersectionTarget` 后交 `IntersectionTargetNavigator`，保留 `relationKind` 兜底；新增 `test/ui/intersection/pages/object_intersection_list_page_test.dart`（4 组绿）+ navigator 回归 13 绿。
    2. N2（断点5）: `object_intersection_card._ConnectionLeadingIcon._fallbackIcon` 与 `evidence_group.fallbackIconKindFor` 两层硬编码图标 switch 删除，统一 `IntersectionIconResolver.resolve`（`sourceRef`/`dimension` 从 `group.kind` 解析）；object_page 全测试目录 60 绿，全仓 `fallbackIconKind` 无代码引用。
    3. N4（断点2）: `object_intersection_section` 在未传 `onReasonTap`（用户主页 B / 圈子主页 C）时内部默认经 `IntersectionTargetNavigator` 下钻（整行对象级可达，消除「整行仅 track 不可下钻」断点）；传入 `onReasonTap`（实体页 D 自定义开助手）时尊重调用方语义、不叠加默认下钻（不双跳），零改脏树调用方。reason→target 归一逻辑从 N1 list page 顶层函数上移为 `IntersectionTargetNavigator.targetForReason`（B/C/list page 单一真相源，保留 `relationKind` 兜底）。`test/components/object_page/object_intersection_section_test.dart` 新增 2 条 GoRouter host 测试（默认下钻 / 调用方优先不双跳）；object_page 全测试目录 + N1 list page 测试共 69 绿。
  - 第二轮收口（2026-06-21）:
    4. N6: `home_multi_form_feed_post_cards` 两处 `trackClick` 补 `intersectionSourceRef`/`intersectionEvidenceId`，三处 `IntersectionNavAttribution` 补 `evidenceId`（取 `reason.pointSummarySnapshotId`）；新增 GoRouter host span 点击回归（`home_intersection_multiform_feed_widget_test`），15 绿（feed 集合 83 绿）。
    5. N7: `ContentBehaviorTracker.trackTagClick` 公开封装落地（保 `tag_click` 1.8 权重、补全统一交互子契约归因字段，**未**降级为 `click`），`object_intersection_section._reportReasonTap` 改走统一通道；`content_behavior_tracker_test` 新增 `tag_click` 断言，31 绿。
    6. N9: 实体页 D 面 `_handleIntersectionReasonTap` 改消费结构化 `actionHints`（新增端侧闭集常量 `IntersectionActionKeys` + `isAssistant`），删除 `actionType == 'ask_xiaoqu'` 死分支（该值全仓从无产出）；mock `intersection_repository` 改用闭集常量；新增 `intersection_action_keys_test`（11 绿）。
    7. N10: `behaviors.yaml` `referralSource` enum 扩 `my_intersections` + 云 `ReferralSourceMultiplier` 加 `my_intersections: 1.5`（端云三同步 R08，`verify_metadata` 通过）；新增共享 `referralSourceForObjectType`（user→authorProfile / circle→circlePost / entity→entityPage），`object_intersection_section`/`object_intersection_list_page` 改用；`author_impact_card`→authorProfile，3 个「我的」面→`myIntersections`；contract 测试补闭集 + 映射断言。
    8. N8: `circle_header` `memberAvatarUrls: List<String>` → `memberVisuals: List<IntersectionVisual>` 归一到统一 `IntersectionVisualCluster`（形状/降级/「+N」/可点击统一）；`circle_shell_builders._circleMemberClusterVisuals` 优先 `point.sampleVisuals`、过渡期回退裸 `sampleAvatarUrls` 包装（N3 fixture 化后回退分支自消亡）；`circle_header_widget_test` 新增 2 条簇渲染断言，13 绿。
    9. N5: `IntersectionReasonChip` 升级 `ConsumerWidget`——槽①图标归一统一 `IntersectionTypeIcon`（删本组件第二套 `kind` switch `_icon`，消除与 resolver 分叉）；结论句归一统一 `InteractiveIntersectionText(spans)`，对象/计数片段可点击经统一 `IntersectionTargetNavigator` 进对象页、埋点保 `tag_click`（`trackTagClick`）；4 调用方（`profile_works_tab`=authorProfile / `homepage_detail_shell`=entityPage / `section_creations` 文章卡 + `record_post_card`=circlePost）传 `referralSource` 精确归因；`intersection_reason_chip_widget_test` 重写（图标归一 + weightTier 分化读 `InteractiveIntersectionText.baseStyle` + 可点击 span 导航/`trackTagClick` 全归因），15 绿。
    10. 顺手清理: `author_impact_evidence.dart` 行尾箭头 `chevron_right`→`chevron_forward`（pre-existing iOS 语义债，`verify_dart_semantic` 门禁绿）；author impact + 我的交集 21 绿。
    - 第二轮门禁: `verify_dart_semantic` 绿、`verify_ui_mock_isolation` 绿、`verify_metadata` 绿；交集核心测试集合 83 绿。
    - 已知非本轮：`home_circles_hub_page_test`（`home-circle-grid-post-*` key 缺失）与 `homepage_detail_page_widget_test`（「主页暂不可用」失效态文案）2 例失败属 discovery/entity 脏树并发 WIP 漂移，与本轮交集改动无关。
  - 第三轮收口（2026-06-23 · N3 env-seed-first 主体）:
    11. N3（env-seed-first + 删第二真相源）: 对象页「你们的交集」改为唯一经 contract fixture 真实下发。
        - `content/test_fixtures/scenarios/content_scenarios.json` 的 `intersection_core.objectIntersections` 新增 `u_lin`/`c_photo`/`e_pku` 三个 alpha 测试对象，每个为完整 `IntersectionReason`（含 `primaryText` + `primarySpans`〔句内对象名蓝字可点 target〕 + 多 `intersectionPoints`〔关系分层 label/count/sampleAvatarUrls〕 + `connectionSummary`），与 erhai/duanqiao 同 schema、与 alpha/beta/gamma seed 同源。
        - `MockIntersectionRepository.getObjectIntersections` 删除硬编码 `_objectEvidenceGroups` / `_EvidenceSeed` / `_connectionSummaryFor` / `_objectKindForObjectType`（按 objectType 合成事实的第二真相源），改为只读 `intersection_core.objectIntersections[objectId]`；无 seed 命中返回空（不造假、无 objectType 回退）。mock 与 remote 同走 `IntersectionReason.fromMap`。
        - `build_alpha_lite_fixture_bundle.py`：content LITE_REFS 增 `intersection_core`，并裁剪为 `objectIntersections`-only（inbox/channelReasons 仍走端侧行内 canonical 回退，零改 inbox 行为，避免 inbox 测试级联）。`build_gamma_curated_fixture_bundle.py`：新增 `CURATED_OBJECT_INTERSECTION_DROP_IDS` 裁掉三个 alpha 测试对象，gamma 仅保留 `fixture_*` 真实首页对象交集（已校验 gamma-curated 0 命中测试 id）。
        - 重写 `intersection_object_evidence_test.dart`：断言真实 fixture 链路（`intersectionId`/`actionTargetId` 取自 seed、`primaryText` + object span 蓝字可点、`join(primarySpans.text)==primaryText`、关系分层 label、count single-source、`把你们连在一起` 连接句、推荐排在事实后、未 seed 对象〔含合法 user 类型〕返回空证明无 objectType 回退）。`flutter test` 8 绿；object_page/intersection 目录 111 绿；profile shell/tab 41 绿。
  - 状态: 收口（2026-06-23；N1–N10 全部已闭并验证，证据见上）。N3 第二真相源（mock 硬编码 `_objectEvidenceGroups`）已删除，对象页交集唯一经 fixture `IntersectionReason` 真实下发，自带 `primarySpans`（句内对象名蓝字 target + 头像簇）。**渲染/导航已统一**：我的主页「我的连接」与三对象页（用户 B / 圈子 C / 实体 D）**共用同一个** `ObjectIntersectionSection` → `ObjectIntersectionCard`/`EvidenceGroup` + `IntersectionTargetNavigator` + `IntersectionIconResolver` codegen（profile/circle/entity shell builders 同源），整行/名字/数字可下钻、归因 `tag_click` 1.8 权重不变——主页与对象页无渲染分叉，instruction #4「统一到与主页同一 ObjectIntersectionSection」已满足。**残留（独立 UI 视觉升级项，非主页/对象页分叉）**：当前共用的 `ObjectIntersectionCard` 以 `EvidenceGroup`（point 证据组行）呈现，尚未升级为直接渲染 `reason.primarySpans` 的 `IntersectionStatementRow`（句内蓝字+头像，目前仅 `我的交集` inbox/impact 时间线在用）。因主页与对象页同源，此升级须在 `ObjectIntersectionSection` 层**跨面统一**进行（一改全改，避免新分叉），seed 已下发 `primarySpans` 为该升级铺好数据；属可独立排期的全局视觉对齐增量，不构成主页对标缺口。

## 评论系统重做（Comment System Redesign）

> 真相源 spec/契约：`quwoquan_service/contracts/metadata/content/post/{fields,service,storage,errors}.yaml`。本会话评论重做（小红书级二层线程 + 综合/最新/最多赞排序 + 端云契约）已落地端侧展示、排序锚定菜单、端云排序契约、fixture 扩充（0/1/5/10/50/100+）与并发硬化（RWMutex + recommendedScore 预计算）。以下为用户确认（`harden_plus_backlog` 决策）后登记的生产持久化迁移延后事项。

- [x] R-CMT01 评论存储为进程内 map + 全局锁，缺 MongoDB/Redis 生产持久化落地
  - 区域: Service
  - 域: `content`
  - 事项: `content-service` 评论读写曾由 `PostService.comments map[string][]map[string]any` 进程内存承载，`storage.yaml` 声明的 MongoDB `comments` 集合与 Redis 缓存未接入 infrastructure 实现。
  - 原因: 进程内实现仅满足 alpha mock + 单实例契约测试，不满足多副本、重启不丢、千万级评论分页与高并发读写。
  - 影响: 进程重启评论全丢、无法水平扩容、深分页/热评论排序大数据量下退化为全量内存扫描排序、跨副本排序漂移。
  - 正确设计: 在 `infrastructure/persistence` 实现 storage-agnostic comment store，一级评论两段 keyset（pinned 段 + 排序段）走复合索引，二级回复按 `(postId,parentCommentId,createdAt,_id)` keyset；application 层只依赖 `domain/comment.Store` 接口，不出现存储驱动 import；`Post.commentCount` 由原子 `$inc` 加速、评论集 DB count 为单一真相源。
  - 验收标准:
    1. 评论读写经 MongoDB store，重启（重连）后评论与排序不丢；
    2. 三种排序在大数据量（≥1e4 评论）走索引分页，无全表内存排序；
    3. 同集合一致性：换排序不换集合/总数；
    4. 多副本下排序由落库字段驱动稳定；
    5. 主请求不再依赖评论 Redis 缓存（移除只写不读 ZSet / 竞态计数器后无降级阻断）。
  - 涉及文件（已落地）: `quwoquan_service/services/content-service/internal/domain/comment/{comment_repository.go,comment_cursor.go,reaction.go,sort_mode.go}`、`internal/infrastructure/persistence/{comment_mongo_store.go,comment_memory_store.go,comment_reaction_mongo_store.go,mongo_post_store.go,post_store.go,post_repository_iface.go}`、`internal/infrastructure/cache/post_cache_repository.go`、`internal/application/{post_service.go,comment_projection.go}`、`internal/adapters/http/content_handler.go`、`cmd/api/main.go`、`contracts/metadata/content/post/{fields,storage,service}.yaml`、`contracts/metadata/_shared/redis_keyspace.yaml`、测试 `services/content-service/tests/{comment_persistence_migration_contract_test.go,comment_keyset_explain_bench_test.go}` 与 `internal/infrastructure/persistence/{comment_memory_store_test.go,comment_keyset_delta_test.go}`
  - 本轮收口（2026-06-20）:
    1. **决断① 排行 ZSet → 删除**：`comment_hot` / `comment_recommended` 排序 ZSet 是只写不读（`ListTopLevel` 直接走 Mongo），per-comment 赞踩计数器读穿回填非原子（stale-backfill 竞态、陈旧 `likeCount`/`recommendedScore` 落库）。判定为写放大无读收益且引入一致性债，整体删除 `infrastructure/cache/comment_cache.go`，从 `redis_keyspace.yaml` 移除对应前缀；排序/计数权威化到 Mongo 复合索引 + `CountDocuments`。`ReactToComment` 计数改为派生自权威成员关系 store（`comment_reactions` 集合），落库分值永不陈旧。
    2. **决断② post 计数热写 → Mongo 原子 `$inc`**：`AddComment`/`DeleteComment` 用 `MongoPostStore.AdjustCommentCount(±1)`（单字段 `$inc`，配 `SetReturnDocument` + 投影）替换每次 `CountDocuments + 整文档改写`；`GetCounters`/`ListComments` 读路径以评论集 DB count 为单一真相源，发现 `Post.commentCount` 漂移时单 `$set` 机会式自愈；`$inc` 失败回退 `reconcilePostCommentCount` 全量对账。未引入 runtime/redis `DecrBy/IncrBy`（避免再加一套跨副本会漂移的计数真相源）。
    3. **决断③ keyset 分页取代 1e4 扫描**：强类型 `comment.Cursor`（`Phase/Score/TimeUnixNano/ID`，base64 JSON 编解码，非 `map[string]any`）；一级两段 keyset（pinned 段 `(pinnedAt,_id)` partial index + 非置顶排序段 `(score,createdAt,_id)`），二级/作者/收到 keyset `(createdAt,_id)`；所有 keyset 服务索引追加 `_id:-1` tiebreak 使排序全索引覆盖。`storage.yaml` 新增 `idx_comments_pinned`（partial `isPinned:true`）/`idx_comments_deleted`（partial `status:deleted`）。
    4. **块2 计数 delta 契约**：`fields.yaml` 评论补 `deletedAt`（软删落时间戳、记录保留可查、count 仍排除 deleted）；`SoftDelete` 真正写入 `deletedAt` 并对已删幂等（不二次扣减）；`comment_projection.go` 输出真实 `deletedAt`；新增 `GetCommentCountsDelta(postId, since)` → `{createdSinceCount, deletedSinceCount, currentTotal, watermark, since}`，半开区间 `(since, watermark]`，watermark 作下次 since 基线避免重复/遗漏；`service.yaml` 声明该接口 metrics/SLO/trace；`make codegen-app` 端侧 `comment_dto.g.dart` 已含 `deletedAt` 供后续端侧消费。
  - 验证证据（2026-06-20，`TEST_MONGO_URI=mongodb://localhost:32775`）:
    - explain 索引覆盖（`TestCommentMongoStore_ListQueriesAreIndexCovered`）：recommended/most_liked/replies 三查询 winningPlan 均 `FETCH ← IXSCAN(idx_comments_recommended|idx_comments_hot|idx_comments_parent_created)`，无 `COLLSCAN`、无阻塞 `SORT`（SORT 仅出现在 rejectedPlans）。
    - ≥1e4 深翻不截断（`TestCommentMongoStore_DeepPageBeyond10kNoTruncation` 10001 条 / 内存 `TestMemoryCommentStore_DeepPageNoTruncation` 12001 条）：全量唯一、无重复、顺序稳定。
    - 翻页不漂移（`TestMemoryCommentStore_LatestKeysetDriftFreeUnderMutation`）：分页中持续 mutate 分值，`createdAt+_id` 不变 keyset 仍不重不漏。
    - delta 半开区间（`TestCommentCountsDelta_ExplainableHalfOpenWindow` + 内存 `TestMemoryCommentStore_DeltaWindowSemantics`）：连续两次 since=上次 watermark，created/deleted 精确不重复计数，currentTotal == 权威 Mongo 非删计数。
    - 并发一致性（`TestCommentCountReconciliation_HighConcurrency`，`-race` 干净）：并发增/删/反应后 `ListComments.totalCount == GetCounters.comment == 权威 Mongo count`。
    - 基准（Apple M5 Pro，docker Mongo over TCP）：`BenchmarkCommentListTopLevel_DeepPage` ~11.3ms/op、`BenchmarkCommentListReplies_DeepPage` ~1.77ms/op（深位 keyset seek，O(pageSize) 与深度无关）、`BenchmarkPostCommentCount_AtomicHotWrite` ~0.94ms/op（含网络往返）。
    - `go build ./...`、`go vet ./services/content-service/...` 通过；`go test ./services/content-service/...` 仅余两项与本任务无关的既有失败（见 R-CMT02）。
  - 状态: 已解决（2026-06-20；评论域已迁出进程内 map，Mongo keyset + 权威 count 落地，证据见上）

- [ ] R-CMT02 评论计数加速器最终一致窗口 + delta watermark 依赖服务端墙钟（残留）
  - 区域: Service
  - 域: `content`
  - 事项: ① `Post.commentCount` 为去规范化加速器，`SoftDelete` 成功与 `AdjustCommentCount(-1)` 之间若进程崩溃，加速器会短暂偏差 1，直到下次 `GetCounters`/`ListComments` 读路径按权威 Mongo count 自愈；② `GetCommentCountsDelta` 的 `createdAt`/`deletedAt`/`watermark` 均由应用服务端墙钟写入/取值，多副本时钟偏移下，半开区间边界可能把一条临界事件计入相邻窗口。
  - 原因: 单一真相源选定为评论集 DB count（强一致），加速器与 delta 走「写后/读时对账 + 半开 watermark」最终一致策略，刻意不引入分布式事务/逻辑时钟以避免过度设计。
  - 影响: ①加速器偏差为自愈瞬态、不影响权威 count 与列表 totalCount（两者实时从 Mongo 取），仅 feed/详情页去规范化字段可能短暂偏 1；②delta 边界偏移为单条、单窗口、不累积（下窗口仍以同一 watermark 续接，不重复不遗漏总量），仅「此期间新增 N/删除 M」在时钟偏移瞬间可能 ±1。均不影响最终一致与端侧 baseline 对齐。
  - 正确设计（如需强一致）: 加速器改事件驱动 outbox 回写 + 周期对账任务；delta 改用 Mongo 服务端时间（`$$NOW`）或单调逻辑水位线替代应用墙钟，消除跨副本时钟依赖。
  - 验收标准:
    1. 注入「SoftDelete 后崩溃」故障，加速器在下一次读路径后收敛到权威 count；
    2. 多副本/时钟偏移仿真下，delta 总量随 watermark 续接零重复零遗漏；
    3. 若落地服务端时间/逻辑水位线，临界事件不再因时钟偏移错窗。
  - 涉及文件: `quwoquan_service/services/content-service/internal/application/post_service.go`（`AdjustCommentCount`/`reconcilePostCommentCount`/`GetCommentCountsDelta`）、`internal/infrastructure/persistence/{comment_mongo_store.go,mongo_post_store.go}`
  - 状态: 待办（残留最终一致项；本轮已实现读时自愈 + 半开 watermark，强一致化作为后续可选里程碑）

- [x] R-CMT03 content-service 既有契约测试两项失败（与评论域硬化无关，working-tree 阻断）
  - 区域: Service
  - 域: `content`
  - 事项: `go test ./services/content-service/tests/` 有两项失败：`TestContractFixtureSeed_ContentAlphaReadsViaHandler`（`content_discovery_core` seedSet 不含 `fixture_photo_001` 评论，断言 comments 非空失败）与 `TestIntersectionSource_EntityObjectProducesFolloweeVisited`（交集文案 `ixsrc_visitor_c来过这里` off-dictionary）。
  - 原因: 二者均由当前 working-tree 中**他项未提交改动**引入：`content_scenarios.json` 共享池重构把 `fixture_photo_001` 评论从 `content_discovery_core` 迁到 `comment_thread_core` seedSet；`intersection_kind_registry.yaml`/`intersection_reason.yaml` 文案词典调整。已用 clean HEAD worktree 复跑证明两测试在干净基线通过，故与本会话评论域/delta 改动无关。
  - 影响: 阻断 content-service `tests` 包整体绿；不影响评论域/计数 delta 正确性（其余全部用例含本会话新增 explain/deep-page/delta/并发用例均绿）。
  - 正确设计: 由 `content_scenarios.json` 共享池重构 / 交集文案词典的负责会话同步修正 seedSet 与词典；或将 `TestContractFixtureSeed` 的评论断言改读包含该评论的 seedSet。
  - 验收标准: clean working-tree 下 `go test ./services/content-service/tests/` 全绿。
  - 涉及文件: `quwoquan_service/contracts/metadata/content/test_fixtures/scenarios/content_scenarios.json`、`quwoquan_service/contracts/metadata/recommendation/rec_model/{intersection_kind_registry.yaml,projections/intersection_reason.yaml}`、`services/content-service/tests/{contract_fixture_seed_contract_test.go,intersection_source_contract_test.go}`
  - 证据: 2026-06-21 R-TST03 收口轮 `go test ./services/content-service/tests/ -count=1` → ok（0.348s）；working-tree 漂移已被他项改动消除，不再阻断。
  - 状态: 已解决（2026-06-21；content-service tests 包当前树全绿，与评论域改动无关的 transient 漂移已消除）

## 内容生产工作流商用化（Content Supply）

> 来源：2026-06-21 内容生产工作流商用化系统性规划（`quwoquan_data/docs/content_supply_commercialization_plan.md`）落地 + 四川景区两工作流真实 e2e + 十→千→十万规模评估。蓝图、三份 spec、Phase 0-4、运行时地基、两工作流 e2e 与规模门均已完成；以下为诚实剩余断点。

- [ ] R-CS01 指令线 homepage source sufficiency 反爬瓶颈
  - 区域: Data
  - 域: `content-supply`（指令维度工作流 / download homepage lane）
  - 原因: homepage lane 要求每实体 ≥1 可读百科/官方源；四川十级 e2e 中阆中古城、黄龙风景区的百度/搜狗百科被反爬隔离 reject（`home_baidu_baike`/`home_sogou_baike`），`homepage retained sources=0 need>=1` 触发 download gate 失败，ReAct 回退两次仍不满足。
  - 影响: commercial 零失败模式下个别实体 source 不足会阻断整批；十级实测 8/10（80%）成功。百/千级放量需 `allowPartialContent` 替补策略或更强多源 plan，否则成功率随外站反爬波动。
  - 涉及文件: download lane、`quwoquan_data/verticals/travel/sources/source_registry.yaml`、task `workflowPolicy.allowPartialContent`
  - 复核（2026-06-21 真实运行时复盘，代码+e2e10 实证）: 多源候选生成工程已实质建成——`research_plan.py` 已对 homepage 同时产出 official_url + 维基（`_wiki_title_for_entity` 经 canonical+短名+别名解析 + `_wikidata_item_for_entity_search` zhwiki 失败兜底）+ curated `knownHomepageSupportSites` + baidu + sogou；CR-049 已落 partial delivery（`allowPartialContent` 默认 true、单实体主页失败不阻断整批）。对真实批次 e2e10 跑 `verify scale-readiness`：`sourceSufficiency.homepage rate=1.0(8/8 活跃)`、`sourcePlanCategories.encyclopedia=10`，**源充分性在计划层已达标**。黄龙/阆中失败精确定位在 `build_prepare`「homepage input unavailable after build_prepare repair budget」（候选有、但抓取到的正文被反爬探针页污染不可用），已由 partial delivery 处理为 8/10、abandoned=2 excluded from refs。
  - 复核（2026-06-23 五景真实放量验证 e2e5，含 article lane）: 本轮发现并修复一个**article 底稿选源缺陷**（与原 homepage 维度不同）：`task/run.py:_article_source_quality_sort_key` 旧排序键 `(quality, length, image)` **不含目标实体聚焦度**，导致放量时长篇多城游记（如青城山被锁到「问道青城山拜水都江堰」实际聚焦仅 8% 的 base_1、九寨沟锁到聚焦 25% 的 base_3）系统性挤掉聚焦单实体的短游记（青城山 base_2 聚焦 61%、九寨沟 wikivoyage 聚焦 67%），使 article lane 的 `baseDraftFidelity` 门被源错配拖垮。已实现 `_entity_focus_score`（实体名+通名别名在信号行的字符占比）并把聚焦度置于排序首位（5% 分档），确定性验证：青城山 04→05、九寨沟 06→wikivoyage 改派正确；青城山切到聚焦源 base_2 后端到端 fidelity 72.1% 过 review+materialize（修复闭环证明）。残留两个**新维度**（待用户确认是否登记为独立 backlog 项）：(a) 都江堰**采集缺口**——批内无任何聚焦简体 article base（最佳 qunar 仅 17%，维基 93% 但属 home lane 非 article），排序无法凭空造源；(b) wikivoyage 等**简繁混排**底稿聚焦度高但简体成稿 3-gram fidelity 偏低（九寨沟 12.7%），需在 `base_draft.py` fidelity 做繁→简归一化或在选源加脚本兼容度项。e2e5 `scale-readiness` 漏斗：homepage 5/5、image 5/5、article 3/5（乐山/峨眉/青城山过门，都江堰/九寨沟 abandoned）。
  - 状态: 待办（homepage 维度残留为「外站反爬 fetch-time 不可控 + 逐实体 curated 兜底」；article 维度的选源排序缺陷本轮已修复并端到端验证，残留繁→简 fidelity 归一化与逐实体 article 源采集充分率两项待确认登记；证据 `artifacts/sichuan-e2e-assessment/scale_readiness_{100,1000}.json`、`runtime/batches/五景放量验证-05688323__e2e5_20260623_01/_shared/scale_readiness_report.json`）
- [ ] R-CS02 十万级放量工程门槛（reliabletask adapter + 吞吐）
  - 区域: Data / Service / Ops
  - 域: `content-supply` / `reliabletask`
  - 原因: `verify scale-readiness` / `site-scale-readiness` 在 `daily_target>=100000` 强制 `queueBackend=reliabletask` + 吞吐 4166.67/h；当前文件队列(`local_file`) + 单会话 ~80/h 仅够十→千级。`object_queue.py` 已定义 `_reliabletask_ref` 路由契约（taskType/queue/dedupeKey/partitionKey），但服务侧 reliabletask adapter（MongoStore+RedisReadyIndex）实际分发未端到端实测；52× 吞吐需外部 cursor-sdk 多 worker ~500 并发 + spend limit + Cursor API 速率配额确认。
  - 影响: 就绪配置 trial 已证明十万级门可过（0 blocker），但生产分发链路未实跑；真实十万级放量前必须落地 reliabletask 分发 + 外部 SDK 编排 + 计费/速率护栏。
  - 涉及文件: `quwoquan_data/scripts/task/object_queue.py`、`quwoquan_service/runtime/reliabletask`、`quwoquan_data/docs/subagent_scheduler_spec.md` §9-10
  - 复核（2026-06-21 真实 e2e10 scale-readiness）: 真实批次 `executionReadiness.queueBackend=""`、`maxConcurrency=0`、`measuredThroughput=null`，百/千级 `decision=no_go`，blocker 含「measured throughput evidence missing」「workflow status must be succeeded」。即吞吐/分发证据只能由真实跑完、烧 token 的放量批次产出，仍受外部 cursor-sdk 多 worker + spend limit + Cursor API 速率配额约束（用户决策项，非会话内可独立闭合）。
  - 复核（2026-06-23 e2e5）: 并发**调度原语已具备**——object-queue 单篇隔离 job（lease/heartbeat/leaseExpiry/notBefore 退避，`queue_runtime_snapshot`）、`task queue work --concurrency N` 本地 worker pool、download lane 实测 5 workers 并发拉 27 source bundles。但本批 `queuePolicy.backend=local_file`，`scale-readiness` 明确 blocker：「daily target >=10000 requires queueBackend=reliabletask」「measured throughput evidence missing; cannot project daily capacity」。即放量级吞吐需切 `reliabletask`（Mongo/Redis）后端 + 真实跑完计时，且 authoring 步受 cursor_sdk 阻断（见 R-CS03），端到端成稿吞吐本轮仍无法实测。
  - 状态: 待办（真实放量门槛，需外部资源授权 + reliabletask 后端 + 解除 cursor_sdk authoring 阻断）
- [ ] R-CS03 作品线真实 token/成本/firstPassRate 未实测
  - 区域: Data
  - 域: `content-supply`（produce author / TokenLedger）
  - 原因: `scaled-e2e prepare` 与 `site-supply trial` 均为结构验证（不烧 token、注入受控吞吐/质量/账本证据）；真实作品 author（cursor sdk）的单位 token、单位通过成本、缓存命中率、firstPassRate 尚无真实 TokenLedger 批次。
  - 影响: 日产十万的商用经济性（单位成本可承受性）未经真实数据验证；scale-readiness commercial 门的 TokenLedger/firstPassRate 维度需真实 author 批次才能过。
  - 涉及文件: TokenLedger、`quwoquan_data/scripts/task/object_queue.py`(`record_usage`)、`quwoquan_data/scripts/verify/scale_readiness.py`
  - 复核（2026-06-21 真实 e2e10 scale-readiness）: 真实批次 `executionReadiness.tokenLedgerCount=0`、`firstPassRate=null`、`expectedObjects.total=0`（e2e10 为 quotas=0 纯实体主页基线，冻结在 content_plan 检查点，结构上不产出 POST，因此无法产生 TokenLedger/firstPassRate/吞吐证据）。要诚实证明放量经济性，必须新跑一个**含内容配额（quotas>0）、Agent 真实创作正文、烧 token、跑完 produce_author→review→materialize→ship** 的真实批次；env preflight 已确认本环境 `CURSOR_API_KEY=present`、`network=ready` 具备真实跑能力。
  - 复核（2026-06-23 e2e5，含 quotas>0）: 新建含配额任务（5 实体 + 5 文章 + 5 图片）并实跑到 review/materialize，但**managed cursor_sdk subagent runner 阻断**：`env doctor` 的 `cursor_startup_probe` 以 `composer-2` 与 `composer-2.5` 均报 HTTP 500 internal error（外部 Cursor API 基础设施/账号侧问题，非本地可控）。因此本轮正文改由**会话模型**创作并确定性 stamp provenance（`agentRunId=cursor-conv-*` + prompt/writingPack/sourceBundle/draft SHA256），质量门全过，但**未经 managed runner ⇒ 无真实 TokenLedger ⇒ `scale-readiness` 仍 blocker「TokenLedger evidence missing」「firstPassRate evidence missing」**。即真实单位 token/成本/缓存命中率/firstPassRate 依旧未实测，根因从「需授权」收敛为「cursor_sdk managed runner 500 阻断」。
  - 复核（2026-06-24 隔离单实体 e2e，`QWQ_DATA_ROOT=/tmp/qwq_e2e` 零污染真实仓库）: **cursor_sdk managed runner 已真实跑通，解除 e2e5 的 HTTP 500 阻断**——把 `QWQ_MANAGED_AGENT_TIMEOUT_SECONDS` 调到 720s 后，build_homepage（都江堰主页 11044B，含《史记·河渠书》/李冰/岷江真实引用，188s 完成）与 produce_author（文章 `都江堰·行前怎么安排` 5169B）均由真实 cursor agent 创作：article `draft_meta.generator=agent`、`model=composer-2.5-fast`、`agentRunId=run-524610ad-...`（真实 run id，非 e2e5 的会话模型 `cursor-conv-*` stamp）。全链路 11 stage 全 completed、failed=[]：explore→baseline→download(真实8源/4图)→build_homepage→build_validate→content_plan→produce_plan→produce_compose→produce_author→produce_annotate(实体标注1 link)→produce_review(media 2/2 passed + review 2/2 approved + 2 包 materialize)。文章质量命中 blueprint 质量门（openingTension/explicitFeelings/decisionPoints/tipsEmbeddingPolicy + cover/wrapRight/closing 多图 + 实体链接）；image 作品 manifest 含完整版权链（creator/license/termsUrl/authorizationProof）。**同时验证去重移除无副作用**：移除图片资产去重链（`_duplicate_source_asset_recompose_refs` 等 + `QWQ_COMPOSE_IGNORE_ASSET_REFS` 旁路）后 produce 域测试 101 passed、e2e 链路全绿。**仍待**：本批未生成 TokenLedger（`record_usage` 未触发），单实体隔离不足以测吞吐/单位成本/firstPassRate，仍需多实体放量批次跑 `scale-readiness` 才能产出商用经济性证据。
  - 本轮 e2e 新发现修复（2026-06-24，用户指令「完成 b/c/d 问题修复」，A 已于发现时修复）:
    - A（已修复）: 文章正文泄漏底稿内部标识 `article_qunar_base_1`（agent 把 prompt 提供的底稿路径片段当溯源写进正文），review gate `check_provenance` 原只查平台名/发布者字段未拦。已加两道防线——`writing_pack.py` prompt 在底稿来源块后明确「禁止把底稿文件名/目录名/source 编号/采集痕迹写进正文标题配文」；`content_review.py:check_provenance` 增 `*_base_N`/`source.md`/`sources/`/`.download` 标识检测（正则命中泄漏样本、不误伤干净正文，produce 101 passed、0 lint）。
    - B（已修复）: entity_workflow 图片作品对齐 route_workflow——`entity_workflow.build_entity_writing_pack` 对 carrier∈{image,gallery} 改调 `write_image_evidence_draft`（幂等删旧正文 + 写 `generator=image_evidence_pack`/`articleContract=structured_image_only`/`selectedAssetIds`），非图片仍走 placeholder。证据：隔离 e2e（`/tmp/qwq_e2e`）真实重跑 `都江堰_image`，draft 由 `generator=pending`+残留 `draft.article.md` → `image_evidence_pack`+`structured_image_only`+正文已删+selectedAssetIds=1；produce 101 passed、0 lint。
    - C（已修复，与去重诉求对齐）: 调研发现「同底稿多作品」基础设施**早已具备**——`handler.py` 已支持 `baseSourceReusePolicy=multi_intent_source_bundle`（`assignments[source]=[posts]` 多值），`content_plan.py:618` 对 `carrier==image` 豁免 one-source-one-work（image 不注册 `base_source_owners`）。真正的过度限制只在 `run.py:_clear_compose_base_draft_assignments` 的 `duplicate_sources` **不分载体**。修复使其载体感知（新增 `image_refs` 参数，由 `_run_produce_compose` 收集 pending image refs 传入）：article+article 复用同底稿仍报 duplicate（反凑数/同质化不放松，与 content_plan「article 一稿一用」一致），image/gallery 参与的同源共用放行（图文同源正常）。**无需改 ledger 结构**。证据：pipeline 188 passed + 新增回归 `test_compose_base_draft_clear_allows_image_work_sharing_article_base`（image 豁免）/ 既有 `..._detects_duplicate_current_plan_sources`（article+article 仍报）；并清理 5 个 import 已删去重符号的死测试（`test_duplicate_source_asset_refs_*`/`test_duplicate_asset_recompose_*`），全仓零残留。澄清：实践中 image 作品写 `sourceCollectionId` 而非 `baseSourceRef`，鲜少触发该门，本修复为防御性载体感知对齐。
    - D（已修复）: `paths.py` 改 `SCHEMA_ROOT = QWQ_SCHEMA_ROOT or _REPO_DATA_ROOT/"schema"`（schema 是受版本控制的契约真相源，跟代码仓库走、不随运行时 `QWQ_DATA_ROOT` 漂移，仍可 env 覆盖）。证据：隔离 `QWQ_DATA_ROOT=/tmp/qwq_isolated_dtest` 下 `SCHEMA_ROOT` 仍解析到仓库 `quwoquan_data/schema`；**删除** e2e 手建软链后 `load_schema('produce','post_manifest')` 仍成功（之前 `Schema not found` 失败点解除），隔离/多环境免软链 schema。
  - 复核（2026-06-24 clean-root 去 few-shot 重跑）: 已按“最小依赖”完成 SOP / templates 精准瘦身——删除 `sop/主页/**/example.md` few-shot 范例、孤儿 `sop/moment.md`、孤儿蓝图 `templates/blueprints/Format/内容角度/主题/风光画报.tmpl.yaml`、纯文档 `templates/shared/style_guide.md` / `templates/shared/image_playbook.yaml` / `templates/_registry/DESIGN_10D.md`；`writing_pack.py` 不再注入 few-shot，`brief.py`/blueprint/writing_pack schema 与命令文档中的 `sopExampleRef` 入口已移除。关键回归：定向 40 tests 通过；`verify_quwoquan_data.sh` 与本轮改动直接相关部分全绿，唯一剩余失败为**用户侧现有脏任务树** `quwoquan_data/tasks/旅行/地域/测试省/景区/*` 的 `task lint`（`effective content.angles 为空`，非本轮 few-shot 清理引入）。在全新隔离根 `/tmp/qwq_e2e_clean_4hUtUj` 仅同步剩余 SOP 骨架（`guide.md` + `article.md` / `image.md` / `video.md` / `scenarios/*.md`）后，`task lint` OK，证明 clean env 不再依赖任何 example few-shot 文件；但真实 `cursor_sdk` managed local workflow 在 `build_homepage` checkpoint **再次**卡住：`task_workflow_state.status=manual_required`、`nextAction=build_homepage infrastructure failed after 3 attempts`、`page.md` 仍为占位。使用同一 `quwoquan_data/.venv` 直接跑 `env preflight --cursor-startup --model composer-2.5-fast --runtime local` 可稳定复现 `InternalServerError / httpStatus=500 / errorCode=internal`，与 batch 内三次 `build_homepage` `internal error` 同源；`verify scale-readiness` 对该 clean batch 给出 `decision=no_go`，blocker 包括 `workflow still waits at checkpoint: build_homepage`、`TokenLedger evidence missing`、`measured throughput evidence missing`、`firstPassRate evidence missing` 与 `daily target >=10000 requires queueBackend=reliabletask`。说明**few-shot 清理与最小 SOP 依赖已验证成立，但 cursor_sdk local 启动面在干净环境下仍未稳定解除 500 阻断**，R-CS03 主项证据不能以“曾经跑通一次”视作关闭。
  - 复核（2026-06-24 startup 500 根因继续收敛）: 已把 `https://api.cursor.com/v1/me` 的直探接入 `env preflight/ready`（`python_runtime.py` 新增 `cursorCloudApi`，`urllib` SSL EOF 时自动 fallback `curl`），避免再把资格问题误判为 `cursor_sdk` 本地逻辑故障。结果表明当前 `CURSOR_API_KEY` 直连 Cloud Agent API 稳定返回 `403 plan_required`，消息 `Cloud Agent is not available for free users. Please upgrade to Pro.`；此前 `cursor_sdk`/bridge 将同类资格错误折叠成 `InternalServerError 500`。真实验证：`quwoquan_data/tests/local_contract/cli/test_cli_environment__local_contract_test.py` 9 passed；`env preflight --json --cursor-startup --model composer-2.5-fast --runtime local` 现直接输出 `cursorCloudApi.status=403`、`errorCode=plan_required`，并跳过误导性的 startup probe。根因已从“local startup 500 不明”进一步收敛为“当前 key/账号不具备 Cursor Cloud Agent 可用资格（或需更换具备权限的 user/service-account key）”。
  - 复核（2026-06-24 新 key + `composer-2.5` clean-root 续跑）: 用户提供新的 `CURSOR_API_KEY` 后，`env preflight --cursor-startup --model composer-2.5 --runtime local` 已全绿：`cursorCloudApi.status=200`、`keyType=user_api_key`、`cursorStartup.status=finished`。沿同一隔离根 `/tmp/qwq_e2e_clean_4hUtUj` 续跑 batch `b1`，managed workflow 已从 `build_homepage` 真正推进到 `WORKFLOW COMPLETE`：主页正文写成并通过 `build_validate`，文章 `都江堰·行前怎么安排` 由真实 agent 创作，随后 `produce_annotate`、`produce_review`、`publish` 全部完成。期间新增发现并修复一层残留发布门：`release_integrity.py` 原把跨 post `asset sha/sourceAssetRef/sourceCollectionId` 复用视为违规，这与用户明确裁定“图文同源/多底稿同图引用均允许，不做去重拦截”冲突；现已移除该 cross-post 去重门，并通过 `quwoquan_data/tests/verify/test_release_integrity_gate.py` 12 passed 验证。`scale-readiness --mode commercial` 新证据：`workflowState.status=succeeded`、`executionReadiness.tokenLedgerCount=1`、`firstPassRate=1.0`、`runtimeIntegrity.passed=true`、`published=3`（homepage=1/article=1/image=1）。R-CS03 已不再受 Cursor startup / publish gate 阻断。
  - 状态: 待办（A/B/C/D 子项、SOP/templates 去 few-shot、Cursor startup、发布门残留去重均已完成并有 clean-root 证据；R-CS03 当前剩余 blocker 已收敛为放量级商业证据缺口：`queueBackend=reliabletask`、`staging/gamma import evidence missing`、`measured throughput 2.0534 objects/hour < required 416.6667 objects/hour`，另有 `trial sample is too small to extrapolate linearly` 警告。即功能链路已通、TokenLedger/firstPassRate 已出现首个真实样本，但距日产万级/十万级商用放量仍缺多实体真吞吐与正式环境导入证据）
- [x] R-CS04 创作侧 tag 投影端云一致缺口
  - 区域: App
  - 域: `content`（创作入口）
  - 原因: 阅读消费侧 tag 内联可点击 + codec round-trip 已闭环；但创作端仍只处理 entity span，正文 `@[label](tag:ref)` 内联未对称投影为 `tagRefs`、编辑态未保留 tag span。
  - 影响: 创作侧产出的正文 tag 内联在发布/编辑往返中丢失，端云 tagRefs 不一致。
  - 涉及文件: `quwoquan_app/lib/ui/content/entry/services/create_page_remote_helpers.dart`、`quwoquan_app/lib/ui/content/entry/providers/create_editor_provider.dart`
  - 证据: 新增 `tagRefsForPayload(state)`（正文 `span.isTag` 内联剥 `tag:` 前缀 + `settings.tagRefs` Set 合并去重），`buildArticleMarkdownForPayload`/`buildCreatePostPayloadMap` 改用之；编辑态 `_toggleSpansInRange` 由 `isEntity` 放宽为 `isInlineMention` 保留 tag span；`flutter analyze` 4 文件 0 issue、相关 4 测试文件 70 用例全绿（含 entity 不回归）。
  - 状态: 已解决（2026-06-21；App 侧 tag 与 entity 完全对称这一目标已达成。注：端云真正落库 entity/tag refs 受 R-CS06 阻断，App 侧对称是其前置而非终点）
- [x] R-CS06 App 发布侧 semanticMentions 端云契约断裂（entity+tag 内联均不落服务端 refs）
  - 区域: App / Service
  - 域: `content`
  - 原因: 服务侧 `content-service` `semantic.Project` 已对称支持 entity/tag，且把 `tagRefs/entityRefs` 当作 published `semanticMentions` 的只读投影（`post_service` 在 `SemanticMentions` 存在时直接覆盖 refs）。但 App 发布**从不构建结构化 `semanticMentions`**（kind/status/targetRef 数组）；顶层 `tagRefs/entityRefs` 被 wire `createWritableFields` 剥离（非可写字段）；wire codegen 按字段名硬编码把 `semanticMentions/reviewAspects` 误生成为 `String?`，与服务侧期望的 `[]object` 数组不一致（R06/R24 桥接债）。
  - 影响: 端侧创作的 entity 与 tag 正文内联发布后**均无法落到服务端 `post.TagRefs/EntityRefs`**，端云 semanticMentions grounding 链在 App 发布侧断裂，削弱云侧可点击数据来源与推荐 grounding（注：数据工程 materialize 侧已能写 manifest semanticMentions，断点专指 App 用户创作发布路径）。
  - 正确设计: metadata-first——wire 字段类型由 `fields.yaml` 的 `type` 驱动渲染（`[]object`→`List<CloudJsonMap>?`，object/GeoPoint→`CloudJsonMap?`，标量/ObjectId→`String?`），消除按字段名硬编码 switch；App 发布由正文 entity/tag 内联 + settings/homepage 构建 published `semanticMentions` 行并提交；服务侧 `Project` 投影落 `entityRefs/tagRefs`（pending/rejected 不落、published+非法 targetRef 整单拒绝、顶层 refs 与投影不一致拒绝）。
  - 涉及文件: `quwoquan_service/tools/codegen_app_metadata/content_post_mutation_wires_codegen.go`+`main.go`、`quwoquan_app/lib/cloud/runtime/generated/content/content_post_mutation_wires.g.dart`、`quwoquan_app/lib/ui/content/entry/services/create_page_remote_helpers.dart`、`quwoquan_service/services/content-service/internal/application/post_service.go`（`applySemanticMentionPayload`）
  - 证据:
    - 契约: wire codegen 改为 metadata type 驱动 + `_mutationMapList` helper；三处 wire 类（Create/Update/PromoteToWork）`semanticMentions`/`reviewAspects` 由 `String?` → `List<CloudJsonMap>?`，`illustrationAssetId`/`sourcePostId` 等 ObjectId 标量不回归仍为 `String?`；`make codegen-app` 幂等无新漂移。
    - App: `create_page_remote_helpers.dart` 新增 `semanticMentionsForPayload`（entity+tag 内联/settings/homepage → published 行 + `isSemanticTargetRefValid` 镜像服务端校验去非法/candidate），`buildCreatePostPayloadMap` 注入；`flutter analyze` 2 文件 0 issue。
    - 测试: App `publish_payload_contract_test.dart` + `publish_draft_projection_bridge_test.dart` 共 28 用例全绿（含 semanticMentions 结构化数组、投影、去重过滤、wire round-trip、tagRefs/entityRefs 不入 wire）；Go `create_semantic_projection_test.go` 3 用例（published entity+tag 落 refs / pending+rejected 排除 / published 非法 targetRef 拒绝 / 顶层 refs 偏离投影拒绝）+ `content_post_mutation_wires_codegen_test.go` 1 用例（[]object→List<CloudJsonMap>? 等类型映射）全绿；`go build/vet ./services/content-service/... ./tools/codegen_app_metadata/...` 绿。
  - 状态: 已解决（2026-06-21；App 用户创作发布路径 entity+tag 内联经结构化 semanticMentions 端云落 refs，metadata-first 契约对齐，桥接债清除）
- [ ] R-CS07 current release 发布面缺实体主页闭环
  - 区域: Data
  - 域: `content-supply`（release publish / homepage lane）
  - 原因: `quwoquan_data/scripts/cli.py verify --scope current` 已收窄为只扫描当前 `quwoquan_data.post_manifest` schema 的 release posts 根；旧无 schema 测试 release 已排除，但当前 schema release 仍存在已发布 post 的主 `entityRefs[0]` 缺同 release 下 `entities/.../page.md` 实体主页产物。`publish.gate` 对 assembled release 要求已发布 post 的主实体主页闭环，`allowPartialContent` 只允许缺计划 post，不允许已发布 post 缺主页。
  - 影响: `make verify` / `verify-quwoquan-data` 被真实发布面质量门阻断；缺实体主页会造成内容消费、搜索承接、推荐交集理由和 entity landing 的端到端链路断点。不能用手写 stub 或放宽 gate 补绿，必须从对应 task/batch 的 homepage lane 重新生产、审核、发布可追溯主页产物，或明确将不完整 release 移出 current 发布面。
  - 涉及文件: `quwoquan_data/scripts/_common/post_verify.py`、`quwoquan_data/scripts/publish/gate.py`、`quwoquan_data/release/旅行__地域__四川省__景区__全国5A景区source-ready资产闭环验证v18__source_ready_assetrefs_10_20260619_02/`、`quwoquan_data/release/旅行__主题__网站供给线__维基导游百级真实运营验证__real_*`
  - 证据: `python3 quwoquan_data/tests/verify/test_verify_scope_semantics.py` 通过；`python3 quwoquan_data/scripts/cli.py verify --scope current` 仍失败，剩余问题包含 `release missing primary entity homepage(s)` 与 `release entity quota: expected 20, got 0`，以及因缺实体闭环导致的 `intersection dimension missing: content`。
  - 状态: 待办（2026-06-21 用户确认登记；下一轮应走 CLI-first 的 homepage lane 补产物或清理 current 发布面归属）
- [ ] R-CS05 video 作品链路后置
  - 区域: Data
  - 域: `content-supply`（video 形态）
  - 原因: 用户主动 defer，计划 §14 Out of Scope；video research lane / producer / 作品判定 / 权利安全门未实现。
  - 影响: 当前仅支持 entity / article / image 三形态，video 作品不可生产。
  - 涉及文件: 计划 §14、produce video lane（未建）
  - 状态: 待办（后置，需用户明确启动）
- [ ] R-CS08 视频商用全矩阵外部依赖未齐备
  - 区域: App / Service / Data / Ops
  - 域: `runtime-media` / `content`
  - 原因: 本轮只收口“视频封面发布展示工程闭环”，但 runtime-media 商用全矩阵仍依赖真实 beta/gamma 网关、self-hosted Android/iOS runner、ECS/pre 环境、对象存储与视频转码/封面生成链路的非 dry-run 通过报告；这些外部运行条件尚未齐备。
  - 影响: 即使 App/Service/Data 的视频 `videoUrl + thumbnailUrl/coverUrl + coverStrategy + coverFrameTimeMs + duration/size` 合同已在 local_contract/scoped tests 闭合，也不能宣称“一流成熟商用视频能力”或“视频商用端到端全矩阵完成”；相关 GWT 的 gamma api_integration/user_acceptance 证据必须保持 pending 或 GATE_BLOCK。
  - 涉及文件: `specs/feature-tree/runtime/runtime-media/video-end-to-end-commercial-matrix.md`、`specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/acceptance.yaml`、`specs/feature-tree/discovery-content/content-display-journey-consistency/video-display-journey/acceptance.yaml`、`agent_ops/deploy/stackctl.py`
  - 状态: 待办（2026-06-22 用户确认登记；需四环境非 dry-run passed 报告、真实移动 runner、ECS/pre 与对象存储/转码链路证据齐备后方可关闭）
- [ ] R-CS09 普通网页/UGC 底稿轻改商用的版权风险（full light-edit 裁定）
  - 区域: Data
  - 域: `content-supply`（produce author / 来源权利分层）
  - 原因: 用户裁定 `factual_reference_only`（去哪儿游记、百科、普通攻略等他人 UGC）与 `licensed_adaptation` 同等以底稿为骨架轻改，可保留优质原句/自然段，`baseDraftFidelity` 对两类来源统一生效。此前代码刻意把 `factual_reference_only` 限制为纯事实证据池（不保留长句/结构）正是为规避他人 UGC 商用复刻的版权风险；本次按用户选择移除了该法律安全策略（`base_draft.py` 贴合度门、`content_review.unauthorized_expression_reuse_issues`、`release_integrity` factual-as-adaptation 门、`writing_pack`/`run.py` author 合同均已统一为底稿轻改）。
  - 影响: 商用发布时，对未获授权的他人 UGC 进行骨架+原句级保留的轻改改写存在著作权侵权风险；去平台名/作者署名/水印只降低来源痕迹，不构成版权许可。需在商用放量前补充来源授权/版权合规策略（如限定为公版/CC/自有授权来源，或获取 UGC 平台改编授权），否则规模化发布放大法律敞口。
  - 涉及文件: `quwoquan_data/scripts/_common/base_draft.py`、`quwoquan_data/scripts/_common/writing_pack.py`、`quwoquan_data/scripts/_common/content_review.py`、`quwoquan_data/scripts/_common/release_integrity.py`、`quwoquan_data/scripts/task/run.py`、`.cursor/skills/quwoquan-data-content/SKILL.md`「来源权利分层」
  - 状态: 待办（2026-06-23 用户确认接受版权风险并裁定 full light-edit；商用放量前需落地来源授权/版权合规策略）

## 创作发布流体验（Create/Publish Flow）

- [x] R-CR01 「附近地点访问失败」整页断点：CreateLocationService 在 mock 环境仍强发 gateway + 系统定位
  - 区域: App
  - 域: `content/entry`、`integration`
  - 原因: `CreateLocationService` 原为直接 `new` 的具体类，alpha/mock 也走真实 gateway 请求 + 系统定位；无网关/密钥/定位权限时必现「附近地点访问失败」。
  - 影响: 发布流「选位置」首屏断点，alpha/开发态不可用。
  - 方案: 三层化（abstract `CreateLocationService` / `RemoteCreateLocationService` / `MockCreateLocationService` 本地 canonical POI，不发 HTTP、不依赖系统定位）；`createLocationServiceProvider` 按 `appDataSourceModeProvider` 切换；`create_page` 去除裸 `new`。
  - 涉及文件: `quwoquan_app/lib/ui/content/entry/services/publish_settings_services.dart`、`quwoquan_app/lib/core/providers/app_providers.dart`、`quwoquan_app/lib/ui/content/entry/pages/create_page.dart`
  - 证据: `test/core/providers/create_location_service_provider_test.dart`（mock→Mock / remote→Remote / mock nearby 永不为空）+ `test/ui/content/entry/contract/location_circle_services_contract_test.dart`（Remote+Mock 契约）+ 既有 `location_selector_page_widget_test.dart` / `entry_location_error_journey_test.dart` 合计 17 测试绿；`verify_ui_mock_isolation`、`verify_ui_app_data_source_mode_ratchet` 均 OK。
  - 状态: 已解决（2026-06-24）

- [x] R-CR02 错误展示载体（全屏 vs 弹窗 vs 卡片/footer/toast）边界未文档化、无回归门
  - 区域: App
  - 域: `runtime-client-foundation`（错误语义）
  - 原因: presentation 选择只存在于 `_presentationFor` 代码内，规格文档缺权威决策矩阵；术语沿用项目并不存在的 `SnackBar`。
  - 影响: 错误 UI 边界口径易漂移，无法检测后续误改。
  - 方案: `specs/ux/error-and-permission-semantics.md` 新增 §1.13「错误展示载体决策矩阵（全屏 vs 弹窗 权威边界）」，冻结 `UiErrorPresentation`→组件映射、`category×scope`→presentation 决策树与互斥边界；术语统一为「弹窗 actionDialog / 轻提示 AppToast」。
  - 涉及文件: `specs/ux/error-and-permission-semantics.md`、`quwoquan_app/test/core/errors/ui_error_semantics_test.dart`
  - 证据: `ui_error_semantics_test.dart` 新增「错误展示载体决策矩阵」7 条用例，逐条断言 `(category, scope)→presentation`，改坏 `_presentationFor` 即红。
  - 状态: 已解决（2026-06-24）

- [x] R-CR03 图片选择器相册下拉贴底弹出 +「最近项目」命名 + PC/桌面选择器缺失（图一）
  - 区域: App
  - 域: `content/entry`（媒体选择）
  - 原因: 相册下拉用 `showCupertinoModalPopup` 贴底从下往上长，选项多时可用性差；相册显示名未统一（应「全部照片」并置顶）；桌面无 `file_picker` 选目录 + 记忆上次目录 + 递归扫描含图子目录聚合为相册。
  - 影响: 移动端相册下拉体验差；PC/桌面无法选图（能力缺口）。
  - 方案（规划）: 抽 `AppTopAnchoredDropdown` 顶部锚定下滑浮层（自适应高度 + 封顶内容区 + scrim 关闭）；`hasAll` 相册置顶 + 显示名「全部照片」；桌面经 `PlatformCapabilities` 能力位路由到 file_picker 选目录（`FileStorageGateway` 持久化上次目录）+ 递归扫描，多选/拖拽复用 `MediaReorderableView`；缺失即结构化降级。
  - 涉及文件: `quwoquan_app/lib/components/media/picker/create_media_picker_page.dart`、`quwoquan_app/lib/components/media/picker/create_media_picker_presentation.dart`、`quwoquan_app/lib/components/media/picker/image_pick_gateway.dart`
  - 状态: 已解决（2026-06-24）。
    - 相册下拉：新增 `quwoquan_app/lib/core/widgets/app_top_anchored_dropdown.dart`（`showAppTopAnchoredDropdown` 顶部锚定下滑 + 自适应高度封顶 + scrim 关闭），`create_media_picker_page.dart` 与桌面页统一复用；移动端 `isAll` 相册置顶并显示「全部照片」（`UITextConstants.mediaPickerAlbumAllPhotos`）。证据：`test/core/widgets/app_top_anchored_dropdown_test.dart`、`test/local_contract/content/create/photo_media_picker_commercial_flow__local_contract_test.dart`（含 `isAll` 置顶用例）。
    - 桌面选择器：`FileStorageGateway` 新增 `listDirectory`（io/web 实现 + 5 个测试 fake stub）；新增 `DesktopImageAlbumScanner`（递归扫描含图子目录聚合相册、跨目录「全部照片」置顶、深度/目录数/单册封顶）、`desktop_picker_services.dart`（`DesktopDirectoryPicker`/`DesktopPickerDirectoryMemory` 记忆上次目录 + `shouldUseDesktopImagePicker` 能力位路由判据）、`DesktopImagePickerPage`（多选编号 + 已选条复用 `MediaReorderableView` 拖拽重排 + 相册下拉复用 `AppTopAnchoredDropdown` + 缩略图走 `gateway.readAsBytes`/`Image.memory` 不新增 `dart:io` + 缺能力位/空目录结构化降级）；`create_page._openMediaPicker` 按 `shouldUseDesktopImagePicker` 路由。证据：`test/components/media/desktop_image_album_scanner_test.dart`、`test/components/media/desktop_picker_services_test.dart`、`test/components/media/desktop_image_picker_page_widget_test.dart`；页面矩阵已登记 `desktop_image_picker_page.dart`（T5）+ `metadata_driven_ui_gap_inventory` exempt。
    - 注：「最近项目」命名项随相册显示名统一收口（移动端聚合册显示「全部照片」），不再单列「最近项目」命名债。

- [ ] R-CR04 CreateLocationService 与 CreateLocationOption 模型分层债（lib/ui → lib/cloud/services/integration）
  - 区域: App
  - 域: `content/entry`、`integration`
  - 原因: R-CR01 三层化时，服务 + Mock + `CreateLocationOption` 模型仍位于 `lib/ui/content/entry/{services,models}`，理想应在 `lib/cloud/services/integration`（对齐 `01-arch-constraints` §2.1）。受 `verify_ui_app_data_source_mode_ratchet`（禁止 lib/ui 引用 `appDataSourceModeProvider`）约束，provider 已集中在 core，但服务实现仍在 ui。
  - 影响: 偏离端云目录约束；不违反现有门禁（mock 隔离 / 数据源棘轮均绿）。迁移需连带搬 `CreateLocationOption` 模型并改多处 import。
  - 涉及文件: `quwoquan_app/lib/ui/content/entry/services/publish_settings_services.dart`、`quwoquan_app/lib/ui/content/entry/models/publish_settings_models.dart`、`quwoquan_app/lib/core/providers/app_providers.dart`
  - 状态: 待办（2026-06-24 用户「系统性梳理遗留事项」确认登记；建议待 create-flow 并发编辑收束后随 R-CR03 一并迁移）

## 测试治理与目录迁移（Three-layer Test Migration）

- [x] R-TST01 三层测试目录的物理迁移尚未全仓完成
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 旧风险来自“三层目录只在 App 先落地，Service/Data/Ops 仍停留在 legacy 目录”的半迁移状态。2026-06-22 已通过 canonical bridge + inventory version 2 把全仓 legacy suite 全部纳入唯一三层执行根：App 377、Service 183、Data 101、agent_ops 9，`pending=0`。
  - 影响: canonical 三层目录现已成为 App / Service / Data / Ops 的唯一执行入口与 acceptance 主证据口径；legacy 文件即使暂留原处，也只能通过 canonical bridge 被发现与引用，不再形成第二真相源。本项关闭表示“治理执行面已收口”，不表示 legacy 测试文件已全部物理搬迁或从磁盘移除。
  - 涉及文件: `specs/gates/test_directory_inventory.yaml`、`agent_ops/scaffold/{test_directory_inventory_lib.py,generate_canonical_test_bridges.py,generate_test_directory_inventory.py,verify_test_directory_inventory.py,normalize_acceptance_recorded_paths.py}`、`Makefile`、`agent_ops/gate/gate_repo.sh`、`specs/03_TESTING_STRATEGY.md`
  - 证据:
    - `python3 agent_ops/scaffold/generate_canonical_test_bridges.py`
    - `python3 agent_ops/scaffold/generate_test_directory_inventory.py`
    - `python3 agent_ops/scaffold/verify_test_specs.py`
    - `python3 agent_ops/scaffold/verify_test_directory_inventory.py`
    - `python3 agent_ops/scaffold/verify_test_no_fake.py`
    - `python3 agent_ops/scaffold/verify_test_coverage_map.py`
    - `cd quwoquan_service && go test ./services/.../tests/local_contract -count=1`
    - `cd quwoquan_service/services/{assistant-service,entity-service,search-service} && go test ./tests/api_integration -count=1`
  - 状态: 已解决（2026-06-22；canonical 三层根、bridge、inventory 与 gate 全部落地，legacy 路径已退出主证据口径；2026-06-22 晚复核补充：关闭口径限定为治理执行面，不等于物理迁移完成）

- [x] R-TST02 Service/Data/Ops 的三层归类仍有启发式基线，需逐套件语义复核
  - 区域: Service / Data / Ops
  - 域: `runtime-test-pyramid`
  - 原因: 旧风险来自“层归类只停留在口头约定，无法追溯每个 suite 为什么落到某个 canonical 层”。2026-06-22 起，inventory version 2 为每个 Service/Data/Ops suite 固化 `current_path -> target_path -> classification_basis -> migration_status`，不再存在“默认都算某一层”的隐式归类。
  - 影响: 三层覆盖口径现在以 canonical target path 与 `classification_basis` 为准；后续若需要调整某个 suite 的层级，必须修改真相源并重新生成 bridge，而不是在 acceptance 或脚本里临时放宽。本项关闭表示“suite 归类已显式可追溯”，不表示分类逻辑已完全脱离路径/命名规则推导。
  - 涉及文件: `agent_ops/scaffold/test_directory_inventory_lib.py`、`specs/gates/test_directory_inventory.yaml`
  - 证据:
    - `specs/gates/test_directory_inventory.yaml` 中 Service/Data/Ops 全量条目均含 `classification_basis` 与 `migration_status: bridged`
    - `python3 agent_ops/scaffold/verify_test_directory_inventory.py`
    - `python3 agent_ops/scaffold/verify_test_coverage_map.py`
    - `agent_ops/scaffold/verify_test_coverage_map.py` 已阻断“有 case id 无 canonical 文件”“有 recorded 但无 canonical 归属”“有 Journey 无 page case”
  - 状态: 已解决（2026-06-22；suite 归类已收敛为显式 inventory 真相源，不再是不可追溯的隐式基线；2026-06-22 晚复核补充：分类结果已显式化，但生成逻辑仍需后续门禁继续收紧）

- [x] R-TST03 canonical `make test-local-contract` 仍被 9 个既有 App 红测阻断
  - 区域: App
  - 域: `runtime-test-pyramid`
  - 原因: 本轮已把 `make test-local-contract` 切到 `test/local_contract/` canonical 入口并成功执行 2500+ 测试，但最终仍被 9 个既有 App 用例阻断。通过直接回放原 legacy 文件确认，失败在迁移前已存在：`chat_message_bubble_widget_test.dart` 3 条（图片/视频预览断言）、`chat_receipt_ui_widget_test.dart` 1 条（图片消息回执缺 `ProviderScope`）、`homepage_detail_page_widget_test.dart` 1 条（缺“主页暂不可用”文案）、`location_selector_page_widget_test.dart` 1 条（缺超时文案）、`work_browser_entry_page_test.dart` 1 条（缺“这个作品不可用了”文案）、`home_circles_hub_page_test.dart` 2 条（缺图片/视频卡片 key）。
  - 影响: 三层目录迁移本身已成立，但 `make test-local-contract` 不能作为全绿证据；若不单独登记，后续很容易把这 9 个存量红灯误判成 canonical wrapper 或目录门引入的回归。
  - 涉及文件: `quwoquan_app/test/{local_contract,ui}/chat/widgets/{chat_message_bubble_widget_test.dart,chat_receipt_ui_widget_test.dart}`、`quwoquan_app/test/{local_contract,ui}/entity/pages/homepage_detail_page_widget_test.dart`、`quwoquan_app/test/{local_contract,ui}/content/entry/widgets/location_selector_page_widget_test.dart`、`quwoquan_app/test/{local_contract,ui}/content/pages/work_browser_entry_page_test.dart`、`quwoquan_app/test/{local_contract,ui}/circle/pages/home_circles_hub_page_test.dart`
  - 证据:
    - 根因：产品已切 `AppPageErrorState`+`runtimeErrorSemantic`（标题/说明与旧 `UITextConstants.*Unavailable*` 不同）、聊天图片改 `AppCachedNetworkImage`（非 `Image`）、圈子 hub feed 改契约 seed（grid key 与 category 过滤不对齐）、摄影 tab inline carousel 禁用外层 onTap。
    - 修复：9 个 legacy 测试对齐当前产品契约（非 shim）；圈子 grid 测试用 `_LegacyHubCircleFeedRepository` 稳定样本 + 视频帖覆盖 work-browser 导航。
    - `flutter test` 上述 6 legacy 文件 47 用例 + 6 canonical wrapper 47 用例全绿（2026-06-21）。
  - 状态: 已解决（2026-06-21；9 个存量红测已修，`make test-local-contract` 阻断项消除；全量 2500+ 套件仍建议 CI 定期跑）

- [ ] R-TST04 canonical 治理完成与物理迁移完成仍可能被混读
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 本轮已把 `pending_count`、bridge 语义和 backlog/acceptance 文案校准为“治理执行面完成”，但仓库中仍保留 670 个 grandfathered legacy 源测试，且 `specs/gates/test_legacy_source_allowlist.yaml` 会长期存在，说明“canonical 已接管执行”与“legacy 已物理清零”仍是两件事。
  - 影响: 若后续只看 `pending_count=0` 或已关闭的 `R-TST01/R-TST02`，仍可能误判为“磁盘已无 legacy”“允许删除 allowlist / bridge 机制”，从而造成迁移完成度漂移。
  - 涉及文件: `specs/03_TESTING_STRATEGY.md`、`specs/gates/test_directory_inventory.yaml`、`specs/gates/test_legacy_source_allowlist.yaml`、`specs/feature-tree/runtime/runtime-test-{pyramid,infra}/**`
  - 证据:
    - `specs/gates/test_directory_inventory.yaml` 已为 `pending_count: 0`
    - `specs/gates/test_legacy_source_allowlist.yaml` 当前 `grandfathered_current_paths: 670`
    - 2026-06-22 已同步收紧 `specs/03_TESTING_STRATEGY.md`、`runtime-test-pyramid/spec.md`、`runtime-testinfra/spec.md` 的完成口径
  - 状态: 待办（2026-06-22 用户确认登记；后续若启动物理迁移 burn-down，需单列计划逐步减少 allowlist）

- [ ] R-TST05 `api_integration` / `user_acceptance` 统一执行入口仍依赖外部环境与凭证注入
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid`
  - 原因: 本轮已把 `Makefile` / `gate-full` 与 `prod_gray_initial`、`gamma_local` 语义对齐，但远端层仍必须依赖 `BETA/GAMMA/PROD_*_BASE_URL` 与测试 token；仓库本身不能在裸 shell 中自举出可运行的 `api_integration` / hosted `user_acceptance`。
  - 影响: 三层执行入口虽已同源，但无法在任意开发机上直接得到“远端层为绿”的完整证据；一旦 CI/本地环境变量或拓扑准备缺失，验证会停在前置检查而不是业务断言。
  - 涉及文件: `Makefile`、`agent_ops/deploy/smoke/run_environment_patrol_smoke.py`、`.cursor/skills/environment-ops/SKILL.md`
  - 证据:
    - `make verify-test-remote-env MODE=api_integration ENV=gamma` 会在入口即阻断缺失的 `GAMMA_BASE_URL`、`GAMMA_PRODUCT_OPS_BASE_URL` 与 token（2026-06-22 晚补）
    - `make verify-test-remote-env MODE=user_acceptance TARGET=gamma-local` 可在无远端前置时直接通过
    - `PROD_BASE_URL=https://example.invalid PROD_PRODUCT_OPS_BASE_URL=https://example.invalid TEST_AUTH_TOKEN=dryrun USER_ACCEPTANCE_DRY_RUN=1 make verify-test-remote-env MODE=user_acceptance TARGET=prod-hosted` wiring 通过（2026-06-22 晚补）
    - `ENV=gamma make test-api-integration` 当前直接被 `GAMMA_BASE_URL` 缺失阻断（2026-06-22）
    - `PROD_BASE_URL=https://example.invalid PROD_PRODUCT_OPS_BASE_URL=https://example.invalid TEST_AUTH_TOKEN=dryrun USER_ACCEPTANCE_DRY_RUN=1 make test-user-acceptance TARGET=prod-hosted` wiring 通过（2026-06-22）
  - 状态: 待办（2026-06-22 用户确认登记；当晚已补 `verify-test-remote-env` preflight，但远端层仍需 stackctl / CI secret / 拓扑准备才能真正实跑）

- [x] R-TST06 acceptance case 到 canonical file / report 的严格 traceability 尚未全仓铺满
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 旧风险来自 strict traceability 只覆盖局部治理节点，full strict 诊断一度仍有 `23` 份 acceptance 文件、`55` 个 layer 级缺口。2026-06-22 夜间继续补齐 `exposure-observability-capacity` 的 direct canonical `local_contract` 与 `config-and-reliability-governance` 的 canonical `api_integration` 后，最后两条真实缺桥/缺测试路径也已收口。
  - 影响: 当前全仓 acceptance case 均能追溯到 canonical file 或 `report.json.case_results[]`，新增 recorded 漂移会被 `verify_test_coverage_map.py` strict hard gate 即时阻断。本项关闭表示“strict traceability 治理面已全仓收口”，不表示后续可以跳过 recorded / report 回填；任何新增节点若掉出 canonical 追溯链，都会立即重新触发门禁。
  - 涉及文件: `agent_ops/scaffold/verify_test_coverage_map.py`、`specs/feature-tree/**/acceptance.yaml`、`quwoquan_service/services/content-service/tests/local_contract/internal/application/exposure_observability_capacity__local_contract_test.go`、`quwoquan_service/services/platform-ops-service/tests/api_integration/config_and_reliability_governance__api_integration_test.go`
  - 证据:
    - 2026-06-22 初版 full strict 诊断为 `23` 份 acceptance 文件、`55` 个 layer 级缺口
    - 2026-06-22 晚间首轮扩围后已把 full strict 缺口压到 `20` 份 acceptance 文件、`26` 个 layer 级缺口
    - 2026-06-22 深夜第二轮扩围后，`verify_test_coverage_map.py` hard gate 已覆盖 runtime 节点、17 个业务/能力节点与 `comment-thread` 的 13 个 item 级 GWT
    - 2026-06-22 收尾补上 `comment-thread.GWT12` 的真实 canonical `api_integration` 后，`comment-thread` item-level strict 扩到 `14` 个 GWT
    - 2026-06-22 夜间继续补上 `xiaoqu-entry-handoff` 的真实 canonical `api_integration` 后，hard gate 覆盖扩到 `18` 个业务/能力节点
    - 2026-06-22 夜间继续把 `page-horizontal-quality` 与 `realtime-push-and-offline-sync` 纳入 strict hard gate 后，hard gate 覆盖扩到 `20` 个业务/能力节点
    - 2026-06-22 夜间补上 `exposure-observability-capacity` 的 direct canonical `local_contract` 并纳入 strict hard gate 后，full strict 诊断收敛到 `1` 份 acceptance 文件、`1` 个 layer 级缺口
    - 2026-06-22 夜间补上 `config-and-reliability-governance` 的 canonical `api_integration` 并纳入 strict hard gate 后，full strict 诊断归零：`0` 份 acceptance 文件、`0` 个 layer 级缺口
    - `make verify-test-coverage-map`
    - `make verify-test-specs`
    - `make verify-test-directory-layout`
    - `make verify-test-no-fake`
    - `python3 agent_ops/scaffold/verify_test_coverage_map.py`
  - 状态: 已解决（2026-06-22；当晚已把 full strict 缺口从 `55` 压到 `0`，strict traceability hard gate 现已全仓闭环）

- [ ] R-TST07 旧 `T1-T4/L1-L4` 口径与 grandfathered legacy 例外仍散落仓库
  - 区域: App / Service / Data / Ops / Docs
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 本轮已清理核心 testing 规则、脚本、模板、README 与 Patrol 用例中的人类可读旧口径，并继续收掉四批真正可去掉的 grandfathered skip：一批是 deterministic 场景（assistant/user），一批是 `chat-service` / `content-service` / `rtc-service` 里由 `TestMain` 已兜底却仍留在文件内的冗余依赖双保险，一批是 `content-service/cmd/import` 与 `http_model_client` 这类可直接自举/去 loopback 的独立测试，最新一批是 `user-service/tests` 在混合 `pg/redis always-on + mongo optional` 运行时上补了按需 Mongo runtime 升级与 handler 重建，不再把文件级 `t.Skip` 当作环境契约。
  - 影响: 新增 debt 已能被 ratchet 阻断，deterministic 场景、已由 `TestMain` 承诺初始化的 legacy skip、独立可自举测试、`user-service` 这批“显式依赖 Mongo 但不该把 skip 散落在文件里”的历史例外，以及 `chat-service` 里真实缺失的 `AssistantRemoved` 事件链路都已继续收缩；但存量运行时旧命名与剩余 grandfathered 例外仍会维持历史心智负担，也意味着 `legacy-source-no-fake` 还不是零债基线。
  - 涉及文件: `specs/gates/test_legacy_source_allowlist.yaml`、`agent_ops/scaffold/{verify_test_specs.py,verify_test_no_fake.py}`、`quwoquan_app/test/patrol/**`、`docs/personal-assistant/README.md`、`quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py`
  - 证据:
    - `specs/gates/test_legacy_source_allowlist.yaml` 当前 `bench_only_allowed_sources: 1`、`skip_grandfathered_sources: 2`
    - 2026-06-22 晚补后，`T4 Patrol E2E` / `L4 Patrol` / `T4 tests must run` / `T1-T4 测试` 等人类可读旧口径在非产物文件中已清零；剩余命中主要是运行时接口名与历史 tier 语义
    - 2026-06-22 深夜继续去掉 `assistant-service/internal/{adapters/http/handler_test.go,application/m11_local_scenario_test.go}` 与 `user-service/tests/error_contract_test.go` 的 skip grandfathered 后，`make verify-test-no-fake` / `make verify-test-directory-layout` / `make verify-test-specs` 继续全绿
    - 2026-06-22 深夜继续去掉 `chat-service/tests/{direct_conversation_relationship_gate_test.go,send_message_relationship_gate_test.go}`、`content-service/tests/{comment_keyset_explain_bench_test.go,intersection_watermark_store_contract_test.go,post_cache_contract_test.go,viewer_object_intersection_store_contract_test.go,redis_router_contract_test.go}` 与 `rtc-service/tests/one_to_one_relationship_gate_test.go` 的冗余 skip 双保险后，`make verify-test-no-fake` / `make verify-test-directory-layout` / `make verify-test-specs` 继续全绿
    - 2026-06-23 凌晨继续给 `content-service/cmd/import` 补 `TestMain` 自举 Mongo，并把 `http_model_client_test.go` 改成内存 `RoundTripper` 后，`cmd/import` canonical wrapper、`make verify-test-no-fake`、`make verify-test-directory-layout`、`make verify-test-specs` 继续全绿
    - 2026-06-23 凌晨继续把 `user-service/tests/{block_cascade_contract,follow_contract,greeting_request_state_machine,persona_contract,sub_account_view_contract}.go` 的文件级 skip 改为按需 `requireMongoBackedRuntime`，并在 `TEST_MONGO_URI=mongodb://127.0.0.1:37019` 下实跑 `go test ./tests -count=1`；`make verify-test-no-fake` / `make verify-test-directory-layout` / `make verify-test-specs` 继续全绿
    - 2026-06-23 清晨继续给 `chat-service` 补 `AssistantRemoved` metadata/codegen/handler 事件链路，并把 `event_publish_contract_test.go` 从 skeleton skip 改成真实断言；在 `TEST_MONGO_URI=mongodb://127.0.0.1:37020` 下实跑 `go test ./tests -run 'TestRemoveAssistant|TestEventPublish_AssistantRemoved|TestEventPublish_SupportedEventTypesComplete' -count=1` 通过。`event_publish_contract__api_integration` canonical wrapper 仍被同文件内既有 `createConversation` 基线红测阻塞，不属于本轮新增回归。
  - 状态: 待办（2026-06-22 用户确认登记；截至 2026-06-23 清晨已清掉 README / 注释 / Patrol 文案旧口径，并把 `skip_grandfathered_sources` 从 21 压到 2；后续需继续 burn-down 运行时接口旧命名、app 侧最后 2 条 legacy skip，以及 chat-service 事件发布套件里与本轮无关的 `createConversation` 基线红测）
