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
