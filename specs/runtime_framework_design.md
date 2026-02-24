# 运行时框架：技术选型与完整设计方案

目标：结合业界最佳实践，给出 runtime 框架的技术选型与完整设计，支撑 `specs/runtime_framework_spec.md` 落地；兼顾内容/社交/圈子/私人助手多方向快速发展、AI Agent 自主开发效率与上线后反馈学习闭环。

---

## 1. 业界最佳实践对齐

### 1.1 元数据驱动架构

| 实践 | 来源 | 本框架落地 |
|------|------|------------|
| **Metadata as executable authority** | Metadata-Driven Architecture | metadata 驱动接口、存储、日志、安全、推荐、代码生成 |
| **Centralized metadata hub** | Enterprise Metadata Patterns | contracts/metadata/ 集中管理，校验脚本 + codegen |
| **Collocate metadata with data** | Self-Describing Data Assets | 业务对象与 metadata 强绑定，禁止游离字段 |
| **Deterministic, reviewable, auditable** | 合规/监管 | metadata 变更走 Git + PR review + make verify |

### 1.2 CQRS + 事件驱动

| 实践 | 来源 | 本框架落地 |
|------|------|------------|
| **Write model ≠ Read model** | CQRS Pattern | 写走 Repository + Event；读走物化视图 |
| **Event Sourcing / Event Store** | DDD + Event Driven | 领域事件持久化，驱动投影、推荐、画像、助手上下文 |
| **Async Projection** | Materialized View Pattern | Projector 消费事件构建 feed/inbox/profile/context |

### 1.3 推荐与个性化

| 实践 | 来源 | 本框架落地 |
|------|------|------------|
| **Feature Store** | ML Platform | recommend_feature 字段标记 → 推荐特征自动归集 |
| **Tag-based + Collaborative + Embedding** | 推荐系统 | tag_taxonomy + 行为协同 + 向量相似 |
| **Feedback Loop** | 推荐闭环 | 用户反馈 → 效果评估 → 策略调优 → 灰度验证 |

### 1.4 向量检索与 RAG

| 实践 | 来源 | 本框架落地 |
|------|------|------------|
| **Vector Similarity Search** | 语义检索 | 内容/用户 embedding → 向量存储 → 相似推荐 + 助手 RAG |
| **Retrieval-Augmented Generation** | LLM Best Practice | 助手从向量存储检索相关上下文 → 注入 prompt |

### 1.5 可观测性与实时

| 实践 | 来源 | 本框架落地 |
|------|------|------------|
| **OTEL 统一标准** | OpenTelemetry | 日志/指标/追踪走 OTEL，对接云厂商 |
| **SSE / Change Stream** | 实时推送 | 聊天、助手流式、内容更新实时推送 |

---

## 2. 技术选型

### 2.1 总览

| 类别 | 选型 | 理由 |
|------|------|------|
| **元数据格式** | YAML + JSON Schema 校验 | 可读、可版本、可机检 |
| **代码生成** | Go template codegen（metadata YAML → Go/OpenAPI/Dart） | AI Agent 开发效率的最大杠杆 |
| **主存储（事务）** | PostgreSQL 云版 | ACID、MVCC；身份、认证、状态机 |
| **主存储（弹性）** | MongoDB 云版 | 文档模型、水平扩展；内容/圈子/聊天/运营 |
| **Event Store** | MongoDB event 集合 + Change Stream | 领域事件持久化 + 实时投影触发 |
| **向量存储** | MongoDB Atlas Vector Search（首选）/ Qdrant 云版 | 推荐相似检索 + 助手 RAG；MongoDB 已为主存储，Atlas 原生 vector 最省力 |
| **全文检索** | MongoDB Atlas Search（首选）/ Elasticsearch 云版 | 内容搜索；Atlas Search 与主存储同库免 ETL |
| **缓存** | Redis 云版 | 会话、热点、TTL 由 metadata 驱动 |
| **消息队列** | RocketMQ 云版 | 可靠投递、顺序消息；事件分发 |
| **配置中心** | MSE Nacos | 运维配置；运营配置走 product-ops |
| **可观测** | OTEL + 云厂商（SLS/ARMS/火山 APM） | 统一标准、厂商可插拔 |
| **实时推送** | SSE（Server-Sent Events） | 轻量、HTTP 友好、端侧 Dart 支持好 |
| **Embedding** | 通义千问 / OpenAI embedding API | 云 SaaS 优先 |
| **LLM（文本推理）** | 通义千问 / DeepSeek / GPT-4o | 问答、总结、回复生成、规划 |
| **多模态 LLM** | 通义千问-VL / GPT-4V | 图片理解（地点/商品/场景识别）、视频理解 |
| **ASR（语音转文字）** | 通义听悟 / Whisper API | 视频内容摘要的语音转文字 |
| **内部通信** | gRPC（编排↔业务）+ HTTP（管理） | 低延迟、强类型 |

### 2.2 存储选型矩阵

| 业务对象 | storage_backend | cache_layer | vector_index | capabilities |
|----------|-----------------|-------------|--------------|--------------|
| UserProfile、Persona | postgres | redis | - | queryable, searchable |
| Post（图片/视频/微趣/文章） | mongodb | redis | atlas_vector | queryable, searchable, aggregatable, vector_searchable |
| Comment | mongodb | memory | - | queryable |
| Message | mongodb | redis | - | queryable |
| Conversation | mongodb | redis | - | queryable |
| VisitRecord、InteractionEvent | mongodb | memory | - | queryable, aggregatable |
| ExperimentBucket | postgres | redis | - | queryable |
| Circle | mongodb | redis | - | queryable, searchable |
| FollowEdge | mongodb | redis | - | queryable, aggregatable |
| ContentEmbedding | mongodb (atlas_vector) | memory | atlas_vector | vector_searchable |
| UserContextEmbedding | mongodb (atlas_vector) | memory | atlas_vector | vector_searchable |
| PageContext（运行时状态） | redis | - | - | - |
| ContentAnalysis（缓存） | redis（24h TTL） | - | - | - |

### 2.3 云厂商映射

| 组件 | 阿里云 | 火山引擎 |
|------|--------|----------|
| PostgreSQL | PolarDB / RDS PostgreSQL | veDB PostgreSQL |
| MongoDB + Atlas Search + Vector | 云数据库 MongoDB | veDB MongoDB |
| Redis | Tair / Redis | 云 Redis |
| 消息队列 | RocketMQ 云版 | BMQ / RocketMQ |
| 配置 | MSE Nacos | 对应配置中心 |
| 可观测 | SLS + ARMS | 火山 APM / 日志 |
| Embedding API | 通义千问 | 豆包大模型 |
| 向量存储（备选） | Lindorm / DashVector | - |

