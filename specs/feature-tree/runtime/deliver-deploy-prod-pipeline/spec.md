# L2 Business Capability：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计引用：[本层 design.md](./design.md)

## 1. 能力目标

以本地环境生产质量、托管控制面生产信任：worktree 候选完成 Alpha/Beta，integration 对精确 `dev1.0` head 完成 Gamma，GitHub 只验真并将可用源码晋级到 `main`；有发布意图的 main 提交经不可变 RC 资格验证后，才可由正式 SemVer 标签选择并按精确 OCI digest 灰度发布。

## 2. 范围与非目标

### In Scope

- `dev1.0 -> main` 五分钟源码 promotion、受信 publisher CAS、规范 linked worktree 持验真 admission 的 non-force fast-forward 发布、不可变环境/资格/标签证据与 OCI digest-only 发布
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



- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：lane 与 integration 都可构造 exact candidate；lane 在 source-admitted required 本地门禁与 typed Alpha/Beta（默认 `not_required`，仅显式 opt-in 真跑）通过后产出 bundle，并可在同一工作树验真 admission 后以受信 non-force fast-forward 通道一条命令发布 `origin/dev1.0`，不依赖远端 lane、lane PR 或换工作区；`main` 只接收 `dev1.0 -> main` 可用源码 promotion。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：Gamma 只对精确 current `dev1.0` head 生产 IntegrationQualificationFact；不由 GitHub 执行，也不被 Alpha/Beta 或历史回执替代。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：同一 source release train 预先封存 nonprod/prod 组件与四环境配置 composition，按 alpha、beta、gamma、prod 的准入顺序验证，任一波次失败即停止晋级。
- [`service-core-composition`](./service-core-composition/spec.md)：以同一 Go host 组合 11 个核心服务而不改变领域契约、数据归属或独立实时/模型故障域。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 5. 能力要求

- 生产治理的简化范围仅为 `administrative`：合并冗余人工审批、复用同一 exact 输入的既有有效证据并去除重复 CI；不削弱 main promotion、stable tag、签名和 exact 物料、health、Provider、回滚/恢复等技术门，不跳过 required 失败，不从该简化取得直接放量授权。实际生产操作仍经现有正式入口、技术前驱与对应授权边界，未实测 OPEN 不关闭。

<a id="req-001"></a>
### REQ-001 本地质量、托管验真与标签驱动发布

