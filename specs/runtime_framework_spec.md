# 运行时框架规范：DDD + 元数据驱动

目标：以业务对象为中心、元数据驱动应用的完整技术框架，确保从接口到存储的标准化，及上层应用的模型驱动；支撑内容、社交、圈子及私人助手多方向快速发展，兼顾开发效率、性能、可扩展性与 AI Agent 自主开发闭环。业务对象与元数据超前建设，不随特性临时补丁。

---

## 0. 目标定位

- **统一运行时**：云侧服务聚焦业务开发，横切能力统一由 runtime 提供；runtime 对接 product-ops（运营）与 platform-ops（运维）。
- **元数据贯穿全链路**：接口、存储、日志、安全、运营、推荐、标签、画像、助手上下文等均由 metadata 驱动；存储层通过元数据做适配映射。
- **标准化与模型驱动**：接口契约、存储 schema、上层应用模型均从 metadata 推导或校验；禁止与 metadata 冲突的硬编码。
- **CQRS + 事件驱动**：写路径走 Repository + 领域事件；读路径走物化视图 + ReadModel，读写解耦以支撑信息流、推荐、助手上下文等高并发多形态读场景。
- **代码生成优先**：metadata 不仅做校验，更驱动代码生成（struct/repo/handler/OpenAPI/Dart DTO），大幅提升开发效率与 AI Agent 自主开发能力。
- **超前建设**：底座与框架可超前于特性建设；0→1 与 1→n 扩展均以 metadata 为先。

---

## 1. 设计开发原则

| 原则 | 说明 |
|------|------|
| **元数据单一事实源** | entity_catalog、field_policy、tag_taxonomy、event_catalog 为唯一权威；接口、存储、日志、安全、推荐、助手均不与之冲突 |
| **接口与存储标准化** | 接口 schema 与存储 schema 均从 metadata 推导；对外统一 Repository/Query，对内由元数据驱动 SQL/NoSQL/缓存/向量适配 |
| **上层应用模型驱动** | App、运营管理、推荐系统、小趣助手等上层应用的业务模型由 metadata 驱动，禁止游离字段或临时补丁 |
| **存储层元数据适配** | 存储后端选择、缓存策略、索引/分片、向量索引、读写路由均由 metadata 声明，框架据此生成或选择适配器 |
| **事件驱动与 CQRS** | 写操作产生领域事件；读模型由事件异步投影构建；推荐、画像、助手上下文均消费事件 |
| **代码生成优先** | metadata → Go struct/interface、Repository 实现、OpenAPI schema、端侧 Dart DTO、Migration 脚本；AI Agent 只需修改 metadata + 补充业务逻辑 |
| **业务对象先行** | 新能力必须先注册 metadata，再建契约与存储，再实现业务逻辑 |
| **横切统一 runtime** | 配置、错误、可观测、HTTP、流式、消息、治理、实验、学习、推荐均通过 runtime 子包，禁止业务重复实现 |

---

## 2. 框架总览

### 2.1 核心理念

- **业务对象为中心**：所有领域能力围绕业务对象（Entity/Aggregate）建模；数据读写、日志、安全、接口、推荐、标签、画像、运营、助手上下文均以业务对象为统一载体。
- **元数据驱动**：entity_catalog、field_policy、tag_taxonomy、event_catalog 为单一事实来源；禁止在代码、接口、日志中硬编码与 metadata 冲突的字段含义或策略。
- **一致性约束**：所有应用（业务服务、App、运营管理、推荐引擎、小趣助手）对同一业务对象数据的处理与变更必须一致，由 metadata 与运行时框架强制执行。

### 2.2 四层结构

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 业务层：领域服务按 DDD 分层实现，仅操作已注册业务对象，通过框架读写       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑ 强制遵从
┌─────────────────────────────────────────────────────────────────────────┐
│ 框架层：元数据驱动的 DDD 领域框架                                         │
│ EntityRegistry | Repository(分层) | CQRS(Event+Projector+ReadModel)     │
│ 拦截链 | 代码生成 | 契约推导 | 标签/画像/上下文管道                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
┌─────────────────────────────────────────────────────────────────────────┐
│ 底座层：runtime 能力组件 + product-ops / platform-ops 接入                │
│ config | errors | observability | http | streaming | messaging |        │
│ governance | experiments | learning | recommendation                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↑
┌─────────────────────────────────────────────────────────────────────────┐
│ 存储层：PostgreSQL | MongoDB | Redis | 向量存储 | Event Store             │
│ 全部由 metadata 声明 storage_backend / cache_layer / vector_index       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 业务对象与元数据

### 3.1 业务对象定义

业务对象（Entity/Aggregate）必须在 metadata 中注册后才能在应用中暴露或持久化：

- **entity_catalog**：对象名称、所属 domain、归属 service、aggregate_root（是否聚合根）、aggregate_members（聚合内成员）、storage_preference、capabilities（queryable/searchable/aggregatable）、taggable、vector_enabled、ddd_layer_mapping（domain/application/adapters/infrastructure 路径）
- **field_policy**：字段级 type、nullable、classification、log_policy、observe_metric、ops_metric、api_exposure、ops_exposure、recommend_feature（是否参与推荐特征）
- **tag_taxonomy**：标签分类体系（用户标签、内容标签、社交标签、圈子标签）
- **event_catalog**：领域事件定义（producer/consumer/channel/schema）

### 3.2 元数据驱动的统一消费场景

| 场景 | 驱动字段 | 说明 |
|------|----------|------|
| 存储 | storage_backend、cache_layer、vector_index | SQL/NoSQL/缓存/向量适配映射由 metadata 驱动 |
| 日志 | log_policy | allow/mask/drop，结构化日志按策略脱敏或丢弃 |
| 安全隐私 | classification | PUBLIC/PII/SENSITIVE/SECRET，存储/传输/展示策略 |
| 接口协议 | api_exposure | 控制 App/管理端接口返回字段可见性 |
| 指标统计 | observe_metric、ops_metric | 字段是否参与可观测指标、运营指标 |
| 运营管理 | ops_exposure、ops_metric | 运营后台展示、分析、报表 |
| 推荐特征 | recommend_feature | 字段是否参与推荐特征向量 |
| 标签与画像 | tag_taxonomy、taggable | 业务对象可关联标签；用户画像由标签 + 行为聚合 |
| 助手上下文 | 业务对象 + 用户行为 + 画像 + 标签 | 全维度上下文供小趣助手推理 |
| 代码生成 | entity_catalog + field_policy | 生成 struct/repo/handler/OpenAPI/DTO |

### 3.3 标签体系与用户画像

#### 3.3.1 标签分类（tag_taxonomy）

