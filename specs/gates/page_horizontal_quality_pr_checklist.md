# PR 自检：页面横向质量矩阵（强制）

> 若本 PR **新增或实质性改版** `lib/ui/**/pages/*` 或 `lib/components/**/*_page.dart`，请完成下列项。  
> **不叫「七支柱」**：合规项以矩阵 **P1–Pn** 为准，可扩展；**P7（断点/布局）与 P8（语义 token）须分开自检**，不得合并成一条描述。

## 矩阵更新

- [ ] 已在 [`page-horizontal-quality-matrix.md`](../feature-tree/runtime/runtime-client-foundation/page-horizontal-quality-matrix.md) **新增一行**或更新已有行（路径、领域、类型、**P1–P8**）。
- [ ] **P1–P8** 每项已填 **`✓` / `—` / `○`**（`○` = 待审计，专项合入前须收敛），**无空白**；`—` 已在「备注」列简要说明。

## 维度快速核对（当前 P1–P8）

- [ ] **P1** iOS 根壳与材质符合规范；无违规 Material 根 Scaffold（见 `ios-native-page-enforcement`）。
- [ ] **P2** 云接口与模型来自 metadata codegen；无手写 path/operation 第二真相源。
- [ ] **P3** 有 Mock + Remote Repository 与数据源切换（无云则标 **—**）。
- [ ] **P4** 页面观测已接统一管道或已标 **—**（豁免说明备注）。
- [ ] **P5** 设置/半屏场景已复用标准组件或标 **—**。
- [ ] **P6** 浅色/深色可读可点或已登记豁免（S6）。
- [ ] **P7** 仅谈 **断点与版式**：`AppSpacing`/`responsiveValue`/登记宽度语义；**不与 token 混写**。
- [ ] **P8** 仅谈 **语义 token**：间距/字阶/圆角/色等；**不与断点策略混写**。

## 各维置 ✓ 的最低证据（与门禁 / 脚本对齐）

| 维 | 置 ✓ 时须满足（摘要） | 自动化 / 文档 |
|----|------------------------|---------------|
| **P1** | 根 `build` 为 `AppScaffold` / `CupertinoPageScaffold` / 已登记等价壳（含 `ConversationPageScaffold`、`SettingsInsetFormPageScaffold`、`IosSelectionPageScaffold` 等）；或 Tab 内嵌内容区无根 `Scaffold`；子树 `Material` 为 `MaterialType.transparency` 宿主 | `python3 scripts/verify_ios_native_surface_gate.py`；`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.1、§2.8 |
| **P2** | 主读写 API 与 DTO 来自 `contracts/metadata` → codegen；无第二套 path/operation | `python3 scripts/verify_cloud_services_semantic.py`（同向）；逐页 import/Repository 核对 |
| **P3** | 云数据经 `Mock*Repository` / `Remote*Repository` 与 `appDataSourceModeProvider`（或等价）；UI 无裸 HTTP | 逐页 Provider/Repository |
| **P4** | 页面级 open/close/停留进入 `AppLogService` 等统一管道；或备注豁免 | Tab 根：`MainAppShell` pageAccess；其余待 GoRouter 级补全时标 **○** 并备注 |
| **P5** | 设置表单走 `SettingsInsetForm*`；对话态走 `settings_conversation/` / `ConversationPageScaffold` 等 | `python3 scripts/verify_settings_canonical.py`、`verify_conversation_sheet_canonical.py`（同向） |
| **P6** | 双色下可读可点；或与 `dual-theme-page-coverage/page-dual-theme-matrix.md` 交叉引用 | 兄弟 L3 S6 |
| **P7** | compact/regular/expanded 版式可用；优先 `AppSpacing.responsiveValue`、`feedMaxContentWidth` 等 | 与 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.7 一致 |
| **P8** | 间距/字阶/圆角/色用语义 token，无魔法数体系 | `python3 scripts/verify_dart_semantic.py` 等 gate 脚本 |

## Reviewer

- [ ] Reviewer 已确认矩阵列与代码变更一致。
