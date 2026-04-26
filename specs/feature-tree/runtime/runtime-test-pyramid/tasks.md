# Test Pyramid Enforcement — 任务

顺序：Gate 绑定 → L2 存储修复 → L1b/c 端侧补齐 → L3 runner → L4 Patrol

---

## P0 — Gate 绑定（解锁最高优先级卡点）

- [x] T01: `quwoquan_service/scripts/gate.sh` 末尾增加 `go test ./services/content-service/... -count=1`
- [x] T02: `scripts/gate_repo.sh` 的 `run_app()` 移除 `QWQ_GATE_TESTS=1` 跳过条件，flutter test 始终执行（L1 路径已始终执行）
- [ ] T03: `gate.sh` 增加 contract.yaml go_func 存在性检查（对每个 `go_func: TestXxx`，检查对应 Go 测试文件中函数存在）
  - 重启条件：TestBehaviorBatchEmpty / TestCounterFlush / TestPostModerationFlow 对应服务端功能（BatchFlush / Moderation）合入 main 后；届时 3 个 pending 函数补齐，T03 检查可 enable（对应 A4 deferred → implemented）
- [x] T04: `gate.sh` 增加 e2e.yaml `patrol_flow` 引用文件存在性检查（warn 级别，不 fail）→ 已在 T38 实现
- [x] T05: `Makefile`（service）新增 `test-contract` target：`go test ./services/.../... -v -count=1 -run Contract`

---

## P0 — L2 Cloud Contract 修复（testcontainers）

- [x] T06: 创建 `services/content-service/tests/testmain_test.go`，使用 testcontainers mongo:7 + miniredis（Docker 不可用时优雅 skip）
- [x] T07: 将 `content_handler_test.go` 中 in-memory store 替换为 `persistence.MongoPostStore`
- [x] T08: 按 `contract.yaml` `go_func` 逐一实现 Go 测试函数（大部分已实现）：
  - [x] `TestCreatePostAggregate` / `TestCreatePostAllTypes`
  - [x] `TestGetPostSuccess` / `TestGetPostNotFound`
  - [x] `TestGetFeedByType` / `TestGetFeedCursorPagination`（`TestListFeedWithPagination` 等价）
  - [x] `TestPostCreatedEventPublished`（EventSpy 验证）
  - [x] `TestLikePost` / `TestFavoritePost` / `TestReportPost`
  - [x] `TestReactIdempotent` / `TestReactWithCounterStrategy` / `TestUnlikeDecrementsCounter`
  - [x] `TestGetPostNotFound`（错误码 contract）/ `TestUpdatePostForbidden`
  - [x] `TestCommentListPagination` / `TestCommentWithNotification`
  - [x] `TestBehaviorBatchReport`
  - [ ] `TestBehaviorBatchEmpty`（contract.yaml status=pending，待 P0 T03 gate 绑定时实现）
  - [ ] `TestCounterFlush`（contract.yaml status=pending，依赖 CounterFlush 服务端实现）
  - [ ] `TestPostModerationFlow`（contract.yaml status=pending，依赖 Moderation 功能）

---

## P1 — L1b Widget Tests（flutter_test + MockRepository）

> 注：实际创建路径调整为 `test/components/content/post/`（与现有 post_card_widget_test.dart 对齐）

- [x] T09: `test/components/content/post/post_card_widget_test.dart` 已存在（PhotoPostCard 覆盖）
- [x] T10: 创建 `test/components/content/post/video_post_card_widget_test.dart`（untracked，已创建）
- [x] T11: 创建 `test/components/content/post/comment_input_bar_widget_test.dart`（untracked，已创建）

---

## P1 — L1c Journey Tests（多屏旅程）

> 注：实际创建路径调整为 `test/ui/discovery/post/journeys/`（已有更丰富的 journey 测试）

- [x] T12: `test/ui/discovery/post/journeys/discovery_post_feed_load_journey_test.dart` 已存在（A1/A2 正常路径 + B1/B2 错误路径 + C1/C2 幂等边界）
- [x] T13: `test/ui/discovery/post/journeys/discovery_post_interaction_journey_test.dart` 已存在（like 乐观更新 + rollback + toast）
- [x] T14: L1c 旅程 — 评论提交完整旅程（含 MockRepo.createComment 调用验证）
  - 实现于 `test/ui/discovery/post/journeys/discovery_post_interaction_journey_test.dart`
  - dart_func: `testCommentPostJourney`（使用 testWidgets，断言 createCommentCallCount/lastCommentText/countersStubCommentCount）

---

## P2 — L3 API Contract Runner（staging HTTP）

顺序：env/infra → runner 框架 → 场景实现 → gate 绑定 → CI job

### P2-基础：环境与框架

- [x] T15: `quwoquan_app/pubspec.yaml` — `http` 已在 dependencies；`http_mock_adapter` 暂不需要（error_inject 通过 staging header 触发，不需要 mock adapter）
- [x] T16: 创建 `quwoquan_app/test/cloud/content/api_contract_runner.dart` — runner 框架
  - `setUpAll`：探测 staging 可达性（HEAD request，5s timeout），不可达则 `markTestSkipped`
  - 从 `dart-define` 读取 `STAGING_BASE_URL` 和 `TEST_AUTH_TOKEN`
  - 封装 `_buildHeaders()` 复用 `CloudRequestHeaders.forPage()`
  - 封装 `_seedPhotoPost()` / `_deletePost()` 辅助函数（通过 staging API）
  - `tearDownAll`：清理 seeded 数据

