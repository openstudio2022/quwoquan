# L2 Business Capability：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以本地环境生产质量、托管控制面生产信任：worktree 候选完成 Alpha/Beta，integration 对精确 `dev1.0` head 完成 Gamma，GitHub 只验真并将可用源码晋级到 `main`；有发布意图的 main 提交经不可变 RC 资格验证后，才可由正式 SemVer 标签选择并按精确 OCI digest 灰度发布。

## 2. 范围与非目标

### In Scope

- `dev1.0 -> main` 五分钟源码 promotion、受信 publisher CAS、integration worktree non-force fast-forward 源码提交、不可变环境/资格/标签证据与 OCI digest-only 发布
- prod-hosted ssh-hosted + rootless Podman 单一执行面，modular-monolith-first 工作负载图谱，托管数据面
- 同一 `prod-hosted` 内 `cluster member × deployment instance × replica` 可重复部署与聚合 CAS
- Strangler split-ready 拆分与契约不变
- gamma-local 与 prod-hosted 工作负载图谱同构

### Out of Scope

- 新增 beta-hosted / prod-gray 等额外环境名
- 恢复 Kubernetes / ACK / `PROD_KUBECONFIG` / `kubectl` 作为第二发布执行面
- 多业务容器共享 Pod / sidecar 承载领域职责 / 集群内自建数据库 StatefulSet 默认

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；为所有 Journey 提供同一候选的受控集成、发布、环境验证、灰度与回滚证据。
- 本能力接收已授权的精确 Git SHA 与 immutable candidate，输出直属 Story 组合的可观察结果；失败时保留已确认事实并返回可恢复的 canonical failure。

## 4. Story



- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：lane 与 integration 都可构造 exact candidate；`dev1.0` 可由受信 publisher 在 Alpha/Beta 准入后 CAS 更新，也可由匹配 integration worktree 执行 non-force fast-forward 源码 push；`main` 只接收 `dev1.0 -> main` 可用源码 promotion。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：Gamma 只对精确 current `dev1.0` head 生产 IntegrationQualificationFact；不由 GitHub 执行，也不被 Alpha/Beta 或历史回执替代。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：同一 source release train 预先封存 nonprod/prod 组件与四环境配置 composition，按 alpha、beta、gamma、prod 的准入顺序验证，任一波次失败即停止晋级。
- [`service-core-composition`](./service-core-composition/spec.md)：以同一 Go host 组合 11 个核心服务而不改变领域契约、数据归属或独立实时/模型故障域。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 本地质量、托管验真与标签驱动发布

