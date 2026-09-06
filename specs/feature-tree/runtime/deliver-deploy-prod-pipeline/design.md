# L2 Design：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚”需要 `daily-merge-release-strategy`、`gray-release-to-prod`、`local-gamma-mirror`、`multi-environment-instance-isolation`、`multi-environment-wave-deployment`、`workflow-naming-consolidation` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：仓库只保留 `dev1.0`、`main` 与六条声明的长期 lane；日常开发只经 `lane/* -> dev1.0` PR 合入，发布 PR 边为 `dev1.0 -> main` promotion。
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
- 决策：仓库只保留 `dev1.0`、`main` 与六条声明的长期 lane。日常开发面固定为 lane，长期集成真相源固定为 `dev1.0` 且接受 `lane/* -> dev1.0` PR、`integration/` 对同名远端的 expected-old 快进合入，以及 promotion 成功后的受管 system fast-forward backsync；唯一发布真相源固定为 `main` 且只接受 `dev1.0 -> main` promotion PR；promotion 成功后仅受管系统可把 `main` fast-forward backsync 到 `dev1.0`。
- 单向状态流：`dev1.0` push 只生成绑定精确 SHA 的 `03/04/05` hosted check evidence，不取得 release eligibility。`dev1.0` 合入 `main` 后生成 promotion receipt 并允许 mainline candidate admission。系统 backsync 只同步 ref，不生成新的 promotion 或 release eligibility。
- 单一 PR Admission：`lane/* -> dev1.0` 只对 GitHub synthetic merge candidate 在 GitHub-hosted runner 执行受影响快速检查；禁止从 lane push 拼接 App 证据，禁止普通 PR 进入 persistent self-hosted、正式 packaging/full coverage、设备、Provider、签名或 Prod secret。`dev1.0 -> main` promotion 与 nightly/release workflow 才执行重证据。
- 影响与计时边界：同一 DAG 只生成一次绑定 base/head/synthetic SHA、source tree、R0–R4 与 required IDs 的 ImpactPlan，所有 job 验同一 digest。风险按 `R0 non-runtime / R1 single-scope / R2 cross-scope-or-device / R3 governance-or-unknown / R4 release-authority-or-promotion` 单调升级；required test/API/Journey ID 由版本化 ownership policy 解析并随 planner digest 封存。普通 PR 的官方 `created_at -> candidate-ready` 只计算本 DAG；push 不再作为外部前序。功能失败与 infra 失败分别投影，时延 hard gate 只有在 `feedback_slo_activation.json` 绑定至少 20 个唯一 exact OCI clean-run refs 后才能从 learning 激活；flaky 仅允许 infra/transport/device-bridge 一次 fresh retry，隔离最多 7 天且不得包含 promotion-critical 测试。
- GitHub runner 边界：普通 `pull_request` 只能到 GitHub-hosted 无密 runner；受保护 reusable workflow、main/promotion、Environment 分支限制、OIDC producer 与 aggregator readback 共同拥有 self-hosted/签名/设备入口。回滚只允许原子 Git revert，不保留双轨开关。
- 机器真相源：`quwoquan_ops/policies/branch_policy.yaml` 唯一声明允许分支闭集、合法 PR 边闭集、integration/release/production-source 角色与 system backsync。hook、Actions、release governance 和 Prod source admission 只消费该合同，不各自维护第二份 allowlist。
- 对象边界：`BranchPolicy` 是从上述版本化合同加载的不可变配置，`BranchTransition` 是一次评估的不可变输入值，`BranchDecision` 是不可变判断结果。Integration evidence 直接使用 GitHub 对精确 SHA 的 hosted Check Runs；Platform Ops 的 `BranchGovernanceEvidenceWriter` 只负责 promotion、backsync 与 blocker receipt，receipt 只引用 Git/GitHub 权威事实和 policy digest，不成为可修改分支状态或第二套 policy。
- 决策导出面：生产模块提供纯 `BranchTransition(event, actorKind, repository, head, base, beforeOid, afterOid, refs) -> BranchDecision(status, reasonCode, stringContext)`。`status` 只允许 `allowed|blocked`，`reasonCode` 只使用 `OPS.BRANCH.*` 稳定身份，OID、ref、actor 与远端诊断只进入 string context；local contract 直接调用该生产 evaluator。
- Git authority 端口：`BranchRefReader.readHeads(repository) -> BranchRefSnapshot` 读取权威 heads、精确 OID 与 ancestry。`BranchBacksyncWriter.fastForward(expectedBeforeOid, promotionOid) -> BranchBacksyncResult` 只执行无 force fast-forward 并回读 exact after OID。equal 为幂等 no-op；同一 attempt 发现 before OID 漂移即返回 `OPS.BRANCH.BACKSYNC_CAS_CONFLICT` 且零写，只有新 attempt 取得新快照后才能重新判定。任何分叉、main 落后、non-fast-forward、权限或网络不可确认都不写 ref。
- Hosted authority：只读 `HostedGovernanceReader` 每次正式发布动态绑定 repository/default branch、Actions 默认权限与 SHA pin、安全能力、`dev1.0/main` ruleset、required check integration、Environment bypass/reviewer/branch policy、PR/run/source 与 observedAt/evidence digest。fixture 只能验证 parser，真实 GitHub readback 才可令 `hostedProtectionVerified=true`；preflight digest 必须在首个 mutation 前重验以阻断 TOCTOU。
- Prod admission：先验证 workflow definition 来自 `refs/heads/main`、source 是可达 `origin/main` 的精确 commit，并由 GitHub readback 证明唯一已合并 `dev1.0 -> main` promotion、merge SHA、最终 promotion head、绑定该 head 的 approval、canonical required workflow run/attempt/check identity、repository default branch 与当前 workflow attempt。
- Prod effect isolation：任一逐次 readback 不可证明时 fail-closed，只产 blocker receipt；candidate、credential materialization、Provider 与 `stackctl` rollout command 均不可达。
- Hosted 边界：原生 ruleset/Environment 或其 API readback 任一不可用时记录 blocker 并阻断 `formalProd`；`production` 保留全事务唯一 required-reviewer 与 prevent-self-review，第二位真实 principal 缺失时继续 fail-closed。`release-signing/device-matrix` 不增加重复人工审批，只依赖受限 ref 闭集（device-matrix 包含 promotion merge ref）、禁止 admin bypass、固定 producer 与 attestation；仓库设置 readback 使用 repository-scoped、只读 GitHub App token，内置 `GITHUB_TOKEN` 不冒充 Administration authority。当前仓库属于个人账户而非 Organization，GitHub 不提供 runner group API，因此等价权威由仓库级精确 runner 名称闭集加 `quwoquan-release-authority` 自定义标签实施并动态 readback；迁入 Organization 后再无损收紧为 runner group。
- 理由：把频繁集成和唯一发布拆开可以稳定 integration checks，同时保持未晋级代码无法取得 release eligibility；共享 evaluator、真实 Git 端口与 hosted readback使三层证据绑定同一 repository、run 与 OID。
- 被否决方案：`main` 同时承担日常集成、创建任何白名单外分支或额外长期分支、非 `dev1.0 -> main` PR 直达发布、人工 `main -> dev1.0`、force backsync、用环境变量自报 system identity，或由 hook/workflow复制分支规则。
- 约束与影响：GitHub 原生保护不可用时，仓内 gate 只能阻断 eligibility 而不能声称远端 direct push 未发生。异常增量只允许在其 lead lane（或过渡期 `dev1.0`）追加修复提交，禁止白名单外 reconcile 分支、自动 merge、force push 或历史改写。
- 合法 main promotion 入库后自动启动同一 DAG，完成不可变 OCI `ReleaseEvidenceManifest` 的 `component-ready -> artifact-complete -> qualified` 总装与 Alpha/Beta/Gamma 阻断验证；正式 Prod apply 不由 workflow_run 或 push 静默执行，必须由人工 dispatch 绑定可达 `main` 的精确 Git SHA、显式设置非 dry-run，并通过 production environment approval。
- `qualified` 必须绑定四环境配置包、Android/iOS 的 nonprod/prod 组件、单一 Web bundle、ContractGraph、真实 Provider readiness 与三层测试。Alpha、Beta、Gamma 环境 composition 引用同一 nonprod App bytes digest，按序接受回执并绑定 rollback readiness 后才成为 `main-admitted`，Prod 全量验证后才成为 `released`。
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
- Readiness 对象边界：`LaunchReadyFact` owner 是 canonical launcher 的 post-launch projector，仅消费同 attempt 的 source/artifact/runtime-config、device/lease/transport、launch attempt、safe-terminal 与 installed-config readback exact bytes；它不消费 UAT 或 release authority。`ContentReadyFact` owner 是 App UAT aggregator，只消费完整 raw journey 集并以 `LaunchReadyFact` ref+digest 为唯一 predecessor；`ReleaseReadyFact` owner 是可信 Hosted promotion aggregator，只消费 promotable `ContentReadyFact`、immutable release composition/artifact 与 EAF/双物理/真实 Provider/migration/rollback/performance/reliability/cleanup。三者共用 create-once/non-symlink/fresh-attempt store 与 canonical JSON digest，失败只保留 `APP.READINESS.*` blocker，不生成后态。
- Readiness 恢复边界：fact 路径冲突、predecessor 摘要/类型/attempt 漂移、raw journey 缺失或 evidence 篡改均要求新 attempt 从最后可信前态重新聚合；禁止覆盖旧 fact、扫描 latest、复制 preflight 状态或把开发启动提升为 release eligibility。

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

