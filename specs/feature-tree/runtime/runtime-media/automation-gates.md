# runtime-media 自动化门禁

## 门禁分层
### 本地高频门禁
- `make gate-runtime-media`

用途：
- 快速回归服务端 patch / queue / metrics
- 回归客户端 realtime hint / namespace / orphan cleanup
- 回归客户端对象缓存、查询快照、缓存清理保护与网络图片入口 ratchet
- 校验里程碑文档包是否齐备

### 发布前半自动门禁
- `make gate-runtime-media-full`

用途：
- 复跑与 `gate-runtime-media` 相同的自动化项
- 联动 `t4-release-rehearsal.md` 的人工演练记录
- 用于统一回答“高标准准出是否成立”

## 当前纳入的自动化项
- `go test ./quwoquan_service/runtime/sync`
- `go test ./quwoquan_service/services/chat-service/internal/application`
- `go test ./quwoquan_service/services/chat-service/tests/local_contract`
- `go test ./quwoquan_service/services/user-service/tests/api_integration -run TestUpdateProfile_AvatarVersionAndSyncPatch`
- `flutter test test/local_contract/cloud/realtime/realtime_avatar_sync_handler__local_contract_test.dart`
- `flutter test test/local_contract/ui/components/media/video/video_playback_timeline__local_contract_test.dart`
- `flutter test test/local_contract/ui/discovery/widgets/works_immersive_viewer_widget__local_contract_test.dart`
- `./gradlew :video_player_android:testDebugUnitTest --tests io.flutter.plugins.videoplayer.ExoPlayerEventListenerTest --tests io.flutter.plugins.videoplayer.VideoPlayerTest --tests io.flutter.plugins.videoplayer.PlatformVideoViewTest`
- `flutter test test/local_contract/core/services/local_chat_search_sync_service__local_contract_test.dart`
- `flutter test test/local_contract/core/services/content_cache_services__local_contract_test.dart`
- `flutter test test/local_contract/ui/chat/widgets/chat_page_widget__local_contract_test.dart`
- `python3 quwoquan_app/scripts/media/verify_app_network_image_surface.py`
- `python3 quwoquan_ops/gate/verify_alpha_media_fixture_surface.py --env alpha|beta|gamma`
- `python3 quwoquan_ops/gate/verify_media_delivery_contract.py`
- `python3 quwoquan_ops/cli/stackctl.py verify --env <alpha|beta|gamma|prod> --kind all --profile <baseline|smoke|integration|release>`
- `specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/*` 文档包存在性检查

## Seeded Media Surface 阻断口径

- `verify_alpha_media_fixture_surface.py` 虽保留历史文件名，但语义已升级为 `alpha / beta / gamma` 共用的全量 seeded media surface gate。
- 枚举范围：`quwoquan_service/contracts/metadata/**/test_fixtures/**/*.json`、`quwoquan_ops/environments/gamma_curated_media_bundle.json` 中所有 `media/avatar/`、`media/image/`、`media/background/`、`media/video/` 引用；`alpha` 额外覆盖 App mock 群会话 `groupAvatarFor(...)` 物化头像。
- 阻断条件：任一引用缺少 shared media 源文件、HTTPS 访问失败、头像/图片/背景图未返回 `200 + image/*`、视频未返回 `206 + video/*` Range 响应，均视为环境验证失败。
- `stackctl verify --env alpha|beta|gamma --profile release` 必须执行该 gate，并显式使用 topology 中的 `mediaAvatar / mediaImage / mediaVideo` public bases；不得退回抽样 URL、单一 `mediaBaseUrl` 或 `--insecure`。
- video target readiness 必须同时满足 canonical public slice 的 HTTPS、Range `206` 与 `video/*` MIME；Range/MIME 失败时不得继续该 target 的 Patrol。
- `gamma-local` 若缓存媒体根缺失 canonical video，只能执行 `stackctl repair --target gamma-local --fix materialize-media`；该动作复制受控 canonical 媒体并校验 manifest hash，不得以修改 App URL 或切换 host 规避 404。
- `prod-sim` 与 `prod-hosted` 的 Patrol canary 必须由 topology 声明的 `VIDEO_PLAYBACK_CANARY_WORK_ID` / `VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY` 注入；任何 `fixture`、`mock`、`seed` canary 均阻断 production 验收。
- T4 环境 smoke 的固定 target 为 `video_playback_canary__user_acceptance_test.dart`：P0 必须等待原生首帧事件，执行分钟级 release-only seek 并等待原生 settle，且断言不存在 `video-player-error`；Android 准入还必须由设备所属 Patrol 日志写出 `nativeFirstFrame=true`、`nativeSeekSettled=true`，并标记 `nativeEvidenceFromPhysicalAndroidDevice=true`。页面节点、poster、controller initialize、`seekTo` Future、emulator 或环境变量均不能代替该证据。
- `beta-local` / `gamma-local` 仅在该固定的**公开视频** canary 未注入任何 actor/token 时允许 guest 只读 Patrol；其余 Patrol 仍必须提供受控测试会话，已提供凭据时不得被匿名模式覆盖。

