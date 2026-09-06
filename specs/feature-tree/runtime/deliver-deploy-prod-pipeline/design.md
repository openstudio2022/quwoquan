# L2 Design：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚”需要 `daily-merge-release-strategy`、`gray-release-to-prod`、`local-gamma-mirror`、`multi-environment-instance-isolation`、`multi-environment-wave-deployment`、`workflow-naming-consolidation` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让本地环境生产源码质量、GitHub验证不可变信任，并以RC资格与stable标签选择解耦main最新源码和Prod激活。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：scoped candidate 可经本地 A/B 准入后由 trusted publisher CAS 更新 dev，也可由匹配 integration worktree 仅以 non-force fast-forward 提交源码；`dev1.0 -> main` 只做可用源码 promotion。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：integration scheduler只对current exact dev head生产Gamma与晋级资格。
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
### DEC-001 源码晋级、发布资格与生产激活采用分离的不可变身份链
- 决策：lane 或 integration writer 以私有 Git index 和不重叠整文件 scope 构造 `ExactIntegrationCandidate`；Environment Ops在detached candidate上生产Alpha及conditional Beta，trusted integration publisher验证前驱后可按既有通道以expected-old非force CAS更新`dev1.0`。唯一`integration/`工作区还可从匹配本地`refs/heads/dev1.0`用普通认证Git push执行non-force fast-forward源码更新，必须以pre-push update line的before/after OID和Git ancestry authority证明；缺OID、authority不可用、非快进、force/delete或来源不匹配全部fail closed。该direct push只提交源码，不签发`integrationEligibility`、Alpha/Beta/Gamma、`IntegrationQualificationFact`、promotion、release或Prod authority；integration scheduler仍仅对current exact dev head生产Gamma和`IntegrationQualificationFact`，后续promotion/release仍消费exact candidate + Alpha/Beta及既有资格链。
- 决策：`dev1.0 -> main`是availability promotion而非release pipeline。唯一required context只验证synthetic merge tree、current refs、审批、ruleset和不可变IntegrationQualificationFact；合入后`MainSourceSeal`证明source-admitted。GitHub promotion禁止执行build、源码测试、ABG、Provider live、设备与环境命令，SLI只计算`promotionReadyAt -> mainReadbackAt`。
- 决策：`main`是最新可用源码，不是待发布版本或Prod selector。普通main push零build、零tag、零production effect；临时验证只使用无Git ref的SemVer-compatible dev artifact identity。
- 决策：`ProductVersionManifest`是目标SemVer的唯一authoring source，单一active release train。发布意图由annotated `vMAJOR.MINOR.PATCH-rc.N`锚定main-reachable commit；RC触发build/sign/SBOM/provenance once及最终包/Provider/UAT/物理设备资格，生成`QualificationFact`。源码、版本投影或material变化必须创建下一RC。
- 决策：product owner选择qualified RC，release owner批准campaign，唯一controller在独立Environment授权后创建同commit、同material/build number/digests的annotated `vMAJOR.MINOR.PATCH`，并经Hosted readback形成`ReleaseTagAdmissionFact`。RC与stable ref均create-only，update/delete无bypass；stable不重新构建。
- 决策：Prod唯一输入为stable tag AdmissionFact绑定的exact OCI digests、source/control-plane SHA与previous-stable ledger identity。production approval后只物化一次，由`stackctl`在同一事务完成`canary -> 5 -> 20 -> 50 -> 100`；回滚只选择ledger证明的历史released digests。`main HEAD`、裸SHA、latest、repository variable和transport tag均不是authority。
- 决策：证据链采用canonical JSON、DSSE/in-toto envelope与create-once OCI/hosted append-only store；后继引用前驱exact bytes。切换后只接受当前schema；兼容读取、并行写入、可变指针降级和workflow success推导全部禁止。
- 并发与恢复：candidate parent/CAS漂移使candidate及A/B事实失效；unknown ref update先按before/after/other readback。Gamma被新head替代时未mutation任务取消，已mutation任务只安全teardown并记录superseded。promotion backsync仍使用expected-before fast-forward CAS，分叉阻断。
- 五分钟观测：目标p95固定300秒，enforcement budget只可由固定UTC 14日全样本窗口、nearest-rank p95和连续K个qualified窗口单调收紧；不使用阶段状态、success-only、rerun重置、样本过滤或放宽例外。
- 理由：把本地质量生产、托管信任验证、产品发布选择和运行激活分开，既能把源码晋级压缩到API验真级延迟，又不会把main最新状态或标签名误当作已验证制品与生产状态。
- 被否决方案：main push重跑ABG/build并自动Prod、GitHub self-hosted生产本地环境事实、RC到stable重建、标签移动/删除、latest-qualified自动选择、按版本号猜回滚、临时成熟度阶段与长期兼容双轨。
- 关联要求：`REQ-001`、`REQ-003`
- 影响 Story：[`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)、[`gray-release-to-prod`](./gray-release-to-prod/spec.md)、[`local-gamma-mirror`](./local-gamma-mirror/spec.md)、[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)、[`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 prod-hosted 扩容是同一 ssh-hosted 集群内的 member×instance×replica
- 决策：生产扩容不新增环境名，也不恢复 K8s/ACK 第二执行面。`quwoquan_ops/environments/prod/access-isolation.yaml` 拥有 `management.hosts` 与 `deploymentInstances.{prevalidate,gray,prod}.replicas`；`stackctl` / `deploy_to_prod.sh` / `render_prod_plane_stack.py` 只消费该拓扑。
- 理由：当前可运行真相源已是 SSH + rootless Podman；规格若继续写 ACK Deployment 会制造第二主线。单 member / 单 replica 必须保持兼容。
- 被否决方案：`prod-gray` 环境、另建 cluster topology 文件并与 access-isolation 形成双真相源、按 replica 各自独立 ledger 绕过 service-plane CAS。
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
- 决策：App 分发以三个分离对象承载事实——`AppArtifactManifest`（属于 `app_factory_material` / `CandidateMaterialManifest` exact-byte 物料闭包、由 app factory producer 写入实际 payload 并由 qualification reducer 验证的 immutable owned entity，不属于 `ReleaseEvidenceManifest`；拥有 platform、BuildMode、distributionClass、package/bundle ID、version/build、signing identity、source/artifact/launch-manifest digest 与 promotability）、`InstallReceipt`（按 store/device/build 追加且集合无界的 separate append-only fact，独立生命周期与查询）、渠道矩阵（从 canonical metadata 生成，覆盖 Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝与官网 `official_web` APK）。打包、签名校验、安装与渠道登记统一走 `stackctl package` 的 canonical App 入口（显式 `env/platform/build-mode/distribution-class/device`），`run.sh` 与 IDE 只做薄包装。
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
- 约束与影响：身份后缀与 flavor 的 `nonprod` 统一切换必须与 producer/reader 同增量原子完成，切换前 `environment_suffixes` 仍是唯一现行身份派生轨，不得双轨；`quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml` 的 `build_profiles` 是本决策的 metadata 冻结面。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)、[`gray-release-to-prod`](./gray-release-to-prod/spec.md)
- 关联验收：`SIT-001`

