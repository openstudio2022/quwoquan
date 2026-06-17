# L3 Scenario: search-object-taxonomy-and-provider-registry

## 节点定位

- `L1_domain_service`: `global-search-experience`
- `L2_business_capability`: `search-provider-routing-and-storage-topology`
- `L3_story`: `search-object-taxonomy-and-provider-registry`

## 背景与动机

如果 searchable object 继续以页面、仓库或服务内部名字存在，统一搜索接口很快会退化为一个壳。该 Scenario 用来冻结 object taxonomy 与 provider registry。

## 功能范围

- searchable object 的统一命名。
- object -> provider -> execution mode 的注册表。
- objectType 与展示语义、跳转语义的绑定边界。
- 外部网页对象与趣我圈内部对象共用同一 taxonomy。

## Out of Scope

- 排序策略。
- 存储实现。

## 约束

- objectType 必须是统一枚举或 metadata 注册项。
- 页面层不得自定义新的搜索对象字符串。
- taxonomy 必须覆盖 `web.document`，使 AI 能通过同一接口同时检索网页与站内对象。

## 第一方地点对象 location.place（R-S05e，force_target）

在跨对象 geo/地点维度（`runtime/search.Document.Geo` + `Fields[placeName/placeId]` + `filters.near`）之上，新增一类**复用该维度的第一方对象 target**：`location.place`（`ai_targets.location`）。

### 对象定义

- `object_type = location.place`，`ai_target = location`，`domain = content`，`provider = content_remote`，`execution_strategy = remote_only`。
- 它是被内容引用的「自由文本地点」聚合去重后的第一方快照对象，进入统一 `quwoquan_objects` 索引，与其它对象一起被 canonical `search(request)` 召回、排序、引用。
- 复用既有 geo 维度字段承载坐标与地名：`Document.Geo`（真实坐标，缺失则为空）+ `Fields[placeName]`（人类可读地名，同时作为 `Title` 供 term 命中）。不新造平行字段。

### 与 entity.homepage 的边界（单一真相源）

- `location.place` **仅覆盖**「被内容引用、但尚未绑定 `canonicalEntityId` / `primaryHomepageId` 的自由文本地点」。
- 一旦某地点被提升为 canonicalEntity（成为 `entity.homepage`），其 `location.place` 对象即被删除，由 `entity.homepage` 承载。
- 因此同一地点在统一索引中**只出现一次**：未提升 → `location.place`；已提升 → `entity.homepage`。geo 维度只有一套机制，二者互斥不重复。

### 身份与去重

- canonical 身份 = `place_` + `sha1(normalize(locationName) + "|" + 粗 geohash(lat,lng,precision=5))` 前 16 hex。
- 规范化地名做大小写折叠 + 去空白；坐标缺失时 geohash 段为空。
- **不使用第三方 POI id 作主键**，身份完全第一方自有，保证多篇内容引用同一地点时稳定收敛为一条快照。

### 灌数源与归属

- 数据源是 content 域的已发布、公开帖子（`post.locationName` + `post.location`）。归属 `content-service`（发布写路径最自然）。
- 写时投影器（`placeindex.PlaceProjector`）在帖子生命周期事件上增量维护第一方地点快照存储（`place_snapshots` 派生读模型，按引用集去重）并同步 ES；冷启动/对账由 `placeindex.Backfill` 从全量帖子重建。
- 地点快照是派生读模型，posts 仍是唯一写真相源；删除最后一篇引用或绑定 canonicalEntity 后，对应快照与索引文档随之删除。

### 点击落地页归属（R-S05e-1，已定义 / WP-D 落地）

- `location.place` 命中后点击进入**临时地点卡** + 「提升为 `entity.homepage`」引导 CTA，符合上文单一真相源（未提升 = `location.place`、已提升 = `entity.homepage`）。
- route / surface 已 metadata-first 定义，禁止 UI 硬编码：
  - route：`_shared/app_routes.yaml` `locationPlaceLanding` → `/locations/{placeId}`（codegen 产出 `AppRoutePaths.locationPlaceLanding`）。
  - surface：`_shared/ui_surfaces.yaml` `locationPlaceLanding`（owner=`search`、`operation_ids: []`，落地页无独立后端 operation；命中详情来自搜索结果 payload 经 route extra 透传）。
  - 提升动作复用 `suggestHomepage` surface（不新造写路径）。
- 消费：`lib/ui/search/pages/location_place_landing_page.dart` + router wiring；`search_network_results_page` 交集「已连接地点」改走 `locationPlaceLanding`（不再误导 `entity.homepage` 详情）。
- 不阻塞召回主链路：当前 `location.place` 可被 canonical `search(request)` 检索召回；落地体验已定义并通过 widget 测试。

## 验收重点

1. searchable object 是否有统一注册表。
2. provider routing 是否基于 registry，而不是页面 if/switch。
3. `location.place` 是否与 `entity.homepage` 严格互斥（同一地点只出现一次），geo 维度是否只有一套机制。