- Source writer 只生产绑定 exact candidate 的源码事实；worktree 或 integration 中不重叠文件可并行编辑，但 Git index、commit/ref、共享生成物、环境、设备、package 与外部 mutation 必须由单一受信执行者串行提交。
- Environment Ops 必须在尚未移动 `dev1.0` 的 detached exact candidate 上执行 Alpha，并仅对 typed 高风险影响执行 Beta；两者通过后，trusted integration publisher 可按既有通道以 expected-old 的非 force fast-forward CAS 更新 `dev1.0`。此外，匹配 `integration/dev1.0` 可用 update line 的 before/after OID 经 ancestry 证明执行普通认证 non-force fast-forward 源码 push；缺 OID、authority 不可用、非快进、force/delete 或来源不匹配均 fail closed。direct push 不签发 `integrationEligibility`、Alpha/Beta/Gamma、`IntegrationQualificationFact`、promotion、release 或 Prod authority；需要晋级/发布时仍须 exact candidate + Alpha/Beta、current dev head Gamma 与既有后续资格链。
- integration scheduler 只对 current exact `dev1.0` head 执行 Gamma，封存 `IntegrationQualificationFact`；Gamma 必须绑定同一 candidate/tree 和 Alpha/Beta exact-byte predecessor，不得无差别重跑相同 CaseResult。新 head 使旧事实不再适用于当前 promotion。
- `dev1.0 -> main` 的唯一 required context 只验证 branch/head/base/merge tree、审批、ruleset、IntegrationQualificationFact、签名、时效、policy/workflow pin 与 secret/generated 边界；不得安装语言工具链、构建、运行源码测试、ABG、Provider live、设备或环境命令。合入后 `MainSourceSeal` 只授予 `source-admitted`，不授予发布资格。
- promotion PR 只携带两项输入：`IntegrationQualificationFact` 及其完整前驱证据树（Alpha/Beta/Gamma 事实、publish result/admission、candidate 与全部命名证据）的一个不可变 OCI bundle exact ref，以及 `promotion_ready_at`。审批、评审线程、ruleset 与 changed-path 边界四类 authority 事实由该 required context 自己从 hosted readback 生产并绑定 exact head/base，PR 作者不得预先自述；审批事件（`pull_request_review`）触发同一 context 重新评估，而不是人工重跑。post-merge handoff 以 GitHub Actions 原生 integration 创建的 create-once check-run 承载，其身份就是 main ruleset 信任的 required check 身份，不引入第二个 GitHub App。
- `main` 永久表示最新可用源码。普通 main push 不构建、不签名、不打标签、不进入 production；临时验证仅产生绑定 commit/tree 与 OCI digest 的短时 dev artifact identity。
- 只有 annotated `vMAJOR.MINOR.PATCH-rc.N` 可启动一次性 build/sign/SBOM/provenance 与最终包/Provider/UAT/物理设备资格验证。`service_factory_material` 与 `app_factory_material` 必须先作为不可变 OCI 物料落地；资格归约者须物化实际 payload 并验证 canonical bytes、`materialDigest`、source/tree/request/RC、签名与 attestation，且 Service 物料须绑定 Prod runtime config/deployment bundle 的 exact digest 闭包，之后才可生成 `CandidateMaterialManifest`。workflow scalar 只可定位物料，不具备事实权威。
- 唯一正式发布链固定为 `service_factory_material` / `app_factory_material` → `CandidateMaterialManifest` → `QualificationFact` → stable `ReleaseTagAdmissionFact` → `ProdActivationAdmissionFact` → `ProdStageAttemptFact*` → `ProdReleasedFact` → `PostReleaseSoakFact`；所有后继均以 canonical bytes digest 引用 create-once 前驱，Actions Artifact 只作诊断。
- 产品选择已 qualified RC 后，唯一 controller 才能创建与该 RC 指向同一 commit、复用同一 build number、`CandidateMaterialManifest` 与 OCI digests 的 annotated `vMAJOR.MINOR.PATCH`；正式标签不得移动、删除、重建或指向 tag object。App official distribution 只从 stable `ReleaseTagAdmissionFact`、`QualificationFact`、`CandidateMaterialManifest` 与 `app_factory_material` 的 exact-byte 闭包读取正式包。
- Prod 唯一入口是 stable `ReleaseTagAdmissionFact`，并须在首个 stage 前物化一个 `ProdActivationAdmissionFact`；生产事务只消费其中已经 exact-byte 验证的 `CandidateMaterialManifest`、factory material 与 OCI/config bundle 闭包，在一次 approval/物化后由 `stackctl` 完成 `canary -> 5 -> 20 -> 50 -> 100`。
- 正式 Prod 不得消费或生成 `ReleaseEvidenceManifest`、`releaseEvidenceRef`、`--release-manifest`、public release-manifest writer 或任何 lifecycle status transition。previous/rollback 只引用 hosted ledger 中 exact `ProdReleasedFact` 及其 rollback readiness；soak 只引用当前 exact `ProdReleasedFact`，不得读取 `main HEAD`、裸 SHA、mutable tag、repository variable 或“最新 qualified”。
- 运行时不得保留旧新 schema 双读、dual-write、warn-only fallback 或第二套发布入口。

<a id="req-002"></a>
### REQ-002 prod-hosted ssh-hosted 部署形态（modular-monolith-first + split-ready）SIT

- `prod-hosted` 唯一执行后端是 `ssh-hosted` + 平面隔离 Linux 账号 + rootless Podman/compose/user systemd；禁止恢复 K8s/ACK/`kubectl`/`PROD_KUBECONFIG` 第二执行面。
- 首发形态由各第一方服务自治 workload、external 实时/媒体 workload 和平台装配共同组成；不存在组合业务 `seed-box`，无 sidecar 承载领域职责。
- 三层正交边界成立：领域服务是逻辑真相源，compose project / systemd unit 是部署单元，`cluster member`（SSH 主机）是物理执行面。
- `prevalidate` / `gray` / `prod` 是同一 hosted 目标内的 deployment instance，不是环境枚举。
- 拓扑真相源为 `quwoquan_ops/environments/prod/access-isolation.yaml` 的 `management.hosts` + `deploymentInstances.*.replicas`；单 member / 单 replica 是默认兼容形态，扩容只追加 host 与 co-located replica placement。
- 正式 rollout 必须对每个 `hostId × plane × replicaId` 产出独立 runtime receipt，并由 service-plane hosted ledger 做聚合 CAS；任一成员缺失、失败或 digest 漂移不得推进 stage / 写入 `full` 成功事实。
- 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / topology resolver 对同一 workload 图谱解释一致。

