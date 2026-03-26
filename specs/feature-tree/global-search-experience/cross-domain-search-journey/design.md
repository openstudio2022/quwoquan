# cross-domain-search-journey 设计方案

## 设计动因

PRD 已经把全局搜索 Journey 冻结为六个正式 `L3_scenario`，但如果没有一条统一设计主轴，后续开发仍会发生三类漂移：

1. 壳层仍由原型 `GlobalSearchSheet` 主导，route / surface / request context 继续散落在 UI。
2. 搜索结果继续依赖“本地池子过滤 + 少量远程接口”的临时方案，无法形成统一结果模型。
3. 最近搜索、语音和问小趣 handoff 会各自独立实现，生命周期边界与 assistant 约束再次分叉。

本次 `/design` 的目标，是把全局搜索的完整 Journey 收口为：

- **全屏 route-driven 搜索页**
- **统一 `Search` 接口 + 内部 `SearchCoordinator` 编排多域搜索**
- **recent search local-first 双写**
- **问小趣 typed handoff，不触碰 runtime**

## 最新实现基线（2026-03-22）

本 Journey 后续实现统一以最新两段式 UX 为准：

- 首页先展示 `最近在搜` 双列历史卡片与历史管理态。
- 输入后同页切换为实时联想态，且只允许 `最常使用 / 联系人 / 聊天记录 / 搜索网络结果` 四段。
- 联系人与聊天记录点击后直接进入会话；“更多”只做页内展开。
- 点击“搜索网络结果”进入独立网络结果页；该页顶部保留搜索框，并用 `小趣搜 + 群组二级分类` 作为顶层 tab。
- `小趣搜` 在本 Journey 中是 assistant 结果 tab，不再是单独快捷入口 handoff。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `cross-domain-search-journey/spec.md` | 已冻结 Journey 范围、对象边界、SLO、生命周期、回滚口径 |
| `cross-domain-search-journey/acceptance.yaml` | `J1/J2/J3/R1` 已足以承接 plan slices |
| 6 个 Scenario spec / acceptance | 已明确最小实施单元与对象边界 |
| `global-search-experience/design.md` | 能力级已选定 route-driven + 统一 `Search` 接口 + 内部 typed contract |
| `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` | 问小趣 handoff 必须经 typed contract，不经 runtime 特判 |
| `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md` | 助手侧本次只允许改 UI / application / cloud client，不允许新增字符串路由 |

结论：

- `/design` 准入满足。
- 本 Journey 的设计顺序固定为：`_shared metadata -> 统一 Search contract -> 域级 Search* provider contract -> codegen -> shell/coordinator -> history/voice/handoff -> tests`。
- G1 已实际执行：
  - `make -C quwoquan_service verify-metadata`
  - `make codegen`
  - `make codegen-app`

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|---|---|---|
| 微信搜索首页 | 四段式 landing、全屏壳层、结果页统一结构 | 不拆分为独立 AI 搜索产品 |
| 微信聊天/联系人结果 | 强对象分组、列表优先级、快速进入详情 | 不继续使用“联系人”作为领域命名 |
| 微信内容搜索结果 | 内容结果 + 分类/频道联动 | 不把频道提升为新业务对象 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|---|---|
| `content-display-journey-consistency/design.md` | route handoff + shared state + absorb 补强思想 |
| `persona-follow-graph/design.md` | typed envelope、metadata-first、G1 校验写法 |
| 现有 `GlobalSearchSheet` | 可复用视觉结构与入口位置，但不复用其状态模型与调用方式 |
| chat / assistant 现有实现 | 语音权限处理、assistant run cloud client 与导航可复用 |

## 方案对比

### 方案 A：imperative 搜索 sheet + 局部数据过滤增强

核心思路：

- 保留 `GlobalSearchSheet.show()`。
- 每个域继续在 App 内自行管理数据池与过滤。
- 最近搜索、语音、问小趣入口各自挂接在页面状态中。

优点：

- 改动最小。
- 短期可快速做出视觉效果。

缺点：

- 不能形成 route / surface / request context 真相源。
- 跨域搜索无法 typed 化。
- 后续 dev 只能继续堆页面状态和兼容逻辑。

### 方案 B：统一后端聚合 `SearchAll` + App 只消费综合接口

核心思路：

- 新增一个后端统一聚合搜索接口。
- App 只负责壳层与展示。

优点：

- 客户端逻辑简单。
- 排序、降级和观测集中。

缺点：

- 当前四个域 search contract 尚未补齐，直接上聚合会放大服务端改造面。
- 会让本次 Journey 依赖额外 orchestration，不利于一把上线。

### 方案 C：route-driven 壳层 + 统一 `Search` 接口 + 内部 typed 搜索接口

核心思路：

