# runtime-media 自动化门禁

## 门禁分层
### 本地高频门禁
- `make gate-runtime-media`

用途：
- 快速回归服务端 patch / queue / metrics
- 回归客户端 realtime hint / namespace / orphan cleanup
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
- `flutter test test/cloud/realtime/realtime_avatar_sync_handler_test.dart`
- `flutter test test/core/services/local_chat_search_sync_service_test.dart`

## 当前仍需人工补充的项
- 双设备 / 双账号 / 弱网 / gap / `requiresResync` 的真机 T4 演练
- 默认群图标降级比例与 hint-to-pull 抓样

## 判定口径
- 自动化门禁通过 + T4 演练记录完整：可宣称高标准准出成立
- 自动化门禁通过但 T4 未执行：仅可宣称功能准出成立
- 自动化门禁失败：不得宣称当前主链路稳定

## 视频：商用端到端环境矩阵边界

- **单一真相源**：[`video-end-to-end-commercial-matrix.md`](./video-end-to-end-commercial-matrix.md) 冻结「商用端到端全矩阵」的环境列表与证据口径。
- **`make gate-runtime-media` / `gate-runtime-media-full`**：覆盖 runtime-media 既定自动化项与（full 模式下）`RUNTIME_MEDIA_T4_EVIDENCE` **不等于**该文件中 **`beta` / `local-gamma` / `cloud-gamma-pre` / `cloud-gamma-prod-smoke` 全矩阵 passed**。
- **Dry-run**：脚本自检与占位 artifact **禁止**冒充矩阵 passed。
- **资源缺失或路由错误**：无法 SSH/部署 ECS、无本机或 Runner 双端、或 `GAMMA_BASE_URL` 未指向 **Caddy gamma-proxy**（`verify_gamma_public_gateway_routing.py` 失败）时 → 不得宣称视频商用端到端全矩阵完成（与群头像 [`avatar-e2e-validation.md`](../runtime-messaging/reliable-async-task-channel/avatar-e2e-validation.md) 口径一致）。

## 内容图片：商用端到端环境矩阵边界

- **单一真相源**：[`image-end-to-end-commercial-matrix.md`](./image-end-to-end-commercial-matrix.md) 冻结「内容图片：上传—自适应—原图授权」商用全矩阵的环境列表、场景与证据口径；**当前默认 `GATE_BLOCK`** 直至四条环境均产出非 dry-run passed JSON。
- **`make gate-runtime-media`**：含图片 URL/variant 元数据静态门禁与契约测试，**不等于**上述全矩阵完成。
- **本地前置自检**：`python3 scripts/check_image_commercial_matrix_prereqs.py`（`--strict` 用于验收前自查；**不**替代云上四条证据）。
