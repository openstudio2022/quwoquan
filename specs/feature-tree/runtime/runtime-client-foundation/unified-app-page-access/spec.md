# L3：统一应用页级埋点（unified-app-page-access）

## 索引

| 文档 | 说明 |
|------|------|
| [design.md](./design.md) | 方案对比、路由状态机、嵌套 push 约定 |
| [coverage-surfaces.md](./coverage-surfaces.md) | **全表面分类**与 /dev 核对清单 |
| [acceptance.yaml](./acceptance.yaml) | 验收与证据矩阵 |
| [plan.yaml](./plan.yaml) | 实施切片（metadata → 根路由 → pageName → 嵌套审计） |
| [CR-20260330-013](../../../../changelog/CR-20260330-013-unified-app-page-access-baseline.yaml) | 变更登记 |

## 背景与目标

- **P4（横向质量）**：页面级 **open / return /（可选）停留** 进入 **`AppLogService`** 统一管道，与 `AppTraceContextStore` 的 `sessionId` / `journeyId` / `pageVisitId` 对齐。
- **问题**：欢迎流使用 **独立 `MaterialApp(home: WelcomeScreen)`**，不在 **`GoRouter` 根 `NavigatorObserver`** 上，只能靠页面 **手写** `writeAppPageAccessOpen/Return`；全站 **`pageName`** 对非 Tab 路径多为 **`route_unknown`**，分析不可读。
- **目标**：**方案 A** — 欢迎页走 **真实路由 `/welcome`**，与 **全屏栈同一套 Observer**；在 **尽量不改动各业务 `*_page.dart`** 的前提下，**覆盖所有应计一次的「页面表面」**。

## In Scope

1. **`contracts/metadata/_shared/app_routes.yaml`** 登记 **`welcome` → `/welcome`**，**`make codegen-app`** 更新 `AppRoutePaths`（**baseline 已落 metadata + 已 codegen**）。
2. **`QuWoQuanAppRoot`**：**单一 `MaterialApp.router`** + **`GoRouter` `redirect`**：未完成欢迎 → **`/welcome`**；完成后 → 允许进入 **`/`** 等主壳路由。欢迎完成后行为与现 **`welcomeCompletedProvider`** 一致。
3. **`WelcomeScreen`**：**删除** 内联 **`writeAppPageAccess*`**（由 Observer 统一打 open/return）。
4. **`page_access_log_util.dart`**：**扩展** `pageNameFromRouteLocation`（或并列 **`pageAccessDisplayNameForLocation`**）：对 **`AppRoutePaths` 上登记的每一条 path 模式**（含带 path param 的 **前缀/模板**）给出稳定 **`pageName`**，消除默认 **`route_unknown`**（可与 `main_tab_registry` 并列维护 **一张表**）。
5. **子栈 / 模态**：凡 **仍走根 `Navigator` 且能产生可见「全屏页」** 的 **`Navigator.push` / `CupertinoPageRoute` / `MaterialPageRoute`**，**必须** 带 **`RouteSettings(name: ...)`**，且 `name` **落在登记集合**内（与 `app_router` 或 **嵌套路由登记常量** 一致），否则 **P4 视为缺口**。

## Out of Scope（本 L3 /dev 不阻塞收口）

- **`AnalyticsService` stub** 与 **`AppLogService` 完全合并**（另开切片 / CR）。
- **页内细粒度点击流**（如技能中心 `skill_center_action`）的 schema 统一（可在后续切片要求 **复用当前 `pageVisitId`**，见 `design.md`）。
- **`welcomeCompletedProvider` 持久化**（未持久则每次冷启动仍见欢迎；与现行为一致，不在本 baseline 改产品语义，除非单独 PRD）。

## 约束

- **metadata-first**：**`/welcome`** 仅通过 **`app_routes.yaml` → codegen**，禁止手写第二套 path 常量于业务页。
- **禁止双计**：同一用户可见「表面」在 **open** 上 **只打一次**；Tab 与全屏栈边界以 **`isShellTabLocation`** 与现有 **`MainAppShell`** 逻辑为准，**不重复** welcome 与 Tab。

## 商用与 NFR

| 项 | 结论 |
|----|------|
| SLO/KPI | 治理型；不单独承诺线上 SLO。 |
| 权限 / 数据 | 日志脱敏沿用 **`AppLogService`** 既有策略。 |
| 灰度 / 回滚 | PR revert；redirect 逻辑可 feature-flag 化（可选，非本 baseline 必须）。 |

## 相关文档

- [`page-horizontal-quality-spec.md`](../page-horizontal-quality-spec.md) **P4** — 横向维度对齐。
