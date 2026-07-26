# L2 Design：商用就绪风险收口 (`commercial-readiness-risk-closure`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据”需要 `zero-risk-production-readiness` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md)：缺失项逐一有稳定错误与修复指引，发布不能继续。

## 3. 端云与数据流

- 上游能力：[`platform-ops-governance`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml`、`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`、`quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml`、`quwoquan_service/contracts/metadata/_control_plane/platform/control_plane.yaml`、`quwoquan_service/contracts/metadata/_control_plane/product/control_plane.yaml`、`quwoquan_ops/policies/branch_policy.yaml`、`.github/workflows/service_pipeline.yml`、`.github/workflows/deploy-prod-auto.yml`、`quwoquan_ops/environments/prod/rollout/stages.yaml`、`quwoquan_ops/policies/config-release/slo_thresholds.yaml`、`quwoquan_ops/observability/monitoring/docker-compose.prod.yml`、`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`、`quwoquan_ops/environments/prod/rollout/routing_policy.yaml`、`quwoquan_service/control-plane/platform-ops/contracts/platform_ops/config_snapshot/operations.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 商用准出由可验证证据和阻断级 OPEN 共同裁决
- 决策：商用准出由可验证证据和阻断级 OPEN 共同裁决。
- 理由：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 准出结果必须同时绑定主体、危险动作审批、供应链摘要、配置 revision、验收证据和受影响范围。
- 外部前置缺失以 `external_blocker` OPEN 表达并阻断对应 production workflow；不得用豁免或合成证据放行。
- 证据至少包含最后一份 SLO snapshot、approval receipt 与 rollback receipt，且只保存引用、摘要和脱敏状态。
- 生产观测通过 Prometheus、Alertmanager、OTel 及声明的节点、容器和数据存储 exporter 提供真实数据。
