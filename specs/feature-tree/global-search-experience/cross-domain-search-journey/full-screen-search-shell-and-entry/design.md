# full-screen-search-shell-and-entry 设计方案

## 设计动因

全局搜索首先是一个入口与壳层问题。只要壳层仍由 `GlobalSearchSheet.show()` 这类 imperative 原型主导，后续结果模型、请求上下文和多入口统一都会继续散落在 UI。

## 最新实现基线（2026-03-22）

该 Scenario 以最新两段式壳层为准：

- 初始态展示搜索框、`最近在搜` 双列卡片、展开与垃圾桶进入记录管理态。
- 输入后切换到联想态，严格按 `最常使用 / 联系人 / 聊天记录 / 搜索网络结果` 四段排布。
- “更多联系人 / 更多聊天记录”只允许页内展开，不新开中间页。
- `小趣搜` 不在本页以快捷入口出现，而在独立网络结果页中承接。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `full-screen-search-shell-and-entry/spec.md` | 已冻结统一入口、全屏壳层、四段式 landing 与 route/surface 真相源要求 |
| `full-screen-search-shell-and-entry/acceptance.yaml` | `A1/S1` 足以承接实施切片 |
| `cross-domain-search-journey/design.md` | Journey 已选定 route-driven 搜索页 |
| iOS UX 规则 | 全局搜索必须是唯一允许的全屏全局浮层 |

## 对标输入分析

- 微信搜索首页的核心不是组件堆叠，而是“入口统一 + 首页四段式 + 返回稳定”。
- 我们需要吸收其结构心智，但不能继续用页面内临时 sheet 承载。

## 方案对比

### 方案 A：继续使用 imperative `GlobalSearchSheet.show()`

优点：

- 代码改动小。

缺点：

- route / surface / page context 无法进入 metadata 真相源。
- 各入口默认上下文容易继续分叉。

### 方案 B：改成普通详情页路由

优点：

- 路由清晰。

缺点：

- 视觉上更像业务页面，不像全局搜索面板。
- 容易破坏 iOS 规则里的“唯一全屏全局浮层”语义。

### 方案 C：route-driven 全屏搜索页，内部仍使用 full-screen modal surface

优点：

- 同时满足 metadata 路由治理与全屏浮层语义。
- 可统一首页、聊天页、群组页、助手页入口。

缺点：

- 需要同步调整入口触发器和返回逻辑。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：新增 `globalSearch` route 与两类 surface

- route：`globalSearch`
- surfaces：
  - `globalSearchLanding`
  - `globalSearchResults`

### KD2：引入 `SearchLaunchContext`

字段最少包含：

- `entrySurfaceId`
- `initialScope`
- `prefilledQuery`
- `restoreState`

它作为 route extra 或页面参数进入 `GlobalSearchPage`，而不是散落在各页面状态里。

### KD3：入口统一走 `SearchEntryLauncher`

- 首页、聊天页、群组页、助手页都调用同一 launcher。
- launcher 只负责组装 `SearchLaunchContext` 与导航，不负责搜索状态。

### KD4：landing 页四段式结构固定

1. 搜索框
2. 问小趣 + 语音
3. 指定搜索内容
4. 最近搜索

### KD5：metadata / codegen 方案

- `_shared/app_routes.yaml`：新增 `globalSearch`
- `_shared/ui_surfaces.yaml`：新增 landing / result surfaces
- `_shared/request_context.yaml`：新增 `global.search.landing`、`global.search.results`

### KD6：迁移与兼容

- `GlobalSearchSheet` 不再作为结构真相源。
- 允许短期内部复用其视觉代码，但最终入口统一转向 `GlobalSearchPage`。
- 不保留旧入口并行治理。

## 字段演进、迁移/回填、必要时双读双写方案

- `GlobalSearchScope` 可在实现期过渡映射到 `SearchScope`。
- 不存在云端双写；仅路由与页面状态迁移。

## feature flag、观测、SLO 验证与回滚方案

- 不新增 feature flag。
- 观测：
  - `global_search_open_count`
  - `global_search_cancel_count`
  - `global_search_entry_source_distribution`
- SLO：
  - landing 首帧即时可见
- 回滚：
  - 整版回退到旧搜索实现

## TDD / ATDD 策略

- `T1_schema`：route / surface / request context
- `T2_module_interaction`：壳层布局、入口统一、返回行为
- `T4_user_journey`：从四个一级页进入搜索首页

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 route/surface/page context | `T1_schema` |
| `P2` | 落地 `GlobalSearchPage` 与统一入口 | `T2_module_interaction`, `T4_user_journey` |
| `P3` | 验证重入、返回与响应式布局 | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 后续若需要 deep link 直达搜索结果，可继续沿用同一路由与 `SearchLaunchContext` 扩展。
