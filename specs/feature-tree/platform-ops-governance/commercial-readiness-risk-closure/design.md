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

- 决策：正式生产 authority 只沿 artifact factory OCI exact bytes → `CandidateMaterialManifest` → `QualificationFact` → stable `ReleaseTagAdmissionFact` → `ProdActivationAdmissionFact` → stage attempts → `ProdReleasedFact` → soak 的 canonical exact-byte predecessor 单轨推进；prevalidation 是链外失败诊断，不是该链的输入、前驱或旁路 authority。
- 决策补充：prevalidation 只在独立 Compose project、远端目录和 rootless user systemd unit 中，消费显式 legacy history/rehearsal-only 的 `non-promotable snapshot` 与 factory OCI 实际 bytes；不得生成或写入 authority、ledger、receipt、qualification、admission、tag、stage 或 released fact。
- 决策补充：受限单机使用声明式容器内存/PID 上限，空间门同时校验当前可用量、可回收量与回收后实测量。
- 理由：在 Provider、SFU、真实数据和公网入口尚未就绪时，仍需验证第一方容器可部署性，但该结果不能被误用为生产准出。
- 被否决方案：使用 `latest`、远端临时构建、旧容器、裸 IP public base，把 Actions Artifact 当正式阶段传递，或把容器启动成功写成正式发布成功。
- 约束与影响：Actions Artifact 只能保存失败诊断；正式消费者必须从 factory OCI 与 hosted authority 按 exact digest 回读。任何 legacy generic validate alias、公开 writer 或 formal caller 均禁止存在。隔离数据使用重新摘要的不可提升配置投影和独立随机认证材料，unit 不得继承正式 credentials；旧运行面回收仅允许匹配声明前缀且处于 `Created/Exited` 的容器和未使用镜像，禁止删除任何 volume 或恢复容器。报告必须分轴输出 container runtime、Provider readiness 与 release eligibility；Provider 不可用必须显式为 unavailable，正式 release eligibility 在完整生产事实链成立前始终为 `GATE_BLOCK`。
- 关联要求：`REQ-009`
- 影响 Story：在 [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md) 中约束预验证与正式准出分轨。
- 关联验收：`SIT-003`、`SIT-008`

<a id="dec-004"></a>
### DEC-004 发布执行面唯一，Portal 仅观察且 Config ACK 是发布前置条件

- 决策：唯一可变发布执行面为受保护的 CI/CD 调用 `stackctl`。
- Portal 只能读取由控制面、Prometheus、Elasticsearch 或业务投影返回的状态，不能 apply、扩量或回滚。
- 发布页仅呈现当前候选摘要下按服务聚合的实例 ACK，不得从本地 release 文件推导阶段、生成 workflow/rollback token 或把默认值显示为成功。
- 决策补充：每个受管实例以 service principal 调用 generated ConfigSnapshot resolve/report operation；ACK 必须绑定当前 `ProdActivationAdmissionFact` exact ref，并由该 activation 追溯同一 `CandidateMaterialManifest` exact digest、factory material exact digest、config deployment bundle exact digest 与 activation revision。`stackctl` 在 hosted rollout 中只接受所有必需实例对当前 activation 新鲜、`in-sync` 的 config-convergence readiness。
- 理由：由 Portal、容器内脚本或调用方参数分别驱动发布会形成第二执行面，且匿名或未绑定的 ACK 无法证明当前候选已实际加载。
- 被否决方案：Portal 提供 release mutation、服务匿名 POST ACK、ACK 绑定部署期本地 manifest 或候选文件、客户端自报 province/carrier 参与分流，或仅凭单一容器存活继续 rollout。
- 约束与影响：Portal 保持只读投影，不能补写 ACK 或改变 activation revision。灰度只使用 appVersion/userId；province/carrier 仅在可信边缘证明链和 hosted UAT 同时完成后才可启用，IaC 在满足该条件前保持显式禁用。缺少任何 ACK、实例过期、activation exact ref 缺失、CandidateMaterialManifest/factory material/config deployment bundle exact digest 不匹配或使用未可信维度时均 fail-closed，且不得用本地状态、旧报告或页面显示替代。无真实 query/mutation 契约的全局搜索、通知计数和工作台入口不得渲染为可操作能力。
- 关联要求：`REQ-006`
- 影响 Story：同 DEC-001，约束 [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md) 的发布执行与配置收敛边界。
- 关联验收：`SIT-002`、`SIT-004`、`SIT-006`

## 5. 失败与恢复

- prevalidation 无法读取显式 `non-promotable snapshot`、factory OCI 实际 bytes 或隔离运行依赖时，返回可区分的诊断失败并保持零正式 mutation；Provider 等被排除能力不可用时必须显式 unavailable，release eligibility 仍为 `GATE_BLOCK`。
- ConfigSnapshot ACK 缺失、过期、drift，或与当前 `ProdActivationAdmissionFact` exact ref、其 `CandidateMaterialManifest`/factory material/config deployment bundle exact digest、activation revision 任一不一致时，发布停在 config-convergence readiness，且不得创建下一 stage attempt。
- 正式 predecessor 的 stage/terminal exact ref 无法从 hosted authority 回读、canonical bytes 摘要不匹配、CAS 冲突或 authority 不可用时，统一 fail-closed 为 `GATE_BLOCK`；不得写下一阶段、`ProdReleasedFact` 或 soak 成功事实。
- 恢复只允许修复原依赖后按同一当前 activation 与 exact predecessor ref 幂等重试；stage CAS 只推进唯一下一阶段。正式回滚由唯一执行面绑定失败 stage exact ref 与 last-good `ProdReleasedFact` 执行，prevalidation 不得触发或模拟回滚。
- 禁止 fallback：不得回退到 Mock、旧 wire、legacy generic validate alias/writer、双读双写、页面本地副本或由 workflow success 合成 authority。

## 6. 质量与观测

- 正式发布观测必须为每个 stage attempt 与 terminal 结果暴露可回读的 exact ref，并证明其当前 activation、同一 CandidateMaterialManifest/factory digest 闭包及唯一前驱关系；不可用、缺失或不一致均告警并保持 `GATE_BLOCK`，不得以 workflow/job success 代替。
- prevalidation 观测只报告诊断 run ref、container runtime、Provider readiness、release eligibility 与零正式 mutation；该 run ref 不得出现在正式 stage/terminal predecessor 链内。
- ConfigSnapshot 收敛观测按当前 activation revision 聚合 ACK 新鲜度与 drift；Portal 仅查询该 hosted 投影。无法取得真实投影时显示不可用，不生成默认成功值。
- 外部前置缺失以 `external_blocker` OPEN 表达并阻断对应 production workflow；不得用豁免或合成证据放行。生产 SLO、告警和 exporter 的字段级约束继续由 runtime L2 与 canonical contracts 拥有，本设计只约束其 exact ref、失败终态和 authority 边界。
