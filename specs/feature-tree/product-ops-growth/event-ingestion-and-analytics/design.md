# L2 Design：事件摄入与分析 (`event-ingestion-and-analytics`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“App 产品事件/异常、受限启动诊断、Provider 中立明细/聚合、Portal 查询和推荐反馈边界的端到端验收”需要 `analytics-metric-dictionary`、`event-schema-governance` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：App 产品事件/异常、受限启动诊断、Provider 中立明细/聚合、Portal 查询和推荐反馈边界的端到端验收。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`analytics-metric-dictionary`](./analytics-metric-dictionary/spec.md)：指标字典必须与 `event_catalog.yaml` 和各领域业务 metadata 同源；不得把 BehaviorSignal 伪装成 Ops 事件。
- [`event-schema-governance`](./event-schema-governance/spec.md)：`page_error_outcome`：统一阻塞错误面依次记录 `shown/recovery_started/recovered/recovery_failed`。

## 3. 端云与数据流

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 Gamma 使用 Elasticsearch Port 替身，Prod 使用真实 SLS
- 决策：Alpha/Beta 使用轻量本地日志替身验证协议。Gamma 绑定 `ext.obs.elasticsearch_local`，以本地 Elasticsearch 承载产品事件、启动诊断、运行日志和小时聚合四个逻辑分区。仅 Prod（含 gray rollout）绑定 `ext.obs.aliyun_sls` 并生成 Prod Remote receipt。
- 理由：Gamma 必须在 production Remote composition 和完整第一方拓扑中验证真实网络、持久化、索引、聚合与查询行为，又不能依赖真实第三方租户或凭据；Elasticsearch 能提供可重复的外部存储边界，Prod hosted 再独立验证 SLS 鉴权、限流、Scheduled SQL、告警和回滚。
- 被否决方案：Gamma 使用 PostgreSQL 冒充日志 Provider、继续使用 `local_log_sink` 文件占位、调用方直连 ES、ES/SLS 双写或失败 fallback，以及用 Gamma receipt 冒充 Prod SLS readiness。
- 约束与影响：`ObservabilityLogSinkPort`、事件目录、product-ops API、查询 Slice 和错误语义保持唯一；Provider 差异只存在于 infrastructure Adapter 与环境组合根。ES 与 SLS 必须复用同一字段投影、脱敏和批次身份规则。
- 关联要求：`REQ-001`
- 影响 Story：[`analytics-metric-dictionary`](./analytics-metric-dictionary/spec.md)、[`event-schema-governance`](./event-schema-governance/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- Alpha/Beta 验证轻量替身的 typed Port 契约。Gamma 创建并探测 ES 四分区及映射，执行写入、重复确认、summary/drilldown、页面体验、活跃会话和 RTC QoE 黑盒验收。Prod 创建 Project、四 Logstore、TTL、索引、RAM、Scheduled SQL 和告警。
- 安全：匿名 `/ops/events` 为 401、`/ops/recovery-failures` 只接收固定十字段并拒绝产品/身份字段、Portal 默认掩码。
- App、Portal 或业务服务直连 ES/SLS，以及任一 Provider 失败后自动切换到另一存储，会重新制造双轨和隐私面，属于拒绝项。
