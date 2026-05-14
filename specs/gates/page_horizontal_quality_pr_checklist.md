# PR 自检：页面横向质量矩阵（强制）

> 若本 PR **新增或实质性改版** `lib/ui/**/pages/*` 或 `lib/components/**/*_page.dart`，请完成下列项。  
> **不叫「七支柱」**：合规项以矩阵 **P1–Pn** 为准，可扩展；**P7（断点/布局）与 P8（语义 token）须分开自检**，不得合并成一条描述。

## S9 / 持续治理（合入前必过）

| 层级 | 要求 |
|------|------|
| **规则** | 仓库 [.cursor/rules/09-page-horizontal-quality.mdc](../../.cursor/rules/09-page-horizontal-quality.mdc)（`alwaysApply`）：改页面路径即须矩阵 + 清单。 |
| **架构约束** | [.cursor/rules/01-arch-constraints.mdc](../../.cursor/rules/01-arch-constraints.mdc) §2.4 表内「横向质量矩阵」行。 |
| **命令** | `make verify-app-page-horizontal-quality`（矩阵 + 漏页/清单）；全量 `bash agent_ops/gate/gate_repo.sh --scope app` 或根目录 `make gate`。 |
| **门禁** | `agent_ops/gate/gate_repo.sh` → `verify_page_horizontal_quality_matrix.py`、`verify_page_matrix_scan_complete.py`、`verify_metadata_driven_ui_gate.py` 等与 P2 同向脚本。 |
| **流程** | 九会话规划见 `specs/.../page-horizontal-quality/nine-session-rollout-plan.md`；**新增页**不等待 S1–S8 重跑，但须 **当 PR 满足 P1–P8 当前列** 或标 `○` 并备注债/Story。 |

## 矩阵更新

- [x] 已在 [`page-horizontal-quality-matrix.md`](../feature-tree/runtime/runtime-client-foundation/page-horizontal-quality-matrix.md) **新增一行**或更新已有行（路径、领域、类型、**P1–P8**）。
- [x] **P1–P8** 每项已填 **`✓` / `—` / `○`**（`○` = 待审计，专项合入前须收敛），**无空白**；`—` 已在「备注」列简要说明。

## 维度快速核对（当前 P1–P8）

- [x] **P1** iOS 根壳与材质符合规范；无违规 Material 根 Scaffold（见 `ios-native-page-enforcement`）。
- [x] **P2** 云接口与模型来自 metadata codegen；无手写 path/operation 第二真相源。
- [x] **P3** 有 Mock + Remote Repository 与数据源切换（无云则标 **—**）；且 **未** 在 `lib/ui`、`lib/app`、`lib/core` 新增 `import .../cloud/services/*/mock/` 或 UI 模型内嵌域名 `prototype*` 占位数据（见 §Mock 与端云隔离）。
- [x] **P4** 页面观测已接统一管道或已标 **—**（豁免说明备注）。
- [x] **P5** 设置/半屏场景已复用标准组件或标 **—**。
- [x] **P6** 浅色/深色可读可点或已登记豁免（S6）。
- [x] **P7** 仅谈 **断点与版式**：`AppSpacing`/`responsiveValue`/登记宽度语义；**不与 token 混写**。
- [x] **P8** 仅谈 **语义 token**：间距/字阶/圆角/色等；**不与断点策略混写**。

## 各维置 ✓ 的最低证据（与门禁 / 脚本对齐）

| 维 | 置 ✓ 时须满足（摘要） | 自动化 / 文档 |
|----|------------------------|---------------|
| **P1** | 根 `build` 为 `AppScaffold` / `CupertinoPageScaffold` / 已登记等价壳（含 `ConversationPageScaffold`、`SettingsInsetFormPageScaffold`、`IosSelectionPageScaffold` 等）；或 Tab 内嵌内容区无根 `Scaffold`；子树 `Material` 为 `MaterialType.transparency` 宿主 | `python3 quwoquan_app/scripts/runtime/verify_ios_native_surface_gate.py`；`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.1、§2.8 |
| **P2** | 主读写 API 与 DTO 来自 `contracts/metadata` → codegen；无第二套 path/operation | `python3 quwoquan_app/scripts/runtime/verify_cloud_services_semantic.py`（同向）；逐页 import/Repository 核对 |
| **P3** | 云数据经 `Mock*Repository` / `Remote*Repository` 与 `appDataSourceModeProvider`（或等价）；UI 无裸 HTTP；**Mock 数据仅在 `Mock*Repository` / `cloud/services/*/mock/`，UI 不直连 mock** | `python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py`；[`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md) |
| **P4** | 页面级 open/close/停留进入 `AppLogService` 等统一管道；或备注豁免 | Tab 根：`MainAppShell` pageAccess；其余待 GoRouter 级补全时标 **○** 并备注 |
| **P5** | 设置表单走 `SettingsInsetForm*`；成员搜索嵌入式壳走 **`search_embedded`**（`EmbeddedMemberSearchPageShell`，见 `settings_canonical_manifest`）；对话态走 `settings_conversation/` / `ConversationPageScaffold` 等 | `python3 quwoquan_app/scripts/settings/verify_settings_canonical.py`、`verify_conversation_sheet_canonical.py`（同向） |
| **P6** | 双色下可读可点；或与 `dual-theme-page-coverage/page-dual-theme-matrix.md` 交叉引用 | 兄弟 L3 S6 |
| **P7** | compact/regular/expanded 版式可用；优先 `AppSpacing.responsiveValue`、`feedMaxContentWidth` 等 | 与 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.7 一致 |
| **P8** | 间距/字阶/圆角/色用语义 token，无魔法数体系 | `python3 quwoquan_app/scripts/runtime/verify_dart_semantic.py` 等 gate 脚本 |

## Mock 与端云隔离（强制）

> 策略全文：[`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md)  
> **禁止**为本 PR **新增** `specs/gates/ui_mock_isolation_allowlist.yaml` 条目；仅允许在清记录债时 **删除** 已有条目。

- [x] `lib/ui/**`、`lib/app/**`、`lib/core/**` **未新增** `import 'package:quwoquan_app/.../mock/...'`。
- [x] **未新增** UI 模型中的域名占位（如 `prototypeCircles`、`unsplash` 业务头像链等）；假数据只放在 **`Mock*Repository` 或 `test/`**。
- [x] 若改动数据源切换：正式包路径不得依赖 **伪 Remote→Mock 委托**（见策略 §3 P2）；开发者开关仅 **非 Release** 可见；正式/上架构建须符合策略 **§5.1 R5**（`--dart-define=APP_DATA_SOURCE=remote` 或等价）。
- [x] **编译单元**：未在 `lib/**` 与业务代码 **同文件** 新增仅测用 fake、`forTest` 工厂、`@visibleForTesting` 扩权等（策略 [`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md) **§4.1**）；夹具放在 `test/**`。
- [x] 本地：`make verify-app-mock-isolation` 或 `python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py` 通过。

## Reviewer

- [x] Reviewer 已确认矩阵列与代码变更一致。
