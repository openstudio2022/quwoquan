# 模型元数据契约（Metadata Contracts）v3

本目录是 runtime 框架的**元数据单一事实来源**，驱动接口、存储、日志、安全、推荐、标签、画像、助手上下文、契约测试及代码生成。

规范依据：`specs/runtime_framework_spec.md` §3 | 设计总览：`DESIGN.md`

---

## 目录结构

```
contracts/metadata/
├── DESIGN.md                     # 设计总览（业务对象分析 + 存储选型 + 超前规划）
├── README.md                     # 本文件
│
├── _shared/                      # 跨聚合共享定义
│   ├── tag_taxonomy.yaml         # 标签分类体系（4 域：用户/内容/社交/圈子）
│   ├── types.yaml                # 共享类型（GeoPoint/Enum/Classification/LogPolicy）
│   ├── redis_keyspace.yaml       # Redis 全局键空间设计
│   └── test_infra.yaml           # 契约测试基础设施配置（测试引擎 + 数据管理）
│
├── post/                         # Post 聚合（content domain, MongoDB）
│   ├── aggregate.yaml            # 聚合定义（Post + Comment + MediaAsset + ContentReaction）
│   ├── fields.yaml               # 全实体字段策略
│   ├── events.yaml               # 领域事件（12 个）
│   ├── storage.yaml              # MongoDB 集合 + 索引 + 向量 + 分片
│   └── service.yaml              # content-service 归属 + API 路由 + 契约测试
│
├── user_profile/                 # UserProfile 聚合（user domain, PostgreSQL）
│   ├── aggregate.yaml            # 聚合定义（+Persona/Auth/Device/Setting/Proposal）
│   ├── fields.yaml               # 全实体字段策略（含安全分级）
│   ├── events.yaml               # 领域事件（9 个）
│   ├── storage.yaml              # PostgreSQL 表 + 关系映射 + Redis 缓存
│   └── service.yaml              # user-service 归属 + API 路由 + 契约测试
│
├── conversation/                 # Conversation 聚合（chat domain, MongoDB）
│   ├── aggregate.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── circle/                       # Circle 聚合（circle domain, MongoDB）
│   ├── aggregate.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── assistant_run/                # AssistantRun 聚合（assistant domain, MongoDB）
│   ├── aggregate.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── follow_edge/                  # 独立实体（user domain, MongoDB）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── block_edge/                   # 独立实体（user domain, PostgreSQL）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── report/                       # 独立实体（content domain, PostgreSQL）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── notification/                 # 独立实体（notification domain, MongoDB）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── skill_consent/                # 独立实体（assistant domain, PostgreSQL）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── visit_record/                 # 独立实体（ops domain, MongoDB）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── experiment_bucket/            # 独立实体（ops domain, PostgreSQL）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── _projections/                 # ReadModel 投影定义
│   ├── discovery_feed.yaml       # 发现流
│   ├── circle_feed.yaml          # 圈子动态流
│   ├── chat_inbox.yaml           # 聊天列表
│   ├── user_profile_view.yaml    # 用户画像（推荐/助手）
│   └── recommend_feature.yaml    # 推荐特征宽表
│
└── _vectors/                     # 向量存储定义
    ├── content_embedding.yaml    # 内容语义向量（1536维）
    └── user_context_embedding.yaml # 用户上下文向量（1536维）
```

---

## 每个业务对象目录结构

### 聚合目录（5 个聚合根）

| 文件 | 职责 |
|------|------|
| `aggregate.yaml` | 聚合定义：domain、成员关系、存储后端、缓存、capabilities、DDD 层映射 |
| `fields.yaml` | 全实体字段策略：type、constraints、classification、log/api/ops exposure、推荐特征 |
| `events.yaml` | 领域事件：producer、consumers、channel、payload、推荐影响 |
| `storage.yaml` | 存储映射：表/集合定义、索引、唯一约束、Redis 缓存配置 |
| `service.yaml` | 服务归属：API 路由、消费者声明、**契约测试策略** |

### 独立实体目录（7 个独立实体）

与聚合目录相同，但 `aggregate.yaml` 替换为 `entity.yaml`（无成员定义）。

---

## 强制要求

