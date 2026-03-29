# global-search-experience 设计方案

## 设计动因

`global-search-experience` 是一次能力归属重构，而不是一次普通页面改版。PRD 已经冻结三件事：

1. 全局搜索是独立 `L1_capability`，不再挂靠 `discovery-content`。
2. “本地聊天搜索 / 群组 facet / 网络结果” 的对象边界必须明确，不再复用历史 chat 搜索节点。
3. 问小趣只作为快捷 handoff，不参与综合搜索结果混排。

如果没有一版能力级设计，后续实现仍会回到三个旧问题：

- UI 继续以 `GlobalSearchSheet` 原型为中心扩张，路由、surface、request context 继续散落。
- 搜索结果继续依赖本地 mock 过滤，无法形成跨域 typed contract。
- assistant handoff 再次走回字符串路由或页面临时参数，违反现有助手约束。

## 最新实现基线（2026-03-22）

以下设计口径以用户最新确认的 `latest_two_stage_ux` 为准；若下文仍出现“综合结果 / 问小趣快捷入口 / 指定搜索内容”等历史表述，均以上述新基线覆盖：

- 搜索体验是两段式：`初始历史态 -> 输入后实时联想态 -> 独立网络结果页`。
- 实时联想态严格按 `最常使用 / 联系人 / 聊天记录 / 搜索网络结果` 四段组织。
- 联系人和聊天记录默认 3 条，可在当前页内联展开更多，并直接进入对应会话。
- `小趣搜` 不再是首页快捷 handoff，而是独立网络结果页最左侧的 assistant 结果 tab。
- 群组能力在搜索中只表现为网络结果页顶部的群组二级分类 tab。

## 2026-03-27 增量基线扩展

本轮 baseline 在上述体验基线之上，额外冻结两层新增设计：

1. `global-search-experience` 下新增治理型 `L2`：`search-provider-routing-and-storage-topology`，用于收口统一 `search(request)` contract、对象 taxonomy、执行策略与云侧搜索读模型拓扑。
2. `cross-domain-search-journey` 内的“人”结果契约不再以旧社交关系搜索挂载为主，而改为 `local-chat-search-contract`：`chat.contact / chat.conversation / chat.message` 统一走端侧本地搜索。
3. `circle.group` 固定为 `hybrid_remote_fallback_local`：云侧优先，失败或 0 结果时回退端侧本地全量结果。
4. 云侧搜索不再以“直接扫描业务主集合”为设计基线，而改为“写模型按域，搜索读路径走 projection / read model，读写分离，多读切片可独立弹性”。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `global-search-experience/spec.md` | 已冻结能力边界、领域服务、数据生命周期、NFR 与历史节点清理口径 |
| `global-search-experience/acceptance.yaml` | `C1/C2/C3` 为旧基线；本轮需补充统一搜索 contract、执行策略与存储拓扑验收 |
| `cross-domain-search-journey/spec.md` | 已冻结统一入口、综合结果、最近搜索、语音与问小趣的完整旅程 |
| Journey 与 topology 两条 L2 及其 L3 docs | 本轮 baseline 需一起冻结，避免体验与架构分裂 |
| `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` | 助手 handoff 必须沿 typed contract / metadata 走，不得进入 runtime 垂类特判 |
| `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` | 助手相关设计必须说明影响层、真相源映射、无字符串硬编码与无第二真相源 |
| 当前 metadata / app 现状 | 现有搜索以旅程型统一接口为主，但尚未冻结本地聊天搜索、`circle.group` fallback 与云侧搜索拓扑 |

结论：

- `/design` 准入满足。
- 设计必须以 `metadata -> codegen -> 业务逻辑 -> 测试` 为唯一切片顺序。
- 本次涉及 metadata/codegen，已实际执行：
  - `make -C quwoquan_service verify-metadata`
  - `make codegen`
  - `make codegen-app`
- G1 校验已通过，说明当前仓库基线健康，可继续在此之上设计搜索增量。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|---|---|---|
| 微信搜索首页 | 全屏壳层、四段式 landing、指定搜索内容、最近搜索 | 不照搬其“搜一搜/问一问”独立产品分域 |
| 微信聊天/联系人结果 | 分组结果结构、结果卡样式、从搜索直达详情的心智 | 不沿用“联系人”作为领域命名 |
| 微信内容结果 | 内容结果与频道/分类并置 | 不把频道升级为独立业务对象 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|---|---|
| `content-display-journey-consistency/design.md` | route handoff + shared provider + result absorb 作为补强、而非唯一真相源 |
| `persona-follow-graph/design.md` | metadata-first、typed contract、跨域上下文 envelope、能力级切片方法 |
| `GlobalSearchSheet` 现状实现 | 可复用视觉原型与现有入口位置，但不再作为结构真相源 |
| `assistant_run` 既有 contract | `CreateRun / CreateRunStream` 与 `triggerType` 可承接问小趣 handoff |

