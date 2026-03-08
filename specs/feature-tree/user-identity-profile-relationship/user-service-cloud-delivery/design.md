# 用户服务云侧实现与端云一致性交付 — 设计方案

## 设计动因

端侧"我的主页"和"作者主页"（`profile-homepage-redesign`）已完成 UI 重构，通过 `ProfileShell` 统一组件 + `UserProfileRepository`（18 方法 Abstract + Mock + Remote 三层）驱动全部业务数据。然而 Remote 无后端可调，当前默认 Mock。

云侧 metadata 完整（`user_profile/fields.yaml` + `service.yaml` + `storage.yaml` + `errors.yaml`、`follow_edge/*`、`block_edge/*`），但 `services/user-service/` 不存在，seed-box Go 二进制也不存在。

本设计将基于已有 metadata 和 content-service 标杆模式，完成 user-service 的 DDD 四层实现、存储与缓存、部署流水线、端侧 codegen 对齐和四层测试覆盖。

## 上游输入评审

| 维度 | 评审结论 |
|------|---------|
| spec.md | F1~F5 功能范围清晰，O1~O8 边界明确 |
| acceptance.yaml | A1~A18 覆盖端云链路、存储缓存、codegen、部署、四层测试、工程质量，每条均有 SMART 判定条件 |
| 阻断项 | **无**。metadata 完整，runtime 能力就绪（`ModuleUser` 已定义、`Repository[T]` + `EventPublisher` + `UnitOfWork` 可用、`NewUserClient()` 已存在） |
| 补充项 | 需新增 `user-service/internal/generated/errors.go`（codegen 产物），需更新 Makefile/CI |

## 对标分析

### 内部标杆：content-service

| 维度 | content-service 做法 | user-service 对齐 |
|------|---------------------|-------------------|
| 启动流程 | `resolveRuntimeIdentity → loadRuntimeConfig → validate → 依赖注入 → Handler.Routes() → ListenAndServe` | 完全复用，增加 PG/Mongo/Redis 三路初始化 |
| Handler | `ContentHandler` 注入 3 个 Service，`Routes()` 返回 `http.Handler` | `UserHandler` 注入 6 个 Service |
| 路由注册 | `RegisterGeneratedRoutes` + `generatedRouteTable` 匹配 method + pathTemplate | 生成 `generated_routes.go`，20+ 路由 |
| Service | 依赖 `persistence.PostRepository` 接口，Option 注入 | 依赖 `persistence.XxxRepository` 接口 + `repository.UnitOfWork` |
| Model | codegen `DO NOT EDIT`，json + bson tag | user 实体 codegen，PG 用 json tag（无 bson） |
| 存储 | `PostStore`（内存）+ `MongoPostStore`（MongoDB） | PG Store + Mongo Store，按实体选择 |
| 测试 | `TestMain` 启动 testcontainers mongo + miniredis，`testHandler` 供契约测试 | 复用 `testinfra.NewSuite(WithPostgres, WithMongo, WithRedis)` |
| 错误码 | `generated/errors.go` 定义 `Err*` sentinel | 生成 `Err*` + `AppErrorFrom*`（与 integration-service 模式一致） |

---

## 方案对比与选型

### KD1: 服务骨架组织方式

**方案 A：标准 DDD 四层（与 content-service 一致）**

```
services/user-service/
├── cmd/api/main.go
├── internal/
│   ├── domain/{user,follow,block}/model/   # codegen 实体
│   ├── domain/{user,follow,block}/repository/  # codegen 接口
│   ├── domain/{user,follow,block}/event/   # codegen 事件
│   ├── application/                        # 手写用例
│   ├── adapters/http/                      # Handler + generated_routes
│   ├── generated/                          # codegen 错误码
│   └── infrastructure/persistence/         # PG + Mongo Store
├── tests/
└── configs/
```

**方案 B：runtime/repository.Factory 驱动（metadata-first 极致化）**

由 `runtime/repository.Factory.Create(entityName)` 按 metadata 自动创建 Repository，无需手写 Store。

**方案 C：扁平化（无子域分包）**

所有实体放在同一个 `domain/model/` 下。

**选型决策：方案 A**

