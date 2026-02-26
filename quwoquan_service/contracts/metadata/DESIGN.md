# 业务对象元数据设计总览

> 本文档是 `contracts/metadata/` 的设计总览，定义每个业务对象及实体的设计原则、定义、存储选型与超前规划。
> 配套规范：`specs/runtime_framework_spec.md` | `specs/runtime_framework_design.md`

---

## 目录

- [1. 设计原则](#1-设计原则)
- [2. 目录结构](#2-目录结构)
- [3. 业务对象全景](#3-业务对象全景)
- [4. 聚合 A：UserProfile（用户档案）](#4-聚合-auserprofile用户档案)
- [5. 聚合 B：Post（内容）](#5-聚合-bpost内容)
- [6. 聚合 C：Conversation（会话）](#6-聚合-cconversation会话)
- [7. 聚合 D：Circle（圈子）](#7-聚合-dcircle圈子)
- [8. 聚合 E：AssistantRun（助手）](#8-聚合-eassistantrun助手)
- [9. 独立实体](#9-独立实体)
- [10. 衍生物：ReadModel / 向量 / Redis](#10-衍生物readmodel--向量--redis)
- [11. 存储选型总览](#11-存储选型总览)
- [12. 契约测试策略](#12-契约测试策略)

---

## 1. 设计原则

### 1.1 元数据先行

- 新增 entity/field/tag/event **必须先在 metadata 中注册**，再暴露接口或存储。
- 禁止在代码、接口、日志中硬编码与 metadata 冲突的字段含义或策略。
- `make verify` 校验 metadata 内部一致性。

### 1.2 聚合自治

- 每个聚合根 + 成员组成**一致性边界**，在同一事务内变更。
- 聚合成员仅通过聚合根的 Repository 访问，禁止直接跨聚合调用。
- 跨聚合交互通过**领域事件**（异步最终一致）。

### 1.3 存储选型原则

| 场景 | 选型 | 判据 |
|------|------|------|
| 强 ACID、关系约束、状态机 | **PostgreSQL** | 数据正确性 > 吞吐量 |
| 高并发读写、灵活 schema、水平扩展 | **MongoDB** | 吞吐量 + 弹性 > 严格 ACID |
| 毫秒级读取、TTL 管理 | **Redis 缓存** | 热数据加速 |
| 语义检索、相似推荐 | **向量存储** | embedding 相似度 |

关键决策：**同一聚合内的所有实体使用同一存储后端**，避免分布式事务。

### 1.4 接口门面统一

- 每个业务对象在 `service.yaml` 中声明归属服务、DDD 层映射和 API 路由。
- OpenAPI schema 从 metadata 推导或校验，保证端云一致。
- 上层应用（App、运营、推荐、助手）的消费关系在 `service.yaml` 中显式声明。

### 1.5 超前建设

- 业务对象与 metadata 超前于特性建设，而非临时补丁。
- 标签体系、推荐特征、向量化能力在 entity 注册时声明就绪。
- Context Pipeline 框架层统一提供，新 entity 注册后自动参与上下文构建。

---

## 2. 目录结构

```
contracts/metadata/
├── DESIGN.md                         # 本文档
├── README.md                         # 使用指南
│
├── _shared/                          # 跨域共享定义
│   ├── tag_taxonomy.yaml             # 标签分类体系（四域）
│   ├── types.yaml                    # 共享类型（GeoPoint, Enum 等）
│   ├── redis_keyspace.yaml           # Redis 全局键空间设计
│   └── openapi_common.yaml          # 共享 OpenAPI schema（ErrorResponse, 分页参数等）
│
├── content/                          # content-service 域容器
│   ├── openapi.yaml                  # content-service OpenAPI（co-located）
│   ├── post/                         # Post 聚合
│   │   ├── aggregate.yaml            # Post + Comment + MediaAsset + ContentReaction
│   │   ├── fields.yaml
│   │   ├── events.yaml
│   │   ├── storage.yaml
│   │   ├── service.yaml
│   │   ├── errors.yaml               # 端云统一错误码
│   │   ├── behaviors.yaml            # 用户行为 + ML 特征
│   │   ├── privacy.yaml              # 隐私与安全策略
│   │   ├── ui_config.yaml            # UI 可配置化
│   │   ├── projections/              # ReadModel 投影
│   │   │   ├── discovery_feed.yaml
│   │   │   ├── photo_post.yaml
│   │   │   ├── video_post.yaml
│   │   │   ├── article_post.yaml
│   │   │   └── moment_post.yaml
│   │   └── tests/                    # 三层测试契约
│   │       ├── mock.yaml
│   │       ├── contract.yaml
│   │       └── e2e.yaml
│   └── report/                       # Report 独立实体（content domain）
│       ├── entity.yaml
│       ├── fields.yaml
│       ├── events.yaml
│       ├── storage.yaml
│       └── service.yaml
│
├── messages/                         # chat-service 域容器
│   ├── openapi.yaml                  # chat-service OpenAPI（co-located）
│   └── conversation/                 # Conversation 聚合
│       ├── aggregate.yaml
│       ├── fields.yaml
│       ├── events.yaml
│       ├── storage.yaml
│       ├── service.yaml
│       └── projections/
│           └── chat_inbox.yaml
│
├── user/                             # user-service 域容器
│   ├── openapi.yaml                  # user-service OpenAPI（co-located）
│   ├── user_profile/                 # UserProfile 聚合
│   │   ├── aggregate.yaml
│   │   ├── fields.yaml
│   │   ├── events.yaml
│   │   ├── storage.yaml
│   │   ├── service.yaml
│   │   └── projections/
│   │       └── user_profile_view.yaml
│   ├── follow_edge/                  # FollowEdge 独立实体
│   │   ├── entity.yaml
│   │   ├── fields.yaml
│   │   ├── events.yaml
│   │   ├── storage.yaml
│   │   └── service.yaml
│   └── block_edge/                   # BlockEdge 独立实体
│       ├── entity.yaml
│       ├── fields.yaml
│       ├── events.yaml
│       ├── storage.yaml
│       └── service.yaml
│
├── social/                           # circle-service 域容器
│   └── circle/                       # Circle 聚合
│       ├── aggregate.yaml
│       ├── fields.yaml
│       ├── events.yaml
│       ├── storage.yaml
│       ├── service.yaml
│       └── projections/
│           └── circle_feed.yaml
│
├── assistant/                        # assistant-service 域容器
│   ├── assistant_run/                # AssistantRun 聚合
│   │   ├── aggregate.yaml
│   │   ├── fields.yaml
│   │   ├── events.yaml
│   │   ├── storage.yaml
│   │   └── service.yaml
│   └── skill_consent/                # SkillConsent 独立实体
│       ├── entity.yaml
│       ├── fields.yaml
│       ├── storage.yaml
│       └── service.yaml
│
├── notification/                     # notification-service 域容器
│   └── notification/                 # Notification 独立实体
│       ├── entity.yaml
│       ├── fields.yaml
│       ├── events.yaml
│       ├── storage.yaml
│       └── service.yaml
│
├── recommendation/                   # rec-model-service 域容器
│   ├── openapi.yaml                  # rec-model-service OpenAPI（co-located）
│   └── rec_model/                    # RecModel 服务实体
│       ├── entity.yaml
│       ├── fields.yaml
│       ├── events.yaml
│       ├── storage.yaml
│       ├── service.yaml
│       └── projections/
│           ├── learning_events.yaml
│           ├── model_registry.yaml
│           ├── recommend_feature.yaml
│           └── training_samples.yaml
│
├── ops/                              # orchestrator/product-ops 域容器
│   ├── openapi.yaml                  # orchestrator-service OpenAPI（co-located）
│   ├── visit_record/                 # VisitRecord 独立实体
│   │   ├── entity.yaml
│   │   ├── fields.yaml
│   │   ├── storage.yaml
│   │   └── service.yaml
│   └── experiment_bucket/            # ExperimentBucket 独立实体
│       ├── entity.yaml
│       ├── fields.yaml
│       ├── storage.yaml
│       └── service.yaml
│
└── _vectors/                         # 向量存储
    ├── content_embedding.yaml
    └── user_context_embedding.yaml
```

---

## 3. 业务对象全景

### 3.1 聚合地图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          趣我圈 业务对象全景                                  │
│                                                                            │
│  ┌─ user domain ─────────────────────┐  ┌─ content domain ──────────────┐ │
│  │ UserProfile [PG] 聚合根            │  │ Post [Mongo] 聚合根           │ │
│  │  ├── Persona                      │  │  ├── Comment                  │ │
│  │  ├── UserAuth                     │  │  ├── MediaAsset               │ │
│  │  ├── UserDevice                   │  │  └── ContentReaction          │ │
│  │  ├── UserSetting                  │  │                               │ │
│  │  └── ProfileUpdateProposal       │  │ Report [PG] 独立              │ │
│  │                                    │  └───────────────────────────────┘ │
│  │ FollowEdge [Mongo] 独立           │                                    │
│  │ BlockEdge [PG] 独立               │  ┌─ circle domain ──────────────┐ │
│  └────────────────────────────────────┘  │ Circle [Mongo] 聚合根        │ │
│                                           │  └── CircleMember            │ │
│  ┌─ chat domain ─────────────────────┐  └───────────────────────────────┘ │
│  │ Conversation [Mongo] 聚合根        │                                    │
│  │  └── Message                       │  ┌─ assistant domain ───────────┐ │
│  └────────────────────────────────────┘  │ AssistantRun [Mongo] 聚合根   │ │
│                                           │  └── InteractionEvent        │ │
│  ┌─ ops domain ──────────────────────┐  │ SkillConsent [PG] 独立        │ │
│  │ VisitRecord [Mongo] 独立           │  └───────────────────────────────┘ │
│  │ ExperimentBucket [PG] 独立         │                                    │
│  └────────────────────────────────────┘  ┌─ notification domain ────────┐ │
│                                           │ Notification [Mongo] 独立     │ │
│                                           └───────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 存储分布统计

| 存储 | 聚合/实体 | 数量 | 定位 |
|------|----------|------|------|
| **PostgreSQL** | UserProfile(+5 成员), BlockEdge, Report, SkillConsent, ExperimentBucket | 10 实体 | 事务一致 + 关系约束 + 安全合规 |
| **MongoDB** | Post(+3 成员), Conversation(+1), Circle(+1), AssistantRun(+1), FollowEdge, VisitRecord, Notification + ReadModel + EventStore | 15+ 实体 | 弹性扩展 + 高并发 |
| **Redis** | 实体缓存 + 推荐热路径 + 助手上下文 + 屏蔽缓存 + 限流 | 缓存层 | 毫秒级读取 |
| **向量存储** | ContentEmbedding, UserContextEmbedding | 2 | 语义检索 |

---

## 4. 聚合 A：UserProfile（用户档案）

### 4.1 当前实现分析

**已有接口（user-service OpenAPI + spec）：**
- `POST /v1/user/auth/login` — 登录（返回 accessToken + refreshToken + userId）
- `POST /v1/user/auth/refresh` — Token 刷新（spec 中定义，OpenAPI 待补充）
- `GET /v1/user/profile/{userId}` — 档案读取（含 basicIdentity + snapshot）
- `GET/POST/PATCH/DELETE /v1/user/personas/*` — 分身 CRUD + 激活
- `POST/DELETE /v1/user/follow/{targetUserId}` — 关注/取关
- `GET /v1/user/{userId}/following|followers` — 关注/粉丝列表（spec 定义，OpenAPI 待补充）
- `GET /v1/user/{userId}/relationship` — 关系查询（spec 定义，OpenAPI 待补充）
- `GET/PATCH /v1/user/settings/notifications` — 通知设置
- `GET/PATCH /v1/user/settings/privacy` — 隐私设置
- `POST /v1/user/devices/push-tokens` — 推送 token 注册
- `POST /v1/user/profile/proposals/{id}/confirm|apply|reject` — ProfileUpdateProposal 状态流转（spec 定义，OpenAPI 待补充）

**App 端页面：**
- `/profile` — 我的档案（创作/互动/生活三个 tab + 统计）
- `/profile/edit` — 编辑资料
- `/profile/personas` — 分身管理
- `/profile/stats` — 档案统计
- `/profile/resonance` — 共鸣页
- `/user/:username` — 他人主页
- `/settings` — 设置（通知/隐私/助手/显示/无障碍/开发者/关于）

**现有 metadata（v1）：** UserProfile + Persona 两个实体，字段不全。

### 4.2 聚合定义（补全后）

| 实体 | 角色 | 存储 | 说明 |
|------|------|------|------|
| **UserProfile** | 聚合根 | PostgreSQL | 用户核心档案，全局唯一 userId |
| **Persona** | 聚合成员 | PostgreSQL | 多分身，支持匿名/私密身份 |
| **UserAuth** | 聚合成员 | PostgreSQL | 认证凭证（密码 hash/OTP secret），安全隔离 |
| **UserDevice** | 聚合成员 | PostgreSQL | 设备绑定与推送 token，去重 |
| **UserSetting** | 聚合成员 | PostgreSQL | 通知 + 隐私设置，1:1 关系 |
| **ProfileUpdateProposal** | 聚合成员 | PostgreSQL | 助手/运营发起的资料修改提案，状态机 |

**为什么全部 PostgreSQL：**
- 认证和凭证需要强 ACID（不允许重复注册、token 泄露、并发冲突）
- Persona 激活需要排他约束（同一时刻只能有一个 isActive=true）
- ProfileUpdateProposal 是状态机（created → confirmed → applied/rejected），需乐观锁
- 设备去重（同 deviceId 不能重复注册）需唯一约束
- 数据量天然有限（用户数有限，每用户实体少量），PostgreSQL 完全承载
- **性能兼顾**：UserProfile + UserSetting + Persona 热数据走 Redis 缓存（TTL 600s）

### 4.3 实体详细设计

#### UserProfile（聚合根）

| 字段 | 类型 | 约束 | 分类 | 说明 |
|------|------|------|------|------|
| userId | string | PK | PUBLIC | 全局唯一用户 ID |
| phone | string | UK, NOT NULL | PII | 手机号（登录凭证） |
| nickname | string | UK, NOT NULL | PUBLIC | 昵称（搜索可用） |
| avatarUrl | string | NULL | PUBLIC | 头像 |
| bio | string | NULL | PUBLIC | 个人签名 |
| gender | enum | NULL | PII | male/female/other/unspecified |
| birthDate | date | NULL | PII | 出生日期 |
| region | string | NULL | PII | 地区（ipResidenceProfile 落库） |
| status | enum | NOT NULL | PUBLIC | active/suspended/deleted（状态机） |
| profileVersion | int | NOT NULL | PUBLIC | 画像快照版本号（端侧增量校验） |
| followerCount | int | NOT NULL, DEFAULT 0 | PUBLIC | 粉丝数（反范式） |
| followingCount | int | NOT NULL, DEFAULT 0 | PUBLIC | 关注数（反范式） |
| postCount | int | NOT NULL, DEFAULT 0 | PUBLIC | 发帖数（反范式） |
| createdAt | timestamp | NOT NULL | PUBLIC | |
| updatedAt | timestamp | NOT NULL | PUBLIC | |

**推荐特征字段**：bio, gender, region, followerCount, followingCount, postCount, createdAt

**搜索字段**：nickname, bio

#### Persona（聚合成员）

| 字段 | 类型 | 约束 | 分类 | 说明 |
|------|------|------|------|------|
| id | string | PK | PUBLIC | |
| userId | string | FK → user_profiles CASCADE | PUBLIC | |
| displayName | string | NOT NULL | PUBLIC | 分身显示名 |
| avatarUrl | string | NULL | PUBLIC | 分身头像 |
| isPrimary | bool | NOT NULL, DEFAULT false | PUBLIC | 主分身（不可删除） |
| isPrivate | bool | NOT NULL, DEFAULT false | PUBLIC | 私密分身 |
| isActive | bool | NOT NULL, DEFAULT false | PUBLIC | 当前激活 |
| createdAt | timestamp | NOT NULL | PUBLIC | |
| updatedAt | timestamp | NOT NULL | PUBLIC | |

**关系约束**：
- `UNIQUE(userId, isPrimary) WHERE isPrimary = true` — 每用户恰好一个主分身
- `UNIQUE(userId, isActive) WHERE isActive = true` — 每用户恰好一个激活分身
- FK `userId → user_profiles.user_id ON DELETE CASCADE`

#### UserAuth（聚合成员）

| 字段 | 类型 | 约束 | 分类 | 说明 |
|------|------|------|------|------|
| userId | string | PK + FK → user_profiles CASCADE | PUBLIC | 1:1 |
| passwordHash | string | NOT NULL | SECRET | bcrypt/argon2 hash |
| otpSecret | string | NULL | SECRET | TOTP 密钥 |
| refreshToken | string | NULL | SECRET | 当前有效 refresh token |
| refreshTokenExpiresAt | timestamp | NULL | PUBLIC | token 过期时间 |
| lastLoginAt | timestamp | NULL | PUBLIC | 最近登录时间 |
| lastLoginIp | string | NULL | PII | 最近登录 IP |
| loginFailCount | int | NOT NULL, DEFAULT 0 | PUBLIC | 连续登录失败次数 |
| lockedUntil | timestamp | NULL | PUBLIC | 账户锁定截止时间 |
| createdAt | timestamp | NOT NULL | PUBLIC | |
| updatedAt | timestamp | NOT NULL | PUBLIC | |

**安全设计**：
- 密码字段 classification=SECRET，log_policy=drop，api_exposure=drop，ops_exposure=drop
- 不缓存到 Redis
- loginFailCount 连续 5 次失败 → lockedUntil 设为 30 分钟后
- 额外 Redis 限流：`login_fail:{userId}` 滑动窗口

#### UserDevice（聚合成员）

| 字段 | 类型 | 约束 | 分类 | 说明 |
|------|------|------|------|------|
| id | string | PK | PUBLIC | |
| userId | string | FK → user_profiles CASCADE | PUBLIC | |
| deviceId | string | NOT NULL | PUBLIC | 设备标识 |
| platform | enum | NOT NULL | PUBLIC | ios/android |
| pushToken | string | NULL | PUBLIC | 推送 token |
| appVersion | string | NULL | PUBLIC | App 版本 |
| lastActiveAt | timestamp | NOT NULL | PUBLIC | 最近活跃时间 |
| createdAt | timestamp | NOT NULL | PUBLIC | |

**约束**：`UNIQUE(userId, deviceId)` — 同用户同设备不重复注册

**缓存**：`device_tokens:{userId}` Redis SET（推送时批量查询）

#### UserSetting（聚合成员）

| 字段 | 类型 | 约束 | 分类 | 说明 |
|------|------|------|------|------|
| userId | string | PK + FK → user_profiles CASCADE | PUBLIC | 1:1 |
| enablePush | bool | NOT NULL, DEFAULT true | PUBLIC | 开启推送 |
| enableMarketing | bool | NOT NULL, DEFAULT false | PUBLIC | 开启营销推送 |
| quietHoursStart | time | NULL | PUBLIC | 免打扰开始时间 |
| quietHoursEnd | time | NULL | PUBLIC | 免打扰结束时间 |
| allowStrangerMsg | bool | NOT NULL, DEFAULT true | PUBLIC | 允许陌生人消息 |
| profileVisibility | enum | NOT NULL, DEFAULT 'public' | PUBLIC | public/friends/private |
| contentLanguage | string | NULL | PUBLIC | 内容语言偏好（超前） |
| feedPreference | enum | NULL | PUBLIC | recommend/chronological（超前） |
| assistantEnabled | bool | NOT NULL, DEFAULT true | PUBLIC | 小趣助手开关 |
| updatedAt | timestamp | NOT NULL | PUBLIC | |

#### ProfileUpdateProposal（聚合成员）

| 字段 | 类型 | 约束 | 分类 | 说明 |
|------|------|------|------|------|
| id | string | PK | PUBLIC | |
| userId | string | FK → user_profiles CASCADE | PUBLIC | |
| source | enum | NOT NULL | PUBLIC | assistant/ops/user |
| proposedChanges | jsonb | NOT NULL | SENSITIVE | 拟修改的字段和值 |
| status | enum | NOT NULL | PUBLIC | created/confirmed/applied/rejected |
| reviewedBy | string | NULL | PUBLIC | 审核人（运营场景） |
| version | int | NOT NULL, DEFAULT 1 | PUBLIC | 乐观锁版本号 |
| createdAt | timestamp | NOT NULL | PUBLIC | |
| resolvedAt | timestamp | NULL | PUBLIC | |

**状态机**：`created → confirmed → applied` 或 `created → rejected`
- 并发安全：`UPDATE ... WHERE id = ? AND version = ?`（乐观锁）

### 4.4 关系映射总览（PostgreSQL）

```
user_profiles (PK: user_id)
    │
    ├── 1:N → personas (FK: user_id, CASCADE)
    │         UNIQUE(user_id, is_primary) WHERE is_primary
    │         UNIQUE(user_id, is_active) WHERE is_active
    │
    ├── 1:1 → user_auth (PK=FK: user_id, CASCADE)
    │
    ├── 1:N → user_devices (FK: user_id, CASCADE)
    │         UNIQUE(user_id, device_id)
    │
    ├── 1:1 → user_settings (PK=FK: user_id, CASCADE)
    │
    └── 1:N → profile_update_proposals (FK: user_id, CASCADE)
              INDEX(user_id, status) WHERE status IN ('created','confirmed')
```

**常用 JOIN 路径**（codegen 生成查询方法）：
- `user_with_active_persona`：UserProfile LEFT JOIN Persona WHERE isActive=true
- `user_with_settings`：UserProfile INNER JOIN UserSetting
- `user_full_snapshot`：UserProfile + 激活 Persona + UserSetting（供 Profile API 返回）

### 4.5 超前设计

| 能力 | 当前状态 | 超前字段/设计 | 用途 |
|------|---------|-------------|------|
| **画像版本化** | spec 提到 profileVersion | profileVersion int 字段 | 端侧增量拉取 |
| **地区识别** | spec 提到 ipResidenceProfile | region 字段 | 推荐本地化 |
| **内容语言偏好** | 未实现 | UserSetting.contentLanguage | 多语言推荐 |
| **Feed 偏好** | 未实现 | UserSetting.feedPreference | 时间线/推荐切换 |
| **助手开关** | 未实现 | UserSetting.assistantEnabled | 小趣个性化开关 |
| **帖子计数** | 未实现 | UserProfile.postCount | 个人主页展示 |
| **OAuth 绑定** | 未实现 | UserAuth 可扩展 oauthProviders JSONB | 第三方登录 |
| **两步验证** | 未实现 | UserAuth.otpSecret | 安全增强 |

---

## 5. 聚合 B：Post（内容）

### 5.1 当前实现分析

**已有接口（content-service OpenAPI + spec）：**
- `GET /v1/content/feed` — 发现流（type=moment|photo|video|article, cursor 分页, 推荐排序）
- `POST /v1/content/posts` — 发布内容（spec 定义）
- `POST /v1/content/behaviors` — 行为批量上报（impression/click/dwell/like/favorite/dislike/report/share）
- `GET/POST/DELETE /v1/content/posts/{postId}/comments` — 评论 CRUD
- `GET /v1/content/posts/{postId}/reactions` — 互动状态读取
- `GET /v1/content/posts/{postId}/counters` — 聚合计数
- `GET /v1/content/media/{mediaId}` — 媒体资产状态
- `GET /v1/content/helper-read/{contentId}` — 帮读摘要（spec 定义）
- `POST /v1/content/recommend` — 推荐（spec 定义）

**App 端页面：**
- `/` — 发现页（微趣/美图/视频/文章四个 tab）
- `/article/:id` — 文章详情
- `/media-viewer/:category/:index` — 沉浸式图片查看器
- `/video-viewer/:index` — 沉浸式视频查看器
- 创作入口：6 种创作类型编辑器

**现有 FeedItem 字段**：id, type(moment/image/video/article), authorId, caption, images[], videoUrl, createdAt, counters{likeCount, commentCount, favoriteCount, shareCount}, metadata{}

### 5.2 聚合定义

| 实体 | 角色 | 存储 | 说明 |
|------|------|------|------|
| **Post** | 聚合根 | MongoDB | 内容主体（图片/视频/微趣/文章） |
| **Comment** | 聚合成员 | MongoDB | 评论与回复（楼中楼） |
| **MediaAsset** | 聚合成员 | MongoDB | 媒体资源（异步处理管线） |
| **ContentReaction** | 聚合成员 | MongoDB | 用户互动状态（点赞/收藏/转发/举报） |

**为什么全部 MongoDB：**
- 内容是全站最高并发场景（浏览、点赞、评论）
- 文档模型天然适合内容嵌套（Post → Comments → Replies）
- 水平扩展支撑增长
- ContentReaction 通过 MongoDB unique compound index 保证幂等
- **性能兼顾**：Post 热数据 + ReactionState 走 Redis 缓存

### 5.3 实体详细设计

#### Post（聚合根）

| 字段 | 类型 | 说明 | 推荐特征 |
|------|------|------|----------|
| _id | ObjectId | | |
| authorId | string | 发布者 | ✓ |
| personaId | string | 发布时使用的分身 | |
| contentType | enum: image/video/micro/article | 内容类型 | ✓ |
| title | string | 标题（文章必填，其他可选） | ✓ |
| body | string | 正文/描述 | |
| tags | []string | 内容标签（tag_taxonomy 约束） | ✓ |
| mediaUrls | []string | 媒体 URL 列表 | |
| coverUrl | string | 封面图 | |
| videoUrl | string | 视频 URL | |
| location | GeoPoint | 地理位置 | ✓ |
| locationName | string | 地点名称（搜索可用） | ✓ |
| status | enum: draft/pending_review/published/archived/deleted | 发布状态机 | |
| visibility | enum: public/friends/private/circle | 可见性 | |
| circleId | string | 关联圈子（圈子内发帖） | ✓ |
| likeCount | int | 点赞数（反范式） | ✓ |
| commentCount | int | 评论数 | ✓ |
| favoriteCount | int | 收藏数 | ✓ |
| shareCount | int | 分享数 | ✓ |
| viewCount | int | 浏览数 | ✓ |
| embedding | []float32 | 内容语义向量（1536维） | |
| helperReadSummary | string | 帮读摘要缓存 | |
| moderationStatus | enum: pending/approved/rejected | 审核状态 | |
| createdAt | timestamp | | ✓ |
| updatedAt | timestamp | | |
| publishedAt | timestamp | 发布时间（排序用） | ✓ |

**超前字段**：
- `visibility` — 支持好友可见/私密/圈子内可见
- `circleId` — 圈子内发帖关联
- `locationName` — 地点搜索 + 助手出行规划
- `helperReadSummary` — 帮读摘要缓存避免重复 LLM 调用
- `moderationStatus` — 内容安全审核流水线

#### Comment（聚合成员）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| postId | ObjectId | 所属帖子（parent ref） |
| authorId | string | 评论者 |
| personaId | string | 评论时的分身 |
| content | string | 评论内容 |
| replyToCommentId | ObjectId | 回复的评论 ID（楼中楼） |
| replyToUserId | string | 回复的用户 ID |
| likeCount | int | 评论点赞数 |
| status | enum: visible/deleted/hidden | |
| createdAt | timestamp | |

#### MediaAsset（聚合成员）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| postId | ObjectId | 所属帖子 |
| type | enum: image/video/audio | 媒体类型 |
| originUrl | string | 原始文件 URL |
| cdnUrl | string | CDN 加速 URL |
| thumbnailUrl | string | 缩略图（超前：视频帧、图片裁剪） |
| width | int | 原始宽度 |
| height | int | 原始高度 |
| durationMs | int | 视频时长（毫秒） |
| fileSizeBytes | int | 文件大小 |
| mimeType | string | MIME 类型 |
| status | enum: uploaded/processing/ready/failed | 处理状态 |
| moderationStatus | enum: pending/approved/rejected | 审核状态 |
| derivatives | []object | 转码/缩略图衍生物 |
| createdAt | timestamp | |

#### ContentReaction（聚合成员）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| postId | ObjectId | 所属帖子 |
| userId | string | 操作用户 |
| liked | bool | 已点赞 |
| favorited | bool | 已收藏 |
| shared | bool | 已分享 |
| reported | bool | 已举报 |
| likedAt | timestamp | 点赞时间 |
| favoritedAt | timestamp | 收藏时间 |
| updatedAt | timestamp | |

**索引**：`UNIQUE(postId, userId)` — 幂等保证
**更新模式**：MongoDB `upsert` + `$set`

**计数同步策略**：
- 点赞/收藏操作 → 更新 ContentReaction + Redis 原子递增 `counter:{postId}:{type}`
- 异步批量回写 Post 文档的 likeCount/favoriteCount 等
- 避免热点 Post 高频更新导致的 MongoDB 写锁竞争

### 5.4 超前设计

| 能力 | 说明 |
|------|------|
| **多分身发布** | personaId 关联，支持匿名/私密身份发内容 |
| **圈子内发帖** | circleId 字段，圈子动态流直接过滤 |
| **内容审核管线** | moderationStatus 状态机，支撑自动+人工审核 |
| **帮读摘要缓存** | helperReadSummary 避免重复 LLM 调用 |
| **评论楼中楼** | replyToCommentId + replyToUserId 支撑完整评论树 |
| **媒体衍生物** | derivatives 数组支撑多规格缩略图/转码 |
| **向量化** | embedding 字段，内容创建时异步生成，供推荐+助手语义检索 |

---

## 6. 聚合 C：Conversation（会话）

### 6.1 当前实现分析

**已有接口（chat-service）：**
- 会话 CRUD（list/create/get）、消息收发、联系人列表/搜索
- 群聊创建、成员增删、会话设置（mute/pin）
- 会话类型：direct/group/circle/encrypted/assistant

**App 端页面：**
- `/chat` — 趣聊（全部/@我/未读/密信 tab）+ 小趣助手置顶会话
- `/chat/:id` — 聊天详情
- `/chat/:id/settings` — 聊天设置
- `/chat/:id/add-members` — 创建群聊

### 6.2 聚合定义

| 实体 | 角色 | 存储 | 说明 |
|------|------|------|------|
| **Conversation** | 聚合根 | MongoDB | 会话（直聊/群聊/圈子聊/加密/助手） |
| **Message** | 聚合成员 | MongoDB | 消息 |

**为什么 MongoDB**：
- 消息写入极高并发（每条消息一次写入）
- 消息按时间倒序分页，文档模型 + 索引天然适合
- 群聊成员列表嵌入 Conversation 文档（成员数通常 < 500）

### 6.3 实体详细设计

#### Conversation（聚合根）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| type | enum: direct/group/circle/encrypted/assistant | 会话类型 |
| title | string | 群聊名称 |
| avatarUrl | string | 群聊头像 |
| creatorId | string | 创建者 |
| memberIds | []string | 成员 ID 列表 |
| members | []ConversationMember | 成员详情（嵌入文档） |
| circleId | string | 关联圈子（type=circle 时） |
| assistantSkillId | string | 关联 Skill（type=assistant 时，超前） |
| lastMessageId | ObjectId | 最新消息 ID |
| lastMessagePreview | string | 最新消息预览 |
| lastMessageTime | timestamp | 最新消息时间（排序用） |
| messageCount | int | 消息总数 |
| settings | ConversationSettings | 会话级设置（嵌入） |
| status | enum: active/archived/deleted | |
| createdAt | timestamp | |
| updatedAt | timestamp | |

**ConversationMember（嵌入文档）：**
- userId, displayName, avatarUrl, role(owner/admin/member), joinedAt, mutedUntil

**ConversationSettings（嵌入文档）：**
- muted, pinned, readCursor(messageId)

#### Message（聚合成员）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| conversationId | ObjectId | 所属会话 |
| senderId | string | 发送者 |
| senderPersonaId | string | 发送时分身 |
| type | enum: text/image/video/card/system/assistant | 消息类型 |
| content | string | 文本内容 |
| mediaUrl | string | 媒体 URL |
| cardPayload | object | 卡片内容（超前：助手卡片、圈子邀请等） |
| replyToMessageId | ObjectId | 引用回复 |
| mentions | []string | @提到的用户 ID |
| status | enum: sent/delivered/read/recalled | 消息状态 |
| recalledAt | timestamp | 撤回时间 |
| metadata | object | 扩展元数据 |
| timestamp | timestamp | 发送时间（排序用） |

### 6.4 超前设计

| 能力 | 说明 |
|------|------|
| **加密会话** | type=encrypted，端到端加密消息 |
| **助手会话** | type=assistant，小趣助手置顶会话 + Skill 关联 |
| **圈子聊天** | type=circle + circleId，圈子绑定群聊 |
| **卡片消息** | type=card + cardPayload，助手行动卡片/圈子邀请/内容分享卡 |
| **消息引用** | replyToMessageId，支持引用回复 |
| **@提醒** | mentions 数组，触发通知 |
| **消息撤回** | status=recalled + recalledAt |
| **多分身聊天** | senderPersonaId，不同分身在不同会话中 |

---

## 7. 聚合 D：Circle（圈子）

### 7.1 当前实现分析

**已有接口（circle-service）：**
- 圈子 CRUD + 活动流 + 成员管理 + 权限 + 行为上报
- 圈子列表（分类维度）、详情、圈子内推荐排序

**App 端页面：**
- `/circles` — 圈子（分类维度 + 推荐圈子 + 活动流 + 瀑布帖卡片）
- `/circle/:id` — 圈子详情
- `/circle/:id/stats` — 圈子统计

### 7.2 聚合定义

| 实体 | 角色 | 存储 | 说明 |
|------|------|------|------|
| **Circle** | 聚合根 | MongoDB | 圈子 |
| **CircleMember** | 聚合成员 | MongoDB | 圈子成员 |

### 7.3 实体详细设计

#### Circle（聚合根）

| 字段 | 类型 | 说明 | 推荐特征 |
|------|------|------|----------|
| _id | ObjectId | | |
| name | string | 圈子名称 | ✓ |
| description | string | 圈子描述 | ✓ |
| coverUrl | string | 封面图 | |
| ownerId | string | 创建者 | |
| category | string | 圈子分类（兴趣/本地/行业等） | ✓ |
| tags | []string | 圈子标签（tag_taxonomy） | ✓ |
| memberCount | int | 成员数（反范式） | ✓ |
| postCount | int | 帖子数 | ✓ |
| weeklyActiveCount | int | 周活跃成员数（超前） | ✓ |
| status | enum: active/archived/deleted | | |
| visibility | enum: public/private/invite_only | 可见性（超前） | |
| joinPolicy | enum: open/approval/invite | 加入策略（超前） | |
| conversationId | ObjectId | 关联群聊（超前） | |
| createdAt | timestamp | | ✓ |
| updatedAt | timestamp | | |

#### CircleMember（聚合成员）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| circleId | ObjectId | 所属圈子 |
| userId | string | 成员 |
| role | enum: owner/admin/member | 角色 |
| joinedAt | timestamp | 加入时间 |
| lastActiveAt | timestamp | 最近活跃（超前） |
| contribution | int | 贡献值（发帖/互动积分，超前） |

**索引**：`UNIQUE(circleId, userId)`

### 7.4 超前设计

| 能力 | 说明 |
|------|------|
| **可见性与加入策略** | visibility + joinPolicy，支持私密圈子 + 审批加入 |
| **圈子绑定群聊** | conversationId 关联 Conversation（type=circle） |
| **周活跃统计** | weeklyActiveCount，推荐活跃圈子 |
| **贡献值** | CircleMember.contribution，圈子内排行 |

---

## 8. 聚合 E：AssistantRun（助手）

### 8.1 当前实现分析

**已有接口（assistant-service）：**
- `POST /v1/assistant/runs` / `runs/stream` — Run 同步/流式
- `POST /v1/assistant/learning/events` — 交互事件上报
- `POST /v1/assistant/learning/scorecards` — 评分卡上报
- `GET /v1/assistant/policy` — 策略拉取
- historicalRetrievalFeedback 注入上下文

**App 端页面：**
- `/assistant` — 助手主页（记忆/任务/技能 tab）
- `/assistant/management` — 助手管理
- 浮窗半屏助手（assistant_half_sheet）

**App 端 personal_assistant 模块**：
- Retrieval providers（web/memory/conversation/page context）
- LLM providers（OpenAI/local heuristic）
- Embedding/Learning/Memory/Skill market

### 8.2 聚合定义

| 实体 | 角色 | 存储 | 说明 |
|------|------|------|------|
| **AssistantRun** | 聚合根 | MongoDB | 一次助手会话执行 |
| **InteractionEvent** | 聚合成员 | MongoDB | 交互事件与反馈 |

### 8.3 实体详细设计

#### AssistantRun（聚合根）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| userId | string | 用户 |
| sessionId | string | 会话 session |
| skillId | string | 使用的 Skill |
| pageType | string | 触发时的页面类型 |
| pageObjectId | string | 触发时的业务对象 ID |
| triggerType | enum: user_query/suggested_action/skill_select | 触发方式 |
| userQuery | string | 用户原始输入 |
| contextSnapshot | object | 三层上下文快照（JSONB） |
| responseType | enum: text/structured/action_card/stream | 输出类型 |
| responseText | string | 文本输出 |
| responsePayload | object | 结构化输出 |
| toolsCalled | []string | 调用的 Tool 列表 |
| llmModel | string | 使用的 LLM 模型 |
| llmTokensUsed | int | token 消耗 |
| latencyMs | int | 总延迟 |
| status | enum: running/completed/failed/cancelled | |
| satisfactionScore | float | 用户满意度评分 |
| contextEmbedding | []float32 | 上下文向量（RAG 检索用） |
| createdAt | timestamp | |
| completedAt | timestamp | |

#### InteractionEvent（聚合成员）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| runId | ObjectId | 所属 run |
| userId | string | |
| eventType | enum: query/response/feedback/action_click/skill_trigger/tool_call/error | 事件类型 |
| payload | object | 事件载荷 |
| feedbackType | enum: thumbs_up/thumbs_down/rating/text | 反馈类型 |
| feedbackScore | float | 反馈分数 |
| feedbackText | string | 反馈文本 |
| traceId | string | OTEL trace 关联 |
| timestamp | timestamp | |

### 8.4 超前设计

| 能力 | 说明 |
|------|------|
| **页面感知** | pageType + pageObjectId，记录触发上下文 |
| **Tool 调用审计** | toolsCalled 列表，追溯 Skill 调用的 Tool |
| **LLM 成本追踪** | llmModel + llmTokensUsed，成本归因 |
| **上下文向量** | contextEmbedding，历史 run 语义检索（RAG） |
| **结构化反馈** | feedbackType/Score/Text 多维反馈，驱动学习闭环 |

---

## 9. 独立实体

### 9.1 FollowEdge（user domain, MongoDB）

| 字段 | 类型 | 说明 |
|------|------|------|
| followerId | string | 关注者 |
| followeeId | string | 被关注者 |
| source | string | 关注来源（profile/recommendation/circle，超前） |
| createdAt | timestamp | |

- `UNIQUE(followerId, followeeId)` — 幂等
- 关注/取关同步更新 UserProfile.followerCount/followingCount（跨聚合事件）
- **为什么 MongoDB**：社交图谱高并发查询 + 水平扩展

### 9.2 BlockEdge（user domain, PostgreSQL）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string PK | |
| blockerId | string | 屏蔽者 |
| blockedId | string | 被屏蔽者 |
| reason | string | 屏蔽原因 |
| createdAt | timestamp | |

- `UNIQUE(blockerId, blockedId)`
- **为什么 PostgreSQL**：屏蔽必须强一致即时生效，数据量小
- **Redis 缓存**：`blocked_set:{userId}` SET，消息/推荐/搜索时 O(1) 检查
- **跨域影响**：聊天过滤、推荐过滤、搜索过滤、评论屏蔽

### 9.3 Report（content domain, PostgreSQL）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string PK | |
| reporterId | string | 举报人 |
| targetType | enum: post/comment/user/circle/message | 目标类型 |
| targetId | string | 目标 ID |
| reason | enum: spam/harassment/violence/adult/copyright/other | 举报原因 |
| description | string | 补充描述 |
| status | enum: pending/reviewing/resolved/dismissed | 状态机 |
| reviewerId | string | 审核人 |
| resolution | enum: warn/delete_content/suspend_user/ban/dismiss | 处置结果 |
| createdAt | timestamp | |
| resolvedAt | timestamp | |

- **为什么 PostgreSQL**：合规审计不可丢失 + 状态机需 ACID
- **超前**：支持举报消息（targetType=message）

### 9.4 Notification（notification domain, MongoDB）

| 字段 | 类型 | 说明 |
|------|------|------|
| _id | ObjectId | |
| userId | string | 接收人 |
| type | enum: social/content/circle/system/assistant | 通知类型 |
| title | string | 标题 |
| body | string | 正文 |
| senderUserId | string | 触发者（社交互动场景） |
| targetType | string | 关联目标类型 |
| targetId | string | 关联目标 ID |
| actionUrl | string | 点击跳转 URL（超前：deep link） |
| read | bool | 已读 |
| dismissed | bool | 已忽略 |
| pushSent | bool | 已发送推送（超前） |
| createdAt | timestamp | |
| readAt | timestamp | |

- **为什么 MongoDB**：通知写入量极大（每次互动产生），需水平扩展
- INDEX: `(userId, read, createdAt DESC)`
- **超前**：actionUrl 支持 deep link，pushSent 追踪推送状态

### 9.5 SkillConsent（assistant domain, PostgreSQL）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string PK | |
| userId | string | 用户 |
| skillId | string | Skill ID |
| grantedScope | jsonb | 授权范围（上下文维度 + tool 权限） |
| grantedAt | timestamp | 授权时间 |
| revokedAt | timestamp | 撤销时间（NULL 表示生效中） |

- `UNIQUE(userId, skillId) WHERE revokedAt IS NULL`
- **为什么 PostgreSQL**：授权决策必须准确一致

### 9.6 VisitRecord（product-ops domain, MongoDB）

| 字段 | 类型 | 说明 |
|------|------|------|
| userId | string | |
| targetType | string | 目标类型（page/post/circle/user） |
| targetKey | string | 目标标识 |
| visitCount | int | 访问次数 |
| lastSeenAt | timestamp | 最近访问 |
| sessionId | string | 会话 ID（超前） |
| source | string | 来源（feed/search/share/notification，超前） |
| timestamp | timestamp | |

### 9.7 ExperimentBucket（product-ops domain, PostgreSQL）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string PK | |
| experimentId | string | 实验 ID |
| userId | string | 用户 |
| variant | string | 分桶变体 |
| assignedAt | timestamp | |

- `UNIQUE(experimentId, userId)` — 分桶确定性
- **为什么 PostgreSQL**：分桶结果需确定性和一致性

---

## 10. 衍生物：ReadModel / 向量 / Redis

### 10.1 ReadModel（Projector 投影构建）

| ReadModel | 数据来源 | 存储 | 消费者 |
|-----------|---------|------|--------|
| **DiscoveryFeed** | Post + 用户行为 + 推荐特征 | MongoDB | App 信息流 |
| **CircleFeed** | Circle + Post + 成员行为 | MongoDB | 圈子动态 |
| **ChatInbox** | Conversation + Message | MongoDB | 聊天列表 |
| **UserProfileView** | UserProfile + 标签 + 行为统计 | MongoDB | 画像（推荐/助手） |
| **RecommendFeature** | 多源聚合 | MongoDB | 推荐引擎特征宽表 |

### 10.2 向量存储

| Entity | 来源 | 维度 | 用途 |
|--------|------|------|------|
| **ContentEmbedding** | Post 内容 → Embedding API | 1536 | 内容相似推荐 + 助手语义检索 |
| **UserContextEmbedding** | 用户画像 + 行为 → Embedding API | 1536 | 用户兴趣匹配 + 助手个性化 |

### 10.3 Redis 键空间

| 键模式 | 用途 | TTL |
|--------|------|-----|
| `cache:{entity}:{id}` | 实体读缓存 | 按 entity 配置 |
| `rec:session_signals:{uid}:{sid}` | 推荐热路径实时信号 | 30min |
| `rec:exposed:{uid}:{sid}` | 已曝光内容 ID | 30min |
| `rec:negative:{uid}:{sid}` | 负反馈过滤集 | 24h |
| `rec:realtime_interest:{uid}:{sid}` | 实时兴趣向量 | 30min |
| `page_ctx:{uid}` | 页面上下文 | 5min |
| `content_analysis:{postId}` | 内容分析缓存 | 24h |
| `blocked_set:{uid}` | 屏蔽用户列表 | 1h |
| `device_tokens:{uid}` | 设备推送 token | 1h |
| `login_fail:{uid}` | 登录失败滑动窗口 | 30min |
| `counter:{postId}:{type}` | 热点内容计数缓冲 | 无（异步回写） |
| `reaction:{uid}:{postId}` | 互动状态缓存 | 5min |

---

## 11. 存储选型总览

### 11.1 PostgreSQL 实体完整列表

| 实体 | 聚合 | 关系 | 事务需求 |
|------|------|------|----------|
| UserProfile | 聚合根 | — | 注册唯一性、状态机 |
| Persona | UserProfile 成员 | FK → user_profiles CASCADE | 激活排他约束 |
| UserAuth | UserProfile 成员 | 1:1 FK → user_profiles CASCADE | 凭证 ACID |
| UserDevice | UserProfile 成员 | FK → user_profiles CASCADE | 设备去重 |
| UserSetting | UserProfile 成员 | 1:1 FK → user_profiles CASCADE | 设置持久化 |
| ProfileUpdateProposal | UserProfile 成员 | FK → user_profiles CASCADE | 状态机+乐观锁 |
| BlockEdge | 独立 | — | 屏蔽即时生效 |
| Report | 独立 | — | 合规审计 |
| SkillConsent | 独立 | — | 授权准确性 |
| ExperimentBucket | 独立 | — | 分桶确定性 |

### 11.2 MongoDB 实体完整列表

| 实体 | 聚合 | 唯一约束 | 并发特征 |
|------|------|---------|----------|
| Post | 聚合根 | — | 高写入+高读取 |
| Comment | Post 成员 | — | 高写入 |
| MediaAsset | Post 成员 | — | 写入后不可变 |
| ContentReaction | Post 成员 | (postId, userId) | 极高并发写 |
| Conversation | 聚合根 | — | 中等写入 |
| Message | Conversation 成员 | — | 极高并发写 |
| Circle | 聚合根 | — | 低写入高读取 |
| CircleMember | Circle 成员 | (circleId, userId) | 中等写入 |
| AssistantRun | 聚合根 | — | 中等写入 |
| InteractionEvent | AssistantRun 成员 | — | 高写入 |
| FollowEdge | 独立 | (followerId, followeeId) | 中等写入 |
| Notification | 独立 | — | 极高写入 |
| VisitRecord | 独立 | — | 极高写入 |
| domain_events | Event Store | (aggregateId, version) | 高写入 |

### 11.3 性能与可扩展性保障

| 策略 | 适用场景 | 实现 |
|------|---------|------|
| **Redis 读缓存** | 所有 PostgreSQL 高频读实体 | Repository cache 中间件，TTL 由 metadata 驱动 |
| **Redis 原子计数** | 热点 Post 的 like/comment/share count | Redis INCR + 异步批量回写 MongoDB |
| **Redis 布隆过滤** | 已曝光内容去重（超大集合时） | 当 exposed set > 10000 时降级为布隆过滤器 |
| **MongoDB 分片** | Post/Message/Notification 超大集合 | 按 createdAt range 或 hash 分片 |
| **PostgreSQL 读副本** | 用户画像/设置高频读 | 读请求路由到只读副本 |
| **跨库避免 JOIN** | PG ↔ Mongo 数据关联 | 通过 ReadModel 物化视图预聚合 |

---

## 12. 契约测试策略

### 12.1 总体原则

元数据驱动的契约测试是整个 runtime 框架质量保障的核心手段。测试基于元数据聚焦**接口契约**。

**核心决策：服务侧使用真实测试数据库，不 mock 存储层。**

- 数据库/缓存使用**命令兼容的轻量测试引擎**，无需修改业务代码，仅切换配置
- 每次测试前预制数据、跑完清理，保证测试隔离
- 只 mock **跨服务调用**和**外部 AI 服务**（LLM/Embedding API），不 mock 本服务的存储

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        元数据驱动契约测试架构                                  │
│                                                                              │
│  ┌─ 端侧（App）───────────────────┐  ┌─ 服务侧（Service）───────────────┐  │
│  │                                 │  │                                   │  │
│  │  fields.yaml → mock API 响应    │  │  storage.yaml → 真实测试数据库     │  │
│  │  service.yaml → 路由 + 断言     │  │  events.yaml → 事件捕获断言       │  │
│  │                                 │  │  fields.yaml → 预制数据工厂       │  │
│  │  隔离边界：                      │  │                                   │  │
│  │  App ←mock→ 云端 API            │  │  真实存储引擎（轻量测试版本）：     │  │
│  │  不依赖任何真实服务               │  │    PG: embedded-postgres          │  │
│  │                                 │  │    Mongo: testcontainers (mongo)   │  │
│  │  Dart mock_api_client           │  │    Redis: miniredis/v2            │  │
│  │  从 fields.yaml 生成 JSON       │  │                                   │  │
│  │                                 │  │  隔离边界：                        │  │
│  │                                 │  │  服务 → 真实本地存储               │  │
│  │                                 │  │  服务 ←mock→ 其它服务 / AI API    │  │
│  └─────────────────────────────────┘  └───────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 12.2 测试数据库引擎选型

**原则：命令/协议完全兼容生产引擎，无需修改业务代码，仅通过配置切换连接地址。**

| 生产引擎 | 测试引擎 | Go 依赖包 | 特点 | 启动速度 |
|---------|---------|----------|------|---------|
| **PostgreSQL 16** | embedded-postgres | `github.com/fergusstrange/embedded-postgres` | 真实 PG 二进制，进程内启动，支持完整 SQL（窗口函数/CTE/JSONB/部分索引） | ~2s 冷启动 |
| **MongoDB 7** | testcontainers (mongo) | `github.com/testcontainers/testcontainers-go/modules/mongodb` | 真实 mongod 容器，支持完整功能（Change Stream/Atlas Search/事务） | ~3s（镜像缓存后） |
| **Redis 7** | miniredis/v2 | `github.com/alicebob/miniredis/v2` | 纯 Go 内存实现，TCP 兼容，支持 STRING/HASH/SET/SORTED SET/TTL/Lua 脚本 | <1ms |

**为什么不全部 mock：**
- mock 无法验证真实的 SQL 语法、索引命中、唯一约束冲突、事务隔离
- mock 无法验证 MongoDB 的 upsert 语义、compound index、Change Stream 行为
- mock 无法验证 Redis 的 TTL 过期、原子操作、数据结构语义
- 使用真实引擎测试，发现的问题更接近生产环境

**为什么不用 testcontainers 全部覆盖：**
- embedded-postgres 比 Docker 容器更快启动（2s vs 5s+）、无 Docker 依赖
- miniredis 纯 Go 内存实现，<1ms 启动，比 Redis 容器快 1000x
- MongoDB 无可靠的纯 Go 内存替代，testcontainers 是最佳选择

### 12.3 测试生命周期与数据管理

```
┌─ TestMain (per package) ─────────────────────────────────────────────────┐
│                                                                          │
│  1. 启动测试引擎                                                          │
│     embedded-postgres → Start() → 真实 PG 实例（随机端口）                │
│     testcontainers    → mongodb.Run() → Mongo 容器（随机端口）            │
│     miniredis         → miniredis.Run() → 内存 Redis（随机端口）          │
│                                                                          │
│  2. 执行 migration                                                       │
│     从 storage.yaml 生成的 DDL → 创建表/集合/索引                         │
│                                                                          │
│  3. 初始化 Repository（生产代码，零修改）                                  │
│     pgxpool.New(embeddedPG.ConnectionString())                           │
│     mongo.Connect(testcontainer.ConnectionString())                      │
│     redis.NewClient(&redis.Options{Addr: miniredis.Addr()})             │
│                                                                          │
│  ┌─ t.Run("scenario_name") ──────────────────────────────────────────┐  │
│  │                                                                    │  │
│  │  4. Seed：从 fields.yaml 生成的 fixture 工厂预制测试数据           │  │
│  │     fixture.NewUserProfile() → INSERT INTO user_profiles ...       │  │
│  │     fixture.NewPost()        → db.posts.InsertOne(...)             │  │
│  │                                                                    │  │
│  │  5. Execute：调用 Application Service / HTTP Handler              │  │
│  │     真实代码路径：Handler → Service → Repository → 真实数据库      │  │
│  │                                                                    │  │
│  │  6. Assert：验证数据库状态 + 事件 + API 响应                       │  │
│  │     SELECT * FROM user_profiles WHERE user_id = ?                  │  │
│  │     db.posts.FindOne({_id: ...})                                   │  │
│  │     miniredis.Get("cache:user_profile:xxx")                        │  │
│  │     eventCapture.AssertPublished("UserProfileUpdated", payload)    │  │
│  │                                                                    │  │
│  │  7. Cleanup：清理本次测试数据                                      │  │
│  │     PG:    TRUNCATE user_profiles, personas, ... CASCADE           │  │
│  │     Mongo: db.posts.Drop() / db.posts.DeleteMany({})              │  │
│  │     Redis: miniredis.FlushAll()                                    │  │
│  │                                                                    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  8. 关闭测试引擎                                                          │
│     embeddedPG.Stop() / container.Terminate() / miniredis.Close()        │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**数据清理策略**：

| 引擎 | 清理方式 | 性能 | 说明 |
|------|---------|------|------|
| **PostgreSQL** | `TRUNCATE ... CASCADE` | ~1ms | 级联清空全部关联表，比 DELETE 快 |
| **MongoDB** | `collection.DeleteMany({})` | ~1ms | 清空集合数据但保留索引 |
| **Redis** | `miniredis.FlushAll()` | <0.1ms | 内存清空 |

**另一方案（PG 事务回滚）**：
- 对于只读或简单写测试，可用 `BEGIN` → 测试 → `ROLLBACK` 实现零残留
- 适用于不涉及事务嵌套的场景

### 12.4 端侧契约测试（App Side）

**目标**：App 自身不依赖云端运行测试，验证 API 契约遵从。

**隔离策略**：
- mock 目标：对应服务的 REST API（端侧无真实数据库，仅 mock 接口）
- mock 数据来源：`fields.yaml`（自动生成符合 constraints/classification 的 JSON）
- 不 mock：App 内部逻辑（状态管理、UI 渲染、本地存储）

**测试场景示例**（以 UserProfile 为例）：

| 场景 | 路由 | 断言 |
|------|------|------|
| 获取档案 | `GET /v1/user/profile/{userId}` | 200 + schema 匹配 + PII 字段已过滤 |
| 更新资料 | `PATCH /v1/user/profile` | 200 + 仅 writable_fields 可写 |
| 分身激活 | `POST /v1/user/personas/{id}/activate` | 200 + 同一时刻仅一个 active |
| 登录流程 | `POST /v1/user/auth/login` | 200 + tokens 返回 |

**mock 数据生成规则**（端侧和服务侧预制数据共用）：

```
fields.yaml constraints → 测试数据生成：
  PK        → UUID / ObjectId
  NOT_NULL  → 必填（类型推导默认值）
  NULLABLE  → 50% 概率为 null
  UNIQUE    → 全局唯一
  DEFAULT_* → 使用默认值

fields.yaml classification → 安全断言：
  SECRET    → api_exposure 必须为 drop，断言不出现在响应中
  PII       → 端侧断言不出现或已脱敏
  SENSITIVE → ops_exposure 断言为 mask
```

### 12.5 服务侧契约测试（Service Side）

**目标**：服务只依赖自身的真实存储，不依赖其它服务接口调用。

**隔离层级**：

| 层 | 真实 or Mock | 说明 |
|----|-------------|------|
| **HTTP Handler** | 真实 | httptest.NewServer 启动真实路由 |
| **Application Service** | 真实 | 真实业务逻辑 |
| **Domain Model** | 真实 | 真实领域模型 |
| **Repository** | 真实 | 真实 Repository 实现，连接测试引擎 |
| **PostgreSQL** | 真实（embedded-postgres） | 完整 SQL 引擎 |
| **MongoDB** | 真实（testcontainers mongo） | 完整 mongod |
| **Redis** | 真实（miniredis/v2） | 命令兼容内存引擎 |
| **EventPublisher** | 捕获 spy | 真实发布，但写入内存 capture 而非 MQ |
| **其它服务 API** | mock | 隔离跨服务依赖 |
| **LLM / Embedding API** | mock | 隔离外部 AI 服务 |

**测试场景示例**（以 Post 为例）：

| 场景 | Command/Query | 断言（真实数据库验证） |
|------|--------------|---------------------|
| 创建内容 | `CreatePost` | MongoDB `db.posts.FindOne()` 验证持久化 + MediaAsset 存在 + PostCreated 事件捕获 |
| 互动 + 计数 | `ReactToContent (like)` | MongoDB upsert 验证 ContentReaction + `miniredis.Get("counter:{postId}:like")` 验证递增 + 事件捕获 |
| 唯一约束 | `ReactToContent` 重复 | MongoDB unique index 报 duplicate key → 幂等处理验证 |
| 评论楼中楼 | `CreateComment` (reply) | MongoDB 查询验证 replyToCommentId 链 + commentCount 递增 |
| 计数刷新 | `FlushCounters` | miniredis 计数值 == MongoDB Post.likeCount 回写值 |
| 全文搜索 | `SearchPosts` | MongoDB text index 实际查询验证搜索结果 |

**以 UserProfile 为例**（PostgreSQL）：

| 场景 | Command/Query | 断言（真实数据库验证） |
|------|--------------|---------------------|
| 创建用户 | `RegisterUser` | `SELECT * FROM user_profiles` 验证行存在 + user_auth 行存在 + user_settings 默认值 |
| 分身排他 | `ActivatePersona` | `SELECT FROM personas WHERE is_active=true AND user_id=?` 恰好 1 行 |
| 唯一约束 | 重复注册同 phone | PG unique violation error → 业务层正确处理 |
| 乐观锁 | 并发 `ConfirmProposal` | PG `WHERE version=?` 竞争 → 一个成功一个失败 |
| 级联删除 | `DeleteUser` | `SELECT FROM personas WHERE user_id=?` 返回空（CASCADE 生效） |

### 12.6 跨聚合契约验证

跨聚合交互通过领域事件，测试关注**事件契约**。

EventPublisher 使用 **spy 实现**（写入内存 capture list），断言：
1. 事件类型和 payload 字段与 `events.yaml` 定义一致
2. 生产侧验证事件发布
3. 消费侧用预录事件驱动 handler，验证投影/副作用

```
生产者测试（真实数据库 + spy EventPublisher）：
  Command → 真实持久化 → assert event captured with correct payload

消费者测试（真实数据库 + 预录事件注入）：
  inject recorded event → handler processes → 真实数据库验证投影更新
```

| 事件 | 生产者断言 | 消费者断言 |
|------|-----------|-----------|
| `UserFollowed` | PG/Mongo 验证 FollowEdge 行 + spy 捕获 payload | PG 验证 UserProfile.followerCount 递增 |
| `ContentReacted` | miniredis 验证计数递增 + spy 捕获 direct 事件 | 推荐热路径 Redis 数据更新 |
| `UserBlocked` | PG 验证 BlockEdge 行 + miniredis 验证 blocked_set | 真实查询验证过滤生效 |

### 12.7 测试基础设施配置

测试引擎选型和数据管理配置集中在 `_shared/test_infra.yaml`，codegen 从中生成 TestMain 和 helper 代码。

详见 `_shared/test_infra.yaml`。

### 12.8 覆盖矩阵

每个业务对象的 `service.yaml → contract_test → coverage_requirements` 定义了最低覆盖要求：

| 覆盖维度 | 要求 |
|---------|------|
| API 路由 | 每个 `api_routes` 至少一个场景 |
| 状态机 | 所有 `state_machine` 转换（正向 + 异常路径） |
| 唯一约束 | 所有 `unique_constraints` 有违反测试（真实数据库拒绝） |
| 安全分级 | 所有 `SECRET` 字段验证不出现在 API 响应 |
| 事件发布 | 所有 `events` 验证 payload_fields（spy 捕获） |
| 内容类型 | 所有 enum 变体（如 image/video/micro/article）覆盖 |
| 缓存一致性 | Redis 缓存写入/失效/TTL 真实验证 |
| 计数策略 | counter flush + 回写一致性验证 |
| 索引验证 | 全文搜索/地理查询/唯一索引真实执行验证 |
| 并发安全 | 乐观锁/排他约束在真实数据库上并发验证 |

### 12.9 测试代码生成（codegen 支持）

`make codegen-test` 从 metadata 自动生成：

| 产出 | 来源 | 说明 |
|------|------|------|
| `*_testmain_test.go` | `test_infra.yaml` + `aggregate.yaml` | TestMain：启动/关闭测试引擎，执行 migration |
| `*_fixture_test.go` | `fields.yaml` | 测试数据工厂（符合 constraints/classification），Seed + Cleanup helpers |
| `*_event_spy_test.go` | `events.yaml` | EventPublisher spy 实现 + payload 断言 helpers |
| `*_contract_test.go` | `service.yaml` | 测试骨架（场景 + 预制 + 断言 + 清理） |
| `testdata/migrations/*.sql` | `storage.yaml` (PG) | PostgreSQL DDL（tables + indexes + constraints） |
| `testdata/migrations/*.js` | `storage.yaml` (Mongo) | MongoDB 集合 + 索引创建脚本 |
| `mock_responses/*.json` | `fields.yaml` + `service.yaml` | 端侧 API mock 响应 JSON |
| `dart_test/*_test.dart` | `fields.yaml` + `service.yaml` | Flutter 端契约测试（超前） |

### 12.10 与 CI/CD 集成

```
PR 提交 → make verify（metadata 一致性）
       → make codegen-test（生成测试代码 + migration + fixture）
       → 启动测试引擎（embedded-postgres + testcontainers mongo + miniredis）
       → make test-contract（运行契约测试）
           ├── 每个测试：Seed → Execute → Assert → Cleanup
           └── 并行执行（各聚合独立测试引擎实例，无干扰）
       → 覆盖率报告（按 coverage_requirements 维度统计）
       → 不满足最低覆盖 → 阻断合入
```

**CI 环境要求**：
- Docker（MongoDB testcontainers 需要）
- 无需安装 PostgreSQL / Redis（embedded-postgres 自带二进制，miniredis 纯 Go）

**本地开发**：
- `make test-contract` 一键运行，开发者无需手动配置任何数据库
- 首次运行自动下载 embedded-postgres 二进制 + 拉取 mongo Docker 镜像