| 标签域 | 适用对象 | 示例 |
|--------|----------|------|
| 用户标签 | UserProfile、Persona | 兴趣偏好、年龄段、活跃度、创作者/消费者 |
| 内容标签 | Post、MediaAsset、Article | 主题、类型（图片/视频/微趣/文章）、风格、情感 |
| 社交标签 | FollowEdge、Conversation | 关系强度、互动频次、话题偏好 |
| 圈子标签 | Circle、CircleMember | 圈子类型、活跃度、主题 |

- 标签由 metadata 统一管理（tag_taxonomy.yaml），禁止在业务代码中硬编码标签枚举。
- 标签可人工标注，也可由推荐/助手引擎自动打标。

#### 3.3.2 用户画像

- 画像是**多源标签 + 行为统计**的聚合视图，存储为 UserProfile 的扩展属性或独立 ReadModel。
- 画像由 Context Pipeline 异步构建（见 §5），供推荐和小趣助手消费。
- 画像字段遵循 field_policy，受 classification、log_policy 等策略约束。

### 3.4 存储策略与存储层元数据适配

| 倾向 | 适用场景 | 推荐存储 | 典型业务对象 |
|------|----------|----------|--------------|
| **事务一致性优先** | 强一致、关系约束、ACID | PostgreSQL | UserProfile、Persona、认证/授权、profileUpdateProposal |
| **读多写多、弹性可扩展** | 高并发、灵活 schema、水平扩展 | MongoDB | Post、Comment、Message、VisitRecord、InteractionEvent |
| **语义检索** | 向量相似度、embedding | 向量存储 | 内容 embedding、用户画像 embedding、助手记忆 |

- **对外**：标准化 Repository/Query 接口，业务层不感知底层存储类型。
- **对内**：storage_backend、cache_layer、vector_index 等由 metadata 声明，框架据此驱动适配器。

---

## 4. 元数据驱动的 DDD 领域框架

### 4.1 业务对象注册中心（EntityRegistry）

- 从 entity_catalog + field_policy + tag_taxonomy 加载业务对象、字段策略与标签体系。
- 提供按 entity/field 查询 classification、log_policy、recommend_feature、capabilities 等。
- 所有读写、日志、审计、推荐、接口 schema 均通过 Registry 获取策略。

### 4.2 Repository 分层抽象

按 entity 的 capabilities（由 metadata 声明）决定实现哪些接口层级：

| 层级 | 接口 | 适用场景 |
|------|------|----------|
| **Repository** | FindByID、Save、Delete | 所有 entity |
| **Queryable** | Find(filter, sort, pagination)、Count | 大多数 entity |
| **Aggregatable** | Aggregate(pipeline) | 需统计的 entity（推荐特征、画像） |
| **Searchable** | Search(query, filter) | 需全文检索的 entity（帖子、文章、评论、圈子、用户等） |
| **VectorSearchable** | SimilaritySearch(embedding, topK) | 向量检索（推荐、助手语义匹配） |

- 适配器按 storage_backend 路由至 PostgreSQL / MongoDB / 向量存储。
- 所有层级由 metadata 的 capabilities 声明驱动，代码生成器据此生成骨架。

### 4.3 CQRS：事件驱动与读写分离

#### 4.3.1 写路径

```
Command → ApplicationService → Repository.Save() → 领域事件发布（Event Store + MQ）
```

- 每次写操作产生领域事件，事件 schema 与 event_catalog 对齐。
- 事件持久化至 Event Store（MongoDB event 集合），同时发布到消息队列。

#### 4.3.2 读路径

```
领域事件 → Projector（异步投影） → ReadModel（物化视图）→ Query 接口
```

- Projector 消费事件，构建面向不同读场景的物化视图。
- ReadModel 可以是 MongoDB 集合、Redis 结构或内存视图。

#### 4.3.3 CQRS 核心场景

| 读场景 | 数据来源 | ReadModel |
|--------|----------|-----------|
| 发现流（图片/视频/微趣/文章） | Post + 用户行为 + 推荐特征 | discovery_feed（按用户个性化排序） |
| 圈子动态 | Circle + Post + 成员行为 | circle_feed（按圈子聚合） |
| 聊天会话列表 | Conversation + Message | chat_inbox（最近消息 + 未读计数） |
| 用户画像 | 多源标签 + 行为统计 | user_profile_view（聚合画像） |
| 助手上下文 | 全域事件 + 画像 + 标签 | assistant_context（结构化 + 向量化） |

### 4.4 读写拦截链

- 读：按 api_exposure 过滤字段；按 log_policy 写日志；按 classification 脱敏。
- 写：校验必填、类型、权限；发布领域事件；按 metadata 决定审计与指标字段。
- 日志/指标：observe_metric、ops_metric 为 true 的字段自动参与可观测与运营指标。

### 4.5 契约与事件 schema

- OpenAPI schema 从 entity_catalog + field_policy 推导或校验。
- 领域事件 payload 与 entity 字段对齐；event_catalog 声明 producer/consumer/channel。
- 端侧 Dart DTO 由 OpenAPI 生成，保证端云一致。

### 4.6 存储层元数据驱动与统一映射

- **元数据声明**：entity_catalog 声明 storage_preference、storage_backend、cache_layer、vector_index、ttl 等；storage_mapping.yaml 定义表/集合、索引、分片。
- **适配映射**：PostgreSQL / MongoDB / 向量存储 / Redis 由 metadata 驱动选择。
- **接口与存储一致**：Repository 对外接口统一；内部 schema 从 metadata 推导或校验。

### 4.7 代码生成（Codegen）

从 metadata 直接生成 80% 样板代码：

| 生成物 | 来源 | 说明 |
|--------|------|------|
| Go struct | entity_catalog + field_policy | 业务对象结构体 |
| Repository 接口与实现 | entity_catalog.capabilities + storage_backend | 按层级生成 CRUD/Query/Aggregate/Search |
| Handler / Route | entity_catalog.crud_paths | HTTP/gRPC handler 骨架 |
| OpenAPI schema | entity_catalog + field_policy | 接口契约 |
| Dart DTO | OpenAPI | 端侧类型 |
| Migration | storage_mapping | DDL / 索引脚本 |
| Event schema | event_catalog | 事件 payload 类型 |

AI Agent 开发流程：修改 metadata → 运行 codegen → 补充业务逻辑 → make verify。

---

## 5. 实时信息流推荐与反馈闭环

### 5.1 核心交互体验目标

类 TikTok 实时信息流体验：用户浏览一批内容后，下一批立即反映其实时偏好变化。适用于所有内容类型（图片、视频、微趣、文章）及圈子推荐，算法能自主调整，无需人工干预。

### 5.2 双通道架构：热路径 + 冷路径

