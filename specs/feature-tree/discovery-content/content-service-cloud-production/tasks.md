# content-service-cloud-production 任务列表

## 当前交付任务

> 顺序：config/metadata → infrastructure → application → adapters → 端侧 → 部署 → 测试

### Phase 0：云侧存储与运行时启用（A1 A2 A3 A4）

- [x] **C1** [config] 增加 MongoDB 配置节到 content-service config.yaml
  - `configs/default/config.yaml` 增加 `mongo.uri`（默认空，即 InMemory）
  - `configs/local/config.yaml` 增加 `mongo.uri: ""`（保持 InMemory）
  - `configs/integration/config.yaml` 增加 `mongo.uri: "${MONGO_URI}"`
  - `configs/prod/config.yaml` 增加 `mongo.uri: "${MONGO_URI}"`

- [x] **C2** [infrastructure] 创建 PostCacheRepository 缓存装饰器
  - 文件：`internal/infrastructure/cache/post_cache_repository.go`
  - 实现 `PostRepository` 接口
  - FindByID → read-through（Redis `cache:post:{id}`，TTL 300s）
  - Update/Delete → write-invalidate
  - Redis 不可用 → catch error → 降级直读 MongoDB
  - 使用 `redis.Router.Scene("general")` 获取 Redis Client

- [x] **C3** [infrastructure] 创建 Redis Pub/Sub EventPublisher 实现
  - 文件：`internal/infrastructure/messaging/redis_event_publisher.go`
  - 实现 `repository.EventPublisher` 接口
  - 使用 `redis.Router.Scene("general")` Publish
  - 事件序列化遵循 `runtime/messaging.MessageEnvelope`
  - 发布通道：`events.content.{eventType}`

- [x] **C4** [infrastructure] 完善 DiscoveryFeedProjector 的 MongoDB 写入
  - 确认 `recommendation/discovery_projector.go` 支持 MongoDB `rm_discovery_feed` collection
  - 确保 CreatePost 成功后同步调用 Projector
  - 失败 catch + log，不阻塞创作响应

- [x] **C5** [main.go] 存储切换 + 缓存 + 事件总线组装
  - 读取 `mongo.uri` 配置：有值 → `MongoPostStore(collection)`；空 → `PostStore(seed)`
  - MongoDB Client 初始化（`mongo.Connect` + graceful shutdown）
  - 创建 `PostCacheRepository` 包装 MongoPostStore
  - 创建 `RedisEventPublisher` 替代 `testinfra.EventSpy`
  - PostService.WithEventPublisher 注入真实 publisher
  - FeedService 中 DiscoveryFeedProjector 注入 MongoDB collection

- [x] **C6** [adapters] HTTP handler 接入治理与可观测中间件
  - handler 注册 `runtime/governance` 限流中间件（429 on exceeded）
  - handler 注册 `runtime/observability` HTTP 中间件（access log + trace span + metrics）
  - 确认 `/healthz`、`/livez`、`/startupz` 端点存在

### Phase 1：云侧缺失 API 实现（A5）

- [x] **C7** [application] 实现 ListComments
  - 在 PostService 或新建 CommentService 中实现
  - 参数：postId + cursor + limit
  - 从 MongoDB `comments` collection 查询
  - 按 `createdAt` 倒序，cursor 基于 `createdAt`
  - 返回 `Page[Comment]`

- [x] **C8** [application] 实现 DeleteComment
  - 软删除：设置 `deletedAt` 字段
  - 通过 EventPublisher 发布 `CommentDeleted` 事件
  - 返回 204 No Content

- [x] **C9** [application] 实现 GetCounters
  - 从 Post 文档中读取 `likeCount/commentCount/favoriteCount/shareCount`
  - 返回 JSON 对象 `{ like, comment, favorite, share }`

- [x] **C10** [application] 实现 ListUserPosts
  - 参数：userId + cursor + limit + contentType（可选）
  - 从 MongoDB `posts` collection 查询 `authorId=userId AND status=published`
  - 按 `publishedAt` 倒序
  - 返回 `Page[Post]`