---

## 3. 完整设计方案

### 3.1 架构总览

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ App / 运营管理 / 推荐引擎 / 小趣助手                                                  │
│ 模型由 metadata 驱动；推荐消费标签+画像+embedding；助手消费全维度上下文               │
└───────────────────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Gateway → Orchestrator → 业务服务（Content/Circle/User/Chat/Assistant/Ops）          │
│ 写：Repository + Event Publish   读：ReadModel / Query                              │
└───────────────────────────────────────────────────────────────────────────────────┘
        │                                   │                               │
        ▼                                   ▼                               ▼
┌─────────────────┐  ┌──────────────────────────────────────┐  ┌─────────────────────┐
│ EntityRegistry   │  │ Repository 分层                       │  │ CQRS                │
│ + TagTaxonomy    │  │ CRUD/Queryable/Aggregatable/         │  │ Event Store         │
│ 策略查询         │  │ Searchable/VectorSearchable          │  │ Projector           │
│                  │  │ 由 metadata.capabilities 驱动         │  │ ReadModel           │
└─────────────────┘  └──────────────────────────────────────┘  └─────────────────────┘
                                            │
            ┌───────────┬───────────┬───────┴───────┬───────────┐
            ▼           ▼           ▼               ▼           ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐
│ PostgreSQL   │ │ MongoDB  │ │ Redis    │ │ Vector     │ │ Event    │
│ 事务一致     │ │ 弹性扩展 │ │ 缓存     │ │ Atlas/     │ │ Store    │
│              │ │ + Search │ │          │ │ Qdrant     │ │ (Mongo)  │
└──────────────┘ └──────────┘ └──────────┘ └────────────┘ └──────────┘
```

### 3.2 元数据 Schema 设计

#### entity_catalog.yaml 扩展

```yaml
version: 2
entities:
  - name: Post
    domain: content
    service: content-service
    aggregate_root: true
    aggregate_members: [Comment, MediaAsset]
    storage_preference: scale_first
    storage_backend: mongodb
    cache_layer: redis
    cache_ttl_seconds: 300
    capabilities: [queryable, searchable, aggregatable, vector_searchable]
    taggable: true
    vector_enabled: true
    ddd_layer_mapping:
      domain: services/content-service/domain/post/
      application: services/content-service/application/post_service.go
      adapters: services/content-service/adapters/post_handler.go
      infrastructure: services/content-service/infrastructure/post_repo.go
    storage_mapping:
      collection: posts
      index_fields: [createdAt, authorId, contentType]
      search_fields: [title, body, tags]
      vector_field: embedding

  - name: UserProfile
    domain: user
    service: user-service
    aggregate_root: true
    aggregate_members: [Persona]
    storage_preference: transaction_first
    storage_backend: postgres
    cache_layer: redis
    cache_ttl_seconds: 600
    capabilities: [queryable, searchable]
    taggable: true
    vector_enabled: true
    ddd_layer_mapping:
      domain: services/user-service/domain/user_profile/
      application: services/user-service/application/user_service.go
      adapters: services/user-service/adapters/user_handler.go
      infrastructure: services/user-service/infrastructure/user_repo.go
    storage_mapping:
      table: user_profiles

  - name: Conversation
    domain: chat
    service: chat-service
    aggregate_root: true
    aggregate_members: [Message]
    storage_preference: scale_first
    storage_backend: mongodb
    cache_layer: redis
    cache_ttl_seconds: 120
    capabilities: [queryable]
    taggable: false
    vector_enabled: false
    ddd_layer_mapping:
      domain: services/chat-service/domain/conversation/
      application: services/chat-service/application/chat_service.go
      adapters: services/chat-service/adapters/chat_handler.go
      infrastructure: services/chat-service/infrastructure/conversation_repo.go
    storage_mapping:
      collection: conversations

  - name: Circle
    domain: circle
    service: circle-service
    aggregate_root: true
    aggregate_members: [CircleMember]
    storage_preference: scale_first
    storage_backend: mongodb
    cache_layer: redis
    cache_ttl_seconds: 300
    capabilities: [queryable, searchable]
    taggable: true
    vector_enabled: false
    ddd_layer_mapping:
      domain: services/circle-service/domain/circle/
      application: services/circle-service/application/circle_service.go
      adapters: services/circle-service/adapters/circle_handler.go
      infrastructure: services/circle-service/infrastructure/circle_repo.go
    storage_mapping:
      collection: circles

  - name: AssistantRun
    domain: assistant
    service: assistant-service
    aggregate_root: true
    aggregate_members: [InteractionEvent]
    storage_preference: scale_first
    storage_backend: mongodb
    cache_layer: memory
    capabilities: [queryable, aggregatable]
    taggable: false
    vector_enabled: true
    ddd_layer_mapping:
      domain: services/assistant-service/domain/assistant_run/
      application: services/assistant-service/application/assistant_service.go
      adapters: services/assistant-service/adapters/assistant_handler.go
      infrastructure: services/assistant-service/infrastructure/assistant_repo.go
    storage_mapping:
      collection: assistant_runs
```

#### field_policy.yaml 扩展

```yaml
version: 2
policies:
  - entity: Post
    field: title
    type: string
    nullable: false
    classification: PUBLIC
    log_policy: allow
    observe_metric: true
    ops_metric: true
    api_exposure: allow
    ops_exposure: allow
    recommend_feature: true        # 参与推荐特征

  - entity: Post
    field: contentType
    type: enum
    values: [image, video, micro, article]
    classification: PUBLIC
    log_policy: allow
    observe_metric: true
    ops_metric: true
    api_exposure: allow
    recommend_feature: true

  - entity: UserProfile
    field: phone
    type: string
    nullable: false
    classification: PII
    log_policy: mask
    observe_metric: false
    ops_metric: false
    api_exposure: drop
    ops_exposure: mask
    recommend_feature: false
