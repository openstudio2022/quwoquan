# /config/app 高并发与可靠性

## 冷启动请求模型

App 冷启动会在首帧后触发远程配置刷新。接口必须按“少个性化、高缓存命中”的系统参数接口设计，不得依赖每请求实时计算完整控制面配置。

## 多级缓存

| 层级 | 内容 | TTL/失效 | 目标 |
|---|---|---|---|
| L0 App | disk LKG | `maxAgeSec`，过期仍可 stale serve | 无网可启动 |
| L1 service memory | active snapshot | release pointer 变更失效 | p99 稳定 |
| L2 shared cache | snapshot by `configHash` | release 失效 / TTL | 多实例一致 |
| L3 control plane | config package/release | 审批发布 | 真相源 |

## HTTP 缓存契约

- 响应头 `ETag = configHash`。
- 请求头 `If-None-Match` 命中时返回 `304`。
- `maxAgeSec` 给客户端 LKG 过期策略。
- `configHash` 不包含 `fetchedAt`，避免同配置重复 hash。

## 并发保护

- 发布时预计算快照，运行时只读快照。
- 单实例内对 miss 使用 singleflight。
- 控制面不可用时不阻塞 `/config/app`，继续返回最近快照或 embedded fallback。
- 高并发冷启动场景下，匿名/低个性化配置允许 CDN/边缘缓存。

## SLO

| 指标 | 目标 |
|---|---|
| availability | 99.95% |
| p95 latency | <= 80ms |
| p99 latency | <= 200ms |
| 5xx rate | <= 0.1% |
| stale fallback rate | <= 2% |
| config activation p95 | <= 5min |

## 降级

1. shared cache miss：读 service memory。
2. memory miss：读 embedded snapshot。
3. 客户端网络失败：读 disk LKG。
4. schema 不兼容：保留 active，拒绝 pending。
5. kill switch：最小 payload immediate 生效。
