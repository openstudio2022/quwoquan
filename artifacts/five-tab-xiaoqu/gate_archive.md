# 五栏小趣收口门禁归档

## 已通过

- `make verify-app-page-horizontal-quality`
- `make verify-app-mock-isolation`
- `make verify-app-seed-manifest`
- `git diff --check`
- `bash -n scripts/beta/start_beta_stack.sh`
- `npm test` in `apps/ops-portal`
- `go test ./runtime/recommendation -run 'TestFeedTypesCoverFiveTabXiaoquSurfaces|TestRecallRequestCarriesAttributionContext'`
- `flutter test test/ui/user/pages/my_profile_page_test.dart --plain-name "我的页顶栏展示全局搜索与小趣入口"`
- `flutter test test/ui/circle/widgets/circles_page_widget_test.dart --plain-name "展示推荐/我的/校园/旅行摄影四场景入口"`
- `flutter test test/components/comment_system/comment_viewer_modal_widget_test.dart --plain-name "评论区支持 @小趣 快捷入口与小趣回复卡"`
- `flutter test test/components/input/customizable_chat_input_bar_test.dart --plain-name "群聊输入区可插入 @小趣 上下文 mention"`
- `flutter test test/ui/chat/widgets/chat_page_widget_test.dart --plain-name "@小趣分组展示评论和群聊小趣回复投影"`
- `flutter test test/ui/chat/widgets/chat_page_widget_test.dart --plain-name "提醒分组展示实体更新和圈子摘要投影"`

## 已验证入口

- `make beta-up`
- `make beta-status`
- `make beta-down`
- `scripts/beta/start_beta_stack.sh status`

## Beta 栈结果

- `make beta-up` 会写入 `.env.beta.local` 并托管 `app-beta`、`product-ops` 与 `ops-portal`。
- 本机验证中 `product-ops` 与 `ops-portal` health 均通过。
- `app-beta` 的 gateway 依赖 fallback Mongo/Redis，本机 Docker daemon 未运行：`Cannot connect to the Docker daemon at unix:///Users/zhaoyuxi/.colima/default/docker.sock`，因此 gateway health 为 pending。该问题是本机基础设施依赖未启动，不是本轮脚本或 ops-portal 编译失败。

## 未执行全量项

- 未执行全仓 `make gate` / `make gate-full`，本仓当前已有大量无关未跟踪 artifacts，且计划要求可行子集优先；本轮已覆盖 app 页面横向质量、mock 隔离、seed、ops portal、推荐契约与核心 widget 旅程。
