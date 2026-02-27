# 开发任务：redis-storage-elastic-infra（L3 聚合）

> L3 父节点不含直接可执行任务；任务拆解至两个 L4 子节点并行执行。

## 当前交付任务（L4 子节点汇总）

| 子节点 | 状态 | 关键交付物 |
|---|---|---|
| `redis-cluster-protocol` | ✅ 完成 | hash tag / ClusterAdapter / PipelineRead |
| `redis-service-multicloud-config` | ✅ 完成 | config schema / env override / keyspace 文档 |

## 作为配置发布化的前置条件

- [x] P1 Redis cluster/standalone 双模式能力已就绪
- [x] P2 多云配置字段（mode/addrs/tls/password）已标准化
- [ ] P3 在配置发布化流程中接入“Redis 高风险字段灰度门禁”联调（由 `risky-config-gray-release` Wave 2 完成）

## 搁置任务（带规划）

- **general-cache 场景 Redis 实体配置**：`redis.general` 配置分支已预留，但 content-service 的实体缓存/计数缓冲尚未实现；待 `counter-buffer-and-reaction-cache` 特性启动时激活。搁置原因：依赖实体缓存业务实现，优先级低于推荐热路径。

## 未来演进任务

- [ ] Bloom Filter 替换 exposed_set（超大 session > 10 万 ID 时，见 `redis-cluster-protocol` 演进任务）
- [ ] general-cache 场景 Redis 集群接入（待 counter-buffer / reaction-cache 特性启动）
- [ ] user-service / notification-service 接入 general Redis 场景（各服务独立配置）
- [ ] hot slot 监控与告警（接入 `observability-and-alerting` 节点）
