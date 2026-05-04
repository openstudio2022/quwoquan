# 群头像同步与显示 E2E 验证规格

**商用全矩阵执行顺序与清单**：[`commercial-e2e-matrix-runbook.md`](./commercial-e2e-matrix-runbook.md)。本地前置自检：`python3 scripts/check_avatar_commercial_matrix_prereqs.py --strict`（`strict_local_prereqs_met` 仅表示 flutter/patrol/双端设备/网关 healthz 等就绪；脚本始终输出 `commercial_declaration_allowed=false`，**不**替代四条环境的非 dry-run JSON）。

## 目标

本规格用于验证群头像从业务变更、可靠异步任务、通知 fanout、端侧同步到真实模拟器显示的完整链路。它不是头像算法单测，而是环境矩阵验收：每个被声明通过的环境都必须产出可追溯报告，且报告能关联同一个 `conversationId` 的服务端证据与端侧 UI 证据。

## 环境矩阵

| 环境 | 运行形态 | 必须验证 | 准出要求 |
| --- | --- | --- | --- |
| `alpha` | 快速本地/CI，允许 mock 或最小 remote | 图片策略、message sender avatar 防回退、基础路由可用 | 不作为可靠任务最终证明 |
| `beta` | 本地 beta stack + Android/iOS 模拟器 | 建群首帧、加人、退人、可靠任务、通知、App 显示 | 至少一个模拟器 passed；发布前应覆盖 Android 和 iOS |
| `local-gamma` | 本地 Docker gamma mirror + seed-box onebox | gamma 配置、remote data source、media base、chat/reliabletask/notification module | `avatar_e2e_report.json`、T3、T4 均 passed |
| `cloud-gamma-pre` | GitHub Actions ECS pre + self-hosted 模拟器 | 真实 `GAMMA_BASE_URL`、真实网关、真实媒体加载、阻断 prod 前置 | pre 阶段失败不得进入 prod |
| `cloud-gamma-prod-smoke` | ECS prod 就地升级后 smoke | 建群、头像最终更新、sync patch、UI 可见 | smoke failed 必须阻断发布完成结论 |

## 核心场景

1. 使用固定测试用户创建群聊，创建者为 `creatorUserId`，初始成员为 `initialMemberIds`。
2. 读取会话详情，断言首帧 `avatarUrl` 等于创建者个人头像或合法用户默认头像，且不得是空、`契`、系统契约占位。
3. 添加成员 `addedMemberId`，触发 `chat.group_avatar.recompute` 可靠任务。
4. 等待会话 `groupAvatarVersion` 递增，且最终 `avatarUrl` 非空、可被媒体层加载。
5. 所有目标成员通过 sync pull 或 App 实时同步收到 `conversation.avatar.updated`。
6. 在聊天详情发送或展示消息，断言 message bubble sender avatar 仍使用发送者个人头像，不被群头像覆盖。
7. 移除成员 `removedMemberId`，再次等待 `groupAvatarVersion` 递增，并重复 sync 与 UI 断言。

## 统一报告 Schema

所有脚本和模拟器 runner 必须写入同构 JSON。字段可扩展，但不得缺少下列顶层字段。

```json
{
  "schemaVersion": 1,
  "scenario": "chat.group_avatar.sync_display_e2e",
  "status": "passed",
  "failureCategory": "",
  "blockingReason": "",
  "recoveryPolicy": {
    "action": "none",
    "disruptionLevel": "none"
  },
  "startedAt": "2026-05-03T00:00:00Z",
  "endedAt": "2026-05-03T00:01:00Z",
  "environment": {
    "env": "beta",
    "runtimeKind": "local-stack",
    "gatewayBaseUrl": "http://127.0.0.1:18080",
    "mediaBaseUrl": "http://127.0.0.1:18081",
    "commitSha": "",
    "githubRunId": ""
  },
  "device": {
    "platform": "android",
    "deviceId": "emulator-5554",
    "name": "Pixel",
    "screenClass": "phone"
  },
  "conversation": {
    "conversationId": "",
    "creatorUserId": "user_test_001",
    "memberIds": ["user_test_001", "user_test_002", "user_test_003"],
    "addedMemberId": "user_test_004",
    "removedMemberId": "user_test_004",
    "initialAvatarUrl": "",
    "finalAvatarUrl": "",
    "groupAvatarVersionBefore": 0,
    "groupAvatarVersionAfterAdd": 0,
    "groupAvatarVersionAfterRemove": 0
  },
  "serviceEvidence": {
    "taskOutbox": {"status": "not_collected", "records": []},
    "asyncTask": {"status": "not_collected", "records": []},
    "notificationOutbox": {"status": "not_collected", "records": []},
    "deliveryLedger": {"status": "not_collected", "deliveredRecipients": []},
    "syncPatches": []
  },
  "serviceEndpointEvidence": {
    "healthz": "http://127.0.0.1:18080/healthz",
    "chatConversations": "/v1/chat/conversations",
    "userSync": "/v1/user/sync",
    "media": "http://127.0.0.1:18080/media/avatar/..."
  },
  "uiEvidence": {
    "conversationListAvatarVisible": false,
    "conversationDetailAvatarVisible": false,
    "avatarImageLoaded": false,
    "senderAvatarPreserved": false,
    "screenshots": []
  },
  "steps": []
}
```

## 失败分类