- **元数据先行**：新增 entity/field/tag/event 必须先在对应目录注册，再暴露接口或实现存储
- **一致性校验**：`make verify` 校验 metadata 内部一致性
- **禁止临时补丁**：禁止在代码、接口、日志中硬编码与 metadata 冲突的字段含义或策略
- **分类声明**：涉及 PII/SENSITIVE/SECRET 的字段必须声明 `classification`
- **代码生成**：`make codegen` 从 metadata 生成 Go struct/Repository/Handler/OpenAPI/Migration
- **变更追溯**：metadata 变更走 Git + PR review，同步更新特性 traceability

---

## 契约测试策略

每个 `service.yaml` 包含 `contract_test` 节，定义基于元数据的接口契约测试。
测试基础设施配置见 `_shared/test_infra.yaml`，详细设计见 `DESIGN.md` §12。

### 原则

| 维度 | 策略 |
|------|------|
| **端侧测试** | App 自身不依赖云端，mock 云端 API 响应（从 `fields.yaml` 自动生成 mock 数据） |
| **服务侧测试** | 服务使用**真实测试数据库**（embedded-postgres / testcontainers mongo / miniredis），**不 mock 存储层** |
| **隔离边界** | 端侧 mock 服务 API；服务侧真实存储 + spy EventPublisher + mock 跨服务和 AI API |
| **数据管理** | 每次测试前 Seed 预制数据，跑完 TRUNCATE/DeleteMany/FlushAll 清理 |
| **断言来源** | 真实数据库查询验证持久化 + spy 捕获验证事件 + API 响应验证 schema |

### 测试引擎选型

| 生产引擎 | 测试引擎 | Go 包 | 特点 |
|---------|---------|------|------|
| PostgreSQL 16 | embedded-postgres | `github.com/fergusstrange/embedded-postgres` | 真实 PG 二进制，无需 Docker |
| MongoDB 7 | testcontainers | `github.com/testcontainers/testcontainers-go/modules/mongodb` | 真实 mongod 容器 |
| Redis 7 | miniredis/v2 | `github.com/alicebob/miniredis/v2` | 纯 Go 内存实现，命令兼容 |

**业务代码零修改**，仅通过配置切换连接地址。

### 覆盖要求

- 每个 `api_routes` 至少一个测试场景
- 所有 `state_machine` 转换覆盖（正向 + 异常）
- 所有 `unique_constraints` 有违反测试（真实数据库拒绝）
- 所有 `SECRET` 字段验证不出现在 API 响应
- 所有 `events` 验证 payload_fields 正确（spy 捕获）
- 缓存一致性：Redis 写入/失效/TTL 真实验证
- 并发安全：乐观锁/排他约束真实数据库并发验证

---

## 消费关系

```
aggregate.yaml / entity.yaml ──→ codegen（struct/repo/handler/migration）
                              ──→ EntityRegistry（运行时策略查询）
fields.yaml                  ──→ codegen（OpenAPI schema / 拦截链 / mock 生成）
                              ──→ 日志脱敏 / 接口过滤 / 推荐特征标记
                              ──→ 契约测试 mock 数据生成
_shared/tag_taxonomy.yaml    ──→ 标签服务 / 画像聚合 / 推荐引擎
events.yaml                  ──→ Event Store / MQ 路由 / Projector 注册
                              ──→ 契约测试事件发布断言
storage.yaml                 ──→ codegen（migration / 索引脚本）/ 存储适配器
                              ──→ 契约测试 Repository mock
service.yaml                 ──→ 服务归属 / API 路由注册 / 消费者声明
                              ──→ 契约测试场景定义 + 覆盖率要求
_projections/*.yaml          ──→ Projector 注册 / ReadModel 生成
_vectors/*.yaml              ──→ 向量索引创建 / Embedding Pipeline 注册
```

---

## 统计

| 类目 | 数量 |
|------|------|
| 聚合根 | 5（UserProfile, Post, Conversation, Circle, AssistantRun） |
| 独立实体 | 7（FollowEdge, BlockEdge, Report, Notification, SkillConsent, VisitRecord, ExperimentBucket） |
| PostgreSQL 实体 | 10（UserProfile 聚合 6 + BlockEdge + Report + SkillConsent + ExperimentBucket） |
| MongoDB 实体 | 15+（Post 聚合 4 + Conversation 2 + Circle 2 + AssistantRun 2 + FollowEdge + Notification + VisitRecord + ReadModels + EventStore） |
| ReadModel | 5（DiscoveryFeed, CircleFeed, ChatInbox, UserProfileView, RecommendFeature） |
| 向量实体 | 2（ContentEmbedding, UserContextEmbedding） |
| 领域事件 | 45+ |
| YAML 文件总计 | 70+ |