```
┌─────────────────────────────────────────────────────────────────────┐
│ 用户在 App 中浏览/交互                                                │
│ 每次行为（曝光/点击/停留/跳过/点赞/不感兴趣）即时上报               │
└─────────────────────────────────────────────────────────────────────┘
        │                                           │
        ▼ 热路径（毫秒级）                          ▼ 冷路径（秒~分钟级）
┌─────────────────────────┐            ┌──────────────────────────────┐
│ 实时信号层（Redis）       │            │ 事件持久化层（Event Store）    │
│                          │            │                               │
│ • session_signals:       │            │ → MQ → Projector →            │
│   {userId}:{sessionId}   │            │   ReadModel 物化视图           │
│ • 实时兴趣向量更新        │            │ → 画像聚合 → 向量存储          │
│ • 实时负反馈过滤集        │            │ → 推荐特征宽表更新             │
│ • 已曝光 ID 集合          │            │ → 长期画像 + 标签更新          │
│ • TTL：session 级别       │            │                               │
└─────────────────────────┘            └──────────────────────────────┘
        │                                           │
        └───────────────┬───────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 推荐引擎（runtime/recommendation）                                    │
│                                                                      │
│ 每次「加载下一批」时：                                                │
│ ① 读取热路径：session 实时信号（当前偏好、负反馈、已曝光）            │
│ ② 合并冷路径：长期画像 + 内容标签 + 推荐特征                        │
│ ③ 召回 → 排序 → 重排（融合实时信号）                                │
│ ④ 返回下一批内容（已去重、已过滤负反馈、已按实时兴趣重排）          │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.3 实时反馈信号模型

| 信号类型 | 采集时机 | 存储 | 消费时机 |
|----------|----------|------|----------|
| 曝光 | 内容进入可视区域 | Redis set（已曝光 ID） | 下一批去重 |
| 点击/进入 | 用户点击内容 | Redis（session 兴趣加权） | 下一批排序加权 |
| 停留时长 | 离开内容时上报 | Redis（正向兴趣信号） | 下一批排序加权 |
| 跳过/快速滑走 | <1s 即离开 | Redis（负向信号） | 下一批降权同类 |
| 不感兴趣 | 显式操作 | Redis（负反馈过滤集） | 下一批过滤同类/同作者 |
| 点赞/收藏 | 显式操作 | Redis + Event Store | 实时加权 + 长期画像 |

所有信号同时写入热路径（Redis，毫秒级可用）和冷路径（Event Store → MQ，秒级持久化）。

### 5.4 接口设计：游标 + Session 上下文

```
GET /v1/content/feed?cursor={cursor}&session_id={sid}&limit=20

Response:
{
  "items": [...],
  "nextCursor": "...",
  "session_context": {
    "session_id": "...",
    "signals_received": 42,
    "interest_drift": "tech → food"
  }
}

POST /v1/content/feed/signal
{
  "session_id": "...",
  "signals": [
    { "content_id": "...", "action": "view", "duration_ms": 3200 },
    { "content_id": "...", "action": "skip", "duration_ms": 400 },
    { "content_id": "...", "action": "like" }
  ]
}
```

- 端侧批量上报信号（低频攒批，如每 3~5 秒或每次滑动到新内容时）。
- 服务端收到信号后即时更新 Redis 热路径。
- 下次 `GET /feed` 时，推荐引擎读取热路径 + 冷路径，产出实时个性化结果。

### 5.5 推荐场景（全内容类型 + 圈子统一适用）

| 场景 | 内容类型 | 实时信号 | 效果 |
|------|----------|----------|------|
| 发现流 | 图片、视频、微趣、文章 | 浏览偏好实时漂移 | 下一批自动调整内容类型和主题配比 |
| 圈子动态 | 圈子内帖子 | 圈子内互动偏好 | 优先展示感兴趣的圈子内容 |
| 圈子推荐 | 圈子本身 | 用户近期兴趣标签 | 推荐匹配实时兴趣的新圈子 |
| 相似推荐 | 同类内容 | 当前正在浏览的内容 | 「看了又看」实时关联推荐 |
| 关注流 | 关注用户内容 | 互动频次 + 实时兴趣 | 按兴趣相关度而非纯时间排序 |

### 5.6 算法自主演进

| 阶段 | 排序策略 | 自主能力 |
|------|----------|----------|
| 初期 | 规则 + 权重（标签匹配 + 热度 + 新鲜度 + 实时信号加权） | 规则可配置，通过 experiments 灰度 |
| 中期 | 轻量 ML（LR/GBDT，输入 = 推荐特征 + 实时信号） | 模型自动训练，A/B 实验自动评估 |
| 远期 | 深度模型（DIN/DIEN 等序列模型，输入 = session 行为序列 + 画像） | 端到端序列建模，实时 serving |

- 推荐算法通过 experiments 灰度部署，learning 评估效果，自动择优。
- 推荐策略版本化管理，可回滚、可审计。

---

## 6. 上下文管道与助手（Context Pipeline）

### 6.1 整体数据流

```
业务事件 + 实时信号
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Context Pipeline（框架层统一提供）                                │
│                                                                  │
│ ① 实时归集：Redis 热路径（session 信号、实时画像）               │
│ ② 事件持久化：Event Store（全量领域事件）                        │
│ ③ 标签提取：从内容/行为中提取标签（tag_taxonomy 约束）           │
│ ④ 一次加工：行为统计、频次、时序窗口、推荐特征                   │
│ ⑤ 二次加工：长期画像聚合、偏好建模、兴趣向量                    │
│ ⑥ 向量化：embedding 存储（内容 + 用户 + 上下文）                │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ 消费端                                                           │
│ • 推荐引擎：热路径实时信号 + 冷路径长期画像 → 实时个性化排序     │
│ • 小趣助手：结构化上下文 + 向量检索 → 理解用户 + 自主改进        │
│ • 运营分析：行为统计 + 标签分布 → 报表 + 策略优化                │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 小趣感知：三层上下文模型

小趣助手的核心能力是「懂用户」，通过三层上下文协同实现：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 第一层：页面级实时上下文（PageContext）—— 此刻我在看什么/做什么      │
│                                                                      │
│ 端侧实时上报当前页面类型 + 业务对象 + 可见内容 + 用户操作           │
│ 操作包括：浏览/点赞/收藏/评论/转发/不感兴趣等显式行为               │
│ → 小趣即时感知用户正在做什么和偏好信号                              │
│ → 显式喜好行为同步写入推荐热路径，作用于下一批信息流推荐            │
└─────────────────────────────────────────────────────────────────────┘
                            ↓ 叠加
┌─────────────────────────────────────────────────────────────────────┐
│ 第二层：Session 级行为上下文 —— 这次打开 App 我做了什么             │
│                                                                      │
│ Redis 热路径：session 内的浏览序列、兴趣漂移、显式喜好信号          │
│ （点赞/收藏/评论/转发 = 强正向信号，不感兴趣 = 强负向信号）         │
│ → 小趣理解用户当前 session 的行为趋势                               │
│ → 推荐引擎实时消费，下一批内容立即反映偏好变化                      │
└─────────────────────────────────────────────────────────────────────┘
                            ↓ 叠加
