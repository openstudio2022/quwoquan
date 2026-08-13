# SLO 错误预算燃烧告警处置手册

对应告警：`GlobalHttpAvailabilityFastBurn`（critical，需立即处置）与
`GlobalHttpAvailabilitySlowBurn`（warning，转工单）。SLO 目标 99.9% 可用性，
错误预算 0.1%；燃烧率语义见 `quwoquan_alerts.yaml` 的 `quwoquan_slo_burn_rate`
组注释。

## 快烧（FastBurn）处置

1. 打开 Grafana `L3 — Error Governance 错误治理`（uid
   `qwq-l3-error-governance`），确认「按服务 HTTP 5xx 比率」中的异常服务
   与「Top 10 错误码速率」中的主导 `MODULE.KIND.REASON`。
2. 结合 `L3 — 服务黄金信号` 的发布标注判断是否与最近发布/重启相关；
   若相关，按 `stackctl deploy` 回滚流程回到 `fromCandidateDigest`
   （prod 操作需人工确认）。
3. 若为依赖故障（Mongo/PG/Redis），查看 `L4 — 基础设施` 与对应
   exporter 告警，按依赖恢复优先。
4. 处置后在 Portal 平台可观测页 ack 告警，留下处置摘要（进入审计链）。

## 慢烧（SlowBurn）处置

1. 同上定位主导错误码与服务，但按工单节奏处理：创建修复任务并绑定
   错误码，无需立即回滚。
2. 检查是否为单一 operation 的持续性失败：契约派生告警
   （`<Domain>ContractOperationAvailabilityBelow*`）若同时触发，按该
   operation 的对象契约 `errors.yaml` 恢复语义修复。
3. 连续两个观察日仍慢烧时升级为快烧处置流程。

## 验证恢复

- 告警恢复（Alertmanager resolved 推送到 Portal）。
- Error Governance 看板 5xx 比率回落至 0.1% 预算线以下。
- `stackctl inspect --env prod --scope metrics` 读回无异常。