<a id="dec-006"></a>
### DEC-006 发布组合身份 releaseCompositionId 与重建指令解耦
- 决策：候选身份（沿用字段名 `candidateId`，语义收窄为 releaseCompositionId）是对有序组件摘要、环境配置摘要与 ContractGraph/迁移兼容摘要求出的 digest，排除 OCI 仓库/tag、transport locator、channelId、分发回执、灰度阶段与运行时审核状态。候选不是重建指令：App-only change 的新候选引用原 Cloud 组件摘要，Cloud builder invocation 必须为 0，反之亦然；渠道回执、审核状态与灰度阶段变化均不产生新候选。
- OCI 边界：`repository@sha256:...` 只用于 CI 内部不可变搬运与 provenance，不进入候选身份，也不强制进入分发回执。
- 被否决方案：把全仓 transport locator、channel/receipt/stage 混入候选摘要（任何分发事件都会伪造“新候选”并触发全量重建）、端云双交付单元各自持有第二套身份、为每用途生成独立制品身份。
- 约束与影响：`quwoquan_ops/ci/release_qualification.py` 的 CandidateMaterial canonical digest/reducer 及聚合器、校验器、timing gate 必须在同一受审增量原子切换，不保留双 publisher/双 reader/运行时 flag；`quwoquan_ops/ci/release_evidence_reader.py` 仅作为命名历史读侧，不是正式 candidate identity owner；失败只允许 Git revert 后继续使用上一 immutable candidate。
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

