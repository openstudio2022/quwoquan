# T4 Patrol 债务用例 · gamma-local 逐条真跑结果（收尾）

环境：emulator-5554 + gamma-local（gateway 19000 / media 19100，emulator 经 10.0.2.2 访问宿主）。
统一 defines：`APP_RUNTIME_ENV=gamma API_CONTRACT_ENV=gamma RUN_T4_PATROL=true`
+ `CLOUD_GATEWAY_BASE_URL/API_CONTRACT_BASE_URL=http://10.0.2.2:19000`
+ `MEDIA_*_CDN_BASE_URL=http://10.0.2.2:19100`
+ `APP_CURRENT_USER_ID=us_01_3278_01kvevr8s7s3b0arr7x3p27efe TEST_AUTH_TOKEN=local-t4-token`。

## 结果矩阵（8 文件 / 11 子用例）

| 文件 | 子用例 | 结果 | 耗时 | 说明 |
|---|---|---|---|---|
| content/create_entry_start_actions_e2e_test.dart | create_entry_start_actions | ✅ PASS | 9s | 重写到现行入口 |
| content/content_draft_preservation_e2e_test.dart | content_draft_preservation | ✅ PASS | 15s | 重写入口 + 修正恢复后断言 |
| ops/event_ingestion_journey_test.dart | ops_event_ingestion_journey | ✅ PASS | 9s | 重写到现行入口 |
| ops/event_reliability_replay_test.dart | ops_event_reliability_replay | ✅ PASS | 10s | 重写到现行入口 |
| content/error_empty_state_test.dart | error_empty_state_ui | ✅ PASS | 5s | 重指向首页壳基线 |
| chat/chat_notification_entry_test.dart | 系统通知点击打开聊天详情 | ✅ PASS | 10s | 自启动后通知链路 |
| chat/chat_notification_entry_test.dart | 后台收到通知后前台打开不崩溃 | ✅ PASS | 8s | openApp 补 appId |
| content/like_post_test.dart | like_post_realtime — 乐观更新 + server 确认 | ❌ GAP | — | setUp seed 失败 |
| content/like_post_test.dart | like_post_realtime — 重复点赞幂等 | ❌ GAP | — | setUp seed 失败 |
| content/comment_post_test.dart | comment_on_post_journey — 发表评论 +1 | ❌ GAP | — | setUp seed 失败 |
| content/comment_post_test.dart | comment_on_post_journey — rate limit toast | ❌ GAP | — | setUp seed 失败 |

合计：**7 子用例 PASS（5 文件全绿 + chat 2/2）/ 4 子用例诚实缺口（like/comment）**。

## 逐条修法

### 自启动模式（全部 8 文件）
每个 `patrolTest` 开头统一 `await launchPatrolAppOnce($);`，对齐已绿 journey，不依赖 `patrol_test_main` 预启动。

### 关键结构性发现（自启动修通后显形）
`DiscoveryPage`（`discovery_page` / `discoveryCreateButton`）在全 lib **无任何实例化**——已不在主导航 `IndexedStack`（落地 tab = `HomePage`，key `home-search-chrome`）。
创作入口已迁移到**底部导航「+」**（`MainAppShell` create tab → `GlobalQuickActionSheet` → `CreateActionSheet`，含 `createActionGallery/Write/Capture`）。
原 5 条用例等待 `discovery_page` 永久超时，根因是「引用已迁移/孤立的旧入口」，非自启动本身。

### 重写到现行入口（create_entry / content_draft / ops×2 / error_empty_state）
新增共享辅助 `test/patrol/support/home_create_entry.dart`（仅 test 复用，不进 lib、不碰并发改动的 `bottom_navigation.dart`）：
- `waitForHomeShell($)`：先等 `home-search-chrome` 出现在树（避免冷启动误触发返回键退出 App），仅在「存在但被遮挡」时用返回键消解。
- `openCreateActionSheet($)`：底部导航「+」语义标签 `创作`（`AppConceptConstants.create`）→ 动作面板。

