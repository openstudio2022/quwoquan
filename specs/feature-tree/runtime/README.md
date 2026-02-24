# L1：runtime（统一运行时能力域）

- 特性路径前缀：`capability.runtime`
- 关联服务：各领域服务复用 runtime 子包
- L2 特性数：20 个（底座层 9 + 框架层 5 + 业务能力层 6）

## 特性树结构

### 底座层：已有 runtime 能力组件
| L2 | 状态 | 说明 |
|----|------|------|
| runtime-config | ✅ 核心完成 | 配置 Provider（env/map），secrets/动态刷新待补 |
| runtime-errors | ✅ 完成 | ErrorCode + AppError + 全模块注册 |
| runtime-observability | ✅ 95% | 日志/中间件/客户端工厂，OTEL exporter 待补 |
| runtime-http | ✅ 完成 | HTTP facade + wrapper 函数 |
| runtime-rpc | 🔲 接口 | RPCMetadata 类型定义，gRPC 实现待补 |
| runtime-messaging | ✅ 完成 | MessageEnvelope + MQ 中间件 |
| runtime-governance | 🔲 接口 | ResiliencePolicy 接口，熔断/限流待实现 |
| runtime-experiments | 🔲 接口 | Assignment/Resolver 接口，分桶实现待补 |
| runtime-learning | 🔲 接口 | Event/Scorecard 接口，反馈记录待补 |

### 框架层：元数据驱动的 DDD 领域框架
| L2 | 状态 | 说明 |
|----|------|------|
| runtime-registry | 🔲 待开发 | EntityRegistry + metadata v3 loader |
| runtime-repository | 🔲 待开发 | 多存储 Repository 框架 + PG/Mongo/Cache/Vector 适配器 |
| runtime-codegen | 🔲 待开发 | 元数据驱动代码生成 |
| runtime-interceptor | 🔲 待开发 | 读写拦截链（安全/校验/事件/指标） |
| runtime-testinfra | 🔲 待开发 | 契约测试基础设施（embedded-pg/testcontainers/miniredis） |

### 业务能力层：CQRS / 推荐 / 流式 / 上下文 / Skill
| L2 | 状态 | 说明 |
|----|------|------|
| runtime-eventstore | 🔲 待开发 | Event Store + 事件发布（P1） |
| runtime-projector | 🔲 待开发 | CQRS Projector + ReadModel（P1） |
| runtime-recommendation | ✅ 核心完成 | 双通道实时推荐引擎 — HotPath+Engine+7阶段管线+SessionCache+BufferedHotPath+ModelScorer+CascadeScorer+FeatureProvider+PreRanker；AB路由/metric待补 |
| runtime-streaming | 🔲 待开发 | SSE + Change Stream（P1） |
| runtime-context | 🔲 待开发 | 三层上下文模型（P2） |
| runtime-skill | 🔲 待开发 | Skill 框架（P2/P3） |