<a id="dec-004"></a>
### DEC-004 App 制品身份、签名隔离与多渠道分发回执
- 决策：App 分发以三个分离对象承载事实——`AppArtifactManifest`（`ReleaseEvidenceManifest` 候选内的 immutable owned entity，拥有 platform、BuildMode、distributionClass、package/bundle ID、version/build、signing identity、source/artifact/launch-manifest digest 与 promotability）、`InstallReceipt`（按 store/device/build 追加且集合无界的 separate append-only fact，独立生命周期与查询）、渠道矩阵（从 canonical metadata 生成，覆盖 Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝与官网 `official_web` APK）。打包、签名校验、安装与渠道登记统一走 `stackctl package` 的 canonical App 入口（显式 `env/platform/build-mode/distribution-class/device`），`run.sh` 与 IDE 只做薄包装。
- 跨边界 port：构建写入走 `AppArtifactPackageWriter` 生成不可变制品、`AppArtifactManifestReader` 提供验证查询；安装证据走 `AppInstallReceiptAppender` 只追加真实安装/商店回执、`AppInstallReceiptQuery` 供准出读取。禁止脚本或 Provider 直连绕过 port。
- 包身份隔离：alpha/beta/gamma/prod 与 Debug/Release 使用不覆盖的 application/bundle ID、显示名与签名映射。
- 正式身份来源：Prod 正式 ID 只取已登记外部事实，非 Prod/Debug 使用隔离后缀并同步 Universal/App Links、OAuth、推送与 Keychain/App Group。
- 签名分发边界：Debug 签名制品仅限开发者本机、Simulator/Emulator 与登记设备；TestFlight、市场与官网只接受 Release。
- 制品格式与渠道解耦：`AppArtifactManifest` 携带显式 `artifactFormat(apk/aab/ipa/app/web)`，由打包请求声明或按平台默认推导，禁止由 distributionClass 推导（原 `store → AAB` 耦合废除）；官网与全部 APK 市场引用同一 release APK source digest，`aab` 仅当已启用渠道 capability 硬性要求时按 DEC-005 构建一次。
- 正式 Android 身份：`com.leadwise.quwoquan`（vivo 开放平台已登记外部事实）；Java namespace 与 applicationId 分离，微信回调 Activity 按 applicationId 约定放置。iOS 正式 Bundle ID 仍缺已登记外部事实，store 渠道保持阻断。
- 渠道逐项声明：每渠道登记 `channelId`、`uploadFormat(ipa/aab/apk)`、package/bundle ID、store product ID、track、version/build、developer signing identity、store signing custodian、可能的 split/optimize/re-sign transformation、source candidate/artifact/launch-manifest digest、upload/review/release receipt 与安装后 signature/receipt 校验方式。`uploadFormat` 只声明渠道接受能力，不驱动构建。市场可能重签或优化，准出不要求下载二进制逐字节相同，而以 source digest、version/build、store 官方签名/receipt、嵌入 launch manifest 与启动 telemetry 绑定；一个渠道的回执不得替代另一渠道。
- 官网分发：Android 官网 APK 复用 official distribution 部署到不可变 CDN 对象并出带 SHA-256 的 receipt，发布前通过包名/签名证书摘要/Build/SHA-256 预验证门禁；`app_release` 契约字段是恢复页、更新提示与网页安装组件共用的唯一下载真相源。iOS 网页版不提供二进制下载。
- 灰度顺序：先内测或分阶段，再公开发布。
- 快速止损：内容 active pointer、Web current pointer 与远端配置的止损在 300 秒内完成，且不要求重新打包或再次审核。
- 商店回滚边界：已安装商店 App 不可强制回滚，服务保留商店客户端 N/N-1 兼容面，禁止把“重新发版”当唯一恢复动作。
- 被否决方案：单一 applicationId/bundle ID 覆盖安装、Debug 包进入市场、要求市场下载物逐字节等同上传物、把内容 release 绑进商店二进制、side-load 冒充市场安装回执。
- 关联要求：`REQ-001`
- 影响 Story：[`gray-release-to-prod`](./gray-release-to-prod/spec.md)、[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)
- 关联验收：[`environment-topology-and-packaging GWT-003`](../runtime-config/environment-topology-and-packaging/spec.md#gwt-003)、[`app-release-recovery-routing GWT-004`](../../product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-004)、[`cold-start-performance GWT-005`](../runtime-client-foundation/cold-start-performance/spec.md#gwt-005)

<a id="dec-005"></a>
### DEC-005 组件构建身份：build once、环境无关、按 digest 复用
- 决策：打包的唯一职责是把一份受审源码闭包变成一份带可验证身份（真实 bytes digest + 签名 + provenance：源码依赖闭包、工具链、签名身份）的不可变字节；选环境、选渠道、选灰度阶段、注入 endpoint 都不属于构建。可执行字节只按 `nonprod/prod` 两个信任域分叉（applicationId、签名、entitlements、三方 SDK 注册身份），环境是部署与激活期的数据输入。
- 最小构建矩阵：Android `nonprod.apk` + `prod.apk`（`com.leadwise.quwoquan`，同一签名 APK 复用官网与全部 APK 市场）；`prod.aab` 仅当已启用渠道 capability 硬性要求时构建一次。iOS `nonprod/prod` 两个身份/签名档位，不按环境重编译。Web 一份 immutable bundle。云侧每组件/OS/arch 按 `nonprod/prod` 两个信任域各构建一次：alpha/beta/gamma 复用同一 nonprod digest，prod 独立 digest。环境名、config digest 与 rollout stage 不得写入镜像字节。
- 云侧信任域裁决：external Provider binding 经编译期 overlay 固化为 Go 二进制内的单环境 `CompiledBindingFor` 视图，是防止 provider substitute 进入 prod 的最强供应链阻断，本决策保留该编译期固化而不改为运行时挂载数据。代价是云镜像不能四环境同 digest，只能按信任域二分——与 App 侧 nonprod/prod 档位完全对称。前提是 alpha/beta/gamma 三环境的 `externalBindings` 声明收敛为同一 nonprod 档内容；环境身份文件（`artifact-identity.json`）与 platform-ops 环境配置树改为部署面挂载物料，从镜像字节中移除。
- 配置外置三层通道：编译与制品封装层不接受 endpoint 类 define，也不携带 target runtime package；AppArtifact 只内置 build-profile 级信任根。安装后 activation 层由 stackctl/canonical launcher 将带 schema 版本的签名 runtime config package 原子写入平台私有容器，可独立重发与回滚而不重编、不重签 AppArtifact。服务端 bootstrap 层下发内容绑定身份、最低支持版本与 feature flag 等运行时事实，灰度阶段不在此列。cache/tag 不授予准出资格，复用时仍 100% 验证 exact digest、producer、SBOM、provenance 与签名。
- 被否决方案：按环境重复编译（12 份 App 制品、4 套云镜像）、按渠道打不同 APK、嵌入渠道号或渠道 SDK 分支、把 rollout stage 写入制品、自建 APK 差分（商店差分由渠道免费提供，开发者永远上传全量包）。
- 约束与影响：身份后缀与 flavor 的 `nonprod` 统一切换必须与 producer/reader 同增量原子完成，切换前 `environment_suffixes` 仍是唯一现行身份派生轨，不得双轨；`app_artifact_manifest.yaml` 的 `build_profiles` 是本决策的 metadata 冻结面。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)、[`gray-release-to-prod`](./gray-release-to-prod/spec.md)
- 关联验收：`SIT-001`

