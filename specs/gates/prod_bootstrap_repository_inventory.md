# 正式入口（main_prod）与 Repository / Mock 依赖清单（P4a）

> **目的**：为「物理剥离 Mock 编译单元」排期；与 [`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md) §5、§9 一致。  
> **现状（2026-07-15）**：`main_prod` **不** import `lib/main.dart`，经 [`app_bootstrap.dart`](../../quwoquan_app/lib/app_bootstrap.dart) 启动；[`appDataSourceModeProvider`](../../quwoquan_app/lib/core/di/app_data_source_mode.dart) 对 `beta/gamma/prod` 固定 Remote、对未知环境启动失败。`AppContentRepository` 聚合入口已删除；其余旧 Provider 仍通过 [`app_providers.dart`](../../quwoquan_app/lib/core/providers/app_providers.dart) 链接到 `Mock*Repository`，必须继续物理剥离。

## 1. `app_providers.dart` 中按数据源分支的 Repository Provider（需 prod 专用图时逐条拆）

| Provider | Remote 类型 | Mock 类型 |
|----------|-------------|-----------|
| `assistantRepositoryProvider` | `RemoteAssistantRepository` | `MockAssistantRepository` |
| `contentRepositoryProvider` | `RemoteContentRepository` | `MockContentRepository` |
| `homepageRepositoryProvider` | `RemoteHomepageRepository` | `MockHomepageRepository` |
| `integrationRepositoryProvider` | `RemoteIntegrationRepository` | `MockIntegrationRepository` |
| `chatRepositoryCompositionProvider` | `RemoteChatRepository`（[`remote/chat_repository_remote.dart`](../../quwoquan_app/lib/cloud/services/chat/remote/chat_repository_remote.dart)） | production 无 Mock；alpha/test 共用 `quwoquan_cloud_mock` 状态引擎，test DTO mapper 由 runner mapper 生成并做 parity 校验 |
| `personaQueryProvider` / `personaCommandWriterProvider` / `profileCommandWriterProvider` | `RemotePersonaQuery` / `RemotePersonaCommandWriter` | production 无 Mock；alpha runner 使用 `AlphaPersonaFacet` |
| `behaviorRepositoryProvider` | `RemoteBehaviorRepository` | `MockBehaviorRepository` |
| `userProfileRepositoryProvider` | `RemoteUserProfileRepository` | `MockUserProfileRepository` |
| `personaRelationshipBlockWriterProvider` / `blockedListQueryProvider` | `RemotePersonaRelationshipFacet` | alpha adapter 仅位于 `quwoquan_cloud_mock` |
| `homeFeedContentReportCommandWriterProvider` / `workBrowserContentReportCommandWriterProvider` / `userProfileContentReportCommandWriterProvider` | `RemoteContentReportAdapter`（context 由各 surface Provider 固定） | `AlphaContentReportAdapter`（仅 `quwoquan_cloud_mock`，override 位于 alpha runner） |
| Circle object-level typed facet providers | Remote generated-client adapters | alpha `AlphaCircle*` typed facets only in `quwoquan_cloud_mock` |
| `searchRepositoryProvider` | `RemoteSearchRepository` | `MockSearchRepository` |
| `rtcCall*Provider` 对象级 Facet | `RemoteCall*` generated-client adapters | alpha adapters 仅位于 `quwoquan_cloud_mock` |
| `userSettingsCommandWriterProvider` / `userSettingsQueryReaderProvider` | `RemoteUserSettingsCommandWriter` / `RemoteUserSettingsQueryReader` | alpha adapter 仅位于 `quwoquan_cloud_mock` |
| `greetingRepositoryProvider` | `RemoteGreetingRepository` | `MockGreetingRepository` |

`appContentRepositoryProvider` 已删除；不得新增同类跨对象组合门面。

`authRepositoryProvider` 与 `socialAuthorizationRepositoryProvider` 已于 2026-07-15
收敛为 production Remote-only；Auth/SocialAuthorization fixture 仅由
`runners/alpha/` 显式 override，不再经 `AppDataSourceMode` 分支。

## 2. 推荐后续切片（P4b+）

1. 将上表 Provider **按域拆文件**（`providers/repositories/chat_providers.dart` 等），每文件仅 `import` 对应 `remote/*.dart` + `mock/*.dart`。
2. 新增 `app_providers_prod.dart` **仅** aggregate Remote 实现 + 共享非 Repository Provider；`main_prod` / `app_bootstrap` 的 import 图只指向 prod aggregate（**不** import `Mock*` 源文件）。
3. 可选：`quwoquan_core.dart` 拆为 `quwoquan_core_public.dart`（无 `app_providers`）供 shell 使用，避免单 barrel 拉全图。

## 3. 验证命令

- `make verify-app-mock-isolation`
- `make verify-app-lib-test-only-symbols`
- `flutter build macos -t lib/main_prod.dart --dart-define=APP_DATA_SOURCE=remote`（与 CI 一致）
