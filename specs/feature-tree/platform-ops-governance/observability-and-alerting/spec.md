# L2 特性：observability-and-alerting

## 功能说明
- 建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路。
- 为用户可见错误提示语热配置提供 dashboard、alert、SLO 与回滚验收。

## Runtime Error Override 观测

| 指标 | 标签 | 口径 | Dashboard | 告警 |
|---|---|---|---|---|
| `controlplane_error_message_override_total` | `result=hit|miss`, `locale` | `runtime/controlplane` 解析 `sys.error_message.<code>.<locale>` 的命中/未命中次数 | Error Governance / User Message Override | hit rate 突降、miss rate 突增、locale 长时间无 hit |
| `runtime_error_response_total` | `module`, `kind`, `reason`, `recovery_action` | runtime/errors 输出结构化错误响应次数 | Error Governance / Runtime Errors | 单 module 错误率突增、recovery_action 缺失 |
| `controlplane_config_sync_total` | `source`, `result` | control-plane config sync 来源与结果 | Control Plane / Config Sync | `source=disk-fallback` 持续出现或 sync failure |

### SLO

- 用户提示语 override 发布后，`p95 <= 60s` 在在线服务中生效；未命中时必须回退 codegen baseline，不影响错误响应可用性。
- `controlplane_error_message_override_total{result="miss"}` 在发布窗口外不得持续异常抬升；若某 locale 发布后 10 分钟内无 hit，进入运营告警。
- config sync 进入 `disk-fallback` 时可继续服务 baseline 文案，但必须 5 分钟内告警并阻止继续推广。

### 回滚

- 文案配置回滚只允许通过 control-plane config revision 回退，禁止手改服务代码或端侧包。
- 回滚后 `hit` 应回落到 baseline revision 对应分布，`miss` 不得高于发布前 2 倍超过 10 分钟。

## 约束
- dashboard 只能消费真实 runtime/controlplane 指标，禁止伪造趋势。
- 告警标签禁止携带具体错误码高基数字段；按 module/kind/reason 或低基数 result/locale 聚合。
- 用户提示语 override 的发布、灰度、回滚和审计记录必须与 runtime-errors 验收绑定。

## 验收标准
- A1：Error Governance dashboard 可展示 override hit/miss、runtime error response、config sync source/result。
- A2：override miss rate、locale 缺失、disk fallback 和 runtime error spike 有告警规则。
- A3：override 发布和回滚无需云服务重启，且不需要端侧升级。
- A4：dashboard 与告警字段均能通过 local_contract/api_integration 测试或真实指标样本证明来源。
