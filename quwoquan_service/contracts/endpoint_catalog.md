# 规范化 Endpoint 名目录（用于 metrics / 日志归因）

目标：统一 `endpoint` 的命名与映射，避免不同服务/团队把 path 当 label 造成高基数与不可聚合。
`endpoint` 用于**接口归因**（metrics/logs）；`pageId` 用于**来源归因**（端侧页面/动作）。

命名规则（建议）：`<domain>.<object>.<action>`，尽量与端侧 `pageId` 同风格，但含义不同。

---

## 1. Orchestrator

| endpoint | method | path | 说明 |
|---|---|---|---|
| `orch.discovery_feed.list` | GET | `/v1/orch/discovery/feed` | 发现流聚合（首页核心旅程） |
| `orch.circle.activities.list` | GET | `/v1/orch/circles/{circleId}/activities` | 圈子活动流聚合 |

---

## 2. Content

| endpoint | method | path | 说明 |
|---|---|---|---|
| `content.feed.list` | GET | `/v1/content/feed` | 候选/非编排路径 |
| `content.behavior.ingest` | POST | `/v1/content/behaviors` | 内容行为事件写入 |
| `content.comment.list` | GET | `/v1/content/posts/{postId}/comments` | 评论列表 |
| `content.comment.create` | POST | `/v1/content/posts/{postId}/comments` | 评论创建 |
| `content.comment.delete` | DELETE | `/v1/content/comments/{commentId}` | 评论删除 |
| `content.reaction.get` | GET | `/v1/content/posts/{postId}/reactions` | 互动状态 |
| `content.counters.get` | GET | `/v1/content/posts/{postId}/counters` | 互动计数（建议强缓存） |
| `content.media.get` | GET | `/v1/content/media/{mediaId}` | 媒体资产状态 |

---

## 3. Chat

| endpoint | method | path | 说明 |
|---|---|---|---|
| `chat.conversation.list` | GET | `/v1/chat/conversations` | 会话列表 |
| `chat.conversation.get` | GET | `/v1/chat/conversations/{conversationId}` | 会话详情 |
| `chat.message.list` | GET | `/v1/chat/conversations/{conversationId}/messages` | 消息列表 |
| `chat.message.create` | POST | `/v1/chat/conversations/{conversationId}/messages` | 发送消息 |
| `chat.conversation.create` | POST | `/v1/chat/conversations` | 创建会话/群聊 |
| `chat.member.add` | POST | `/v1/chat/conversations/{conversationId}/members` | 添加成员 |
| `chat.member.remove` | DELETE | `/v1/chat/conversations/{conversationId}/members/{memberId}` | 移除成员 |
| `chat.conversation.settings.patch` | PATCH | `/v1/chat/conversations/{conversationId}/settings` | 会话设置 |
| `chat.contact.list` | GET | `/v1/chat/contacts` | 联系人列表 |
| `chat.contact.search` | GET | `/v1/chat/contacts/search` | 联系人搜索 |

---

## 4. User

| endpoint | method | path | 说明 |
|---|---|---|---|
| `user.auth.login` | POST | `/v1/user/auth/login` | 登录 |
| `user.profile.get` | GET | `/v1/user/profile/{userId}` | 用户资料/画像快照 |
| `user.persona.list` | GET | `/v1/user/personas` | persona 列表 |
| `user.persona.create` | POST | `/v1/user/personas` | persona 创建 |
| `user.persona.patch` | PATCH | `/v1/user/personas/{personaId}` | persona 更新 |
| `user.persona.delete` | DELETE | `/v1/user/personas/{personaId}` | persona 删除 |
| `user.persona.activate` | POST | `/v1/user/personas/{personaId}/activate` | persona 激活 |
| `user.follow.create` | POST | `/v1/user/follow/{targetUserId}` | 关注 |
| `user.follow.delete` | DELETE | `/v1/user/follow/{targetUserId}` | 取消关注 |
| `user.settings.notifications.get` | GET | `/v1/user/settings/notifications` | 通知设置读取 |
| `user.settings.notifications.patch` | PATCH | `/v1/user/settings/notifications` | 通知设置更新 |
| `user.settings.privacy.get` | GET | `/v1/user/settings/privacy` | 隐私设置读取 |
| `user.settings.privacy.patch` | PATCH | `/v1/user/settings/privacy` | 隐私设置更新 |
| `user.push_token.register` | POST | `/v1/user/devices/push-tokens` | push token 注册 |