┌─────────────────────────────────────────────────────────────────────┐
│ 第三层：长期画像上下文（五维全息画像）—— 我是谁、我喜欢什么          │
│                                                                      │
│ 内容偏好 + 社交关系 + 圈子参与 + 聊天话题 + 助手交互记录           │
│ → 小趣深层理解用户个性化偏好与需求                                  │
└─────────────────────────────────────────────────────────────────────┘
```

#### 6.2.1 第一层：页面级实时上下文（PageContext）

端侧在用户切换页面或浏览内容时，实时上报当前页面上下文：

| 页面场景 | 上报的业务对象 | 关键字段 |
|----------|----------------|----------|
| **信息流浏览** | 当前可见的 Post 列表（ID + contentType + tags）+ 用户操作 | 浏览位置、停留内容、点赞/收藏/跳过 |
| **内容详情页** | Post 完整对象 + 用户显式操作（点赞/收藏/评论/转发/不感兴趣） | contentType、mediaUrls、tags、comments、userActions |
| **聊天会话** | Conversation + 近 N 条 Message | 对话方、话题、群聊成员 |
| **群聊** | Conversation(group) + 近 N 条 Message + 成员列表 | 群主题、活跃话题、成员关系 |
| **圈子详情** | Circle + 圈子动态 Post 列表 + CircleMember | 圈子主题/标签、成员画像 |
| **圈子发现** | 推荐圈子列表 | 圈子标签、匹配度 |
| **搜索页** | 搜索关键词 + 搜索结果列表 | query、结果类型 |
| **用户主页** | 目标用户的 UserProfile + 其 Post 列表 | 与当前用户的关系 |

端侧通过轻量 API 上报 PageContext（非轮询，仅在页面切换/内容进入时上报）：

```
POST /v1/assistant/page-context
{
  "page_type": "content_detail",
  "business_objects": {
    "post": { "id": "...", "content_type": "image", "title": "...", "tags": [...], "media_urls": [...] },
    "comments": [{ "id": "...", "body": "...", "author": "..." }, ...]
  },
  "user_action": "viewing",
  "user_actions": [
    { "action": "like", "object_id": "...", "timestamp": "..." },
    { "action": "save", "object_id": "...", "timestamp": "..." },
    { "action": "comment", "object_id": "...", "body": "...", "timestamp": "..." },
    { "action": "share", "object_id": "...", "target": "...", "timestamp": "..." }
  ],
  "timestamp": "..."
}

user_actions 中的显式喜好行为同步写入推荐热路径（Redis session_signals），
作用于信息流下一次推荐生成（见 §5.3 实时反馈信号模型）。
```

#### 6.2.2 第二层：Session 级行为上下文

与推荐共享的 Redis 热路径数据（见 §5），包括：
- Session 内浏览序列和兴趣漂移
- 实时交互信号（点赞/收藏/跳过/停留时长）
- 已互动内容和话题分布

#### 6.2.3 第三层：长期画像上下文（五维全息画像）

| 感知维度 | 数据来源（业务对象 + 事件） | 感知方式 | 产出 |
|----------|----------------------------|----------|------|
| **内容偏好** | Post（浏览/点赞/收藏/跳过）、content_tags | 实时 session 信号 + 长期行为统计 | 兴趣标签分布 + 实时漂移向量 |
| **社交关系** | FollowEdge、Conversation、Message（互动频次/话题） | 社交图谱分析 + 关系标签 | 亲密关系图 + 社交偏好 |
| **圈子参与** | Circle、CircleMember（加入/活跃/发帖/互动） | 圈子行为聚合 | 圈子兴趣图谱 + 活跃度 |
| **聊天话题** | Message（NLP 话题提取 → tag_taxonomy 映射） | 话题识别 + 情感分析 | 近期关注话题 + 情绪状态 |
| **助手交互** | AssistantRun、InteractionEvent（满意度/常问类型/偏好风格） | 记录 run 评估 + scorecard | 用户期望模型 + 风格偏好 |

### 6.3 小趣主动交互能力（按页面场景）

小趣不仅被动回答，更根据 PageContext 主动提供当前场景相关的能力。每种页面场景下，小趣主动推送**建议操作（Suggested Actions）**。

#### 6.3.1 信息流浏览场景

小趣感知用户正在浏览信息流，结合推荐实时信号：
- **信息流推荐优化**：根据实时浏览偏好动态调整推荐（与 §5 推荐引擎联动）
- **主动提问建议**：「想看更多旅行类内容？」「要不要关注这位创作者？」

#### 6.3.2 内容详情页场景（图片/视频/文章/微趣）

小趣感知用户正在查看的具体内容，提供：

| 内容类型 | 小趣主动能力 | 技术基础 |
|----------|-------------|----------|
| **图片** | 识别地点/景点（「这是哪里？」）、识别商品（「这件衣服是什么品牌？」）、相似图片推荐 | 多模态理解（图片 → 视觉 embedding + 物体识别） |
| **视频** | 视频内容总结、关键时刻标记、相关问答 | 视频帧采样 + 语音转文字 + 摘要生成 |
| **文章** | 全文总结、关键观点提取、延伸阅读建议 | NLP 摘要 + 关键词提取 |
| **微趣** | 话题相关互动建议、相似微趣推荐 | 短文本理解 + 标签匹配 |
| **游记/景点** | 出行规划建议、路线推荐、相关攻略、住宿/餐饮问询 | 地理信息提取 + 知识库检索 |
| **评论区** | 评论总结（正面/负面/关键观点）、自动回复内容生成、互动建议 | NLP 情感分析 + 摘要 + 生成 |

所有内容类型通用：
- **优化搜索**：根据当前内容自动补全搜索建议（如看到咖啡相关内容 → 搜索建议「附近咖啡店」）
- **关联问询**：根据当前内容生成 2~3 个相关问题供用户点击快速问询
- **自然语言问答**：用户可以对当前内容用自然语言提问（如「这张图的拍摄地在哪？」「帮我总结一下文章核心观点」）

#### 6.3.3 聊天会话场景（含群聊）

小趣感知当前对话上下文：

| 能力 | 说明 |
|------|------|
| **对话总结** | 长对话/群聊消息摘要（帮用户快速了解错过的讨论） |
| **自动回复生成** | 根据对话上下文生成回复建议（用户可一键发送或编辑） |
| **话题识别** | 识别当前聊天话题，推荐相关内容/圈子/活动 |
| **群聊辅助** | 群讨论总结、投票/决策辅助、@提醒建议 |
| **跨域关联** | 聊天中提到的地点/商品/内容 → 自动关联详情和推荐 |

#### 6.3.4 圈子场景

小趣感知用户正在浏览的圈子：

| 能力 | 说明 |
|------|------|
| **关联圈子推荐** | 根据当前圈子的标签和主题推荐相似/互补圈子 |
| **好友推荐加入** | 结合社交图谱推荐可能感兴趣的好友加入当前圈子 |
| **圈子动态总结** | 帮用户快速了解圈子近期热门讨论和动态 |
| **发帖建议** | 根据圈子主题和用户画像建议发帖话题 |

#### 6.3.5 搜索场景

| 能力 | 说明 |
|------|------|
| **上下文增强搜索** | 结合当前浏览内容和画像优化搜索结果（看了游记再搜「酒店」→ 优先推荐该目的地酒店） |
| **搜索建议** | 根据 PageContext 主动推荐搜索词 |
| **自然语言搜索** | 支持「帮我找类似这种风格的内容」「有没有关于这个话题的圈子」等 |

#### 6.3.6 Suggested Actions 接口

端侧在页面加载后，从小趣获取当前页面的建议操作：

```
GET /v1/assistant/suggested-actions?page_type=content_detail&object_id={postId}

