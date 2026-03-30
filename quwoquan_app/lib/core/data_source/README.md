# core/data_source — 数据源模式（渐进迁入）

目标：将 **`AppDataSourceMode`**、dart-define / SharedPreferences 持久化、开发者开关可见性策略从 [`app_content_repository.dart`](../services/app_content_repository.dart) 与 [`app_providers.dart`](../providers/app_providers.dart) **渐进迁入**本目录，避免与某一域 `mock/*_mock_data.dart` 同文件混写。

参见 [`specs/gates/mock_data_cloud_integration_policy.md`](../../../../specs/gates/mock_data_cloud_integration_policy.md) **§9.1** 建议文件名：`app_data_source_mode.dart`、`data_source_policy.dart`。

**当前**：类型与 `Notifier` 仍在 `app_content_repository.dart`；本目录仅占位文档，避免无说明空目录。