```

#### tag_taxonomy.yaml（新增）

```yaml
version: 1
taxonomies:
  user_tags:
    description: 用户标签
    auto_taggable: true
    tags:
      - { id: interest_tech, label: 科技 }
      - { id: interest_art, label: 艺术 }
      - { id: interest_food, label: 美食 }
      - { id: role_creator, label: 创作者 }
      - { id: role_consumer, label: 消费者 }
      - { id: active_high, label: 高活跃 }

  content_tags:
    description: 内容标签
    auto_taggable: true
    applicable_entities: [Post, MediaAsset]
    tags:
      - { id: type_image, label: 图片 }
      - { id: type_video, label: 视频 }
      - { id: type_micro, label: 微趣 }
      - { id: type_article, label: 文章 }
      - { id: topic_travel, label: 旅行 }
      - { id: topic_food, label: 美食 }
      - { id: mood_positive, label: 正面情绪 }

  social_tags:
    description: 社交标签
    applicable_entities: [FollowEdge, Conversation]
    tags:
      - { id: rel_close, label: 密切关系 }
      - { id: rel_casual, label: 普通关系 }
      - { id: chat_frequent, label: 频繁聊天 }

  circle_tags:
    description: 圈子标签
    applicable_entities: [Circle]
    tags:
      - { id: circle_interest, label: 兴趣圈 }
      - { id: circle_local, label: 本地圈 }
      - { id: circle_active, label: 活跃圈 }
```

### 3.3 CQRS + Event Store 设计

#### 3.3.1 Event Store

```yaml
# contracts/metadata/event_catalog.yaml 扩展
events:
  - name: post.created
    producer: content-service
    consumers: [projector, recommendation, product-ops]
    channel: mq
    payload_entity: Post

  - name: post.viewed
    producer: content-service
    consumers: [projector, recommendation, assistant-context]
    channel: mq
    payload_fields: [postId, userId, duration, source]

  - name: post.feedback
    producer: content-service
    consumers: [projector, recommendation, assistant-context, learning]
    channel: mq
    payload_fields: [postId, userId, action, timestamp]
    # action: like | save | dislike | report | share

  - name: user.tag_updated
    producer: user-service
    consumers: [projector, recommendation, assistant-context]
    channel: mq
    payload_fields: [userId, tags, source]

  - name: assistant.page_context_reported
    producer: assistant-service
    consumers: [assistant-context]
    channel: direct          # 不走 MQ，直接写 Redis（低延迟）
    payload_fields: [userId, sessionId, pageType, objectIds, userAction]

  - name: assistant.suggested_actions_served
    producer: assistant-service
    consumers: [learning, product-ops]
    channel: mq
    payload_fields: [userId, pageType, objectId, actions, selectedAction]

  - name: assistant.content_analyzed
    producer: assistant-service
    consumers: [projector]
    channel: mq
    payload_fields: [postId, contentType, analysisResult, tags]
```

#### 3.3.2 Projector 与 ReadModel

```go
type Projector interface {
    EventTypes() []string
    Project(ctx context.Context, event DomainEvent) error
}

type DiscoveryFeedProjector struct { ... }
type CircleFeedProjector struct { ... }
type ChatInboxProjector struct { ... }
type UserProfileViewProjector struct { ... }
type AssistantContextProjector struct { ... }
```

| Projector | 消费事件 | 产出 ReadModel |
|-----------|----------|----------------|
| DiscoveryFeedProjector | post.created/updated/feedback | discovery_feed（MongoDB，按用户个性化） |
| CircleFeedProjector | post.created + circle 事件 | circle_feed（按圈子聚合） |
| ChatInboxProjector | message.sent/received | chat_inbox（最近消息 + 未读） |
| UserProfileViewProjector | user.* + behavior.* | user_profile_view（画像 + 标签聚合） |
| AssistantContextProjector | 全域事件 | assistant_context（结构化 + embedding） |
| RecommendFeatureProjector | post.* + user.* + feedback.* | recommend_features（推荐特征宽表） |

### 3.4 实时推荐系统设计（类 TikTok 双通道架构）

核心目标：用户每次浏览后，下一批内容立即反映其实时偏好变化。适用于所有内容类型和圈子推荐。

#### 3.4.1 双通道数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│ 端侧行为上报（批量，每 3~5s 或滑动到新内容时）                         │
│ POST /v1/content/feed/signal                                         │
│ { session_id, signals: [{content_id, action, duration_ms}, ...] }   │
└─────────────────────────────────────────────────────────────────────┘
        │                                           │
        ▼ 热路径（毫秒级写入 Redis）                ▼ 冷路径（异步持久化）
┌──────────────────────────┐           ┌───────────────────────────────┐
│ Redis（session 级状态）    │           │ Event Store → MQ → Projector  │
│                           │           │                                │
│ • session_signals:        │           │ → 推荐特征宽表（增量更新）     │
│   兴趣标签权重漂移         │           │ → 长期画像聚合                  │
│ • exposed_set:            │           │ → 向量存储更新                  │
│   已曝光 ID（去重用）      │           │ → 运营分析                      │
│ • negative_set:           │           │                                │
│   负反馈过滤（同类/同源） │           │                                │
│ • realtime_interest:      │           │                                │
│   session 实时兴趣向量     │           │                                │
└──────────────────────────┘           └───────────────────────────────┘
```

#### 3.4.2 推荐引擎（每次加载下一批时执行）

```
┌───────────────────────────────────────────────────────────────────────┐
│ runtime/recommendation                                                 │
│                                                                        │
│ ① 合并特征：                                                           │
│    热路径（Redis session 实时兴趣、负反馈、已曝光）                      │
│    + 冷路径（长期画像、内容标签、推荐特征宽表）                          │
│                                                                        │
│ ② 召回层（多路并行）：                                                  │
│    • 实时兴趣召回：session 兴趣向量 → 向量相似内容                      │
│    • 标签匹配召回：realtime user_tags ∩ content_tags                    │
│    • 协同过滤召回：行为相似用户的偏好                                    │
│    • 热门/新鲜召回：时间 + 全局热度                                      │
│                                                                        │
│ ③ 排序层：                                                              │
│    初期：规则 + 权重（实时信号加权 > 长期画像 > 热度）                   │
│    中期：轻量 ML（LR/GBDT，实时特征 + 长期特征）                        │
│    远期：深度序列模型（DIN/DIEN，session 行为序列）                      │
│                                                                        │
│ ④ 重排层：                                                              │
│    • 去重：过滤 exposed_set                                             │
│    • 负反馈：过滤 negative_set（同类/同作者/同话题）                     │
│    • 多样性：内容类型（图片/视频/微趣/文章）配比控制                     │
│    • 实验：experiments 分桶                                             │
│    • 运营：置顶/打压策略                                                │
│                                                                        │
│ ⑤ 输出：排序后的下一批内容 + nextCursor                                 │
└───────────────────────────────────────────────────────────────────────┘
```

