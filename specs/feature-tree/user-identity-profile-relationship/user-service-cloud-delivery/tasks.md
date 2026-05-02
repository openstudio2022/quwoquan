# 用户服务云侧实现与端云一致性交付 — 任务列表

## 当前交付任务

### S1: 骨架 + 配置（先行）

- [ ] T01: [骨架] 执行 `make new-service SERVICE=user-service PORT=18081`，生成标准 DDD 目录
- [ ] T02: [配置] 填充 `configs/default/config.yaml`：service/http/postgres/mongodb/redis 配置节
- [ ] T03: [配置] 填充 `configs/alpha/config.yaml` / `configs/beta/config.yaml`：本地 PG/Mongo/Redis 地址
- [ ] T04: [配置] 填充 `configs/gamma/config.yaml`：集成环境（DSN 由 Secret 注入）
- [ ] T05: [配置] 填充 `configs/prod/config.yaml`：生产环境（Redis cluster + TLS）
- [ ] T06: [拓扑] 更新 `deploy/shared/process_domain_mapping.yaml` dev 环境增加 `user-service: domains: [user]`
- [ ] T07: [验证] `make gate` 通过 verify_deployment_domain_mapping

### S2: Domain 层

- [ ] T08: [model] 创建 `internal/domain/user/model/user_profile.go`：UserProfile struct（对齐 `user_profile/fields.yaml`）
  - 字段：userId(PK), nickname, avatarUrl, bio, gender, birthDate, region, status, profileVersion, followerCount, followingCount, postCount, circleCount, likeCount, createdAt, updatedAt
- [ ] T09: [model] 创建 `internal/domain/user/model/persona.go`：Persona struct（对齐 `user_profile/fields.yaml`）
  - 字段：id, userId, displayName, avatarUrl, bio, isPrimary, isActive, createdAt, updatedAt
- [ ] T10: [model] 创建 `internal/domain/user/model/user_setting.go`：UserSetting struct
- [ ] T11: [model] 创建 `internal/domain/user/model/user_work.go`：UserWork struct
- [ ] T12: [model] 创建 `internal/domain/user/model/user_life_item.go`：UserLifeItem struct
- [ ] T13: [repository] 创建 `internal/domain/user/repository/profile_repository.go`：ProfileRepository interface
  - FindByID, Create, Update, IncrementCounter(field, delta), FindByNickname
- [ ] T14: [repository] 创建 `internal/domain/user/repository/persona_repository.go`：PersonaRepository interface
  - FindByID, FindByUserID, Create, Update, Delete, DeactivateAll(userId), ActivateOne(personaId)
- [ ] T15: [repository] 创建 `internal/domain/user/repository/work_repository.go`：WorkRepository interface
- [ ] T16: [repository] 创建 `internal/domain/user/repository/life_item_repository.go`：LifeItemRepository interface
- [ ] T17: [event] 创建 `internal/domain/user/event/events.go`：UserProfileUpdated, PersonaCreated, PersonaActivated
- [ ] T18: [model] 创建 `internal/domain/follow/model/follow_edge.go`：FollowEdge struct（对齐 `follow_edge/fields.yaml`）
  - 字段：followerId, followeeId, source, createdAt
- [ ] T19: [repository] 创建 `internal/domain/follow/repository/follow_repository.go`：FollowRepository interface
  - Create, Delete, Exists, ListByFollower(cursor, limit), ListByFollowee(cursor, limit), CountByFollower, CountByFollowee
- [ ] T20: [event] 创建 `internal/domain/follow/event/events.go`：UserFollowed, UserUnfollowed
- [ ] T21: [model] 创建 `internal/domain/block/model/block_edge.go`：BlockEdge struct（对齐 `block_edge/fields.yaml`）
  - 字段：id, blockerId, blockedId, reason, createdAt
- [ ] T22: [repository] 创建 `internal/domain/block/repository/block_repository.go`：BlockRepository interface
  - Create, Delete, Exists, ListByBlocker(cursor, limit)
- [ ] T23: [event] 创建 `internal/domain/block/event/events.go`：UserBlocked, UserUnblocked
- [ ] T24: [codegen] 创建 `internal/generated/errors.go`：7 个 `Err*` sentinel + 7 个 `AppErrorFrom*` 函数（对齐 `errors.yaml`）