理由：
1. 与 content-service 模式完全一致，团队认知成本为零
2. user 域有 3 个子域（user/follow/block），分包清晰
3. `runtime/repository.Factory`（方案 B）尚未被任何服务实际采用，在 user-service 上首次使用风险过高
4. 扁平化（方案 C）在实体数量多时文件组织混乱

---

### KD2: 存储引擎选型

按 `storage.yaml` 已有定义，无需重新选型：

| 实体 | 存储引擎 | 理由（storage.yaml） |
|------|---------|---------------------|
| UserProfile, Persona, UserSetting, BlockEdge, UserWork, UserLifeItem | **PostgreSQL** | 强 ACID、关系约束、乐观锁、GIN 全文搜索 |
| FollowEdge | **MongoDB** | 高写入吞吐、灵活 schema、图遍历索引 |

PostgreSQL 使用 `jackc/pgx/v5`（pool），MongoDB 使用 `go.mongodb.org/mongo-driver/v2`。

---

### KD3: 缓存策略

按 `storage.yaml` 已有定义：

| Key Pattern | TTL | 类型 | 实体 | 失效事件 | 实现 |
|:------------|:----|:-----|:-----|:---------|:-----|
| `cache:user_profile:{userId}` | 600s | string(JSON) | UserProfile | UserProfileUpdated | `redis.Client.Set/Get/Del` |
| `cache:user_setting:{userId}` | 600s | string(JSON) | UserSetting | UserSettingUpdated | `redis.Client.Set/Get/Del` |
| `blocked_set:{userId}` | 3600s | **set** | BlockEdge | UserBlocked(SADD) / UserUnblocked(SREM) | `redis.Client.SAdd/SIsMember/SRem` |
| `device_tokens:{userId}` | 3600s | set | UserDevice | -- | `redis.Client.SAdd` |

**缓存读写模式**：Cache-Aside（旁路缓存）

```
Read:
  1. Redis GET → hit → 返回
  2. miss → PostgreSQL SELECT → Redis SET(TTL) → 返回

Write:
  1. PostgreSQL UPDATE
  2. Redis DEL（而非更新，避免脏写）
  3. 发布 DomainEvent（供异步消费方感知）
```

**方案对比**（缓存装饰器）：

| 方案 | 优点 | 缺点 | 选型 |
|------|------|------|------|
| A: `runtime/repository.NewCachedRepository` 装饰器 | 自动化，codegen 可生成 | 仅支持单实体缓存，不支持 join 视图 | -- |
| **B: 手写 Cache 层** | 灵活支持 `user_full_snapshot`（join profile+persona+setting） | 多一层代码 | **选定** |
| C: Application 层内联缓存 | 无额外层 | 缓存逻辑与业务逻辑耦合 | -- |

选定方案 B 理由：`GetProfile` 需要 join profile + activePersna + setting（`user_full_snapshot`），单实体装饰器无法满足；手写 Cache 层可精确控制 join 逻辑和缓存粒度。

---

### KD4: 部署方式

**方案 A（推荐）：user-service 作为 seed-box Pod sidecar**

```
seed-box Pod
├── seed-box 容器 (port 8080) — content/chat/circle 等
├── recommendation-service 容器 (port 18090) — 已有
└── user-service 容器 (port 18081) — 新增
```

优点：与 recommendation-service 部署模式一致，改动最小，不需要创建 seed-box Go 二进制。
缺点：Pod 内多容器资源共享，user-service 故障不影响其他容器（独立 readiness）。

**方案 B：user-service 独立 Deployment**

独立 Deployment + Service + HPA，不在 seed-box Pod 内。

优点：独立扩缩、独立发布。
缺点：需更新 `process_domain_mapping.yaml` 将 user 从 seed-box 分离，影响拓扑一致性约束。

**方案 C：seed-box 聚合二进制**

创建 `cmd/seed-box/main.go` 聚合所有域 Handler。

优点：长期最优，单进程单端口。
缺点：需要所有域 Handler 可导入，当前 circle/chat/integration 的 Handler 导出模式不一致，改造工作量大。

**选型决策：方案 A（sidecar）**

