# L3：页面横向质量矩阵（page-horizontal-quality）

> **索引**：规格与全量矩阵在父目录平铺，便于与 `ios-native-page-enforcement`、`dual-theme-page-coverage` 并列检索。  
> **命名**：**不叫「支柱」**；合规项为可扩展 **横向维度 P1–Pn**（当前 **P1–P8**，**P7 布局 / P8 语义 token 分列**）。

| 文档 | 路径 |
|------|------|
| 横向维度定义、页面类型 T1–T7、强制校验 v1/v2 | [page-horizontal-quality-spec.md](../page-horizontal-quality-spec.md) |
| 领域 × 类型 × P1–P8 矩阵 | [page-horizontal-quality-matrix.md](../page-horizontal-quality-matrix.md) |
| PR 自检清单 | [page_horizontal_quality_pr_checklist.md](../../../../gates/page_horizontal_quality_pr_checklist.md) |
| v1 自动化校验 | 仓库根 `scripts/verify_page_horizontal_quality_matrix.py` |
| 变更请求（baseline） | [`CR-20260329-005-page-horizontal-quality-baseline.yaml`](../../../../changelog/CR-20260329-005-page-horizontal-quality-baseline.yaml) |

## L1 / L2 / L3 映射

| 层级 | 标识 |
|------|------|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `page-horizontal-quality` |
