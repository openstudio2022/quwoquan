# content-service-cloud-production 设计方案

## 设计动因

spec.md 已明确：content-service 需从"开发验证态"推进到"灰度/生产就绪态"。核心约束为：
1. 存储必须持久化（MongoDB），不能继续用内存 PostStore
2. 读热路径必须有缓存层（Redis），减轻 DB 压力
3. 创作后内容必须 ≤5s 出现在发现流（事件驱动投影）
4. 所有声明的 API 必须实现（消灭 handleNotImplemented）
5. 部署配置必须可通过 Kustomize 管理，支持 dev/integration/prod 三环境
6. 四层测试覆盖核心创作→发现旅程

## 上游输入评审

- **spec.md**：功能范围 14 条，边界清晰，约束明确 → 充分
- **acceptance.yaml**：A1-A12 可量化，测试层映射完整 → 充分
- **阻断项**：无。metadata 已由 `content-service-contract-foundation` 基线化，codegen 工具链已就绪

## 对标输入分析

本特性为内部工程成熟度提升，参照对象为同仓 chat-service：

| 维度 | chat-service（参照） | content-service（目标） |
|------|---------------------|----------------------|
| 存储 | MongoDB（已启用） | MongoDB（待启用） |
| 缓存 | — | Redis CacheableRepository |
| 事件 | Redis Pub/Sub EventPublisher | Redis Pub/Sub EventPublisher |
| 部署 | Kustomize base + 3 overlays + HPA + PDB | 复刻同结构 |
| CI | 独立 test-chat-service Job + MongoDB service | 复刻同模式 |
| 探针 | liveness + readiness + startup | 复刻 |

---

## 方案对比

### 决策 1：存储切换策略

#### 方案 A：Config-driven 条件切换（推荐）

main.go 检查 `mongo.uri` 配置项：有值则创建 `MongoPostStore`，无值则降级到 `PostStore`（InMemory）。保留现有 `PostRepository` 类型化接口不变。

**优点**：改动最小（仅 main.go 10 行），向后兼容本地开发，无需改 PostService 签名。
**缺点**：未使用 runtime `Factory`，缓存需手动适配。
**适用条件**：PostRepository 接口稳定，不需要 runtime 的 generic `Repository[map[string]any]` 能力。

#### 方案 B：EntityRegistry + Factory 全量迁移

PostService 改为使用 `repository.Repository[map[string]any]`，通过 `Factory.Create("Post")` 获取带缓存的通用 Repository。

**优点**：完全遵循 runtime 统一能力；Factory 自动装饰缓存和拦截器。
**缺点**：需重写 PostService/FeedService/BehaviorService 的全部存储交互（从类型化 `*postmodel.Post` 改为 `map[string]any`），丧失编译时类型安全；改动量大（估算 20+ 文件）。
**适用条件**：未来多聚合根需要统一治理时。

#### 选型决策

**选定方案 A**。理由：
- `PostRepository` 接口已经正确抽象了存储，两种实现（InMemory/Mongo）可互换
- 方案 B 的收益（Factory 自动装饰）可通过手动创建 typed 缓存适配器获得
- 改动范围可控（仅 main.go + config + 缓存适配器），风险低
- 方案 B 作为未来演进方向，当新增聚合根（如 Report）时再引入

### 决策 2：缓存接入策略

#### 方案 A：Typed 缓存适配器（推荐）

创建 `PostCacheRepository` 实现 `PostRepository` 接口，内部持有底层 `PostRepository`（Mongo）和 `redis.Client`（general scene）。FindByID 走 read-through，Update/Delete 走 write-invalidate。

```go
type PostCacheRepository struct {
    inner  PostRepository
    redis  redis.Client
    ttl    int  // 300s, from storage.yaml
}
```

**优点**：类型安全，与现有 PostService 无缝集成，缓存 key 与 storage.yaml 一致。
**缺点**：手动编写，不通过 runtime Factory 自动装饰。

#### 方案 B：application 层手动缓存

PostService 内部在 FindByID 前后手动操作 Redis。

**优点**：无需新文件。
**缺点**：业务逻辑和缓存逻辑耦合，违反 DDD 分层。

#### 选型决策

**选定方案 A**。缓存是基础设施层关注点，应在 infrastructure 层解决，PostService 无感知。

### 决策 3：事件总线选型

#### 方案 A：Redis Pub/Sub（推荐）

复用 chat-service 已验证的模式。content-service 通过 `redis.Router.Scene("general")` 的 Publish 发布事件，DiscoveryFeedProjector 通过 Subscribe 消费。

**优点**：基础设施已就绪（redis.Router 支持 Pub/Sub），chat-service 已验证可靠性，零新增依赖。
**缺点**：不持久，subscriber 不在线则丢消息。

#### 方案 B：专用 MQ（NATS/Kafka）

引入独立消息中间件。

**优点**：持久化、consumer group、replay。
**缺点**：新增运维依赖，当前事件量级不需要。

#### 选型决策

**选定方案 A**。理由：
- 内容事件非强一致性要求（feed 投影可从 DB 重建）
- Redis Pub/Sub 的吞吐对当前规模绰绰有余
- chat-service 同模式已验证
- 方案 B 为未来演进方向（千万级 + 多消费者时切换）

### 决策 4：DiscoveryFeedProjector 消费模式

#### 方案 A：进程内同步投影（推荐）

