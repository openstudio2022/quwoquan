# L2 Design：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚”需要 `daily-merge-release-strategy`、`gray-release-to-prod`、`local-gamma-mirror`、`multi-environment-instance-isolation`、`multi-environment-wave-deployment`、`workflow-naming-consolidation` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：仓库只保留 `dev1.0` 与 `main`；日常开发直接进入 `dev1.0`，唯一 PR 边为 `dev1.0 -> main` promotion。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：按 alpha、beta、gamma、prod 的准入顺序发布同一制品，任一波次失败即停止晋级。
- [`service-core-composition`](./service-core-composition/spec.md)：以同一 Go host 组合 11 个核心服务而不改变领域契约、数据归属或独立实时/模型故障域。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_ops/environments`、`quwoquan_ops/environments/prod/kustomization.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 dev1.0 集成与 main 发布组成唯一受控主链
- 决策：仓库只保留 `dev1.0`、`main` 两个分支。长期集成真相源固定为 `dev1.0` 并接受日常直接开发，唯一发布真相源固定为 `main` 且只接受 `dev1.0 -> main` promotion PR；promotion 成功后仅受管系统可把 `main` fast-forward backsync 到 `dev1.0`。
- 单向状态流：`dev1.0` push 只生成绑定精确 SHA 的 `03/04/05` hosted check evidence，不取得 release eligibility。`dev1.0` 合入 `main` 后生成 promotion receipt 并允许 mainline candidate admission。系统 backsync 只同步 ref，不生成新的 promotion 或 release eligibility。
- 机器真相源：`quwoquan_ops/policies/branch_policy.yaml` 唯一声明两个分支、唯一 PR 边、integration/release/production-source 角色与 system backsync。hook、Actions、release governance 和 Prod source admission 只消费该合同，不各自维护第二份 allowlist。
- 对象边界：`BranchPolicy` 是从上述版本化合同加载的不可变配置，`BranchTransition` 是一次评估的不可变输入值，`BranchDecision` 是不可变判断结果。Integration evidence 直接使用 GitHub 对精确 SHA 的 hosted Check Runs；Platform Ops 的 `BranchGovernanceEvidenceWriter` 只负责 promotion、backsync 与 blocker receipt，receipt 只引用 Git/GitHub 权威事实和 policy digest，不成为可修改分支状态或第二套 policy。
- 决策导出面：生产模块提供纯 `BranchTransition(event, actorKind, repository, head, base, beforeOid, afterOid, refs) -> BranchDecision(status, reasonCode, stringContext)`。`status` 只允许 `allowed|blocked`，`reasonCode` 只使用 `OPS.BRANCH.*` 稳定身份，OID、ref、actor 与远端诊断只进入 string context；local contract 直接调用该生产 evaluator。
- Git authority 端口：`BranchRefReader.readHeads(repository) -> BranchRefSnapshot` 读取权威 heads、精确 OID 与 ancestry。`BranchBacksyncWriter.fastForward(expectedBeforeOid, promotionOid) -> BranchBacksyncResult` 只执行无 force fast-forward 并回读 exact after OID。equal 为幂等 no-op；同一 attempt 发现 before OID 漂移即返回 `OPS.BRANCH.BACKSYNC_CAS_CONFLICT` 且零写，只有新 attempt 取得新快照后才能重新判定。任何分叉、main 落后、non-fast-forward、权限或网络不可确认都不写 ref。
- Hosted authority：只读 `HostedGovernanceReader` 绑定 repository/default branch、PR number、head/base/merged SHA、workflow run/attempt/source ref、actor/installation identity、main/dev before-after OID、适用 protection/ruleset、observedAt 与 evidence digest。fixture 只能验证 parser，不能冒充 hosted evidence；尚未精确证明的托管 authority 保留在 L3 `OPEN-002`。
- Prod admission：先验证 workflow definition 来自 `refs/heads/main`、source 是可达 `origin/main` 的精确 commit，并由 GitHub readback 证明唯一已合并 `dev1.0 -> main` promotion、merge SHA、最终 promotion head、绑定该 head 的 approval、canonical required workflow run/attempt/check identity、repository default branch 与当前 workflow attempt。
- Prod effect isolation：任一逐次 readback 不可证明时 fail-closed，只产 blocker receipt；candidate、credential materialization、Provider 与 `stackctl` rollout command 均不可达。
- Private-free 边界：无原生 protection/ruleset 时记录 `hostedProtectionVerified=false` 并阻断 `formalProd` 声明，具备上述逐次证据的 release validation 可以继续；满足父能力的 hosted protection 与 approval 后才交给 `gray-release-to-prod` 的 effectful rollout。
- 理由：把频繁集成和唯一发布拆开可以稳定 integration checks，同时保持未晋级代码无法取得 release eligibility；共享 evaluator、真实 Git 端口与 hosted readback使三层证据绑定同一 repository、run 与 OID。
- 被否决方案：`main` 同时承担日常集成、创建任何临时或第三长期分支、非 `dev1.0 -> main` PR 直达发布、人工 `main -> dev1.0`、force backsync、用环境变量自报 system identity，或由 hook/workflow复制分支规则。
- 约束与影响：GitHub 原生保护不可用时，仓内 gate 只能阻断 eligibility 而不能声称远端 direct push 未发生。`dev1.0` 异常只允许在同一分支追加修复提交，禁止临时 reconcile 分支、自动 merge、force push 或历史改写。
- 合法 main promotion 入库后自动启动同一 DAG，完成不可变 OCI `ReleaseEvidenceManifest` 的 `component-ready -> candidate-ready` 总装与 Alpha/Beta/Gamma 阻断验证；正式 Prod apply 不由 workflow_run 或 push 静默执行，必须由人工 dispatch 绑定可达 `main` 的精确 Git SHA、显式设置非 dry-run，并通过 production environment approval。
- `candidate-ready` 必须绑定四环境配置包、四环境 App 真实 payload、ContractGraph、真实 Provider readiness 与三层测试；按序接受 Alpha/Beta/Gamma 回执并绑定 rollback readiness 后才成为 `deployable`，Prod 全量验证后才成为 `released`。
- 同一候选制品就绪后，Alpha、Beta、Gamma-local 在隔离运行面并行执行；聚合器仍按 `alpha -> beta -> gamma` 验证回执，任一失败均不得申请 Prod approval。
- Prod 只保留一个 production environment approval 与一个事务 job；checkout、OIDC/registry login、ReleaseEvidenceManifest 验签、治理校验和配置包物化只执行一次，随后由 `stackctl` 依次推进 `canary、5、20、50、100`。
- push 与默认 dispatch 均保持 dry-run；dry-run 不提交 hosted ledger，因此只执行 `canary` 只读校验并明确标记边界，禁止伪造 `5/20/50/100` 回执。
- 发布身份只使用 `fromCandidateDigest -> toCandidateDigest`；镜像 transport tag 和逐服务配置包仅是装配坐标，不得重新成为晋级或恢复身份。
- 600/1800 秒准出以 GitHub workflow `created_at -> candidate/prod completed_at` 的官方日历时长为唯一关键路径；Jobs API 的 DAG 只生成 `machineCriticalPath` 诊断，矩阵长尾与 runner 排队不得由 shell timer 或静态预算替代。
- mainline timing 在渲染后以精确 GHCR OCI digest 发布，再由独立 append-only hosted timing authority 按 candidate digest + workflow run 建索引并执行 bind/query readback；该索引不复用 Prod rollout CAS，AI advisory 与普通 gate 均无写入口，三天 Actions Artifact 仅作诊断副本。
- 任一匹配 job 缺少 GitHub `created_at` 时保留日历与机器路径中仍可证明的事实，但不生成 queue 数值；`CiTimingSummary.missingEvidence` 写入 `githubJobs.createdAt`、状态保持 `historical_incomplete`，随后确定性阻断。
- Deployment 与 Deployment Status 的 `pending/queued/in_progress` 会承载部署、并发或 runner 状态，不能证明 required-reviewer 的请求或批准时刻。approval 分段计时必须消费绑定 repository、workflow run、head SHA 与 `production` environment 的显式 durable `deployment_review` 事件；当前缺少该 hosted 事件事实时必须 `historical_incomplete + GATE_BLOCK`。
- 主链软目标 600 秒、硬门 1800 秒；创建后 1500 秒停止继续晋级，并由 `stackctl` 的确定性回滚闭环恢复上一稳定候选。
- 第一方容器 prevalidate 经 stackctl 独立执行，不能取得正式 rollout、ledger、receipt 或 Provider readiness。
- 本地镜像重用 package 时必须校验来源 image；Caddyfile、服务内部端口与 non-prod control-plane policy 均由 canonical 装配消费，禁止临时 symlink、手工重标记或脚本旁路。
- 关联要求：`REQ-001`
- 影响 Story：[`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)、[`gray-release-to-prod`](./gray-release-to-prod/spec.md)、[`local-gamma-mirror`](./local-gamma-mirror/spec.md)、[`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)、[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)、[`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 prod-hosted 扩容是同一 ssh-hosted 集群内的 member×instance×replica
- 决策：生产扩容不新增环境名，也不恢复 K8s/ACK 第二执行面。`access-isolation.yaml` 拥有 `management.hosts` 与 `deploymentInstances.{prevalidate,gray,prod}.replicas`；`stackctl` / `deploy_to_prod.sh` / `render_prod_plane_stack.py` 只消费该拓扑。
- 理由：当前可运行真相源已是 SSH + rootless Podman；规格若继续写 ACK Deployment 会制造第二主线。单 member / 单 replica 必须保持兼容。
- 被否决方案：`prod-gray` 环境、`cluster_topology.yaml` 与 access-isolation 双真相源、按 replica 各自独立 ledger 绕过 service-plane CAS。
- 约束与影响：每个 placement 有独立 remote root / project / unit / `SERVICE_INSTANCE_ID`，gray 与 prod 共置，正式 commit 前 `postChecks` 必须覆盖全部期望 placement，部分成功不得写 `full`。
- 关联要求：`REQ-002`
- 关联验收：`SIT-002`

<a id="dec-003"></a>
### DEC-003 核心 Go 服务以 Service Core 组合部署且保持 split-ready
- 决策：`api-edge`、`assistant-service`、`chat-service`、`circle-service`、`content-service`、`entity-service`、`integration-service`、`notification-service`、`search-service`、`tag-service` 与 `user-service` 组合为一个 `service-core` Go 进程、镜像与部署单元，Python `recommendation-service`、`realtime-gateway`、`rtc-service`、`product-ops-service` 与 `platform-ops-service` 保持独立进程，组合不改变服务 contracts、公开 hostname/port/route、数据源、迁移 owner 或可观测 `service.name`。
- 理由：核心服务共享受治理运行时和同一发布节奏，组合可减少单机部署开销，Python 模型运行时及长连接服务具有不同语言、资源和故障恢复特征，继续独立可避免将其扩散为单 PID 故障域。
- 被否决方案：把所有服务、实时、RTC、模型和运维服务合并为一个进程，或为组合部署合并领域，或让 module 间以私有 import/共享 store 直接调用，或在一个 target 并存两套 topology 或运行时切换。
- 约束与影响：模块只暴露自身薄 bootstrap，顶层 host 只组合 module factory，module 间仍经原 generated HTTP/WS contract，workload composition 从服务自治部署输入生成，候选同时绑定 OCI、SBOM、provenance、module/config/migration digest，切换为整体 candidate 操作，回滚只使用上一 immutable candidate 的精确 bytes，host 按 module 执行配置、迁移、listener admission、health、资源预算、shutdown 和 observability，任一 required module 的不可恢复失败使 aggregate fail-closed。
- 关联要求：`REQ-002`
- 影响 Story：[`service-core-composition`](./service-core-composition/spec.md)
- 关联验收：[`service-core-composition GWT-001/GWT-002`](./service-core-composition/spec.md#gwt-001)

## 5. 失败与恢复

- 失败类型：分支 policy 无效、PR/ref 非法、`main` direct push、backsync 非 fast-forward、ref compare-and-swap 冲突、Prod source 不可达 main、权限拒绝、依赖超时、候选摘要冲突、证据缺失或持久化失败。
- 可见结果：调用方收到稳定 `OPS.BRANCH.*` 或父能力 canonical failure；任何失败均不写 promotion、candidate、backsync、deploy 或 rollback 成功事实。
- 恢复动作：非法 PR/ref 修正 head/base 后重试。backsync equal 幂等完成，安全 ancestor 可重读后重试。`dev1.0` 分叉时停止并要求人工裁决，不创建临时分支或 force。push 返回成功但 readback 未知时禁止盲重试，先从权威 ref 回读。after 等于 promotion OID 时收口成功，after 仍等于 before 时可安全重试，其他值冻结 eligibility。远端权限、网络、ancestry 或 hosted authority 不可确认时停止并保留 before/after readback。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 分支治理由 Platform Ops owner 记录 `branch_policy_decision_total{event,status,reasonCode}`、`branch_backsync_terminal_seconds{status}`、`branch_ref_readback_complete_total{ref,status}` 与 `branch_release_eligibility_total{status,reasonCode}`；每条 attempt 绑定 repository、run/attempt、promotion SHA、before/after OID 和 evidence digest，脱敏 receipts 保留至少 90 天。
- 每个 policy/admission attempt 的 reason 覆盖率与 ref readback 完整率目标为 100%。成功 promotion 后 backsync 在 300 秒内进入 success、idempotent 或 blocked 终态的月度目标为 99%。任一无 reason decision、readback 缺失、`main/dev1.0` 分叉、未授权 main source 取得 eligibility 或 backsync 超过 300 秒立即触发 Platform Ops P1 告警。外部 GitHub 不可用时保持 fail-closed，不用 availability 降级换取放行。
- `prod-hosted` 的正式灰度 workflow 必须人工 dispatch 并保留 approval；在 Provider、SFU、真实数据、观测、灾备或回滚证据缺失时只允许不可提升 prevalidate，且 post-deploy probe 置信度仍须单独验收。
- 运行装配从各服务 `environments/<env>/deploy`、Ops 同名环境入口和真实 Compose/Kustomize 扫描推导；本地端口保留 `local_env_port_manifest`，prod rollout 保留 `gray_rollout_stages`，服务配置由自治 package 的 provenance 摘要证明。
- 每个 Prod rollout stage 必须执行 `stackctl health + inspect + doctor + integration probes + slo gate`；任一失败写入 GATE_BLOCK/rollback 证据，不得由 workflow 合成成功。
- App 四分片耗时必须读取四个实际 Jobs API 节点并取最大值；任何 shard 缺失时 timing gate 失败，不允许回退到 static/serial 近似值。
- 独立可观测：每域 `service.name` + 指标维度独立，使“逻辑独立”在合并部署时依然成立，并为拆分提供数据依据。
