# design：page-horizontal-quality

## 上游规格评审

- 已对齐仓库主线：`metadata-first`、iOS Native UX spec、`page-horizontal-quality-spec.md` 中 P1–P8 定义及与 `metadata_driven_ui_gap_inventory` 的 **P2 映射规则**。  
- **Out of Scope**：不在本 L3 内一次性改完所有页面的 `○` → `✓`；逐页收敛由各业务 L3 的 `plan.yaml` 承载。  
- **九会话落实**：执行顺序与每会话出口见 [`nine-session-rollout-plan.md`](./nine-session-rollout-plan.md)（S1–S8 各单一横向维，**S7/S8 分离**；**S9** 收口 + gate）。
- **实施波次 B（Mock·端云·测试编译隔离）**：与 S1–S9 **正交**，见同文件 **§实施波次 B** + [`tasks.md`](./tasks.md) **M8** + [`mock_data_cloud_integration_policy.md`](../../../../gates/mock_data_cloud_integration_policy.md)；验收 **A6** / `plan.yaml` **slice-6** 与实施首 PR 同步落盘。

## S2 冻结边界（P2 元数据契约 · 登记基线）

**S2** 在设计与验收上 **仅等于**：[`page-horizontal-quality-matrix.md`](../page-horizontal-quality-matrix.md) 的 **P2 列**与 `specs/gates/metadata_driven_ui_gap_inventory.yaml` 中各页 `status` **按规则一致**（`compliant`→✓，`partial`/`current_map`→○，`exempt`→—）；**全页逐行对照、统计与「规格基线锁定」声明** 以 [`s2-metadata-driven-contract-baseline-20260330.md`](./s2-metadata-driven-contract-baseline-20260330.md) 为证据。**S2 不承诺** 将全量 `partial` 改为 `compliant` 或消灭 UI 层 Map（属后续域级 `/dev` 与 S9）。权威顺序与兄弟 L3 见 [`metadata-driven-client-data-contract/spec.md`](../metadata-driven-client-data-contract/spec.md) 覆盖矩阵。

## S1 冻结边界（勿与 S6/S7/S8 混谈）

**S1** 在设计与验收上 **仅等于**：[`page-horizontal-quality-matrix.md`](../page-horizontal-quality-matrix.md) 的 **P1 列**全量落实（凡适用页为 **✓** 或 **—**，**—** 须在备注或 `ios_native_surface_allowlist` 等旁路有据可查）以及 **`ios-native-page-enforcement`** 所覆盖的 **iOS 根壳门禁面**（`scripts/verify_ios_native_surface_gate.py`、allowlist；置 ✓ 的最低证据见 [`page_horizontal_quality_pr_checklist.md`](../../../../gates/page_horizontal_quality_pr_checklist.md) §P1 与 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.1、§2.8）。**S1 会话完成出口**以 [`nine-session-rollout-plan.md`](./nine-session-rollout-plan.md) **会话 1** 表格列「本会话退出时矩阵状态」为唯一口径（凡适用页 P1 为 **✓** 或 **—**）。**S6/P6**（双色）、**S7/P7**（断点/版式）、**S8/P8**（语义 token）均 **不在 S1 冻结范围内**，S1 的 PR/评审不得将其与 P1 根壳门禁面混为同一必收项。

## 方案对比与选型结论

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 可扩展横向矩阵 + 门禁脚本** | 单表登记全页路径与 P1–Pn；CI 校验路径存在与符号合法；PR 清单强制更新 | **选用** |
| **B. 分散在各域 spec 重复列表** | 无统一枚举，易漏页、难门禁 | 不采纳 |
| **C. 仅文档无自动化** | 无法阻断漏登记 | 不采纳 |

## 迁移 / 双写 / feature flag

- 不适用双读双写；**无 feature flag**。新增维度（P9…）时同步 bump 脚本 `PILLAR_COUNT` 与矩阵表头。

## 观测与回滚

- **观测**：矩阵变更频率、PR checklist 勾选、与 `dual-theme-page-coverage` 矩阵交叉引用。  
- **回滚**：revert 矩阵/脚本/CR；不影响运行时用户数据。

本 L3 为 **索引型场景**：横向维度定义、矩阵与门禁脚本以父目录与 `specs/gates/` 为唯一真相源，见 `spec.md` 文档表。

## 方案选型（实现要点）

- **沿用** `page-horizontal-quality-spec.md` 中的 T1–T7 页面类型与 **P1–P8** 维度语义（**P7** 断点/版式，**P8** 语义 token，**禁止合并表述**）。  
- **校验**：`scripts/verify_page_horizontal_quality_matrix.py` + PR 清单；不在此目录重复矩阵正文。  
- **各维置 ✓ 最低证据**：见 [`specs/gates/page_horizontal_quality_pr_checklist.md`](../../../../gates/page_horizontal_quality_pr_checklist.md) §「各维置 ✓ 的最低证据」。

## 与相关 L3 的关系

- 与 `ios-native-page-enforcement`、`dual-theme-page-coverage` 并列消费同一套维度语义；具体页面改造在各业务 L3 的 `plan.yaml` 中切片。

## 迁移与回滚

无独立数据迁移；矩阵或脚本变更通过 PR 与门禁回滚。

## 实施波次 B — §5.1 功能规格基线（2026-03-30）

与 S1–S9 **正交**：不新增业务 metadata/codegen；冻结 **客户端工程** 对「发布态 / 开发测试态」的共用验收口径。

### 上游规格

- 唯一策略正文：[`mock_data_cloud_integration_policy.md`](../../../../gates/mock_data_cloud_integration_policy.md) **§5.1**（表 **R1–R6**、**D1–D4**、**测试代码用语边界**）。
- **Out of Scope（本基线不承诺）**：Dart AOT 二进制内 **物理零 Mock 类链接**（**P4** 另列实施切片，见策略 §5 与 [`CR-20260330-010`](../../../../changelog/CR-20260330-010-mock-isolation-implementation-wave.md)）。

### 方案结论

| 维度 | 结论 |
|------|------|
| 发布态默认数据源 | Release 下有效模式 **Remote**；`APP_DATA_SOURCE` 与 `main_prod`/CI 显式 **remote**（R1、R5） |
| 用户可见切换 | Release **无** Mock/Remote 入口（R2） |
| 工程隔离 | `lib/ui`、`lib/app`、`lib/core` **不** import `cloud/services/*/mock/`（R4）；`verify_ui_mock_isolation.py` 强制执行 |
| 开发测试态 | **单一** `appDataSourceModeProvider` 一键切换（D1）；开关仅非 Release（D2） |
| 伪 Remote | `Remote*Repository` **不得**整表委托 `Mock*`（R6 / 策略 §3 P2） |

### 流程与规则对齐

- Cursor：`08-mock-data-isolation.mdc`；`/explore` G0-10、`/verify` 端侧小节、`/commit` 可选 mock 门禁。
- 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — Flutter `/dev` 与 `/commit` 追加 `make verify-app-mock-isolation`；正式构建审阅 **§5.1 R5**。

### 观测与回滚

- **观测**：`make gate` app 段、`app_pipeline` 中 `flutter build ... -t lib/main_prod.dart --dart-define=APP_DATA_SOURCE=remote`。
- **回滚**：revert 策略 §5.1 段落或 CI 定义；恢复前须重新评估商店默认数据源。
