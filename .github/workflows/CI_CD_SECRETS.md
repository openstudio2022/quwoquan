# GitHub Actions CI/CD：五分钟源码晋级与标签驱动发布

本文档只描述当前永久单轨合同、现行 workflow 接线与尚待闭合的外部前提。它不证明 GitHub Environments、Apps、keys、rulesets、hosted authorities、runner 或生产基础设施已经配置；缺少对应权威 readback 时必须保持 `GATE_BLOCK`。

合同真相源：

- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md`
- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md`
- `quwoquan_ops/policies/branch_policy.yaml`
- `quwoquan_ops/policies/release_selection_policy.yaml`
- `quwoquan_ops/policies/product_version.yaml`
- `quwoquan_ops/environments/prod/access-isolation.yaml`

## 1. 永久执行边界

发布链严格分成四段：

1. Environment Ops 在受控本地执行面生产 Alpha、Beta、Gamma（ABG）事实。
2. `03. Delivery Gate` 只验真 `dev1.0 -> main` 源码 promotion evidence。
3. RC qualification 对一个不可变 RC 构建、签名、SBOM、provenance 并完成最终资格归约；stable tag controller 只选择已 qualified 的同一份物料。
4. Prod 只消费 stable `ReleaseTagAdmissionFact` 绑定的 exact OCI digests，在一次审批与一次物化后执行 `canary -> 5 -> 20 -> 50 -> 100`。

所有后继事实都必须引用前驱 canonical bytes digest。Actions Artifact 仅是可删除诊断副本，不是 admission authority。禁止 `latest`、repository variable、裸 Git SHA、`main HEAD`、RC tag 或 workflow success 充当 Prod selector；禁止兼容双读、双写、可变指针 fallback 或第二发布入口。

普通 `main` 分支更新只表示最新 `source-admitted` 可用源码：不会自动构建、签名、创建标签、打包或发布到 Prod，也不会改变历史 RC、stable tag 或当前生产 digest。现行 `service_pipeline.yml` 只接受 `workflow_call`/手动触发，`app_pipeline.yml` 只接受 `workflow_call`；三个 release workflow 也都只接受手动 dispatch，因此没有由 `main` 更新触发的发布链。

## 2. 本地 Environment Ops 生产 ABG

Alpha、Beta、Gamma 的正式 producer 只能位于受控本地 Environment Ops 执行面；GitHub-hosted 和 GitHub self-hosted workflow 都不得执行 ABG、Data mutation、设备 Journey 或环境 cleanup。

- Alpha：在尚未移动 `dev1.0` 的 detached exact candidate 上执行默认真实依赖最小闭包。
- Beta：只在 typed 高风险 `ImpactPlan` 要求时执行；`no_live` 必须产生绑定 candidate 与 ImpactPlan 的 `not_required` fact，不能从 skipped 推导通过。
- trusted integration publisher：保留为带资格的可选更新通道，只在 Alpha/conditional Beta 的 `EnvironmentAcceptanceFact` 与 source facts 精确绑定同一 candidate、签名、cleanup 与 lease closure 后，以 expected-old 非 force fast-forward CAS 更新 `dev1.0` 并 exact readback；integration worktree direct fast-forward push 不生产或替代这些事实。
- Gamma：integration scheduler 只对 current exact `dev1.0` head 执行，引用同一 Alpha/Beta exact-byte predecessor，封存 `IntegrationQualificationFact`。新 head 会使旧 Gamma 与 promotion eligibility 失效。

每个环境事实必须闭合 package identity、startup、full health、受影响 CaseResult、readback、inspect/doctor、finally teardown、lease revoke 和端口释放。环境、设备、package、Git index 与 Git ref 均为单 writer 资源，不能由并行 workflow 竞争。

## 3. `03. Delivery Gate` 只做 promotion evidence 验真

`.github/workflows/delivery-gate.yml` 是 `dev1.0 -> main` 的唯一 required context，context 名精确为 `03. Delivery Gate`。它监听 promotion PR（`pull_request`）与审批事件（`pull_request_review`，用于在审批后重新评估而不是人工重跑）以及 `main` push，不监听普通分支更新。