理由：
1. recommendation-service 已验证 sidecar 模式可行
2. 不需要创建 seed-box 二进制（方案 C 改造工作量超出本特性范围）
3. 保持 `process_domain_mapping.yaml` 拓扑不变（user 仍在 seed-box）
4. 独立容器有独立探针，user-service 故障不影响其他域

---

### KD5: 路由注册方式

**方案 A：codegen `generated_routes.go`（与 content-service 一致）**

`generatedRouteTable` + `resolveGeneratedOperation` + `dispatchGeneratedOperation`

**方案 B：手写 ServeMux 注册**

```go
mux.HandleFunc("GET /v1/user/profile/{userId}", h.handleGetProfile)
mux.HandleFunc("POST /v1/user/follow/{targetUserId}", h.handleFollow)
```

**选型决策：方案 B（手写）**

理由：
1. Go 1.22+ 的 `net/http` 原生支持 method + path pattern（`GET /v1/...`），无需 codegen 匹配逻辑
2. content-service 的 `generatedRouteTable` + `resolveGeneratedOperation` 是在 Go 1.21 时代写的权宜之计
3. 手写路由 20+ 行，清晰可审计，与 `service.yaml` 一一对应
4. 减少 codegen 依赖，user-service 作为新服务可采用更现代的模式

---

### KD6: 错误码生成方式

**方案 A：sentinel `Err*` + 手写 `rterr.NewAppError`（content-service 模式）**

```go
var ErrUserNotFound = errors.New("USER.USER.not_found")

// Handler 中手写
rterr.NewAppError(code, "用户不存在", debugMsg, false)
```

**方案 B：`Err*` + codegen `AppErrorFrom*`（integration-service 模式）**

```go
var ErrUserNotFound = errors.New("USER.USER.not_found")

func AppErrorFromUserNotFound(debugMessage string) *rerrors.AppError {
    code, _ := rerrors.ParseCode(string(ErrUserNotFound.Error()))
    return rerrors.NewAppError(code, "用户不存在", debugMessage, false)
}
```

**选型决策：方案 B**

理由：
1. `user_message` 来自 `errors.yaml`，不应在 Handler 中硬编码
2. `AppErrorFrom*` 将 `errors.yaml` 的 user_message 固化到 codegen 产物，确保端云一致
3. 与 integration-service 模式一致，已被验证
4. Handler 调用 `generated.AppErrorFromUserNotFound(debugMsg)` 即可，无需记忆 user_message

---

### KD7: 测试基础设施

**方案 A：手写 TestMain（content-service 模式）**

```go
func TestMain(m *testing.M) {
    // 手动启动 mongo container + miniredis + ...
}
```

**方案 B：`testinfra.NewSuite`（runtime 标准模式）**

```go
func TestMain(m *testing.M) {
    suite := testinfra.NewSuite(t,
        testinfra.WithPostgres(),
        testinfra.WithMongo("user_test"),
        testinfra.WithRedis(),
    )
    defer suite.TearDown()
    // Wire services...
}
```

**选型决策：方案 B**

理由：
1. `testinfra.NewSuite` 封装了 embedded-postgres + testcontainers-mongo + miniredis 的生命周期管理
2. 统一测试基础设施，减少 boilerplate
3. `suite.CleanPG(t)` / `suite.CleanMongo(t)` 提供标准清理方法

---

### KD8: 跨聚合计数更新（follow → profile count）

**方案 A：同步事务（应用层编排）**

```go
func (s *FollowService) Follow(ctx context.Context, followerId, followeeId string) error {
    // 1. MongoDB: insert follow_edge
    // 2. PostgreSQL: UPDATE user_profiles SET follower_count = follower_count + 1 WHERE user_id = followeeId
    // 3. PostgreSQL: UPDATE user_profiles SET following_count = following_count + 1 WHERE user_id = followerId
    // 4. Redis: DEL cache:user_profile:{followeeId}, DEL cache:user_profile:{followerId}
}
```

**方案 B：事件驱动异步（最终一致）**

Follow → 发布 UserFollowed 事件 → 异步消费者更新 count

**选型决策：方案 A（同步）**

