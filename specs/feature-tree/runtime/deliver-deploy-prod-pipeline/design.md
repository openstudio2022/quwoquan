# L2 Design：生产交付管线 (`deliver-deploy-prod-pipeline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚”需要 `daily-merge-release-strategy`、`gray-release-to-prod`、`local-gamma-mirror`、`multi-environment-instance-isolation`、`multi-environment-wave-deployment`、`workflow-naming-consolidation` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`daily-merge-release-strategy`](./daily-merge-release-strategy/spec.md)：`main` 是唯一长期发布主干；短期 PR 分支受控、合入即删，退役分支只保留 archive tag/bundle。
- [`gray-release-to-prod`](./gray-release-to-prod/spec.md)：**统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- [`local-gamma-mirror`](./local-gamma-mirror/spec.md)：gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- [`multi-environment-instance-isolation`](./multi-environment-instance-isolation/spec.md)：beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- [`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)：同一 source release train 预先封存四份环境专属 artifact，按 alpha、beta、gamma、prod 的准入顺序验证，任一波次失败即停止晋级。
- [`service-core-composition`](./service-core-composition/spec.md)：以同一 Go host 组合 11 个核心服务而不改变领域契约、数据归属或独立实时/模型故障域。
- [`workflow-naming-consolidation`](./workflow-naming-consolidation/spec.md)：**约束**：不得保留重复名称（如 05/05b、08b/08b）或依赖旧的 `workflow_run` 定时合流链。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_ops/environments`、`quwoquan_ops/environments/prod/kustomization.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 main 后只允许一条权威受控主链
- 决策：main 后只允许一条权威受控主链。
- 分支真相：`main` 同时是唯一长期开发与发布真相源；短期 PR 分支不是第二主干，禁止从 archive tag/bundle 恢复为活动发布分支。
- 理由：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- main push 自动启动同一 DAG，完成不可变 OCI `ReleaseEvidenceManifest` 的 `component-ready -> candidate-ready` 总装与 Alpha/Beta/Gamma 阻断验证；正式 Prod apply 不由 workflow_run 或 push 静默执行，必须由人工 dispatch 绑定可达 main 的精确 Git SHA、显式设置非 dry-run，并通过 production environment approval。
- `candidate-ready` 必须绑定同一 source capsule 派生的四份环境 artifact、四环境 App 真实 payload、ContractGraph、真实 Provider readiness 与三层测试；每份环境 artifact 已封存本环境镜像/config/binding/authority，按序接受 Alpha/Beta/Gamma 回执并绑定 rollback readiness 后才成为 `deployable`，Prod 全量验证后才成为 `released`。
- 同一 release train 就绪后，Alpha、Beta、Gamma-local 在隔离运行面并行执行；聚合器仍按 `alpha -> beta -> gamma` 验证回执，任一失败均不得申请 Prod approval。环境阶段不得重新构建或跨环境重用最终镜像。
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

<a id="dec-004"></a>
### DEC-004 App 制品身份、签名隔离与多渠道分发回执
- 决策：App 分发以三个分离对象承载事实——`AppArtifactManifest`（`ReleaseEvidenceManifest` 候选内的 immutable owned entity，拥有 platform、BuildMode、distributionClass、package/bundle ID、version/build、signing identity、source/artifact/launch-manifest digest 与 promotability）、`InstallReceipt`（按 store/device/build 追加且集合无界的 separate append-only fact，独立生命周期与查询）、渠道矩阵（从 canonical metadata 生成，覆盖 Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝与官网 `official_web` APK）。打包、签名校验、安装与渠道登记统一走 `stackctl package` 的 canonical App 入口（显式 `env/platform/build-mode/distribution-class/device`），`run.sh` 与 IDE 只做薄包装。
- 跨边界 port：构建写入走 `AppArtifactPackageWriter` 生成不可变制品、`AppArtifactManifestReader` 提供验证查询；安装证据走 `AppInstallReceiptAppender` 只追加真实安装/商店回执、`AppInstallReceiptQuery` 供准出读取。禁止脚本或 Provider 直连绕过 port。
- 包身份隔离：alpha/beta/gamma/prod 与 Debug/Release 使用不覆盖的 application/bundle ID、显示名与签名映射。
- 包身份隔离：Prod 正式 ID 只取已登记外部事实，非 Prod/Debug 使用隔离后缀并同步 Universal/App Links、OAuth、推送与 Keychain/App Group。
- 分发约束：Debug 签名制品仅限开发者本机、Simulator/Emulator 与登记设备。TestFlight、市场与官网只接受 Release。
- 渠道逐项声明：每渠道登记 `channelId`、`uploadFormat(ipa/aab/apk)`、package/bundle ID、store product ID、track、version/build、developer signing identity、store signing custodian、可能的 split/optimize/re-sign transformation、source candidate/artifact/launch-manifest digest、upload/review/release receipt 与安装后 signature/receipt 校验方式。市场可能重签或优化，准出不要求下载二进制逐字节相同，而以 source digest、version/build、store 官方签名/receipt、嵌入 launch manifest 与启动 telemetry 绑定；一个渠道的回执不得替代另一渠道。
- 官网分发：Android 官网 APK 复用 official distribution 部署到不可变 CDN 对象并出带 SHA-256 的 receipt，发布前通过包名/签名证书摘要/Build/SHA-256 预验证门禁；`app_release` 契约字段是恢复页、更新提示与网页安装组件共用的唯一下载真相源。iOS 网页版不提供二进制下载。
- 灰度与回滚：先内测或分阶段验证，再进入公开发布。
- 灰度与回滚：内容 active pointer、Web current pointer 与远端配置的止损在 300 秒内完成，且不要求重新打包或再次审核。
- 灰度与回滚：已安装商店 App 不可强制回滚，服务保留商店客户端 N/N-1 兼容面，禁止把“重新发版”当唯一恢复动作。
- 被否决方案：单一 applicationId/bundle ID 覆盖安装、Debug 包进入市场、要求市场下载物逐字节等同上传物、把内容 release 绑进商店二进制、side-load 冒充市场安装回执。
- 关联要求：`REQ-001`
- 影响 Story：[`gray-release-to-prod`](./gray-release-to-prod/spec.md)、[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)
- 关联验收：[`environment-topology-and-packaging GWT-003`](../runtime-config/environment-topology-and-packaging/spec.md#gwt-003)、[`app-release-recovery-routing GWT-004`](../../product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-004)、[`cold-start-performance GWT-005`](../runtime-client-foundation/cold-start-performance/spec.md#gwt-005)

<a id="dec-005"></a>
### DEC-005 同一 Release Train 预构建四份环境专属云制品

- 决策：mainline candidate 以 `releaseTrainId` 绑定共同 source capsule、ContractGraph 与 toolchain，并在 `candidate-ready` 前生成 Alpha/Beta/Gamma/Prod 四份 `EnvironmentArtifactManifest`。每份 manifest 绑定本环境的 `service-core` 与五个独立服务镜像、config、Provider binding、endpoint authority、runtime topology、SBOM/provenance 和 purity attestation。
- 决策：本地 `stackctl package` 与 Service Pipeline 共用 `environment × runtime_image_owner` 构建矩阵。允许共享 BuildKit/module/base-image cache，禁止跨环境复用最终 image digest；同环境完全相同输入才可 CAS 复用。
- 决策：镜像内只嵌入不含自身 OCI digest 的 artifact identity core，外部 activation seal 绑定真实 image digest 与 rollout authority。`prod-sim` 与 `prod-hosted` 同属 Prod，但 target seal 不可交换；prevalidate 与 rollout 复用同一 `prod-hosted` payload，只追加 authority receipt。
- 理由：一套跨环境镜像加四份运行时配置仍允许环境变量重解释二进制，且本地 service-core 与正式 split-services 构建集合不一致。环境专属 artifact 使 package、启动、回滚和供应链证据拥有同一物理边界。
- 被否决方案：flat images + 四环境 config、按 source tag 跨环境复用最终镜像、运行时 `APP_ENV` 选表、平台运维镜像复制全环境 facts、以及以 RTC 单能力摘要代表全环境闭包。
- 回滚：只接受上一份同环境 `environmentArtifactDigest` 的完整镜像/config/binding/topology；service-core 与环境镜像集整体回滚，不从当前工作树重建旧候选。
- 可测试观察面：构建矩阵恰为四环境乘 runtime image owner，同一 source 产生四份不同环境 artifact。
- 可测试观察面：把 Alpha 镜像装到 Beta 或改 `APP_ENV` 时，在 listener 前失败。
- 可测试观察面：回滚后 image/config/binding/topology 摘要全部恢复。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`multi-environment-wave-deployment`](./multi-environment-wave-deployment/spec.md)、[`service-core-composition`](./service-core-composition/spec.md)

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、候选摘要冲突、证据缺失或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- `prod-hosted` 的正式灰度 workflow 必须人工 dispatch 并保留 approval；在 Provider、SFU、真实数据、观测、灾备或回滚证据缺失时只允许不可提升 prevalidate，且 post-deploy probe 置信度仍须单独验收。
- 运行装配从各服务 `environments/<env>/deploy`、Ops 同名环境入口和真实 Compose/Kustomize 扫描推导；本地端口保留 `local_env_port_manifest`，prod rollout 保留 `gray_rollout_stages`，服务配置由自治 package 的 provenance 摘要证明。
- 每个 Prod rollout stage 必须执行 `stackctl health + inspect + doctor + integration probes + slo gate`；任一失败写入 GATE_BLOCK/rollback 证据，不得由 workflow 合成成功。
- App 四分片耗时必须读取四个实际 Jobs API 节点并取最大值；任何 shard 缺失时 timing gate 失败，不允许回退到 static/serial 近似值。
- 独立可观测：每域 `service.name` + 指标维度独立，使“逻辑独立”在合并部署时依然成立，并为拆分提供数据依据。