PR body 只接受一个 JSON 对象，恰好两个键：

- `qualification_bundle_ref`：由 `promotion_hosted.py publish-oci-bundle` 发布的 IQF 证据 bundle exact OCI `@sha256` ref。bundle 是 `.qwq_output/env/repo/local/scoped-candidate/process` store 的确定性 tar，含 `integration-qualification/<devHead>/<id>.json`、Alpha/Beta/Gamma `EnvironmentAcceptanceFact`、publish result/admission、candidate 与全部命名证据，Gate 以 `verify_references=True` 校验整条链。
- `promotion_ready_at`：UTC 时间戳，作为 SLI `promotionReadyAt -> mainReadbackAt` 的起点。

当前职责是：

- 校验 head/base/merge SHA 与唯一合法分支边；
- 取回 bundle，用 PR head exact bytes 中的仓内 Ed25519 公钥 keyring（`quwoquan_ops/policies/evidence_signing_keyring.yaml`）与固定 signer identity（`quwoquan-integration-scheduler-local` / `quwoquan-environment-ops-local`）验证 current dev head 的 `IntegrationQualificationFact` 及其 A/B/G 链；Gate 不持有任何可签名材料，无 repository secret；
- 自己从 hosted readback 生产 approval（`/pulls/{n}/reviews`，只计 head commit 上非作者的最后一条 APPROVED）、threads（GraphQL `reviewThreads` 全部 resolved）、ruleset（main 上 active ruleset 要求 PR、无 bypass actor、required check 精确为 `03. Delivery Gate`）与 changed-boundary（branch policy + promotion 影响面 + secret/generated）四类事实，再由 `release_control.py promotion-admit` 消费；
- 只验真 promotion admission 所需前驱与 exact identity，不在该 context 内执行合并、ref mutation 或 post-merge effect；
- 以 GITHUB_TOKEN（`checks: write`）创建 create-once handoff check-run `quwoquan/promotion-admission-handoff/v1`，其 App 身份就是 main ruleset 信任的 GitHub Actions integration（`github-actions` / `15368`），不再需要自建 GitHub App；
- 为 `main` push 后形成 `MainSourceSeal` 提供准入事实；固定 SLI 目标 p95 为 300 秒，handoff 有效窗口等于 ratchet enforcement budget（1800 秒）。

该 context 禁止安装语言工具链、构建、源码测试、打包、ABG、Provider live、设备执行、环境 cleanup、合并或 Git ref 写入。仓库 ruleset 只应要求这一项 promotion context；不得再把其他编号 context 组合成源码晋级条件。

本地左移：`make commit-gate` 在 `.github/workflows/**` 变更时运行 `verify_workflow_actionlint.sh`（pinned actionlint，拦截解析期即失效的非法上下文、不存在属性与 reusable 输入类型错误）；workflow↔仓内 CLI 的 argparse required 一致性由 `verify_workflow_cli_arguments.py` 负责（含常量循环内 f-string 声明的成组 required）；step 内引用自身 `steps.<id>.outputs` 由 `verify_github_supply_chain.py` 拦截。三者在 `gate_repo.sh` 全量执行。

### 3.1 `04. Lane Gate` 只做 lane PR 静态/合同复算与 dev1.0 ruleset 读回

`.github/workflows/lane-gate.yml` 是 `lane/* -> dev1.0` 的唯一 hosted required check，context 名精确为 `04. Lane Gate`，由 `branch_policy.yaml#required_integration_checks` 唯一声明，与 `03. Delivery Gate` 不共享 workflow 或名字。它只监听 `pull_request: branches: [dev1.0]`，在 exact PR head 的 clean checkout 上重跑静态治理、ImpactPlan/boundary、candidate-bound Code Health Delta 与 `quwoquan_ops/tests/local_contract/**` 四分片；不打包、不签名、不触碰设备或环境。合入不在该 context 内发生：由 integration 工作区通道携 Alpha/Beta admission 把远端 `dev1.0` 快进到已过检的 lane head（见 `daily-merge-release-strategy`）。

