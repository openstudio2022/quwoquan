# L3：全页面深色 / 浅色模式覆盖（dual-theme-page-coverage）

> **编号**：**S6**（与并行会话中的 iOS 原生壳、元数据驱动、端云一体化、统一埋点、组件复用等轨道并列；本轨道专注 **双色模式完整性**。）  
> **层级**：L3_story（隶属 L2 `runtime-client-foundation`）

## 背景与动机

`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.5 **Symmetric Dark Mode** 要求：每一套浅色材质须有深色对应，深色模式不是简单反色。历史上部分页面仍使用 **固定亮度色值、仅按浅色设计、或未接 `isDark`/`CupertinoDynamicColor`**，导致深色模式下对比不足、漏光或与壳层材质冲突。

`app-theme-infrastructure` 已定义 **全局主题运行时**（含 `system/light/dark`）；本 L3 将 **落地范围收紧为「可枚举的页面 / 全屏表面」**，要求 **逐页可验收**，并 **补齐不支持双色的页面**。

## 目标用户与目标

| 角色 | 目标 |
|------|------|
| 终端用户 | 任意可导航页面在 **浅色 + 深色** 下均可读、可点、层级清晰 |
| 开发者 | 有 **页面矩阵** 与 **门禁/清单** 可对照改；禁止新增「仅浅色」业务页 |
| 质量 | 可按域分批回归；关键路径支持 **截图对比或 Golden**（可选增强） |

## 功能范围（In Scope）

### S6-1 页面枚举与分类（分析，无遗漏口径）

对以下 **Dart 表面** 建立 **全量清单**（与路由、主导航、模态栈对齐，版本化归档于本 feature 目录或 `specs/` 约定路径）：

| 范围 | 说明 |
|------|------|
| `lib/ui/**/pages/**/*.dart` | 业务页面入口 |
| `lib/components/**/**_page.dart` 及承担 **全屏** 的组件 | 如媒体编辑器、选择器、相机等 |
| `lib/app/shell/**` | 主壳、底栏、与主题相关的 `AnnotatedRegion` |
| **排除** | 纯导出文件、无 UI 的 `*_models.dart`、测试专用页（若在 `test/`） |

清单中 **每一行** 至少包含：**路径、领域、路由/入口类型（Tab / GoRoute / push）、当前双色结论（支持 / 部分 / 不支持 / 豁免）、证据（截图或自检项）、责任人/迭代**。

### S6-2「支持双色」的判定标准（必须同时满足）

1. **页面主背景、主表面、主/次文字、分割线、图标** 在浅色与深色下均来自 **语义 token** 之一：`AppColorsFunctional.getColor(isDark, ColorType.*)`、`CupertinoDynamicColor.resolve`、`SettingsSemanticConstants` / `SearchSemanticConstants` 等已登记语义；**禁止**用 `Color(0xFF…)`、`Colors.white/black` 作为主阅读面或主文字（`specs/02_*` 与 `dart-semantic-gate` 已禁的类别与本 L3 **对齐执行**）。
2. **状态栏 / 系统导航栏图标亮度** 与当前页背景对比 **AA 级意图**（与 `app-theme-infrastructure` UI7 一致；具体测量可在设计稿或抽检中约定）。
3. **强制深色业务场景**（如作品频道 `worksBackground`）须在矩阵中标记为 **豁免类**，并写明 **浅色是否禁用或如何降级**，避免用户切浅色后不可读。

### S6-3 不支持时的补齐策略

- 优先 **替换为语义色 + 双模式分支**；能统一走 `Theme` / `CupertinoTheme.of(context)` 的 **不重复传 `isDark`**。
- **表单 / 设置类** 优先复用 `SettingsInsetFormPageScaffold` / `insetForm*` token，与 `page-layout-semantics--settings-page-structure` 一致。
- **半屏 / Sheet** 与全屏页 **同一套表面层级规则**，禁止浅色页 + 深色 sheet 无依据混用。

### S6-4 验收与持续集成（v1 → v2）

| 阶段 | 要求 |
|------|------|
| **v1** | 全量矩阵完成；**所有「不支持/部分」行有修复 PR 或登记为带截止的技术债**；`flutter analyze` + 域内抽检通过 |
| **v2（可选）** | 增加脚本或 Golden：**关键页** 深浅色截图对比；或与 `verify_dart_semantic.py` 扩展硬编码色巡逻范围 |

## Out of Scope

- 不改变 **业务功能范围**（仅视觉与主题可达性）。
- 不替代 **app-theme-infrastructure** 的全局 Theme 架构实现；本 L3 **消费**其结果并 **约束页面层**。
- 不在本 baseline 内完成 **全量自动化视觉回归**（可作为后续 slice）。

## 约束与对标

- **唯一体验标准**：`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.5、§3.2 颜色语义表。
- **兄弟 Story**：`app-theme-infrastructure`（全局运行时）、`dart-semantic-gate`（硬编码字面量）、`ios-native-page-enforcement`（根壳材质）、`page-layout-semantics*`（设置块结构）。

## 覆盖矩阵

| 既有 Story | 关系 |
|------------|------|
| app-theme-infrastructure | 提供全局 light/dark/system；本 L3 保证 **页面层** 全部接入 |
| dart-semantic-gate | 互补：禁硬编码色；本 L3 补 **按页矩阵与豁免登记** |
| ios-native-page-enforcement | 根壳一致后，**同一壳在双色下材质不断裂** |

## 数据生命周期 / 权限

不适用。

## 迁移与回滚

- **迁移**：按领域分批合入；矩阵状态从「不支持」→「支持」需附自检说明或截图。
- **回滚**：若某页深色回归风险高，可短期标为 **豁免** 并开 issue，**禁止**无截止永久豁免。

## 验收重点摘要（供总会话统一验收）

- 存在 **经评审的全页面矩阵**（无故意遗漏；新增页在 PR 中更新矩阵或门禁）。
- **无未关闭的 P0「仅浅色」**（豁免类除外且已文档化）。
- `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` 与 `02_IOS_NATIVE_FRONTEND_UX_SPEC` 一致。

## L1 / L2 / L3 映射

| 层级 | 标识 |
|------|------|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `dual-theme-page-coverage`（**S6**） |