理由：
1. 用户关注后立即看到 followerCount 变化（端侧 `toggleFollow` 后刷新 profile）
2. 跨 MongoDB→PostgreSQL 无分布式事务，但 follow 操作本身幂等（unique index），count 更新用 `SQL +1/-1` 原子操作
3. 若 PG 更新失败，follow_edge 已写入 MongoDB，下次查询 count 可通过定时修复任务对齐（最终一致 fallback）
4. 当前不追求精确计数，最终一致即可

---

### KD9: PostgreSQL 连接管理

使用 `jackc/pgx/v5/pgxpool`：

```go
pool, err := pgxpool.New(ctx, cfg.Postgres.DSN)
pool.Config().MaxConns = int32(cfg.Postgres.MaxOpenConns)     // 25
pool.Config().MinConns = int32(cfg.Postgres.MaxIdleConns)     // 5
pool.Config().MaxConnLifetime = time.Duration(cfg.Postgres.ConnMaxLifetimeMinutes) * time.Minute // 30min
```

事务通过 `pool.BeginTx(ctx, pgx.TxOptions{})` + `tx.Commit/Rollback`。
`PersonaService.Activate` 使用事务保证唯一 active 约束。

---

### KD10: main.go 启动流设计

```
1. resolveRuntimeIdentity()
   → SERVICE_NAME=user-service, APP_ENV, CONFIG_ROOT, CONFIG_VERSION, IMAGE_VERSION

2. loadRuntimeConfig()
   → default → env → version 三层合并（复用 content-service 配置加载逻辑）

3. validateRuntimeCompatibility() + preflightConfig()
   → PostgreSQL ping、MongoDB ping、Redis ping

4. 初始化存储连接
   4a. pgxpool.New(cfg.Postgres.DSN)                      → pgPool
   4b. mongo.Connect(cfg.MongoDB.URI) → db("quwoquan")    → mongoDB
   4c. redis.MustNewRouter(cfg.Redis)                      → redisRouter

5. 运行 PostgreSQL Migration
   → embedded migration files (infrastructure/migration/*.sql)

6. 构建 Persistence Stores
   6a. PgProfileStore(pgPool)       → profileStore
   6b. PgPersonaStore(pgPool)       → personaStore
   6c. PgSettingStore(pgPool)       → settingStore
   6d. PgBlockStore(pgPool)         → blockStore
   6e. PgWorkStore(pgPool)          → workStore
   6f. PgLifeItemStore(pgPool)      → lifeItemStore
   6g. MongoFollowStore(mongoDB)    → followStore

7. 构建 Cache Layers
   7a. ProfileCache(redisRouter.Scene("general"))  → profileCache
   7b. SettingCache(redisRouter.Scene("general"))   → settingCache
   7c. BlockCache(redisRouter.Scene("general"))     → blockCache

8. 构建 Application Services
   8a. ProfileService(profileStore, personaStore, settingStore, profileCache, settingCache)
   8b. FollowService(followStore, profileStore, profileCache)
   8c. BlockService(blockStore, blockCache)
   8d. PersonaService(personaStore, pgPool)  // 注入 pool 供事务
   8e. WorkService(workStore)
   8f. LifeItemService(lifeItemStore)

9. 构建 HTTP Handler
   handler := httpadapter.NewUserHandler(
       profileService, followService, blockService,
       personaService, workService, lifeItemService,
   ).Routes()

10. 注册探针
    /healthz  → 200（快速）
    /livez    → PG ping + Redis ping
    /startupz → PG ping + Mongo ping + Redis ping

11. ListenAndServe(:18081) + 优雅关闭（SIGTERM → 30s drain）
```

**seed-box 集成接口**：
导出 `NewUserHandler(...)` 和 `Routes()`，供未来 seed-box 聚合二进制调用。

---

### KD11: 端侧 codegen 对齐

**当前状态**：
- `UserWorkItem`/`UserLifeItem` 在 `user_profile_mock_data.dart` 手写
- `UserErrorCode` 枚举不存在
- Remote 实现使用 `throw Exception('xxx failed: ${resp.statusCode}')`