<a id="req-003"></a>
### REQ-003 验证执行面与证据分层

- Alpha/Beta/Gamma 的正式 producer 必须位于受控本地 Environment Ops 执行面；GitHub-hosted 与 GitHub self-hosted workflow 均不得执行 ABG、Data mutation、设备 Journey 或环境 cleanup。
- Alpha 是默认真实依赖最小闭包；Beta 仅由 typed 高风险 impact 启用；Gamma 只对 exact current `dev1.0` head执行。`no_live` 必须生成绑定 candidate 与 ImpactPlan 的 `not_required` fact，不能从 skipped 推导。
- 环境 PASS 仅在 package identity、startup、full health、受影响 CaseResult、readback、inspect/doctor、finally teardown、lease revoke 与端口释放全部闭合后封存为唯一 `EnvironmentAcceptanceFact`；Beta/Gamma 分别引用前驱 exact bytes。
- 模拟器或仿真器只支持本地集成事实并显式 `nonPromotable`；最终签名包的 Android/iOS 物理设备接受属于 RC qualification，不进入五分钟 promotion，也不重跑 ABG 业务矩阵。
- GitHub 只验证不可变证据并承担 RC build/sign/attest、资格归约、正式 tag admission 和 Prod approval/transaction。普通 source push、lane PR、promotion PR 不得触发 packaging、coverage 全量、设备矩阵、Provider live 或 environment workflow。
- Nightly 只运行 fingerprint-aware 的深度回归、性能与可靠性，不轮转环境、不替代任何 candidate/head/RC 的 required fact，也不改变资格、标签或生产状态。
- `prevalidate` / `prod-sim` 历史 snapshot 仅允许显式 `non-promotable` / history reader 只读；它们不得产生 admission 或 verdict，也不得进入正式发布链。
- promotion 的固定 SLI 为 `promotionReadyAt -> mainReadbackAt`，包含 queue、验真、merge 与 ref readback，不包含 ABG、产品等待、qualification、tag、Prod 或 soak。目标 p95 为 300 秒；当前 enforcement budget 只可按固定窗口的完整全样本算法单调收紧，不得分阶段、success-only、重置计时或放宽。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_ops/environments`、`quwoquan_ops/environments/prod/kustomization.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 本地质量、五分钟源码晋级与标签发布

- GIVEN exact candidate、当前 refs、ImpactPlan、产品版本目标及其 owner evidence 均有效。
- WHEN writer 请求集成、promotion、RC qualification、正式标签选择或 Prod 发布。
- THEN Alpha/Beta 只在受信 publisher CAS 通道移动 branch ref 前对同一 detached candidate 执行，publisher 只在 required facts 通过后 CAS 更新 `dev1.0`；匹配 integration worktree 的 direct fast-forward push 只移动源码 ref且不产生这些事实，Gamma 仍只对 current exact dev head 封存资格。
- THEN promotion workflow 只验不可变事实并在预算内生成 `MainSourceSeal`；main 前移既不启动资格构建，也不改变既有 RC、stable tag 或 Prod active digest。
- THEN RC 对精确 main 提交只构建和签名一次；资格归约者物化并验证实际 `service_factory_material` / `app_factory_material` canonical bytes 及 Service Prod runtime config/deployment bundle 闭包，生成唯一 `CandidateMaterialManifest` 后，才以最终包/Provider/UAT/物理设备事实生成 `QualificationFact`。
- THEN stable tag 与选中 RC 指向同一 commit 并复用同一 `CandidateMaterialManifest`；App official distribution 沿 stable/Qualification/CandidateMaterialManifest/app factory exact-byte 闭包取包，Prod 沿 `ReleaseTagAdmissionFact → ProdActivationAdmissionFact → ProdStageAttemptFact* → ProdReleasedFact → PostReleaseSoakFact` 在一个受审批事务中完成灰度与 readback。
- THEN 正式 Prod 不接受 `ReleaseEvidenceManifest`、`releaseEvidenceRef`、`--release-manifest`、public release-manifest writer 或 lifecycle status transition；失败回滚只引用 exact previous `ProdReleasedFact` 与 rollback readiness，soak 只引用 exact current `ProdReleasedFact`。
- THEN 任一正式前驱或后继的 exact bytes 漂移均在 mutation 前 fail closed；`prevalidate` / `prod-sim` 历史 snapshot 不能进入正式链，且不存在 GitHub ABG、重复 build、mutable-latest 输入、双读双写或伪成功事实。

<a id="sit-002"></a>
### SIT-002 prod-hosted ssh-hosted 部署形态（modular-monolith-first + split-ready）SIT

