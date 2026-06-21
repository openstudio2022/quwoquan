# 首页推荐商用化 · 阶段9 · T4 Patrol 首页推荐用户旅程

> 时间 2026-06-19（UTC+8）· 设备 emulator-5554 · 后端 gamma-local（gateway 19000 / media 19100，
> content-service `sha256:af8610ba3c0d`）· patrol_cli 4.4.0 · patrol(vendored) 4.6.1 · Flutter 3.44.0

## 0. 结论速览

- **Total:0 根因已定位并修复**：Android 工程缺少 Patrol 原生 instrumentation 接线（`PatrolJUnitRunner` /
  Test Orchestrator / `androidTest/MainActivityTest.java`）。补齐后原生发现从 `Total:0 → Total:15`（全量目录）/
  `Total:4`（`--target` 单文件）。
- **首页推荐旅程 4/4 对 gamma 真跑绿**（`01_home_recommendation_journey.log`，exit 0）。
- 两处**诚实标注的证据缺口**（均为环境/数据，非 App/测试缺陷）：交集渲染（X-Client-User-Id 依赖 + 无 JWT 网关）、
  推荐频道 moment 种子仅 1 条。下文给出根因 + 复现 + T2/T3 覆盖对照。

## 1. Total:0 根因 + 修法

| 维度 | 现状 | 结论 |
|---|---|---|
| pubspec `patrol` 配置 | `test_directory: test/patrol` 已存在；patrol_cli 正确读取并在该目录生成 `test_bundle.dart` | 目录约定**无**问题 |
| `integration_test` 依赖 | dev_dependencies 已含 | OK |
| 版本匹配 | patrol_cli 4.4.0 + patrol 4.6.1，能正常构建 bundle + APK + 执行 RPC | 兼容（非 Total:0 主因） |
| **Android native runner** | `android/app/build.gradle.kts` **缺** `testInstrumentationRunner=PatrolJUnitRunner`、`testInstrumentationRunnerArguments`、`testOptions{execution=ANDROIDX_TEST_ORCHESTRATOR}`、`androidTestUtil(orchestrator)`；且**无** `src/androidTest/.../MainActivityTest.java` | **这是 Total:0 真因** |

**修法（仅 patrol 集成工程配置 + 测试用例，未改业务 lib）：**
1. `android/app/build.gradle.kts`：`defaultConfig` 加 `PatrolJUnitRunner` + `clearPackageData`；新增
   `testOptions{execution = ANDROIDX_TEST_ORCHESTRATOR}`；`compileOptions` 开 `isCoreLibraryDesugaringEnabled`；
   `dependencies` 加 `coreLibraryDesugaring(desugar_jdk_libs:2.0.3)` + `androidTestUtil(androidx.test:orchestrator:1.5.1)`。
2. 新增 `android/app/src/androidTest/java/com/quwoquan/quwoquan_app/MainActivityTest.java`
   （`@RunWith(Parameterized.class)` + `PatrolJUnitRunner.setUp/waitForPatrolAppService/listDartTests/runDartTest`）。
3. 旁路网络问题：sqlite3 3.3.2 native-asset build hook 从 GitHub 下载 `libsqlite3.*.android.so`，
   单发 HttpClient 无重试、China pub 镜像下偶发断流；重跑该 hook 即成功（非产品/配置问题）。

验证：`make`/`patrol test` 现可发现并执行原生用例（`00_native_discovery_validation.log` 全量 `Total:15`）。

## 2. 首页推荐旅程结果（`--target` 单文件，4/4 PASS）

文件：`quwoquan_app/test/patrol/discovery/home_recommendation_journey_test.dart`