唯一的 hosted 读取是 governance job 以默认只读 `github.token`（`permissions: contents: read`，rulesets 只需 metadata read）执行 `verify_hosted_integration_ruleset.py`，读回 `repos/{r}/rulesets` 中适用于 `refs/heads/dev1.0` 的 ruleset 并产出 `hosted-integration-ruleset-receipt`；它不持有任何 secret，不创建 check-run，不写任何 ref。

## 4. 三个 release workflow 的单一职责

### 4.1 RC qualification：`release-qualification.yml`

入口只接受精确 RC 资格图：

- `rc_tag_admission_ref` 与 `qualification_request_ref`：不可变 RC AdmissionFact/QualificationRequest 的 exact OCI `@sha256` ref；
- `source_git_sha`：RC peeled commit；
- `product_version_manifest_ref`：当前 ProductVersionManifest 的 exact OCI `@sha256` ref；
- `package_acceptance_fact_ref`、`provider_fact_ref`、`uat_fact_ref`、`supply_chain_fact_ref`：必须全部绑定同一 material/source 的 exact OCI `@sha256` refs。

移动端 `artifactBuildNumber` 不由调用者输入；workflow 在 `release-qualification` Environment 内用 hosted run identity 调用单调 allocator，随后把 allocation exact ref/digest 同时传给 App factory 与 CandidateMaterialManifest reducer。

`release-qualification` job 只能对该 RC commit build/sign/attest once，产出一个 `CandidateMaterialManifest`，绑定 Android、iOS、Service、Web exact OCI digests、同一 build number、SBOM、provenance 与 signing receipt。最终 `QualificationFact` 还必须绑定同一 `materialId` 的 Android/iOS 物理设备 package acceptance、Provider、真实 Remote UAT 与 supply-chain facts。源码、版本投影或制品字节变化必须创建下一个 RC；同一 RC 只能重试同身份的未完成步骤。

现行 workflow 已串联 hosted build-number allocation、Service/App reusable factories、CandidateMaterialManifest reducer 与 QualificationFact finalizer；但只有外部 package/Provider/UAT/supply-chain facts 的 exact bytes 均可拉取并通过同一 material/source 绑定时才会产出资格事实。仓库接线通过不等于真实最终签名包或物理设备事实已经产生。

### 4.2 stable tag selection/admission：`release-tag-selection.yml`

唯一 `release-controller` 负责 create-only annotated RC/stable SemVer tag。stable 只能选择一个 exact qualified RC，必须与其指向同一 main-reachable commit，并复用同一 source tree、`CandidateMaterialManifest`、artifact build number 与 OCI digests，禁止 rebuild。

controller 必须在创建后 exact readback tag object OID、peeled commit、creator identity 与 tag ruleset，并生成 `ReleaseTagAdmissionFact`。tag 必须直接指向 commit；lightweight tag、tag-of-tag、移动、删除、重建、同 material 多 stable tag 全部拒绝。

现行 workflow 的 controller 路径要求 admission evaluator 在 create-only push 前通过，并在 push 后 exact readback tag object 与 peeled commit；creator/ruleset facts 必须以 exact refs 参与 evaluator。仅有 Git tag 或 workflow success 仍不构成 stable admission。

controller 身份与 readback（DEC-009）：唯一 controller 就是仓库 deploy key `release-controller`（可写），tag ruleset 只给 DeployKey 留 create bypass、update/delete 全 denied；workflow 用 `RELEASE_CONTROLLER_DEPLOY_KEY` 经 SSH 推 annotated tag（tagger = `release-controller`，message 携带 `release-tag-intent: <intentId>`），推前用 `ssh-keygen -lf` 指纹与 hosted `repos/{r}/keys` 读回比对。creator/ruleset readback 由 `release_tag_readback.py` 从 GITHUB_TOKEN 只读 REST（`keys`、`git/ref/tags`、`git/tags/{oid}`、`rulesets` 含 ETag）归约，不再需要 controller GitHub App、外部 readback 服务或 `RELEASE_CONTROLLER_READBACK_URL/TOKEN`。