## 方案对比

### 方案 A：继续沿用原型壳层，App 内做本地过滤增强

核心思路：

- 保留 `GlobalSearchSheet.show()` 作为入口。
- 继续用页面内本地数据池或 mock 数据过滤。
- 只在 UI 层补视觉和结果样式。

优点：

- 前期改动最少。
- 不需要新增 metadata 路由与服务契约。

缺点：

- 无法形成全局搜索的正式能力边界。
- 结果仍停留在本地过滤，不满足 metadata-first。
- 问小趣、社交关系、频道 facet 继续各走各路。

### 方案 B：新增网关聚合 `SearchAll`，App 只消费单一综合接口

核心思路：

- 新建统一聚合搜索接口。
- App 只请求一个 `SearchAll`，服务端负责 fan-out、混排、降级。

优点：

- 客户端逻辑最简单。
- 统一排序与观测更集中。

缺点：

- 当前各域 search operation 尚未补齐，直接上聚合接口会放大服务端改造面。
- 会让 capability 设计过早绑定单一后端聚合形态。
- 与“频道是 circle facet、问小趣不混排”的局部 UI 规则耦合更深。

### 方案 C：新建独立 L1，采用 route-driven 全屏搜索页 + 统一 `Search` 接口 + 内部 typed 编排

核心思路：

- 新建独立 `global-search-experience` 能力与路由/surface 真相源。
- App 对页面与业务层只暴露一个统一 `SearchRepository.search(SearchRequest)` 接口。
- 统一接口内部由 `SearchPlanner + SearchCoordinator` 编排 `local_only / remote_only / hybrid_remote_fallback_local` 三类 provider。
- 问小趣复用 `assistant_run` 既有 typed contract，只新增 handoff trigger，不做 AI 结果混排。

优点：

- 最符合 metadata-first 与现有仓库边界。
- 产品层和 App 层都只有一个统一搜索接口，不再暴露分域搜索心智。
- 未来若需要网关聚合，不需要改动搜索页和结果模型真相源。

缺点：

- 需要同时补 route/surface/request context 与多个域搜索 contract。
- 统一接口背后仍需承担一次并发编排与局部降级。

## 选型决策

**选定方案：方案 C**

决策理由：

1. 它把“能力归属”“壳层交互”“统一搜索接口”“助手 handoff”统一到一条 metadata-first 主线上。
2. 它让用户层、页面层和 app 层都只面对一个搜索入口，而不是一组拆散的域搜索接口。
3. 它满足助手链路约束：本次只影响 `UI + application + cloud client`，不引入新的 `runtime / skill / tool / prompt` 逻辑。

## 架构总览

能力级拓扑采用以下文本架构：

1. root surfaces：`home / chat / circle / assistant`
2. search shell：`global search landing / result page`
3. app orchestration：`UnifiedSearchFacade`、`SearchPlanner`、`SearchCoordinator`、`SearchSessionState`、`RecentSearchSyncEngine`
4. local providers：
   - `chat.contact`
   - `chat.conversation`
   - `chat.message`
5. hybrid provider：
   - `circle.group`（remote primary + local fallback）
6. remote providers：
   - `content.post`
   - `circle.circle`
   - `entity.homepage`
   - `integration.location_poi`
7. assistant handoff：`AssistantRepository.createRun*`
8. local + cloud sync：recent search local store + user-scoped cloud sync
9. cloud search storage：write model by domain + search read model / projection + read/write separation + multi-reader elasticity

## 关键设计决策

### KD1：全局搜索壳层必须 route-driven，但视觉上仍是全屏搜索面板

- `_shared/app_routes.yaml` 新增 `globalSearch`。
- App 通过路由进入统一的 `GlobalSearchPage`。
- 页面内部继续使用全屏 modal surface 语义，保持 iOS UX 规则不变。
- 不再保留 `GlobalSearchSheet.show()` 作为结构真相源。

### KD2：能力级对外只暴露统一 `Search` 接口

本次冻结两层 contract：

对页面和业务层：

- `SearchRequest`
- `SearchResponse`
- `SearchSection`
- `SearchResultItem`
- `SearchObjectType`
- `SearchExecutionStrategy`

对内部 provider：

- `chat.contact / chat.conversation / chat.message`：local provider
- `circle.group`：hybrid provider
- `content.post / circle.circle / entity.homepage / integration.location_poi`：remote provider

`SearchCoordinator` 只作为统一接口背后的实现细节，负责：

- query debounce
- stale request cancel
- 并发 fan-out
- 局部超时降级
- 结果分组与排序
- 空态/错误态收敛

### KD3：群组结果在统一搜索里仍由 circle 域提供

