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
