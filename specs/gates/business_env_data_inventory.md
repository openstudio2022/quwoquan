# 业务对象三环境共用测试数据清单

本文档是 alpha/beta/gamma 共用测试数据的页面到业务对象依赖清单。后续新增页面、Repository 或人工 beta 场景时，必须先更新对应 contract fixture 与 seed manifest，再实现业务代码或测试。

## 环境口径

| 环境 | App 数据源 | 云侧数据源 | 用途 |
|---|---|---|---|
| alpha | contract-seeded MockRepository | 单服务自身 reset+seed 测试存储 | 端侧离线 mock 与云侧单服务接口验证 |
| beta | RemoteRepository | 本地服务按 `app_beta_seed_manifest.json` reset+seed | 本地端云联调与人工测试 |
| gamma | RemoteRepository | 云侧集成环境按 `app_gamma_seed_manifest.json` reset+seed | 云侧集成验证 |
| prod | 真实用户数据 | 真实用户数据 | 正式发布 |
| prod-gray | 同一个生产 App 包 | 云侧灰度策略/配置版本 | 灰度，不是单独 App 包 |

### 多实例 / 单套补充约束

- 端侧 `alpha` / `beta` / `gamma` 可在**不同模拟器**并行运行多个实例，但每个实例都必须显式绑定 `device-id`。
- `beta` 云侧数据源只允许一套本地服务栈；重新启动 beta 时必须先停止旧实例并回收 `18080/18087/18088` 等固定端口。
- `gamma` 云侧数据源只允许一套 ECS gamma 或一套 local-gamma mirror；并行只体现在多个端侧实例同时访问同一套 gamma。
- 不得为端侧多实例再复制一套 beta/gamma seed 数据；仍以既有 `app_beta_seed_manifest.json` / `app_gamma_seed_manifest.json` 为唯一真相源。

## 页面依赖矩阵

| 范围 | 页面 | 业务对象 | seedRefs |
|---|---|---|---|
| App 壳 | `quwoquan_app/lib/app/shell/main_app_shell.dart`、`bottom_navigation.dart`、`quwoquan_app/lib/ui/welcome/pages/welcome_screen.dart` | `user.profile`、`notification.app_message`、`chat.conversation` | `user_profile_core`、`notification_core`、`chat_core` |
| 首页/发现 | `home_page.dart`、`discovery_page.dart`、内容详情/媒体页、搜索页 | `content.post`、`content.feed`、`content.comment`、`content.reaction`、`user.profile_snapshot` | `home_feed_core`、`content_discovery_core`、`content_detail_core`、`search_core` |
| 圈子/群组 | `home_circles_hub_page.dart`、`circles_page.dart`、`circle_detail_page.dart`、圈子设置/统计页 | `circle.circle`、`circle.group`、`circle.member`、`circle.file`、`chat.conversation` | `circle_core`、`circle_home_feed_core`、`circle_profile_core`、`circle_group_chat_link_core` |
| 趣信 | `chat_page.dart`、`chat_detail_page.dart`、`chat_conversation_page.dart`、`chat_settings_page.dart`、群管理页 | `chat.conversation`、`chat.message`、`chat.member`、`chat.user_state`、`chat.group_settings`、`chat.contact_row` | `chat_core`、`chat_settings_core`、`chat_contacts_core`、`chat_group_flow_core` |
| 主页/用户 | `my_profile_page.dart`、`other_profile_page.dart`、`edit_profile_page.dart`、persona/共鸣/统计/评论页 | `user.profile`、`user.profile_subject`、`user.persona`、`user.relationship_capability`、`content.post`、`circle.circle` | `user_profile_core`、`persona_core`、`profile_feed_core`、`relationship_core` |
| 实体主页 | `homepage_detail_page.dart`、`homepage_picker_page.dart`、`suggest_homepage_page.dart`、认领/维护/状态报告页 | `entity.homepage`、`entity.homepage_claim`、`entity.homepage_suggestion`、`entity.homepage_status_report` | `entity_homepage_core`、`entity_claim_core`、`entity_picker_core` |
| 创作入口 | `create_page.dart`、`article_typography_page.dart`、发布位置/圈子/主页选择页、`video_editor_page.dart` | `content.draft`、`content.publish_payload`、`circle.circle`、`integration.location_poi`、`entity.homepage` | `publish_core`、`location_poi_core`、`circle_core`、`entity_picker_core` |
| 助手 | 助手会话、找私助、技能中心、管理/设置/回放页 | `assistant.conversation`、`assistant.turn`、`assistant.stream_event`、`assistant.skill`、`assistant.skill_subscription`、`notification.app_message` | `assistant_p0_core`、`skill_management_core`、`notification_core` |
| RTC/设置 | 来电/去电/语音/视频页、参与人选择、设置/开发者设置页 | `rtc.call_session`、`rtc.participant`、`chat.member`、`user.call_settings`、`user.appearance_settings`、`ops.event` | `rtc_core`、`chat_contacts_core`、`settings_core` |