RC 前置的人工权威由 `release_control.py initial-release-authority`（首个 train 激活，绑定 `gh api user` 读回的审批人）与 `release_control.py rc-select`（RC 选择，绑定 main-reachable commit/tree 与 manifest digest）在本地 create-once 生成并 `publish-oci`；`product_version.yaml` 的 `initialReleaseAuthority.authorityFact` 记录该 OCI exact ref 与 canonical bytes digest。

### 4.3 stable-tag Prod：`deploy-prod-auto.yml`

唯一输入是 `release_tag_admission_ref`，必须为 stable `ReleaseTagAdmissionFact` 的 exact immutable OCI `@sha256` ref。Prod admission 从该 fact 解析并复核 QualificationFact、source/control-plane SHA、全部 exact OCI digests、previous active released ledger 与 rollback readiness；不得从源码分支、裸 SHA、RC、transport tag 或“最新 qualified”查询推导发布物。

`production` approval 后只允许一次拉取、验签、解包和物化，随后同一事务通过：

```text
stackctl deploy --target prod-hosted --stage canary|5|20|50|100
```

顺序推进五个 stage。每阶段必须封存 activation、health、SLO、placement 与 readback facts；失败只回滚到 hosted ledger 证明仍存在且兼容的 previous stable exact digests，builder invocation 必须为 0。terminal released fact 与只读 `PostReleaseSoakFact` 分离。

现行 workflow 必须先物化 stable admission、previous active released ledger、rollback readiness 及其 qualification/material 前驱，并经 `release_control.py prod-admit` 生成 exact `ProdActivationAdmissionFact`，之后才允许正式 mutation。真实 runner credential、每阶段 evidence、terminal 与 soak readback 未满足时不得宣称 Prod 发布完成。

## 5. 必需 GitHub Environments

以下是永久交付链需要的四个 Environment；这里列的是 required configuration contract，不是当前配置证明。

### `release-qualification`

- 只允许受信 RC qualification automation 使用；授予 `contents: read`、`id-token: write`、`attestations: write`、`packages: write` 所需最小权限。
- 必须绑定 immutable RC admission、hosted build-number allocation 与 build/sign/attest identities。
- 当前 App factory 还引用 `release-signing` Environment；其签名输入必须由 qualification 边界受控，不能变成独立发布入口。
- 物理设备、Provider、UAT、supply-chain 任一事实缺失或 material/source 不一致即 fail closed。

### `release-selection`

- 只允许唯一 `release-controller`；不得允许普通 `GITHUB_TOKEN`、个人 PAT 或通用 deploy key 绕过 controller identity。
- 保存 dedicated `RELEASE_CONTROLLER_DEPLOY_KEY`，仅授予创建目标 release tag 所需权限。
- tag ruleset 必须 create-only，update/delete 全拒绝且无 bypass actor；creator/ruleset API readback 必须绑定刚创建的 tag object。
- product authority、release authority、active product version train 或 exact qualified RC 任一缺失时不得创建 stable tag。

### `system-backsync`（保留合同，当前无 caller）

- `main -> dev1.0` 的回同步现由唯一 integration 工作区按自身 FF 通道执行：`make promotion-backsync` 校验远端 main 头是恰好一次两父 merge 且第二父等于本地 `dev1.0`，`--ff-only` 后经既有 pre-push FF 通道推送并 `ls-remote` 读回；dev1.0 已前移时阻断交人工，不 reset、不自动 merge。
- reusable `system-backsync.yml` 保留 expected-before nonforce fast-forward 合同，但 `delivery-gate.yml` 不再调用它；接回前提是 dedicated `SYSTEM_BACKSYNC_DEPLOY_KEY`（只授予 `dev1.0` 写权限，不得复用 `PROD_SERVICE_SSH_KEY`、开发者 key、release controller key 或通用 PAT）与 `system-backsync` Environment 就位（见 daily-merge-release-strategy OPEN-004）。
- post-merge handoff 的身份验证不再依赖 `QWQ_PROMOTION_RECORDER_APP_*`：`main_source_seal` job 只读 source SHA 上唯一名为 `quwoquan/promotion-admission-handoff/v1` 的 Check Run，并由 `promotion_evidence.py validate-hosted-handoff` 以 GitHub Actions integration（`github-actions` / `15368`）身份结合对应 workflow run（`pull_request` 或 `pull_request_review` 事件）校验 run/ref/digest。

