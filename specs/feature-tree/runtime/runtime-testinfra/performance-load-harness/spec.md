# L3 Story：契约驱动压测与性能证据 (`performance-load-harness`)

> 所属能力：[`runtime-testinfra`](../spec.md)

> Journey / Scenario：横切工程能力，不直接拥有 AppRoot Scenario。

> 设计引用：[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为开发、测试或运维角色，我希望按 operation 契约生成受控负载并出具与 SLO 声明对照的性能证据，从而让服务与旅程的延迟劣化在放量前被门禁发现，而不是靠线上告警回溯。

## 2. 范围与非目标

### In Scope

- 契约驱动的负载生成、阶梯并发、p50/p95/p99 与错误率证据。
- `stackctl loadtest` 编排入口、SLO 阈值对照与 pass/fail 判定。
- 性能证据在 `.qwq_output` 的幂等落盘与 CaseResult 关联。

### Out of Scope

- 单个业务对象的具体预算数值（由所属节点 spec 与 operation 契约拥有）。
- Prod 容量规划与放量决策。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 负载只由契约与公开 operation 生成

- 负载生成只消费 generated client 与所属领域公开 operation；禁止裸 HTTP、自造 wire payload 或测试专用 bulk API。
- 环境压测数据前置只经强类型 capability request 准备；Prod 在首条压测 mutation 前拒绝。私有隔离存储专项的离线制品边界见 [REQ-003](#req-003)，不得进入本环境准备轨。
- 负载画像（并发阶梯、持续时长、目标 operation 集）是显式声明的输入，同一画像对同一候选可重复执行。

<a id="req-002"></a>
### REQ-002 性能证据与 SLO 对照且幂等可重建

- 每次执行产出 p50/p95/p99 延迟、错误率与吞吐证据，写入 `.qwq_output`，删除后可凭同一候选与画像重建。
- 证据必须与 operation 契约 `slo.*` 声明或 `slo_thresholds` 阈值对照，输出可区分的 pass/fail 判定；无阈值声明的 operation 不得输出伪判定。
- benchmark-only policy 的结果只作性能取证，不得计入环境正式绿色回执。
- 前置失败或提前退出的 run 与完整 run 分开表达，不进入性能基线。

<a id="req-003"></a>
### REQ-003 三层证据与数据来源分开，不以离线容量代替环境闭环

- `local_contract` 只证明可控时钟、状态机、预算计算和 typed port 行为；`api_integration` 使用真实引擎、production application/Remote/自动 consumer 证明提交、收敛与成本；`user_acceptance` 使用同候选真实 App、设备操作和受管读回证明用户可见结果。性能、迁移和故障环境证据不另造第四层，不互相抵扣。
- 每份结果绑定 exact candidate/source、合同、配置、资源、引擎/toolchain、数据来源与实际基数、负载及故障范围，并记录执行数、失败、skip 和提前退出；源码、编译、运行健康、容量与用户旅程分别判定。
- 千万级合成数据只能在获授权的 persistence adapter/迁移/容量专项私有隔离目标中作为离线 storage benchmark 使用，制品绑定 manifest/digest。它不属于环境 capability 准备，不赋予业务事实资格；不得直写 Prod、共享环境、在线投影或给 UAT 预填结果。
- Alpha/Beta/Gamma 端到端数据仍由强类型请求经领域公开 command/event 建立，内容与 Creator 只引用合格 immutable release；同数据数量的 benchmark 与真实环境证据分别报告。没有合法环境供给或缺设备就保持对应层阻断。

<a id="req-004"></a>
### REQ-004 大度数与热点负载必须显式冻结，不能只提高系统上限

- 关注容量画像分别覆盖 1000/10000 单主体出边与 10000/1000000/10000000 单目标入边；空态、临界限额、超额拒绝、多热点、冷热混合、高 churn 及热门 Post/Comment 互动成员分档同时声明。
- 负载必须冻结批准资源、总数据量、热点比例、业务 baseline/peak/spike、读写混合、持续时长、正常余量与恢复预算；没有生产峰值与资源批准可输出安全容量测量曲线，但不能宣称满足未知业务峰值。
- 开环阶梯避免 coordinated omission，覆盖持续稳态、峰值、突发、长时间 churn/soak、冷启动/全失效、无结果搜索、深 seek、同 Pair 竞争、不同 source 追同热点及慢 consumer；记录 1→2→4 实例曲线但不预设线性扩容。
- 系统关注人数上限不自动扩大数据库 batch、扫描、单页字节、deadline 或内存预算；不能任意截断作者列表冒充完整 following 流，也不能用同步千万粉丝 fanout 获得测量绿灯。

<a id="req-005"></a>
### REQ-005 所有 attempt、实际扫描与端到端新鲜度同源计量

- 记录全部 attempt 的耗时与结果，包括成功、合法 no-op、quota/权限拒绝、过载拒绝、服务错误、超时及重试；同时记录单用户意图的总耗时、durable 确认率、完整互动附着率与最终收敛率。业务拒绝可分型但不得从负载分母消失，内容成功而互动不可用不算完整互动成功。
- 实际查询成本至少包含每页往返、真实执行计划及 keys/docs examined、扫描行、缓冲/IO、锁等待、复制延迟；同步记录 CPU/内存/GC、连接池、缓存字节/命中/回源放大、队列最老年龄和消费者处理率。返回 limit 不代替 scan bound，命中测试必须证明少了权威读取，不以两次成功响应自证。
- 提交到统计、推荐特征及前台可见呈现均以同一事实关联的端到端分布测量；P99 不能由投影、服务 cache 与 App 各自 P99 相加得到。cacheAge 与 projectionLag 分开，驻留可见区刷新总 QPS、重试放大与冷恢复成本计入峰值，离线/后台另列。
- 正确性 oracle 在负载全过程核对已确认事实、身份、名额、成员贡献、独立来源版本、投影及实际 scorer 输入；结束时总数碰巧相同不能抹去过程中丢写、串主体、重复贡献或越权。
- 业务延迟、确认率与新鲜度数字只读本节契约引用指向的 owning Story 与 operation SLO；阈值缺失时报告阻断而非在 harness 另订较低标准。

<a id="req-006"></a>
### REQ-006 HA 只在指定故障模型下裁定 RPO、RTO 与恢复成本

- 每项演练必须先声明授权环境、故障域、故障对象、最大同时失效范围、复制/持久确认前提、旧主 fencing、操作及自动恢复边界，再分别声明数据 RPO、业务写恢复 RTO、缓存冷恢复和 consumer 追赶预算；不得从事务、majority 配置或多副本数量直接推断达标。
- 已确认写的丢失判定须逐条关联 authority 与 receipt，并覆盖恢复所需 outbox、quota 和不可逆抑制事实；未知命令不伪造终态。单节点故障的目标不得外推地域灾难，备份恢复单独绑定一致恢复点与 RPO/RTO。
- PG 安全主库失效与旧主隔离、Mongo 失多数派及恢复、服务滚动重启、Redis 缓存丢失与落后副本旧 generation 提升均需对应真实故障证据；安全/读己之写始终读 authority，普通 cache 按源绝对期限承诺 bounded stale，不以清库替代旧代际复活反例。
- 毒事件、租约接管与恢复积压分区隔离；连续已应用水位不能跳过毒事件，失租 worker 不能推进新水位，清理有预算且可重启续跑；恢复处理率须足以排空积压，不以吞事件换 RTO。
- 故障实施仍受 [fault-injection-harness REQ-001](../fault-injection-harness/spec.md#req-001) 的现役闭集与受管入口约束。未支持的数据库切主/备份恢复 profile、未批准资源或不安全注入必须在执行前阻断，不能凭本 Story 获得 kill、切主或扩展生产故障面的授权。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)；跨层证据、离线/环境边界与故障测量设计：[L2 DEC-006](../design.md#dec-006)。
- 关注限额与可见确认：[follow-relationship REQ-010](../../../user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#req-010)、[REQ-011](../../../user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#req-011)；分页、统计与缓存：[social-graph-read REQ-005](../../../user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#req-005)、[REQ-006](../../../user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#req-006)、[REQ-007](../../../user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#req-007)。
- 互动统计和新鲜度：[reaction-state-counter REQ-006](../../../discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#req-006)、[REQ-007](../../../discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#req-007)；推荐特征：[runtime-recommendation REQ-004](../../runtime-recommendation/spec.md#req-004)；Feed 资源和 SLO：[streaming-feed-performance](../../../discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md)。
- 业务具体阈值/负载只读取 owning operation、SLO 与显式配置：User `contracts/relationship/persona_relationship/`、Content `contracts/content/content_reaction/` 及 `quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`。behavior ingest 流量不能替代关注/点赞命令容量。
- HA 故障域与备份恢复要求引用 [system-topology-and-networking](../../system-topology-and-networking/spec.md) 和 [commercial-readiness-risk-closure SIT-005](../../../platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-005)；故障 profile/结果 shape 只由 harness owner contract 定义。业务 RPO/RTO 数字未冻结时保持 [OPEN-002](#open-002)，不在本 Story 复制或代批准。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 契约驱动压测出具 SLO 对照证据

- GIVEN alpha/beta/gamma 候选环境健康，目标 operation 具有有效 `slo.*` 或阈值声明。
- WHEN 参与者以显式负载画像执行 `stackctl loadtest`。
- THEN 产出 p50/p95/p99、错误率与吞吐证据并与阈值对照给出 pass/fail，证据可从 `.qwq_output` 幂等重建。
- AND 超阈值时判定为失败且不写入伪成功事实；Prod 目标在首条压测 mutation 前被拒绝。

<a id="gwt-002"></a>
### GWT-002 大度数负载包含失败分母、实际成本与端到端分布

- GIVEN 同候选拥有批准的资源/负载画像及 1000/10000 出边、千万单目标入边容量档，owning Story 与 operation 阈值可解析。
- WHEN 执行开环稳态、峰值、突发、churn、冷缓存、深页/无结果搜索和扩副本场景。
- THEN 全 attempt 含错误、拒绝、超时与重试进入报表，单意图确认/完整附着另列；真实扫描、锁/副本/缓存/连接/队列成本与正确性 oracle 可核验。
- AND 同事实提交到可见统计/推荐/scorer 的端到端分布直接对照 owning SLO，不相加分项 P99；未批准峰值、资源不够或扫描越界时不得标容量通过。
- AND 真实前台呈现由所属业务旅程原位证明，不被服务端分位数代替。

<a id="gwt-003"></a>
### GWT-003 指定故障范围下核对持久确认与恢复预算

- GIVEN 已批准故障模型、资源、复制/确认策略及 owning RPO/RTO，且注入属于受管故障闭集并已证明可恢复。
- WHEN 在负载中触发对应 authority、缓存或 consumer 故障并恢复，包括旧主隔离、丧失多数派、Redis 旧代际提升或毒事件/租约接管反例。
- THEN 故障影响范围与模型一致，逐条 confirmed 事实/receipt 及恢复依赖无超出 RPO 的丢失；未知命令不伪终结，权限与读己之写不降到普通缓存。
- AND 业务写、缓存冷恢复、积压追赶分别对照预算，旧缓存不续源期限、失租 worker 不推进 checkpoint、毒事件不被跳过，恢复过程与失败均有原始证据。
- AND 未支持 profile、未授权切主或不具备可验证 RPO/RTO 时执行前阻断；地域灾难与备份恢复另列，单节点通过不外推。
- AND 用户感知终态继续由所属业务旅程原位取证，不在 harness 另造旅程。

<a id="gwt-004"></a>
### GWT-004 离线存储基准不能冒充环境或真机证据

- GIVEN 同一变更分别有私有隔离 storage benchmark、真实环境公开 command/event 结果与 App 局部测试。
- WHEN 汇总容量与关注/点赞旅程准出证据。
- THEN benchmark 只证明其适配器/引擎与数据画像，无法生成环境绿色回执；环境数据仍有合法准备和读回，缺真实链、物理设备、授权或任一 required 证据即保持对应层阻断。
- AND Prod/共享数据库 seed、直接投影预填及跨 case 可变事实复用在 mutation 前拒绝；历史 run、skip 或小数据功能通过不能替代本候选目标基数。
- AND 实际数据来源与写前拒绝可核验，所属旅程原位提供前台证据，不在 harness 创建替代旅程。

## 6. 依赖

- 前置要求：[`runtime-testinfra`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-005](../design.md#dec-005)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 压测 harness 实现与首批 SLO 对照证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma release 候选上的正式取证、鉴权态与参数化 path
  operation 的覆盖扩展，以及把压测证据纳入发布准出的接线。loadgen 执行器、
  `stackctl loadtest` 编排与首批真实环境证据已落地——alpha-local 上
  GetFeed/GetAppConfig/ListCircles/SearchHomepages 四个公开只读 operation
  的 p95 与可用率全部通过契约 SLO 对照，证据于
  `.qwq_output/env/alpha/runs/*-loadtest-alpha-local/`。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 大度数容量、完整分母及指定故障模型尚无准出证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[REQ-003](./spec.md#req-003)、[REQ-004](./spec.md#req-004)、[REQ-005](./spec.md#req-005)、[REQ-006](./spec.md#req-006) 尚缺当前候选的千/万出边、千万入边与热点真实负载、全 attempt/实际扫描、新鲜度和 HA 组合证据；专属业务峰值、批准资源及指定故障范围的 RPO/RTO 还须 owning service/运行 owner 冻结。历史公开只读 operation 测量不能替代关注/Reaction 写容量或恢复承诺。
- 完成判定：[GWT-002](./spec.md#gwt-002)、[GWT-003](./spec.md#gwt-003)、[GWT-004](./spec.md#gwt-004) 的真实测试直接绑定完整 `spec_ref`：`local_contract` 锁定分母、预算、判定、状态/报告分类与准入反例；`api_integration`/真实负载与环境演练证明实际成本、全过程正确性、真实复制与恢复，以及数据来源和拒绝发生在写前；真实前台呈现由相应业务 `user_acceptance` 绑定且由所属旅程原位提供，不被服务端分位数代替，也不在 harness 创建替代旅程。负载和阈值先获 owning source 确认，再提供同候选真实引擎、自动 consumer、全过程正确性与经授权故障恢复证据，离线 benchmark/环境 E2E/业务 user_acceptance 分开裁定。缺资源、未执行、skip、未授权或 unsupported profile 均不关闭。
- 依赖：[fault-injection-harness OPEN-001](../fault-injection-harness/spec.md#open-001) 的受管故障执行与恢复能力、[system-topology-and-networking](../../system-topology-and-networking/spec.md) 的故障域，以及 [commercial-readiness-risk-closure OPEN-007](../../../platform-ops-governance/commercial-readiness-risk-closure/spec.md#open-007) 的备份恢复。未有正式数据库切主/旧代际提升/恢复 profile 时保持阻断，不允许本项成为手工故障入口或生产 seed 授权。