- `GlobalSearchPage` 作为统一全屏壳层。
- 页面与业务层只调用统一 `SearchRepository.search(SearchRequest)`。
- 统一接口内部由 `SearchCoordinator` 调用域 Repository。
- 每个域补齐自己的内部 `Search*` contract 与 DTO。
- assistant 仅做 typed handoff，不混排 AI 结果。

优点：

- 与现有仓库结构和 metadata-first 约束最一致。
- 壳层、统一搜索接口、结果模型、历史、助手 handoff 可以一次性统一。
- 保留未来下沉到聚合接口的空间。

缺点：

- 统一接口背后仍要承担并发编排和局部降级。
- 需要同步补四个域的 search contract。

## 选型决策

**选定方案：方案 C**

决策理由：

1. 它能够在当前仓库现实下完成可实施的一把上线。
2. 它让产品和 App 层真正只面对一个统一搜索接口。
3. 它不会让全局搜索被某一个域或某一个后端聚合实现绑死。
4. 它满足助手设计约束：问小趣 handoff 通过 typed contract 完成，不进入 runtime 特判。

## 关键设计决策

### KD1：搜索页采用 route-driven 全屏页面，而不是 imperative sheet

- `_shared/app_routes.yaml` 增加 `globalSearch`。
- `app_router.dart` 统一跳转到 `GlobalSearchPage`。
- `GlobalSearchPage` 内部用 `AppFullscreenModalSurface` 呈现视觉，保持“全屏搜索面板”产品语义。
- `GlobalTopActions` 退化为“搜索入口触发器”，不再持有搜索状态。

### KD2：App 对外只暴露统一 `Search` 接口

对页面和业务层：

- `SearchRequest`
- `SearchResponse`
- `SearchLaunchContext`
- `SearchQueryState`
- `SearchRepository`

内部实现：

- `SearchCoordinator`
- `SearchSessionState`
- `SearchSection`
- `SearchResultItem`

职责：

- 统一入口和统一返回
- debounce 与取消前一轮请求
- 并发 fan-out
- 结果映射、分组与优先级
- 局部降级
- 结果页状态和 landing 页状态统一

### KD3：Journey 冻结统一搜索接口与内部 provider contract

本次正式搜索 contract 矩阵：

| 域 | Contract | 说明 |
|---|---|---|
| `content/post` | `SearchPosts` | 返回内容搜索项 |
| `user/user_profile` | `SearchSocialRelations` | 返回公开身份 + 关系态搜索项 |
| `messages/conversation` | `SearchConversations`、`SearchMessages` | 会话命中与消息命中分开 |
| `social/circle` | `SearchCircles` | 返回群组项 + facet buckets |

现有 `SearchContacts`：

- 可保留为 chat 域已有 contract
- 不再作为产品治理入口
- 若 dev 期间需要兼容，仅作为实现过渡，而不是设计真相源

### KD4：结果分组与对象边界固定

Journey 级结果分组冻结为：

- `content`
- `social_relation`
- `messages`
- `group_hubs`
- `group_facets`

规则：

- `group_facets` 只作为 `group_hubs` 的补强分组或筛选来源
- 不新增 `channel` 主域
- 不新增 `assistant` 结果分组

### KD5：recent search 采用 local-first + cloud sync 双写

本地：

- 首页即时展示
- 离线可读
- 写入低延迟

云端：

- 跨设备恢复
- 用户手动清理的一致性

同步策略：

- 普通 query 进入 recent search
- 问小趣 query 不进入 recent search
- local 失败不影响搜索主链路
- cloud 失败时保留本地成功

### KD6：语音只做 query 输入，不做 assistant 理解

- 新增 `SearchVoiceAsrAdapter` 包装系统 ASR。
- 成功后回填搜索框并立即进入普通搜索状态。
- 权限失败 / ASR 失败时回到手动输入。
- 不复用 chat voice send 的上传/发送链路。

### KD7：问小趣只做 typed handoff

助手侧符合性说明：

- 影响层：`UI + application + cloud client`
- 不影响：`runtime / skill / tool / prompt`
- 真相源：
  - `assistant/assistant_run/service.yaml`
  - `assistant/assistant_run/fields.yaml`
  - `assistant` generated contracts

设计要求：

- handoff 使用现有 `CreateRun / CreateRunStream`
- 通过 `triggerType` 与 source context 区分来源
- 不通过 label 文案或 `contains()` 识别 handoff 行为
- 不新增 runtime compatibility 逻辑；若必须有云端兼容，限定在 cloud client 参数适配层，并在 dev 后清理

### KD8：metadata / codegen 方案