## 强制规则

- 测试数据按业务对象组织，页面只引用 scenario id 或 seedRef。
- `alpha` 端侧 mock、`beta/gamma` 云侧 seed 必须使用同一业务对象 ID。
- 人工 beta 数据必须进入 fixture 与 `app_beta_seed_manifest.json`，不得在脚本或数据库临时追加。
- beta / gamma 服务端不允许因端侧多实例而新增第二套本地/云侧栈；任何“切换”都必须是 stop-then-start。
- 生产 App 只有一个包，禁止独立 `app-prod-gray`；灰度由应用市场分发策略、端侧上下文和云侧策略控制。
- `prod/prod-gray` 禁止 `test_fixtures`、`seedRefs`、`requiresSeedReset`、`mock` 数据源。

## flutter run 页面真实数据链路

| 页面面 | alpha 数据源 | beta/gamma 数据源 | 必测路径/方法 |
|---|---|---|---|
| 首页关注/精选 | `MockContentRepository` 从 `content_discovery_core` 初始化 | `RemoteContentRepository.listDiscoveryFeedPage` | `GET /v1/content/feed` |
| 首页圈子/圈子列表 | `MockCircleRepository` 从 `circle_core` 与 `circle_home_feed_core` 初始化 | `RemoteCircleRepository.listCircles` + `listHomeCircleDiscoveryFeed` 聚合圈子 feed | `GET /v1/circles`、`GET /v1/circles/{circleId}/feed` |
| 趣信消息 | `MockChatRepository` 从 `chat_core` 初始化 | `RemoteChatRepository.listInbox/listConversations/listMessages/listMembers` | `GET /v1/chat/inbox`、`GET /v1/chat/conversations`、`GET /v1/chat/conversations/{conversationId}/messages` |
| 趣信联系人 | `chat_contacts_core` | `RemoteChatRepository.listContacts`，圈子/趣群 tab 由 `ListCircles/ListConversations` 派生 | `GET /v1/chat/contacts`、`GET /v1/circles`、`GET /v1/chat/conversations` |
| 我的主页/作者主页 | `MockUserProfileRepository` 从 `user_profile_core/profile_feed_core` 初始化 | `RemoteUserProfileRepository`，当前用户由环境包 `runtime.currentUserId` 注入 | `GET /v1/me`、`GET /v1/user/{id}`、`GET /v1/content/profile-subjects/{id}/posts`、`GET /v1/users/{id}/works`、`GET /v1/users/{id}/circles` |

**并行运行说明**：

- `alpha` / `beta` / `gamma` 的页面真实数据链路允许被多个端侧实例并发消费。
- `beta/gamma` 的 RemoteRepository 不得通过“第二套本地服务栈”来实现并行，而应共享同一套 remote endpoint。

## 收口任务清单

| 任务 | 目标 | 验收 |
|---|---|---|
| 页面数据链路审计 | 找清 `flutter run` 首页、趣信、主页、圈子显示数据来自哪个 Provider/Repository/API | 本文档 `flutter run 页面真实数据链路` 表完整覆盖 |
| Remote 空桩清理 | beta 不得在关键页面返回空桩 | `listHomeCircleDiscoveryFeed`、趣信联系人圈子/趣群 tab 均有远端派生数据 |
| beta 预置网关补齐 | 人工 beta 启动时主要页面路径都有 fixture 响应 | `scripts/start_app_beta_manual.sh --skip-app` 健康检查覆盖上述路径 |
| 三环境共用测试 | alpha mock 与 beta remote 使用同一 fixture ID；gamma 暂缓远端执行但保留 manifest 与路径约束 | `make test-app-alpha-seed`、`flutter test test/cloud/services/business_beta_remote_repository_test.dart`、`python3 quwoquan_app/scripts/env/run_app_alpha_beta_seed_matrix.py` |
