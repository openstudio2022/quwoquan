# 群头像同步与显示 E2E 验证规格

**商用全矩阵执行顺序与清单**：[`commercial-e2e-matrix-runbook.md`](./commercial-e2e-matrix-runbook.md)。

## 目标

本规格用于验证群头像从业务变更、可靠异步任务、通知 fanout、端侧同步到真实模拟器显示的完整链路。它不是头像算法单测，而是环境矩阵验收：每个被声明通过的环境都必须产出可追溯报告，且报告能关联同一个 `conversationId` 的服务端证据与端侧 UI 证据。

## 环境矩阵

| 环境 | 运行形态 | 必须验证 | 准出要求 |
| --- | --- | --- | --- |
| `alpha` | `alpha-local` | 图片策略、message sender avatar 防回退、基础路由可用 | 工程与功能准出，不作为商用矩阵最终证明 |
| `beta` | `beta-local` + Android/iOS runner | 建群首帧、加人、退人、可靠任务、通知、App 显示 | Android 与 iOS 非 dry-run passed |
| `gamma` | `gamma-local` | Remote data source、真实本地 gateway/media、chat/reliabletask/notification module | probe、api_integration、user_acceptance 均 passed |
| `prod` | `prod-hosted` 的三阶段 rollout | 建群、头像最终更新、sync patch、UI 可见与回滚 | `gray-initial → carry-on → full` 同 release/config hash 通过 |

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
  "schema": "chat-avatar-e2e-probe-report",
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
    "runtimeKind": "beta-local",
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
    "chatConversations": "/chat/conversations",
    "userSync": "/user/sync",
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
| `env_not_ready` | 依赖服务、容器或配置未就绪 |
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

- `beta-local` 与 `gamma-local` 可采集本地 Mongo 只读证据，至少包含 `taskType`、`aggregateId`、`status`、`attempts`、`startedAt`、`completedAt`、`notificationId`、`recipientId`。
- `prod-hosted` 默认依赖黑盒 API、sync patch、SLO readback 与受控发布诊断证据。
- Redis/MQ 不作为事实源，报告中不得把 Redis ready index 单独作为成功依据。

## 端侧证据要求

- 模拟器必须以 `APP_DATA_SOURCE=remote` 运行。
- 测试必须连接当前环境的 `CLOUD_GATEWAY_BASE_URL` 与媒体 base URL。
- UI 验证必须覆盖真实图片组件渲染，不得只验证 HTTP 响应。
- 稳定选择器只能是语义化 key 或可访问性 label，不得引入 test-only 业务分支。

## 准出规则

- `alpha-local`、`beta-local`、`gamma-local`、`prod-hosted` 任一缺少报告时，不得声明“端到端显示验证完成”。
- prod 任一 rollout stage 失败，必须停止后续阶段并保留回滚证据。

## 商用矩阵证据登记模板（四环境，非 dry-run）

| 槽位 | manifest 键 | 探针 JSON（gamma 可用 `aggregate`） | Android 矩阵 JSON | iOS 矩阵 JSON | GitHub Actions（run / artifact） |
|------|---------------|-------------------------------|-------------------|---------------|----------------------------------|
| alpha-local | `alpha_local` | | | | |
| beta-local | `beta_local` | | | | |
| gamma-local | `gamma_local` | `aggregate` 或 `probe` | | | |
| prod-hosted | `prod_hosted` | | | | |

- **Manifest 路径**：`.qwq_output/env/repo/runs/commercial-matrix-chat-avatar/manifest.yaml`（勿提交真实机密）。
- **校验命令**：
  ```bash
  make verify-chat-avatar-commercial-matrix COMMERCIAL_MATRIX_MANIFEST=.qwq_output/env/repo/runs/commercial-matrix-chat-avatar/manifest.yaml
  ```
  退出码 **0**：机器认可四条证据；**2**：`GATE_BLOCK`。
- **CI 快速校验**：workflow `Verify Chat Avatar Commercial Matrix Evidence`
  （`workflow_dispatch`，传入 manifest 路径）。

## 当前执行状态（2026-07-19）

- probe、device matrix、gamma-local aggregate 与 manifest verifier 已收敛到
  `quwoquan_ops/tests/acceptance/user_acceptance/service_ops/{chat-service}/**`。
- 环境只接受 `alpha`、`beta`、`gamma`、`prod`，分别映射四个 canonical target；
  `cloud-gamma-*` 和远端 ECS gamma 入口已删除。
- dry-run 只验证命令与报告结构，不能作为商用证据。

四个 target 尚未全部产出非 dry-run、可追溯 JSON，因此结论保持 `GATE_BLOCK`。
