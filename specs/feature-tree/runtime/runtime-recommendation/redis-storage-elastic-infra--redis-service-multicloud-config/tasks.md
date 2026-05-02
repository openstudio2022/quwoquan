# 开发任务：redis-service-multicloud-config

## 当前交付任务

### config schema（content-service）

- [x] **C1** 扩展 `configs/config.yaml`：`redis.rec` + `redis.general` 双场景结构
  - 含 mode / addr / addrs / password / db / tls / pool 字段
  - 含详细注释（阿里云/火山引擎部署示例）
  - 文件：`quwoquan_service/services/content-service/configs/config.yaml`

- [x] **C2** 定义 `redisSceneCfg` Go struct（对应 YAML schema）
  - 文件：`quwoquan_service/services/content-service/cmd/api/main.go`

### env 覆盖与 buildRedisClient（content-service）

- [x] **C3** 实现 `applyEnvOverrides()` + `applyRedisSceneEnv(prefix, cfg)`
  - 覆盖 `CONTENT_REDIS_REC_*` 和 `CONTENT_REDIS_GENERAL_*`
  - 向后兼容过往版本 `CONTENT_REDIS_ADDR / PASSWORD / DB`
  - 文件：`cmd/api/main.go`

- [x] **C4** 重构 `buildRedisClient` → `buildRecRedisClient`
  - `mode=cluster` → `NewRedisClusterAdapter`
  - `mode=standalone` → `NewRedisClientAdapterWithPool`
  - `addr/addrs 均空` → `NewMemoryRedis`（fallback）
  - 同文件

- [x] **C5** 实现 `resolvePoolConfig(redisSceneCfg) RedisPoolConfig`
  - cluster 默认 `DefaultClusterPoolConfig()`，standalone 默认 `DefaultRedisPoolConfig()`
  - 零值字段自动填充
  - 同文件

### 键空间文档

- [x] **K1** 更新 `redis_keyspace.yaml`
  - 所有 rec:* key 加 hash_tag: userId 字段
  - 每条 key pattern 加 redis_scene: rec/general 字段
  - 补充多云兼容性说明和场景分离原则
  - 文件：`quwoquan_service/contracts/metadata/_shared/redis_keyspace.yaml`

### 编译验证

- [x] **V1** `go vet quwoquan_service/services/content-service/cmd/api` PASS
- [x] `go build quwoquan_service/services/content-service/internal/infrastructure/recommendation/...` PASS

### 测试（已完成）

- [x] **T1** `TestApplyRedisSceneEnv_*` (6 个 case) — 验证 env 覆盖逻辑
  - 文件：`services/content-service/cmd/api/main_test.go`

- [x] **T2** `TestApplyEnvOverrides_*` (5 个 case) — 验证新旧 env 变量覆盖顺序和向后兼容
  - 文件：`services/content-service/cmd/api/main_test.go`

- [x] **T3** `TestResolvePoolConfig_*` (4 个 case) — 验证零值自动填充 + 显式配置优先
  - 文件：`services/content-service/cmd/api/main_test.go`

## 搁置任务（带规划）

- **general 场景 buildGeneralRedisClient**：`redis.general` 配置分支代码已预留在 config struct 中，但 `buildGeneralRedisClient` 函数尚未实现（因为 content-service 暂无 general 缓存用例）。搁置原因：无使用方，不提前实现。触发条件：counter-buffer 或 entity-cache 特性启动。

- **redisSceneCfg 提取到 runtime/config**：当前在 main.go 内，第 2 个服务需要 Redis 时提取共享。

## 未来演进任务

- [ ] general 场景接线（counter-buffer / entity-cache 特性）
- [ ] `redisSceneCfg` 提取到 `quwoquan_service/runtime/config`
- [ ] 配置中心对接（K8s ConfigMap / ACM / 火山引擎 Config）