- [x] **C11** [application] 实现 GetHelperRead
  - 仅支持 `contentType=article` 的 Post
  - 返回文章摘要（从 Post 的 `summary` 字段，或截取 body 前 200 字）
  - 非 article 类型返回 404

- [x] **C12** [adapters] 更新 generated_routes.go / content_handler.go
  - 将 C7-C11 的实现接入路由分发
  - 消灭所有 `handleNotImplemented` 返回 503 的分支
  - 注意：此步涉及 codegen 文件更新，需先 `make codegen-content-service`

### Phase 2：端侧接口补齐与兼容层清理（A6 A7）

- [x] **D1** [cloud/services] ContentRepository abstract 接口补充 15 个方法
  - Post 生命周期：`updatePost`、`deletePost`、`publishPost`
  - 圈子分发：`updatePostCircles`、`repostToCircle`、`quoteToCircle`
  - 媒体上传：`initMediaUpload`、`completeMediaUpload`、`abortMediaUpload`、`getMediaAsset`
  - 视频封面：`selectAutoVideoCover`、`selectManualVideoCover`
  - 文章摘要：`generateArticleSummary`
  - 推荐：`getRecommendation`
  - 用户创作列表：`listUserPosts`

- [x] **D2** [cloud/services] MockContentRepository 补充 15 个方法 Mock 实现
  - 返回本地 mock 数据，不发 HTTP
  - 媒体上传返回 mock sessionId / mediaId
  - listUserPosts 从 mock data 按 authorId 过滤

- [x] **D3** [cloud/services] RemoteContentRepository 补充 15 个方法 Remote 实现
  - URL 路径与 service.yaml routes 一致
  - 使用 `CloudRuntimeConfig.gatewayBaseUrl`
  - 使用 `CloudRequestHeaders.forPage(pageId)`
  - 统一错误处理（`CloudResponseDecoder`）

- [x] **D4** [cloud/services] 清理 FeedItemDto 兼容层
  - 移除 `listDiscoveryFeedPageLegacy` 方法
  - 搜索所有 `FeedItemDto` 引用，迁移到 `PostBaseDto` 子类
  - 确认 `_LegacyContentDataService` 不再使用 Legacy 方法
  - `flutter analyze lib/` 无错误

### Phase 3：部署与 CI（A8 A9）

- [x] **K1** [deploy] 创建 content-service Kustomize base
  - `deploy/service/content-service/kustomize/base/deployment.yaml`
    - 参照 chat-service：探针（liveness `/healthz` + readiness `/healthz` + startup `/startupz`）
    - 端口 18080（content-service 默认端口）
    - 环境变量：APP_ENV, SERVICE_NAME, CONFIG_ROOT, CONFIG_VERSION, IMAGE_VERSION, MONGO_URI
    - 资源限制：requests cpu=200m mem=256Mi, limits cpu=1 mem=512Mi
    - topologySpreadConstraints
    - terminationGracePeriodSeconds: 30
  - `deploy/service/content-service/kustomize/base/service.yaml`（port 18080）
  - `deploy/service/content-service/kustomize/base/hpa.yaml`（min=2, max=6, cpu=70%, mem=75%）
  - `deploy/service/content-service/kustomize/base/pdb.yaml`（minAvailable=1）
  - `deploy/service/content-service/kustomize/base/kustomization.yaml`

- [x] **K2** [deploy] 创建 content-service Kustomize overlays
  - `overlays/dev/kustomization.yaml`：replicas=1, HPA min=1 max=2
  - `overlays/integration/kustomization.yaml`：replicas=2, HPA min=2 max=4
  - `overlays/prod/kustomization.yaml`：replicas=3, HPA min=3 max=12, cpu=65%, mem=70%
  - 每个 overlay 通过 configMapGenerator 注入 APP_ENV + CONFIG_VERSION + IMAGE_VERSION
  - 参照 chat-service prod overlay 的 replacements 模式

- [x] **K3** [deploy] 创建 content-service Dockerfile
  - `deploy/service/content-service/Dockerfile`
  - 参照 chat-service Dockerfile：multi-stage build, golang:1.22-alpine builder
  - COPY configs/ 到 /etc/content-service/
  - EXPOSE 18080