- Source writer 只生产绑定 exact candidate 的源码事实；不重叠文件可并行编辑，默认 Git index/commit/ref 与共享生成物仍独占串行。环境、设备、package 与外部 mutation 按各自实际资源授予唯一执行权，不使用跨环境全局互斥：云侧按 host-target 单实例，设备按 device/application 独占，构建只锁私有输出，独立 target 可持续并行。租约、executor fence、容量及 owned cleanup 由 [`multi-environment-instance-isolation` REQ-001/004](./multi-environment-instance-isolation/spec.md#req-004) 拥有；资格前驱与 Prod 授权顺序不变。
- lane `make accept` 必须在远端 `dev1.0` 移动前对 exact candidate 完成去重后的 required 本地检查（source-admitted Lane Gate 闭集：静态治理、ImpactPlan/changed boundary、canonical Code Health Delta；不含 `lane_gate:ops-local-contract:*`、`focused:dart`、`focused:go:*`、`scope_build:*`）与 typed Alpha/Beta（默认 `not_required`：Alpha=`ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV`，Beta=`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`；仅显式 `--alpha`/`--beta` 真跑），产出 portable acceptance bundle；缺 required 源码检查或 typed 环境事实不得 accepted。显式 `PUBLISH=1` 时同一 run 在同一 lane 工作树继续 admit 并发布，不换工作区、不移动 lane HEAD；`integration/dev1.0` 消费他树 bundle 的两段式是同一 admission/CAS 通道的等价形态，不是第二真相源。最终 publisher 独立验证 admission 自摘要、exact 前驱/签名/有效期、candidate/tree、before/after、规范 linked worktree 与 hub origin/remote 及 ancestry，以 expected-old non-force FF 发布并读回；缺/伪造/漂移 admission、外来 clone 或非规范 hub/origin、仅 `QWQ_ACCEPTANCE_PUBLISH=1` 或非快进均零远端写入。`integrationEligibility` 仅由 exact admission 建立，push 不重新签发环境及后续资格。日常 dev 合入只要求本地 accept/bundle/integrate/hook 强制验真，不重跑完整套件；专用 publisher/broker 与 hosted 资格强制保持 daily-merge OPEN-004 `track`，不阻塞该本地通道。按授权撤除 dev 旧 `04. Lane Gate` required check，已可达已发布 dev 且未发布增量已保全的远端 lane 可删除，无需等待替代门。服务端普通授权凭据仍可 FF，不能保证 Alpha；dev 禁删/禁 non-FF 和 main promotion 强制继续保留。晋级仍须已发布 current dev head 的 Gamma/IQF → `dev1.0 -> main` PR/Delivery Gate → MainSourceSeal → 受管 system backsync → 已发布 dev exact SHA → 本地 lane，同步不得传播本地未发布 dev。
- integration scheduler 只对 current exact `dev1.0` head 执行 Gamma，封存 `IntegrationQualificationFact`；Gamma 必须绑定同一 candidate/tree 和 Alpha/Beta exact-byte predecessor，不得无差别重跑相同 CaseResult。新 head 使旧事实不再适用于当前 promotion。
- `dev1.0 -> main` 的唯一 required context 只验证 branch/head/base/merge tree、审批、ruleset、IntegrationQualificationFact、签名、时效、policy/workflow pin 与 secret/generated 边界；不得安装语言工具链、构建、运行源码测试、ABG、Provider live、设备或环境命令。合入后 `MainSourceSeal` 只授予 `source-admitted`，不授予发布资格。
- promotion 的 required evidence 必须包含当前 `main baseSha → dev1.0 headSha/tree` 完整差异的 canonical `full` Code Health Delta；与 canonical ImpactPlan、policy、implementation 和 evidence fingerprint 精确绑定。包装层 `status=passed`、最后一次 push 健康事实或仅 IQF 均不能替代完整 promotion range。健康报告缺失、字节漂移、错误 range/tree、`fast` 或 `GATE_BLOCK` 必须在 admission 前拒绝；`PR_WARN` 只消费既有 Review health disposition contract 对当前 report/finding 的裁决，缺失裁决时 fail closed，不建立第二评分或裁决 schema。
- promotion PR 只携带两项输入：`IntegrationQualificationFact` 及其完整前驱证据树（Alpha/Beta/Gamma 事实、publish result/admission、candidate 与全部命名证据）的一个不可变 OCI bundle exact ref，以及 `promotion_ready_at`。审批、评审线程、ruleset 与 changed-path 边界四类 authority 事实由该 required context 自己从 hosted readback 生产并绑定 exact head/base，PR 作者不得预先自述；审批事件（`pull_request_review`）触发同一 context 重新评估，而不是人工重跑。post-merge handoff 以 GitHub Actions 原生 integration 创建的 create-once check-run 承载，其身份就是 main ruleset 信任的 required check 身份，不引入第二个 GitHub App。
- `main` 永久表示最新可用源码。普通 main push 不构建、不签名、不打标签、不进入 production；临时验证仅产生绑定 commit/tree 与 OCI digest 的短时 dev artifact identity。
- 只有 annotated `vMAJOR.MINOR.PATCH-rc.N` 可启动一次性 build/sign/SBOM/provenance 与按声明交付目标适用的资格验证。`service_factory_material` / `app_factory_material` 中被交付目标及其真实依赖要求的物料必须先作为不可变 OCI 字节落地；资格归约者须物化实际 payload 并验证 canonical bytes、`materialDigest`、source/tree/request/RC、签名与 attestation，且 Service 物料须绑定 Prod runtime config/deployment bundle 的 exact digest 闭包，之后才可生成 `CandidateMaterialManifest`。workflow scalar 只可定位物料，不具备事实权威。
- 唯一正式发布链固定为 `service_factory_material` / `app_factory_material` → `CandidateMaterialManifest` → `QualificationFact` → stable `ReleaseTagAdmissionFact` → `ProdActivationAdmissionFact` → `ProdStageAttemptFact*` → `ProdReleasedFact` → `PostReleaseSoakFact`；所有后继均以 canonical bytes digest 引用 create-once 前驱，Actions Artifact 只作诊断。
- 产品选择已 qualified RC 后，唯一 controller 才能创建与该 RC 指向同一 commit、复用同一 build number、`CandidateMaterialManifest` 与 OCI digests 的 annotated `vMAJOR.MINOR.PATCH`；正式标签不得移动、删除、重建或指向 tag object。App official distribution 只从 stable `ReleaseTagAdmissionFact`、`QualificationFact`、`CandidateMaterialManifest` 与 `app_factory_material` 的 exact-byte 闭包读取正式包。
- Prod 唯一入口是 stable `ReleaseTagAdmissionFact`，并须在首个 stage 前物化一个 `ProdActivationAdmissionFact`；生产事务只消费其中已经 exact-byte 验证的 `CandidateMaterialManifest`、factory material 与 OCI/config bundle 闭包，在一次 approval/物化后由 `stackctl` 完成 `canary -> 5 -> 20 -> 50 -> 100`。
- 正式 Prod 不得消费或生成 `ReleaseEvidenceManifest`、`releaseEvidenceRef`、`--release-manifest`、public release-manifest writer 或任何 lifecycle status transition。previous/rollback 按 `REQ-005` 使用唯一存在性契约：有 prior 时只引用 hosted ledger 中 exact `ProdReleasedFact` 及其 rollback readiness，无 prior 时必须引用受信 absent 证明与未激活安全态恢复证据；soak 只引用当前 exact `ProdReleasedFact`，不得读取 `main HEAD`、裸 SHA、mutable tag、repository variable 或“最新 qualified”。
- 运行时不得保留旧新 schema 双读、dual-write、warn-only fallback 或第二套发布入口。

<a id="req-002"></a>
### REQ-002 prod-hosted ssh-hosted 部署形态（modular-monolith-first + split-ready）SIT

- `prod-hosted` 唯一执行后端是 `ssh-hosted` + 平面隔离 Linux 账号 + rootless Podman/compose/user systemd；禁止恢复 K8s/ACK/`kubectl`/`PROD_KUBECONFIG` 第二执行面。
- 首发形态由各第一方服务自治 workload、external 实时/媒体 workload 和平台装配共同组成；不存在组合业务 `seed-box`，无 sidecar 承载领域职责。
- 三层正交边界成立：领域服务是逻辑真相源，compose project / systemd unit 是部署单元，`cluster member`（SSH 主机）是物理执行面。
- `prevalidate` / `gray` / `prod` 是同一 hosted 目标内的 deployment instance，不是环境枚举。
- 拓扑真相源为 `quwoquan_ops/environments/prod/access-isolation.yaml` 的 `management.hosts` + `deploymentInstances.*.replicas`；单 member、每个执行 plane 一个 replica 是合法默认配置，扩容只追加 host 与匹配的 co-located replica placement。单机与多机共用一个 canonical expected inventory 完整性算法，不以至少两台主机或每 plane 至少两个 replica 作为正式 rollout 的必要条件，不新增单机兼容开关、版本分支或旧算法。
- 正式 rollout 的期望集合必须从当前 stage 对应 deployment instance 的完整 inventory 派生，包含声明的全部 service/edge placement；host/plane/service 过滤不得缩小正式验收集合。空集合、缺 plane/placement、重复 replica identity、同 instance/plane 在同 host 的固定发布口冲突、未知或不支持该 plane 的 host、管理端点与 inventory 不符、service/edge 或 gray/prod 共置身份不匹配，均在任何远端 mutation 前拒绝。
- 正式 rollout 必须对每个期望 `hostId × plane × replicaId` 产出绑定本次 instance、candidate/config digest 的独立 runtime receipt 与 ACK。service-plane hosted ledger 仅在全部 expected placement 的结果逐一且唯一通过、无缺项/重复/意外或错误 host、无失败或 digest 漂移时聚合 CAS；部分成功不得推进 stage / 写入 `full` 成功事实，CAS 前 inventory 漂移同样阻断。
- topology 通过只证明 inventory 完整，不豁免任何安全、权限、容量、Provider、数据恢复、资格、审批、health/SLO 或正式 readback 门。单机共置仍是一个物理故障域，必须如实保留 candidate/stable 资源竞争、宿主故障同时影响 service/edge 与恢复不可用的风险；未取得容量与恢复实证不得声称已可部署、跨故障域高可用、零中断或达到新的 RPO/RTO。
- 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / topology resolver 对同一 workload 图谱解释一致。

<a id="req-003"></a>
### REQ-003 验证执行面与证据分层

- Alpha/Beta/Gamma 的正式 producer 必须位于受控本地 Environment Ops 执行面；GitHub-hosted 与 GitHub self-hosted workflow 均不得执行 ABG、Data mutation、设备 Journey 或环境 cleanup。
- 写入 `origin/dev1.0` 是 source-admitted：默认不跑 live Alpha，只签 typed `not_required`（`ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV`）；live Alpha 仅显式 opt-in，证明已发布源码能装能起，不是日常合入必跑门。Beta 只在 lane 验收显式 opt-in 时真跑，否则不按集成深度分流，统一以政策原因码 `ACCEPTANCE.BETA_OPTIONAL_BY_POLICY` 签绑定 candidate 与 ImpactPlan 的 typed `not_required` fact，不能从 skipped 推导；Gamma 只对 exact current `dev1.0` head 执行，与可选 prod canary 一起构成 integration 侧仅有的两级集成验证（见 [L2 DEC-014](./design.md#dec-014)）。
- 环境 PASS 仅在 package identity、startup、full health、受影响 CaseResult、readback、inspect/doctor 与本次 owned cleanup/lease closure 全部闭合后封存唯一 EnvironmentAcceptanceFact；新建资源按授权 teardown 并证明端口释放，复用的健康 runtime 保持运行且只释放本次 exact lease，不为签发事实 down 其他 target。Beta/Gamma 仍引用前驱 exact bytes；Alpha 离线 App 结果不能替代 Alpha 服务 gate 或环境资格。
- 模拟器或仿真器只支持本地集成事实并显式 `nonPromotable`；iOS Simulator 验收不产生真机或分发资格。最终签名包的 Android/iOS 物理设备接受属于含 App 移动包交付目标的 RC qualification，不进入五分钟 promotion，不因服务资格通过而补写，也不重跑 ABG 业务矩阵。
- GitHub 只验证不可变证据并承担 RC build/sign/attest、资格归约、正式 tag admission 和 Prod approval/transaction。普通 source push、lane PR、promotion PR 不得触发 packaging、coverage 全量、设备矩阵、Provider live 或 environment workflow。
- Nightly 只运行 fingerprint-aware 的深度回归、性能与可靠性，不轮转环境、不替代任何 candidate/head/RC 的 required fact，也不改变资格、标签或生产状态。
- `prevalidate` / `prod-sim` 历史 snapshot 仅允许显式 `non-promotable` / history reader 只读；它们不得产生 admission 或 verdict，也不得进入正式发布链。
- `stackctl verify --verification-purpose core-diagnostic` 是 Gamma 与 Prod prevalidate 共用的只读/受控业务核心诊断 selector：只汇总同一 exact candidate、Data release、apply、activate 与 binding 下的现役 Data/Ops/App verifier，不签 formal environment readiness。六项 feature 闭集为 `identity|feed-detail|search-recommendation|image-video-range|post-write-readback|chat-write-readback`；缺 selected required case 必须失败，未选择项明确 `not_executed`。报告恒为 `nonPromotable=true`、`releaseEligibility=GATE_BLOCK`、`readinessWritten=false`。
- 该 selector 默认不要求 M10、Beta predecessor、lifecycle Exit 或 premium；显式选择相应现役正式能力时仍服从其 owner 门。默认 formal verify 完全不变，M10 无 Beta 等既有拒绝继续生效。Prod 只接受 `target=prod-hosted`、`deployment-instance=prevalidate` 与 `data-mode=isolated`；正式 Prod、external binding 或隔离不可证均在业务请求前拒绝。
- `prevalidate` 另接受 integration 工作区的 exact dev candidate rehearsal：候选必须由当前干净工作树以 canonical prod-hosted 打包入口生成并绑定 `sourceRevision`/tree，HEAD 必须等于本地 `refs/heads/dev1.0`，且候选内容身份等于 HEAD——`sourceRevision` 等于 HEAD，或者（打包入口按内容寻址复用既有不可变候选时）`sourceRevision` 是 HEAD 的祖先且两者之间没有任何打包输入路径的改动；镜像为本机 build-once 的 `linux/amd64` content digest，只经 exact digest 校验交付到目标平面账号；只进入 `prevalidate` deployment instance、`data-mode isolated` 与独立 namespace，结果固定 `nonPromotable=true`、`releaseEligibility=GATE_BLOCK`，零 ledger/receipt/admission/tag/stage 写入，不得进入正式链，也不得替代 Gamma、RC qualification 或 prod canary 证据。隔离数据面可接受 canonical immutable content release 的 hosted-import 与 activation（既非 seed 也非正式生产数据），其 readback 只构成 rehearsal 诊断。rehearsal 候选允许 legal-static 主体字段仍为占位，但必须在候选与报告中显式标记，且不构成任何法务、登录商用或发布证据；rehearsal 的公网入口由宿主共享 edge 按 Host 分流并以宿主自身 ACME 承接，不属于 `public-ca-prod` 签发自动化，也不构成 DNS/TLS 准出证据。
- promotion 的固定 SLI 为 `promotionReadyAt -> mainReadbackAt`，包含 queue、验真、merge 与 ref readback，不包含 ABG、产品等待、qualification、tag、Prod 或 soak。目标 p95 为 300 秒；当前 enforcement budget 只可按固定窗口的完整全样本算法单调收紧，不得分阶段、success-only、重置计时或放宽。

<a id="req-004"></a>
### REQ-004 唯一资格链按声明交付目标限定适用范围

- 服务端部署与 App 分发是独立交付目标，不是两条发布系统。受控 `QualificationRequest` 在构建前显式声明非空交付目标及适用平台/渠道范围，并由既有 request authority 批准；省略、空范围、未知目标或运行时推断均拒绝。请求范围必须与实际 effect 一致，不由 factory 是否成功、缺失字段、workflow skipped 或环境变量倒推；已封存请求不得减项绕过失败，范围变化必须重新按既有 RC/request 生命周期申请，禁止改写旧事实。
- 唯一 qualification reducer 根据声明目标与真实依赖验证 expected material/evidence 闭包，生成同一 `CandidateMaterialManifest` 与限定范围的 `QualificationFact`；stable controller、Prod admission 和 App distribution 逐级校验该范围及 exact predecessor，不能把 `qualified` 当成无范围全产品通过。factory 中存在某平台字节不等于获准分发该平台；仅声明服务目标可以没有非依赖 App 移动包，但必须覆盖服务实际部署依赖的全部字节，例如服务部署包含 Web 静态物料时该物料及供应链仍必需，不能因其 factory 来自 App 就跳过。
- 服务部署资格只要求所选服务 artifact/factory 的 build/sign/attest、Prod config/deployment bundle、同 source/material 的真实服务测试、适用环境/Provider/UAT 与恢复证据。其资格不以未选择的 App 移动包真机或渠道审核为前置，也不产生 App 安装、设备、渠道或分发资格；服务 activation 的既有 previous released/rollback readiness、生产审批与 SoD 保持不变。
- 含 App 移动包交付目标时，实际签名包、包身份、供应链、适用 Provider/UAT 和 Android/iOS 双物理平台接受仍是必需证据，不因选择 iOS Simulator 验收而缩减；各渠道继续独立要求对应签名、审核、分发及真实安装回执，不互相代替。未选择或未取得 required 证据的 App/渠道保持 not-ready/不具备资格，Simulator/Emulator 始终只形成 `nonPromotable` 本地事实，服务通过不得衍生 App 通过。
- 同一请求同时声明服务部署与 App 分发时，两类 required 闭包均须满足才可签发该请求的 Qualification/stable admission；不能以服务分项通过签发联合成功，不能删去 App 字段把联合请求变成服务请求。后续 effect 只可消费已声明且通过的目标；App-only 资格不允许执行服务部署，服务-only 资格不允许分发 App。各目标内部真正的依赖仍由 canonical material/contracts 决定，解耦不是任意省略材料。
- Human 审批、产品选择、SoD、签名 authority、build-once、OCI exact ref/bytes、tag create-only 与 `dev1.0 → main` 唯一 promotion 通道均不变；不另建 service-only reducer/controller/入口，不保留 V1/V2、历史兼容、dual-read 或 warn-only。本文只冻结适用语义，字段与错误码由既有 qualification/CMM/admission contract owner 原子落地后才能执行，未表达范围的旧形状不能在切换后当成默认完整资格。

<a id="req-005"></a>
### REQ-005 首次无 prior 与有 prior 升级共享同一生产生命周期

- Prod admission 必须持有当前目标 prior 存在性的明确结果：合法 present 绑定 exact previous `ProdReleasedFact`、active ledger generation、实际 digest 与 rollback readiness；合法 absent 绑定受信 hosted ledger/history、完整 target inventory 与公开流量入口的只读证据，证明真正无 active released、无未解释的既往发布或在途 activation，且目标处于可验证的未激活安全态。缺字段、空对象或查询失败不是 absent；超时、权限不足、receipt 丢失、inventory 不完整、残留未受管服务/路由、历史状态矛盾均为 unknown 并阻断 admission。
- 首个产品 release train 的人工激活只授权版本列车，不证明 Prod 没有 prior，也不授权首发恢复。正式首发另须既有受信 Human request/approval 明确首次部署意图，并 exact 绑定服务交付目标、stable admission、service/CMM/必要 Web 物料、环境/target、完整 inventory、absent 证明及恢复边界；继续满足签名、SoD、容量、备份恢复和所有 required checks，不新增 bootstrap 发布入口或本地自述权威。
- absent/present 是同一个必填 prior 契约的互斥当前形态，不是 schema 版本、运行模式或可选 bypass 标志。present 不允许省略 previous identity 或走首发恢复；absent 不填写假的 previous released/old image/空摘要，不可引用本次 candidate 自身、Data empty baseline、prevalidate/rehearsal 或 initial release train authority 替代。存在旧发布但当前停流、撤销、故障或 active 指针丢失时仍不能宣称首次；先由现役恢复与 readback 解析真实历史。
- 首次成功仍经相同 activation、ordered stage attempts 和 stage 100 的 create-once `ProdReleasedFact`；达到相应阶段准入前公共非授权流量保持关闭，canary 仅允许受控验证流量，后续放量按原阶段政策执行。无 stable fallback 不能转发到未知 upstream 或当作旧版本 healthy；不能提供安全入口与全部原阶段证据时 fail closed，不改变灰度阈值和 soak 窗口。
- 首次失败必须先关闭本次 candidate 对外业务流量并证明受管入口不再路由到候选，再停用本次 attempt 明确拥有的服务进程/自动重启单元和尚未激活的发布配置，保持目标未激活。持久数据、volume、媒体、备份、恢复点、审计与其他共存工作负载必须保留；已经产生的数据或不可逆迁移不自动回退、删除或伪称不存在，须有事前恢复/隔离证明和必要的单独授权。首发恢复只能报告“已恢复未激活安全态”或恢复失败，不得报告回滚到上一版本、生成 previous `ProdReleasedFact` 或为失败尝试启动 soak。
- absent 证明必须绑定同一 hosted authority 的 expected generation/无 active 前值与完整 inventory，在首个 mutation 前及成功/恢复终态 CAS 前重新验真；并发首次部署只允许一个 winner。首次失败恢复后保留 append-only 历史与新 generation，不重置为全新空 ledger；后续重试须证明该未激活终态与无成功 prior，重新绑定授权和前值，不能沿用旧 absent 快照。CAS 或远端执行 outcome unknown 时先 exact command/attempt/readback，无法区分未执行、已成功或部分执行时停止，不能盲重试、猜空或改写事实。
- target观察的保护必须由默认host上的既有service-plane ledger authority授予，并由完整inventory每个plane的受管executor实际持有到子进程收口；本机controller锁或单独ledger读锁不足以证明全target一致。配置/路由/unit/公开指针的全部writer共用该执行权，私有不可见staging与已准入exact运行身份的正常重启不被误判为发布切换；未覆盖writer、孤立子进程、participant失联或guard漂移均阻断完整观察。observe至Human consume与activation CAS必须连续持有同一execution owner/generation；释放后旧观察不得交接，租约到期不能证明远端停止，细则归`DEC-015`。
- 若实现缺少正式停流、停用 attempt-owned unit、保留资源与安全态 readback 的受管能力，则首发仍为 `GATE_BLOCK`。修改共享公网入口、迁移/删除既有数据、覆盖共存服务或涉及不可逆恢复的动作须额外明确授权；单机首发总目标不自动授权这些动作。本文只冻结行为与互斥设计，具体字段/path/错误码由后续 canonical admission/ledger/recovery contracts 单轨落地，禁止旧新事实兼容读取。

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
- THEN lane 在远端 ref 移动前对同一 exact candidate 完成 source-admitted required 检查与 typed Alpha/Beta（默认 `not_required`；仅显式 opt-in 真跑）并产出 bundle；integration 在本地 FF 前验真 bundle/parent，最终 publisher 独立验真 admission 后才 expected-old FF 发布 `dev1.0`。缺 bundle、仅 env=1、前驱/身份漂移或 non-FF 均零写；这些拒绝由本地受管入口执行，不推导服务端 Alpha 强制；hosted broker 缺口为 OPEN-track，撤 dev 旧 required check 后仍须保留禁删/禁 non-FF 与 main promotion。Gamma 仅对已发布 current exact dev head 封存资格。promotion 后 MainSourceSeal 由受管 system backsync 消费，读回 dev `after` 才回同步本地 lane。
- THEN promotion admission 读取 required evidence 内部 exact bytes 并验证完整 base/head/tree 的 canonical full 健康报告：缺失、stale、wrong-range、只覆盖最后 push、fast、blocker 或未裁决 PR_WARN 均拒绝；current full PASS 或按既有 Review contract 裁决通过的 PR_WARN 才可继续。
- THEN promotion workflow 只验不可变事实并在预算内生成 `MainSourceSeal`；main 前移既不启动资格构建，也不改变既有 RC、stable tag 或 Prod active digest。
- THEN RC 对精确 main 提交按请求声明交付目标及真实依赖只构建和签名一次；资格归约者物化并验证适用的 factory canonical bytes 及 Service Prod runtime config/deployment bundle 闭包，生成唯一 `CandidateMaterialManifest` 后，才以对应目标的真实证据生成限定范围的 `QualificationFact`；含 App 移动包目标时最终签名包与物理设备事实仍必需。
- THEN stable tag 与选中 RC 指向同一 commit 并复用同一 `CandidateMaterialManifest`；App official distribution 沿 stable/Qualification/CandidateMaterialManifest/app factory exact-byte 闭包取包，Prod 沿 `ReleaseTagAdmissionFact → ProdActivationAdmissionFact → ProdStageAttemptFact* → ProdReleasedFact → PostReleaseSoakFact` 在一个受审批事务中完成灰度与 readback。
- THEN 正式 Prod 不接受 `ReleaseEvidenceManifest`、`releaseEvidenceRef`、`--release-manifest`、public release-manifest writer 或 lifecycle status transition；有 prior 的失败回滚只引用 exact previous `ProdReleasedFact` 与 rollback readiness，无 prior 的失败只可按 `REQ-005` 恢复受管未激活安全态而不伪造 released；soak 只引用 exact current `ProdReleasedFact`。
- THEN 任一正式前驱或后继的 exact bytes 漂移均在 mutation 前 fail closed；`prevalidate` / `prod-sim` 历史 snapshot 不能进入正式链，且不存在 GitHub ABG、重复 build、mutable-latest 输入、双读双写或伪成功事实。

<a id="sit-002"></a>
### SIT-002 prod-hosted ssh-hosted 部署形态（modular-monolith-first + split-ready）SIT

- GIVEN 执行“prod-hosted ssh-hosted 部署形态（modular monolith first + split ready）”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“prod-hosted ssh-hosted 部署形态（modular monolith first + split ready）”对应动作。
- THEN `prod-hosted` 从服务自治部署入口扫描装配第一方 workload，实时/媒体 external workload 独立归 Ops，且不存在组合业务 `seed-box` 或承载领域职责的 sidecar。
- THEN 执行面仅为 SSH + rootless Podman；`stackctl prod-hosted-plan`、正式 `stackctl deploy` 与 `deploy_to_prod.sh` 按同一 canonical inventory 解释 `host × deployment instance × replica`。声明一台 host、service/edge 各一个 replica 且共置匹配的完整配置可通过各正式 stage 的拓扑门；增加合法 host/replica 后仍由相同算法覆盖全部声明 placement，不存在单机豁免或旧算法分支。
- THEN 每个 placement 有独立 remote root / compose project / systemd unit / config ACK identity；service/edge 及 gray/prod 的 replica identity 与 host 共置匹配以便本机 gray router handoff。缺 plane/placement、重复 replica identity、同 instance/plane 同 host 固定发布口冲突、未知/错误 host、管理端点漂移或共置错配均在远端 mutation 前失败；过滤出看似完整的子集不能替代整个 expected inventory。
- THEN 正式 ledger commit 的 `postChecks` 与独立 runtime receipt/ACK 逐一且唯一覆盖全部 expected placement，并绑定本次 instance、candidate/config digest；缺项、重复、意外或错误 host、失败、摘要漂移以及 CAS 前 inventory 变化均阻断聚合 CAS。部分成功不写 `full`、不推进 stage，不以后一份同名成功覆盖前一份失败或重复证据。
- THEN 不同主机数量不改变安全、权限、容量与恢复门；授权目标的真实逐 replica receipt、ACK、health/SLO 与 hosted ledger readback 一致且完整后才可推进发布。静态 plan 通过不能替代正式远端验收；单机报告如实呈现共置资源竞争、整机故障影响和未验恢复能力，不声称跨故障域 HA。
- THEN 数据面采用固定小规格存算分离单主（PolarDB PostgreSQL / Tair / MongoDB 单主，不依赖 Serverless）+ 同 VPC 私网 + ExternalName/DSN 抽象 + Secret 注入；每域只连归属存储，无硬编码连接、无跨域直连。
- THEN Strangler 拆分前后，域级 API / route / Service 名 / 端侧配置 / 数据面归属完全不变。
- THEN `gamma-local` 与 `prod-hosted` 工作负载图谱（含数据面 Service 名/DSN 变量）同构；`stackctl` / workflow / topology resolver 对同一 workload 图谱解释一致。

<a id="sit-003"></a>
### SIT-003 exact dev candidate 的不可提升 prod-hosted rehearsal

- GIVEN integration 工作树干净且 HEAD 等于本地 `refs/heads/dev1.0`，候选由 canonical prod-hosted 打包入口生成并绑定该 `sourceRevision`/tree。
- GIVEN `prod-hosted` 平面账号、rootless Podman 与 user systemd 已就绪，且宿主共享 edge 独占公网 80/443。
- WHEN 以该 exact dev candidate 执行 `prevalidate` rehearsal。
- THEN 工作树脏、HEAD 不等于本地 `refs/heads/dev1.0` head、候选内容身份不等于 HEAD（`sourceRevision` 既不等于 HEAD，也不是「HEAD 的祖先且打包输入路径无改动」的内容寻址复用）、镜像架构不是 `linux/amd64`，或本地镜像 content digest 与候选不一致时，在任何远端传输前 fail closed。
- THEN 候选镜像只经 exact digest 从本机交付到目标平面账号并读回一致，部署只落 `prevalidate` deployment instance 与独立 namespace，service/edge user systemd unit 为 enabled/active。
- THEN 必需服务的原生健康探针持续执行且通过，初始化任务成功完成；探针未调度、OOM、初始化失败或超过启动预算均返回可区分的失败结果，既有共存应用、候选镜像与持久数据不因重试被无条件清理。
- THEN 受限输入存储与可重建部署工作区隔离，按环境、预验证/正式用途及密钥用途独立授权；符号链接、非当前用户所有或宽权限目录在写入前拒绝。准备空目录不生成账号、凭据或证书，也不构成任何依赖就绪证据。
- THEN 报告分轴给出 container runtime、Provider readiness 与 release eligibility，其中 `releaseEligibility` 恒为 `GATE_BLOCK` 且 `nonPromotable=true`；该候选不可被 formal rollout、frozen diagnostic snapshot 输入、tag、admission 或 ledger 消费。
- THEN 隔离数据面对 canonical immutable content release 的 hosted-import 与 activation readback 只记为 rehearsal 诊断；legal-static 占位与宿主共享 edge 的 TLS 承接均在候选与报告中显式标记为非准出证据。
- THEN 同一 release/payload 的核心诊断只能经现有 `stackctl verify` selector 汇总；Data 的 exact apply/activate/binding 与各 selected case 缺一即失败，结果恒不可提升且不写 readiness。将同一请求改为正式 Prod instance、external data mode 或试图消费为 formal readiness 时拒绝。

<a id="sit-004"></a>
### SIT-004 声明交付目标的资格不跨目标外推

- GIVEN 受控请求预先声明服务部署、App 分发或两者，绑定 exact RC/source/tree、request authority 与所选 material 依赖。
- WHEN 同一 qualification reducer 归约实际证据，唯一 stable controller 选择该候选，后继请求执行对应交付动作。
- THEN 服务目标的真实服务物料、测试、环境、Provider、恢复及供应链闭包完整时，不因未选择且非依赖的 App 移动包/双真机证据缺失而拒绝其资格；由此形成的 stable/admission 只允许该服务目标，不得用于 App 分发，也不把依赖 Web 字节的存在解释为 App 移动包资格。
- THEN 含 App 移动包目标时，缺签名、任一 required 物理平台、Provider/UAT 或渠道所需证据即不能完成对应包/渠道准出；Simulator-only、服务通过或其他渠道成功均不能替代。未选择的 App 目标仍不可分发，不出现推定 passed。
- THEN 联合目标缺任一 required 分项即不能产生联合 Qualification/stable 成功；请求目标缺失、为空、未知，后继扩张/缩减声明范围、actual artifact/evidence 与目标不符、删除必要工厂/依赖物料或篡改 exact digest 均在任何发布 mutation 前阻断。只含 App 的资格不能进入服务 activation。
- THEN 相同输入的重放沿既有 create-once 身份读取；补齐证据、变更目标或切换候选不改写历史 Qualification/tag。审批、SoD、签名/attestation、OCI actual bytes 与 source/tree/request/RC 一致性仍逐级验真，main 晋级仅产生 source-admitted，不授予任何交付目标资格。

<a id="sit-005"></a>
### SIT-005 真正无 prior 的首次部署与失败安全态恢复

- GIVEN 当前完整 hosted ledger/history、target inventory 和流量入口读回均可验证，且受信 Human request 绑定 exact 服务交付物料、环境、首发/升级意图和相应恢复证据。
- WHEN 同一 Prod admission 与 rollout 生命周期校验 prior，执行阶段推进、失败恢复或 outcome unknown 的对账。
- THEN 只有可证明无 active released、无未解释历史/在途 activation 且入口处于未激活安全态时可选 absent；present 必须绑定真实 previous released 与恢复闭包。空 state 文件读取、查询失败/权限不足、残留路由、receipt 缺失或 partial inventory 不得代替 absent，已有 prior 不得通过首发标志绕过升级门。
- THEN 同一 target 的两次首发以同一 expected generation 竞争仅一个成功；观察进行中改变配置/路由/unit/公开指针的writer必须被同一执行权拒绝或使观察失败，不能只在头尾比较摘要。不同target保持独立，已准入exact身份的正常重启不改变发布代际；缺任一host/plane、错误endpoint或孤立进程不产生完整观察。第一次 mutation 后或终态 CAS 前前值/inventory 变化即阻断。调用结果丢失时只按 exact command/attempt 查询并幂等对账，不重复猜空提交；控制端断开或TTL到期后，旧子进程未退出/可靠隔离及读回前仍禁止接管。
- THEN 首次成功只在全部原阶段证据齐全后生成首个 released terminal；无 prior 不放宽签名、审批/SoD、备份、容量与恢复要求，不以候选自指、Data empty baseline 或首个 train 激活冒充旧版本。
- THEN 在候选部分启动、配置应用、灰度流量或终态写回失败时，恢复先切断本次业务流量并读回，再停用本次 owned unit/重启与未激活配置；完整 inventory 证明未再暴露候选，持久数据、媒体、volume、恢复点和审计全部保留，其他共存服务不变。停流或停用失败时保留恢复失败/unknown，不发布成功安全态、released 或 soak；安全态成功也不能称为上一版本回滚。
- THEN 首发失败后的重试引用已恢复未激活的历史终态与新 generation，受信授权重新绑定当前物料/环境/恢复证据，不重置 ledger；存在真实 prior 时始终按原 exact previous released 恢复。缺不可逆动作或共享入口变更的专项授权时停止该动作，目标总授权不替代专项授权。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 deliver deploy prod pipeline 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：正式 Prod 仍残留 `ReleaseEvidenceManifest` / `releaseEvidenceRef` / `--release-manifest` 读写与 lifecycle status 语义，factory material actual-byte 校验和 terminal fact 单轨尚未完成原子切换。
- 目标：本地 Alpha/Beta、dev head Gamma、五分钟 evidence-only promotion，以及从实际 factory material 到 `PostReleaseSoakFact` 的唯一正式链闭合；删除正式 Prod 的 release-manifest 与生命周期状态第二轨。
- 完成判定：`SIT-001` 全部结果子句由职责匹配的 current local_contract/api_integration/user_acceptance 直接绑定并通过，且门禁证明正式入口不存在被禁止的 release-manifest surface

<a id="open-011"></a>
### OPEN-011 promotion 健康警告的 Review 闭包物化

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：full report 与 exact promotion range 已有 producer/reader，但 promotion bundle 尚未携带 existing Review contract 所需的 current plan、named evidence receipt 与 completed primary result；缺少 PR_WARN 裁决通过的 admission 集成证据。警告保持 `PROMOTION.HEALTH_DISPOSITION_REQUIRED`，不得以 wrapper passed 绕过。
- 目标：物化 existing Review health disposition contract 的 exact 前驱闭包，复用 `validate_candidate_closure`，绑定同一 full report/findingId 与完整 promotion candidate；不建立第二裁决 schema。
- 完成判定：`SIT-001` 中按 existing Review contract 裁决通过的 PR_WARN 可继续，缺失、旧 candidate、漏 finding、无效 OPEN 或 blocker 仍在 admission 前拒绝，均有 current local_contract 直接证据。

<a id="open-002"></a>
### OPEN-002 prod-hosted inventory 完整性与单机正式远端验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：manifest 默认单 host，但当前 `prod_hosted_topology.py` 的正式门仍要求至少两台 host 且每 plane 两个跨 host replica；尚未实现 `REQ-002` 的唯一 expected inventory 验证与完整负向合同。移除数量硬门不等于正式 Prod 就绪：单机 candidate/stable 共置峰值容量、端口与权限隔离、整机故障影响、可恢复 baseline、逐 replica receipt/ACK 和 hosted 聚合 CAS 的真实 readback 尚未验证；真实主机/平面凭据与授权执行证据仍是外部前驱，不以第二台主机作为单机验收的替代条件。
- 目标：在现役唯一 rollout 主线上按 canonical inventory 验证单机或多机全部 placement，不保留兼容开关、版本分支或旧算法；对已授权单机完成容量与恢复验证后，再在全部既有正式前驱齐备时取得真实 rollout 证据。单机不承诺跨故障域高可用，多机配置可通过同一算法也不构成跨故障域恢复已验。
- 完成判定：`SIT-002` 的完整单 host/多 host 正例、缺项/重复/端口冲突/错误 host/receipt 与 CAS 漂移负例均有直接绑定的 `local_contract`；授权单机的容量、隔离、故障影响与恢复证据完整，且 `SIT-001` 的正式链、terminal fact、rollback/soak exact predecessor 与 mutation-before-block 结果由真实 rollout/readback 证实并有有效 `spec_ref`。App/Service 资格、首次 previous baseline、灰度观测门槛及 soak 窗口仍按各自现役要求执行，不由本 OPEN 豁免。

<a id="open-004"></a>
### OPEN-004 正式 Android 身份外部登记同步

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：正式 Android applicationId 已冻结为 `com.leadwise.quwoquan`（vivo 开放平台已登记）；微信/QQ/支付宝开放平台回调、Firebase/推送、App Links/OAuth、其余市场后台与签名证书登记仍需按新身份同步。任一外部平台存在其他 applicationId 登记时保持 `GATE_BLOCK`，禁止同时发布两个身份。iOS 正式 Bundle ID 仍缺已登记外部事实。
- 目标：完成全部外部平台对 `com.leadwise.quwoquan` + 生产签名证书摘要的登记，并以渠道 readback 证明一致。
- 完成判定：`SIT-001` 下 `stackctl store-channels` 对已启用渠道的身份 readback 与 `app_artifact_manifest.yaml` 一致，且 DEC-004 正式身份条目无冲突登记

<a id="open-009"></a>
### OPEN-009 dataRelease 物理坐标绕过 canonical binding

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚未实现 `dataRelease` 对 canonical data-plane binding 与 `bindingDigest` 的消费。当前内容 release 解析仍走第二条物理坐标通道：local import 从 `mongoPortRole`、`redisPortRole`、`userPostgresPortRole` 拼接 loopback endpoint，hosted import 直接读取 `mongoUriEnv`、`redisAddrEnv`、`userPostgresDsnEnv`、`mediaRootEnv`；因此它可在未绑定同一 resource/namespace/role/CAS 身份时访问数据面，必须保持 typed blocker，不得把 data-plane binding 的通过结果外推为 release import/readback 已闭合。
- 已落地的前置：prod deploy 入口（`quwoquan_ops/cli/prod/deploy_to_prod.sh`）已要求 `DATA_PLANE_BINDING` 并校验候选自带的 `packages/runtime-shared/data-plane-binding.json` 与 `EXPECTED_DATA_PLANE_BINDING` 一致，候选 manifest 的 `dataPlaneBinding.{ref,digest,bindingDigest}` 篡改由 `test_deployment_candidate_manifest__contract__local_contract_test.py` 判否；`clusterRef` 物理 selector 已从 runtime topology package 与 log sink package 删除（[DEC-012](design.md#dec-012)）。
- 尚缺实现与验收证据：data release resolver 尚未读取 canonical binding artifact/digest，也没有覆盖旧物理坐标旁路判否及 Gamma 同 binding import/readback 的直接测试。附带 track 项：`dataPlane.resources.*.physicalIdentity` 允许只声明部分 mode（如仅 `external`）的 mapping，校验期不报错，缺失 mode 直到 `resolve_data_plane_environment` 才 fail closed；收紧为"字符串或三 mode 齐全"会更早暴露配置歧义，但需先确认四环境声明均已齐全，随本 OPEN 一并处理。
- 目标：由 data release resolver 消费与目标 runtime package 相同的 canonical data-plane binding artifact/digest，显式映射 MongoDB、PostgreSQL、Redis 与 media/object-storage binding；删除 port-role/env-name 物理坐标旁路，缺 binding、歧义、digest 漂移、role/namespace 不匹配或 CAS/readback 不完整均 fail closed。
- 完成判定：`SIT-002` 的数据面抽象、每域归属、gamma/prod 同构与拆分后契约不变子句均成立；聚焦 `local_contract` 以直接 `spec_ref` 覆盖 local/hosted 两种旧旁路判否、canonical binding 唯一解析、digest/CAS 漂移与缺失映射，Gamma `api_integration` 证明内容 import/readback 使用同一已封存 binding，Prod 仍由外部准入证据关闭。

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

<a id="open-007"></a>
### OPEN-007 `quwoquan_data/tests/local_contract` 没有任何 hosted 执行点

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`9f2ee2093` 把 `03. Delivery Gate` 收敛为只验 promotion evidence 时拆掉 data local_contract 分片，原 `04. Lane Gate` 分片器只跑 ops 合同。取消 lane PR、检查集合左移 accept 后，仍须证明受影响 `quwoquan_data/tests/local_contract/**` 在同一 exact candidate 上有稳定 fail-closed 执行点；L0 选择或手动全量不能自证其已进入 bundle，历史 hosted 覆盖缺口并未自动消失。
- 目标：由 Data 合同 owner 与交付链 owner 把受影响 data local_contract 接入 canonical accept 检查集合，形成 exact source evidence；hosted 只验其闭包与受信发布身份，不新建 Data lane PR 或独立交付 required check。
- 完成判定：`SIT-001` 下 candidate 触及 `quwoquan_data/**` 时，真实 accept 在 current exact candidate 上执行对应非空 data 合同分片，失败不得 accepted；本地 integrate 验真对缺失/失败/漂移的该证据拒绝发布，不重跑完整套件；hosted 资格强制另归 daily-merge OPEN-004 `track`，不作为该本地接线的前置。未取得 current 接线与执行证据前，本 OPEN 和 `local-continuous-integration#open-004` 都保持未闭合。
- 依赖：ubuntu-latest 上 data 合同的宿主能力清单（与 ops 合同同类的 macOS/工具链前提需先逐条声明）。

<a id="open-008"></a>
### OPEN-008 `candidateId` 与 `releaseCompositionId` 在发布链读侧仍混用

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`4512b65fb` 把 27 个 App/ops 生成物与 `store_distribution.py`、`release_bound_environment_identity_test_support.py` 收敛为 `candidateId` / `candidate-ready` / `deployable` 语义，但发布链读侧尚未收敛：`quwoquan_ops/cli/lib/app_readiness_facts.py` 仍要求 manifest 含 `releaseCompositionId` 且 status ∈ `{artifact-complete, qualified, main-admitted}`，`dev1.0` 上另有约 30 个文件（多为生成物内嵌 JSON）仍未改名。同一 manifest 在写侧与读侧使用不同字段名与状态集，读侧对新语义的 manifest 会 fail closed 或静默不匹配，新语义的 App readiness 事实链尚未在任一环境真实产出。
- 目标：以 `quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml` 为唯一 authoring source，把 `app_readiness_facts.py` 与其余读侧收敛到 `candidateId` 与新 status 集，并让 codegen 收敛残余生成物；不保留双读。
- 完成判定：全仓（生成物除外）`releaseCompositionId` 零命中，`app_readiness_facts` 的 local contract 以新字段名与 status 集通过，`SIT-001` 的 App readiness 事实链在 Alpha 上真实产出一次。
- 依赖：发布链 owner 对 `artifact-complete/qualified/main-admitted` 与 `candidate-ready/deployable` 状态映射的裁决。

<a id="open-012"></a>
### OPEN-012 首发 absent 证明与未激活安全态恢复尚未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：`qualified_prod.py`、admission/rollback schema 与 workflow 仍无条件要求 previous released；hosted ledger state 文件缺失仅返回空 state/receipt，不能证明无历史、无在途事务或完整 inventory 未激活。当前 finalizer 回滚会重部署 previous candidate，`deploy_to_prod.sh` 对无 previous 拒绝；gray cleanup 的停用单元不构成首发停流/安全态恢复事务。尚缺 `REQ-005` 的互斥 prior 完整首发链、受信首发 Human authority消费、完整空态取证、受管流量关闭、attempt-owned 单元停用/资源保留与安全态终态 readback，以及真实首发失败演练证据。`DEC-015` 已选定在默认host既有service-plane ledger内扩展execution-slot、各plane以原SSH身份启动受限guard并监督子进程的方案；当前controller本机锁与ledger锁互不覆盖，配置tar、路由、systemd、prevalidate及可见distribution writer仍未全部参与，不能签完整target观察。尚缺中央持久slot、受信执行单投递、各plane guard/immutable重启路径、全部writer接入与observe→consume→CAS连续交接实现及真实安装读回，不新增host/DB或授予跨plane/root凭据。
- 目标：在现役唯一 activation/attempt/terminal/ledger 生命周期内表达合法 absent/present，严格区分 unknown；首发失败回到可证明未激活安全态，有 prior 升级仍使用原 exact released baseline。删除无条件 previous 必填的实现冲突但保留对应存在性证明、恢复义务与所有安全门，不创建 bootstrap 旁路或历史兼容版本。
- 完成判定：`SIT-005` 的无 prior/有 prior、查询失败不得当空、重复首发 CAS、lost response readback、部分执行恢复、失败后新 generation 重试、假 previous/候选自指/错误环境/授权范围及保留数据负例由 current `local_contract` 直接绑定；`api_integration` 在获授权目标证明真实完整取证、首发成功与失败停流/停用/保留资源/安全态 hosted readback。首次涉及共享入口修改、数据迁移或其他不可逆动作前必须持专项授权，尚无授权/恢复能力/实证时本 OPEN 保持阻断；不修改灰度阈值、soak 时长、资格目标或 main 晋级。

<a id="open-013"></a>
### OPEN-013 声明交付目标的资格范围尚未原子落地

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：`release_qualification.py` 的 artifact normalizer 固定要求 service/android/ios/web，资格归约无条件要求 Android/iOS 双物理接受；`qualified_prod.py`、Prod activation schema 与 workflow 仍强制 service/app 两类工厂。尚缺 request/CMM/Qualification 的受控交付目标表达、逐目标适用证据校验与真实 factory/admission 范围闭包验收；只修改文档不能解除该实现阻断。iOS Simulator 不是正式 App 真机证据。
- 目标：按 `REQ-004` 在同一 qualification reducer/controller/exact fact 链内一次切换 request、CMM、Qualification、stable admission、Prod 与 App consumer 及工厂 workflow；删除无条件跨目标耦合，不新增第二入口、schema 版本并存或缺字段默认。服务依赖 Web 等实际物料仍完整验真，App 包与渠道保留其物理设备、签名、分发和真实 readback 门。
- 完成判定：`SIT-004` 的服务/App/联合目标正例、Simulator 非提升、未选择目标禁止 effect、联合缺项、删字段/依赖物料、scope 漂移、SoD/签名/摘要失败均有直接绑定的 `local_contract`；`api_integration` 证明 current actual factory bytes 经唯一 reducer 到 stable/admission 的范围闭包，App 对应 `user_acceptance` 与渠道真实回执未取得时仍保持 not-ready。服务正式发布还须满足既有单机容量/恢复/readback 与其他前驱，本 OPEN 不变更首次 previous baseline、灰度阈值或 soak 窗口。

<a id="open-010"></a>
### OPEN-010 exact dev candidate rehearsal 尚未在真实 prod-hosted 单机闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：正式链在 stable tag、GHCR 工厂物料、production approval 与多 member 冗余前置齐备前无法把任何候选送上 `prod-hosted`；在此之前，唯一能把当前 exact dev candidate 部署到日本单机做端到端内部验证的受治理通道就是 `REQ-003` 新增的 rehearsal。候选来源门、本机 `linux/amd64` build-once 物料、exact digest 本地交付、legal-static 占位标记、rehearsal 专用签名材料（GraphQL read registry、官方 Skill 包）、prod-hosted runtime-topology 身份与非准出 TLS 标记已由 `local_contract` 绑定；尚缺真实 `prod-hosted` 单机上的一次 rehearsal 部署读回、隔离数据面对 canonical release 的 hosted-import/activation 诊断读回，以及宿主共享 edge 公网入口下 prod buildProfile App 以白名单身份可达的读回。
- 完成判定：`SIT-003` 的 `t1`、`t2`、`t3`、`t4` 分别由 current `local_contract` 直接绑定并通过；同一 exact dev candidate 在真实 `prod-hosted` 单机上完成一次 rehearsal——镜像 exact digest 交付读回一致、service/edge unit enabled/active、报告 `releaseEligibility` 为 `GATE_BLOCK` 且 `nonPromotable=true`（`t2`、`t3`），隔离数据面完成一次 canonical release 的 hosted-import/activation 诊断读回，且宿主共享 edge 按 Host 分流并标记为非准出后 prod buildProfile App 以白名单身份可达（`t4`）。
- 依赖：`prod-hosted` 平面账号、rootless Podman 与 user systemd 已 bootstrap 并经平面账号 SSH 读回；`api/ops/cdn/upload/rtc.quwoquan.com` A 记录已发布；GraphQL read registry 的 rehearsal 签名 key 由仓外 `QWQ_GRAPHQL_READ_REGISTRY_*` 显式提供且 keyId 必须与正式 prod authority 可区分；工作树必须干净且 HEAD 等于本地 `dev1.0`，跨会话并行写入同一 worktree 时须先合并提交再打包；prod 内部 cohort 需要 User 拥有的四环境授权与签发契约、经正式认证核验的真实 accountId、独立受限密钥注入及真实 OTP Provider 依赖，不能仅打开当前拒绝 prod 的非生产 managed identity 开关；Data 必须消费同候选、同实例的 binding 与现役 handoff，按 apply、activate、verify 取得隔离读回，Content 与 App 不得把 production release 字样等同于公开访问。现役生产内容 handoff 的评审计划/候选前驱必须在消费面可验，旧 research attestation 不进入正式 integrate；POST candidate evidence 的 integration 工作区身份仍需由治理 owner 支持，不得以切换分支或关闭 current 校验替代。秘密目录准备不解除账号、Provider、mTLS、App signer 与设备输入缺失，相关正向验收继续阻断。
