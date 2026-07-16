# L2 规格：runtime-redis

## 1. 定位

`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制。
它不是业务数据访问层，不解释业务对象，也不根据 metadata 创建 Store、Reader 或缓存。

业务缓存属于对应服务的对象 Reader adapter：

```text
Object Query Facade
  -> named Reader port
  -> service internal/infrastructure/cache/<object>_reader
  -> runtime Redis client scene
```

具体 adapter 由服务 composition root 显式创建和注入。

## 2. 能力范围

### 2.1 Client

统一 client 覆盖：

- String：Get、Set、SetNX、Del、Incr、Expire。
- Hash：HSet、HGet、HGetAll、HIncrByFloat。
- Set：SAdd、SMembers、SIsMember、SRem。
- Pub/Sub：Publish、Subscribe。
- Pipeline：显式批处理。
- Bytes：仅供明确需要二进制值的 infrastructure adapter。

client 返回结构化 runtime failure，并传播 OperationContext、trace/request id 与 scene。

### 2.2 Scene

首发 scene：

- `rec`：推荐 HotPath、会话特征与高 QPS pipeline。
- `general`：对象缓存、计数、限流与低频状态。
- `realtime`：seq、dedup、presence 与 Pub/Sub fanout。

消费者必须通过 `Scene(name)` 显式选 scene。业务 Store/Reader 不接受“任意 key 自动选
scene”的隐式依赖；key prefix 与 TTL 仍由 metadata/keyspace 合同校验。

### 2.3 配置与拓扑

typed config 声明每个 scene 的 mode、address、TLS、pool 和 secret reference。
连接创建属于 `quwoquan_service/internal/platform/**`；公共 runtime 暴露稳定接口与
健康/指标合同。

standalone/cluster 是同一 scene adapter 的部署配置差异，不改变业务 Facade 或数据端口。

## 3. 对象缓存接入

每个缓存必须满足：

1. 对应 metadata `storage.yaml` 声明 cache role、key、TTL 与失效事件。
2. 服务定义业务命名 Reader，例如 `PostDetailReader`、`PersonaSnapshotReader`。
3. `internal/infrastructure/cache/**` 实现 read-through、negative cache 或精确失效。
4. composition root 显式把 cache Reader 注入 query Facade。
5. command 只提交 authoritative Store + outbox；缓存写入不参与聚合事务。
6. local contract 验证 key/TTL/失效，api integration 使用真实 Redis 验证一致性。

禁止：

- 跨对象缓存装饰器或动态 CRUD。
- 由 metadata 在运行期选择业务 Store/Reader 实现。
- application/domain 直接调用 Redis。
- 缓存冒充 authoritative store。
- 缓存失败静默吞错；必须按恢复策略降级并产生指标。

## 4. Composition root

```go
// 示意：具体类型由服务显式选择。
redisScenes := platform.MustOpenRedisScenes(cfg.Redis)

postDetailReader := cache.NewPostDetailReader(
    persistence.NewMongoPostDetailReader(mongo),
    redisScenes.Scene("general"),
    cfg.PostDetailCache,
)
postQuery := application.NewPostQueryFacade(postDetailReader)
```

禁止把对象名、存储类型或 cache role 交给公共工厂动态返回业务接口。

## 5. 四环境

- **alpha**：local contract 可注入显式 fake client；不得把 fake 结果记作集成证据。
- **beta**：使用真实 Redis 与 beta seed，验证恢复、TTL 和权限。
- **gamma**：拓扑与 prod 同构，执行真实并发、故障与恢复验证。
- **prod**：所有必需 scene 缺地址/secret/健康状态即 fail-fast；禁止 Memory、Noop、
  Mock 或自动 fallback。

## 6. 可观测与安全

每个 scene 至少输出：

- command latency histogram、error count、timeout count。
- pool active/idle/wait、connection failure、reconnect。
- cache hit/miss/negative-hit/eviction（由对象 adapter 带 object/operation 维度）。
- Pub/Sub lag、subscriber count、drop/reconnect。

日志不得记录 secret、PII 或完整 value；key 仅输出经策略允许的类型/哈希。

## 7. 测试证据

- `local_contract`：client 接口、scene 隔离、keyspace/TTL、对象 cache Reader
  conformance、结构化错误。
- `api_integration`：真实 standalone/cluster Redis、并发 SetNX/Incr、Pub/Sub、断连
  恢复、对象 cache hit/miss/失效。
- `user_acceptance`：仅当缓存策略影响用户旅程时验证无陈旧展示、错误恢复和 SLO。

## 8. 验收

1. runtime client 不依赖任何业务对象或服务 infrastructure。
2. 所有业务缓存都通过对象 named Reader adapter 接入。
3. service composition root 对每个 adapter 的选择清晰可审计。
4. beta/gamma/prod 无测试替身和自动 fallback。
5. scene 指标、健康、错误与 trace 可按 operation/object 聚合。
6. `make gate` 与对应 local_contract/api_integration 全绿。