#### 3.4.3 接口设计

```go
// 信息流接口（所有推荐场景统一）
type FeedService interface {
    // 获取下一批推荐内容（融合实时 session 信号）
    GetFeed(ctx, req GetFeedRequest) (*FeedResponse, error)
    // 批量上报行为信号（热路径即时更新）
    ReportSignals(ctx, req ReportSignalsRequest) error
}

type GetFeedRequest struct {
    FeedType   string  // discovery | circle | follow | similar
    SessionID  string  // 推荐 session（一次打开 app 或一次连续浏览）
    Cursor     string  // 游标（续拉）
    Limit      int
    ContextID  string  // 可选：相似推荐时传入当前内容 ID
}

type FeedResponse struct {
    Items          []FeedItem
    NextCursor     string
    SessionContext SessionContext  // 返回 session 状态摘要，端侧可用于调试
}

type SessionContext struct {
    SessionID       string
    SignalsReceived int
    InterestDrift   string   // 兴趣漂移描述（如 "tech → food"）
    DiversityScore  float64  // 当前批次多样性得分
}
```

#### 3.4.4 算法自主演进

| 阶段 | 排序策略 | 自主能力 | 技术选型 |
|------|----------|----------|----------|
| **初期** | 规则引擎（标签匹配 + 热度 + 新鲜度 + 实时信号权重） | 规则可配置，通过 experiments 灰度 | Go 规则引擎 |
| **中期** | 轻量 ML（LR/GBDT） | 离线训练 → 在线 serving；A/B 自动评估择优 | Python 训练 + Go/ONNX serving |
| **远期** | 深度序列模型（DIN/DIEN/SASRec） | 实时 session 序列输入；端到端自动训练部署 | TFServing / Triton |

- 所有阶段的排序模型均通过 experiments 灰度上线，learning 自动评估效果指标（CTR/留存/多样性/满意度）。
- 效果优于基线则自动提权，劣于基线则自动回滚——实现算法自主演进。

### 3.5 小趣助手：三层上下文感知 + 主动交互

#### 3.5.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 端侧（App）                                                              │
│                                                                          │
│ ┌───────────────┐  ┌────────────────┐  ┌────────────────────────────┐  │
│ │ PageContext    │  │ 信号上报       │  │ 小趣 UI 层                  │  │
│ │ Reporter       │  │ (feed/signal)  │  │ • 浮窗 Suggested Actions   │  │
│ │ 页面切换时上报 │  │ 交互信号批量   │  │ • 问答输入框                │  │
│ │ 当前业务对象   │  │ 上报           │  │ • 流式回答（SSE）           │  │
│ └───────┬───────┘  └───────┬────────┘  └────────────┬───────────────┘  │
│         │                  │                         │                   │
└─────────┼──────────────────┼─────────────────────────┼───────────────────┘
          │                  │                         │
          ▼                  ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ assistant-service                                                         │
│                                                                          │
│ ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐ │
│ │ PageContext       │  │ Context          │  │ AssistantEngine         │ │
│ │ Manager           │  │ Assembler        │  │                        │ │
│ │                   │  │                  │  │ • Suggested Actions    │ │
│ │ 接收+缓存+解析   │  │ 三层上下文组装   │  │   Generator            │ │
│ │ 页面级上下文     │  │ → prompt 注入    │  │ • QA Runner（LLM）     │ │
│ │                   │  │                  │  │ • Content Analyzer     │ │
│ │ Redis 存储       │  │ Page + Session   │  │   （多模态理解）       │ │
│ │ page_ctx:{uid}   │  │ + Profile + RAG  │  │ • SSE 流式输出         │ │
│ └──────────────────┘  └──────────────────┘  └────────────────────────┘ │
│                                                                          │
│ 依赖：                                                                   │
│ • runtime/context（画像 + embedding）                                    │
│ • runtime/recommendation（热路径信号）                                   │
│ • runtime/streaming（SSE）                                               │
│ • Embedding API（多模态 embedding）                                      │
│ • LLM API（推理 + 生成）                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 3.5.2 PageContext 接口设计

```go
type PageContextService interface {
    // 端侧页面切换或内容进入时调用；UserActions 中的显式喜好行为
    // 同步写入推荐热路径（Redis session_signals），作用于下一批信息流推荐
    ReportPageContext(ctx context.Context, req PageContextRequest) error
    // 获取当前页面的建议操作（端侧页面加载后调用）
    GetSuggestedActions(ctx context.Context, req SuggestedActionsRequest) (*SuggestedActionsResponse, error)
}

type PageContextRequest struct {
    UserID      string
    SessionID   string
    PageType    PageType   // feed | content_detail | chat | group_chat | circle | circle_discover | search | user_profile
    Objects     PageObjects
    UserAction  string     // viewing | scrolling | composing | searching
    UserActions []UserActionEvent // 显式喜好行为（点赞/收藏/评论/转发/不感兴趣）
}

type UserActionEvent struct {
    Action    string // like | save | comment | share | dislike
    ObjectID  string
    Body      string // comment 时的内容
    Target    string // share 时的目标
    Timestamp time.Time
}

type PageObjects struct {
    Post         *PostSnapshot         // 内容详情：完整对象快照
    Posts        []PostBrief           // 信息流：可见内容简要列表
    Conversation *ConversationSnapshot // 聊天：会话 + 近 N 条消息
    Circle       *CircleSnapshot       // 圈子：圈子 + 动态 + 成员
    SearchQuery  string                // 搜索：当前搜索词
    TargetUser   *UserBrief            // 用户主页：目标用户简要
}

type PostSnapshot struct {
    ID          string
    ContentType string    // image | video | article | micro
    Title       string
    Body        string
    Tags        []string
    MediaURLs   []string
    Author      UserBrief
    Comments    []CommentBrief
    Location    *GeoPoint
}
```

#### 3.5.3 Suggested Actions 生成（按场景）

```go
type SuggestedActionsRequest struct {
    UserID    string
    SessionID string
    PageType  PageType
    ObjectID  string   // 主业务对象 ID
}

type SuggestedActionsResponse struct {
    Actions        []SuggestedAction
    CommentSummary *CommentSummary    // 评论总结（内容详情页）
    ChatSummary    *ChatSummary       // 对话总结（聊天页）
    CircleInsight  *CircleInsight     // 圈子洞察（圈子页）
}

type SuggestedAction struct {
    Type  string  // summary | question | plan | search | recommend | reply
    Label string  // 显示文案（如「帮你总结这篇文章」）
    Icon  string
    Payload map[string]any  // 点击后传递给 QA Runner 的参数
}
```

