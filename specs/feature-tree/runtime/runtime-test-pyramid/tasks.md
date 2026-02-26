# Test Pyramid Enforcement — 任务

顺序：Gate 绑定 → L2 存储修复 → L1b/c 端侧补齐 → L3 runner → L4 Patrol

---

## P0 — Gate 绑定（解锁最高优先级卡点）

- [ ] T01: `quwoquan_service/scripts/gate.sh` 末尾增加 `go test ./services/content-service/... -count=1`
- [ ] T02: `scripts/gate_repo.sh` 的 `run_app()` 移除 `QWQ_GATE_TESTS=1` 跳过条件，flutter test 始终执行
- [ ] T03: `gate.sh` 增加 contract.yaml go_func 存在性检查（对每个 `go_func: TestXxx`，检查对应 Go 测试文件中函数存在）
- [ ] T04: `gate.sh` 增加 e2e.yaml `patrol_flow` 引用文件存在性检查（warn 级别，不 fail）
- [ ] T05: `Makefile`（service）新增 `test-contract` target：`go test ./services/.../... -v -count=1 -run Contract`

---

## P0 — L2 Cloud Contract 修复（testcontainers）

- [ ] T06: 创建 `services/content-service/tests/testmain_test.go`，使用 `runtime/testinfra` 启动 testcontainers mongo:7 + miniredis
- [ ] T07: 将 `content_handler_test.go` 中 `persistence.NewPostStore(DefaultSeedPosts())` 替换为 testcontainers-backed MongoDB store
- [ ] T08: 按 `contract.yaml` `go_func` 逐一实现缺失的 Go 测试函数：
  - `TestCreatePostAggregate`
  - `TestCreatePostAllTypes`
  - `TestGetPostSuccess`
  - `TestGetPostNotFound`
  - `TestListFeedWithPagination`
  - `TestWritableFieldsEnforced`
  - `TestPostCreatedEventPublished`（EventSpy 验证）
  - `TestLikePost` / `TestFavoritePost` / `TestReportPost`
  - `TestPostNotFoundError` / `TestRateLimitedError`

---

## P1 — L1b Widget Tests（flutter_test + MockRepository）

- [ ] T09: 创建 `test/features/content/widgets/photo_post_card_widget_test.dart`
  - 断言：`show_author_avatar=true` → 头像可见
  - 断言：likeButton tap → Notifier state.likeCount +1（乐观）
- [ ] T10: 创建 `test/features/content/widgets/video_post_card_widget_test.dart`
  - 断言：视频封面渲染（coverUrl 不为 null 时）
  - 断言：durationMs 转 "mm:ss" 显示正确
- [ ] T11: 创建 `test/features/content/widgets/comment_input_bar_widget_test.dart`
  - 断言：空文本时 submit 按钮 disabled
  - 断言：enterText 后按钮 enabled

---

## P1 — L1c Journey Tests（多屏旅程）

- [ ] T12: 创建 `test/features/content/journeys/discovery_to_detail_journey_test.dart`
  - 旅程：`DiscoveryPage` → tap PhotoCard → `PhotoDetailPage` 加载
  - 断言：GoRouter extra 传参正确（postId 在详情页可见）
- [ ] T13: 创建 `test/features/content/journeys/like_optimistic_rollback_journey_test.dart`
  - 旅程：tap likeButton → likeCount +1 → MockRepo throw RateLimitException → 回滚
  - 断言：Toast 显示 `ContentErrorMessages.zh[rateLimited]`
  - 断言：likeCount 回到原值
- [ ] T14: 创建 `test/features/content/journeys/comment_post_journey_test.dart`
  - 旅程：`PhotoDetailPage` → tap CommentInputBar → enterText → tap Submit
  - 断言：`MockContentRepository.createComment()` 被调用 1 次
  - 断言：评论列表 item count +1，commentCount 文本 +1

---

## P2 — L3 API Contract Runner

- [ ] T15: 在 `quwoquan_app/test/cloud/content/` 创建 `api_contract_runner.dart`，使用 `package:http` 打 staging API
- [ ] T16: 实现 `e2e.yaml[test_type: api_contract]` 对应的 Dart 测试：
  - `discovery_feed_load_and_render` → GET `/v1/content/feed?type=image`，assert PhotoPostDto 解析通过
  - `behavior_batch_report_reaches_service` → POST `/v1/content/behaviors`，assert 204
  - `feed_cursor_pagination_end_to_end` → 两次分页 GET，assert 无重叠 item
  - `error_state_displayed_correctly` → mock server 返回 post_not_found，assert CloudErrorMapper 映射
- [ ] T17: `Makefile`（根目录）新增 `test-api-contract` target（需设置 `STAGING_BASE_URL`）

---

## P3 — L4 Patrol E2E（真实设备）

- [ ] T18: `quwoquan_app/pubspec.yaml` 添加 `patrol: ^3.x` 和 `integration_test` 依赖
- [ ] T19: 创建 `lib/core/test_keys.dart`，声明关键 Widget 的 Key 常量
  - `TestKeys.photoPostCard`、`TestKeys.likeButton`、`TestKeys.commentInputBar`、`TestKeys.submitCommentButton`
- [ ] T20: 在 PostCard / CommentInputBar 等 Widget 打上 `Key(TestKeys.xxx)`
- [ ] T21: 创建 `test/patrol/content/discovery_feed_patrol_test.dart`（对应 e2e.yaml `discovery_feed_load_and_render`）
- [ ] T22: 创建 `test/patrol/content/like_post_patrol_test.dart`（对应 `like_post_realtime`）
- [ ] T23: 创建 `test/patrol/content/comment_post_patrol_test.dart`（对应 `comment_on_post_journey`）
- [ ] T24: 配置 Firebase Test Lab CI job（`.github/workflows/e2e.yaml`）

---

## 规划任务（后续迭代）

- [ ] codegen_app_metadata 读取 `mock.yaml[widget_scenarios]` 生成 `_generated_widget_test.dart` 骨架
- [ ] gate 检查 mock.yaml 中每个有 `dart_func` 字段的 scenario 都有对应 Go/Dart 测试函数
- [ ] 覆盖率门禁：L1 总体 >80%，L2 per-endpoint 100%