### S3: Infrastructure 层

- [ ] T25: [migration] 创建 `internal/infrastructure/migration/001_user_profiles.up.sql`
  - CREATE TABLE user_profiles (PK user_id, 全字段, idx_nickname, idx_phone, idx_status, gin_search(nickname,bio))
- [ ] T26: [migration] 创建 `internal/infrastructure/migration/002_personas.up.sql`
  - CREATE TABLE personas (PK id, idx_user_id, uq_primary(user_id,is_primary), uq_active(user_id,is_active))
- [ ] T27: [migration] 创建 `internal/infrastructure/migration/003_user_settings.up.sql`
- [ ] T28: [migration] 创建 `internal/infrastructure/migration/004_block_edges.up.sql`
  - CREATE TABLE block_edges (PK id, idx_blocker, idx_blocked, uq_block_edge(blocker_id,blocked_id))
- [ ] T29: [migration] 创建 `internal/infrastructure/migration/005_user_works.up.sql`
- [ ] T30: [migration] 创建 `internal/infrastructure/migration/006_user_life_items.up.sql`
- [ ] T31: [persistence] 创建 `internal/infrastructure/persistence/pg_profile_store.go`
  - 实现 ProfileRepository：FindByID, Create, Update, IncrementCounter, FindByNickname
  - 使用 `pgxpool.Pool`，参数化查询
- [ ] T32: [persistence] 创建 `internal/infrastructure/persistence/pg_persona_store.go`
  - 实现 PersonaRepository：CRUD + DeactivateAll + ActivateOne
  - DeactivateAll + ActivateOne 在同一事务内执行
- [ ] T33: [persistence] 创建 `internal/infrastructure/persistence/pg_setting_store.go`
- [ ] T34: [persistence] 创建 `internal/infrastructure/persistence/pg_block_store.go`
  - 实现 BlockRepository：Create(幂等 ON CONFLICT DO NOTHING), Delete, Exists, ListByBlocker
- [ ] T35: [persistence] 创建 `internal/infrastructure/persistence/pg_work_store.go`
- [ ] T36: [persistence] 创建 `internal/infrastructure/persistence/pg_life_item_store.go`
- [ ] T37: [persistence] 创建 `internal/infrastructure/persistence/mongo_follow_store.go`
  - 实现 FollowRepository：Create(幂等 unique index), Delete, Exists, ListByFollower/Followee(cursor+limit)
  - MongoDB ensureIndex 在 init 中执行
- [ ] T38: [cache] 创建 `internal/infrastructure/cache/profile_cache.go`
  - Get(userId) → JSON decode UserProfile，Set(userId, profile, 600s)，Del(userId)
  - GetFullSnapshot(userId) → profile + activePersna + setting 聚合缓存
- [ ] T39: [cache] 创建 `internal/infrastructure/cache/setting_cache.go`
  - Get/Set/Del，TTL=600s
- [ ] T40: [cache] 创建 `internal/infrastructure/cache/block_cache.go`
  - IsMember(blockerId, blockedId) → Redis SISMEMBER
  - Add(blockerId, blockedId) → Redis SADD
  - Remove(blockerId, blockedId) → Redis SREM
  - LoadFromDB(blockerId) → PG SELECT → Redis SADD batch → EXPIRE 3600s

### S4: Application 层

- [ ] T41: [service] 创建 `internal/application/profile_service.go`：ProfileService
  - GetProfile(userId)：cache hit → return；miss → PG join profile+persona+setting → cache set → return
  - UpdateProfile(userId, data)：PG update（乐观锁 profileVersion）→ cache del → 发布 UserProfileUpdated
  - GetStats(userId)：从 profile 提取 count 字段
- [ ] T42: [service] 创建 `internal/application/follow_service.go`：FollowService
  - Follow(followerId, followeeId)：Mongo insert → PG IncrementCounter(followee, followerCount, +1) → PG IncrementCounter(follower, followingCount, +1) → cache del both → 发布 UserFollowed
  - Unfollow：反向操作 → 发布 UserUnfollowed
  - ListFollowing/ListFollowers：Mongo cursor 分页
  - GetRelationship：Mongo Exists 双向查询 → {isFollowing, isFollowedBy, isMutual}
