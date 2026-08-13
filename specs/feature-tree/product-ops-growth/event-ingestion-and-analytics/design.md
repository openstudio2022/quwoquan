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
### DEC-001 四环境使用同一 Elasticsearch 日志存储合同
- 决策：Alpha、Beta、Gamma、Prod 均绑定 `ext.obs.elasticsearch`，以环境隔离的 Elasticsearch 集群承载产品事件、启动诊断、运行日志和小时聚合四个逻辑分区；环境组合根只提供集群 endpoint 与受保护认证材料，不选择第二种日志后端。
- 理由：统一真实网络、持久化、索引、聚合、查询、告警和回滚语义，避免 Alpha/Beta 的 PostgreSQL 替身与 Prod SLS 形成无法由同一候选晋级的三轨实现。
- 被否决方案：任一环境使用 PostgreSQL、SLS、文件或内存冒充日志 Provider，调用方直连 ES，多后端双写、失败 fallback，以及用一个环境的 receipt 冒充另一个环境 readiness。
- 约束与影响：`ObservabilityLogSinkPort`、事件目录、product-ops API、查询 Slice、错误语义、索引模板、ILM 与 rollup 代数保持唯一；环境差异只允许 endpoint、认证、容量与保留执行资源不同。
- 关联要求：`REQ-001`
- 影响 Story：[`analytics-metric-dictionary`](./analytics-metric-dictionary/spec.md)、[`event-schema-governance`](./event-schema-governance/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 跨轨统一漏斗只做读侧 actorHash 天级合并，不建数仓
- 决策：「曝光 → 消费 → 发布 → 再消费」漏斗横跨产品遥测轨（ES，身份键 sessionId 可派生 actorHash）与行为归因轨（Mongo/Redis 流，身份键 personaId/feedRequestId）。统一视图只在读侧合并：join 键固定为 actorHash（sha256(actorId)，与 growth 投影同派生域）；产品轨由 `GetGrowthOverview` 扩展天级去重段计数，行为轨由 content-service 归因端点扩展 actor 去重数，product-ops 聚合层读侧合并、不复制事实。漏斗每段标注 sourceTrack 与 freshness，缺任一轨显式 unavailable，禁止跨轨数值换算。
- 理由：两轨物理隔离是既定架构（BehaviorSignal 不得伪装 Ops 事件）；当前规模下天级去重计数由既有 ES/Mongo 聚合承载即可，提前引入数仓（ClickHouse/BigQuery）是无收益的第二存储面。
- 被否决方案：以下路线均被否决。
  - 引入独立分析数仓做明细 join。
  - 用户级明细跨轨关联（隐私与基数不允许）。
  - 在任一轨复制另一轨事实形成第二真相源。
  - 分钟级实时跨轨漏斗。
- 约束与影响：先契约（product-ops `GetGrowthOverview` response_fields 扩展与 content 归因端点扩展）再 verify/codegen 再实现；规模超出单机聚合能力时重评数仓，禁止提前建设。
- 关联要求：[`analytics-metric-dictionary REQ-003`](./analytics-metric-dictionary/spec.md#req-003)
- 影响 Story：[`analytics-metric-dictionary`](./analytics-metric-dictionary/spec.md)
- 关联验收：`SIT-002`

<a id="dec-003"></a>
### DEC-003 rollup 写侧与 ES 告警评估共用一条契约驱动执行链
- 决策：`rollups.yaml` 经 codegen 生成 `RollupCatalog`，ES 写侧由单一数据驱动执行器按 catalog 遍历产出全部 rowKind 聚合行，批修复读回直接消费 raw 文档全字段。`product_telemetry_alerts.yaml` 每条告警用 `fields` 显式声明 condition 字段的派生，rollup 的 filter/where 与告警的 condition/where 共用同一最小条件语言。评估循环内建于 product-ops：聚合行读回、内存字段派生、条件求值、Alertmanager v2 推送，firing 按评估间隔三倍续期自动 resolve，由 `telemetry_alerts.policy_path` 与 `alertmanager_url` 配置启用。control_plane 告警字段由评估器自产：派生失败计数、聚合 generatedThrough 新鲜度水位、ES ILM 实际保留天数。seek unsettled 采用 settle 直方图超 2000ms 尾部占比的代理口径；rtc 比率类告警的分子由字段级 where 承载，顶层 filter 只做公共排除，保证分子分母口径分离。
- 理由：聚合定义、告警字段与数据行形态必须单源，显式派生声明使门禁能静态闭合校验——condition 字段包含于 fields、fields 输入包含于 rowKind measures。
- 被否决方案：外置独立告警评估服务、ES watcher/transform 承载、condition 字段与 measures 隐式同名映射。
- 约束与影响：先改 `rollups.yaml` 与告警契约，再 codegen，再实现，禁止按 rowKind 手写第二套聚合分支；新增告警字段必须先有 rowKind measure 或 evaluator 白名单登记，`verify_ops_event_schema_completeness.py` 的告警字段闭合段命中即 BLOCK。
- 关联验收：`SIT-002`
- 遗留：四环境启用收据由 [`OPEN-011`](./spec.md#open-011) 跟踪。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 四环境分别创建并探测 ES 四分区及映射，执行写入、重复确认、summary/drilldown、页面体验、活跃会话和 RTC QoE 黑盒验收；Prod 额外证明正式认证、容量、快照、告警与回滚。
- 安全：匿名 `/ops/events` 为 401、`/ops/recovery-failures` 只接收固定十字段并拒绝产品/身份字段、Portal 默认掩码。
- App、Portal 或业务服务直连 ES，以及任一集群失败后自动切换到未声明存储，会重新制造双轨和隐私面，属于拒绝项。