<a id="dec-006"></a>
### DEC-006 发布组合身份 releaseCompositionId 与重建指令解耦
- 决策：`releaseCompositionId` 是对有序组件摘要、环境配置摘要与 ContractGraph/迁移兼容摘要求出的 digest，`evidenceSetDigest` 独立散列测试、Provider 与资格证据并允许在同一软件组合上刷新；两者都排除 OCI 仓库/tag、transport locator、channelId、灰度阶段与运行时审核状态。候选不是重建指令：App-only change 的新候选引用原 Cloud 组件摘要，Cloud builder invocation 必须为 0，反之亦然；渠道回执、审核状态与灰度阶段变化均不产生新候选。
- OCI 边界：`repository@sha256:...` 只用于 CI 内部不可变搬运与 provenance，不进入候选身份，也不强制进入分发回执。
- 被否决方案：把全仓 transport locator、channel/receipt/stage 混入候选摘要（任何分发事件都会伪造“新候选”并触发全量重建）、端云双交付单元各自持有第二套身份、为每用途生成独立制品身份。
- 约束与影响：`canonical_digests.py` 及聚合器、校验器、timing gate 必须在同一受审增量原子切换，不保留双 publisher/双 reader/运行时 flag；失败只允许 Git revert 后继续使用上一 immutable candidate。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)
- 关联验收：`SIT-001`

