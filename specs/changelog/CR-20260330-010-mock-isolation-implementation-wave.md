# CR-20260330-010：Mock·端云·测试编译隔离 — 实施波次 B

> 本文件为 **Markdown 登记副本**；与 `CR-20260330-010-mock-isolation-implementation-wave.yaml` 等价时以 YAML 为准（实施首 PR 可补 YAML）。

| 字段 | 值 |
|------|-----|
| id | CR-20260330-010-mock-isolation-implementation-wave |
| status | specified |
| feature_path | runtime/runtime-client-foundation/page-horizontal-quality |

## summary

在 S1–S9 横向矩阵收口之后，单独开启 **实施波次 B**：按 `mock_data_cloud_integration_policy.md` 阶段 P0–P4 与 §4.1、§9 目录目标，清空 `ui_mock_isolation_allowlist`、拆分 Remote/Mock、建立 `test/support` 与 `lib/core/data_source`、prod 入口与 Release 门控。

## artifacts

- `specs/gates/mock_data_cloud_integration_policy.md`（含 **§5.1**；基线登记见 **`CR-20260330-011`**）
- `specs/gates/ui_mock_isolation_allowlist.yaml`
- `specs/gates/lib_test_only_symbols_allowlist.yaml` + `quwoquan_app/scripts/runtime/verify_lib_no_test_only_symbols.py`
- `specs/gates/prod_bootstrap_repository_inventory.md`（P4a Mock/Remote Provider 清单）
- `quwoquan_app/lib/app_bootstrap.dart`、`quwoquan_app/lib/quwoquan_app_shell.dart`、`quwoquan_app/lib/main_prod.dart`（prod 数据源锁定）
- `quwoquan_app/lib/cloud/services/chat/chat_repository_api.dart`、`remote/chat_repository_remote.dart`、`mock/chat_repository_mock.dart`
- `quwoquan_app/test/support/**`、`quwoquan_app/lib/core/data_source/README.md`
- `quwoquan_app/test/smoke/app_bootstrap_smoke_test.dart`
- `specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/nine-session-rollout-plan.md`
- `specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/tasks.md`（**M8**）
- `specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality/plan.yaml`（**slice-6** 已合入 — §5.1 规格/流程基线）

## 与 CR-20260330-011 的分工

- **011**：冻结 §5.1 功能规格表 + Cursor/主线命令 + acceptance **A8**（文档与门禁口径）。
- **010（本 CR）**：跟踪 **B0/B2/P4** 等仍可选或后续工程切片（`test/support`、物理拆 Mock 等）。