| 分类 | 含义 |
| --- | --- |
| `env_not_ready` | 依赖服务、容器、ECS 或配置未就绪 |
| `device_not_found` | 未发现可运行 Android/iOS 模拟器 |
| `gateway_unreachable` | 网关健康检查或核心 API 不可达 |
| `auth_failed` | 测试 token、用户上下文或 header 被拒绝 |
| `avatar_task_timeout` | 可靠任务未在超时内完成或版本未递增 |
| `notification_not_delivered` | `conversation.avatar.updated` 未送达全部目标成员 |
| `media_load_failed` | `avatarUrl` 不可下载或 App 图片层加载失败 |
| `ui_avatar_not_visible` | 会话列表或聊天详情未显示群头像 |
| `sender_avatar_regression` | 消息气泡发送者头像回退为群头像、空图或契约占位 |
| `unknown` | 未归类失败，必须附带原始异常摘要 |

## 服务端证据要求

- `beta` 与 `local-gamma` 可采集本地 Mongo 只读证据，至少包含 `taskType`、`aggregateId`、`status`、`attempts`、`startedAt`、`completedAt`、`notificationId`、`recipientId`。
- `cloud-gamma` 默认只依赖黑盒 API 与 sync patch 证据；若 workflow 具备 ECS SSH 诊断能力，可在 ECS 内执行只读诊断并作为 artifact 上传。
- Redis/MQ 不作为事实源，报告中不得把 Redis ready index 单独作为成功依据。

## 端侧证据要求

- 模拟器必须以 `APP_DATA_SOURCE=remote` 运行。
- 测试必须连接当前环境的 `CLOUD_GATEWAY_BASE_URL` 与媒体 base URL。
- UI 验证必须覆盖真实图片组件渲染，不得只验证 HTTP 响应。
- 稳定选择器只能是语义化 key 或可访问性 label，不得引入 test-only 业务分支。

## 准出规则

- `beta`、`local-gamma`、`cloud-gamma-pre`、`cloud-gamma-prod-smoke` 任一缺少报告时，不得声明“端到端显示验证完成”。
- `cloud-gamma-pre` 中 API probe 或 self-hosted 模拟器失败，必须阻断 prod 部署。
- `cloud-gamma-prod-smoke` 失败，必须阻断发布完成结论并保留回滚证据。

## 商用矩阵证据登记模板（E1–E4，非 dry-run）

| 槽位 | manifest 键 | 探针 JSON（或 E2 `aggregate`） | Android 矩阵 JSON | iOS 矩阵 JSON | GitHub Actions（run / artifact） |
|------|---------------|-------------------------------|-------------------|---------------|----------------------------------|
| E1 beta | `e1_beta` | | | | |
| E2 local-gamma | `e2_local_gamma` | `aggregate` 或 `probe` | | | |
| E3 cloud-gamma-pre | `e3_cloud_gamma_pre` | | | | |
| E4 prod-smoke | `e4_cloud_gamma_prod_smoke` | | | | |

- **Manifest 路径**（仓库内）：`artifacts/commercial-matrix/chat-avatar/manifest.yaml`（勿提交真实机密；可仅登记相对路径与 CI artifact 链接）。
- **校验命令**：
  ```bash
  make verify-chat-avatar-commercial-matrix COMMERCIAL_MATRIX_MANIFEST=artifacts/commercial-matrix/chat-avatar/manifest.yaml
  ```
  退出码 **0**：机器认可四条证据；**2**：`GATE_BLOCK`。
- **CI 快速校验**：workflow `08b. Verify Chat Avatar Commercial Matrix Evidence`（`workflow_dispatch`，上传 manifest 路径）。

## 当前执行证据（2026-05-03）

### 工程/脚本形态（dry-run 与不冒充商用矩阵）

本轮已完成本地可执行门禁和脚本形态验证：

- `go test ./runtime/reliabletask`
- `go test ./services/chat-service/tests -run TestGroupAvatar`
- `flutter test test/cloud/realtime/realtime_avatar_sync_handler_test.dart`
- `python3 -m py_compile scripts/run_chat_avatar_e2e_probe.py scripts/run_chat_avatar_device_matrix.py scripts/run_chat_avatar_device_matrix_ci.py scripts/run_local_gamma_avatar_e2e.py scripts/run_local_gamma_t3.py scripts/verify_chat_avatar_commercial_matrix_evidence.py`
- `bash -n scripts/start_local_gamma_mirror.sh`
- `bash -n scripts/run_chat_avatar_commercial_matrix_orchestrator.sh`
- `python3 scripts/run_chat_avatar_e2e_probe.py --dry-run --env beta --report artifacts/avatar-e2e/beta/avatar_e2e_report.json`
- `python3 scripts/run_local_gamma_avatar_e2e.py --dry-run --skip-device-matrix --report artifacts/local-gamma/avatar_e2e_report.json`
- `python3 scripts/run_chat_avatar_device_matrix.py --dry-run --env local-gamma --platform ios --device-id dry-run-device --report artifacts/device-matrix/chat-avatar/local-gamma-ios-dry-run.json`

上述含 `dry-run` 的项**不得**作为商用矩阵 passed 依据；正式准出须填 manifest 并通过 `verify_chat_avatar_commercial_matrix_evidence.py`。

**商用矩阵前提（修订）**：矩阵可在 **阿里云 ECS onebox**（`scripts/deploy_gamma_ecs.sh` / `deploy-gamma-ecs.yml`）+ **本机或已注册 self-hosted Runner**（Flutter/Patrol）上完成。`GAMMA_BASE_URL` 必须指向 **Caddy gamma-proxy** 端口（见 [`environment_matrix.md`](../../../../../deploy/shared/environment_matrix.md)），否则探针会误连 content 直出端口导致 `route_not_found` 或落入 Caddy 占位响应。部署后先跑 `python3 scripts/verify_gamma_public_gateway_routing.py --base-url "$GAMMA_BASE_URL"` 再执行 `run_chat_avatar_e2e_probe.py` / device-matrix。  
在四项环境均未产出 **非 dry-run、可追溯 JSON** 前，结论仍须保持 `GATE_BLOCK`，不得宣称群头像端到端显示验证商用完成。
