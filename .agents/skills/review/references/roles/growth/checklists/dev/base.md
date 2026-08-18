# growth · dev · base

承接原 `/obs-audit` 的检查面：树归属、验收锚点、三层测试、SLO 覆盖、告警噪声、日志字段、
trace 串联、错误码、回滚触发条件。

## PRE 准入

- [MUST] 本次新增的每个指标都能归属到某个 Story 或能力验收，没有孤立指标
  check: 找到无法归属到 Story/验收锚点的指标，判失败
- [MUST] SLO 覆盖已声明，且阈值有依据而不是拍数
  check: 阈值无来源说明，判失败

## DURING 执行中

- [MUST NOT] 新增不可归属到 Story/能力验收的孤立指标
  gate: make verify-observability-catalog
- [MUST NOT] 指标口径与 metadata 定义分叉，形成第二套统计
  gate: make verify-metric-identity-homology
- [MUST NOT] 日志或埋点携带未脱敏的 PII
  gate: make verify-operation-privacy-redaction

## POST 自检

- [MUST] 观测目录一致
  gate: make verify-observability-catalog
- [MUST] 指标发射端真实存在
  gate: make verify-metric-emitter-existence
- [MUST] 指标身份同源
  gate: make verify-metric-identity-homology
- [MUST] 指标阈值同源
  gate: make verify-metric-threshold-homology
- [MUST] 对象告警覆盖成立
  gate: make verify-object-alert-coverage
- [MUST] 隐私脱敏通过
  gate: make verify-operation-privacy-redaction
- [SHOULD] 页面埋点覆盖达标
  gate: make verify-page-telemetry-coverage
- [SHOULD] 告警演练闭环
  gate: make verify-alert-drill-closure

## HANDOFF 交接

- 产出：新增指标/告警清单及其归属的 Story、看板或查询入口
- 未决项去向：暂无看板的指标转 `OPEN-###`，写明谁在什么节奏下看它
- 下一步：POST 评审汇总
- 证据链：上述 gate 输出