<a id="dec-007"></a>
### DEC-007 部署/分发执行与回执 owner 边界
- 决策：CI/CD release/distribution control plane 是渠道分发动作与原始回执的唯一 owner。渠道分发回执只保留 `releaseCompositionId`、source artifact digest、`channelId`、version/build、平台侧脱敏 ID/状态、权威 readback 摘要与时间，每渠道独立且不复制 APK。灰度激活是 Platform Ops 拥有的流量策略：激活回执单独绑定 `releaseCompositionId`、策略 revision、stage、SLO 判定与时间，`policyDigest` 只属于激活决策。`canary/5/20/50/100` 不改变 APK、镜像、配置包或候选身份，App 全程无感知灰度阶段。Product Ops 只消费“最低可用版本、更新/恢复入口、当前公开版本”等只读投影，无分发执行权、不保存市场 Attempt、不持有市场凭据。
- 指针条件更新：Web `current` 与 Android `latest` 的 compare-and-swap 只是“预期当前值一致才切换”的部署并发保护，不属于打包，不进入候选身份。
- 数据边界：数据不是交付物，从不进入任何包。内容只经 canonical immutable content release activation 进入四环境；行为数据只允许非生产由测试数据控制面经领域公开 command/event 构造，Prod 在首条 mutation 前拒绝。
- 被否决方案：Product Ops PostgreSQL 保存分发 Attempt/Receipt、Integration runtime 代理应用市场发布、把审核/回执/CAS/OCI/policy 塞进打包身份、灰度 stage 写入 IaC 制品。
- 约束与影响：应用市场分发只消费“Cloud 已达到允许公开的稳定状态”，不拥有也不推进灰度；市场安装事实在首个商用闭环前不得以静态渠道登记、side-load 或官网安装替代。
- 关联要求：`REQ-001`
- 影响 Story：[`gray-release-to-prod`](./gray-release-to-prod/spec.md)
- 关联验收：`SIT-001`

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
- App 构建耗时必须读取 Android nonprod/prod、iOS nonprod/prod 与 Web shared 五个实际 Jobs API 节点并取最大值。任何 shard 缺失时 timing gate 失败，不允许回退到 static/serial 近似值。
- 独立可观测：每域 `service.name` + 指标维度独立，使“逻辑独立”在合并部署时依然成立，并为拆分提供数据依据。
