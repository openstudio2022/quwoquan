# L3 Story：搜索对象分类体系与 ProviderREGISTRY (`search-object-taxonomy-and-provider-registry`)

> 所属能力：[`search-provider-routing-and-storage-topology`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望联系人、内容、圈子、主页与地点使用统一对象分类和 Provider 注册返回强类型结果，从而在不同入口获得可理解、可路由且权限安全的搜索结果。

## 2. 范围与非目标

### In Scope

- searchable object 统一命名与 provider 注册。
- location.place 作为复用 geo 维度的第一方对象 target 的 taxonomy 注册与检索路由。
- location.place 与 entity.homepage 的单一真相源边界（互斥、不重复）。
- 第一方地点快照存储的身份/去重与灌数源。
- `location.place` 命中的临时落地卡与“提升为实体主页” CTA；复用搜索 payload，不新建后端 operation。

### Out of Scope

- 排序策略与存储弹性拓扑（归 search-storage-topology-and-elasticity）。
- 完整地点 detail 页与独立后端 detail/写 operation（落地层仅复用搜索结果 payload + suggestHomepage 既有 surface）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 location 作为第一方对象 target 注册进统一 taxonomy 与 retrieve 契约

- location 成为 canonical search 可召回的一类对象，且 geo 维度机制仅一套。

<a id="req-002"></a>
### REQ-002 第一方地点快照存储按地名去重、对绑定实体的地点单源排除

- 同一地点在统一索引中只出现一次（未提升=location.place，已提升=entity.homepage）。

<a id="req-003"></a>
### REQ-003 location.place 命中落地为临时地点卡并引导提升为 entity.homepage

- location.place 点击落地体验定义并验证；未提升=location.place、已提升=entity.homepage 单一真相源在落地层一致。
- 地点提升候选只能携带一个经过格式校验的 canonical `sourcePlaceId`；该值持久化为 Homepage 的内部精确 lookup alias，候选发布后随 `entity.homepage` 搜索投影的 `placeId` anchor 写入统一索引。任何普通用户提交的任意 alias 必须被拒绝。

<a id="req-004"></a>
### REQ-004 searchable object 的统一命名

- searchable object 的统一命名。
- objectType 必须是统一枚举或 metadata 注册项。
- 页面层不得自定义新的搜索对象字符串。
- taxonomy 必须覆盖 `web.document`，使 AI 能通过同一接口同时检索网页与站内对象。
- 它是被内容引用的「自由文本地点」聚合去重后的第一方快照对象，进入统一 `quwoquan_objects` 索引，与其它对象一起被 canonical `search(request)` 召回、排序、引用。
- 因此同一地点在统一索引中**只出现一次**：未提升 → `location.place`；已提升 → `entity.homepage`。geo 维度只有一套机制，二者互斥不重复。
- route / surface 已 metadata-first 定义，禁止 UI 硬编码：

## 4. 契约引用

- canonical：`contracts/metadata/_shared/search_objects.yaml`
- canonical：`contracts/metadata/_shared/search_contract.yaml`
- canonical：`contracts/metadata/_shared/app_routes.yaml`
- canonical：`contracts/metadata/_shared/ui_surfaces.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 location 作为第一方对象 target 注册进统一 taxonomy 与 retrieve 契约

- GIVEN search_objects.yaml 已登记 object_type=location.place 与 ai_target=location（object_type=location.place）。
- GIVEN runtime/search 已加性新增 ObjectTypeLocation 与 TargetLocation。
- WHEN 校验 metadata ai_targets 与 runtime AllTargets 一一对应，并把 location.place 文档解析为 target。
- THEN len(ai_targets)==len(AllTargets) 且 location→location.place 双向映射成立。
- THEN TargetForDocument(location.place)==location，ObjectTypesForTargets([location])==[location.place]。
- THEN 既有 geo 跨对象维度符号（GeoNear/Near/Document.Geo/nearMatch/hit geo|distanceKm|placeName）保持不变。

<a id="gwt-002"></a>
### GWT-002 第一方地点快照存储按地名去重、对绑定实体的地点单源排除

- GIVEN 多篇已发布公开帖子引用同一自由文本地名（无 canonicalEntityId/primaryHomepageId）。
- GIVEN 另有帖子的地点已绑定 canonicalEntityId。
- WHEN 写时投影器与 backfill 从帖子聚合 location.place 快照并投影到统一索引。
- THEN 同一规范化地名(+粗 geohash)收敛为一条 location.place 快照，popularity 反映引用计数。
- THEN 绑定 canonicalEntity 的帖子不产生 location.place；其曾引用的地点在失去最后一篇自由文本引用后被删除。
- THEN 帖子转私有/删除/解绑后，对应快照与 ES 文档被移除（无残留）。

<a id="gwt-003"></a>
### GWT-003 location.place 命中落地为临时地点卡并引导提升为 entity.homepage

- GIVEN search 结果页交集「已连接地点」承载 location.place 命中（未绑定 canonicalEntity）。
- GIVEN route locationPlaceLanding 与 surface locationPlaceLanding 已 metadata-first 定义并 codegen。
- WHEN 点击 location.place 命中，进入 /locations/{placeId} 落地页；点击「提升为实体主页」CTA。
- THEN 落地页渲染临时地点卡（地名 + 地址 + 临时徽标）；冷启动、深链与进程恢复按 canonical `/search(ids:[placeId])` 重读，无独立地点详情 operation。
- THEN CTA 跳转 suggestHomepage（复用既有 surface），携带地名 query 与 canonical `sourcePlaceId`，不新造写路径。
- THEN 候选发布后 `/search(ids:[sourcePlaceId])` 返回该 `entity.homepage`（其 `placeId` anchor），而不是遗留 `location.place`；原地点路由因此可重定向主页且不产生双结果。
- THEN 进入上报 location_place_landing.enter 曝光、CTA 上报 promote_click（JourneyEventTracker）。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