| 目录 | 设计动作 | 产物 |
|---|---|---|
| `_shared/app_routes.yaml` | 新增 `globalSearch` | `app_route_paths.g.dart` |
| `_shared/ui_surfaces.yaml` | 新增 `globalSearchLanding`、`globalSearchResults` | `app_ui_surfaces.g.dart` |
| `_shared/request_context.yaml` | 新增 landing/result page ids 与内部 provider `Search*` page ids | `*_request_page_ids.g.dart` |
| `content/post/fields.yaml + service.yaml` | 新增 `PostSearchItemView`、`SearchPosts` | content generated DTO/API metadata |
| `user/user_profile/fields.yaml + service.yaml` | 新增 `SocialRelationSearchItemView`、history sync contracts | user generated DTO/API metadata |
| `messages/conversation/fields.yaml + service.yaml` | 新增 `ConversationSearchItemView`、`MessageSearchItemView`、两类搜索操作 | chat generated DTO/API metadata |
| `social/circle/fields.yaml + service.yaml` | 新增 `CircleSearchItemView`、`CircleFacetBucketView`、`SearchCircles`，前台统一映射为群组结果 | circle generated DTO/API metadata |
| `assistant/assistant_run/*` | 增加 handoff trigger / context | assistant generated contracts |

### KD9：发布策略按整版上线，观测与回滚前置

- 不设计用户可见 feature flag。
- 保留整版发布回滚。
- 通过 query latency、section degrade、history sync fail、ASR fail、xiaoqu handoff success 等指标做验收前 guardrail。

## metadata / codegen 方案

本次设计不是“代码优先”，而是以下顺序：

1. `_shared` 搜索 route / surface / request context
2. 四域内部 `Search*` operation 与搜索 DTO
3. 统一 `SearchRequest / SearchResponse` app contract
4. recent search sync contract
5. assistant handoff contract
6. 运行 G1：
   - `make -C quwoquan_service verify-metadata`
   - `make codegen`
   - `make codegen-app`
7. 再进入 App Repository / SearchCoordinator / UI

G1 基线已在本轮 `/design` 实际执行并通过。

## 字段演进、迁移/回填、必要时双读双写方案

### 字段演进

- `GlobalSearchScope` -> `SearchScope`
- `query + scope` 的轻量历史结构 -> `RecentSearchEntry`
- chat-only contact result -> user-based `SocialRelationSearchItemView`

### 迁移 / 回填

- 旧 `GlobalSearchSheet` 的入口统一迁到 `GlobalSearchPage`
- 现有本地 recent search 若存在，迁移到新 local schema
- 不保留历史特性树节点，不做治理层兼容

### 双读 / 双写

- recent search：local + cloud 双写
- search result：不做持久化双写
- `SearchContacts`：允许作为实现过渡输入，但不进入设计真相源
- 页面和业务层只依赖统一 `Search` 接口

## feature flag、观测、SLO 验证与回滚方案

### feature flag

- 本 Journey 不新增业务 feature flag。
- 发布控制依赖整版回滚。

### 观测

- `global_search_query_latency_ms`
- `global_search_section_timeout_count`
- `global_search_history_sync_failure_count`
- `global_search_asr_failure_count`
- `global_search_xiaoqu_handoff_success_count`

### SLO 验证

- landing 首屏即时展示
- 首批结果 `P95 < 1.5s`
- 单域故障不阻塞全页
- 语音失败不阻塞文本搜索

### 回滚

1. 整版发布回滚。
2. 若只出现 assistant handoff 问题，也不引入新兼容路径，而是整体回退到旧搜索实现。
3. recent search 本地数据保持可读，不对用户已有历史做破坏性清理。

## TDD / ATDD 策略

| 验收 | 测试层 | 设计策略 |
|---|---|---|
| `J1` | `T1/T2/T4` | route/surface/request context、全屏壳层与统一入口 |
| `J2` | `T1/T2/T3/T4` | 统一 `Search` 接口、内部 Search* contract、结果分组、局部降级 |
| `J3` | `T1/T2/T3/T4` | recent search sync、语音转词、问小趣 handoff |
| `R1` | `T3/T4` | 观测、SLO、回滚演练 |

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|---|---|---|---|
| `P1` | 冻结 `_shared`、统一 `Search` 接口与四域 provider metadata | `J1/J2` | `T1_schema` |
| `P2` | 建立 codegen baseline | `J1/J2/J3` | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地全屏壳层与统一入口 | `J1` | `T2_module_interaction`, `T4_user_journey` |
| `P4` | 落地统一 `Search` 接口与结果分组 | `J2` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P5` | 落地 recent search / voice / xiaoqu handoff | `J3` | `T2_module_interaction`, `T3_cross_service_integration`, `T4_user_journey` |
| `P6` | 验证观测、SLO 与整体回滚 | `R1` | `T3_cross_service_integration`, `T4_release_rehearsal` |

## 未来演进

- 后续可把统一 `Search` 接口的底层实现下沉为 `SearchAll`，但不改变 UI / result model contract。
- 若 query 量级提高，可引入更强排序或混排，但不改变“问小趣不混排”的 Journey 规则。
- 若 recent search 生命周期后续统一治理，可把自动过期时间纳入 user 域配置。