### `production`

- 只接受 stable `ReleaseTagAdmissionFact`；一次发布只产生一次 approval 与一个串行 rollout transaction。
- job 固定使用受保护的 `[self-hosted, macOS, ARM64]` runner；runner 只能物化已 admission 的 exact OCI digests。
- 环境审批事实必须来自可认证、可回读的 hosted approval authority；若 GitHub 原生 required reviewers 不可用，不能用 queue/start time、Deployment status 或人工布尔输入替代。
- production approval、previous stable ledger、rollback readiness、host placement、SLO/Alertmanager readback 或凭据任一不可验证时，必须在首个 mutation 前停止。

## 6. Trusted Apps、keys 与受信输入

### GitHub 与 release controller

- trusted integration publisher：受信 GitHub App/broker 对 `dev1.0` 执行 expected-old fast-forward CAS；客户端通过 exact HTTPS broker URL 和短期 token 调用，CLI 默认 token 名为 `QWQ_INTEGRATION_PUBLISHER_TOKEN`。该通道保留为执行 Alpha/Beta 准入并签发集成资格的发布通道，但不再是 `dev1.0` 唯一 writer。`integration/` 工作区可用普通认证 Git 凭据把匹配本地 `refs/heads/dev1.0` non-force fast-forward 推到远端同名分支；缺 before/after OID、ancestry authority 不可用、非快进、force/delete 或来源不匹配必须阻断。此 direct push 只提交源码，不签发 `integrationEligibility`、Alpha/Beta/Gamma、`IntegrationQualificationFact`、promotion、release 或 Prod authority。
- 源码回同步：promotion 后由 integration 工作区 `make promotion-backsync` 以 FF 通道把 `dev1.0` 跟到 main merge commit；受管 system actor 通道（reusable system backsync）保留合同、暂无 caller。分叉、unknown outcome 或身份不可证明时零写停止。
- 证据签名信任根（L2 DEC-010）：Alpha/Beta/Gamma `EnvironmentAcceptanceFact` 与 `IntegrationQualificationFact` 用 Ed25519 签名（`ed25519:<base64>`）。两个 signer identity（`quwoquan-environment-ops-local`、`quwoquan-integration-scheduler-local`）的私钥只在本地仓外 `QWQ_EVIDENCE_SIGNING_KEY_ROOT`（默认 `~/.cache/quwoquan/keys/evidence-signing`，0600），由 `make evidence-signing-bootstrap` 生成并把公钥登记进仓内 `quwoquan_ops/policies/evidence_signing_keyring.yaml`（版本化 authoring source，改动随提交进入 `dev1.0`）。Gate 与所有验签方只读 keyring 中的 active 公钥；不存在同名 secret、环境变量或 repository variable。轮换用 `ROTATE=1 make evidence-signing-bootstrap`，旧 key 置 `retired` 后不再验签。
- release controller：`RELEASE_CONTROLLER_DEPLOY_KEY` 必须是独立、最小权限、可轮换的 SSH key，其公钥即仓库 deploy key `release-controller`（写权限）；workflow 推标签前以指纹比对 hosted 读回，不能复用开发者 key，也不再需要 controller GitHub App。
- production approval ingress：受控 GitHub App installation + webhook secret。必须先对 raw request bytes 校验 `X-Hub-Signature-256`，再 append request/approved 事件；重复 delivery 不同 payload、乱序、自批或身份映射漂移全部拒绝。

### RC build/sign/attest

当前 `app_pipeline.yml` 实际读取以下 `release-signing` secrets；缺失时 Android 产品必须 fail closed：

