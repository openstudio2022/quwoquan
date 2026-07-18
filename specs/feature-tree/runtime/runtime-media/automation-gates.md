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
- `go test ./quwoquan_service/services/chat-service/tests`
- `go test ./quwoquan_service/services/user-service/tests -run TestUpdateProfile_AvatarVersionAndSyncPatch`
- `flutter test test/local_contract/cloud/realtime/realtime_avatar_sync_handler__local_contract_test.dart`
- `flutter test test/core/services/local_chat_search_sync_service_test.dart`
- `flutter test test/core/services/content_cache_services_test.dart`
- `flutter test test/ui/chat/widgets/chat_page_widget_test.dart`
- `python3 quwoquan_app/scripts/media/verify_app_network_image_surface.py`
- `python3 quwoquan_ops/gate/verify_alpha_media_fixture_surface.py --env alpha|beta|gamma`
- `python3 quwoquan_ops/gate/verify_media_delivery_contract.py`
- `python3 quwoquan_ops/cli/stackctl.py verify --env <alpha|beta|gamma|prod> --kind all --tier <t1|t2|t3|t4>`
- `specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/*` 文档包存在性检查

## Seeded Media Surface 阻断口径

- `verify_alpha_media_fixture_surface.py` 虽保留历史文件名，但语义已升级为 `alpha / beta / gamma` 共用的全量 seeded media surface gate。
- 枚举范围：`quwoquan_service/contracts/metadata/**/test_fixtures/**/*.json`、`quwoquan_ops/environments/gamma_curated_media_bundle.json` 中所有 `media/avatar/`、`media/image/`、`media/background/`、`media/video/` 引用；`alpha` 额外覆盖 App mock 群会话 `groupAvatarFor(...)` 物化头像。
- 阻断条件：任一引用缺少 shared media 源文件、HTTPS 访问失败、头像/图片/背景图未返回 `200 + image/*`、视频未返回 `206 + video/*` Range 响应，均视为环境验证失败。
- `stackctl verify --env alpha|beta|gamma --tier t4` 必须执行该 gate，并显式使用 topology 中的 `mediaAvatar / mediaImage / mediaVideo` public bases；不得退回抽样 URL、单一 `mediaBaseUrl` 或 `--insecure`。
- video target readiness 必须同时满足 canonical public slice 的 HTTPS、Range `206` 与 `video/*` MIME；Range/MIME 失败时不得继续该 target 的 Patrol。
- `gamma-local` 若缓存媒体根缺失 canonical video，只能执行 `stackctl repair --target gamma-local --fix materialize-media`；该动作复制受控 canonical 媒体并校验 manifest hash，不得以修改 App URL 或切换 host 规避 404。
- `prod-sim` 与 `prod-hosted` 的 Patrol canary 必须由 topology 声明的 `VIDEO_PLAYBACK_CANARY_WORK_ID` / `VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY` 注入；任何 `fixture`、`mock`、`seed` canary 均阻断 production 验收。
- T4 环境 smoke 的固定 target 为 `video_playback_canary__user_acceptance_test.dart`：它必须等待 `video-player-ready`，并断言不存在 `video-player-error`；页面节点出现或 poster 可见均不能代替原生播放器 ready 证据。
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
- **完整证据**：`gate-runtime-media-full` 会通过 `verify_runtime_media_t4_evidence.py` 校验 JSON：schema、显式 `dryRun=false`、环境/target/rollout stage、commit/config hash、canonical `publicSliceKey`、服务端 `206 + video/*` 和设备 `stageRendered=true/playerReady=true/playerError=false`、截图/Patrol 报告路径缺一不可；仅存在一个文件路径不构成通过。失败报告必须以 `playerState` 区分未渲染、显式播放器错误和 ready 超时，禁止把页面未渲染误记为播放器错误。
- **资源缺失或路由错误**：缺少 beta/gamma-local 运行栈、设备 Runner、prod-hosted 分平面凭据、release canary 或其 CDN 路由时 → 不得宣称视频商用端到端全矩阵完成（与群头像 [`avatar-e2e-validation.md`](../runtime-messaging/reliable-async-task-channel/avatar-e2e-validation.md) 口径一致）。

## 内容图片：商用端到端环境矩阵边界

- **单一真相源**：[`image-end-to-end-commercial-matrix.md`](./image-end-to-end-commercial-matrix.md) 冻结「内容图片：上传—自适应—原图授权」商用全矩阵的环境列表、场景与证据口径；**当前默认 `GATE_BLOCK`** 直至四条环境均产出非 dry-run passed JSON。
- **`make gate-runtime-media`**：含图片 URL/variant 元数据静态门禁与契约测试，**不等于**上述全矩阵完成。
- **本地前置自检**：`python3 scripts/check_image_commercial_matrix_prereqs.py`（`--strict` 用于验收前自查；**不**替代云上四条证据）。
