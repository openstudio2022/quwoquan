# L3：iOS 原生页面壳与门禁（ios-native-page-enforcement）

## 背景与动机

`quwoquan_app` 面向 **iOS 原生画质**（`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`）。记录上部分全屏页仍使用 **Material `Scaffold` 作为根壳**，与「Native First / No Android Leakage」冲突，且难以在 PR 阶段自动拦截新增违规。

## 目标用户与目标

| 角色 | 目标 |
|------|------|
| 终端用户 | 全应用页面层级、导航栏、材质与 iOS 系统应用一致 |
| 开发者 | 新增/修改页面时有 **可执行门禁** 阻断违规根壳 |
| 质量 / CI | `make gate` 失败即阻止合入非 iOS 根壳页面 |

## 功能范围（In Scope）

1. **页面根壳策略**：`lib/ui/**/pages/` 下业务页及约定的 `components` 全屏页，根 `build` **必须**以 `CupertinoPageScaffold` 或 `AppScaffold`（及项目内等价的 iOS 壳封装）作为最外层可导航壳，**禁止** `return Scaffold(` 作为页面根（Material 全屏壳）。
2. **门禁**：仓库 `scripts/verify_ios_native_surface_gate.py` + `specs/gates/ios_native_surface_allowlist.yaml`；**默认阻断** 新增 `return Scaffold(`；存量例外仅经 allowlist 登记，且 **allowlist 仅允许收缩**（新违规不得加入长期豁免，除非同步记为技术债任务）。
3. **规范对齐**：本 L3 与 `page-layout-semantics`、`07-ios-native-ux` 规则、`SettingsInsetFormPageScaffold` 等已落地模式一致；不重复定义 token，仅约束 **根壳选型** 与 **CI 阻断面**。

## Out of Scope

- 不在本 L3 一次性改写所有记录页面的视觉细节（圆角、间距等）——由后续切片与 `page-layout-semantics` 子项消化。
- 不禁止 `Material(type: transparency)` 作为 **Cupertino 子树** 的防溢出/字体渲染宿主（与现有 `AppScaffold` 模式一致）。
- 不覆盖 **非 Dart UI**（Web、Android 专属壳）。
- 不在本 baseline 内实现 **AST 级** 全量组件审计（仅约定 v1 为基于文件的正则门禁，v2 可演进）。

## 约束与对标

- **唯一体验标准**：`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.1、§2.8。
- **架构约束**：页面入口仍在 `lib/ui/{domain}/pages/`（见仓库目录规则）。

## 覆盖矩阵

| 既有 Story | 关系 |
|------------|------|
| `page-layout-semantics` | 本 L3 补齐 **根壳** 与 **CI**；其负责 leading/选择器/设置块结构 |
| `dart-semantic-gate` | 互补：语义 token / 相对路径；本门禁专盯 **Material 根 Scaffold** |
| `dual-theme-page-coverage`（**S6**） | 同一套 iOS 壳在 **浅色/深色** 下材质与对比达标；见兄弟 L3 `dual-theme-page-coverage/spec.md` |
| `page-horizontal-quality` | **P1** 与本门禁对齐；全页清单与 **P1–P8** 矩阵见 `page-horizontal-quality-spec.md` / `page-horizontal-quality-matrix.md` |

## 数据生命周期 / 权限

不适用（工程治理与 UI 壳）。

## 迁移与回滚

- **迁移**：将 allowlist 中文件逐一切换为 `AppScaffold`/`CupertinoPageScaffold` 后从 allowlist 删除。
- **回滚**：若门禁误伤，可短期扩大 allowlist 并开 issue；**禁止**在无 CR 说明下永久扩大豁免列表。

## 场景验收 S1（本会话可独立 baseline 的边界）

> **`acceptance.yaml` 中 `scenario_acceptance.id: S1`**：开发者在**约定扫描路径**内的 Dart 文件写入 **`return Scaffold(`**（Material 根壳典型写法）时，本地 **`make gate` 非零退出**，且 stderr **引用** `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`（Native First / No Android Leakage）。  
> **S1 不等价于**：全量满足 `02` 全文（Token、断点、深色、无 ripple 等）；后者由 **`page-horizontal-quality` P1**、`dart-semantic-gate`、`dual-theme-page-coverage`（S6）等分担，**不得**在仅交付 S1 的会话中要求「逐条 02 审计完毕」。

## 验收重点摘要

- `make gate` 执行时运行 `verify_ios_native_surface_gate.py` 且通过。
- 新增页面若使用 `return Scaffold(` 且无 allowlist 条目 → **gate 失败**。
- `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` / `CR` 已归档。

## L1 / L2 / L3 映射

| 层级 | 标识 |
|------|------|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `ios-native-page-enforcement` |
