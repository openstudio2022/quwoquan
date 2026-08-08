# L2 Business Capability：事件摄入与分析 (`event-ingestion-and-analytics`)

> 所属领域：[`product-ops-growth`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一采集 App 产品事件、异常和受限启动诊断，经同一 `ObservabilityLogSinkPort` 和 Elasticsearch 存储合同形成可查询明细与聚合，并将推荐反馈保持在唯一行为事实边界；Alpha、Beta、Gamma、Prod 不再按环境切换日志后端。

## 2. 范围与非目标

### In Scope

- 九字段事件目录、页面目录、App 加密 outbox、product-ops 日志端口单轨与 Portal 查询。
- 启动与运行时不可恢复异常的十字段匿名接收与 app_startup 产品投影隔离。
- BehaviorReporter 到 HotPath/投影/推荐/指标单出口。
- 四环境 Elasticsearch 共用写入、幂等、查询、脱敏、保留和错误合同；调用方不得感知环境或集群身份。

### Out of Scope

- ClickHouse、消息队列、对象存储归档、Assistant 学习并入 Ops。
- App、Portal 或领域服务直连 Elasticsearch，以及任一集群失败后回退到另一存储。

## 3. Journey / Scenario 贡献

- [`JNY-002 / SCN-005`](../../spec.md#scn-005)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：App 产品事件/异常、受限启动诊断、日志明细/聚合、Portal 查询和推荐反馈边界的端到端验收，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`analytics-metric-dictionary`](./analytics-metric-dictionary/spec.md)：指标字典必须与 `event_catalog.yaml` 和各领域业务 metadata 同源；不得把 BehaviorSignal 伪装成 Ops 事件。
- [`event-schema-governance`](./event-schema-governance/spec.md)：`page_error_outcome`：统一阻塞错误面依次记录 `shown/recovery_started/recovered/recovery_failed`。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 九字段目录与 App 可靠交付

- App/Go/Portal 生成目录一致，未知事件/字段/枚举本地和服务端均拒绝。
- networkClass 固定为 wifi/ethernet/5g/4g/mobile/other/none；VPN 叠加时上报底层 接入，单独 vpn/lte/nr/offline 均被服务端拒绝。
- session 状态机、页面映射、10s/50条/128KiB、单飞密封批次、重试/死信/actor 隔离可验证。
- app_anr_outcome、page_first_usable、page_error_outcome 全量进入同一 Reporter
- 原生 ANR 仅在产品 outbox accepted 后确认，入队失败保留重试
- Dart ANR 必须去重，TTI 必须收敛到成功、超时或失败终态，恢复动作记录对应 outcome。
- App 体验三项一级黄金指标的 source、SLO、freshness、低基数下钻与每业务最多三项规则 由机器目录和负例门禁共同锁定。

<a id="req-002"></a>
### REQ-002 Provider 中立写入幂等、聚合与查询门面

- 写入必须校验 canonical digest 与整批 payload；重复 ACK、超时后已写入确认和重复查询不得产生第二份事实。
- Alpha、Beta、Gamma、Prod 均绑定 `ext.obs.elasticsearch`，覆盖产品事件、启动诊断、运行日志与小时聚合四个逻辑分区，并通过同一 product-ops 查询门面证明写入、批次确认、明细、汇总、页面体验、活跃会话和 RTC QoE 语义。
- 四环境使用相同索引模板、ILM、rollup 代数、脱敏和错误合同；环境证据按各自 package、集群、身份与回滚回执隔离，任一环境的 ES receipt 不得替代另一环境。
- Portal 只经 product-ops 查询；任何环境都禁止调用方直连 Provider、双写、自动 fallback 或暴露后端身份。

<a id="req-003"></a>
### REQ-003 不可恢复异常与产品启动事件隔离

- `/ops/recovery-failures` 是唯一匿名恢复异常入口，只接收 `occurredAt`、`appVersion`、`buildNumber`、`platform`、`osVersion`、`deviceModel`、`errorSource`、`errorType`、`errorMessage`、`stackTrace` 十个脱敏字段；未知字段整条拒绝。
- 正常和缓慢启动在安全 Shell 后经普通 Reporter 写产品事件；不得生成启动尝试 ID、检查点、诊断编号或异常指纹，也不得向恢复异常接口复制产品/身份字段。
- 恢复异常继续使用同一 `ObservabilityLogSinkPort` 和环境日志 Provider；客户端本地加密队列只负责失败补报，不形成第二远端链路。

<a id="req-004"></a>
### REQ-004 推荐反馈单出口与一次生效

- ContentBehaviorTracker 和 ContentEngagementTracker 只调用 BehaviorReporter，BehaviorRepository 不调用 Ops。
- /content/behaviors 或专用命令只产生一次 BehaviorSignal，并经 BehaviorBatchReported 驱动推荐投影。
- VisitRecord 只持有访问计数与统计读模型，不发布第二路推荐事件；同一 actor 与 Idempotency-Key 的重放在 Mongo 聚合与回执同一事务内只计数一次。
- Portal behavior 卡读取 recommendation Prometheus 真实指标。

<a id="req-005"></a>
### REQ-005 统一页面访问旅程

- 统一页面访问旅程
- `logType` 仅允许 `event | error`；`eventType` 是唯一语义键，不存在 `eventName`。
- `networkClass` 仅允许 `wifi | ethernet | 5g | 4g | mobile | other | none`；不得上报 `vpn` 或未声明的自由文本值。
- 登录主体使用真实账号用户键做可逆 URL-safe 编码；游客使用安全持久化的 `guest_<ULID>`，禁止硬件标识。
- 导航 observer、底栏和全屏模态统一写 `AppPageContextStore`；无法解析页面上下文的异常使用 canonical unknown surface，不上传自由文本页面名。
- `Idempotency-Key` 必须等于 canonical 请求体 SHA-256；无逐事件 `eventId`。
- 禁止 `sessionId/userId/pageName/callStack` 等产品或身份字段。
- 队列满先删最旧普通采样事件；异常仅在普通事件清完后进入加密死信，禁止静默丢弃。
- 页面/事件、性能分位数/启动错误率、异常 TopN 三类聚合均不得包含 session/user。
- App 网络出口统一为 `BehaviorReporter`；Engagement tracker 只做计算并调用该端口。

## 6. 契约与依赖

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 九字段目录与 App 可靠交付

- GIVEN 执行“九字段目录与 App 可靠交付”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“九字段目录与 App 可靠交付”对应动作。
- THEN App/Go/Portal 生成目录一致，未知事件/字段/枚举本地和服务端均拒绝。
- THEN networkClass 固定为 wifi/ethernet/5g/4g/mobile/other/none；VPN 叠加时上报底层 接入，单独 vpn/lte/nr/offline 均被服务端拒绝。
- THEN session 状态机、页面映射、10s/50条/128KiB、单飞密封批次、重试/死信/actor 隔离可验证。
- THEN app_anr_outcome、page_first_usable、page_error_outcome 全量进入同一 Reporter
- AND 原生 ANR 仅在产品 outbox accepted 后确认，入队失败保留重试
- AND Dart ANR 不重复，TTI 收敛到成功、超时或失败终态，恢复动作记录对应 outcome。
- THEN App 体验三项一级黄金指标的 source、SLO、freshness、低基数下钻与每业务最多三项规则 由机器目录和负例门禁共同锁定。

<a id="sit-002"></a>
### SIT-002 Provider 中立写入幂等、聚合与查询门面

- GIVEN 执行“Provider 中立写入幂等、聚合与查询门面”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“Provider 中立写入幂等、聚合与查询门面”对应动作。
- THEN canonical digest 与整批 payload 通过校验；重复 ACK、超时后已写入确认和重复查询只返回原事实。
- THEN Alpha、Beta、Gamma、Prod 分别经 Elasticsearch 返回与公开合同一致的 raw、hourly、页面体验、活跃会话和 RTC QoE 结果，且无集群身份或敏感标识泄露。
- THEN 每个环境独立证明 ES 索引模板、ILM、rollup、鉴权、告警和回滚，且 receipt 不能跨环境替代。

<a id="sit-003"></a>
### SIT-003 不可恢复异常与产品启动事件隔离

- GIVEN 原生、Flutter 启动或运行时根级异常已经在客户端脱敏并保存。
- WHEN 客户端匿名提交恢复异常，或正常启动在安全 Shell 后提交产品事件。
- THEN `/ops/recovery-failures` 只接受规定十字段并写入同一日志端口，匿名 `/ops/events` 保持 401，正常/缓慢启动不进入恢复异常接口。
- THEN 上传失败、重复捕获或损坏队列不会产生第二条远端链路、用户阻塞或重复崩溃。

<a id="sit-004"></a>
### SIT-004 推荐反馈单出口与一次生效

- GIVEN 执行“推荐反馈单出口与一次生效”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“推荐反馈单出口与一次生效”对应动作。
- THEN ContentBehaviorTracker 和 ContentEngagementTracker 只调用 BehaviorReporter，BehaviorRepository 不调用 Ops。
- THEN /content/behaviors 或专用命令只产生一次 BehaviorSignal，并经 BehaviorBatchReported 驱动推荐投影。
- THEN VisitRecord 重放只返回首次回执且访问计数不增加，不产生 VisitRecorded 或其他并行推荐信号。
- THEN Portal behavior 卡读取 recommendation Prometheus 真实指标。

<a id="sit-005"></a>
### SIT-005 匿名恢复异常的跨副本来源准入

- GIVEN `/ops/recovery-failures` 由多个 product-ops-service 副本共同承载，且 api-edge 已配置共享来源限流策略。
- WHEN 同一匿名来源的请求跨副本或副本重启持续到达。
- THEN api-edge 以共享状态统一裁决来源配额，实际准入上限不随副本数或重启放大。
- AND product-ops-service 只校验载荷并写入日志端口，不维护第二套来源限流状态。
- AND local contract 与真实边界 receipt 分别证明共享裁决和多副本上限。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 产品遥测的四环境 Elasticsearch Provider 证据未闭合

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：四环境统一 Elasticsearch 的完整 Port、索引模板、ILM、鉴权、告警和回滚证据尚未共同闭合；真机恢复补报仅由 `OPEN-004` 跟踪。
- 完成判定：`SIT-002` 与四环境各自的 Provider receipt 均通过。

<a id="open-002"></a>
### OPEN-002 九字段目录与 App 可靠交付

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：App/Go/Portal 生成目录一致，未知事件/字段/枚举本地和服务端均拒绝。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 Provider 中立写入幂等、聚合与查询门面

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺真实环境验收证据；四环境 Elasticsearch 已完成单轨代码与契约收口，但同一候选四环境 Provider receipt 对 canonical digest、全批校验、重复 ACK、超时后已写入确认和查询去重的真实闭环尚未完成。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 不可恢复异常与产品启动事件隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 Prod 真实 Elasticsearch 接收、Android/iPhone 本地加密队列和真机补报证据的共同闭合；恢复异常必须严格保持十字段，并与产品事件和身份事实完全隔离。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 推荐反馈单出口与一次生效

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：ContentBehaviorTracker 和 ContentEngagementTracker 只调用 BehaviorReporter，BehaviorRepository 不调用 Ops。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 业务对象指标到告警和看板闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：关键业务对象缺指标、告警或看板绑定时，无法按对象判断错误、延迟和转化异常。
- 完成判定：关键对象 operation/event 的 metric、告警和 dashboard 可由 metadata 与运行证据双向定位。

<a id="open-007"></a>
### OPEN-007 多领域行为漏斗与推荐归因完整性

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺失端侧行为事件会使 Journey 漏斗和推荐反馈无法归因。
- 完成判定：AppRoot 关键 Journey 的行为事件、公共归因字段和推荐反馈均通过目录、代码与真实事件证据校验。

<a id="open-008"></a>
### OPEN-008 匿名恢复异常入口的来源限流是每副本进程内窗口，不构成权威准入

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前 `/ops/recovery-failures` 的匿名来源限流由 `product_ops.recovery_failure` 的 inbound HTTP adapter 在进程内以固定窗口计数承担，窗口状态只存在于单个副本的内存里。多副本部署时每个副本各自计一份窗口，同一来源的实际准入上限随副本数放大，因此该限流不是权威准入，只是单副本内的自保。
- 匿名入口的性质决定这不是纯运维问题：该端点不要求身份，来源键只能取自连接层地址，一旦准入上限失真，异常上报量就可能超出日志端口的容量预期并挤占正常产品事件的写入。
- 副本重启会丢失全部窗口状态，因此同一来源可以通过触发或等待实例替换重新取得完整配额，限流结论不具有跨副本或跨重启的可复现性。
- 长期修向是把匿名来源限流上收到 api-edge 的准入策略，由已拥有共享限流状态的边缘层按来源统一裁决，`product_ops.recovery_failure` 的 inbound adapter 退回为只做载荷校验。在上收完成前不得把进程内窗口描述为准入保证，也不得据它放宽日志端口的容量预算。
- 完成判定：`SIT-005` 通过，匿名恢复异常入口的来源准入由 api-edge 侧的共享限流状态裁决，多副本下同一来源的实际准入上限与声明上限一致，并有直接绑定该行为的 local_contract 与真实边界收据。
- 依赖：api-edge `edge_security/rate_limit_bucket` 的共享限流状态与匿名来源键定义。