## 当前仍需人工补充的项
- 双设备 / 双账号 / 弱网 / gap / `requiresResync` 的真机 user_acceptance 演练
- 默认群图标降级比例与 hint-to-pull 抓样
- 冷启动 feed、连续滚动、重复进入详情、分层清理缓存后的真机录屏和抓包证据

## 判定口径
- 自动化门禁通过 + user_acceptance 演练记录完整：可宣称高标准准出成立
- 自动化门禁通过但 user_acceptance 未执行：仅可宣称功能准出成立
- 自动化门禁失败：不得宣称当前主链路稳定

## 视频：商用端到端环境矩阵边界

- **单一真相源**：[`video-end-to-end-commercial-matrix.md`](./video-end-to-end-commercial-matrix.md) 冻结「商用端到端全矩阵」的环境列表与证据口径。
- **`make gate-runtime-media` / `gate-runtime-media-full`**：覆盖 runtime-media 既定自动化项与（full 模式下）`RUNTIME_MEDIA_T4_EVIDENCE` **不等于**该文件中 **`beta-local` / `gamma-local` / `prod-hosted(gray-initial)` 全矩阵 passed**。
- **Dry-run**：脚本自检与占位 artifact **禁止**冒充矩阵 passed。
- **完整证据**：`gate-runtime-media-full` 必须拒绝单份或重复 target 报告，并恰好覆盖 `alpha-local`、`beta-local`、`gamma-local`、`prod-hosted`；四条证据使用相同 commit/config hash，显式 `dryRun=false`，包含真实存在的 probe/report/screenshot/recording、asset/version/post 锚点、完整 Range 结果、原生 first-frame/seek-settled 和结构化播放器状态。Android 报告必须由物理机 Patrol 原始日志解析出原生两个证据，记录 `nativePlaybackRawLogPath`，并由 full gate 重新读取该归档文件；`seekEvidenceSource` 必须为 `native_settled`，不得经 `VIDEO_PLAYBACK_NATIVE_SEEK_SETTLED` 等环境变量声明。prod 还须以同一 release/config hash 覆盖 `gray-initial`、`carry-on`、`full`。P1-A/P1-B 在各自启用时使用独立证据块，不能影响 P0 判定。
- **资源缺失或路由错误**：缺少 beta/gamma-local 运行栈、设备 Runner、prod-hosted 分平面凭据、release canary 或其 CDN 路由时 → 不得宣称视频商用端到端全矩阵完成（与群头像 [`avatar-e2e-validation.md`](../runtime-messaging/reliable-async-task-channel/avatar-e2e-validation.md) 口径一致）。

## 内容图片：商用端到端环境矩阵边界

- **单一真相源**：[`image-end-to-end-commercial-matrix.md`](./image-end-to-end-commercial-matrix.md) 冻结「内容图片：上传—自适应—原图授权」商用全矩阵的环境列表、场景与证据口径；**当前默认 `GATE_BLOCK`** 直至四条环境均产出非 dry-run passed JSON。
- **`make gate-runtime-media`**：含图片 URL/variant 元数据静态门禁与契约测试，**不等于**上述全矩阵完成。
- **本地前置自检**：`python3 scripts/check_image_commercial_matrix_prereqs.py`（`--strict` 用于验收前自查；**不**替代云上四条证据）。