- [x] **K4** [ci] 更新 service_pipeline.yml
  - 新增 `test-content-service` Job
    - 触发条件：`quwoquan_service/services/content-service/` 路径变动
    - services: MongoDB 7-jammy (port 27017)
    - 步骤：checkout → setup-go → cache → build → test（`go test ./services/content-service/... -v -count=1`）
    - 环境变量：`MONGO_URI=mongodb://localhost:27017`
  - `validate-deploy` Job 增加 content-service overlay 校验
    - `kustomize build deploy/service/content-service/kustomize/overlays/$env`

### Phase 4：四层测试补全（A10 A11 A12）

- [x] **T1** [test/cloud] 云侧契约测试：创作→投影一致性
  - 文件：`services/content-service/tests/post_projection_contract_test.go`
  - 场景：CreatePost → 查 rm_discovery_feed → 新内容存在
  - 场景：UpdatePost → rm_discovery_feed 同步更新
  - 场景：DeletePost → rm_discovery_feed 中移除

- [x] **T2** [test/cloud] 云侧契约测试：缓存命中/失效
  - 文件：`services/content-service/tests/post_cache_contract_test.go`
  - 场景：FindByID → cache miss → MongoDB 读取 → cache fill
  - 场景：FindByID（第二次）→ cache hit → 不读 MongoDB
  - 场景：Update → cache invalidate → 再次 FindByID → cache miss → refill

- [x] **T3** [test/cloud] 云侧契约测试：ListComments + DeleteComment + GetCounters
  - 文件：扩展 `services/content-service/tests/post_comment_contract_test.go`
  - 场景：CreateComment → ListComments → 可见
  - 场景：DeleteComment → ListComments → 不可见
  - 场景：Like + Comment → GetCounters → 计数正确

- [x] **T4** [test/cloud] 云侧契约测试：ListUserPosts
  - 文件：`services/content-service/tests/post_user_list_contract_test.go`
  - 场景：用户创建 3 个 Post → ListUserPosts → 返回 3 个
  - 场景：cursor 分页正确

- [x] **T5** [test/cloud] 云侧契约测试：领域事件发布
  - 文件：`services/content-service/tests/post_event_contract_test.go`
  - 场景：PostCreated 事件结构验证、CommentDeleted 事件发布、读操作无事件

## 搁置任务（带规划）

- [ ] **S1** runtime Factory 全量迁移（重启条件：新增 Report 聚合根或需要统一 interceptor 链时）
- [ ] **S2** Redis Pub/Sub → 专用 MQ（重启条件：事件消费者 >3 或 QPS > 10K）
- [ ] **S3** 创作页目录迁移 features/create → ui/content/entry（重启条件：下次 UI 重构）
- [ ] **S4** `_LegacyContentDataService` 彻底移除（重启条件：D4 兼容层清理完成后）
- [ ] **S5** 端侧契约测试：15 个新方法 Remote 请求结构（重启条件：端侧 Remote 联调开始时）
- [ ] **S6** 端侧组件测试：创作页 4 类型 Widget test（重启条件：创作页 UI 重构时）
- [ ] **S7** 端侧组件测试：发现页 Feed 加载 Widget test（重启条件：发现页接入 Remote 时）
- [ ] **S8** 端侧组件测试：评论列表/删除交互 Widget test（重启条件：评论 UI 重构时）
- [ ] **S9** T3 云侧端到端集成测试：全链路延迟验证（重启条件：staging 环境可用时）
- [ ] **S10** T4 Patrol E2E：创作到发现旅程 + 评论旅程（重启条件：端侧 UI 稳定后）

## 未来演进任务

- [ ] **E1** 热点计数缓冲：Redis INCR + 定时批量回写 MongoDB（对应 design.md 演进表）
- [ ] **E2** MongoDB 分片：`_id: hashed` 分片键，内容量 > 500 万时启动
- [ ] **E3** 读写分离：feed query 使用 `secondaryPreferred`，读 QPS > 5K 时启动
- [ ] **E4** CDN 媒体加速：OSS + CDN 域名替换，媒体 QPS > 1K 时启动
