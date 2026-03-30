# L3：S8 — P8 设计系统语义 token 全页落实

## 背景与动机

- 横向质量矩阵 **P8** 要求：间距、字阶、圆角、色等走 **语义 token**，禁止魔法数与非语义混用（与 `verify_dart_semantic.py` 同向）。  
- 当前大量已知违规登记在 `scripts/.verify_dart_semantic_baseline.txt`，门禁在 baseline 下通过；**目标**是在 **S8 会话**内按波次 **收缩 baseline**、更新矩阵 **P8** 列，而非永久依赖豁免列表。  
- **P7（断点/版式）** 由独立会话 S7 负责；本 L3 **禁止**将断点策略与 token 替换混在同一 PR 的验收口径中。

## 目标用户与目标

| 角色 | 目标 |
|------|------|
| 开发者 | 有 **明确页面清单 + 波次 + 置 ✓ 证据**，可逐 PR 落实 token |
| Reviewer | PR 可对照 **baseline 行删除** 与 **矩阵 P8** 一致性审查 |
| CI | `verify_dart_semantic.py` 保持阻断新增违规；baseline **单调减**（除登记豁免） |

## 功能范围（In Scope）

1. **范围面**：与 [`page-horizontal-quality-matrix.md`](../page-horizontal-quality-matrix.md) 扫描基线一致 — `lib/ui/**/pages/*_page.dart`、`welcome_screen.dart`、`lib/components/**/*_page.dart`、`lib/app/shell/*.dart`；以及矩阵声明的 **挂靠面**（与父行共用 P8）。  
2. **依赖闭包**：矩阵 **页文件** 无违规 ≠ 整页合规；子树在 `ui/*/widgets/`、`components/` 的硬编码须在 **同一波次或紧随 PR** 收口，否则矩阵 **P8=✓** 须在备注中指向未收口子路径（**○**）。  
3. **优先工单（baseline 已含页级路径）**：下列 **12 个文件** 为 **W1 强制批次**（与 explore 结论一致）：  
   - `lib/components/media/camera/camera_capture_page.dart`  
   - `lib/ui/circle/pages/circle_edit_settings_page.dart`  
   - `lib/ui/content/entry/pages/create_page.dart`  
   - `lib/ui/content/entry/pages/video_editor_page.dart`  
   - `lib/ui/content/pages/article_detail_page.dart`  
   - `lib/ui/rtc/pages/incoming_call_page.dart`  
   - `lib/ui/rtc/pages/outgoing_call_page.dart`  
   - `lib/ui/user/pages/edit_profile_page.dart`  
   - `lib/ui/user/pages/persona_management_page.dart`  
   - `lib/ui/user/pages/profile_stats_page.dart`  
   - `lib/ui/user/pages/sub_account_management_page.dart`  
   - `lib/ui/welcome/pages/welcome_screen.dart`  
4. **token 真相源**：`AppSpacing`、`AppTypography`、`AppColors` / `AppColorsFunctional`、`SettingsSemanticConstants`、`design_semantic_constants`；**新增重复字面量**前须先评估是否扩展 `AppSpacing`「扩展语义尺寸」或域内私有 `*_layout_constants.dart`（仍须为 **命名常量**，禁止散落魔法数）。

## Out of Scope

- **P7**：`responsiveValue`、`compactBreakpoint` 等版式策略 — **S7**。  
- **metadata / codegen / Go 服务**：本 L3 **无** `contracts/metadata` 变更。  
- **小趣 runtime 垂类特判、字符串硬编码协议**：不适用本 L3；若改动触及助手 UI，仍须遵守 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`，**不得**借 token 改造引入新特判。  
- **一次性清空 baseline**：不承诺单 PR 清零；承诺 **波次推进 + baseline 单调减**。

## 约束与对标

- 父规格：[`page-horizontal-quality-spec.md`](../page-horizontal-quality-spec.md) **P8** 行。  
- 门禁：[`scripts/verify_dart_semantic.py`](../../../../../scripts/verify_dart_semantic.py)、[`page_horizontal_quality_pr_checklist.md`](../../../../../specs/gates/page_horizontal_quality_pr_checklist.md) §P8。  
- iOS 体验：`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`（token 与材质一致，**不替代** P1 根壳门禁）。

## 既有 Story 覆盖矩阵

| Story | 关系 |
|-------|------|
| `page-horizontal-quality` | 父 L3；矩阵与 PR 清单 |
| `nine-session-rollout-plan` | S8 会话定义 |
| `ios-native-page-enforcement` | 与 `verify_dart_semantic` 部分规则重叠；改代码时注意 **P1/P8 PR 边界** |

## 数据生命周期 / 权限 / 分享

不适用（无用户数据模型变更）。

## 非功能目标

- **可维护性**：字面量集中为命名常量，便于深色模式与响应式后续迭代。  
- **CI**：`verify_dart_semantic` 继续接入 `make gate` app 段；baseline 变更须可 diff 审计。

## 迁移、灰度与回滚

- **迁移**：仅 Dart 源码与 baseline 文本；无 DB。  
- **灰度**：不需要 feature flag。  
- **回滚**：revert 对应 PR；恢复 baseline 行若需保持 gate 绿。

## 验收重点摘要

- 各波次 PR：**删除**对应 `.verify_dart_semantic_baseline.txt` 条目或 **`// ignore: verify_dart_semantic`** 仅限 **单行且备注原因**。  
- `page-horizontal-quality-matrix.md` **P8** 列与 **备注** 与真实代码一致。  
- `python3 scripts/verify_dart_semantic.py` 通过；矩阵与扫描脚本通过。

## L1 / L2 / L3

| 层级 | 标识 |
|------|------|
| L1 | `runtime` |
| L2 | `runtime-client-foundation` |
| L3 | `s8-p8-semantic-token` |