- `QWQ_ANDROID_RELEASE_KEYSTORE_B64`
- `QWQ_ANDROID_RELEASE_STORE_PASSWORD`
- `QWQ_ANDROID_RELEASE_KEY_ALIAS`
- `QWQ_ANDROID_RELEASE_KEY_PASSWORD`
- `QWQ_ANDROID_EXPECTED_SIGNING_CERTIFICATE_SHA256`
- `QWQ_ANDROID_NONPROD_GOOGLE_SERVICES_JSON`
- `QWQ_ANDROID_PROD_GOOGLE_SERVICES_JSON`
- `QWQ_APP_RUNTIME_CONFIG_PROD_TRUSTED_PUBLIC_KEYS_JSON`

当前 App factory 同时读取这些非机密 Environment variables：

- `PROD_OPS_OIDC_ISSUER`
- `PROD_OPS_OIDC_CLIENT_ID`
- `PROD_OPS_OIDC_AUDIENCE`
- `PROD_OPS_OIDC_SCOPE`

GitHub OIDC、GHCR write/read 与 attestation signer identity必须有受信策略校验。iOS 最终签名/分发凭据尚无当前 workflow 中的正式 secret 命名与接线；不得虚构名称或用 unsigned `.app` 代替最终 iOS package acceptance。

### Prod runner-local SSH keys

`deploy-prod-auto.yml` 当前没有直接读取自定义 Actions SSH secret。正式 `prod-hosted` 运行应由受保护 runner 按 `quwoquan_ops/environments/prod/access-isolation.yaml` 使用本地 keyring 或 ssh-agent；私钥不能进入仓库、Actions Artifact 或日志。

默认 runner-local keyring 是 `~/.ssh/quwoquan-prod/`，文件按 Linux service account 命名：

- `prod-edge-svc` 对应 `PROD_EDGE_SSH_KEY`；
- `prod-media-svc` 对应 `PROD_MEDIA_SSH_KEY`；
- `prod-service-svc` 对应 `PROD_SERVICE_SSH_KEY`；
- `prod-data-svc` 对应只读审计 `PROD_DATA_SSH_KEY`；
- `prod-ops` 对应仅 bootstrap/凭据分发使用的 `PROD_OPS_SSH_KEY`。

正式 rollout 只要求当前 stage/placement 实际涉及的 read-write 平面。每把运行 key 还必须有安全引用、签发方、带时区有效期与规范化公钥 SHA-256 metadata，并与私钥导出的公钥一致。当前 workflow 尚未展示这些值的安全注入与 validator 接线，因此不能把本节当作“runner 已就绪”的证明。

## 7. 必需 hosted authorities

以下 authority 必须 create-once、可认证、可 exact-byte readback，且后继只按 digest 引用：

- GitHub refs、promotion PR/check、branch/tag ruleset、creator 与 main reachability readback；
- trusted integration publisher broker 的 CAS before/after/other 终态；
- Environment Ops 的 DSSE signer/key trust 与 Alpha/Beta/Gamma evidence store；
- promotion approval/threads/boundary/ruleset facts 和永久全样本 timing ledger；
- RC selection、monotonic artifact build-number allocator、SBOM/provenance/signing attestations 与 qualification evidence store；
- ProductVersionManifest 对应的 previous-stable import 或 initial-release authority、product authority、release authority；
- hosted human authority：真实 PostgreSQL、独立 provider signing key、正式 OIDC issuer/client/JWKS/groups、至少两个不同 MFA principals，以及 GitHub App webhook append-only ledger；
- Prod service-plane append-only ledger：previous active released digests、rollback readiness、每 placement/stage evidence、terminal released fact 与独立 soak observations；
- GHCR/OCI registry 的 digest existence、signature、OIDC issuer/workflow identity 与 readback authority。

这些 authority 不能由本地 JSON、聊天确认、Review PASS、workflow conclusion、Actions Artifact 或 repository variable 替代。

## 8. 当前必须 fail closed 的外部前提

截至当前仓库快照，以下事实不能从源码与 workflow 文件推导为已闭合：

