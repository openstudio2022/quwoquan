# global-search-experience 设计方案

## 设计动因

`global-search-experience` 是一次能力归属重构，而不是一次普通页面改版。PRD 已经冻结三件事：

1. 全局搜索是独立 `L1_capability`，不再挂靠 `discovery-content`。
2. “社交关系”与“频道 facet” 的对象边界已经明确，不再复用历史 chat 搜索节点。
3. 问小趣只作为快捷 handoff，不参与综合搜索结果混排。

如果没有一版能力级设计，后续实现仍会回到三个旧问题：

- UI 继续以 `GlobalSearchSheet` 原型为中心扩张，路由、surface、request context 继续散落。
- 搜索结果继续依赖本地 mock 过滤，无法形成跨域 typed contract。
- assistant handoff 再次走回字符串路由或页面临时参数，违反现有助手约束。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `global-search-experience/spec.md` | 已冻结能力边界、领域服务、数据生命周期、NFR 与历史节点清理口径 |
| `global-search-experience/acceptance.yaml` | `C1/C2/C3` 足以承载能力级设计与后续 plan |
| `cross-domain-search-journey/spec.md` | 已冻结统一入口、综合结果、最近搜索、语音与问小趣的完整旅程 |
| 6 个 L3 Scenario spec / acceptance | 已冻结对象边界与最小实施单元 |
| `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` | 助手 handoff 必须沿 typed contract / metadata 走，不得进入 runtime 垂类特判 |
| `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` | 助手相关设计必须说明影响层、真相源映射、无字符串硬编码与无第二真相源 |
| 当前 metadata / app 现状 | 仅 `SearchContacts` 已存在；`app_routes / ui_surfaces / request_context` 尚无 C 端 global search 真相源 |

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

### 方案 C：新建独立 L1，采用 route-driven 全屏搜索页 + App `SearchCoordinator` + 域级 typed 搜索契约

核心思路：

- 新建独立 `global-search-experience` 能力与路由/surface 真相源。
- App 以 `SearchCoordinator` 并行 fan-out 到 `content / user / messages / circle` 四个域。
- 各域先补齐正式 `Search*` operation 与 DTO。
- 问小趣复用 `assistant_run` 既有 typed contract，只新增 handoff trigger，不做 AI 结果混排。

优点：

- 最符合 metadata-first 与现有仓库边界。
- UI、路由、结果模型、assistant handoff 都有稳定 typed contract。
- 未来若需要网关聚合，不需要改动搜索页和结果模型真相源。

缺点：

- 需要同时补 route/surface/request context 与多个域搜索 contract。
- 客户端需要承担一次并发编排与局部降级。

## 选型决策

**选定方案：方案 C**

决策理由：

1. 它把“能力归属”“壳层交互”“域级 contract”“助手 handoff”统一到一条 metadata-first 主线上。
2. 它能在不引入新聚合服务的前提下完成一把上线，且为后续网关聚合保留演进空间。
3. 它满足助手链路约束：本次只影响 `UI + application + cloud client`，不引入新的 `runtime / skill / tool / prompt` 逻辑。

## 架构总览

能力级拓扑采用以下文本架构：

1. root surfaces：`home / chat / circle / assistant`
2. search shell：`global search landing / result page`
3. app orchestration：`SearchCoordinator`、`SearchSessionState`、`RecentSearchSyncEngine`
4. domain repositories：
   - `ContentRepository.searchPosts`
   - `UserProfileRepository.searchSocialRelations`
   - `ChatRepository.searchConversations / searchMessages`
   - `CircleRepository.searchCircles`
5. assistant handoff：`AssistantRepository.createRun*`
6. local + cloud sync：recent search local store + user-scoped cloud sync

## 关键设计决策

### KD1：全局搜索壳层必须 route-driven，但视觉上仍是全屏搜索面板

- `_shared/app_routes.yaml` 新增 `globalSearch`。
- App 通过路由进入统一的 `GlobalSearchPage`。
- 页面内部继续使用全屏 modal surface 语义，保持 iOS UX 规则不变。
- 不再保留 `GlobalSearchSheet.show()` 作为结构真相源。