Response:
{
  "actions": [
    { "type": "summary", "label": "帮你总结这篇文章", "icon": "summary" },
    { "type": "question", "label": "这张照片是在哪里拍的？", "icon": "location" },
    { "type": "question", "label": "这件外套是什么品牌？", "icon": "product" },
    { "type": "plan", "label": "帮你规划这个目的地的行程", "icon": "travel" },
    { "type": "search", "label": "搜索类似内容", "icon": "search" }
  ],
  "comment_summary": {
    "total": 128,
    "sentiment": { "positive": 0.65, "neutral": 0.25, "negative": 0.1 },
    "key_topics": ["风景很美", "交通不便", "推荐住宿"]
  }
}
```

### 6.4 小趣助手上下文消费模型

助手 run 时消费三层上下文的完整模型：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 小趣 Run 时上下文注入                                                 │
│                                                                      │
│ ① PageContext（第一层）                                               │
│    当前页面类型 + 业务对象数据 + 用户操作                             │
│    → 决定小趣应提供哪些主动能力                                      │
│    → 为用户问询提供精准上下文（如「帮我总结」→ 总结当前内容）        │
│                                                                      │
│ ② Session 上下文（第二层）                                           │
│    当前 session 浏览序列 + 兴趣漂移 + 实时信号                      │
│    → 理解用户当前意图趋势                                            │
│                                                                      │
│ ③ 长期画像（第三层）                                                 │
│    五维全息画像 + embedding                                          │
│    → 个性化回答风格和深层理解                                        │
│                                                                      │
│ ④ 内容理解（按需加载）                                               │
│    图片视觉理解 / 视频摘要 / 文章 NLP / 评论分析                    │
│    → 支撑多模态问答和内容总结                                        │
│                                                                      │
│ ⑤ 向量检索（RAG）                                                    │
│    记录交互 embedding + 内容 embedding + 知识库                      │
│    → 检索相关记忆和知识增强回答                                      │
│                                                                      │
│ 全部注入 prompt → LLM 推理 → 流式输出（SSE）                        │
└─────────────────────────────────────────────────────────────────────┘
```

- **主动模式**：用户进入页面 → 小趣根据 PageContext 自动生成 Suggested Actions（含 Skill 推荐）→ 用户点击或忽略
- **问答模式**：用户输入自然语言 → Skill Router 路由到合适 Skill → Skill 结合三层上下文 + 内容理解 + RAG 回答
- **Skill 模式**：用户主动选择 Skill → Skill 获取授权上下文 + 调用可用 Tools → 完成任务
- **自主改进**：助手根据用户反馈调整策略，形成 learning → inference → feedback 闭环

### 6.5 Skill 可扩展框架

小趣的能力不是封闭的，而是通过 Skill 框架持续扩展能力边界。Skill 是小趣的能力单元，可由内部开发或生态开放。

#### 6.5.1 核心概念

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Skill 生态                                                                │
│                                                                          │
│ ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │
│ │ Skill Store      │  │ Skill Router      │  │ Tool Registry           │  │
│ │                  │  │                   │  │                        │  │
│ │ 注册/发现/       │  │ PageContext +     │  │ 当前页面可用的          │  │
│ │ 版本管理/        │  │ 用户意图          │  │ 业务能力/操作           │  │
│ │ 评分/审核        │  │ → 匹配适用 Skill  │  │ → Skill 可调用          │  │
│ └─────────────────┘  └──────────────────┘  └────────────────────────┘  │
│          │                    │                        │                 │
│          ▼                    ▼                        ▼                 │
│ ┌───────────────────────────────────────────────────────────────────┐  │
│ │ Skill Runtime（执行环境）                                           │  │
│ │                                                                    │  │
│ │ • 上下文注入：三层上下文按 Skill 声明的权限范围注入               │  │
│ │ • Tool 调用：Skill 通过 Tool Registry 调用业务能力                │  │
│ │ • 权限沙箱：用户授权 + metadata 策略约束                         │  │
│ │ • 流式输出：通过 SSE 输出结果                                    │  │
│ └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 6.5.2 Skill 定义（SkillManifest）

每个 Skill 通过元数据声明自身的能力、上下文需求和工具依赖：

```yaml
# contracts/metadata/skill_catalog.yaml
skills:
  - id: travel_planner
    name: 出行规划助手
    description: 根据游记/景点内容生成出行规划
    provider: internal                      # internal | ecosystem
    version: "1.0.0"

    # ① Skill 适用的页面场景（Skill Router 据此匹配）
    applicable_pages:
      - page_type: content_detail
        content_types: [article, image]     # 特定内容类型
        tag_match: [topic_travel, topic_food, topic_local]  # 内容标签匹配

    # ② Skill 需要的上下文范围（用户授权后注入）
    context_requirements:
      page_context: required                # 当前页面业务对象
      session_context: optional             # session 行为上下文
      profile_dimensions:                   # 长期画像中需要的维度
        - content_preference                # 内容偏好
        - circle_participation              # 圈子参与
      content_analysis: required            # 内容多模态分析结果

    # ③ Skill 可调用的 Tools（业务能力）
    tool_dependencies:
      - tool: content.search                # 搜索相关内容
      - tool: content.recommend_similar     # 推荐相似内容
      - tool: location.resolve              # 地理位置解析
      - tool: location.nearby_search        # 附近搜索
      - tool: post.create_draft             # 创建草稿

    # ④ Skill 输出类型
    output_types: [text, structured_plan, action_card]

    # ⑤ 权限与安全
    data_classification_max: PUBLIC         # 最高可访问的数据分级
    requires_user_consent: true             # 是否需要用户主动授权
```

#### 6.5.3 Tool Registry：页面级业务能力注册

