# Production Mock / Repository 清零台账

> 与 [`mock_production_separation_backlog.md`](mock_production_separation_backlog.md) 配套。
> 本表只登记必须从 production source 删除的历史类，不是目标接口清单；新增条目即门禁失败。
> **契约包**：[`quwoquan_app/packages/quwoquan_cloud_contracts`](../../quwoquan_app/packages/quwoquan_cloud_contracts/)。

---

## 唯一运行时策略

production composition 只装配 generated typed client 对应的细粒度
`*CommandWriter/*Query` Facet 与 Remote adapter；独立 alpha/test runner 才能依赖
`packages/quwoquan_cloud_mock`。`AppContent` 入口已经删除；其余应用内
Mock/Remote 切换和 Repository 均为待删除输入。`kReleaseMode`、dart-define、allowlist 和
tree-shaking 不能替代 dependency、kernel/AOT 与 SBOM 的物理隔离证明。

---

## CI 基线（迁移回归对比）

在结构性迁移 PR 前后于仓库根执行并归档日志：

```bash
(cd quwoquan_app && flutter pub get && dart analyze --fatal-infos)
(cd quwoquan_app && flutter test test/local_contract/cloud/circle/contract/ test/local_contract/cloud/content/ -r expanded)
python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py
make verify-app-mock-isolation
```

---

## 历史 Mock 类删除清单

| 域 | 类名 | 已从 production 删除 | 历史位置 |
|----|------|-----------------|------|
| Circle | `MockCircleRepository` | [ ] | [`circle_repository.dart`](../../quwoquan_app/lib/cloud/services/circle/circle_repository.dart) |
| Content | `MockContentRepository` | [ ] | [`content_repository.dart`](../../quwoquan_app/lib/cloud/services/content/content_repository.dart) |
| RTC | `MockRtcRepository` | [ ] | [`rtc_repository.dart`](../../quwoquan_app/lib/cloud/services/rtc/rtc_repository.dart) |
| Invite | `MockInviteRepository` | [x] | deleted with unused `InviteRepository`/`RemoteInviteRepository` provider path; no compatibility alias |
| User | `MockUserRepository` | [ ] | [`user_repository.dart`](../../quwoquan_app/lib/cloud/services/user/user_repository.dart) |
| UserProfile | `MockUserProfileRepository` | [ ] | [`user_profile_repository.dart`](../../quwoquan_app/lib/cloud/services/user/user_profile_repository.dart) |
| Chat | `MockChatRepository` | [ ] | [`chat_repository_mock.dart`](../../quwoquan_app/lib/cloud/services/chat/mock/chat_repository_mock.dart) |
| Assistant | `MockAssistantRepository` | [ ] | [`assistant_repository.dart`](../../quwoquan_app/lib/cloud/services/assistant/assistant_repository.dart) |
| Homepage | `MockHomepageRepository` | [ ] | [`entity_repository.dart`](../../quwoquan_app/lib/cloud/services/entity/entity_repository.dart) |
| Behavior | `MockBehaviorRepository` | [ ] | [`behavior_repository.dart`](../../quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart) |
| Block | `MockBlockRepository` | [ ] | [`block_repository.dart`](../../quwoquan_app/lib/cloud/services/user/block_repository.dart) |
| KeywordBlock | `MockKeywordBlockRepository` | [ ] | [`keyword_block_repository.dart`](../../quwoquan_app/lib/cloud/services/user/keyword_block_repository.dart) |
| RelationshipCapability | `MockRelationshipCapabilityRepository` | [ ] | [`relationship_capability_repository.dart`](../../quwoquan_app/lib/cloud/services/user/relationship_capability_repository.dart) |
| CallSettings | `MockCallSettingsRepository` | [ ] | [`call_settings_repository.dart`](../../quwoquan_app/lib/cloud/services/user/call_settings_repository.dart) |
| AppearanceSettings | `MockAppearanceSettingsRepository` | [ ] | [`appearance_settings_repository.dart`](../../quwoquan_app/lib/cloud/services/user/appearance_settings_repository.dart) |
| Greeting | `MockGreetingRepository` | [ ] | [`greeting_repository.dart`](../../quwoquan_app/lib/cloud/services/user/greeting_repository.dart) |
| OpsVisit | `MockOpsVisitRepository` | [ ] | [`ops_visit_repository.dart`](../../quwoquan_app/lib/cloud/services/ops/ops_visit_repository.dart) |
| OpsEvent | `MockOpsEventRepository` | [ ] | [`ops_event_repository.dart`](../../quwoquan_app/lib/cloud/services/ops/ops_event_repository.dart) |
| UserSync | `MockUserSyncRepository` | [ ] | [`user_sync_repository.dart`](../../quwoquan_app/lib/cloud/services/user/user_sync_repository.dart) |
| HomepageIntroduction | `MockHomepageIntroductionRepository` | [ ] | [`entity_introduction_repository.dart`](../../quwoquan_app/lib/cloud/services/entity/entity_introduction_repository.dart) |
| Intersection | `MockIntersectionRepository` | [ ] | [`intersection_repository.dart`](../../quwoquan_app/lib/cloud/services/content/intersection_repository.dart) |
| RealtimeConnection | `MockRealtimeConnectionDelegate` | [x] | deleted; alpha replacement is owned by `runners/alpha` |
| RealtimeEventCatalog | `MockRealtimeEventCatalog` | [x] | deleted; fixture catalog is alpha/test-only |
| Tag | `MockTagRepository` | [ ] | [`tag_repository_mock.dart`](../../quwoquan_app/lib/cloud/services/tag/tag_repository_mock.dart) |
| Footprint | `MockFootprintRepository` | [ ] | [`footprint_repository.dart`](../../quwoquan_app/lib/cloud/services/content/footprint_repository.dart) |
| ContactDiscovery | `MockContactDiscoveryRepository` | [ ] | [`contact_discovery_repository.dart`](../../quwoquan_app/lib/cloud/services/user/contact_discovery_repository.dart) |
| FollowingSubject | `MockFollowingSubjectRepository` | [ ] | [`following_subject_repository.dart`](../../quwoquan_app/lib/cloud/services/user/following_subject_repository.dart) |

`AppContentRepository`、`RemoteAppContentRepository`、`MockAppContentRepository`
与 `appContentRepositoryProvider` 已于 2026-07-15 同批删除；`AppDataSourceMode`
归位到 `core/di/app_data_source_mode.dart`，没有保留 barrel、alias 或空 Remote。

未完成条目的类名集合必须与 `lib/cloud` 的 `class Mock*` 扫描结果完全相等；新增 Mock
不得通过补表长期存在，只允许在同一原子迁移中进入 mock package 并从 production
source tree 删除。

---

## 相关文档

- [`mock_test_separation_roadmap.md`](mock_test_separation_roadmap.md)（波次与门禁）
- [`mock_data_cloud_integration_policy.md`](mock_data_cloud_integration_policy.md)
- 契约包：[`quwoquan_app/packages/quwoquan_cloud_contracts/README.md`](../../quwoquan_app/packages/quwoquan_cloud_contracts/README.md)
