# design：page-horizontal-quality

## 上游规格评审

- 已对齐仓库主线：`metadata-first`、iOS Native UX spec、`page-horizontal-quality-spec.md` 中 P1–P8 定义及与 `metadata_driven_ui_gap_inventory` 的 **P2 映射规则**。  
- **Out of Scope**：不在本 L3 内一次性改完所有页面的 `○` → `✓`；逐页收敛由各业务 L3 的 `plan.yaml` 承载。

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