结果模型不再长期使用散乱 `Map<String, dynamic>`，而是冻结：

- `SearchQuery`
- `SearchScope`
- `SearchSectionKind`
- `SearchResultItem`
- `SearchSection`
- `SearchSessionState`

其中：

- 用户词统一为 `群组`
- circle 域继续提供群组结果与 facet 真相源
- 跨域组合由统一搜索接口内部完成

### KD4：最近搜索是 local-first 的双写模型

- 本地存储用于即时显示和离线回显。
- 云端同步用于跨设备恢复。
- 同步对象只包含普通搜索 query。
- 问小趣 query 不进入该模型。

### KD5：问小趣 handoff 只影响 UI / application / cloud client

影响层冻结为：

- `UI`: 搜索页入口与跳转
- `application`: handoff context 组装
- `cloud client`: 调用 `CreateRun / CreateRunStream`

不影响：

- `runtime`
- `skill`
- `tool`
- `prompt`

落实方式：

- 使用 `triggerType = global_search_handoff` 之类的 typed 枚举扩展
- 不以“问小趣”文案做行为路由
- 不新增 runtime if/switch

### KD6：能力级 metadata / codegen 变更矩阵

| 目录 | 设计目标 | 主要产物 |
|---|---|---|
| `_shared/app_routes.yaml` | 新增 `globalSearch` route | `app_route_paths.g.dart` |
| `_shared/ui_surfaces.yaml` | 新增 search landing / result surfaces | `app_ui_surfaces.g.dart` |
| `_shared/request_context.yaml` | 新增 global search page ids 与内部 provider `Search*` request page ids | `*_request_page_ids.g.dart` |
| `_shared/search/search_contract.yaml` | 冻结 `SearchRequest / SearchResponse / SearchObjectType / SearchExecutionStrategy` | 端云统一搜索 contract codegen |
| `_shared/search/search_objects.yaml` | 冻结 searchable object taxonomy、provider registry、execution mode | 端云 object registry codegen |
| `content/post/service.yaml` | 新增 `SearchPosts` | content API metadata / DTO |
| `messages/conversation/service.yaml` | 仅保留同步与会话读取主契约；不再把聊天搜索 operation 作为产品主入口 | chat API metadata / DTO |
| `social/circle/service.yaml` | 新增 / 对齐 `SearchCircles`、`SearchCircleGroups` 与 group fallback 所需 contract | circle API metadata / DTO |
| `entity/homepage/service.yaml` | 对齐共享主页搜索对象 | entity API metadata / DTO |
| `integration/location/service.yaml` | 对齐位置搜索对象 | integration API metadata / DTO |
| `assistant/assistant_run/*` | 新增 handoff trigger 枚举或上下文字段 | assistant generated contracts |

### KD7：不设计细粒度灰度，保留整版回滚与观测

用户已经明确本次不走兼容双轨与灰度发布，因此设计上：

- 不新增业务 feature flag
- 不做双轨入口并存
- 保留整版回滚口径
- 强化观测与超时降级

### KD8：新增治理型 L2，体验旅程与搜索架构分别挂载

- `cross-domain-search-journey` 只负责用户旅程、页面组织、跳转与体验验收。
- `search-provider-routing-and-storage-topology` 负责统一 contract、对象 taxonomy、provider routing、fallback 与云侧存储拓扑。
- 页面内搜索、全局搜索和 picker 搜索统一消费同一个 canonical `search(request)`，但是否本地执行由 provider registry 决定。

### KD9：聊天搜索冻结为端侧本地搜索

- `chat.contact`、`chat.conversation`、`chat.message` 统一走端侧本地索引。
- 登出不清空本地索引，但必须按 owner / sub account 分区隔离。
- 切换子账号不得读到其他子账号分区。
- 消息撤回、删除与用户显式清理时，必须同步删除本地索引项。
- 云端 `messages` 的 14 天 TTL 与端侧长期保留可不一致；本期端侧生命周期以“用户主动删除”为主。

### KD10：`circle.group` 固定为 remote primary + local fallback

- `circle.group` 首先查询云侧。
- 云侧失败、超时、熔断或返回 0 结果时，回退端侧本地全量结果。
- fallback 结果必须返回 `resolvedFrom=local_fallback` 一类 typed 降级标记，以支撑 UI 和观测。
- 本期不做 remote + local 融合重排，只做云优先 / 本地兜底，控制复杂度和成本。

### KD11：云侧搜索读路径必须与业务写路径分离

- 写模型继续按域落在现有 Mongo / PostgreSQL 主存储。
- 搜索读请求统一落到 search read model / projection，不把“扫描业务主集合”作为长期方案。
- 读侧按 objectType 拆分，支持多读切片与独立副本数。
- `suggest` 模式默认 lexical-only，并优先缓存 / 热点建议，避免在最高 QPS 路径默认启用 semantic/vector。
- 未来若需要统一高性能搜索读库，可替换 read model 的底层实现，但不改变 canonical `search(request)` contract。

