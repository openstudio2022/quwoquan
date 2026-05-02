# L2 特性：content-service-cloud-production

## 背景与动机

content-service 已完成契约基础层（`content-service-contract-foundation`，已归档），metadata 驱动的领域模型、错误码、行为采集、隐私安全、UI 配置、三层测试契约均已就绪。端侧 Discovery 页和创作页在 Mock 模式下已完成 UI 验证（双轨发现页、沉浸式作品浏览器、微趣社交流、创作四类型入口）。

**但 content-service 尚无法部署到灰度和生产**，原因如下：

1. **存储层未启用**：`main.go` 默认使用内存 `PostStore`，MongoDB `MongoPostStore` 已实现但仅在契约测试中使用，服务重启即丢数据。
2. **实体缓存未接入**：`storage.yaml` 定义了 5 个 Redis 缓存键，runtime `CacheableRepository` 装饰器已就绪，但 content-service 未通过 `EntityRegistry + Factory.WithCache` 构建 Repository。
3. **事件总线为空壳**：`EventPublisher` 使用测试用 `EventSpy`，无生产级 Redis Pub/Sub 或 MQ，导致创作后无法实时推送到发现流投影。
4. **6 个已声明 API 返回 `handleNotImplemented`**：ListComments、DeleteComment、GetCounters、ListUserPosts、GetHelperRead，加上 Report 系列。
5. **端侧 14 个云侧已实现 API 未封装**：UpdatePost、DeletePost、PublishPost、媒体上传链路、推荐接口等均未在 `ContentRepository` 中封装。
6. **部署配置不完整**：无 Kustomize base/overlays、无 HPA/PDB、无 Service、无健康检查探针。CI Pipeline 缺少 content-service 契约测试 Job。
7. **四层测试缺失关键旅程**：创作→发现流可见、评论 CRUD 全旅程、媒体上传全链路、缓存命中/失效验证均无覆盖。

本特性将 content-service 从"开发验证态"推进到"灰度/生产就绪态"，使其具备千万级内容发布的基础能力。

## 目标用户

- **内容创作者**：发布微趣、美图、视频、文章后，内容在发现流中 ≤5s 可见，操作（点赞、评论、收藏）持久化且不丢失。
- **内容消费者**：在发现页浏览内容时获得稳定、低延迟的体验，Feed 加载 P99 ≤ 800ms。
- **平台运维**：content-service 可通过标准化 Kustomize 配置独立部署、弹性伸缩、灰度发布，具备可观测性和治理能力。

## 功能范围

### 云侧（content-service）

1. **存储层启用**：`main.go` 切换默认存储为 `MongoPostStore`，通过 `EntityRegistry` 驱动 Repository 初始化，保留 InMemory 作为 `APP_ENV=alpha` 的 fallback。
2. **实体缓存接入**：Post 读取走 `CacheableRepository` 装饰器（Redis `cache:post:{id}`，TTL 300s），写时失效（Update/Delete → InvalidateCache）。Reaction 缓存 `reaction:{uid}:{pid}` TTL 300s。
3. **事件总线启用**：接入 Redis Pub/Sub 作为 `EventPublisher` 实现。发布 `PostCreated`、`PostUpdated`、`PostDeleted`、`CommentCreated`、`ReactionChanged` 事件。`DiscoveryFeedProjector` 消费事件维护 `rm_discovery_feed` 读模型。
4. **缺失 API 实现**：
   - `ListComments`：游标分页，按 `createdAt` 排序
   - `DeleteComment`：软删除 + `CommentDeleted` 事件
   - `GetCounters`：从缓存/DB 聚合 like/comment/favorite/share 计数
   - `ListUserPosts`：用户主页创作 Tab，按 `authorId` + `status=published` 过滤
   - `GetHelperRead`：辅助阅读摘要（文章类型）
5. **治理能力接入**：HTTP handler 接入 `runtime/governance` 限流/熔断中间件，`runtime/observability` 追踪 + 指标 + IO 日志中间件。
6. **配置规范化**：MongoDB DSN 通过环境变量 `MONGO_URI` 注入（Secret），Redis 配置通过 `config.yaml` 的 `redis.rec` / `redis.general` 节。

### 端侧（quwoquan_app）

7. **ContentRepository 接口补齐**：Abstract + Mock + Remote 三层补充以下方法：
   - Post 生命周期：`updatePost`、`deletePost`、`publishPost`
   - 圈子分发：`updatePostCircles`、`repostToCircle`、`quoteToCircle`
   - 媒体上传：`initMediaUpload`、`completeMediaUpload`、`abortMediaUpload`、`getMediaAsset`
   - 视频封面：`selectAutoVideoCover`、`selectManualVideoCover`
   - 文章摘要：`generateArticleSummary`
   - 推荐：`getRecommendation`
   - 用户创作列表：`listUserPosts`
8. **FeedItemDto 兼容层清理**：移除 `listDiscoveryFeedPageCurrent`，所有调用方迁移到 `PostBaseDto` 子类。

### 部署与 CI

9. **content-service Kustomize 配置**：
   - `base/`：Deployment、Service、HPA、PDB
   - `overlays/dev`：单副本、低资源限制
   - `overlays/integration`：2 副本、中等资源
   - `overlays/prod`：3+ 副本、高资源、topologySpreadConstraints
   - 健康检查探针（liveness + readiness）
10. **CI Pipeline 补充**：新增 `test-content-service` Job（含 MongoDB service container），Kustomize validate 覆盖所有 overlays。

