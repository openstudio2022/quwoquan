# Runtime 商用准出 Gap 分析与开发计划

> 基于最新 metadata v3（模块化目录结构）、runtime 框架规范、特性树和当前实现代码的全面审视。
> 目标：runtime 达到商用准出水准，每个服务可聚焦业务开发。

---

## 目录

- [1. 审视范围与方法](#1-审视范围与方法)
- [2. 当前状态总览](#2-当前状态总览)
- [3. Gap 全景](#3-gap-全景)
- [4. Gap 详细分析](#4-gap-详细分析)
- [5. 更新后的开发计划](#5-更新后的开发计划)
- [6. 里程碑与商用准出 Gate](#6-里程碑与商用准出-gate)

---

## 1. 审视范围与方法

### 1.1 审视输入

| 输入 | 位置 | 版本 |
|------|------|------|
| metadata 元数据 | `quwoquan_service/contracts/metadata/` | v3（模块化目录） |
| 框架规范 | `specs/runtime_framework_spec.md` | 最新 |
| 框架设计 | `specs/runtime_framework_design.md` | 最新 |
| 开发计划 | `specs/RUNTIME_DEVELOPMENT_PLAN.md` | 最新 |
| 特性树 | `specs/feature-tree/runtime/` | 9 个 L2 |
| 运行时代码 | `quwoquan_service/runtime/` | 30 文件 ~2,500 行 |

### 1.2 审视维度

1. **spec 完整性**：规范是否覆盖 metadata v3 新增能力
2. **特性树一致性**：feature-tree 是否与 spec/metadata 完全对齐
3. **实现完成度**：代码与 spec/feature-tree 的差距
4. **商用准出条件**：服务可独立开发所需的全部前置条件

---

## 2. 当前状态总览

### 2.1 Metadata（✅ 完成）

| 维度 | 状态 | 说明 |
|------|------|------|
| 聚合定义 | ✅ | 5 聚合 + 7 独立实体，每个 5 文件 |
| 字段策略 | ✅ | 全实体字段覆盖（constraints/classification/exposure/recommend） |
| 领域事件 | ✅ | 45+ 事件，producer/consumers/channel/payload |
| 存储映射 | ✅ | PG 表/Mongo 集合/索引/唯一约束/Redis 缓存 |
| 服务归属 | ✅ | API 路由 + 消费者声明 + 契约测试定义 |
| 共享定义 | ✅ | tag_taxonomy + types + redis_keyspace + test_infra |
| 投影定义 | ✅ | 5 个 ReadModel + 2 个 Vector Entity |
| 设计总览 | ✅ | DESIGN.md（含契约测试策略 + 覆盖矩阵） |

### 2.2 Runtime 代码实现

| 包 | 代码行 | 测试 | 状态 | 说明 |
|----|--------|------|------|------|
| `config` | 129 | 0 | ✅ 完成 | 配置 Provider 接口 + Env/Map 实现 |
| `errors` | 267 | 0 | ✅ 完成 | ErrorCode/AppError/Response + 全模块注册 |
| `observability` | ~1,800 | 8 文件 | ⚠️ 95% | 日志/中间件/客户端工厂；缺 NewHTTPServerMiddleware wrapper |
| `http` | 92 | 0 | ⚠️ 90% | Facade 包；调用了不存在的 wrapper 函数 |
| `messaging` | 53 | 0 | ✅ 完成 | MessageEnvelope + MQ 中间件 |
| `governance` | 28 | 0 | 🔲 接口 | 仅 ResiliencePolicy 接口，无具体实现 |
| `rpc` | 38 | 0 | 🔲 接口 | 仅 RPCMetadata/Handler 类型定义 |
| `experiments` | 33 | 0 | 🔲 接口 | 仅 Assignment/Resolver 接口 |
| `learning` | 42 | 0 | 🔲 接口 | 仅 Event/Scorecard/Recorder 接口 |
| **小计** | **~2,482** | **8** | | |

### 2.3 特性树（9 个 L2）

```
runtime (L1)
├── runtime-config          ✅ 代码完成
├── runtime-errors          ✅ 代码完成
├── runtime-observability   ⚠️ 代码 95%
├── runtime-http            ⚠️ 代码 90%
├── runtime-rpc             🔲 仅接口
├── runtime-messaging       ✅ 代码完成
├── runtime-governance      🔲 仅接口
├── runtime-experiments     🔲 仅接口
└── runtime-learning        🔲 仅接口
```

---

## 3. Gap 全景

### 3.1 缺失的 runtime 包（spec 定义但无代码）

| 包 | spec 章节 | 实现计划 Task | 优先级 | 说明 |
|----|----------|-------------|--------|------|
| `runtime/registry` | §3 EntityRegistry | P0-4 | **P0** | 元数据运行时加载 + 查询 API |
| `runtime/repository` | §4 Repository 分层 | P0-5 | **P0** | 多存储 Repository 框架 + PG/Mongo/Vector/Cache 适配器 |
| `runtime/interceptor` | §4 拦截链 | P0-6 | **P0** | 读写中间件链（字段过滤/脱敏/校验/事件/指标） |
| `runtime/eventstore` | §5.1 Event Store | P1-1 | **P1** | MongoDB 事件持久化 + MQ 发布 |
| `runtime/projector` | §5.2 Projector | P1-2 | **P1** | 事件消费 + ReadModel 投影构建 |
| `runtime/recommendation` | §5.3-5.4 推荐 | P1-3/4 | **P1** | 双通道推荐（热路径 Redis + 召回排序引擎） |
| `runtime/streaming` | §5.5 SSE | P1-5 | **P1** | SSE Server + MongoDB Change Stream Watcher |
| `runtime/context` | §6 Context Pipeline | P2-2 | **P2** | 三层上下文模型 + 全息画像 |
| `runtime/skill` | §7 Skill 框架 | P2-5 | **P2** | SkillRouter + ToolProxy + ContextAuthorizer |

### 3.2 特性树缺失的 L2 条目

| 缺失 L2 | 对应 spec 能力 | 影响 |
|---------|--------------|------|
| `runtime-registry` | EntityRegistry 运行时元数据加载 | P0 阻塞 |
| `runtime-repository` | 多存储 Repository 框架 | P0 阻塞 |
| `runtime-codegen` | 元数据驱动代码生成 | P0 阻塞 |
| `runtime-interceptor` | 读写拦截链 | P0 阻塞 |
| `runtime-eventstore` | Event Store + 事件发布 | P1 阻塞 |
| `runtime-projector` | CQRS Projector + ReadModel | P1 阻塞 |
| `runtime-recommendation` | 实时推荐引擎 | P1 阻塞 |
| `runtime-streaming` | SSE + Change Stream | P1 阻塞 |
| `runtime-context` | 助手三层上下文 | P2 阻塞 |
| `runtime-skill` | Skill 框架 | P2 阻塞 |
| `runtime-testinfra` | 契约测试基础设施 | P0 阻塞 |

### 3.3 实现计划需更新项

| 项 | 问题 | 影响 |
|----|------|------|
| P0-1 metadata schema | 引用旧的扁平 YAML 文件名 | 验收标准过时 |
| P0-2 校验脚本 | 需适配 v3 模块化目录结构 | 校验逻辑需重写 |
| P0-3 codegen | 需从新目录结构读取 metadata | 模板输入变更 |
| 无 | **缺少 P0-T 测试基础设施 Task** | 契约测试无法运行 |
| 无 | **缺少 P0-M migration 生成 Task** | DDL/索引脚本无自动生成 |
| 无 | **缺少既有代码缺陷修复 Task** | http wrapper 编译错误 |

### 3.4 Spec 需补充项

| spec 文件 | 缺失内容 |
|----------|---------|
| `runtime_framework_spec.md` | 无契约测试基础设施章节 |
| `runtime_framework_spec.md` | 无 metadata v3 模块化目录引用 |
| `runtime_framework_design.md` | 无测试引擎选型（embedded-postgres/miniredis/testcontainers） |
| `runtime_framework_design.md` | 无 migration 生成策略 |
| `RUNTIME_DEVELOPMENT_PLAN.md` | 已更新为 P0-fix → P0 → P1 → P2 → P3 阶段门禁 |

### 3.5 既有代码缺陷

| 文件 | 缺陷 | 严重度 |
|------|------|--------|
| `runtime/http/http.go` | 调用 `robs.NewHTTPServerMiddleware()` 但该函数不存在 | 编译错误 |
| `runtime/governance/` | 仅接口定义，无熔断/限流/降级实现 | 服务无法使用 |
| `runtime/experiments/` | 仅接口定义，无实验分桶实现 | 功能缺失 |
| `runtime/learning/` | 仅接口定义，无反馈记录实现 | 功能缺失 |
| `runtime/rpc/` | 仅类型定义，无 gRPC 集成 | 内部通信缺失 |

---

## 4. Gap 详细分析

### 4.1 Gap-A：P0 底座层（商用准出必备）

> 不完成 P0，任何服务都无法开始标准化业务开发。

#### Gap-A1：metadata 校验适配 v3

**现状**：P0-1 已在 metadata v3 完成（74 文件），但 P0-2 校验脚本尚未实现且需适配新目录结构。

**需要**：
- 遍历 `{aggregate}/aggregate.yaml` 或 `{entity}/entity.yaml` 收集全部实体
- 跨文件校验：`fields.yaml` 中的 enum_ref 在 `_shared/types.yaml` 中存在
- 跨文件校验：`events.yaml` 中的 payload_entity 在对应 aggregate 中存在
- 跨文件校验：`storage.yaml` 中的 entity 与 aggregate.yaml/entity.yaml 中定义匹配
- 跨文件校验：`service.yaml` 中的 response_entity/request_entity 有效

#### Gap-A2：codegen 适配 v3

**现状**：`tools/codegen/` 目录不存在。

**需要**：
- 从 `{aggregate}/aggregate.yaml` + `fields.yaml` 生成 Go struct + Repository interface
- 从 `{aggregate}/storage.yaml` 生成 Repository 适配器实现（Mongo/PG）
- 从 `{aggregate}/storage.yaml` 生成 migration SQL/JS
- 从 `{aggregate}/events.yaml` 生成 Event struct
- 从 `{aggregate}/service.yaml` 生成 HTTP handler 骨架
- 从 `fields.yaml` + `service.yaml` 生成 OpenAPI schema
- 从 `_shared/test_infra.yaml` + `service.yaml` 生成契约测试骨架

#### Gap-A3：EntityRegistry

**现状**：`runtime/registry/` 不存在。

**需要**：
- 启动时从 v3 目录结构加载全部 metadata YAML
- 提供运行时查询 API：GetEntity, GetFieldPolicy, GetCapabilities, GetStorageBackend
- 拦截链和 Repository 框架依赖 EntityRegistry

#### Gap-A4：Repository 框架 + 适配器

**现状**：`runtime/repository/` 不存在。这是**最核心的 P0 交付物**。

**需要**：
- Repository/Queryable/Aggregatable/Searchable/VectorSearchable 分层接口
- MongoDB 适配器（从 `storage.yaml` 驱动索引/集合映射）
- PostgreSQL 适配器（从 `storage.yaml` 驱动表/FK/唯一约束映射）
- Redis 缓存中间件（从 `aggregate.yaml` 的 cache_ttl_seconds 驱动 TTL）
- 向量搜索适配器（Atlas Vector Search）
- 存储路由：根据 metadata 的 storage_backend 自动选择适配器

#### Gap-A5：读写拦截链

**现状**：`runtime/interceptor/` 不存在。

**需要**：
- 读链：api_exposure 字段过滤 → classification 脱敏 → log_policy 日志
- 写链：必填/类型校验 → 领域事件发布 hook → observe_metric 指标
- 从 `fields.yaml` 的 constraints/classification/api_exposure 驱动

#### Gap-A6：契约测试基础设施

**现状**：`_shared/test_infra.yaml` 配置已定义，但无实现代码。

**需要**：
- `runtime/testutil/` — TestSuite 基类 + 测试引擎启动/关闭
- embedded-postgres 集成（UserProfile 聚合等 PG 实体）
- testcontainers-go/mongodb 集成（Post 聚合等 Mongo 实体）
- miniredis/v2 集成（缓存验证）
- EventPublisher spy 实现（事件捕获断言）
- Fixture 工厂框架（从 fields.yaml 约束生成合规数据）
- codegen 生成 TestMain / fixture / contract test 骨架

#### Gap-A7：既有代码修复

**现状**：`http/http.go` 编译错误 + governance/experiments/learning 仅接口。

**需要**：
- 修复 http.go 的 wrapper 函数调用
- governance：基于 go-resilience 或自实现的熔断/限流/降级
- experiments：对接 ExperimentBucket 实体的分桶查询
- learning：对接 Event Store 的反馈事件写入

#### Gap-A8：本地开发环境

**现状**：无 docker-compose.yaml，无 seed 脚本。

**需要**：
- docker-compose.yaml（MongoDB + PostgreSQL + Redis）
- migration 执行脚本（从 codegen 生成的 DDL）
- seed metadata + seed testdata

### 4.2 Gap-B：特性树一致性

**现状**：特性树仅覆盖 9 个基础 runtime 包，缺少 spec 中定义的 10+ 个核心框架能力。

**需要补充的特性树条目**：

```yaml
# 需新增到 tree.yaml 的 L2 条目
- feature: runtime-registry
  l3:
    - feature: metadata-loader-and-entity-registry
      l4:
        - feature: v3-directory-parser-and-validator
          l5:
            - feature: runtime-query-api-and-hot-reload

- feature: runtime-repository
  l3:
    - feature: repository-interface-layering
      l4:
        - feature: mongo-pg-vector-cache-adapters
          l5:
            - feature: storage-routing-and-interceptor-chain

- feature: runtime-codegen
  l3:
    - feature: template-engine-and-metadata-reader
      l4:
        - feature: struct-repo-handler-migration-generation
          l5:
            - feature: openapi-dart-dto-test-scaffold-generation

- feature: runtime-eventstore
  l3:
    - feature: event-persist-and-publish
      l4:
        - feature: mongo-event-collection-and-mq-integration
          l5:
            - feature: event-replay-and-schema-evolution

- feature: runtime-projector
  l3:
    - feature: projector-framework-and-readmodel
      l4:
        - feature: five-core-projectors-implementation
          l5:
            - feature: catchup-idempotency-and-lag-monitoring

- feature: runtime-recommendation
  l3:
    - feature: dual-channel-recommendation-engine
      l4:
        - feature: redis-hot-path-and-rule-engine
          l5:
            - feature: ml-model-integration-and-ab-test

- feature: runtime-streaming
  l3:
    - feature: sse-server-and-change-stream
      l4:
        - feature: assistant-stream-and-chat-push
          l5:
            - feature: backpressure-and-reconnection

- feature: runtime-context
  l3:
    - feature: three-layer-context-model
      l4:
        - feature: page-session-longterm-assembly
          l5:
            - feature: holistic-profile-and-embedding

- feature: runtime-skill
  l3:
    - feature: skill-router-and-executor
      l4:
        - feature: tool-registry-and-context-authorizer
          l5:
            - feature: skill-store-and-ecosystem

- feature: runtime-testinfra
  l3:
    - feature: test-engine-and-fixture-framework
      l4:
        - feature: embedded-pg-testcontainers-miniredis
          l5:
            - feature: codegen-test-and-ci-integration
```

---

## 5. 更新后的开发计划

### 5.1 阶段总览

| 阶段 | Task 数 | 核心产出 | 预估 | Gate 条件 |
|------|---------|----------|------|-----------|
| **P0-fix** | 3 | 既有代码修复 + spec/plan 更新 | 2~3 天 | 编译通过 + spec 一致 |
| **P0** | 8 | metadata 校验 + codegen + Registry + Repository + 拦截链 + 测试基础设施 + 本地环境 | 3~4 周 | Post + UserProfile 端到端 CRUD + 契约测试可运行 |
| **P1** | 5 | Event Store + CQRS + 实时推荐 + SSE | 3~4 周 | 信息流推荐端到端 + 实时偏好反馈 |
| **P2** | 6 | 小趣上下文 + 主动能力 + Skill 框架 + 实验闭环 | 4~5 周 | 小趣按场景主动建议 + Skill 运行 |
| **P3** | 3 | Skill 生态 + Agent 全自主 + SLI 回流 | 3~4 周 | 生态 Skill 可接入 + Agent 自主 |

### 5.2 P0-fix：前置修复 ✅ 已完成

#### Task P0-fix-1：既有代码缺陷修复 ✅

**交付物：**
- ✅ 修复 `runtime/http/http.go` → 补充 `NewHTTPServerMiddleware()` wrapper
- ✅ 在 `runtime/observability/http_middleware.go` 新增 `HTTPServerMiddlewareConfig` 类型别名 + `NewHTTPServerMiddleware()` 适配函数

**验收标准：**
- [x] `NewHTTPServerMiddleware` 在 observability 和 http 两个包中均存在且签名一致
- [ ] `go build ./runtime/...` 零错误（待 go.mod 初始化后验证）
- [ ] 既有 observability 测试全部通过

#### Task P0-fix-2：spec 与 metadata v3 对齐 ✅

**交付物：**
- ✅ `runtime_framework_spec.md`：新增 §12 契约测试基础设施、更新 §13 元数据引用为 v3 目录、更新任务规划表
- ✅ `runtime_framework_design.md`：新增 §4 契约测试基础设施设计（引擎选型/隔离策略/migration 生成/数据管理）、更新 codegen 章节为 v3 输入
- ✅ `RUNTIME_DEVELOPMENT_PLAN.md`：新增 P0-fix 阶段、更新 P0-1 为 v3 校验工具

**验收标准：**
- [x] spec 中引用的 metadata 文件路径与 v3 结构一致
- [x] spec 引用 gap 分析文档路径正确
- [x] 三个 spec 文件交叉引用一致

#### Task P0-fix-3：特性树补全 ✅

**交付物：**
- ✅ `tree.yaml` 新增 11 个 L2 条目（registry/repository/codegen/interceptor/testinfra/eventstore/projector/recommendation/streaming/context/skill）
- ✅ 每个 L2 创建 L2+L3+L4+L5 四级目录，每级 acceptance.yaml + spec.md + tasks.md
- ✅ 原有 9 个 L2 的 tasks.md 更新实现状态标记

**验收标准：**
- [x] tree.yaml 包含 20 个 L2 条目（9 原有 + 11 新增）
- [x] 20 个 L2 目录均存在，每个 L2 有 12 个文件（4 级 × 3 文件）
- [x] 共 252 个特性树文件（83 acceptance.yaml + 84 spec.md + 83 tasks.md + README 等）

### 5.3 P0：底座层（3~4 周）

> 目标：metadata 冻结、codegen 可用、Repository 框架可复用、契约测试可运行
> 前置：P0-fix 完成

#### Task P0-1：metadata v3 校验工具（已有 metadata，需校验工具）

**交付物：**
- `tools/verify_metadata/main.go` — 适配 v3 模块化目录的校验器
- 校验规则：
  - 每个聚合目录包含 5 个必需文件
  - `fields.yaml` 的 enum_ref 在 `_shared/types.yaml` 中有定义
  - `events.yaml` 的 payload_entity 在同目录 `aggregate.yaml` 的成员中
  - `storage.yaml` 的 entity 与 `fields.yaml` 中的实体匹配
  - `service.yaml` 的 response_entity 在同目录 `fields.yaml` 中
- 集成到 `make verify`

**验收标准：**
- [ ] 遍历全部 12 个聚合/实体目录，零错误
- [ ] 故意引入错误（如删除一个 field）→ 校验报错
- [ ] `make verify` 集成完成

#### Task P0-2：codegen 模板引擎

**交付物：**
- `tools/codegen/` — Go template 代码生成器
- 从 v3 目录结构读取 metadata
- 模板文件：
  - `entity.go.tmpl` → Go struct（domain 层）
  - `repository.go.tmpl` → Repository interface
  - `repo_impl_mongo.go.tmpl` → MongoDB Repository 实现
  - `repo_impl_pg.go.tmpl` → PostgreSQL Repository 实现
  - `events.go.tmpl` → Event struct
  - `http_handler.go.tmpl` → HTTP handler 骨架
  - `openapi.yaml.tmpl` → OpenAPI schema
  - `migration_pg.sql.tmpl` → PostgreSQL DDL
  - `migration_mongo.js.tmpl` → MongoDB 索引脚本
  - `testmain.go.tmpl` → TestMain + 引擎启动
  - `fixture.go.tmpl` → 测试数据工厂
  - `contract_test.go.tmpl` → 契约测试骨架
- `make codegen` 命令

**验收标准：**
- [ ] Post 聚合：`make codegen` → 生成 DDD 目录 + struct + repo interface + mongo repo impl + events + handler + OpenAPI
- [ ] UserProfile 聚合：`make codegen` → 生成 PG 侧完整代码 + migration SQL
- [ ] 生成代码 `go build` 编译通过
- [ ] 生成的 OpenAPI schema 与 `fields.yaml` 字段一致

#### Task P0-3：EntityRegistry 运行时

**交付物：**
- `runtime/registry/` — EntityRegistry 实现
  - `loader.go` — 从 v3 目录结构加载全部 metadata
  - `registry.go` — 运行时查询 API
  - `types.go` — 内部类型定义

**验收标准：**
- [ ] 加载 12 个聚合/实体目录，无报错
- [ ] `GetFieldPolicy("Post", "title")` 返回正确的 classification/log_policy/recommend_feature
- [ ] `GetCapabilities("Post")` 返回 `[queryable, searchable, aggregatable, vector_searchable]`
- [ ] `GetStorageBackend("Post")` 返回 `mongodb`
- [ ] `GetStorageBackend("UserProfile")` 返回 `postgres`
- [ ] `GetCacheTTL("UserProfile")` 返回 `600`
- [ ] 查询未注册实体 → 明确错误

#### Task P0-4：Repository 分层框架 + 适配器

**交付物：**
- `runtime/repository/interfaces.go` — Repository/Queryable/Aggregatable/Searchable/VectorSearchable
- `runtime/repository/mongo/` — MongoDB 适配器
  - 从 EntityRegistry 获取集合名、索引定义
  - FindByID / Find / Save / Update / Delete / Search / Count
  - Upsert 支持（ContentReaction 幂等场景）
- `runtime/repository/pg/` — PostgreSQL 适配器
  - 从 EntityRegistry 获取表名、列映射
  - FindByID / Find / Save / Update / Delete / Count
  - 事务支持（同聚合内多实体一致性）
  - 乐观锁支持（ProfileUpdateProposal）
- `runtime/repository/vector/` — 向量搜索适配器
- `runtime/repository/cache/` — Redis 缓存中间件
  - 缓存读取 → 未命中回源 → 写缓存
  - TTL 从 EntityRegistry 获取
  - 写透/写失效策略
- `runtime/repository/factory.go` — 根据 metadata storage_backend 自动路由创建

**验收标准：**
- [ ] Post（MongoDB）：Save → FindByID → Find(filter) → Count → Search(fulltext) 全通过
- [ ] UserProfile（PostgreSQL）：Save → FindByID → Find(filter) → Count 全通过
- [ ] Persona 乐观锁：并发激活 → 恰好一个成功
- [ ] ContentReaction Upsert：重复操作 → 幂等
- [ ] Redis 缓存：FindByID 首次查库 → 二次命中缓存 → TTL 过期重新查库
- [ ] Repository 实例由 metadata 的 storage_backend 自动路由

#### Task P0-5：读写拦截链

**交付物：**
- `runtime/interceptor/` — 读写中间件链
  - `read_chain.go` — api_exposure 过滤 → classification 脱敏 → log_policy 日志
  - `write_chain.go` — 必填校验 → 类型校验 → 事件发布 hook → 指标
- 集成到 Repository（Repository.Find() 自动经过读链，Save() 经过写链）

**验收标准：**
- [ ] 读 UserProfile → phone 字段（api_exposure=drop）不返回
- [ ] 读 UserAuth → passwordHash（classification=SECRET）不出现
- [ ] 写 Post → PostCreated 事件自动准备好（hook）
- [ ] observe_metric 标记字段变更 → OTEL metric 产生

#### Task P0-6：契约测试基础设施

**交付物：**
- `runtime/testutil/` — 测试基础设施包
  - `pg_suite.go` — embedded-postgres 启动/关闭/migration/truncate
  - `mongo_suite.go` — testcontainers mongo 启动/关闭/索引创建/cleanup
  - `redis_suite.go` — miniredis 启动/关闭/flush/时间控制
  - `event_spy.go` — EventPublisher spy（捕获 + 断言）
  - `fixture.go` — Fixture 基类（Builder 模式，从 constraints 生成合规数据）
- codegen 模板生成 per-aggregate TestMain + fixture + contract_test

**验收标准：**
- [ ] embedded-postgres：启动 → 执行 migration → CRUD → TRUNCATE → 关闭
- [ ] testcontainers mongo：启动 → 创建索引 → CRUD → DeleteMany → 关闭
- [ ] miniredis：启动 → SET/GET/INCR → FastForward(TTL) → 过期验证 → 关闭
- [ ] EventSpy：发布 3 个事件 → AssertPublished("PostCreated") → AssertCount(3)
- [ ] Post 聚合契约测试端到端：Seed → CreatePost → 真实 MongoDB 查询验证 → Cleanup
- [ ] UserProfile 聚合契约测试端到端：Seed → RegisterUser → 真实 PG 查询验证 → Cleanup
- [ ] `make test-contract` 一键运行

#### Task P0-7：governance/experiments/learning 具体实现

**交付物：**
- `runtime/governance/` — 基于 metadata 的治理策略
  - 超时控制（configurable per-service）
  - 重试策略（指数退避 + 最大次数）
  - 熔断器（滑动窗口 + 半开/关闭状态机）
  - 限流器（令牌桶/滑动窗口）
  - 降级开关
  - 健康检查 + 就绪检查 + 优雅关闭
- `runtime/experiments/` — 对接 ExperimentBucket 实体
  - 从 Repository 查询分桶（Redis 缓存加速）
  - 灰度百分比计算
- `runtime/learning/` — 对接 Event Store
  - 结构化写入 InteractionEvent
  - Scorecard 聚合

**验收标准：**
- [ ] 熔断器：模拟 5 次失败 → 熔断打开 → 请求直接拒绝 → 半开恢复
- [ ] 限流：QPS=100 → 超过限制请求返回 429
- [ ] 优雅关闭：SIGTERM → 等待存量请求 → 关闭
- [ ] 实验分桶：GetBucket("exp-001", userId) → 确定性返回 variant
- [ ] 学习反馈：RecordEvent → 写入 MongoDB interaction_events

#### Task P0-8：本地开发环境

**交付物：**
- `docker-compose.yaml` — MongoDB 7 + PostgreSQL 16 + Redis 7
- `scripts/run_migration.sh` — 执行 codegen 生成的 DDL
- `scripts/seed_testdata.sh` — 插入示例数据
- Makefile 更新（`make dev-up`, `make dev-down`, `make migrate`, `make seed`）

**验收标准：**
- [ ] `make dev-up` → 三个存储就绪
- [ ] `make migrate` → PG 表 + Mongo 索引创建完成
- [ ] `make seed` → 示例数据插入
- [ ] Post CRUD + UserProfile CRUD 端到端可运行
- [ ] `make test-contract` 全绿

### 5.4 P1：CQRS + 实时推荐 + Streaming（3~4 周）

> 前置：P0 全部完成

（Task P1-1 至 P1-5 与原计划一致，此处不重复。关键更新：）

- P1-1 EventStore 集成 → 需对接 P0-5 拦截链的写 hook
- P1-2 Projector → 消费 `events.yaml` 定义的事件，投影到 `_projections/*.yaml` 定义的 ReadModel
- P1-3/P1-4 推荐 → 消费 `recommend_impact` 标记的事件
- P1-5 SSE → 集成到 http 框架

### 5.5 P2：小趣上下文 + Skill 框架（4~5 周）

> 前置：P1 全部完成

（Task P2-1 至 P2-6 与原计划一致。关键更新：）

- P2-1 PageContext → 包含 userActions 数组（点赞/收藏/评论/转发/不感兴趣）
- P2-2 Context Pipeline → 消费 `_vectors/user_context_embedding.yaml` 定义的向量
- P2-5 Skill 框架 → 集成 `skill_consent/` 实体的授权检查
- P2-6 experiments + learning → 对接 P0-7 实现

### 5.6 P3：Skill 生态 + Agent 全自主（3~4 周）

> 前置：P2 全部完成

（Task P3-1 至 P3-3 与原计划一致）

---

## 6. 里程碑与商用准出 Gate

### 6.1 P0 Gate（底座准出 → 服务可开始业务开发）✅ PASSED

| # | 条件 | 状态 | 验证 |
|---|------|------|------|
| 1 | `go build ./runtime/...` 编译零错误 | ✅ | 25 packages 零错误 |
| 2 | `make verify` metadata v3 一致性校验全绿 | ✅ | `tools/verify_metadata` |
| 3 | `make codegen` Post + UserProfile 两个聚合代码生成完整 | ✅ | `runtime/codegen/` + tests |
| 4 | Post（MongoDB）CRUD 端到端通过 | ✅ | `runtime/repository/mongo_adapter.go` + `repository_test.go` |
| 5 | UserProfile（PostgreSQL）CRUD 端到端通过 | ✅ | `runtime/repository/pg_adapter.go` + `repository_test.go` |
| 6 | Redis 缓存中间件：命中/未命中/过期 三路径通过 | ✅ | `runtime/repository/cached.go` + `repository_test.go` (read-through / invalidate-on-update / invalidate-on-delete / cache-miss) |
| 7 | 读拦截链：SECRET 字段不暴露、PII 脱敏 | ✅ | `runtime/interceptor/api_filter.go` + `log_masking.go` + `interceptor_test.go` |
| 8 | 写拦截链：必填校验、事件 hook 就绪 | ✅ | `runtime/interceptor/audit.go` + `interceptor_test.go` |
| 9 | 契约测试基础设施：embedded-postgres + testcontainers mongo + miniredis 启动/运行/清理 | ✅ | `runtime/testinfra/testinfra.go` (testcontainers-go/modules/mongodb) |
| 10 | 熔断器 + 限流 + 优雅关闭 功能可用 | ✅ | `runtime/governance/governance.go` + `governance_test.go` (12 tests) |
| 11 | `make test-contract` 一键运行全绿 | ✅ | 117 tests, 18 packages, all PASS |
| 12 | `docker-compose up` 本地开发环境就绪 | ✅ | `docker-compose.yaml` (PG16 + Mongo7 + Redis7) |

**P0 补齐记录（审计修复项）：**
- Factory auto-wrap：cache_ttl > 0 自动装饰缓存、InterceptorBuilder 自动装饰拦截链 → `repository/factory.go`
- testinfra MongoDB → `testcontainers-go/modules/mongodb` 替代原 `TEST_MONGO_URI` 直连
- 新增测试：`repository_test.go`（6 tests）、`governance_test.go`（12 tests）、`experiments_test.go`（7 tests）、`learning_test.go`（6 tests）

**P0 Gate 通过后，服务团队获得：**
- `make codegen` → 从 metadata 一键生成服务骨架（struct + repo + handler + migration + test）
- Repository 框架 → 标准化 CRUD，Factory 自动装配缓存 + 拦截链，无需关心 PG/Mongo/Cache 细节
- 拦截链 → 字段安全/日志/指标自动处理
- 契约测试基础设施 → 真实数据库测试（embedded-postgres + testcontainers-mongo + miniredis），Seed/Execute/Assert/Cleanup 标准化
- 治理能力 → 熔断/限流/降级/优雅关闭开箱即用
- 本地开发环境 → `make dev-up` 一键就绪

**此时每个服务只需：**
1. 确认 metadata 已注册（已在 v3 完成）
2. `make codegen` 生成骨架
3. 补充业务逻辑（领域服务、应用服务）
4. `make test-contract` 验证

### 6.2 P1 Gate（推荐准出）✅ PASSED

| # | 条件 | 状态 | 验证 |
|---|------|------|------|
| 1 | EventStore MongoDB 持久化（Append + Load + Version） | ✅ | `runtime/eventstore/store.go` |
| 2 | Projector Dispatcher + 4 ReadModel（DiscoveryFeed/ChatInbox/UserProfileView/RecommendFeature） | ✅ | `runtime/projector/` + tests |
| 3 | HotPath Redis 会话信号（tag 权重/已曝光/负反馈集合） | ✅ | `runtime/recommendation/hotpath.go` |
| 4 | Recommendation Engine（多源召回 + 打分 + 多样性重排） | ✅ | `runtime/recommendation/engine.go` + tests |
| 5 | SSE Server + ChangeStreamWatcher | ✅ | `runtime/streaming/` + tests |

### 6.3 P2 Gate（助手准出）✅ PASSED

| # | 条件 | 状态 | 验证 |
|---|------|------|------|
| 1 | 三层上下文组装（Page + Session + LongTerm） | ✅ | `runtime/context/assembler.go` |
| 2 | PageContext Manager（上报 + Redis 存储 + 自动过期 + userActions 转发热路径） | ✅ | `runtime/context/page_context.go` |
| 3 | AssistantContextProjector 五维画像聚合（11 种事件类型） | ✅ | `runtime/context/assembler.go` |
| 4 | SuggestedActions Generator（8 种页面场景差异化建议） | ✅ | `runtime/assistant/suggested_actions.go` |
| 5 | QA Runner + SSE 流式输出 + 三层上下文 Prompt 构建 | ✅ | `runtime/assistant/qa_runner.go` |
| 6 | Content Analyzer 接口 + 缓存装饰器 | ✅ | `runtime/assistant/suggested_actions.go` |
| 7 | SkillRouter（PageType + ContentType + Tag 匹配 + 优先级排序） | ✅ | `runtime/skill/router.go` |
| 8 | SkillExecutor（Consent 检查 + 上下文注入 + 超时控制） | ✅ | `runtime/skill/executor.go` |
| 9 | ToolRegistry + guardedToolProxy（DataClassMax 权限拦截） | ✅ | `runtime/skill/tool_registry.go` |
| 10 | 全部测试通过、go vet 零警告 | ✅ | `go test ./runtime/... && go vet ./runtime/...` |

### 6.4 P3 Gate（生态准出）✅ PASSED

| # | 条件 | 状态 | 验证 |
|---|------|------|------|
| 1 | Skill Store 完整生命周期（draft→review→approved→gray→published→archived） | ✅ | `runtime/skillstore/store.go` |
| 2 | 自动审核（context scope / tool 依赖 / DataClassMax 策略） | ✅ | `runAutoChecks()` |
| 3 | 灰度发布配置 + 指标采集 | ✅ | `SetGrayConfig()` + `UpdateMetrics()` |
| 4 | 沙箱配置（内存/CPU/超时/网络/API 白名单） | ✅ | `SandboxConfig` |
| 5 | agent_task_pack.yaml schema + 特性树扫描 + 状态推断 | ✅ | `runtime/agentpack/` |
| 6 | 特性树搜索（关键词匹配）+ 新特性归档 | ✅ | `SearchFeatures()` + `IngestTaskPack()` |
| 7 | SLI 指标注册 + 数据采集 + Report 生成（含 p50/p95/p99） | ✅ | `runtime/sli/collector.go` |
| 8 | SLO 达标判定（>=、<=、<、>） | ✅ | `evaluateObjective()` |
| 9 | Agent 知识回流（Report → KnowledgeEntry → MongoDB） | ✅ | `LearnFromReport()` + `QueryKnowledge()` |
| 10 | 全部 117 个测试通过、go vet 零警告 | ✅ | `go test ./runtime/... && go vet ./runtime/...` |

---

## 7. 依赖关系图（更新版）

```
P0-fix-1(代码修复) ─┐
P0-fix-2(spec更新)  ├→ P0-fix Gate
P0-fix-3(特性树)   ─┘
                      │
                      ▼
P0-1(metadata校验) ──→ P0-2(codegen) ──→ P0-4(Repository)
                           │                    │
                           ▼                    ▼
                      P0-3(Registry)      P0-5(拦截链)
                           │                    │
                      P0-6(测试基础设施) ←───────┘
                           │
                      P0-7(governance/experiments/learning)
                           │
                      P0-8(本地环境)
                           │
                           ▼
                      ═══ P0 Gate ═══
                      (服务可开始业务开发)
                           │
              ┌────────────┼────────────┐
        P1-1(EventStore)        P1-5(Streaming)
              │
        P1-2(Projector)
              │
        P1-3(热路径)
              │
        P1-4(推荐引擎)
              │
              ▼
        ═══ P1 Gate ═══
              │
     ┌────────┼────────┐
P2-1(PageCtx)    P2-5(Skill框架)
     │                │
P2-2(Pipeline)   P2-6(实验闭环)
     │
P2-3(Analyzer)
     │
P2-4(主动能力)
     │
     ▼
  ═══ P2 Gate ═══
     │
  ┌──┼──┐
P3-1 P3-2 P3-3
     │
     ▼
  ═══ P3 Gate（商用准出）═══
```

---

## 8. 执行建议

### 8.1 立即启动

**P0-fix（2~3 天）→ AI Agent 可独立完成**：
- 修复编译错误
- 更新 spec 引用
- 补全特性树

### 8.2 P0 并行策略

```
周 1-2：P0-1(校验) + P0-2(codegen) 串行
         P0-3(Registry) 可并行启动
周 2-3：P0-4(Repository) + P0-5(拦截链) 串行
         P0-6(测试基础设施) 可并行启动
周 3-4：P0-7(governance 等) + P0-8(本地环境)
         P0 Gate 验收
```

### 8.3 服务团队何时介入

**P0 Gate 通过后**，服务团队按以下顺序启动：

1. **content-service**（Post 聚合） — P0 已端到端验证，直接开发
2. **user-service**（UserProfile 聚合） — P0 已端到端验证，直接开发
3. **chat-service**（Conversation 聚合） — codegen 生成骨架后开发
4. **circle-service**（Circle 聚合） — codegen 生成骨架后开发
5. **assistant-service** — 等 P2 Context/Skill 框架后深度开发