**目标**：
1. `make codegen-app` 生成：
   - `lib/cloud/runtime/generated/user/user_profile_dto.g.dart`
   - `lib/cloud/runtime/generated/user/user_work_dto.g.dart`
   - `lib/cloud/runtime/generated/user/user_life_item_dto.g.dart`
   - `lib/cloud/runtime/generated/user/user_metadata.g.dart`
   - `lib/cloud/runtime/generated/user/user_errors.g.dart`（`UserErrorCode` 枚举）

2. 替换手写类型：`UserWorkItem` → `UserWorkDto`，`UserLifeItem` → `UserLifeItemDto`

3. Remote 错误处理：
```dart
// Before
throw Exception('getUserProfile failed: ${resp.statusCode}');

// After
final error = CloudErrorMapper.fromResponse(resp);
throw CloudException(error);  // UserErrorCode.fromCode(error.code)
```

4. `CloudErrorMapper` 需注册 `UserErrorCode`

---

### KD12: 部署配置详设

#### 12.1 Dockerfile

```dockerfile
FROM golang:1.24-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /user-service ./services/user-service/cmd/api/

FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /user-service /usr/local/bin/user-service
COPY contracts/metadata /etc/metadata
EXPOSE 18081
ENTRYPOINT ["user-service"]
```

#### 12.2 seed-box deployment.yaml sidecar 新增

```yaml
- name: user-service
  image: seed-box/user-service:latest
  imagePullPolicy: IfNotPresent
  ports:
    - name: user-http
      containerPort: 18081
  env:
    - name: APP_ENV
      value: integration
    - name: SERVICE_NAME
      value: user-service
    - name: CONFIG_ROOT
      value: /etc/seed-box-config
    - name: CONFIG_VERSION
      value: v0.0.0
    - name: IMAGE_VERSION
      value: v0.0.0
    - name: POSTGRES_DSN
      valueFrom:
        secretKeyRef:
          name: user-service-postgres
          key: dsn
  readinessProbe:
    httpGet:
      path: /healthz
      port: user-http
    initialDelaySeconds: 5
    periodSeconds: 10
  livenessProbe:
    httpGet:
      path: /livez
      port: user-http
    initialDelaySeconds: 15
    periodSeconds: 20
  startupProbe:
    httpGet:
      path: /startupz
      port: user-http
    failureThreshold: 30
    periodSeconds: 5
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
    limits:
      cpu: "1"
      memory: 1Gi
```

#### 12.3 CI 流水线更新

| Workflow | 修改 |
|----------|------|
| `service_pipeline.yml` | 增加 `go build ./services/user-service/...` + Docker build + push |
| `delivery-gate.yml` | L2 门禁增加 `go test ./services/user-service/...` |
| `pre-release-gate.yml` | deploy-integration 包含 user-service |

#### 12.4 Makefile 更新

```makefile
build:
    go build ./runtime/...
    go build ./tools/...
    go build ./services/user-service/...

test-contract:
    go test ./services/content-service/... ./services/user-service/... -v -count=1
```

#### 12.5 灰度流程

```
代码入库 dev1.0 → merge to main → tag v*-rc*
  → 04. Pre-Release Gate (gate + deploy-integration + L3 + L4)
  → 05. Deploy To Prod (Gray) / 06. Auto
    → Stage 1: 50% (auto) → SLO gate → Stage 2: 100% (审批)
```

---

## Story 与测试层映射

| Story | 范围 | 验收项 | 测试层 |
|-------|------|--------|--------|
| S1: 骨架 + 配置 | `make new-service` + 四环境配置 + process_domain_mapping | -- | -- |
| S2: Domain 层 | 3 子域 model + repository + event（codegen 对齐 metadata） | A17 | T2 |
| S3: Infrastructure 层 | PG Store×6 + Mongo Store×1 + Cache×3 + Migration DDL×7 | A5, A6, A7 | T2 |
| S4: Application 层 | ProfileService + FollowService + BlockService + PersonaService + WorkService + LifeItemService | A1, A2, A3, A4 | T2 |
| S5: HTTP Adapter + main.go | UserHandler 20+ 路由 + main.go 启动流 + 探针 | A1, A18 | T2 |
| S6: 云侧契约测试 | L2 测试×7 文件（testmain + helpers + profile/follow/block/persona/cache/error/work_life） | A14 | T2 |
| S7: 部署流水线 | Dockerfile + Kustomize overlay + CI workflow + Makefile + 配置版本 | A10, A11, A12 | T3 |
| S8: 端侧 codegen 对齐 | codegen-app + DTO 替换 + UserErrorCode + Remote 错误处理 | A8, A9 | T1 |
| S9: 端侧测试补充 | L1 DTO 字段契约 + 错误码契约 + L4 旅程测试×4 | A13, A16 | T1, T4 |
| S10: 集成验证 + 验收 | L3 端云集成 + make gate-full + A1~A18 逐项 | A15, A17, A18 | T3 |