#### 3.5.4 各场景主动能力技术方案

**内容详情页（图片/视频/文章/微趣）**

```
PageContext(content_detail, Post)
        │
        ├─→ Content Analyzer
        │    ├─ 图片：调用多模态 LLM（视觉理解）→ 场景/物体/地点识别
        │    ├─ 视频：帧采样 + ASR（语音转文字）→ 摘要生成
        │    ├─ 文章：NLP 摘要 + 关键词提取 + 观点抽取
        │    └─ 微趣：短文本理解 + 话题标签
        │
        ├─→ Suggested Actions Generator
        │    ├─ 通用：内容总结、相关搜索建议、关联问询（2~3个）
        │    ├─ 图片类：地点识别、商品识别、风格推荐
        │    ├─ 游记/景点类：出行规划、攻略搜索、住宿/餐饮
        │    └─ 评论区：评论总结（正面/负面/关键观点）+ 自动回复生成
        │
        └─→ 缓存：content_analysis:{postId} → Redis（24h TTL）
             首次分析后缓存，避免重复调用 LLM
```

**聊天会话场景（含群聊）**

```
PageContext(chat/group_chat, Conversation + Messages)
        │
        ├─→ Chat Analyzer
        │    ├─ 对话总结：近 N 条消息 → NLP 摘要
        │    ├─ 话题识别：消息内容 → tag_taxonomy 映射
        │    ├─ 情感分析：对话氛围判断
        │    └─ 群聊特有：多人讨论摘要、决策/投票识别
        │
        ├─→ Suggested Actions Generator
        │    ├─ 对话总结（「帮你总结最近讨论」）
        │    ├─ 回复建议（根据上下文生成 2~3 条回复选项）
        │    ├─ 话题关联（提到的地点/商品/内容 → 关联推荐）
        │    └─ 群聊辅助（讨论总结、投票发起建议）
        │
        └─→ 触发条件：
             • 进入聊天页面（上报 PageContext）
             • 群聊消息积累 > N 条未读
             • 用户长按消息（触发上下文菜单）
```

**圈子场景**

```
PageContext(circle, Circle + Posts + Members)
        │
        ├─→ Circle Analyzer
        │    ├─ 圈子动态总结：近期热门讨论
        │    ├─ 成员分析：活跃成员 + 用户好友中的成员
        │    └─ 标签匹配：circle_tags ∩ user_tags → 相关度
        │
        └─→ Suggested Actions Generator
             ├─ 关联圈子推荐（「你可能也喜欢这些圈子」）
             ├─ 好友推荐加入（「你的好友 XX 也在这里」）
             ├─ 动态总结（「本周热门：...」）
             └─ 发帖建议（「这个圈子最近在聊...」）
```

**搜索场景**

```
PageContext(search, SearchQuery + Results)
        │
        └─→ 上下文增强搜索
             ├─ 从当前 PageContext 历史中提取最近浏览内容
             ├─ 搜索词 + 最近内容上下文 → 搜索意图推断
             ├─ 推荐搜索补全（如 浏览游记 + 搜「酒店」→「[目的地]酒店推荐」）
             └─ 自然语言搜索转换（「帮我找类似内容」→ 向量相似搜索）
```

#### 3.5.5 Content Analyzer 多模态理解

| 内容类型 | 分析能力 | 技术选型 | 缓存策略 |
|----------|----------|----------|----------|
| 图片 | 场景识别、物体检测、地点识别、商品识别、OCR | 多模态 LLM（通义千问-VL / GPT-4V） | content_analysis:{postId} Redis 24h |
| 视频 | 关键帧提取、ASR、内容摘要、关键时刻 | 帧采样 + ASR API + LLM 摘要 | content_analysis:{postId} Redis 24h |
| 文章 | 全文摘要、关键词、观点提取、实体识别 | LLM 摘要 + NLP pipeline | content_analysis:{postId} Redis 24h |
| 微趣 | 话题理解、情感分析、标签提取 | 轻量 NLP + LLM | content_analysis:{postId} Redis 24h |
| 评论 | 情感分类、观点聚合、热评识别 | LLM 批量分析 | comment_summary:{postId} Redis 1h |

所有分析结果首次生成后缓存，后续请求直接返回。评论总结因评论持续新增，TTL 较短。

#### 3.5.6 三层上下文组装与 Prompt 注入

```go
type ContextAssembler interface {
    // 组装完整上下文供 LLM 推理
    Assemble(ctx context.Context, userID string, sessionID string) (*AssistantContext, error)
}

type AssistantContext struct {
    // 第一层：当前页面
    PageContext      *PageContextSnapshot
    ContentAnalysis  *ContentAnalysisResult   // 按需：多模态分析结果
    // 第二层：Session
    SessionSignals   *SessionSignalSnapshot   // 本次 session 行为序列
    InterestDrift    string                   // 兴趣漂移描述
    // 第三层：长期画像
    HolisticProfile  *UserHolisticProfile     // 五维全息画像
    // RAG 检索
    RelevantMemories []RetrievedChunk         // 向量检索命中的历史记忆
    RelevantContent  []RetrievedChunk         // 向量检索命中的相关内容
}
```

Prompt 组装策略：
- **PageContext 优先**：当前页面的业务对象数据总是放在 prompt 最前面，确保 LLM 理解用户「此刻在做什么」
- **Session 次之**：补充当前 session 的行为趋势
- **画像兜底**：个性化风格和深层偏好
- **RAG 按需**：用户问询时检索相关知识
- **Token 管控**：三层上下文按优先级截断，确保不超过 LLM 上下文窗口

助手自主改进能力：
- **实时感知**：PageContext + 推荐热路径，感知用户当前兴趣和操作上下文
- **短期记忆**：当前 session 的对话 + 页面浏览 + 操作上下文
- **长期记忆**：历史交互 embedding（向量存储）+ 全息画像
- **交叉洞察**：跨域关联分析（如「最近频繁在美食圈发帖 + 聊天中提到旅行 → 可能在计划美食旅行」）
- **反馈驱动**：scorecard 评估 → learning 归集 → 策略版本更新 → 下次 run 注入改进

### 3.6 Skill 可扩展框架：技术设计