- [ ] T43: [service] 创建 `internal/application/block_service.go`：BlockService
  - Block(blockerId, blockedId)：PG insert → Redis SADD → 发布 UserBlocked
  - Unblock：PG delete → Redis SREM → 发布 UserUnblocked
  - CheckBlocked(blockerId, blockedId)：Redis SISMEMBER → miss → PG Exists → Redis LoadFromDB
  - ListBlocked(blockerId)：PG ListByBlocker
- [ ] T44: [service] 创建 `internal/application/persona_service.go`：PersonaService
  - ListPersonas(userId)：PG FindByUserID
  - CreatePersona(userId, data)：PG Create → 发布 PersonaCreated
  - UpdatePersona(personaId, data)：PG Update
  - DeletePersona(personaId)：校验 !isPrimary → PG Delete
  - ActivatePersona(personaId)：PG BeginTx → DeactivateAll(userId) → ActivateOne(personaId) → Commit → cache del → 发布 PersonaActivated
- [ ] T45: [service] 创建 `internal/application/work_service.go`：WorkService
  - ListUserWorks(userId, cursor, limit)
- [ ] T46: [service] 创建 `internal/application/life_item_service.go`：LifeItemService
  - ListUserLifeItems(userId, category, cursor, limit)

### S5: HTTP Adapter + main.go

- [ ] T47: [handler] 创建 `internal/adapters/http/user_handler.go`：UserHandler struct + NewUserHandler + Routes()
  - 注入 6 个 Service
  - `Routes()` → `http.NewServeMux()` 注册 20+ 路由
  - `/healthz`, `/livez`, `/startupz` 探针
- [ ] T48: [handler] 实现 20+ handle 方法：
  - handleGetProfile, handleUpdateProfile
  - handleFollow, handleUnfollow, handleListFollowing, handleListFollowers, handleGetRelationship
  - handleBlock, handleUnblock, handleListBlocked
  - handleListPersonas, handleCreatePersona, handleUpdatePersona, handleDeletePersona, handleActivatePersona
  - handleListUserWorks, handleListUserLifeItems, handleListUserLikes
  - handleGetNotificationSettings, handleUpdateNotificationSettings, handleGetPrivacySettings, handleUpdatePrivacySettings
  - 每个 handle：解析请求 → 调用 Service → writeJSON / WriteHTTPError
- [ ] T49: [main] 实现 `cmd/api/main.go`：标准启动流（KD10 设计）
  - resolveRuntimeIdentity → loadRuntimeConfig → validate → PG/Mongo/Redis init → migration → stores → caches → services → handler → server
- [ ] T50: [helper] 创建 `internal/adapters/http/response.go`：writeJSON、writeError、parseCursorLimit 等公共方法
- [ ] T51: [验证] `go build ./services/user-service/...` 编译通过

### S6: 云侧契约测试（L2）

- [ ] T52: [test] 创建 `tests/testmain_test.go`：TestMain 使用 `testinfra.NewSuite(WithPostgres, WithMongo, WithRedis)`
  - 初始化 stores → caches → services → handler → `testHandler`
  - 运行 migration
- [ ] T53: [test] 创建 `tests/helpers_test.go`：createProfile, createFollowEdge, createBlockEdge, cleanAll 辅助方法
- [ ] T54: [test] 创建 `tests/profile_crud_contract_test.go`：A1 验收
  - TestGetProfile_Success：创建 profile → GET → 断言全字段
  - TestGetProfile_NotFound：GET 不存在 userId → 404 + USER.USER.not_found
  - TestUpdateProfile_Success：PATCH → 字段更新 → profileVersion 递增
  - TestUpdateProfile_NicknameTaken：PATCH 已存在昵称 → 409 + USER.USER.nickname_taken
  - TestGetProfile_CacheHit：GET → GET（第二次 cache hit 验证）
  - TestGetProfile_CacheInvalidation：GET → PATCH → GET（缓存失效验证）
- [ ] T55: [test] 创建 `tests/follow_contract_test.go`：A2 验收
  - TestFollow_Success：POST → follow_edge 存在 → followerCount +1
  - TestFollow_Idempotent：重复 POST → 不报错 → count 不重复增加
  - TestUnfollow_Success：DELETE → follow_edge 不存在 → followerCount -1
  - TestListFollowing_CursorPagination：创建 N 条 → 分页查询
  - TestGetRelationship_Mutual：A follow B + B follow A → isMutual=true
