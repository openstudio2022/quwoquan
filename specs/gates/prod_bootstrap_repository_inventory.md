# 正式入口（main_prod）与 Repository / Mock 依赖清单（P4a）

> **目的**：为「物理剥离 Mock 编译单元」排期；与 [`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md) §5、§9 一致。  
> **现状（2026-03-30）**：`main_prod` **不**再 import `lib/main.dart`，经 [`app_bootstrap.dart`](../../quwoquan_app/lib/app_bootstrap.dart) 启动，并对 [`appDataSourceModeProvider`](../../quwoquan_app/lib/core/services/app_content_repository.dart) 做 **恒 Remote + setMode 忽略非 remote** 覆盖；**仍**通过 `quwoquan_app_shell` → `quwoquan_core` → [`app_providers.dart`](../../quwoquan_app/lib/core/providers/app_providers.dart) 链接到各 `Mock*Repository` 类型（AOT 体积目标见策略 §5.1 说明）。

## 1. `app_providers.dart` 中按数据源分支的 Repository Provider（需 prod 专用图时逐条拆）

| Provider | Remote 类型 | Mock 类型 |
|----------|-------------|-----------|
| `assistantRepositoryProvider` | `RemoteAssistantRepository` | `MockAssistantRepository` |
| `contentRepositoryProvider` | `RemoteContentRepository` | `MockContentRepository` |
| `homepageRepositoryProvider` | `RemoteHomepageRepository` | `MockHomepageRepository` |
| `integrationRepositoryProvider` | `RemoteIntegrationRepository` | `MockIntegrationRepository` |
| `chatRepositoryProvider` | `RemoteChatRepository`（[`remote/chat_repository_remote.dart`](../../quwoquan_app/lib/cloud/services/chat/remote/chat_repository_remote.dart)） | `MockChatRepository` |
| `userRepositoryProvider` | `RemoteUserRepository` | `MockUserRepository` |
| `authRepositoryProvider` | `RemoteAuthRepository` | `MockAuthRepository` |
| `inviteRepositoryProvider` | `RemoteInviteRepository` | `MockInviteRepository` |
| `behaviorRepositoryProvider` | `RemoteBehaviorRepository` | `MockBehaviorRepository` |
| `userProfileRepositoryProvider` | `RemoteUserProfileRepository` | `MockUserProfileRepository` |
| `contentInteractionRepositoryProvider` | `RemoteContentInteractionRepository` | `MockContentInteractionRepository` |
| `blockRepositoryProvider` | `RemoteBlockRepository` | `MockBlockRepository` |
| `reportRepositoryProvider` | `RemoteReportRepository` | `MockReportRepository` |
| `keywordBlockRepositoryProvider` | `RemoteKeywordBlockRepository` | `MockKeywordBlockRepository` |
| `circleRepositoryProvider` | `RemoteCircleRepository` | `MockCircleRepository` |
| `searchRepositoryProvider` | `RemoteSearchRepository` | `MockSearchRepository` |
| `rtcRepositoryProvider` | `RemoteRtcRepository` | `MockRtcRepository` |
| `callSettingsRepositoryProvider` | `RemoteCallSettingsRepository` | `MockCallSettingsRepository` |
| `greetingRepositoryProvider` | `RemoteGreetingRepository` | `MockGreetingRepository` |

另：`dataServiceProvider`、`appContentRepositoryProvider`（见 [`app_content_repository_provider.dart`](../../quwoquan_app/lib/cloud/services/app_content/app_content_repository_provider.dart)）等组合门面，同理依赖 `AppDataSourceMode`。

## 2. 推荐后续切片（P4b+）

1. 将上表 Provider **按域拆文件**（`providers/repositories/chat_providers.dart` 等），每文件仅 `import` 对应 `remote/*.dart` + `mock/*.dart`。
2. 新增 `app_providers_prod.dart` **仅** aggregate Remote 实现 + 共享非 Repository Provider；`main_prod` / `app_bootstrap` 的 import 图只指向 prod aggregate（**不** import `Mock*` 源文件）。
3. 可选：`quwoquan_core.dart` 拆为 `quwoquan_core_public.dart`（无 `app_providers`）供 shell 使用，避免单 barrel 拉全图。

## 3. 验证命令

- `make verify-app-mock-isolation`
- `make verify-app-lib-test-only-symbols`
- `flutter build macos -t lib/main_prod.dart --dart-define=APP_DATA_SOURCE=remote`（与 CI 一致）