## metadata / codegen 方案

G1 基线已实际执行并通过：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

本次 `/design` 冻结的 search 增量仍需按以下顺序实施：

1. `_shared` 路由/surface/request context
2. 四个域的内部 `Search*` operation 与 DTO
3. 统一 `SearchRequest / SearchResponse` app contract
4. recent search 云同步 contract
5. assistant handoff trigger contract
6. codegen 产物刷新
7. App Repository / coordinator / UI 消费生成物

## 字段演进、迁移/回填、必要时双读双写

### 字段演进

- `GlobalSearchScope` 原型枚举 -> 正式 `SearchScope`
- 原型分组标题 -> `SearchSectionKind`
- recent search 本地散乱模型 -> `RecentSearchEntry`

### 迁移 / 回填

- 旧 `GlobalSearchSheet` 入口迁到 route-driven `GlobalSearchPage`
- 旧 chat 搜索节点已从特性树中删除，不再做治理迁移
- recent search 若已有本地缓存，升级到新 schema 时做一次无损迁移

### 双读 / 双写

- recent search 采用 local + cloud 双写
- 查询结果不做长期双写，仅当前会话读模型
- 聊天搜索结果仅存在于本地索引 / 本地 snapshot，不新增云侧搜索结果双写
- `SearchContacts`、`SearchConversations`、`SearchMessages` 若短期保留，仅允许作为实现过渡，不再作为产品主 contract
- 页面与业务层不直接依赖分域 `Search*` 接口

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 本次不新增业务 feature flag。
- 发布控制依赖整版上线与整版回滚。

### 观测

核心指标：

- `global_search_open_count`
- `global_search_query_latency_ms`
- `global_search_section_degrade_count`
- `global_search_result_click_count`
- `global_search_history_sync_failure_count`
- `global_search_asr_failure_count`
- `global_search_xiaoqu_handoff_count`
- `global_search_local_index_hit_count`
- `global_search_circle_group_local_fallback_count`
- `global_search_remote_reader_latency_ms`
- `global_search_reader_cache_hit_rate`

### SLO 验证

- landing 打开即时完成
- query 后首批结果分组 `P95 < 1.5s`
- 单域失败不阻塞整页
- 问小趣 handoff `P95 < 800ms` 完成页面接续
- `suggest` 默认 lexical-only，semantic 不进入最高 QPS 路径
- 云侧读侧查询不得长期依赖扫描业务主集合

### 回滚

1. 回退整版发布，恢复旧搜索实现。
2. 保持新 metadata 文档与 codegen 产物，不在运行时做二次兼容。
3. recent search local schema 允许向后兼容读取，不回滚用户本地数据。

## TDD / ATDD 策略

- `T1_schema`
  - route/surface/request context
  - 统一 `SearchRequest / SearchResponse`
  - 内部四域 `Search*` contract
  - recent search DTO / assistant handoff contract
- `T2_module_interaction`
  - 搜索页壳层、分组 UI、ASR、问小趣入口
- `T3_cross_service_integration`
  - 统一搜索接口背后的多域 fan-out、局部降级、history sync、assistant handoff
- `T4_user_journey`
  - 首页/聊天/群组/助手入口主旅程
  - 语音转词与问小趣接续

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|---|---|---|---|
| `P1` | 冻结 capability 级 metadata、统一搜索接口与内部 provider 拓扑 | `C1/C2` | `T1_schema` |
| `P2` | 建立 Journey / Scenario 设计基线与 codegen baseline | `C1/C2/C3` | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 建立发布观测、SLO 与整体回滚口径 | `C2/C3` | `T2_module_interaction`, `T4_user_journey` |
| `P4` | 冻结治理型 L2：canonical contract、对象 taxonomy、执行策略与 fallback | `C2/C4` | `T1_schema`, `T3_cross_service_integration` |
| `P5` | 冻结本地聊天搜索生命周期与账号隔离规则 | `C3/C4` | `T2_module_interaction`, `T4_user_journey` |
| `P6` | 冻结云侧搜索读模型、读写分离与多读切片弹性方案 | `C4` | `T3_cross_service_integration`, `T4_release_rehearsal` |

## 未来演进

- 若后续搜索量和时延压力上升，可在不改统一 `Search` 接口的前提下引入网关聚合 `SearchAll`。
- 若 assistant 需要更强的搜索接续，可在 typed handoff 上增加上下文枚举，但仍不得在 runtime 做字符串路由。
- 若 recent search 未来需要统一生命周期治理，再把自动过期时间纳入 user 域配置真相源。