- [ ] T56: [test] 创建 `tests/block_contract_test.go`：A3 验收
  - TestBlock_Success：POST → block_edge 存在 → Redis SISMEMBER=true
  - TestBlock_Idempotent：重复 POST → 不报错
  - TestUnblock_Success：DELETE → block_edge 不存在 → Redis SISMEMBER=false
  - TestCheckBlocked_CacheMiss：清 Redis → CheckBlocked → PG 回填 Redis
  - TestListBlocked：创建 N 条 → 分页查询
- [ ] T57: [test] 创建 `tests/persona_contract_test.go`：A4 验收
  - TestCreatePersona_Success
  - TestActivatePersona_Transaction：activate B → A.isActive=false, B.isActive=true
  - TestActivatePersona_Concurrent：并发 activate → 无唯一约束违反（一个成功一个等待）
  - TestDeletePersona_PrimaryForbidden：删除 isPrimary → 403
- [ ] T58: [test] 创建 `tests/cache_contract_test.go`：A5 验收
  - TestProfileCache_TTL：set → get(hit) → wait 600s+ → get(miss)（miniredis FastForward）
  - TestBlockCache_SetOperations：SADD → SISMEMBER(true) → SREM → SISMEMBER(false)
  - TestBlockCache_TTL：3600s（miniredis FastForward）
- [ ] T59: [test] 创建 `tests/error_contract_test.go`：A9 验收
  - 7 个错误码 × HTTP status × error code 字符串 × user_message
- [ ] T60: [test] 创建 `tests/work_life_contract_test.go`：
  - TestListUserWorks_Pagination
  - TestListUserLifeItems_CategoryFilter
- [ ] T61: [验证] `go test ./services/user-service/... -v -count=1` 全部通过

### S7: 部署流水线

- [ ] T62: [docker] 创建 `services/user-service/Dockerfile`：多阶段构建（KD12.1 设计）
- [ ] T63: [kustomize] 更新 `deploy/service/seed-box/kustomize/base/deployment.yaml`：新增 user-service sidecar 容器
- [ ] T64: [kustomize] 更新 `deploy/service/seed-box/kustomize/base/service.yaml`：新增 user-http 端口 18081
- [ ] T65: [kustomize] 更新 `deploy/service/seed-box/kustomize/overlays/integration/kustomization.yaml`：
  - images 增加 `seed-box/user-service`
  - env replacements 增加 user-service 容器
- [ ] T66: [kustomize] 更新 `deploy/service/seed-box/kustomize/overlays/prod/kustomization.yaml`：同 integration
- [ ] T67: [ci] 更新 `.github/workflows/service_pipeline.yml`：增加 user-service 构建 + 镜像 + 测试
- [ ] T68: [ci] 更新 `.github/workflows/delivery-gate.yml`：L2 门禁增加 user-service
- [ ] T69: [makefile] 更新 `quwoquan_service/Makefile`：build/test-contract 增加 user-service 路径
- [ ] T70: [config] 创建 `releases/config/user-service/v0.0.1.yaml`：初始配置版本
- [ ] T71: [secret] 文档化 Kubernetes Secret 创建步骤（user-service-postgres DSN）
- [ ] T72: [high-risk] 更新 `deploy/service/config-release/high_risk_fields.yaml`：增加 postgres.dsn/password
- [ ] T73: [验证] `kustomize build deploy/kustomization/aliyun-integration` 成功
- [ ] T74: [验证] `make gate` 通过（含 verify_deployment_domain_mapping + verify_deploy_kustomization）

### S8: 端侧 codegen 对齐

- [ ] T75: [codegen] 执行 `make verify-metadata && make codegen && make codegen-app`
  - 生成 user_profile_dto.g.dart, user_work_dto.g.dart, user_life_item_dto.g.dart, user_errors.g.dart