### 四层测试

11. **T1 契约与静态层**：
    - 云侧：创作→投影一致性契约测试、评论 CRUD 契约测试、计数器一致性契约测试、缓存命中/失效契约测试
    - 端侧：ContentRepository Remote 方法契约测试（HTTP 请求/响应结构）
12. **T2 模块与交互层**：
    - 端侧：创作页 4 类型 widget test、发现页 Feed 加载 widget test、评论列表交互 widget test
13. **T3 端云集成层**：
    - content-service 端到端集成测试（HTTP → MongoDB → Redis → 事件 → 投影）
14. **T4 端到端旅程层**：
    - Patrol E2E：创作微趣→发现流可见旅程、创作美图→发现流可见旅程、评论全旅程

## 不做什么（Out of Scope）

- **推荐模型训练与更新**：rec-model-service 的模型迭代属于 `recommendation-platform` 独立 L1。
- **CDN/OSS 媒体对象存储集成**：媒体存储的云厂商选型与 CDN 接入属于 `media-processing-helper-read` 独立 L2。
- **Report 举报体系**：CreateReport/GetReport/ResolveReport 属于独立 L3 特性，不在本次范围。
- **全文搜索功能**：Atlas 全文/向量索引的搜索 API 属于独立特性。
- **端侧创作页目录迁移**：`lib/features/create/` → `lib/ui/content/entry/` 的目录重构不在本次范围，仅保证创作 → `ContentRepository.createPost` 的数据链路贯通。
- **MongoDB 分片与读写分离**：千万级性能优化作为后续 L2 特性，本次确保索引就绪和基础分页性能。
- **热点计数缓冲（Redis INCR + 异步回写）**：属于性能优化，本次仅实现 GetCounters 从 DB 读取。

## 约束

### 技术约束

- 云侧必须使用 `runtime/repository.Repository[T]` 接口 + `EntityRegistry` 驱动初始化，禁止绕过 Registry 直接操作 MongoDB。
- 缓存装饰器必须使用 `runtime/repository/cached.go` 的 `CacheableRepository`，禁止自建缓存层。
- 事件发布必须使用 `runtime/messaging.MessageEnvelope`，禁止自定义 MQ 序列化。
- 端侧 Remote 实现必须使用 `CloudRuntimeConfig.gatewayBaseUrl` + `CloudRequestHeaders.forPage(pageId)`。
- codegen 产物 `DO NOT EDIT` 标记文件禁止手改。

### 部署约束

- `deploy/shared/process_domain_mapping.yaml` 中 content 归属不变：dev=content-service，integration/prod=seed-box。
- integration 与 prod 的 process-domain 映射必须一致。
- content-service 部署配置必须参照 chat-service 的 Kustomize 结构（base + 3 overlays）。

### 业务约束

- 存储切换必须向后兼容：已有的 Mock 数据不影响本地开发体验。
- 端侧 Mock/Remote 切换仍通过 `appDataSourceModeProvider` 控制，UI 层无感知。

## 适用范围与约束

- **适用**：content-service 的 Post 聚合及全部子类型（image/video/micro/article），以及 Comment、MediaAsset、ContentReaction、DiscoveryFeed 投影。
- **适用环境**：dev（独立 content-service）、integration（seed-box 内）、prod（seed-box 内）。
- **不适用**：其他域服务（user-service、chat-service、circle-service）的生产就绪化——模式相同但独立交付。
- **前置条件**：`content-service-contract-foundation` 已归档完成；metadata YAML、codegen 工具链已就绪。

## 对标输入与吸收结论

本特性为内部工程成熟度提升，将已存在的代码从开发态推到生产态，无需外部产品对标。

技术参考：
- **chat-service 部署配置**：作为同仓 Kustomize 配置的参照标准（HPA/PDB/探针/资源限制/overlays 结构）。
- **runtime 已有能力**：Repository 工厂、CacheableRepository、Redis Router、governance、observability 均已在 chat-service 中验证，content-service 复用即可。

## 验收重点

| 维度 | 关键验收点 |
|------|-----------|
| 存储持久化 | MongoDB 启用，重启不丢数据 |
| 缓存命中 | Post 读取走 Redis，写后失效 |
| 事件投影 | 创作→发现流 ≤5s |
| API 完整性 | 云侧 0 个 handleNotImplemented；端侧 Remote 方法全覆盖 |
| 部署就绪 | Kustomize 3 环境 + HPA + PDB + 探针 |
| CI 覆盖 | content-service 契约测试入 Pipeline |
| 四层测试 | T1 契约 + T2 组件 + T3 集成 + T4 E2E 覆盖核心旅程 |
| 治理能力 | 限流/熔断/可观测接入 |

## 子节点规划（L3，在 /design 阶段细化）

| 子节点 | 职责 | 依赖 |
|--------|------|------|
| `storage-cache-event-enablement` | MongoDB 启用 + Redis 缓存 + 事件总线 + 治理接入 | 无 |
| `missing-api-completion` | 6 个 handleNotImplemented 端点实现 | storage-cache-event-enablement |
| `client-api-alignment` | 端侧 15 个方法补齐 + FeedItemDto 清理 | missing-api-completion |
| `deployment-ci-readiness` | Kustomize + CI Pipeline + 配置管理 | storage-cache-event-enablement |
| `production-test-coverage` | 四层测试补全（T1-T4） | 以上所有 |
