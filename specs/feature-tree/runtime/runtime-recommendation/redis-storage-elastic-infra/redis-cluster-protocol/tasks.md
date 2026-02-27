# 开发任务：redis-cluster-protocol

## 当前交付任务

### runtime 层（hotpath.go）

- [x] **R1** 修改 `sessionKey()` 加 `{userId}` hash tag：`{userId}:sessionId`
  - 文件：`quwoquan_service/runtime/recommendation/hotpath.go`
  - 测试：`go test quwoquan_service/runtime/recommendation/...` ✅

### 基础设施层（redis_client.go）

- [x] **R2** 实现 `RedisClusterAdapter`（wraps `redis.ClusterClient`）
  - 实现所有 `RedisClient` 接口方法（Get/Set/Del/SAdd/SMembers/SIsMember/HIncrByFloat/HGetAll/Expire）
  - 文件：`quwoquan_service/services/content-service/internal/infrastructure/recommendation/redis_client.go`

- [x] **R3** 实现 `RedisClusterAdapter.PipelineRead`（`RedisPipeliner` 接口）
  - cluster pipeline 与 standalone pipeline 实现一致（hash tag 保证同 slot → 单 RTT）
  - 同文件

- [x] **R4** 新增 `DefaultClusterPoolConfig()`
  - PoolSize = CPU×30, MinIdleConns = CPU×8
  - 同文件

- [x] **R5** TLS 支持
  - `NewRedisClusterAdapter(addrs, password, enableTLS bool, pool)` 参数
  - `tls.VersionTLS12` 最低版本
  - 同文件

### 编译验证

- [x] **V1** `go build quwoquan_service/runtime/recommendation/...` PASS
- [x] **V2** `go build quwoquan_service/services/content-service/internal/infrastructure/recommendation/...` PASS
- [x] **V3** `go test quwoquan_service/runtime/recommendation/... -count=1` PASS

### 测试（已完成）

- [x] **T1** `TestSessionKey` — 验证 `sessionKey()` 返回 `{userId}:sessionId` 格式
  - 文件：`runtime/recommendation/engine_test.go`

- [x] **T2** `TestSessionKey_HashTagPresence` — 验证花括号位置和内容（只包 userId）
  - 文件：`runtime/recommendation/engine_test.go`

- [x] **T3** `TestHotPath_HashTagKeys` — 验证 HotPath 实际写入的键包含 hash tag
  - 文件：`runtime/recommendation/engine_test.go`

- [x] **T4** 编译期接口合规检查 `_ rtrec.RedisClient = (*RedisClusterAdapter)(nil)`
  - 文件：`infrastructure/recommendation/cluster_adapter_test.go`

- [x] **T5** `TestDefaultClusterPoolConfig_Values` / `TestDefaultClusterPoolConfig_LargerThanStandalone`
  - 文件：`infrastructure/recommendation/cluster_adapter_test.go`

## 搁置任务（带规划）

- **单元测试：RedisClusterAdapter 接口方法（live 行为）**：编译期接口合规已验证（T4）；live 方法行为测试（SAdd/SMembers/HIncrByFloat 等）需要 miniredis cluster 模式支持（`go-redis/miniredis` v2.23+ 起实验性支持 cluster），搁置原因：miniredis cluster 支持尚不稳定，待 v2.25 GA 后补充。

## 未来演进任务

- [ ] Bloom Filter adapter (`RedisBloomAdapter`) 替换超大 exposed_set
- [ ] 读副本延迟路由策略可配置（当前固定 `RouteByLatency`）
- [ ] Cluster 健康检查 / 自动 failover 监控探针