---

## 5. ProductOps（运营）

| endpoint | method | path | 说明 |
|---|---|---|---|
| `ops.events.ingest` | POST | `/v1/ops/events` | 体验/行为/业务事件接收 |
| `ops.visits.ingest` | POST | `/v1/ops/visits` | visits 同步 |
| `ops.experiment.bucket.get` | GET | `/v1/ops/experiments/{experimentId}/bucket` | 实验分桶 |

---

## 6. Assistant

| endpoint | method | path | 说明 |
|---|---|---|---|
| `assistant.run.create` | POST | `/v1/assistant/runs` | 创建 run |
| `assistant.run.stream` | POST | `/v1/assistant/runs/stream` | 流式 run |
| `assistant.learning.events.ingest` | POST | `/v1/assistant/learning/events` | interaction events 上报 |
| `assistant.learning.scorecards.ingest` | POST | `/v1/assistant/learning/scorecards` | scorecards 上报 |
| `assistant.policy.get` | GET | `/v1/assistant/policy` | 拉取 policy |

---

## 7. Recommendation（推荐模型服务 rec-model-service）

推荐平台下模型服务（推理），常驻 POST /v1/score；训练工程 rec-model-training 无对外 HTTP endpoint。

| endpoint | method | path | 说明 |
|---|---|---|---|
| `recommendation.score.predict` | POST | `/v1/score` | 多场景推荐打分（content_feed / circle_discovery / friend_suggestion） |
| `recommendation.health` | GET | `/health` | 健康检查 |

---

## 8. 关键接口错误归因（contracts-first）

用于确保 `endpoint -> code(module/kind/reason)` 可机检，避免服务自定义漂移。以下为关键接口的最小错误集合：

| endpoint | 常见错误码（示例） |
|---|---|
| `orch.discovery_feed.list` | `ORCH.USER.invalid_argument` / `ORCH.NETWORK.timeout` / `ORCH.SYSTEM.internal_error` |
| `content.feed.list` | `CONTENT.USER.invalid_argument` / `CONTENT.MIDDLEWARE.unavailable` / `CONTENT.SYSTEM.internal_error` |
| `chat.message.create` | `CHAT.USER.invalid_argument` / `CHAT.USER.forbidden` / `MQ.MIDDLEWARE.publish_failed` |
| `user.auth.login` | `USER.USER.unauthorized` / `USER.USER.rate_limited` / `USER.SYSTEM.internal_error` |
| `ops.events.ingest` | `OPS.USER.invalid_argument` / `OPS.MIDDLEWARE.unavailable` / `OPS.SYSTEM.internal_error` |
| `assistant.run.create` | `ASSISTANT.USER.invalid_argument` / `ASSISTANT.NETWORK.timeout` / `ASSISTANT.SYSTEM.internal_error` |
| `recommendation.score.predict` | `RECOMMENDATION.USER.invalid_argument` / `RECOMMENDATION.NETWORK.timeout` / `RECOMMENDATION.SYSTEM.internal_error` |

约束：

- 所有接口返回错误必须满足 `contracts/openapi/common.yaml#/components/schemas/ErrorResponse`。
- `code` 必须满足 `<MODULE>.<KIND>.<REASON>`，并与 `contracts/error_codes.md` 一致。
- 若新增 endpoint，需同步补齐该表至少 1 条用户错误 + 1 条系统/依赖错误。