每个页面场景暴露可被 Skill 调用的业务能力（Tools）：

| 页面场景 | 可用 Tools | 说明 |
|----------|-----------|------|
| **全局** | `user.profile.read`、`content.search`、`content.recommend_similar`、`tag.resolve` | 所有场景通用 |
| **内容详情** | `content.get_detail`、`content.get_comments`、`content.analyze`（多模态）、`content.like`、`content.save`、`post.create_draft`（回复草稿） | 内容相关操作 |
| **聊天** | `chat.get_messages`、`chat.send_message`、`chat.summarize`、`chat.generate_reply` | 聊天相关操作 |
| **圈子** | `circle.get_detail`、`circle.get_members`、`circle.recommend_related`、`circle.suggest_friends` | 圈子相关操作 |
| **搜索** | `search.execute`、`search.suggest`、`search.semantic`（向量搜索） | 搜索操作 |
| **信息流** | `feed.get_next`、`feed.report_signal`、`feed.adjust_preference` | 信息流操作 |

Tools 通过 metadata 注册（`tool_catalog.yaml`），与 entity_catalog 对齐：

```yaml
# contracts/metadata/tool_catalog.yaml
tools:
  - id: content.analyze
    name: 内容多模态分析
    description: 对图片/视频/文章进行识别、摘要、实体提取
    applicable_pages: [content_detail]
    input_entities: [Post]
    output_type: ContentAnalysisResult
    data_classification_max: PUBLIC
    rate_limit: 10/min

  - id: location.nearby_search
    name: 附近搜索
    description: 根据地理位置搜索附近的 POI
    applicable_pages: [content_detail, search]
    input: { type: GeoPoint, radius_km: number }
    output_type: POIList
    requires_user_consent: true             # 需要用户授权位置
    data_classification_max: PII

  - id: chat.generate_reply
    name: 生成回复建议
    description: 根据对话上下文生成回复候选
    applicable_pages: [chat, group_chat]
    input_entities: [Conversation, Message]
    output_type: ReplySuggestions
    data_classification_max: SENSITIVE      # 聊天内容敏感
    requires_user_consent: true
```

#### 6.5.4 Skill Router：场景匹配与调度

```
用户进入页面 / 用户提问 / 用户点击 Suggested Action
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ Skill Router                                                       │
│                                                                    │
│ 输入：                                                             │
│   PageContext（页面类型 + 业务对象 + 内容标签）                    │
│   + 用户意图（自然语言 / 点击 action / 主动选择 Skill）           │
│                                                                    │
│ 匹配策略：                                                         │
│   ① 页面匹配：Skill.applicable_pages ∩ 当前 PageContext           │
│   ② 标签匹配：Skill.tag_match ∩ 当前内容 tags                    │
│   ③ 意图匹配：用户问询 → NLU 意图识别 → Skill 能力匹配          │
│   ④ 权限检查：Skill 所需 data_classification ≤ 用户已授权级别     │
│                                                                    │
│ 输出：                                                             │
│   排序后的适用 Skill 列表（用于 Suggested Actions 展示）           │
│   或 直接调度到最匹配的 Skill 执行                                │
└───────────────────────────────────────────────────────────────────┘
```

#### 6.5.5 上下文授权模型

Skill 获取用户上下文需要**双重授权**：

```
┌─────────────────────────────────────────────────────────────────────┐
│ 上下文授权：用户主权 + metadata 策略                                  │
│                                                                      │
│ ① Skill 声明：context_requirements（我需要什么上下文）              │
│ ② metadata 策略：field_policy.classification + api_exposure          │
│    → 框架层强制过滤（PII/SENSITIVE 字段不可泄露给低权限 Skill）     │
│ ③ 用户授权：首次使用 Skill 时弹窗确认授权范围                      │
│    「出行规划助手需要访问你的当前浏览内容和兴趣偏好，是否允许？」    │
│ ④ 授权记录：user_skill_consent（可随时撤销）                       │
│                                                                      │
│ 注入上下文时的过滤链：                                               │
│   原始上下文 → classification 过滤 → api_exposure 过滤              │
│   → Skill 声明范围裁剪 → 用户授权范围裁剪 → 最终注入 Skill         │
└─────────────────────────────────────────────────────────────────────┘
```

#### 6.5.6 Skill Store

| 能力 | 说明 |
|------|------|
| **注册与发布** | Skill 开发者提交 SkillManifest + 实现代码；审核通过后上架 |
| **版本管理** | 每个 Skill 版本化，支持灰度发布和回滚 |
| **发现与推荐** | 用户可在 Skill Store 浏览；系统根据用户画像和场景自动推荐 Skill |
| **评分与反馈** | 用户对 Skill 评分，learning 收集效果指标 |
| **审核与安全** | 审核 Skill 的 context_requirements 和 tool_dependencies 是否合理；sandbox 执行 |
| **生态开放** | 内部 Skill（provider: internal）先行；后续开放 ecosystem 接入 |

#### 6.5.7 Skill 与已有能力的关系

之前 §6.3 定义的小趣主动能力（内容总结、评论分析、出行规划、搜索优化等）均可建模为内置 Skill：

| 已有能力 | 对应 Skill | 类型 |
|----------|-----------|------|
| 图片地点/商品识别 | `image_recognizer` | internal |
| 文章总结与观点提取 | `article_summarizer` | internal |
| 评论总结与回复生成 | `comment_analyzer` | internal |
| 出行规划 | `travel_planner` | internal |
| 对话总结与回复建议 | `chat_assistant` | internal |
| 圈子推荐与好友建议 | `circle_recommender` | internal |
| 上下文增强搜索 | `smart_search` | internal |
| 视频摘要 | `video_summarizer` | internal |

生态 Skill 示例（未来开放）：

| Skill | provider | 说明 |
|-------|----------|------|
| `food_guide` | ecosystem | 美食推荐与餐厅预订 |
| `fashion_advisor` | ecosystem | 穿搭建议与商品链接 |
| `language_tutor` | ecosystem | 外语学习助手 |
| `fitness_coach` | ecosystem | 健身计划与打卡 |

### 6.6 缓存策略与实时性保障

| 数据 | 存储 | TTL | 更新策略 |
|------|------|-----|----------|
| **PageContext** | Redis Hash | 页面生命周期（用户离开即过期，默认 5min） | 端侧页面切换时上报 |
| **Suggested Actions 缓存** | Redis | 同 PageContext | PageContext 变更时重新生成 |
| Session 实时信号 | Redis Hash/Set | session 生命周期（默认 30min） | 每次用户交互即时写入 |
| 实时兴趣向量 | Redis | session 级别 | 信号累积后增量更新 |
| 已曝光 ID 集合 | Redis Set | session 级别 | 每次曝光追加 |
| 负反馈过滤集 | Redis Set | 24h | 显式操作时写入 |
| 长期画像 | MongoDB ReadModel | - | Projector 异步更新 |
| 内容 embedding | 向量存储 | - | 内容创建时生成 |
| **内容理解缓存**（图片识别/文章摘要/评论总结） | Redis | 24h | 首次请求时生成并缓存 |
| 推荐特征宽表 | MongoDB | - | Projector 异步更新 |

