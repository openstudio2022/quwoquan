# 测试代码分离 — 波次路线图（仓库真相源）

与 [`mock_migration_checklist.md`](mock_migration_checklist.md)、[`mock_production_separation_backlog.md`](mock_production_separation_backlog.md) 一致。

## 已落地（本迭代）

| 项 | 说明 |
|----|------|
| **契约包** | [`packages/quwoquan_cloud_contracts`](../../packages/quwoquan_cloud_contracts/)：`CircleRepository`、`ContentRepository`（含 `CommentPage`、`kFeedSortRecommend`） |
| **组合根** | [`cloud_repository_binding.dart`](../../quwoquan_app/lib/core/di/cloud_repository_binding.dart) + [`app_providers.dart`](../../quwoquan_app/lib/core/providers/app_providers.dart) 使用 `cloudRepositoryImplForMode` |
| **正式入口** | 已有 [`main_prod.dart`](../../quwoquan_app/lib/main_prod.dart) 锁定 Remote |
| **门禁** | [`verify_lib_no_import_test_tree.py`](../../scripts/verify_lib_no_import_test_tree.py)，`make verify-app-lib-no-test-import`，已接入 [`gate_repo.sh`](../../scripts/gate_repo.sh) |
| **Analytics** | [`AnalyticsService.forTesting`](../../quwoquan_app/lib/analytics/analytics.dart) 按 `mode` 默认 Remote/Mock `OpsEventRepository` |

## 后续波次

1. 将其余 `*Repository` 抽象迁入 `quwoquan_cloud_contracts`。  
2. 按域将 `Mock*` 迁入 `test/cloud/services/...` 镜像（配合 R2 包或 R1）。  
3. 可选：`pubspec.release.yaml` 去掉 dev-only mock 包依赖。