### content_draft 恢复断言修正（关键根因）
`create_moment_input` 是 `article_editor.dart` 的**空文档占位输入框**。草稿恢复后编辑器载入正文 → 文档非空 → 该占位框不再渲染。原测试在恢复后等 `createMomentInput` 必然超时。
修正：恢复后直接断言草稿正文 `_draftText` 可见（「草稿可恢复」的真实证据）。

### chat openApp 补 appId
`$.native.openApp()` 无参时 patrol 解析 package 为空（`intent for launching package "" is null`）。
修正：`openApp(appId: 'com.quwoquan.quwoquan_app')`（applicationId 见 `android/app/build.gradle.kts`）。`QUERY_ALL_PACKAGES`（debug manifest）保留。

## 诚实缺口：like_post / comment_post（4 子用例）

根因双层，均非自启动可解：

1. **seed 缺必需请求头**：用例 `setUp` 的 `_seedPhotoPost` POST `/v1/content/posts` 仅带 `Content-Type` + `Authorization`，缺 `X-Client-Sub-Account-Id`。
   - 复现（curl）：
     ```bash
     curl -s -X POST "http://localhost:19000/v1/content/posts" \
       -H "Content-Type: application/json" -H "Authorization: Bearer local-t4-token" \
       -d '{"contentType":"image","title":"probe","body":"probe","mediaUrls":["https://example.com/p.jpg"]}'
     # → HTTP 400 {"code":"CONTENT.USER.invalid_argument","userMessage":"缺少 X-Client-Sub-Account-Id",...}
     ```
   - 真机表现：4 子用例在 `setUp` 抛错（Test summary `Total: 0`，4 个 ❌ 无 body detail）。

2. **结构性不匹配**：即便补齐头，`contentType=image`（work 身份）的帖子不会出现在落地首页推荐频道（`identity=moment`）。用例随后 `waitUntilVisible(photoPostCard)`（在落地 feed 内）将找不到该帖。

> 结论：这 2 个文件守护的是「seed 一个帖 → 出现在落地 feed → 互动」的旧模型，在当前首页（identity=moment 推荐频道）下不成立。
> 需**测试重设计**（补 `X-Client-Sub-Account-Id` 等头 + 改为按 postId 直达详情页，而非依赖落地 feed 露出），并依赖详情页 deep-link/路由入口；超出「自启动模式」债务范围，未伪造通过。

## 复现命令（任一文件）
```bash
export PATH="$PATH:$HOME/.pub-cache/bin"
cd quwoquan_app && patrol test \
  --target test/patrol/content/create_entry_start_actions_e2e_test.dart \
  -d emulator-5554 \
  --dart-define=APP_RUNTIME_ENV=gamma --dart-define=API_CONTRACT_ENV=gamma \
  --dart-define=RUN_T4_PATROL=true \
  --dart-define=CLOUD_GATEWAY_BASE_URL=http://10.0.2.2:19000 \
  --dart-define=API_CONTRACT_BASE_URL=http://10.0.2.2:19000 \
  --dart-define=MEDIA_IMAGE_CDN_BASE_URL=http://10.0.2.2:19100 \
  --dart-define=MEDIA_VIDEO_CDN_BASE_URL=http://10.0.2.2:19100 \
  --dart-define=APP_CURRENT_USER_ID=us_01_3278_01kvevr8s7s3b0arr7x3p27efe \
  --dart-define=TEST_AUTH_TOKEN=local-t4-token
```

## 回归守护
- `flutter analyze lib test`：**0 error**（仅既有 info/warning；本轮 patrol 文件仅 `$.native` deprecation info，与已绿 journey 同款）。
- `flutter test test/patrol`：**All tests skipped, 0 fail**（patrol 用例 `skip:!kRunPatrolT4`，证明改动编译通过且不破坏既有套件）。
- `verify_file_line_budget.py`：BLOCK 的 5 个文件（content_repository_mock / app_spacing / home_multi_form_feed_media / global_search_page / search_network_results_page）**全部是并发未提交改动（` M`）**，本轮未触碰；本轮改动全部在 `test/patrol/**`，零 lib 行数增量。