---

## 7. 底座层：runtime 能力组件

| 子包 | 职责 | 对接 |
|------|------|------|
| config | ConfigProvider 抽象（File/Nacos） | platform-ops |
| errors | 统一错误码、用户文案 | - |
| observability | 日志/指标/追踪（OTEL） | platform-ops |
| http | Inbound/Outbound pipeline | - |
| **streaming** | SSE Server/Client、Change Stream 适配 | 实时推送 |
| messaging | Envelope、trace 传播、幂等消费 | product-ops |
| governance | 超时/重试/熔断/限流/降级 | platform-ops |
| experiments | 实验分桶、灰度策略 | product-ops |
| learning | 反馈事件、评估、策略版本 | product-ops |
| **recommendation** | 实时信号归集（热路径）、特征合并、召回/排序/重排、算法版本管理 | product-ops |
| **skill** | Skill Runtime（路由/调度/上下文注入/Tool 调用/沙箱/授权）、Skill Store 管理、SkillManifest 注册 | assistant-service |

---

## 8. 业务层约束（强制遵从）

| 约束 | 说明 |
|------|------|
| 业务对象先行 | 新能力必须先注册 entity + field_policy + 标签，再暴露接口或存储 |
| 禁止临时补丁 | 禁止绕过 metadata 在 OpenAPI、DB、日志、推荐、运营中直接加字段 |
| 读写走框架 | 写走 Repository + 领域事件；读走 ReadModel / Query |
| 横切走 runtime | 日志、指标、实验、治理、推荐、流式等统一通过 runtime 子包 |
| 标签走 taxonomy | 标签枚举、新增、关联均通过 tag_taxonomy，禁止硬编码 |
| 一致性 | App、运营、推荐、小趣助手对同一业务对象的处理与 metadata 一致 |

---

## 9. DDD 聚合定义与服务分层

### 9.1 聚合根与聚合边界

entity_catalog 中通过 `aggregate_root` 和 `aggregate_members` 定义聚合边界：

| 聚合根 | 聚合成员 | 所属 domain | 一致性边界 |
|--------|----------|-------------|------------|
| Post | Comment、MediaAsset | content | Post 内的评论和媒体资源在同一事务内 |
| Conversation | Message | chat | 会话内的消息在同一事务内 |
| UserProfile | Persona | user | 用户档案与人设在同一事务内 |
| Circle | CircleMember | circle | 圈子与成员在同一事务内 |
| AssistantRun | InteractionEvent | assistant | run 与交互事件在同一事务内 |

- 聚合根拥有全局唯一 ID，聚合成员仅通过聚合根访问。
- 跨聚合交互必须通过领域事件（异步最终一致），禁止直接调用。
- codegen 根据聚合定义生成完整 DDD 分层目录。

### 9.2 服务内部 DDD 分层

每个业务服务按以下分层实现，由 codegen 从 metadata 的 `ddd_layer_mapping` 生成：

```
services/<service>/
├── domain/                  # 领域层：聚合根、实体、值对象、领域事件、Repository 接口
│   ├── <aggregate>/
│   │   ├── entity.go        ← codegen from entity_catalog
│   │   ├── events.go        ← codegen from event_catalog
│   │   └── repository.go    ← codegen from capabilities
├── application/             # 应用层：ApplicationService、Command/Query handler
│   └── <aggregate>_service.go  ← codegen 骨架 + 手写业务逻辑
├── adapters/                # 适配层：HTTP/gRPC handler、外部服务客户端
│   ├── http_handler.go      ← codegen from crud_paths
│   └── grpc_handler.go
├── infrastructure/          # 基础设施层：Repository 实现、存储适配器
│   └── <aggregate>_repo.go  ← codegen from storage_backend
└── bootstrap/               # 启动层：依赖注入、配置加载
    └── main.go
```

依赖方向：domain ← application ← adapters ← infrastructure ← bootstrap。

---

## 10. 超前建设与扩展模式

### 10.1 超前建设

- 业务对象、聚合边界、标签体系与 metadata 超前于特性建设。
- 新增 entity/field/tag/event 时，同步更新全部 metadata，并完成所有消费场景的策略声明。
- Context Pipeline 作为框架层能力超前就绪，新 entity 注册后自动参与上下文构建与小趣感知。

### 10.2 0→1（AI Agent 新建服务完整流程）

```
1. 领域分析：Agent 根据业务需求识别 domain、聚合根、聚合成员、事件
2. 注册 metadata：在 entity_catalog 中定义 aggregate_root、aggregate_members、
   capabilities、storage_backend、ddd_layer_mapping
3. 定义字段策略：field_policy（含 classification、log_policy、recommend_feature 等）
4. 定义标签：tag_taxonomy 中新增或关联标签域
5. 定义事件：event_catalog 中声明领域事件及 consumers
6. 运行 codegen：自动生成完整 DDD 分层目录 + Repository + Handler + OpenAPI + Migration
7. 补充业务逻辑：Agent 仅需编写 domain 层聚合行为 + application 层编排
8. make verify：校验 metadata ↔ 契约 ↔ 存储 ↔ 代码一致性
9. make gate：全绿合入
10. 归入特性树：完成的特性自动沉淀至 specs/feature-tree，更新 tree_index
```

### 10.3 1→n（在已有底座上扩展）

- 新业务对象仅通过 metadata 扩展；codegen 产出增量骨架；框架自动应用策略。
- 禁止在业务代码中为单特性增加与 metadata 不一致的处理逻辑。
- 新 entity 注册后自动参与推荐特征归集、小趣上下文构建、运营指标上报。

---

## 11. 反馈与学习闭环

### 11.1 生产反馈驱动优化

| 环节 | 机制 | 说明 |
|------|------|------|
| 行为归集 | learning 上报 + event_catalog | 用户显式/隐式反馈结构化存储 |
| 效果评估 | SLI/SLO 绑定 entity | 推荐 CTR、留存、助手满意度等 |
| 策略调优 | experiments + learning | 实验→效果→决策的数据流 |
| 灰度验证 | governance + experiments | 新策略灰度发布 + 效果验证 |

### 11.2 AI Agent 全生命周期自主闭环

#### 11.2.1 Agent 主导的完整生命周期