**推荐实施顺序**：S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9 → S10

理由：先骨架，再从 domain 到 infrastructure 到 application 到 adapter 自底向上构建，每一层完成后可立即写对应的 L2 测试验证。部署在服务可运行后执行。端侧对齐和测试最后，因为依赖云侧 API 就绪。

---

## 适用场景与约束

### 适用场景

- user 域业务对象数量有限（6 PG 表 + 1 MongoDB 集合），单服务承载合理
- 读多写少场景（GetProfile 高频，Follow/Block 低频），Cache-Aside 策略适合
- sidecar 部署与 recommendation-service 模式一致，团队已熟悉

### 约束与局限性

- **跨存储无分布式事务**：follow 写 MongoDB + count 更新 PG 无原子性保证，依赖幂等 + 最终一致
- **sidecar 资源共享**：user-service 与 seed-box 主容器共享 Pod 资源上限，需监控
- **PostgreSQL 连接数**：每 Pod 1 个连接池（25 conns），3 Pod = 75 conns，需确保 PG 实例支持
- **缓存一致性窗口**：UpdateProfile 后到缓存失效间有短暂不一致（毫秒级）
- **followerCount 非精确**：极端并发下 +1/-1 可能不精确，需要定期修复任务

---

## 未来演进

### E1: seed-box 聚合二进制

当所有域 Handler 导出模式统一后，创建 `cmd/seed-box/main.go` 聚合所有域，替代 sidecar 模式。
- 触发条件：content/circle/chat/integration 的 Handler 均导出 `NewXxxHandler() http.Handler`
- 变更范围：新增 seed-box main，删除 sidecar 配置
- 影响：减少 Pod 内容器数量，降低资源开销

### E2: 精确计数器

当用户量级上升到百万级时，followerCount/followingCount 可能出现累计偏差。
- 触发条件：count 漂移率 > 0.1%
- 方案：定时修复任务（cron）对比 MongoDB count(follow_edges) 与 PG followerCount，修正差值
- 变更范围：新增 cron job，不影响主流程

### E3: 事件驱动缓存失效

当前缓存失效在同一请求内同步执行（DEL）。未来可通过 DomainEvent → 消息队列 → 消费者异步失效。
- 触发条件：缓存操作延迟影响请求 P95
- 变更范围：引入 MQ 消费者，不影响主流程

### E4: 用户搜索

GIN trigram 索引已建（`gin_user_profiles_search` on nickname, bio），搜索 API 属于 gateway/orchestrator 域。
- 触发条件：gateway 服务就绪
- 变更范围：gateway 调用 user-service 的 search endpoint

---

## 编码规范

### Go 云侧

- DDD 分层：domain ← application ← adapters ← infrastructure（单向依赖）
- domain 层仅 import 标准库 + `quwoquan_service/runtime/` 接口
- 错误返回使用 `runtime/errors.AppError`
- HTTP 响应使用 `runtime/errors.WriteHTTPError`
- Repository 返回 `error`（不返回 bool），让调用方决定处理策略
- 所有 SQL 使用参数化查询，禁止字符串拼接

### Dart 端侧

- 错误处理使用 `CloudException(UserErrorCode)`
- DTO 使用 codegen 产物，禁止手写
- Remote 实现使用 `CloudRuntimeConfig.gatewayBaseUrl` + `CloudRequestHeaders.forPage()`

---

## 遗留带规划任务

见 tasks.md「搁置任务」和「未来演进任务」章节。