#### 3.6.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│ runtime/skill                                                             │
│                                                                          │
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│ │ Skill Store   │  │ Skill Router  │  │ Tool         │  │ Context      │ │
│ │ Manager       │  │              │  │ Registry     │  │ Authorizer   │ │
│ │              │  │ 场景匹配     │  │              │  │              │ │
│ │ 注册/版本/   │  │ 意图识别     │  │ 页面级 Tool  │  │ 声明裁剪     │ │
│ │ 审核/灰度    │  │ 能力路由     │  │ 注册与发现   │  │ 策略过滤     │ │
│ └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│        │                 │                  │                 │          │
│        ▼                 ▼                  ▼                 ▼          │
│ ┌───────────────────────────────────────────────────────────────────┐   │
│ │ Skill Runtime（执行引擎）                                          │   │
│ │                                                                    │   │
│ │ • SkillExecutor：调度 Skill 执行                                  │   │
│ │ • ContextInjector：按授权范围注入上下文                           │   │
│ │ • ToolProxy：代理 Skill 的 Tool 调用（鉴权+限流+审计）           │   │
│ │ • Sandbox：隔离执行环境（ecosystem Skill 沙箱化）                │   │
│ │ • OutputStreamer：SSE 流式输出                                    │   │
│ └───────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 3.6.2 核心接口设计

```go
// Skill 定义
type Skill interface {
    Manifest() SkillManifest
    Execute(ctx context.Context, input SkillInput) (SkillOutput, error)
}

type SkillManifest struct {
    ID               string
    Name             string
    Provider         string            // internal | ecosystem
    Version          string
    ApplicablePages  []PageMatcher     // 适用的页面场景
    ContextRequirements ContextScope   // 需要的上下文范围
    ToolDependencies []string          // 依赖的 Tool IDs
    OutputTypes      []string          // text | structured | action_card
    DataClassMax     string            // PUBLIC | PII | SENSITIVE
    RequiresConsent  bool
}

type PageMatcher struct {
    PageType     string     // content_detail | chat | circle | ...
    ContentTypes []string   // image | video | article | micro（可选）
    TagMatch     []string   // 内容标签匹配（可选）
}

// Skill 执行输入（由 Runtime 组装）
type SkillInput struct {
    UserID        string
    SessionID     string
    PageContext    *PageContextSnapshot       // 第一层：当前页面（按授权裁剪）
    SessionCtx    *SessionSignalSnapshot     // 第二层：Session（按授权裁剪）
    ProfileCtx    *ProfileDimensions         // 第三层：画像（按声明维度裁剪）
    ContentAnalysis *ContentAnalysisResult   // 内容分析结果（如有）
    UserQuery     string                     // 用户自然语言输入（如有）
    ToolCaller    ToolCaller                 // Tool 调用代理
}

// Skill 可调用的 Tool 代理
type ToolCaller interface {
    Call(ctx context.Context, toolID string, params map[string]any) (any, error)
    AvailableTools() []ToolDescriptor
}

// Skill 执行输出
type SkillOutput struct {
    Type      string              // text | structured | action_card | stream
    Text      string              // 文本输出
    Structured map[string]any     // 结构化输出（如出行规划）
    Actions   []ActionCard        // 可执行操作卡片
    StreamCh  <-chan StreamChunk  // 流式输出通道
}
```

#### 3.6.3 Skill Router 技术方案

```go
type SkillRouter interface {
    // 根据当前上下文匹配适用的 Skill 列表（用于 Suggested Actions）
    MatchSkills(ctx context.Context, pageCtx PageContextSnapshot) ([]SkillMatch, error)
    // 根据用户意图路由到最佳 Skill
    RouteByIntent(ctx context.Context, pageCtx PageContextSnapshot, userQuery string) (*SkillMatch, error)
}

type SkillMatch struct {
    Skill       SkillManifest
    Score       float64         // 匹配分数
    MatchReason string          // 匹配原因（页面/标签/意图）
    SuggestedLabel string       // 建议展示文案
}
```

路由策略（分层匹配）：

```
① 精确匹配：page_type + content_type + tag_match 全命中 → 高分
② 页面匹配：page_type 命中但标签不完全匹配 → 中分
③ 意图匹配：NLU 解析用户问询 → 匹配 Skill 描述（语义相似度）→ 按相似度打分
④ 权限过滤：Skill.DataClassMax > 用户未授权级别 → 过滤掉
⑤ 排序：分数 + Skill 评分 + 用户历史使用频次 → 最终排序
```

#### 3.6.4 Tool Registry 技术方案

```go
type ToolRegistry interface {
    // 注册 Tool（启动时从 tool_catalog.yaml 加载）
    Register(tool ToolDescriptor) error
    // 获取当前页面可用的 Tools
    GetAvailableTools(pageType string) []ToolDescriptor
    // 执行 Tool（经过鉴权+限流+审计）
    Execute(ctx context.Context, toolID string, callerSkillID string, params map[string]any) (any, error)
}

type ToolDescriptor struct {
    ID              string
    Name            string
    ApplicablePages []string
    InputSchema     map[string]any   // JSON Schema
    OutputType      string
    DataClassMax    string
    RateLimit       string           // 如 "10/min"
    RequiresConsent bool
}
```

Tool 执行链路：

```
Skill 调用 ToolCaller.Call("content.analyze", params)
        │
        ▼
ToolProxy（runtime/skill 内部）
  ① 鉴权：Skill.DataClassMax ≥ Tool.DataClassMax？
  ② 用户授权：用户是否授权该 Skill 调用此 Tool？
  ③ 限流：RateLimit 检查
  ④ 审计：记录 Skill → Tool 调用日志
  ⑤ 执行：调用对应业务服务的 Repository/Service 方法
  ⑥ 过滤：返回结果按 field_policy.classification 过滤敏感字段
        │
        ▼
返回结果给 Skill
```

#### 3.6.5 上下文授权存储

```yaml
# user_skill_consent 存储（MongoDB）
consents:
  - user_id: "user_123"
    skill_id: "travel_planner"
    granted_at: "2026-02-08T10:00:00Z"
    scope:
      page_context: true
      session_context: true
      profile_dimensions: [content_preference, circle_participation]
      tools: [content.search, location.nearby_search]
    revocable: true
```

授权 UI 流程：
1. 用户首次触发 Skill（点击 Suggested Action 或自然语言路由到 Skill）
2. 端侧弹出授权确认：展示 Skill 名称 + 需要的上下文范围 + 需要的 Tool 权限
3. 用户确认 → 记录 consent → Skill 执行
4. 用户可在设置中查看和撤销已授权的 Skill

#### 3.6.6 Skill 开发与发布流程

**内部 Skill 开发（provider: internal）：**

