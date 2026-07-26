# 测试侧 Cloud 替身

本目录只保存 production `lib/**` 不可达的测试适配与统一 re-export。测试通过 [`repository_mock_reexports.dart`](repository_mock_reexports.dart) 引用替身，不从业务代码导入 Mock。

- assistant：[`assistant_facets_mock.dart`](assistant_facets_mock.dart) 提供 `AlphaAssistantFacets` 与强类型 fixture，provider 覆盖位于 [`assistant_facet_overrides.dart`](assistant_facet_overrides.dart)。
- chat：状态和 fixture 解析由 `quwoquan_cloud_mock` 的 `AlphaChatStateEngine` 持有；测试 mapper 由 `generate_chat_test_adapter.py` 生成，`verify_chat_mock_remote_parity.py` 阻断 Mock/Remote 语义漂移。
