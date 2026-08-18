# observability · dev · base

## PRE 准入

- [MUST] 本次新增或改动的观测点已实际产生过数据，不是只在代码里存在
  check: 无任何实际样本或查询结果，判失败

## DURING 执行中

- [MUST NOT] 指标只声明不发射
  gate: make verify-metric-emitter-existence
- [MUST NOT] 日志与埋点泄露未脱敏 PII
  gate: make verify-operation-privacy-redaction
- [MUST NOT] 让 trace 在服务边界断开而不记录原因
  check: 跨服务调用未透传 traceId 且未记录断点原因，判失败

## POST 自检

- [MUST] 观测目录一致
  gate: make verify-observability-catalog
- [MUST] 指标发射端存在
  gate: make verify-metric-emitter-existence
- [MUST] 运行时日志治理通过
  gate: make verify-runtime-log-governance
- [MUST] 错误码声明与实际发射一致
  gate: make verify-emitted-error-code-declaration
- [MUST] 端云错误语义一致
  gate: make verify-app-error-endcloud-parity
- [SHOULD] Prometheus 抓取同源
  gate: make verify-prometheus-scrape-homology
- [SHOULD] 告警规则测试通过
  gate: make verify-prometheus-rule-tests

## HANDOFF 交接

- 产出：可用于排障的查询入口（requestId / traceId 怎么查）
- 未决项去向：已知的 trace 断点转 `OPEN-###`，写明影响哪类排障
- 下一步：POST 评审汇总
- 证据链：上述 gate 输出与一次实际查询样本