- [ ] T76: [替换] `UserWorkItem` → `UserWorkDto`（user_profile_mock_data.dart, profile_state_provider.dart）
- [ ] T77: [替换] `UserLifeItem` → `UserLifeItemDto`（user_profile_mock_data.dart, profile_state_provider.dart）
- [ ] T78: [错误码] 更新 `CloudErrorMapper` 注册 `UserErrorCode`
- [ ] T79: [remote] 更新 `RemoteUserProfileRepository` 错误处理：
  - `throw Exception(...)` → `throw CloudException(CloudErrorMapper.fromResponse(resp))`
- [ ] T80: [验证] `flutter analyze` 无新增错误
- [ ] T81: [验证] `flutter test test/cloud/user/` 已有测试通过

### S9: 端侧测试补充

- [ ] T82: [test-L1] 创建 `test/cloud/user/contract/user_dto_field_contract_test.dart`：
  - UserWorkDto 字段 × fields.yaml
  - UserLifeItemDto 字段 × fields.yaml
- [ ] T83: [test-L1] 创建 `test/cloud/user/contract/user_error_code_contract_test.dart`：
  - UserErrorCode 枚举 × errors.yaml 7 个错误码
  - 每个枚举的 .code 与 errors.yaml 的 code 字符串一致
  - 每个枚举的 .httpStatus 与 errors.yaml 的 http_status 一致
- [ ] T84: [test-L4] 创建 `test/ui/user/journeys/follow_unfollow_journey_test.dart`：
  - 进入作者主页 → 关注 → 粉丝数+1 → 取关 → 粉丝数-1
- [ ] T85: [test-L4] 创建 `test/ui/user/journeys/edit_profile_journey_test.dart`：
  - 我的主页 → 编辑资料 → 修改昵称 → 保存 → 返回验证
- [ ] T86: [test-L4] 创建 `test/ui/user/journeys/persona_management_journey_test.dart`：
  - 分身列表 → 创建 → 激活 → 返回验证
- [ ] T87: [test-L4] 创建 `test/ui/user/journeys/block_user_journey_test.dart`：
  - 作者主页 → 更多 → 屏蔽 → 确认 → 验证
- [ ] T88: [验证] `flutter test test/cloud/user/ test/ui/user/` 全部通过

### S10: 集成验证 + 验收

- [ ] T89: [集成] 本地 `docker compose up` → user-service 启动 → curl 验证 /healthz
- [ ] T90: [集成] 端侧切换 `AppDataSourceMode.remote` → 验证 getUserProfile 端云链路
- [ ] T91: [gate] 执行 `make gate-full` 全部通过
- [ ] T92: [验收] A1~A18 逐项验证（见 acceptance.yaml）
- [ ] T93: [部署] `make deploy-integration` → Pod Running + Ready → user-service 探针通过

## 搁置任务（带规划）

- [ ] **Auth/Login 流实现**（搁置原因：属于 `auth-profile-snapshot/auth-token-lifecycle` 节点范围；重启条件：该节点进入 dev 阶段）
- [ ] **seed-box 聚合二进制**（搁置原因：所有域 Handler 导出模式尚未统一；重启条件：content/circle/chat/integration Handler 均导出 `NewXxxHandler() http.Handler`；由 design.md E1 描述）
- [ ] **用户搜索 API**（搁置原因：属于 gateway/orchestrator 域；重启条件：gateway 服务就绪；GIN 索引已由本特性 T25 建立）
- [ ] **推荐引擎用户特征供给**（搁置原因：属于 recommendation 域；重启条件：recommendation-service 需要 UserFeatureVector 接口）
- [ ] **通知服务设备 token 推送**（搁置原因：属于 notification 域；重启条件：notification-service 进入 dev 阶段）

## 未来演进任务

- [ ] **E1: seed-box 聚合二进制**：创建 `cmd/seed-box/main.go` 聚合所有域 Handler，替代 sidecar 模式（design.md E1）
- [ ] **E2: 精确计数修复 Cron**：followerCount/followingCount 定期对比修复（design.md E2）
- [ ] **E3: 事件驱动缓存失效**：DomainEvent → MQ → 异步消费者失效缓存（design.md E3）
- [ ] **E4: 用户搜索**：gateway 调用 user-service search endpoint，利用 GIN trigram 索引（design.md E4）
- [ ] **E5: runtime/repository.Factory 自动化**：当 Factory 在 content-service 验证成功后，user-service 迁移到 Factory 驱动模式，减少手写 Store
