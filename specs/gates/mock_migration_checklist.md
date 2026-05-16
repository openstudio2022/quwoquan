# Mock / Repository 迁移勾选表（后续整改）

> 与 [`mock_production_separation_backlog.md`](mock_production_separation_backlog.md) 配套；**运行时策略**见下文 R1/R2。  
> **契约包**：[`packages/quwoquan_cloud_contracts`](../../packages/quwoquan_cloud_contracts/)（首批 Circle + Content 抽象）。

---

## 运行时策略（评审结论）

| 选项 | 说明 | 当前默认 |
|------|------|----------|
| **R1** | 应用进程内仅 `Remote*`；`Mock*` 仅 `flutter test` | 未采纳 |
| **R2** | 保留 `AppDataSourceMode` 切换；内嵌实现可经 `packages/quwoquan_cloud_mock`（后续）与 `test/` 镜像协同 | **推荐**（与离线内嵌、现有 [`main_prod.dart`](../../quwoquan_app/lib/main_prod.dart) 锁定 Remote 并存） |

**结论**：在完全迁入 `test/` 前，**保留**应用内 Mock/Remote 切换；商店/正式构建使用 `-t lib/main_prod.dart` + `APP_DATA_SOURCE=remote`（见 [`main_prod.dart`](../../quwoquan_app/lib/main_prod.dart)）。后续若将 `Mock*` 物理迁入 `test/`，必须引入 **R2** 包或 **R1** 并移除应用内 mock 分支。

---

## CI 基线（迁移回归对比）

在结构性迁移 PR 前后于仓库根执行并归档日志：

```bash
(cd quwoquan_app && flutter pub get && dart analyze --fatal-infos)
(cd quwoquan_app && flutter test test/cloud/circle/contract/ test/cloud/content/ -r expanded)
python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py
make verify-app-mock-isolation
```

---

## Mock*Repository 类清单（迁移时勾选）

| 域 | 类名 | 迁入 test/ 镜像 | 备注 |
|----|------|-----------------|------|
| Circle | `MockCircleRepository` | [ ] | [`circle_repository.dart`](../../quwoquan_app/lib/cloud/services/circle/circle_repository.dart) |
| Content | `MockContentRepository` | [ ] | [`content_repository.dart`](../../quwoquan_app/lib/cloud/services/content/content_repository.dart) |
| RTC | `MockRtcRepository` | [ ] | [`rtc_repository.dart`](../../quwoquan_app/lib/cloud/services/rtc/rtc_repository.dart) |
| Auth | `MockAuthRepository` | [ ] | [`auth_repository.dart`](../../quwoquan_app/lib/cloud/services/user/auth_repository.dart) |
| Invite | `MockInviteRepository` | [ ] | [`invite_repository.dart`](../../quwoquan_app/lib/cloud/services/user/invite_repository.dart) |
| User | `MockUserRepository` | [ ] | [`user_repository.dart`](../../quwoquan_app/lib/cloud/services/user/user_repository.dart) |
| UserProfile | `MockUserProfileRepository` | [ ] | [`user_profile_repository.dart`](../../quwoquan_app/lib/cloud/services/user/user_profile_repository.dart) |
| Chat | `MockChatRepository` | [ ] | [`chat_repository_mock.dart`](../../quwoquan_app/lib/cloud/services/chat/mock/chat_repository_mock.dart) |
| Assistant | `MockAssistantRepository` | [ ] | [`assistant_repository.dart`](../../quwoquan_app/lib/cloud/services/assistant/assistant_repository.dart) |
| Homepage | `MockHomepageRepository` | [ ] | [`entity_repository.dart`](../../quwoquan_app/lib/cloud/services/entity/entity_repository.dart) |
| Integration | `MockIntegrationRepository` | [ ] | [`integration_repository.dart`](../../quwoquan_app/lib/cloud/services/integration/integration_repository.dart) |
| Behavior | `MockBehaviorRepository` | [ ] | [`behavior_repository.dart`](../../quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart) |
| ContentInteraction | `MockContentInteractionRepository` | [ ] | [`content_interaction_repository.dart`](../../quwoquan_app/lib/cloud/services/content/content_interaction_repository.dart) |
| Block | `MockBlockRepository` | [ ] | [`block_repository.dart`](../../quwoquan_app/lib/cloud/services/user/block_repository.dart) |
| Report | `MockReportRepository` | [ ] | [`report_repository.dart`](../../quwoquan_app/lib/cloud/services/content/report_repository.dart) |
| KeywordBlock | `MockKeywordBlockRepository` | [ ] | [`keyword_block_repository.dart`](../../quwoquan_app/lib/cloud/services/user/keyword_block_repository.dart) |
| RelationshipCapability | `MockRelationshipCapabilityRepository` | [ ] | [`relationship_capability_repository.dart`](../../quwoquan_app/lib/cloud/services/user/relationship_capability_repository.dart) |
| CallSettings | `MockCallSettingsRepository` | [ ] | [`call_settings_repository.dart`](../../quwoquan_app/lib/cloud/services/user/call_settings_repository.dart) |
| AppearanceSettings | `MockAppearanceSettingsRepository` | [ ] | [`appearance_settings_repository.dart`](../../quwoquan_app/lib/cloud/services/user/appearance_settings_repository.dart) |
| Greeting | `MockGreetingRepository` | [ ] | [`greeting_repository.dart`](../../quwoquan_app/lib/cloud/services/user/greeting_repository.dart) |
| OpsVisit | `MockOpsVisitRepository` | [ ] | [`ops_visit_repository.dart`](../../quwoquan_app/lib/cloud/services/ops/ops_visit_repository.dart) |
| OpsEvent | `MockOpsEventRepository` | [ ] | [`ops_event_repository.dart`](../../quwoquan_app/lib/cloud/services/ops/ops_event_repository.dart) |
| AppContent | `MockAppContentRepository` | [ ] | [`app_content_repository_mock.dart`](../../quwoquan_app/lib/cloud/services/app_content/app_content_repository_mock.dart) |

**AppContentRepository**（[`app_content_repository.dart`](../../quwoquan_app/lib/core/services/app_content_repository.dart)）为应用级原型入口，迁移时需单独评估。

---

## 相关文档

- [`mock_test_separation_roadmap.md`](mock_test_separation_roadmap.md)（波次与门禁）
- [`mock_data_cloud_integration_policy.md`](mock_data_cloud_integration_policy.md)
- 契约包：[`packages/quwoquan_cloud_contracts/README.md`](../../packages/quwoquan_cloud_contracts/README.md)