### P2-场景：4 个 api_contract 场景实现

- [x] T17: 场景 `behavior_batch_report_reaches_service` — 已在 api_contract_runner.dart 实现
- [x] T18: 场景 `feed_cursor_pagination_end_to_end` — 已实现（含两页无重叠断言 + aspectRatio 语义层）
- [x] T19: 场景 `error_state_displayed_correctly` — 已实现（404 + 错误码映射 + 不可重试断言）
- [x] T20: 场景 `media_not_ready_graceful_error` — 已实现（X-Test-Error-Inject header + recoveryAction）

### P2-门禁：gate 绑定

- [x] T21: 根目录 `Makefile` 新增 `test-api-contract` target
- [x] T22: 根目录 `Makefile` 新增 `gate-full: gate test-api-contract`
- [x] T23: `scripts/gate_repo.sh` 新增 `patrol` scope

### P2-CI：daily API Contract job

- [x] T24: 创建 `.github/workflows/daily-api-contract.yml`（daily cron + pre-release tag 触发）
  - trigger: `schedule: cron('0 2 * * *')` + `workflow_dispatch`
  - env: `STAGING_BASE_URL` + `TEST_AUTH_TOKEN` 从 GitHub Secrets 注入
  - step: `make test-api-contract`
  - on failure: Slack/飞书通知（advisory，不阻塞 PR）
  - pre-release trigger: 在 release.yml 末尾调用此 workflow，失败则阻塞发布

---

## P3 — L4 Patrol E2E（真实设备 / Firebase Test Lab）

顺序：依赖/配置 → TestKeys → Widget 打桩 → 测试实现 → CI/FTL

### P3-基础：依赖与配置

- [x] T25: `quwoquan_app/pubspec.yaml` 新增 `patrol: ^3.15.0` + `integration_test`（flutter pub get 成功）
- [x] T26: 创建 `quwoquan_app/patrol.yaml`（app_id/bundle_id/timeout/retry）
- [x] T27: 创建 `quwoquan_app/integration_test/patrol_test_main.dart`（Patrol entry point）

### P3-TestKeys：Widget 定位基础设施

- [x] T28: `quwoquan_app/lib/core/test_keys.dart` 已存在并补充 `discoveryPage`、`photoFeedGrid`、`videoFeedList`
- [x] T29: 在 `discovery_page.dart` 打 `Key(TestKeys.photoFeedGrid)` + `Key(TestKeys.photoPostCard)`（首项）；`media_post_card.dart` 打 `buttonKey: TestKeys.likeButton/commentButton`、`countKey: TestKeys.likeCountText/commentCountText`
- [x] T30: 在 `comment_viewer.dart` 打 `Key(TestKeys.commentInputBar)`、`Key(TestKeys.commentTextField)`、`Key(TestKeys.submitCommentButton)`
- [ ] T31: 在 error toast widget 上打 `Key(TestKeys.errorToast)`
  - 重启条件：统一 toast 组件提取后（当前 toast 分散在各页面，无单一 Widget 可打桩）
  - 注：`TestKeys.errorToast` 已在 `lib/core/test_keys.dart` 声明，Widget 打桩待组件提取后补充
- [x] T32: Patrol L4 测试已使用 `$(TestKeys.xxx)` 语法定位（`feed_load_test.dart`、`like_post_test.dart`、`comment_post_test.dart`）

### P3-测试实现：3 个 Patrol 场景

- [x] T33: 创建 `test/patrol/discovery/feed_load_test.dart`（发现页 Feed 加载 + photoFeedGrid 可见）
- [x] T34: 创建 `test/patrol/content/like_post_test.dart`（乐观更新 + 幂等场景，含 staging API seeding）
- [x] T35: 创建 `test/patrol/content/comment_post_test.dart`（真实 IME 评论 + rate limit toast）

### P3-CI/FTL：Firebase Test Lab

- [x] T36: 创建 `.github/workflows/e2e.yaml`（Android + iOS 双平台，FTL 4 设备矩阵，pre-release tag 触发）
- [x] T37: `scripts/gate_repo.sh` 新增 `run_patrol_local()` 函数 + `patrol` scope（本地调试用）

---

## P4 — Gate 增强：patrol_flow 与 api_contract 文件存在性检查

- [x] T38: `quwoquan_service/scripts/gate.sh` 新增 `e2e.yaml patrol_flow` 文件存在性检查（warn 级）：
  已实现：grep 解析 patrol_flow 字段 + 文件存在性验证
- [x] T39: `gate.sh` 新增 `e2e.yaml api_contract` 场景覆盖率检查（warn 级）：
  已实现：grep -B2 解析 api_contract 场景名 + api_contract_runner.dart 覆盖检查
- [ ] T40: `gate.sh` 新增 `L3 staging skip 率` 指标输出（CI artifact 记录）
  - 重启条件：staging 环境稳定运行后，作为 SLO dashboard 一部分

---

## 规划任务（后续迭代）

- [ ] codegen_app_metadata 读取 `mock.yaml[widget_scenarios]` 生成 `_generated_widget_test.dart` 骨架
- [ ] gate 检查 mock.yaml 中每个有 `dart_func` 字段的 scenario 都有对应 Go/Dart 测试函数
- [ ] 覆盖率门禁：L1 总体 >80%，L2 per-endpoint 100%
- [ ] L3 响应时间 SLO 报表：每次 daily 把 p50/p95 写入 CI artifact，形成趋势图
- [ ] L4 Golden screenshot 对比：FTL 截图与 baseline 对比（视觉回归）