- GIVEN 执行“prod-hosted ssh-hosted 部署形态（modular monolith first + split ready）”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“prod-hosted ssh-hosted 部署形态（modular monolith first + split ready）”对应动作。
- THEN `prod-hosted` 从服务自治部署入口扫描装配第一方 workload，实时/媒体 external workload 独立归 Ops，且不存在组合业务 `seed-box` 或承载领域职责的 sidecar。
- THEN 执行面仅为 SSH + rootless Podman；`stackctl prod-hosted-plan` / `deploy_to_prod.sh` 按 `host × deployment instance × replica` 迭代，单 host 默认仍可解析。
- THEN 每个 placement 有独立 remote root / compose project / systemd unit / config ACK identity；gray 与 prod placement 共置匹配以便本机 gray router handoff。
- THEN 正式 ledger commit 的 `postChecks` 覆盖全部期望 placement；部分成功不得聚合 CAS。
- THEN 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- THEN Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- THEN `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / topology resolver 对同一 workload 图谱解释一致。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 deliver deploy prod pipeline 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：正式 Prod 仍残留 `ReleaseEvidenceManifest` / `releaseEvidenceRef` / `--release-manifest` 读写与 lifecycle status 语义，factory material actual-byte 校验和 terminal fact 单轨尚未完成原子切换。
- 目标：本地 Alpha/Beta、dev head Gamma、五分钟 evidence-only promotion，以及从实际 factory material 到 `PostReleaseSoakFact` 的唯一正式链闭合；删除正式 Prod 的 release-manifest 与生命周期状态第二轨。
- 完成判定：`SIT-001` 全部结果子句由职责匹配的 current local_contract/api_integration/user_acceptance 直接绑定并通过，且门禁证明正式入口不存在被禁止的 release-manifest surface

<a id="open-002"></a>
### OPEN-002 prod-hosted 多 member 真实远端放量

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仓内已具备多 host/replica plan、渲染 identity、部署迭代与聚合 CAS 合同；真实第二台 ECS、平面 SSH 凭据与一次完整 `canary → 5 → 20 → 50 → 100` 仍缺。
- 目标：在声明 ≥2 个 `management.hosts` 与匹配 replica placement 的前提下，用真实 SSH 完成多 member 发布、逐 host receipt 与 ledger 聚合 CAS。
- 完成判定：`SIT-002` 对应 live 行为满足，且 `SIT-001` 的正式链、terminal fact、rollback/soak exact predecessor 与 mutation-before-block 结果由同一次真实 rollout 证实并有有效 `spec_ref`

<a id="open-004"></a>
### OPEN-004 正式 Android 身份外部登记同步

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：正式 Android applicationId 已冻结为 `com.leadwise.quwoquan`（vivo 开放平台已登记）；微信/QQ/支付宝开放平台回调、Firebase/推送、App Links/OAuth、其余市场后台与签名证书登记仍需按新身份同步。任一外部平台存在其他 applicationId 登记时保持 `GATE_BLOCK`，禁止同时发布两个身份。iOS 正式 Bundle ID 仍缺已登记外部事实。
- 目标：完成全部外部平台对 `com.leadwise.quwoquan` + 生产签名证书摘要的登记，并以渠道 readback 证明一致。
- 完成判定：`SIT-001` 下 `stackctl store-channels` 对已启用渠道的身份 readback 与 `app_artifact_manifest.yaml` 一致，且 DEC-004 正式身份条目无冲突登记

<a id="open-005"></a>
### OPEN-005 build-once 构建矩阵原子切换未完成

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前流水线仍按四环境重复编译 App（12 份）与云镜像（4 套），`environment_suffixes` 仍是唯一现行 App 身份派生轨，`candidateId` 摘要仍混入环境专属制品输入；DEC-005/DEC-006 已冻结目标身份但尚缺实现与验收证据。
- 目标：按 DEC-005/DEC-006 完成统一 nonprod 包身份切换、runtime config 外置、组件按 digest 复用与 producer/reader 原子 cutover，删除四环境重复编译路径且不保留双轨。
- 实现约束：Android native runtime package 现由 Gradle 从 `dart-defines` property 抄写生成（iOS plist 由 build phase 同理派生），endpoint define 的移除必须与原生注入通道改造、nonprod/prod flavor 收敛及 pipeline producer 在同一受审增量内原子切换，不得先行单独删除 define 造成注入源断供。注入通道改造时 runtime config package 一并携带 schema 版本、签发时间与 source tree digest，App 启动握手校验 staleness，过期即进入阻断式配置错误页而不是继续裸跑。
- 云侧实现约束：镜像环境分叉的物理来源有三。其一，所有一方 Dockerfile 把 `QWQ_ARTIFACT_ENVIRONMENT`/`QWQ_ARTIFACT_CONFIG_DIGEST` 烤入 `/etc/quwoquan/artifact-identity.json`（`runtime/artifactidentity/identity.go` 启动时用 `APP_ENV` 断言匹配，reader 已支持 `QWQ_ARTIFACT_IDENTITY_FILE` 挂载路径覆盖）。其二，platform-ops 把整棵环境配置树拷进镜像 `/app` 并以 `REPO_ROOT=/app` 消费。其三也是最深的一处：external Provider binding 按环境选择（非生产 provider substitute 与 prod 真实三方互斥），经 `QWQ_PROVIDER_BINDING_MANIFEST_DIGEST` overlay 在编译期固化为 Go 二进制内的 `CompiledBindingFor` 单环境视图，`verify_cloud_environment_artifact_binding.py` 门禁同时强制这三处存在且禁止生产源码做运行时环境选择。
- 云侧信任域裁决（DEC-005 已定）：保留 Provider binding 编译期固化这一防 substitute 进 prod 的最强供应链阻断，云镜像收敛为 `nonprod/prod` 两档而不是四环境同 digest，与 App 档位对称。实施前提：alpha/beta/gamma 的 `externalBindings` 声明先收敛为同一 nonprod 档内容（当前 integration-service 与 product-ops-service 存在个别能力 enabled/not_required 差异）。落地时须同一受审增量内：身份文件与环境配置树改为部署面挂载物料、binding overlay 输入从每环境改为每信任域、反转 `environment_artifact_identity.yaml` 与 `manifest_validation.py` 的"repository 环境绑定 + 跨环境 digest 禁令"为"nonprod 三环境同 owner 必须同 digest、prod 独立"、收敛 `plan_service_release_images.py` 矩阵与 `service_pipeline.yml` 计数 gate，并同步 stackctl 本地环境装配与全部 release local_contract fixture。
- 完成判定：`SIT-001` 下同一候选的 App 构建为 nonprod/prod 两档、Cloud 组件按信任域两档且 alpha/beta/gamma 同 owner 同 digest，App-only change 的 Cloud builder invocation 为 0

<a id="open-006"></a>
### OPEN-006 Vivo 首链真实市场分发闭环

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前分发编排工具链已就位——`stackctl store-channels` 渠道准入门、`stackctl store-distribution` 逐渠道 append-only 分发回执（fan-out 强制同一 candidate 的全部 android 渠道引用同一 release APK digest）、`InstallReceipt` 契约与官网 latest 指针条件更新；仍缺 vivo 开发者凭据在位后的一次真实上传、审核、上架、市场客户端下载安装与首启兼容闭环。静态渠道登记、side-load 或官网安装不得替代市场安装事实。
- 目标：以同一 reviewed Prod APK 完成 vivo 首链：上传与审核回执经 `store-distribution` 登记，上架后从 vivo 市场客户端安装并产出 `channelId=vivo_market` 的 InstallReceipt 与启动 telemetry。其他市场复用同一分发编排与同一 source digest，仅凭据、审核与公开能力按平台独立，不新增渠道专包。
- 依赖：`QWQ_VIVO_DEV_CREDENTIAL_PATH` 凭据文件、vivo 开放平台审核通过、真机市场安装通道。
- 完成判定：`SIT-001` 下 vivo_market 存在 uploaded→published 完整回执链与 verified InstallReceipt，且回执 artifactDigest 与官网 latest 指针引用同一 release APK source digest

<a id="open-003"></a>
### OPEN-003 300 秒止损演练执行证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺一次带计时 receipt 的真实演练验收证据，无法证明三条止损路径各自在 300 秒内完成。三条工具链实现均已存在且不触发重打包：内容 active pointer 回上一 immutable release（`quwoquan_data ship rollback`）、Web current pointer 回上一 artifact（`stackctl deploy --artifact-kind web --expected-current` CAS 切换）、远端配置关闭不兼容能力（`GetAppConfig` kill_switches `immediate`）；演练仍依赖运行中的环境和可回切的上一 release/artifact。
- 目标：在 `gamma-local` 对三条止损路径各执行一次演练，产出含开始/结束时间戳与恢复验证的机器 receipt，全程无打包/编译步骤。
- 完成判定：`SIT-001` 的 auto rollback 可验证子句满足，且演练 receipt 证明三条路径耗时 ≤300 秒并有真实 `spec_ref` 绑定
