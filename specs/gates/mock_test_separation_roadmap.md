# 测试代码分离 — 波次路线图（仓库真相源）

与 [`mock_migration_checklist.md`](mock_migration_checklist.md)、[`mock_production_separation_backlog.md`](mock_production_separation_backlog.md) 一致。

## 已落地基线

| 项 | 说明 |
|----|------|
| **契约包** | [`quwoquan_app/packages/quwoquan_cloud_contracts`](../../quwoquan_app/packages/quwoquan_cloud_contracts/)：`CircleRepository`、`ContentRepository`（含 `CommentPage`、`kFeedSortRecommend`） |
| **组合根** | [`cloud_repository_binding.dart`](../../quwoquan_app/lib/core/di/cloud_repository_binding.dart) + [`app_providers.dart`](../../quwoquan_app/lib/core/providers/app_providers.dart) 使用 `cloudRepositoryImplForMode` |
| **正式入口** | 已有 [`main_prod.dart`](../../quwoquan_app/lib/main_prod.dart) 锁定 Remote |
| **门禁** | [`verify_lib_no_import_test_tree.py`](../../quwoquan_app/scripts/runtime/verify_lib_no_import_test_tree.py)，`make verify-app-lib-no-test-import`，已接入 [`gate_repo.sh`](../../quwoquan_ops/gate/gate_repo.sh) |
| **Analytics** | [`AnalyticsService.forTesting`](../../quwoquan_app/lib/analytics/analytics.dart) 按 `mode` 默认 Remote/Mock `OpsEventRepository` |

## 2026-07-13 商用物理隔离波次

1. 先解除 `quwoquan_cloud_contracts -> quwoquan_app` 反向依赖，让合同包成为 pure Dart。
2. 建立 `quwoquan_cloud_mock` 与独立 alpha/test runner；fixture 由 metadata seed
   manifest 构建期生成，不在设备运行时读仓库相对路径。
3. 建立 production Remote composition；production pub dependency 不引用 mock package。
4. 以 Integration/Location 验证 contract/remote/mock/DI 分层，再消费上游 Content
   Post+Report ABI，随后按对象波次迁移 34 个生产源码测试替身顶层类
   （32 个 `Mock*`、1 个 `Stub*`、1 个 `Noop*`）。
5. 每波同批删除旧 Mock/Repository/fixture/fallback 和相关 allowlist，补
   local_contract、Dart Remote api_integration 与行为型 user_acceptance。
6. clean checkout 双构建并检查 dependency graph、kernel/AOT reachability 与 SBOM；
   物理零 Mock 未证明前保持 `GATE_BLOCK`。