- `quwoquan_ops/policies/product_version.yaml` 的 release train 为 `inactive`，previous stable 为 `not_imported`，initial release authority 为 `absent`，activation 为 `blocked`；因此 RC/stable 发布链尚未激活。
- Hosted branch protection/ruleset、唯一 promotion binding、system actor 与八条允许 refs 的真实 API readback 尚未提供；在此前 `hostedProtectionVerified=false`、`formalProd=false`。
- `dev1.0` ruleset 尚未把 `04. Lane Gate` 设为 `required_status_checks`（须 strict、`do_not_enforce_on_create=false`），且当前带一条无规格来源的 `DeployKey`/`always` bypass actor（PR #77 首次 hosted 读回 `34077603331` 已实证缺 required check 即 fail closed）。governance job 的只读 `github.token` 读不到 `bypass_actors`（GitHub 只向 ruleset write 权限返回该字段），因此读回只在字段可见且非空时阻断并以 `bypassActorsObservable` 留痕；该 bypass 须由 admin 按 daily-merge-release-strategy OPEN-004 移除，不能指望 governance job 替其证明。缺 required check 时 `04. Lane Gate` 转红，lane PR 不可视为已通过 hosted 强制。该 ruleset **不得**加 `pull_request` 规则（会封死 integration fast-forward 合入通道）；promotion 后 `main -> dev1.0` 回同步推的是 merge commit、不带本 check，在专用 system backsync actor 与其 bypass 语义就位前（daily-merge-release-strategy OPEN-004）只能由人工按 OPEN 流程处理。
- 受管 system backsync 尚无执行面：`system-backsync` Environment 与仅写 `dev1.0` 的 `SYSTEM_BACKSYNC_DEPLOY_KEY` 未配置，`delivery-gate.yml` 也不再调用 reusable backsync；当前回同步只由 integration 工作区 `make promotion-backsync` 完成（daily-merge-release-strategy OPEN-004）。
- `03. Delivery Gate` 验签只依赖仓内 `evidence_signing_keyring.yaml`；keyring 缺 identity 的 active 公钥、或 IQF/EAF 由未登记 key 签发时，PR job 在验签步骤 fail closed（不需要也不接受 repository secret）。
- trusted publisher 的真实 GitHub App/broker credential、跨主机协调与 Hosted ref CAS/readback 尚缺外部证明。
- RC workflow 尚未真实闭合 service/app factory dispatch、hosted build-number CAS、最终 Android/iOS 签名包、双物理平台 acceptance、Provider、Remote UAT 与 supply-chain facts。
- release controller 尚未闭合 creator/ruleset readback、RC/stable admission 发布和不可变 tag 保护的真实 Hosted 证据。
- production approval authority 所需 GitHub App installation/webhook secret、hosted DB/provider signing key、OIDC/MFA principals 与 durable request/approved readback 尚缺正式 UAT evidence。
- `prod-hosted` 多 placement 真实 SSH rollout、SLO gate、故障注入、previous-stable 自动回滚与 terminal/soak readback 尚缺生产演练证据。
- 当前 Prod workflow 的 admission output 与 runner credentials 仍为未闭合接线，不能启动正式 mutation。
- 正式 iOS identity、签名/分发接线与物理设备验收尚未闭合；Android 外部平台登记也必须与冻结 applicationId 和签名证书摘要一致。

任一前提缺失、过期、签名错误、source/tree/material/tag/digest/authority 漂移或 readback 不一致，都必须保留首个 typed blocker，不得降级为 warning 或借用历史 receipt。

## 9. 配置与核对原则

1. 先在 Hosted 系统建立独立 Apps、Environments、keys、rulesets 与 append-only authorities，再以只读 API/readback证明实际状态。
2. 只把当前 workflow 明确读取的 secret/variable 配置到对应 Environment；尚无接线的 credential 先保持外部 blocker，不创建同义变量或“备用”入口。
3. 所有 private key/token 只在最小权限边界短时物化；日志、Artifact、receipt 与仓库只能记录不可逆 public digest/reference。
4. 首次 formal release 前，必须完成从 qualified RC 到 stable admission、一次 production approval、exact-digest rollout、failure rollback 与 soak 的同一 candidate真实演练。
5. 任何文档、测试或 workflow 只能陈述已由当前 exact readback证明的层级；本地 contract PASS 不等于 Hosted、runtime、release 或 UAT 闭环。
