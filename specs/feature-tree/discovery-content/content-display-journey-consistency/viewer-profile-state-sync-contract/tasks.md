# viewer-profile-state-sync-contract — tasks

## Current Slice

### P1: canonical key and sync config baseline

- [x] T01: [app] 在 `post_base_dto.dart` 增加 `authorProfileSubjectId => authorId` 迁移期 canonical getter
- [x] T02: [projection] 在 `post_summary_view.dart` 使用 canonical 作者 key，并补齐 photo/video `body` 投影
- [x] T03: [metadata] 在 `contracts/metadata/_control_plane/platform/config_schema.yaml` 新增 `sys.client_state_sync.*`
- [x] T04: [codegen] 执行 `make -C quwoquan_service verify-metadata && make codegen && make codegen-app`

### P2: shared provider integration

- [x] T05: [provider] 在 `app_providers.dart` 新增 `UserRelationshipStateProvider`
- [x] T06: [provider] 在 `app_providers.dart` 新增 `PostInteractionStateProvider`
- [x] T07: [profile] 在 `profile_state_provider.dart` 让 `toggleFollow()` 同步 capability relationState 与 shared provider
- [x] T08: [viewer/feed] 在 `home_page.dart`、`works_immersive_viewer.dart` 接入 shared provider 快照与回写
- [x] T09: [route] 在 `user_profile_route_extra.dart` / `app_router.dart` 兼容 `profileSubjectId`

### P3: outbox delayed sync

- [x] T10: [config] 在 `ContentRuntimeConfigState` 解析 `client_state_sync`
- [x] T11: [provider] 在 `app_providers.dart` 新增 `ClientStateSyncOutboxNotifier`
- [x] T12: [interaction] viewer/profile follow/like/save 改为 enqueue 到 outbox
- [x] T13: [test] 新增 config / outbox / profile shared-provider 聚焦测试

## Verification

- [x] V01: `flutter test test/ui/content/post/contract/content_runtime_config_provider_test.dart test/ui/content/post/post_summary_view_test.dart test/core/providers/client_state_sync_providers_test.dart test/ui/user/providers/profile_state_provider_test.dart`
- [x] V02: `make -C quwoquan_service build && make -C quwoquan_service test-contract`
