# L2 Business Capability：运行时 Redis (`runtime-redis`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制。

## 2. 范围与非目标

### In Scope

- 跨服务 Redis client、scene 连接池、健康检查和指标。
- Redis Cluster hash tag、pipeline 和同 slot 原子操作约束。
- alpha/beta/gamma/prod 的配置差异与 fail-fast 行为。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-006 / SCN-014`](../../spec.md#scn-014)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`redis-scene-client`](./redis-scene-client/spec.md)：同一 scene 在同一环境必须解析到唯一连接与 prefix；prod 必需 scene 缺地址、凭据或健康状态时必须拒绝启动。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime redis 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 缓存失败不得静默吞错；必须按恢复策略降级并产生指标

- 缓存失败不得静默吞错；必须按恢复策略降级并产生指标。
- Redis Cluster 的事务和批量 key 操作必须处于同一 slot；调用方用稳定 hash tag 保证共址。
- `PipelineRead` 的同批 key 必须共享 hash tag，禁止以跨 slot fallback 掩盖调用错误。
- local contract 可注入显式 fake client，但不得把 fake 结果记作集成证据。
- beta/gamma/prod 的必需 scene 缺地址、secret 或健康状态时必须 fail-fast；禁止 Memory/Noop fallback。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime redis 能力 SIT

- GIVEN 执行“runtime redis 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime redis 能力”对应动作。
- THEN 直属 Story 共同交付“`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制”，失败终态可区分且不产生伪成功事实。
- AND Cluster 模式的批量读写遵循同 slot 约束，必需 scene 配置缺失时进程拒绝就绪。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime redis 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