### KD2：能力级只引入域级 `Search*` contract，不在 v1 增加统一 `SearchAll`

本次正式冻结四类站内搜索 contract：

- `content/post`：`SearchPosts`
- `user/user_profile`：`SearchSocialRelations`
- `messages/conversation`：`SearchConversations`、`SearchMessages`
- `social/circle`：`SearchCircles`

`SearchCoordinator` 负责：

- query debounce
- 并发 fan-out
- 局部超时降级
- 结果分组与排序
- 空态/错误态收敛

### KD3：结果模型统一 typed 化

App 内部不再长期使用散乱 `Map<String, dynamic>` 承载综合结果，而是冻结：

- `SearchQuery`
- `SearchScope`
- `SearchSectionKind`
- `SearchResultItem`
- `SearchSection`
- `SearchSessionState`

各域 Repository 只负责返回 typed DTO，跨域组合由 `SearchCoordinator` 完成。

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
| `_shared/request_context.yaml` | 新增 global search page ids 与 domain `Search*` request page ids | `*_request_page_ids.g.dart` |
| `content/post/service.yaml` | 新增 `SearchPosts` | content API metadata / DTO |
| `user/user_profile/service.yaml` | 新增 `SearchSocialRelations`、history sync contracts | user API metadata / DTO |
| `messages/conversation/service.yaml` | 新增 `SearchConversations`、`SearchMessages` | chat API metadata / DTO |
| `social/circle/service.yaml` | 新增 `SearchCircles` + facet 返回 | circle API metadata / DTO |
| `assistant/assistant_run/*` | 新增 handoff trigger 枚举或上下文字段 | assistant generated contracts |

### KD7：不设计细粒度灰度，保留整版回滚与观测

用户已经明确本次不走兼容双轨与灰度发布，因此设计上：

- 不新增业务 feature flag
- 不做双轨入口并存
- 保留整版回滚口径
- 强化观测与超时降级

## metadata / codegen 方案

G1 基线已实际执行并通过：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

本次 `/design` 冻结的 search 增量仍需按以下顺序实施：

1. `_shared` 路由/surface/request context
2. 四个域的 `Search*` operation 与 DTO
3. recent search 云同步 contract
4. assistant handoff trigger contract
5. codegen 产物刷新
6. App Repository / coordinator / UI 消费生成物

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
- `SearchContacts` 作为已有 chat contract 保留，但不再作为“社交关系”产品真相源

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

### SLO 验证

- landing 打开即时完成
- query 后首批结果分组 `P95 < 1.5s`
- 单域失败不阻塞整页
- 问小趣 handoff `P95 < 800ms` 完成页面接续

### 回滚

1. 回退整版发布，恢复旧搜索实现。
2. 保持新 metadata 文档与 codegen 产物，不在运行时做二次兼容。
3. recent search local schema 允许向后兼容读取，不回滚用户本地数据。

## TDD / ATDD 策略

- `T1_schema`
  - route/surface/request context
  - 四域 `Search*` contract
  - recent search DTO / assistant handoff contract
- `T2_module_interaction`
  - 搜索页壳层、分组 UI、ASR、问小趣入口
- `T3_cross_service_integration`
  - 多域 fan-out、局部降级、history sync、assistant handoff
- `T4_user_journey`
  - 首页/聊天/圈子/助手入口主旅程
  - 语音转词与问小趣接续

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|---|---|---|---|
| `P1` | 冻结 capability 级 metadata 与 contract 拓扑 | `C1/C2` | `T1_schema` |
| `P2` | 建立 Journey / Scenario 设计基线与 codegen baseline | `C1/C2/C3` | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 建立发布观测、SLO 与整体回滚口径 | `C2/C3` | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 若后续搜索量和时延压力上升，可在不改 UI contract 的前提下引入网关聚合 `SearchAll`。
- 若 assistant 需要更强的搜索接续，可在 typed handoff 上增加上下文枚举，但仍不得在 runtime 做字符串路由。
- 若 recent search 未来需要统一生命周期治理，再把自动过期时间纳入 user 域配置真相源。
