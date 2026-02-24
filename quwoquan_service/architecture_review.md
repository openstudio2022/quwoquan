# 趣我圈云侧架构核对表（Review，云侧附录）

> 根目录权威入口：`specs/runtime_framework_spec.md`（含架构）  
> 本文件保留云侧核对细节作为附录，避免与根目录权威规范重复维护。

本文件用于在实现前做一次“端侧能力 → 云侧对象/接口 → 一致性/幂等/观测”全局核对，避免遗漏与返工。它不替代 `design.md` 与 `specs/*/spec.md`，而是提供一张可快速检查的索引表。

---

## 1. 服务边界（8 服务）

- **gateway-service**：HTTPS 终端、认证、限流、路由、trace 注入
- **orchestrator-service**：跨服务编排与聚合（发现流/圈子流/可选群聊编排）
- **content-service**：Feed、发布、媒体、帮读、推荐、内容行为、评论/互动状态
- **circle-service**：圈子 CRUD、活动流、成员/权限、圈内推荐、圈子行为
- **user-service**：认证、Profile/画像快照、profileUpdateProposal、persona、follow graph、用户设置、push token
- **chat-service**：会话/消息、联系人、群聊创建与成员管理、会话设置
- **product-ops（运营）**：埋点/行为采集、实验分桶、visits 同步、运营策略数据（为推荐/分析提供输入）
- **assistant-service**：runs/stream、learning ingest、policy

> 运维/平台域（可观测性、系统配置、服务治理）不属于 product-ops，见：
> - `specs/platform-ops/spec.md`
> - `platform/observability/`、`platform/config/`
> - `contracts/service_governance.md`

---

## 2. 关键业务对象清单（MVP）

### Content 域

- `Post`
- `MediaAsset`（含 derivatives、moderationStatus、processingStatus）
- `ContentBehaviorEvent`（impression/click/dwell/like/favorite/dislike/report/share…）
- `Comment` / `CommentThread`
- `ReactionState`（liked/favorited/reported…）
- `Counters`（likeCount/commentCount/favoriteCount/shareCount…）

### User 域

- `UserIdentity`（userId、账号、状态）
- `UserProfile` + `ProfileSnapshot`（versioned）
- `ProfileUpdateProposal`（created/approved/rejected/applied）
- `Persona`（isPrimary/isPrivate/active）
- `FollowEdge`（followerId → followingId）
- `UserNotificationSettings` / `UserPrivacySettings`
- `DevicePushToken`（platform/token/deviceId）

### Chat 域

- `Conversation`（direct/group）
- `ConversationMember`
- `ConversationSettings`（muted/pinned…）
- `Message`
- `Contact`

### Ops/Assistant 域（关键链路）

- `VisitRecord`（targetKey/lastSeenAt/count7d/count30d…）
- `ExperimentBucket`
- `AppLogEvent`（runId/requestId 关联）
- `InteractionEvent` / `Scorecard` / `AssistantRunRequest/Response`

---

## 3. 端云契约矩阵（按端侧页面/交互）

| 端侧能力 | 主要调用 | 备注 |
|---------|----------|------|
| 发现 Feed | `GET /v1/orch/discovery/feed` 或 `GET /v1/content/feed` | 推荐优先走编排聚合 |
| 内容互动（赞/藏/举报/停留） | `POST /v1/content/behaviors` + `POST /v1/ops/events`（可选） | 行为事件为主，状态读取另行接口 |
| 评论发布/列表 | `GET/POST /v1/content/posts/{id}/comments` | content-service 承载 MVP |
| 用户资料 | `GET /v1/user/profile/{userId}` | 返回画像快照 |
| profileUpdateProposal 回流 | `POST /v1/user/profile/proposals/{id}/confirm|reject|apply` | 强一致状态机 |
| persona 管理/切换 | `GET/POST/PATCH/DELETE /v1/user/personas` + `POST .../activate` | personaId 影响下游身份 |
| 关注/粉丝 | `POST/DELETE /v1/user/follow/{id}` + followers/following | 用于 isFollowing |
| 聊天列表/消息 | `GET /v1/chat/conversations`、`POST/GET .../messages` | 游标分页 |
| 群聊创建/成员 | `POST /v1/chat/conversations` + members API | 可选走 orchestrator 编排 |
| Visits 同步 | `POST /v1/ops/visits` | 与端侧 VisitSyncService 对齐 |
| Assistant Run | `POST /v1/assistant/runs` / `/stream` | runId 串联日志 |
| learning 上报 | `POST /v1/assistant/learning/events|scorecards` | 最终一致写入 |
| 设置：通知/隐私 | `GET/PATCH /v1/user/settings/*` | push token 另行注册 |
| Push token 注册 | `POST /v1/user/devices/push-tokens` | 对接云推送 SaaS 前置 |

---

## 4. 一致性分级（必须提前约束）

| 类别 | 一致性要求 | 典型对象 |
|------|------------|----------|
| **强一致** | 必须防并发覆盖、必须唯一/幂等 | UserIdentity、Auth、ProfileUpdateProposal、Persona activate |
| **最终一致** | 允许延迟与异步处理 | Counters、BehaviorEvent、Visits、Learning events、推荐特征 |
| **事件为主** | 只记录事件，不强求即时状态 | impression/click/dwell 等 |

---

## 5. 幂等、重试与观测（建议统一约定）

- **幂等**：所有 create/ingest 类接口支持 `Idempotency-Key`（网关透传），服务端按 key 去重。
- **追踪**：网关注入 `requestId/traceId`；Assistant Run 使用 `runId` 作为跨日志关联主键。
- **persona 上下文**：统一 `X-Persona-Id`（或 token claim）透传到下游。

---

## 6. 特性粒度追踪（端云一体）

为保证“需求→设计→实现→测试→合入”可自动化校验，新增单一事实来源：
- `changes/feature_catalog.yaml`（全量特性清单）
- `changes/<date>-<slug>/traceability.yaml`（服务/对象/API/横切能力/测试映射）

要求：
- 任何架构级变更必须先落到特性目录，再更新 contracts/specs/tasks。

---

## 7. 模型元数据核对（字段策略）

新增核对项：
- 字段是否在 `contracts/metadata/field_policy.yaml` 定义分类与日志策略
- 事件是否在 `contracts/metadata/event_catalog.yaml` 定义 producer/consumer
- 核心对象是否在 `contracts/metadata/entity_catalog.yaml` 登记

目标：
- 消除硬编码字段策略，确保端侧展示、云侧存储、观测与运营统计一致。

---

## 8. 云厂商接入核对（阿里云/火山引擎）

两条线统一核对：
- 运维线：OTEL 接入日志/指标/trace，告警与 SLO 模板可落云厂商 SaaS
- 运营线：事件采集、实验、反馈闭环可按厂商能力配置接入

原则：
- 协议与契约保持中立（OpenAPI/OTEL/JSON Schema），厂商接入通过配置与连接器实现可插拔。