| 用例 | 结果 | 真实 gamma 交互证据 |
|---|---|---|
| `home_rec_feed_first_load_renders_real_remote_card` | ✅ 19s | 推荐 feed 首刷非空，渲染真实远端卡片（作者头部 `home-relation-card-header` + 互动行 `home-relation-card-actions`） |
| `home_rec_open_immersive_consumption_and_return` | ✅ 22s | 点击内容卡进入沉浸消费（首页 `home-search-chrome` 被全屏路由覆盖），原生返回回到 feed |
| `home_rec_author_object_nav_and_follow_entry` | ✅ 27s | 点击作者头像跳转用户主页（`profile-header-avatar`/`profile-shell-summary-card`），主页含「关注/已关注」入口 |
| `home_rec_negative_feedback_converges` | ✅ 12s | 更多→不感兴趣→卡片本地移除 + 降级提示「将减少这类内容」（行为同时上报 gamma） |

固化：`01_home_recommendation_journey.log`、`03_patrol_report_index.html`。

## 3. 证据缺口（环境/数据，非 App/测试缺陷）

### 3.1 交集证据（intersectionReasons）在 App 内不渲染
- 根因：gamma-local 推荐 feed 的个性化交集**仅由 `X-Client-User-Id` 决定**；gamma-local 无 JWT 校验网关（T3 §1），
  App feed 读取按生产设计仅发 `Authorization`（由生产网关注入身份），不在端侧硬塞 `X-Client-User-Id`。
- 证据（`02_intersection_header_dependency.txt`）：
  - auth-only → intersectionNonEmpty=0；带 `X-Client-User-Id` → 6/20。
- 复现：`curl -H 'X-Client-User-Id: us_01_3278_01kvevr8s7s3b0arr7x3p27efe' '.../v1/content/feed?sort=recommended&limit=20'`
- 覆盖：交集行渲染 + name/count span 跳转由 **T2** `home_intersection_multiform_feed_widget_test`、
  `home_intersection_object_nav_test`、`intersection_target_navigator_test` 守护；数据就绪由 **T3** 真跑证明。
  T4 用「作者头像→用户主页」覆盖对象跳转链路（同一导航目标）。

### 3.2 推荐频道（identity=moment）gamma 仅 1 条种子
- 根因：推荐频道 `feedQuery={category: micro, identity: moment}`；gamma-local 仅 seed 了 1 条 moment
  （`fixture_moment_001`，含图、likes 199），默认内容 feed 富集（20 篇文章 + nextCursor）。
- 影响：「多形态卡片 / 连续下拉曝光不重复」无法在推荐频道 App 内演示（单卡）。
- 覆盖：多形态渲染由 **T2** `home_intersection_multiform_feed_widget_test`（moment/photo/video/article 四形态 + 1–9+ 图规则）守护；
  富集分页由 curl 证明（`sort=recommended` → 20 + nextCursor=true）。
- 后续命令（如需在 App 内演示）：向 gamma 注入更多 moment 种子（属 `shared_pool_real_asset_pipeline` 范畴，本轮按要求未触碰）。

## 4. 顺带暴露的既有 T4 债（非本任务范围，建议另案）

修通原生发现后，全量目录 `Total:15` 中 8 条既有 T4 用例失败，根因与本旅程无关：
- `like_post/comment_post/content_draft/create_entry/error_empty_state/ops_*`：误以为 App 已被
  `patrol_test_main` 启动（实际 patrol 4.x bundle 不把非 `*_test.dart` 入口作为 App 启动器），未调用
  `launchPatrolAppOnce` → 找不到 `discovery_page` 超时。
- `chat_notification_entry`：原生 `openApp()` 需 `QUERY_ALL_PACKAGES` 权限。
- 正解：这些用例应改用 `launchPatrolAppOnce` 自启动模式（与本旅程/feed_load/basic_viability 一致）。

## 5. 回归守护
- `flutter analyze lib test`：**0 error**（仅 info/warning；本文件 3 处 `$.native` deprecation info，与既有 patrol 用例一致）。
- `flutter test`：见 `05_flutter_test_regression.log`（新增旅程 `skip: !kRunPatrolT4`，`flutter test` 下跳过，不影响既有套件）。