```
┌───────────────────────────────────────────────────────────────────┐
│ 0→1：新服务 / 新聚合                                               │
│                                                                    │
│ 需求分析 → 领域建模 → 注册 metadata → codegen → 补充业务 → verify │
│     ↑                                                         │    │
│     └── Agent 从已有特性树学习领域模式                          │    │
└──────────────────────────────────────────────────────────────│────┘
                                                               ↓
┌───────────────────────────────────────────────────────────────────┐
│ 1→n：基于底座的特性端到端自主                                       │
│                                                                    │
│ 特性需求 → metadata delta → codegen 增量 → 业务逻辑 → verify     │
│ → 生成 agent_task_pack.yaml → 归入特性树                          │
└──────────────────────────────────────────────────────────────│────┘
                                                               ↓
┌───────────────────────────────────────────────────────────────────┐
│ 上线后：生产数据回流学习                                             │
│                                                                    │
│ SLI/SLO 指标 → 效果评估 → Agent 决策知识库更新                    │
│ → 下次开发时 Agent 可引用记录效果数据做更好的设计决策               │
└───────────────────────────────────────────────────────────────────┘
```

#### 11.2.2 agent_task_pack.yaml schema

```yaml
version: 1
feature_slug: "feed-realtime-recommendation"
feature_tree_path: "content/feed/realtime-recommendation"
metadata_delta:
  entity_catalog:
    - action: add
      entity: SessionSignal
      aggregate_root: false
      aggregate_parent: UserProfile
  field_policy:
    - action: add
      entity: SessionSignal
      fields: [sessionId, userId, signals, createdAt]
  event_catalog:
    - action: add
      event: session.signal_reported
  tag_taxonomy:
    - action: add
      taxonomy: content_tags
      tags: [{id: signal_positive, label: 正向信号}]
contract_delta:
  openapi_paths:
    - POST /v1/content/feed/signal
  dart_dtos:
    - FeedSignalRequest
    - FeedSignalResponse
codegen_outputs:
  - domain/session_signal/entity.go
  - domain/session_signal/events.go
  - adapters/http_handler_signal.go
  - infrastructure/session_signal_repo.go
business_logic_files:
  - application/feed_signal_service.go     # Agent 手写
acceptance:
  - id: A1
    description: "信号上报后 Redis 热路径即时更新"
    sli_binding: "feed.signal.latency_p99 < 50ms"
production_feedback:
  sli_metrics: ["feed.signal.latency_p99", "feed.ctr", "feed.retention_d1"]
  learning_loop: "上线 7 天后自动评估 CTR 与留存，效果数据归入 Agent 决策知识库"
```

#### 11.2.3 特性树沉淀

- 每个特性完成后，Agent 自动将 `agent_task_pack.yaml` 归入 `specs/feature-tree/`。
- `tree_index.yaml` 自动更新，形成**全量特性树**。
- Agent 后续开发时可检索特性树，学习已有领域模式、接口模式、存储模式。
- 面向未来：特性树 + SLI 回流 = Agent 可自主判断新需求应复用哪些已有能力、应避免哪些已知坑点。

---

## 12. 契约测试基础设施

### 12.1 测试引擎选型

服务侧契约测试使用**真实兼容的轻量测试引擎**，不 mock 存储层。业务代码零修改，仅通过配置切换连接地址。

| 生产存储 | 测试引擎 | Go 包 | 启动时间 | 依赖 |
|----------|----------|-------|----------|------|
| PostgreSQL 16 | embedded-postgres | `github.com/fergusstrange/embedded-postgres` | ~2s | 无（自带二进制） |
| MongoDB 7 | testcontainers-go (mongo module) | `github.com/testcontainers/testcontainers-go/modules/mongodb` | ~3s | Docker |
| Redis 7 | miniredis/v2 | `github.com/alicebob/miniredis/v2` | <1ms | 无 |

### 12.2 测试隔离策略

- **服务内使用真实数据库**：Repository → 真实引擎（embedded-postgres/testcontainers/miniredis）
- **EventPublisher → Spy**：捕获发布的事件用于断言，不依赖真实 MQ
- **跨服务 API → Mock**：隔绝级联影响
- **外部 AI API → Mock**：LLM/Embedding 接口 mock

### 12.3 测试生命周期

```
TestMain (per package)
├── 启动测试引擎（embedded-pg/testcontainers/miniredis）
├── 执行 migration（从 storage.yaml 生成的 DDL）
├── 初始化 Repository（生产代码，零修改）
├── t.Run("scenario")
│   ├── Seed（fixture 工厂预制数据）
│   ├── Execute（Application Service / HTTP Handler）
│   ├── Assert（数据库状态 + 事件 + API 响应）
│   └── Cleanup（TRUNCATE / DeleteMany / FlushAll）
└── 关闭测试引擎
```

### 12.4 codegen 生成物

metadata 驱动生成以下测试代码：

| 模板 | 输出 | 说明 |
|------|------|------|
| `testmain.go.tmpl` | `*_testmain_test.go` | 引擎启动/关闭 + migration |
| `fixture.go.tmpl` | `*_fixture_test.go` | 从 fields.yaml 约束生成合规 Builder |
| `event_spy.go.tmpl` | `*_event_spy_test.go` | EventPublisher spy + 断言方法 |
| `contract_test.go.tmpl` | `*_contract_test.go` | service.yaml 定义的场景骨架 |

详细配置见 `contracts/metadata/_shared/test_infra.yaml`，每个业务对象的测试配置见其 `service.yaml` 的 `contract_test` 节。

---

## 13. 任务规划

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

## 13. 元数据与规范引用

- 元数据位置：`quwoquan_service/contracts/metadata/`（v3 模块化目录结构）
  - 每个业务对象独立目录（`post/`, `user_profile/`, `conversation/`, `circle/`, `assistant_run/` 等）
  - 每个目录包含：`aggregate.yaml` + `fields.yaml` + `events.yaml` + `storage.yaml` + `service.yaml`
  - 独立实体使用 `entity.yaml` 替代 `aggregate.yaml`
  - 共享定义：`_shared/tag_taxonomy.yaml`, `_shared/types.yaml`, `_shared/redis_keyspace.yaml`, `_shared/test_infra.yaml`
  - 投影定义：`_projections/` 目录
  - 向量定义：`_vectors/` 目录
  - 设计总览：`DESIGN.md`（含 §12 契约测试策略）
  - P2 新增：`skill_catalog.yaml`、`tool_catalog.yaml`（Skill/Tool 注册）
- 配套规范：
  - `specs/runtime_framework_design.md` — 技术设计
  - `specs/RUNTIME_DEVELOPMENT_PLAN.md` — 落地计划（P0-fix → P0 → P1 → P2 → P3）
  - `specs/runtime_gap_analysis_and_plan.md` — 商用准出 Gap 分析与开发计划
  - `specs/runtime_extension_catalog.md` — 端云一体化可扩展开发规范（20 个扩展场景 + qwq CLI + 验证流水线）
  - `specs/00_AGENT_MASTER_SPEC.md` — Agent 入口
