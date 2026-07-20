# `test/local_contract/cloud/services/` — 与 `lib/cloud/services/` 路径镜像

迁移 `Mock*Repository` 时，在此目录下保持与 `lib` **相同的相对路径**（例如 `circle/circle_repository_mock.dart`），便于对照与 code review。

当前多数存量实现仍在 `lib/`；[`repository_mock_reexports.dart`](repository_mock_reexports.dart) 统一导出非生产替身，供测试逐步改用单一入口。

已完成物理迁移（production `lib/**` 不可达）：

- assistant：[`assistant_facets_mock.dart`](assistant_facets_mock.dart)（`AlphaAssistantFacets` + 强类型 fixture）；provider 绑定见 [`assistant_facet_overrides.dart`](assistant_facet_overrides.dart)。
- chat：状态与 fixture 解析位于 `quwoquan_cloud_mock` 的 `AlphaChatStateEngine`；alpha runner 的 `alpha_chat_repository.dart` 仅做 App DTO 映射，测试侧由 `generate_chat_test_adapter.py` 生成同源 mapper，`verify_chat_mock_remote_parity.py` 阻断漂移与第二状态。