```
1. 在 skill_catalog.yaml 中注册 SkillManifest
2. 在 tool_catalog.yaml 中注册需要的 Tools（如果新增）
3. 实现 Skill interface（Execute 方法）
4. make verify → 校验 Skill 声明与 metadata 一致性
5. experiments 灰度发布
```

**生态 Skill 开发（provider: ecosystem，未来）：**

```
1. 开发者在 Skill Store 平台注册
2. 提交 SkillManifest（声明 context/tool 需求）
3. 提交 Skill 实现代码（限定 SDK + 运行时环境）
4. 自动审核：
   - context_requirements 是否合理（不得过度索取）
   - tool_dependencies 是否在白名单内
   - 代码安全扫描（沙箱兼容性）
5. 人工审核（敏感权限）
6. 灰度发布 → 效果评估 → 正式上架
```

#### 3.6.7 Skill 与推荐/信息流联动

Skill 不仅被动触发，还可以与推荐引擎联动：

| 联动场景 | 机制 |
|----------|------|
| Skill 推荐 | Skill Router 根据 PageContext + 画像 → 推荐最相关的 Skill 展示在 Suggested Actions 中 |
| Skill 反馈驱动推荐 | Skill 执行结果（如出行规划）→ 产生领域事件 → 影响推荐特征（如 travel_intent 标签） |
| Skill 丰富内容理解 | Skill 的 Content Analyzer 结果 → 缓存后供推荐引擎消费（如图片中的地点标签） |

### 3.7 DDD 聚合根与服务分层

#### 3.7.1 聚合边界设计

| 聚合根 | 聚合成员 | Domain | 一致性边界 | 跨聚合交互方式 |
|--------|----------|--------|------------|----------------|
| Post | Comment, MediaAsset | content | Post 内的评论和媒体在同一事务内变更 | 通过 post.created / post.updated 事件通知其他聚合 |
| Conversation | Message | chat | 会话内消息在同一事务内 | 通过 message.sent 事件触发通知/上下文更新 |
| UserProfile | Persona | user | 用户档案与人设在同一事务内 | 通过 user.profile_updated 事件触发画像/推荐更新 |
| Circle | CircleMember | circle | 圈子与成员在同一事务内 | 通过 circle.member_joined 事件触发推荐/画像更新 |
| AssistantRun | InteractionEvent | assistant | run 与交互事件在同一事务内 | 通过 assistant.run_completed 事件触发画像更新 |

设计原则：
- 聚合根拥有全局唯一 ID，聚合成员仅通过聚合根的 Repository 访问
- 跨聚合交互必须通过领域事件（异步最终一致），禁止直接调用另一个聚合的 Repository
- codegen 根据 `aggregate_root` + `aggregate_members` + `ddd_layer_mapping` 生成完整目录结构

#### 3.7.2 服务内部 codegen 目录结构

以 content-service 为例，codegen 从 metadata 自动生成：

```
services/content-service/
├── domain/
│   └── post/
│       ├── entity.go          ← codegen: Post + Comment + MediaAsset 结构体
│       ├── value_objects.go   ← codegen: ContentType enum 等
│       ├── events.go          ← codegen: PostCreated, PostUpdated 等事件
│       ├── repository.go      ← codegen: PostRepository 接口（按 capabilities）
│       └── service.go         ← 手写: 领域服务（聚合根行为逻辑）
├── application/
│   └── post_service.go        ← codegen 骨架 + 手写: 应用编排、Command handler
├── adapters/
│   ├── http_handler.go        ← codegen: HTTP handler（CRUD + 自定义路由）
│   └── event_handler.go       ← codegen 骨架: 事件消费 handler
├── infrastructure/
│   ├── mongo_post_repo.go     ← codegen: MongoDB Repository 实现
│   └── redis_cache.go         ← codegen: Redis 缓存适配器
├── projector/
│   ├── discovery_feed.go      ← codegen 骨架 + 手写: 发现流投影
│   └── circle_feed.go         ← codegen 骨架 + 手写: 圈子动态投影
└── bootstrap/
    └── main.go                ← codegen: 依赖注入 + 启动
```

### 3.8 Repository 分层实现

```go
// 基础 CRUD
type Repository[T Entity] interface {
    FindByID(ctx context.Context, id string) (*T, error)
    Save(ctx context.Context, entity *T) error
    Delete(ctx context.Context, id string) error
}

// 可查询
type Queryable[T Entity] interface {
    Repository[T]
    Find(ctx context.Context, filter Filter, sort Sort, page Pagination) ([]T, Cursor, error)
    Count(ctx context.Context, filter Filter) (int64, error)
}

// 可聚合
type Aggregatable[T Entity] interface {
    Queryable[T]
    Aggregate(ctx context.Context, pipeline Pipeline) ([]Result, error)
}

// 可全文检索
type Searchable[T Entity] interface {
    Queryable[T]
    Search(ctx context.Context, query string, filter Filter) ([]T, error)
}

// 可向量检索
type VectorSearchable[T Entity] interface {
    SimilaritySearch(ctx context.Context, embedding []float32, topK int, filter Filter) ([]T, error)
}
```

### 3.9 Streaming 子包

```go
// runtime/streaming
type SSEServer interface {
    Broadcast(event SSEEvent) error
    Subscribe(ctx context.Context, channel string) (<-chan SSEEvent, error)
}

type ChangeStreamWatcher interface {
    Watch(ctx context.Context, collection string, pipeline Pipeline) (<-chan ChangeEvent, error)
}
```

- 聊天消息实时推送
- 助手流式响应（逐字输出）
- 内容/圈子动态实时更新

### 3.10 代码生成（Codegen）

```
metadata v3（模块化目录）→ codegen 模板 → 生成物

{aggregate}/aggregate.yaml + fields.yaml
    → Go struct（domain/entity.go）
    → Repository interface（domain/repository.go）
    → Repository impl（adapters/mongo_repo.go 或 adapters/pg_repo.go）
    → Handler 骨架（adapters/http_handler.go）

{aggregate}/fields.yaml + service.yaml
    → OpenAPI schema（contracts/openapi/<service>.v1.yaml）
    → Dart DTO（quwoquan_app/lib/cloud/models/）

{aggregate}/events.yaml
    → Event struct（domain/events.go）
    → Projector 骨架

{aggregate}/storage.yaml
    → PostgreSQL Migration（migrations/*.sql）
    → MongoDB 索引脚本（scripts/indexes/*.js）

_shared/tag_taxonomy.yaml
    → Tag enum / constants

_shared/test_infra.yaml + {aggregate}/service.yaml
    → TestMain（*_testmain_test.go）
    → Fixture 工厂（*_fixture_test.go）
    → EventSpy（*_event_spy_test.go）
    → 契约测试骨架（*_contract_test.go）
```

