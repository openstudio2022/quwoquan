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

<a id="dec-002"></a>
### DEC-002 灾备准出只信任 hosted 隔离恢复 receipt
- 决策：灾备准出只接受由受控 data-plane 工作流生成、并绑定计划摘要与恢复目标的
  hosted receipt；本机 dump、CI 合成文件和页面手工输入均不得作为生产证据。
- 理由：备份文件存在无法证明加密、异地副本、可恢复性和 RPO/RTO。release 必须对
  receipt 的内容摘要、KMS key version、远端副本状态、隔离恢复目标、恢复耗时和
  容量成本水位 fail-closed。
- 被否决方案：把 `/var/backups` 的 gzip dump、默认 localhost 连接或过期报告作为
  release green 条件。
- 约束与影响：receipt 仅保存引用、摘要和脱敏状态；签名或远端操作身份由 hosted
  authority 证明。缺少受控 data-plane/KMS/云存储权限时，production workflow 必须阻断。
- 关联要求：`REQ-005`
- 影响 Story：同 DEC-001，约束 [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md) 的灾备准出。
- 关联验收：`SIT-005`

<a id="dec-003"></a>
### DEC-003 第一方容器预验证与正式 release transaction 物理分轨

- 决策：预验证只使用独立 Compose project、远端目录和 rootless user systemd unit。
- 决策补充：只消费 Service Pipeline 发布到 GHCR 的 OCI digest 制品，不进入 rollout lock、SLO、正式 release ledger 或 receipt。
- 决策补充：受限单机使用声明式容器内存/PID 上限，空间门同时校验当前可用量、可回收量与回收后实测量。
- 理由：在 Provider、SFU、真实数据和公网入口尚未就绪时，仍需验证第一方容器可部署性，但该结果不能被误用为生产准出。
- 被否决方案：使用 `latest`、远端临时构建、旧容器、裸 IP public base，或把容器启动成功写成正式发布成功。
- 约束与影响：隔离数据使用重新摘要的不可提升配置投影和独立随机认证材料，unit 不得继承正式 credentials；Actions Artifact 只可作为非必需兼容输出，ReleaseManifest 配置包和镜像均以 GHCR digest 消费。旧运行面回收仅允许匹配声明前缀且处于 `Created/Exited` 的容器和未使用镜像，禁止删除任何 volume 或恢复容器。报告必须并列输出 container runtime、Provider readiness 与 release eligibility，后两者在完整生产证据前固定为 `GATE_BLOCK`。
- 关联要求：`REQ-009`
- 影响 Story：在 [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md) 中约束预验证与正式准出分轨。
- 关联验收：`SIT-008`、`GWT-003`

<a id="dec-004"></a>
### DEC-004 发布执行面唯一，Portal 仅观察且 Config ACK 是发布前置条件

- 决策：唯一可变发布执行面为受保护的 CI/CD 调用 `stackctl`。
- Portal 只能读取由控制面、Prometheus、Elasticsearch 或业务投影返回的状态，不能 apply、扩量或回滚。
- 发布页仅呈现当前候选摘要下按服务聚合的实例 ACK，不得从本地 release 文件推导阶段、生成 workflow/rollback token 或把默认值显示为成功。
- 决策补充：每个受管实例以 service principal 调用 generated ConfigSnapshot resolve/report operation；其 service/environment/instance 身份、ReleaseManifest digest、configVersion 和 desired/effective hash 由控制面验证。`stackctl` 在 hosted rollout 中只接受所有必需实例在有效期内对候选摘要 `in-sync` 的 config-convergence readiness。
- 理由：由 Portal、容器内脚本或调用方参数分别驱动发布会形成第二执行面，且匿名或未绑定的 ACK 无法证明当前候选已实际加载。
- 被否决方案：Portal 提供 release mutation、服务匿名 POST ACK、客户端自报 province/carrier 参与分流，或仅凭单一容器存活继续 rollout。
- 约束与影响：灰度只使用 appVersion/userId。province/carrier 仅在可信边缘证明链和 hosted UAT 同时完成后才可启用，IaC 在满足该条件前保持显式禁用。缺少任何 ACK、实例过期、摘要不匹配或未可信维度时均 fail-closed，且不得用本地状态、旧报告或页面显示替代。无真实 query/mutation 契约的全局搜索、通知计数和工作台入口不得渲染为可操作能力。
- 关联要求：`REQ-006`
- 影响 Story：同 DEC-001，约束 `SIT-004` 与 `SIT-006`。
- 关联验收：`SIT-002`、`SIT-004`、`SIT-006`

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
