# 五栏小趣收口验证矩阵

## T1 静态与契约

- 规格旧口径：`群组 / 趣聊 / assistant_tab_page_widget_test` 已从本轮触达 specs 中清理。
- entity seed：`entity_scenarios.json` 已包含 5 所大学与 3 个旅行摄影主页样本。
- recommendation runtime：`FeedTopic / FeedHomepage / FeedSearch` 与 `feedRequestId / surface / homepageId / topicId` 归因字段已加测试。

## T2 Widget / 端侧旅程

- `flutter test test/ui/user/pages/my_profile_page_test.dart --plain-name "我的页顶栏展示全局搜索与小趣入口"`
- `flutter test test/ui/circle/widgets/circles_page_widget_test.dart --plain-name "展示推荐/我的/校园/旅行摄影四场景入口"`
- `flutter test test/components/comment_system/comment_viewer_modal_widget_test.dart --plain-name "评论区支持 @小趣 快捷入口与小趣回复卡"`
- `flutter test test/components/input/customizable_chat_input_bar_test.dart --plain-name "群聊输入区可插入 @小趣 上下文 mention"`
- `flutter test test/ui/chat/widgets/chat_page_widget_test.dart --plain-name "@小趣分组展示评论和群聊小趣回复投影"`
- `flutter test test/ui/chat/widgets/chat_page_widget_test.dart --plain-name "提醒分组展示实体更新和圈子摘要投影"`

## T3 服务 / Ops

- `go test ./runtime/recommendation -run 'TestFeedTypesCoverFiveTabXiaoquSurfaces|TestRecallRequestCarriesAttributionContext'`
- `npm test` in `apps/ops-portal`

## T4 Beta 状态

- `make beta-up -> make beta-status -> make beta-down` 已执行。
- `product-ops` 与 `ops-portal` health 通过；gateway 依赖 fallback Mongo/Redis，本机 Docker daemon 未运行，触发 `Cannot connect to the Docker daemon at unix:///Users/zhaoyuxi/.colima/default/docker.sock`，因此 T4 真机完整旅程需在 Docker/Colima 可用后复跑。