PostService 在 CreatePost 成功后，同步调用 DiscoveryFeedProjector 写入 `rm_discovery_feed`。同时通过 EventPublisher 发布事件供外部消费者（推荐引擎、搜索索引器）异步处理。

**优点**：延迟最低（同进程调用 ≤ 100ms），无消息丢失风险，实现简单。
**缺点**：投影失败可能影响创作请求（需 catch + 降级）。

#### 方案 B：异步订阅投影

Projector 通过 Redis Pub/Sub 订阅 PostCreated 事件，异步写入投影。

**优点**：解耦，创作不受投影失败影响。
**缺点**：增加延迟（Pub/Sub 传输 + 消费处理），可能丢消息。

#### 选型决策

**选定方案 A**。理由：
- spec 要求 ≤5s 可见，同步投影可保证 ≤100ms
- 投影写入操作轻量（单文档 upsert）
- 失败处理：catch error + log + 不阻塞创作响应
- EventPublisher 仍发布事件，外部消费者（推荐、搜索）异步处理

### 决策 5：端侧接口补齐策略

#### 方案 A：批量补齐全部 15 个方法（推荐）

一次性在 ContentRepository 的 abstract/mock/remote 三层补齐所有 service.yaml 中已实现的端点对应方法。

**优点**：端云接口完全对齐，一次性完成。
**缺点**：改动量较大（约 300 行代码）。

#### 方案 B：按优先级分批补齐

先补齐创作生命周期（update/delete/publish），后续批次补齐媒体和推荐。

**优点**：分步交付，风险分散。
**缺点**：需多次迭代，端侧接口长期不完整。

#### 选型决策

**选定方案 A**。这些方法都是 service.yaml 已声明、云侧已实现的端点，端侧只需要 HTTP 包装，不涉及复杂业务逻辑，一次性补齐效率最高。

---

## 关键设计决策汇总

| # | 决策 | 方案 | 理由 |
|---|------|------|------|
| D1 | 存储切换 | Config-driven 条件切换 | 改动小、向后兼容、PostRepository 接口已就绪 |
| D2 | 缓存接入 | Typed PostCacheRepository | 类型安全、infrastructure 层职责、无侵入 |
| D3 | 事件总线 | Redis Pub/Sub | 已验证、零新增依赖、当前规模适用 |
| D4 | 投影模式 | 进程内同步投影 + 外部异步事件 | ≤100ms 延迟、无丢消息、catch 降级 |
| D5 | 端侧补齐 | 批量一次性补齐 15 个方法 | 端点已实现、包装简单、避免多轮迭代 |

---

## Story 与测试层映射

| Story (L3) | 包含的 Acceptance | 测试层覆盖 |
|---|---|---|
| storage-cache-event-enablement | A1 存储 + A2 缓存 + A3 事件投影 + A4 治理 | T1 契约 + T3 集成 |
| missing-api-completion | A5 缺失 API | T1 契约 + T3 集成 |
| client-api-alignment | A6 端侧方法 + A7 兼容层清理 | T1 契约 + T2 组件 |
| deployment-ci-readiness | A8 Kustomize + A9 CI | T1 静态校验 |
| production-test-coverage | A10 T1 + A11 T2 + A12 T3+T4 | T1 + T2 + T3 + T4 |

---

## 适用场景与约束

- **适用**：content-service Post 聚合在 dev/integration/prod 三环境的生产化运行
- **约束**：
  - `PostRepository` 保持类型化接口（`*postmodel.Post`），不迁移到 `Repository[map[string]any]`
  - 缓存适配器在 infrastructure 层实现，PostService 无感知
  - Redis 不可用时降级到直读 MongoDB（缓存适配器内 catch error）
  - 投影失败不阻塞创作请求（PostService 内 catch + log）
- **局限性**：
  - 未使用 runtime Factory 的自动装饰能力（需手动编写 PostCacheRepository）
  - Redis Pub/Sub 无持久化，subscriber 离线丢消息（可从 DB 重建投影）
  - 热点计数不在本次范围（GetCounters 直读 DB）

---

## 未来演进

| 演进项 | 触发条件 | 目标 |
|--------|----------|------|
| 迁移到 runtime Factory | 新增 Report 聚合根或需要统一 interceptor 链时 | PostService 使用 `Repository[map[string]any]` |
| Redis Pub/Sub → NATS/Kafka | 事件消费者 >3 或 QPS > 10K 时 | 持久化消息、consumer group |
| 热点计数缓冲 | 单 Post like/view QPS > 1K 时 | Redis INCR + 异步回写 MongoDB |
| MongoDB 分片 | 内容量 > 500 万时 | `_id: hashed` 分片键 |
| 读写分离 | 读 QPS > 5K 时 | `secondaryPreferred` for feed queries |
| CDN 媒体加速 | 媒体请求 QPS > 1K 时 | OSS + CDN 域名替换 |

---

## 存量带规划任务

| 存量项 | 规划 | 承接节点 |
|--------|------|----------|
| runtime Factory 全量迁移 | 新聚合根引入时启动 | content-type-framework |
| 创作页目录迁移 (features/create → ui/content/entry) | 下次 UI 重构时 | dual-rail-discovery-redesign |
| Report 举报体系 | 独立 L3 特性 | publish-comment-reaction |
| `_CurrentContentDataService` 移除 | FeedItemDto 清理后 | 本特性 client-api-alignment |
