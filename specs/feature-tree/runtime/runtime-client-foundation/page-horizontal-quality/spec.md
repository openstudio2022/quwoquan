# L3：页面横向质量矩阵（page-horizontal-quality）

> **索引**：规格与全量矩阵在父目录平铺，便于与 `ios-native-page-enforcement`、`dual-theme-page-coverage` 并列检索。  
> **命名**：**不叫「支柱」**；合规项为可扩展 **横向维度 P1–Pn**（当前 **P1–P8**，**P7 布局 / P8 语义 token 分列**）。

| 文档 | 路径 |
|------|------|
| 横向维度定义、页面类型 T1–T7、强制校验 v1/v2 | [page-horizontal-quality-spec.md](../page-horizontal-quality-spec.md) |
| 领域 × 类型 × P1–P8 矩阵 | [page-horizontal-quality-matrix.md](../page-horizontal-quality-matrix.md) |
| PR 自检清单 | [page_horizontal_quality_pr_checklist.md](../../../../gates/page_horizontal_quality_pr_checklist.md) |
| v1 自动化校验 | 仓库根 `quwoquan_app/scripts/runtime/verify_page_horizontal_quality_matrix.py` + `verify_page_matrix_scan_complete.py`；**`make verify-app-page-horizontal-quality`** |
| Cursor 治理规则 | [`.cursor/rules/09-page-horizontal-quality.mdc`](../../../../../.cursor/rules/09-page-horizontal-quality.mdc)（`alwaysApply`） |
| 变更请求（baseline） | [`CR-20260329-005-page-horizontal-quality-baseline.yaml`](../../../../changelog/CR-20260329-005-page-horizontal-quality-baseline.yaml) |
| 九会话落实规划（S1–S9） | [nine-session-rollout-plan.md](./nine-session-rollout-plan.md) |
| 统一页级埋点（P4 / 欢迎并轨 GoRouter） | [unified-app-page-access/spec.md](../unified-app-page-access/spec.md) |
| **S2（P2）全页核对与基线锁定** | [s2-metadata-driven-contract-baseline-20260330.md](./s2-metadata-driven-contract-baseline-20260330.md) |
| 变更请求（九会话规划） | [`CR-20260329-006-page-horizontal-quality-nine-session-rollout.yaml`](../../../../changelog/CR-20260329-006-page-horizontal-quality-nine-session-rollout.yaml) |
| 变更请求（S2 / P2 登记基线） | [`CR-20260330-007-page-horizontal-quality-s2-p2-baseline.yaml`](../../../../changelog/CR-20260330-007-page-horizontal-quality-s2-p2-baseline.yaml) |
| 变更请求（S3–S9 合卷 / P4 埋点 + 矩阵收口） | [`CR-20260330-008-page-horizontal-quality-s3-s9-rollout.yaml`](../../../../changelog/CR-20260330-008-page-horizontal-quality-s3-s9-rollout.yaml) |
| 变更请求（S9 治理收口：规则 + Makefile + PR 清单） | [`CR-20260330-014-page-horizontal-quality-s9-governance-closure.yaml`](../../../../changelog/CR-20260330-014-page-horizontal-quality-s9-governance-closure.yaml) |
| Mock·端云·测试隔离策略（§4.1 §9 **§5.1 发布/开发测试态功能规格**） | [`mock_data_cloud_integration_policy.md`](../../../../gates/mock_data_cloud_integration_policy.md) |
| **§5.1 基线冻结登记** | [`CR-20260330-011-mock-release-functional-spec-baseline.yaml`](../../../../changelog/CR-20260330-011-mock-release-functional-spec-baseline.yaml)（与 [`CR-20260329-007`](../../../../changelog/CR-20260329-007-mock-data-isolation-gate.yaml) 互补） |
| **实施波次 B**（S1–S9 之后） | [nine-session-rollout-plan.md §实施波次 B](./nine-session-rollout-plan.md) + [`tasks.md` M8](./tasks.md) |
| CR-20260330-010（实施波次 B） | [`CR-20260330-010-mock-isolation-implementation-wave.md`](../../../../changelog/CR-20260330-010-mock-isolation-implementation-wave.md)（YAML 副本可与实施首 PR 一并补） |
| **S8（P8 语义 token）子 L3** | [`../s8-p8-semantic-token/spec.md`](../s8-p8-semantic-token/spec.md) · [`CR-20260330-012`](../../../../changelog/CR-20260330-012-s8-p8-semantic-token-baseline.yaml) |

## L1 / L2 / L3 映射

| 层级 | 标识 |
|------|------|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `page-horizontal-quality` |
