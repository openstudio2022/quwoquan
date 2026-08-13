# L2 Business Capability：可观测性与告警 (`observability-and-alerting`)

> 所属领域：[`platform-ops-governance`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路。

## 2. 范围与非目标

### In Scope

- runtime/controlplane 真实指标 dashboard。
- userMessage override hit/miss、runtime error response、config sync source/result 告警。
- 文案发布、灰度、回滚与审计证据。

### Out of Scope

- 使用伪造趋势替代真实 metrics。
- 在 dashboard 中按具体 errorCode 建高基数序列。

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`log-metric-trace-unification`](./log-metric-trace-unification/spec.md)：以 requestId 和 traceId 关联日志、指标与追踪，同时限制标签基数并脱敏主体数据。
- [`slo-error-budget-governance`](./slo-error-budget-governance/spec.md)：定义“SLO 错误预算治理”的可观察主路径、失败语义及父能力交接。
- [`alert-drill-closure`](./alert-drill-closure/spec.md)：以受控故障演练证明「注入 → 指标/告警命中 → 恢复 → 回执」动态闭环。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 observability and alerting 能力 SIT

- Error Governance dashboard 能关联 override hit/miss、runtime error response 与 config sync fallback。
- override 发布窗口内 hit/miss 变化可解释，miss 异常、locale 缺失、disk fallback 有告警。
- 回滚恢复 baseline 文案，不需要重启服务或端侧升级。

<a id="req-002"></a>
### REQ-002 建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路

- 建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路。
- 用户提示语 override 发布后，`p95 <= 60s` 在在线服务中生效；未命中时必须回退 codegen baseline，不影响错误响应可用性。
- `controlplane_error_message_override_total{result="miss"}` 在发布窗口外不得持续异常抬升；若某 locale 发布后 10 分钟内无 hit，进入运营告警。
- config sync 进入 `disk-fallback` 时可继续服务 baseline 文案，但必须 5 分钟内告警并阻止继续推广。
- 文案配置回滚只允许通过 control-plane config revision 回退，禁止手改服务代码或端侧包。
- 回滚后 `hit` 应回落到 baseline revision 对应分布，`miss` 不得高于发布前 2 倍超过 10 分钟。
- dashboard 只能消费真实 runtime/controlplane 指标，禁止伪造趋势。
- 告警标签禁止携带具体错误码高基数字段；按 module/kind/reason 或低基数 result/locale 聚合。
- 用户提示语 override 的发布、灰度、回滚和审计记录必须与 runtime-errors 验收绑定。

## 6. 契约与依赖

- 上游能力：[`platform-ops-governance`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 observability and alerting 能力 SIT

- GIVEN 执行“observability and alerting 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“observability and alerting 能力”对应动作。
- THEN Error Governance dashboard 能关联 override hit/miss、runtime error response 与 config sync fallback。
- THEN override 发布窗口内 hit/miss 变化可解释，miss 异常、locale 缺失、disk fallback 有告警。
- THEN 回滚恢复 baseline 文案，不需要重启服务或端侧升级。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 observability and alerting 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Error Governance dashboard 能关联 override hit/miss、runtime error response 与 config sync fallback。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 对象 runtimeEntrypoint 指标遥测缺口（余 1 项棘轮）

- 类型：`capability_gap`
- 优先级：`P3`
- 准出影响：`track`
- 影响或价值：尚缺 `content.media_original_access_fact` 一项的
  emit 接入与消费面——其实现文件当前处于并行改造中间态，接入需待
  该对象静止。其余 17 项已全链闭合：契约 runtime_entrypoints 声明的
  投影/事实追加/订阅/边缘决策指标由统一 helper 在入口出口按 outcome
  计数，helper 是 runtime/observability/entrypoint_metrics.go，
  Python 侧以 prometheus_client 同模式实现；消费面由
  qwq-l3-projection-facts 看板与 quwoquan_l3_projection_facts 告警组
  承载，promtool 正负例已锁缺失 series 时 or-vector-0 语义；
  gateway 两项按单轨原则契约名对齐既有实现 emitter。
- 完成判定：`SIT-001` 范围内 `verify_object_alert_coverage.py` 的
  runtimeEntrypoint 消费面项清零（当前余 1，只减不增）；
  media_original_access_fact 静止后同增量补 emit 与看板 target。
- 依赖：content media_original_access_fact 并行改造静止。

<a id="open-003"></a>
### OPEN-003 promtool 告警求值覆盖余量（约 23/193，只增不减）

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺约 170 条手写告警的表达式求值回归——它们仅有
  YAML 契约与同源静态校验，阈值或标签打错只能在真实事故中暴露。
  `promtool test rules` 已随 `make gate` 与 Delivery Gate service
  scope 执行，当前约 23 个 alertname 有注入序列求值，批次为
  SLO burn-rate、黑盒拨测、跨 group critical 代表、LiveKit 丢包
  与契约派生链。
- 完成判定：`SIT-001` 范围内每个手写告警 group 的全部 critical 告警
  有 promtool 正负例；覆盖 alertname 数只增不减（棘轮基线 23）。
- 依赖：无外部阻断，按 group 分批补齐。

<a id="open-004"></a>
### OPEN-004 行为归因卡为进程内计数，多副本需中央 Prometheus 化

- 类型：`capability_gap`
- 优先级：`P3`
- 准出影响：`track`
- 影响或价值：尚缺行为归因卡的跨副本聚合——Portal 行为归因卡经
  content-service `/metrics/rec/behavior-attribution` 读进程内
  `prometheus.DefaultGatherer` 快照，当前单副本部署下数值真实且
  Portal 已明示口径；content-service 扩到多副本后该卡只反映被打到的
  单个进程，需要改为经中央 Prometheus 查询聚合。
- 完成判定：`SIT-001` 范围内该卡改为消费中央 Prometheus 聚合查询
  （复用 product-ops 的 Prometheus 代理设施），多副本部署下数值与
  中央面板一致，Portal 页面测试覆盖聚合口径。
- 依赖：content-service 多副本容量窗口（当前四环境均单副本）。