<a id="dec-008"></a>
### DEC-008 factory actual bytes 到 Prod 终态采用单一 authority 链
- 对象与 owner：Service/App factory material producer 分别拥有其 immutable actual payload bytes；release qualification 的 validator/reducer 物化两个 factory exact ref，验证 canonical bytes 后拥有唯一 `CandidateMaterialManifest`；release tag controller 只选择并 exact 引用同一 CMM，不生成、改写或归约物料；qualified Prod owner 独占 `ProdActivationAdmissionFact`、`ProdStageAttemptFact`、`ProdReleasedFact`、`ProdRollbackFact` 与 `PostReleaseSoakFact`；official distribution 保留 package/channel 校验与逐渠道回执，但只消费 stable admission、Qualification、CMM 与 app factory exact-byte 闭包，不拥有 release selection、admission 或 Prod authority。
- Command/query 分流：formal effect command 只接受 stable `ReleaseTagAdmissionFact` exact ref，并先物化 `ProdActivationAdmissionFact` envelope 后交给 `stackctl`；qualification 与 Prod query 只从 exact refs 回读并物化 CMM/factory actual bytes，不接受调用方字段副本。公开 `package --kind release-manifest` writer 与 formal `--release-manifest` surface 必须删除。历史诊断只暴露命名读侧 `validate_legacy_non_promotable_snapshot` / `validate_historical_release_snapshot`，不得存在 generic `validate` alias、writer、verdict、admission 或向 formal command 转接的动态 attribute/import surface。
- 一致性、幂等与物料闭包：CMM 创建前必须复验 factory actual payload 的 canonical bytes、`materialDigest`、source/tree、qualification request、RC、signature 与 attestation；Service factory 还须包含 Prod runtime config/deployment bundle exact digest，App official distribution 固定沿 stable → Qualification → CMM → app factory → `AppArtifactManifest` 取包，并继续验证 package bytes、source/tree、package/channel identity 与独立 channel receipt。workflow scalar、OCI transport tag 与 local cache 只能定位或加速，不能成为 authority。
- 终态约束：每次 stage execution 追加一个 `ProdStageAttemptFact`，失败重试必须创建新 attempt；同一 activation 的 stage `100` passed 只允许 create-once 一个 `ProdReleasedFact`。activation/rollback 必须 exact 引用 previous `ProdReleasedFact` 及 rollback readiness，rollback 形成独立 terminal；soak 只 exact 引用 current `ProdReleasedFact`。任一前驱、actual bytes 或 hosted readback 漂移都须在首个 mutation 前 typed `GATE_BLOCK`，不得写 activation、stage、released、rollback 或 soak 成功事实。
- 原子切换顺序：同一 scoped candidate commit 内先交付 factory actual-byte validator 与 Service config/deployment bundle closure，再切 formal Prod 和 official distribution consumer，最后删除 public writer、formal option 与旧 finalizer；禁止先删除输入、compat shim、dual-read/dual-write 或 warn-only fallback。`prevalidate` / `prod-sim` 只可经上述两个命名 legacy reader 读取 historical/non-promotable snapshot，物理与调用图均不得进入正式链。
- 失败恢复与测试 seam：tag 选择与 readback 沿用 owner 已声明的 `RELEASE_TAG.STALE`、`RELEASE_TAG.QUALIFICATION_INVALID`、`RELEASE_TAG.READBACK_INVALID` 等 typed code；其他边界只使用其 canonical owner contract 已声明的错误，缺少适用错误契约即在 mutation 前 `GATE_BLOCK`，本设计不新增 wire code。local contract 必须覆盖 actual payload tamper，以及 source/tree/request/RC/signature/attestation/config closure 漂移；CLI 与动态 import/attribute gate 必须证明 REM writer、formal option、generic legacy alias 均不可达；API/hosted readback seam 必须覆盖 stage `100` create-once、retry 新 attempt、released/rollback terminal 排他、soak exact predecessor；official distribution seam 必须覆盖 app factory、package bytes、source/tree、channel identity 与逐渠道 receipt 不变量。
- 理由：将“生产了哪些真实字节”“哪些物料通过资格归约”“stable 选择了哪份 CMM”“Prod 实际激活及终态”“App 发往哪个渠道”拆给各自 owner，可消除 REM/CLI/finalizer 第二权威，同时让篡改、重试、回滚和外部阻断都能按 exact predecessor 恢复。
- 被否决方案：从 workflow scalar 重建 CMM、以 OCI tag/local cache 代替 actual bytes、release tag 或 official distribution 重新归约物料、stage status 就地更新、stage `100` 重写 released terminal、用 generic legacy validator 回流 formal、先删输入再补 consumer、compat shim 或双读过渡。
- 关联要求：[`REQ-001`](./spec.md#req-001)、[`REQ-003`](./spec.md#req-003)
- 影响 Story：[`gray-release-to-prod`](./gray-release-to-prod/spec.md)、[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)
- 关联验收：[`SIT-001`](./spec.md#sit-001)、[`gray-release-to-prod GWT-001`](./gray-release-to-prod/spec.md#gwt-001)、[`multi-environment-wave-deployment GWT-001`](./multi-environment-wave-deployment/spec.md#gwt-001)

## 5. 失败与恢复

- 失败类型：分支 policy 无效、PR/ref 非法、`main` direct push、integration push 缺 before/after OID或 ancestry authority、integration/backsync 非 fast-forward、force/delete、ref compare-and-swap 冲突、Prod source 不可达 main、权限拒绝、依赖超时、候选摘要冲突、证据缺失或持久化失败。
- 可见结果：调用方收到稳定 `OPS.BRANCH.*` 或父能力 canonical failure；任何失败均不写 promotion、candidate、backsync、deploy 或 rollback 成功事实。
- 恢复动作：非法 PR/ref 修正 head/base 后重试。backsync equal 幂等完成，安全 ancestor 可重读后重试。`dev1.0` 分叉时停止并要求人工裁决，不创建临时分支或 force。push 返回成功但 readback 未知时禁止盲重试，先从权威 ref 回读。after 等于 promotion OID 时收口成功，after 仍等于 before 时可安全重试，其他值冻结 eligibility。远端权限、网络、ancestry 或 hosted authority 不可确认时停止并保留 before/after readback。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。
- factory/CMM/Prod 恢复：exact-byte 校验、签名/attestation、配置闭包、hosted readback 或 predecessor 失败时保持零 production/distribution mutation；修复 authority 或生产下一 RC 后以新 command 重试，不改写原 fact。stage 失败只可按 exact previous released terminal 与 rollback readiness 回滚；attempt outcome 未知时先 hosted readback，同一 outcome 幂等收口，确认失败后新建 attempt，禁止覆盖旧 attempt。
- 外部阻断：生产主机、凭据、审批、Provider、真实设备、渠道审核或 hosted authority 不可用时保留 typed blocker 与最后可证明的 exact ref；prevalidate、prod-sim、历史 snapshot、Actions success 或旧 receipt 都不得包装为正式 Prod/渠道成功。

## 6. 质量与观测

- 分支治理由 Platform Ops owner 记录 `branch_policy_decision_total{event,status,reasonCode}`、`branch_backsync_terminal_seconds{status}`、`branch_ref_readback_complete_total{ref,status}` 与 `branch_release_eligibility_total{status,reasonCode}`；每条 attempt 绑定 repository、run/attempt、promotion SHA、before/after OID 和 evidence digest，脱敏 receipts 保留至少 90 天。
- 每个 policy/admission attempt 的 reason 覆盖率与 ref readback 完整率目标为 100%。成功 promotion 后 backsync 在 300 秒内进入 success、idempotent 或 blocked 终态的月度目标为 99%。任一无 reason decision、readback 缺失、`main/dev1.0` 分叉、未授权 main source 取得 eligibility 或 backsync 超过 300 秒立即触发 Platform Ops P1 告警。外部 GitHub 不可用时保持 fail-closed，不用 availability 降级换取放行。
- `prod-hosted` 的正式灰度 workflow 必须人工 dispatch 并保留 approval；在 Provider、SFU、真实数据、观测、灾备或回滚证据缺失时只允许不可提升 prevalidate，且 post-deploy probe 置信度仍须单独验收。
- 运行装配从各服务 `environments/<env>/deploy`、Ops 同名环境入口和真实 Compose/Kustomize 扫描推导；本地端口保留 `local_env_port_manifest`，prod rollout 保留 `gray_rollout_stages`，服务配置由自治 package 的 provenance 摘要证明。
- 每个 Prod rollout stage 必须执行 `stackctl health + inspect + doctor + integration probes + slo gate`；任一失败写入 GATE_BLOCK/rollback 证据，不得由 workflow 合成成功。
- factory/CMM/activation/stage/terminal/soak 观测必须记录 exact predecessor digest、authority、run/attempt、stage、decision、typed reason 与 hosted readback 摘要；required actual-byte/readback 与 reason 覆盖率目标均为 100%，缺任一项立即阻断。stage health/SLO 阈值只消费 canonical rollout policy，不在 workflow scalar 或本设计复制；真实 Prod 外部阻断与 rollback 不计作 passed 样本，也不得提升 release/distribution 状态。
- App 构建耗时必须读取 Android nonprod/prod、iOS nonprod/prod 与 Web shared 五个实际 Jobs API 节点并取最大值。任何 shard 缺失时 timing gate 失败，不允许回退到 static/serial 近似值。
- 独立可观测：每域 `service.name` + 指标维度独立，使“逻辑独立”在合并部署时依然成立，并为拆分提供数据依据。
