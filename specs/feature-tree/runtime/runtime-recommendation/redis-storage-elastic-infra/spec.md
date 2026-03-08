# L3 组件：redis-storage-elastic-infra（已归档 → 迁入 runtime-redis）

> **archived = true**
> 本节点已提升为平台级 L2 节点 `runtime/runtime-redis`。
> ClusterAdapter + hash tag → `runtime-redis/unified-client-and-router/scene-pool-and-prefix-routing`
> 多场景配置 + env override → `runtime-redis/config-and-keyspace-contract/multi-scene-config-schema`
> 已有实现保留不动，后续迭代在 `runtime-redis` 下进行。

## 功能定位（历史）

为 quwoquan 所有服务提供 **Redis 弹性基础设施公共能力**，解决用户规模增长时 Redis 容量不足的问题，同时支持阿里云 Tair / 火山引擎 VeCache 两大云厂商，代码零差异，仅配置差异。

本节点是 `runtime-recommendation` 下的**基础设施子节点**，与算法功能节点 `dual-channel-recommendation-engine` 平级，体现"推荐运行时 = 算法能力 + 存储基础设施"的职责边界。

## 职责边界

| 职责 | 归属 |
|------|------|
| Redis Cluster 客户端封装（ClusterAdapter） | 本节点 L4a |
| 跨 key 操作的 hash tag 协议约定 | 本节点 L4a |
| 多场景 Redis 配置 schema（rec/general 分离） | 本节点 L4b |
| 多云 env 变量覆盖注入规范 | 本节点 L4b |
| Redis 键空间文档（keyspace.yaml） | 本节点 L4b |
| 具体业务信号处理逻辑（HotPath / BufferedHotPath） | `redis-hot-path-and-rule-engine` |
| 具体推荐排序/召回逻辑 | `dual-channel-recommendation-engine` |
| 各云厂商帐号/网络接入配置 | 运维（不在本节点） |

## 子节点

| 节点 | 层级 | 说明 |
|------|------|------|
| `redis-cluster-protocol` | L4 | runtime 层：ClusterAdapter + hash tag 协议 + PipelineRead 扩展 |
| `redis-service-multicloud-config` | L4 | 配置层：多场景 config schema + env override + 部署兼容性方案 |

两个 L4 子节点可**并行开发**，无强依赖：L4a 是 Go 代码改动，L4b 是配置/文档改动。

## 适用范围与约束

**适用场景**：
- DAU ≥ 5 万、推荐热路径 Redis 内存 ≥ 8 GB 时需要 cluster 模式
- 部署在阿里云（使用 Tair 集群版）或火山引擎（使用 VeCache 集群版）
- 同一服务内有多个 Redis 场景（如推荐热路径 + 实体缓存）需要独立扩容时

**不适用场景**：
- 本地开发、单机部署（使用 standalone/memory 模式即可）
- 数据量极小时（< 1 GB），standalone 模式性能更好且无 slot 路由开销

**约束**：
- Redis Cluster 模式下，`MULTI/EXEC` 事务仅允许同 slot 的 key
- `MGET/MSET` 跨 slot 操作被禁止，必须通过 hash tag 保证同 slot
- 不修改业务逻辑层（HotPath 的信号处理语义不变）

## 验收标准概要

- A1：ClusterAdapter 通过 `RedisClient` + `RedisPipeliner` 接口契约测试
- A2：hash tag 后 pipeline 读（3 key → 1 RTT）在 cluster 模式下成立
- A3：standalone/cluster 模式通过配置切换，不改代码
- A4：阿里云 Tair / 火山引擎 VeCache 均可通过相同 env 变量部署