AI Agent 开发流程：

```
1. Agent 修改 metadata（新增 entity / field / tag / event）
2. 运行 codegen → 自动生成骨架
3. Agent 补充业务逻辑（仅 domain 层与 application 层）
4. make verify → 校验一致性
5. make gate → 全绿合入
```

### 3.11 底座层：runtime 子包完整清单

| 子包 | 职责 | 对接 |
|------|------|------|
| config | ConfigProvider（File/Nacos） | platform-ops |
| errors | 统一错误码、用户文案 | - |
| observability | 日志/指标/追踪（OTEL） | platform-ops |
| http | Inbound/Outbound pipeline、Client 工厂 | - |
| **streaming** | SSE Server/Client、Change Stream 适配 | 实时推送 |
| messaging | Envelope、trace 传播、幂等消费 | product-ops |
| governance | 超时/重试/熔断/限流/降级 | platform-ops |
| experiments | 分桶解析、灰度策略 | product-ops |
| learning | 反馈事件、评估、策略版本 | product-ops |
| **recommendation** | 双通道信号归集（Redis 热路径 + Event Store 冷路径）、召回/排序/重排、算法版本管理、FeedService 接口 | product-ops |
| **context** | Context Pipeline、画像聚合、embedding 生成 | assistant |
| **skill** | Skill Runtime（Router/Executor/ToolProxy/Sandbox/Authorizer）、Skill Store Manager、SkillManifest + ToolCatalog 注册 | assistant-service |
| **codegen** | metadata → 代码模板生成 | 开发工具链 |

### 3.12 部署与运行

- **本地**：Docker Compose（MongoDB、PostgreSQL、Redis）；文件配置；Mock Embedding API
- **云侧**：K8s 或 ECS；云托管全部存储；OTEL Collector 对接；Embedding API 调用云 SaaS

---

## 4. 契约测试基础设施设计

### 4.1 测试引擎选型

服务侧契约测试使用真实兼容的轻量测试引擎，不 mock 存储层。业务代码零修改，仅切换连接地址。

| 生产存储 | 测试引擎 | Go 包 | 选型理由 |
|----------|----------|-------|----------|
| PostgreSQL 16 | embedded-postgres | `github.com/fergusstrange/embedded-postgres` | 真实 PG 二进制，进程内启动 ~2s，支持完整 SQL（窗口函数/CTE/JSONB/部分索引/触发器），无需 Docker |
| MongoDB 7 | testcontainers-go | `github.com/testcontainers/testcontainers-go/modules/mongodb` | 真实 mongod 容器，支持完整功能（事务/Change Stream/聚合管道/文本索引），镜像缓存后 ~3s |
| Redis 7 | miniredis/v2 | `github.com/alicebob/miniredis/v2` | 纯 Go 内存 Redis，TCP 兼容，<1ms 启动，支持时间控制验证 TTL |

### 4.2 隔离策略

```
┌─────────────────────────────────────────────────────────────┐
│ 服务侧契约测试边界                                            │
│                                                              │
│  HTTP Handler → Application Service → Domain Model           │
│       │                                      │               │
│       ▼                                      ▼               │
│  Repository ──→ 真实测试数据库                                │
│  (生产代码)    embedded-pg / testcontainers / miniredis       │
│                                                              │
│  EventPublisher ──→ Spy（捕获事件用于断言）                    │
│  CrossServiceAPI ──→ Mock（隔绝级联）                         │
│  LLM/Embedding  ──→ Mock（外部 AI API）                      │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Migration 生成策略

codegen 从 `storage.yaml` 生成 migration 脚本：

- **PostgreSQL**：`migration_pg.sql`（CREATE TABLE + INDEX + FK + UNIQUE CONSTRAINT）
- **MongoDB**：`migration_mongo.js`（createCollection + createIndex + text/vector index）
- 测试引擎在 TestMain 中自动执行 migration，确保 schema 与生产一致

### 4.4 数据管理

| 阶段 | PostgreSQL | MongoDB | Redis |
|------|-----------|---------|-------|
| Seed | Fixture Builder → INSERT | Fixture Builder → InsertOne | Fixture Builder → SET/HSET |
| Cleanup | `TRUNCATE ... CASCADE` | `DeleteMany({})` | `FlushAll()` |

Fixture Builder 从 `fields.yaml` 的 constraints 自动推导合规默认值（PK 随机、NOT_NULL 填充、FK 预制关联数据）。

详细配置见 `contracts/metadata/_shared/test_infra.yaml`。

---

## 5. 实施路线

详细落地计划见 `specs/RUNTIME_DEVELOPMENT_PLAN.md`（含 P0-fix → P0 → P1 → P2 → P3 阶段门禁）。
商用准出 Gap 分析见 `specs/runtime_gap_analysis_and_plan.md`。

| 阶段 | Task 数 | 核心产出 | 预估 | Gate 条件 |
|------|---------|----------|------|-----------|
| **P0-fix** | 3 | 既有代码修复 + spec 对齐 + 特性树补全 | 2~3 天 | 编译通过 + spec 一致 |
| **P0** | 8 | metadata 校验 + codegen + Registry + Repository + 拦截链 + 测试基础设施 + 本地环境 | 3~4 周 | Post + UserProfile 端到端 CRUD + 契约测试全绿 |
| **P1** | 5 | Event Store + CQRS + 实时推荐双通道 + SSE | 3~4 周 | 信息流推荐端到端可用 + 下一批反映实时偏好 |
| **P2** | 6 | 小趣三层上下文 + 主动能力 + Skill 框架 + 实验闭环 | 4~5 周 | 小趣按场景主动建议 + 内置 Skill 运行 |
| **P3** | 3 | Skill 生态 + Agent 全自主 + SLI 回流 | 3~4 周 | 生态 Skill 可接入 + Agent 端到端自主 |

---

## 6. 参考

- `specs/runtime_framework_spec.md`：规范与原则
- `specs/runtime_gap_analysis_and_plan.md`：商用准出 Gap 分析
- `specs/RUNTIME_DEVELOPMENT_PLAN.md`：商用准出开发计划
- `specs/runtime_extension_catalog.md`：端云扩展场景
- `quwoquan_service/contracts/metadata/DESIGN.md`：metadata 设计总览
- `quwoquan_service/技术选型.md`：云侧选型细节
