# L3 Story：每日合并发布策略 (`daily-merge-release-strategy`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与应用交付与发布验收。

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望 lane worktree 与 integration 都能在明确文件范围内并行构造 exact candidate，既可由受信 publisher 在本地环境准入后 CAS 更新 `dev1.0`，也可由唯一 integration 工作区以可证明的 non-force fast-forward 普通 push 提交源码，再把具备完整资格链的已集成可用源码快速晋级到 `main`，
从而既不强迫跨模块修复返回原 worktree，也不让未验字节、并行覆盖或 main 最新状态直接进入 Prod。

## 2. 范围与非目标

### In Scope

- `dev1.0` 集成分支、`main` 可用源码分支与六条长期 lane 分支的唯一角色、合法 promotion 边以及白名单外任何分支的禁令。
- 人工 direct push、PR head/base、系统 fast-forward backsync 与 Prod source admission 的可观察准入结果。
- 非法边、非 fast-forward、远端状态不可证明与 SHA 不可达 `main` 时的 fail-closed 终态。
- GitHub 托管 refs、branch protection/ruleset 与 system actor 权限的只读 readback 和当前有效性证明。

### Out of Scope

- hook、workflow、GitHub ref 与发布脚本的具体实现；由本 Story 的验收约束实现，不在规格复制代码。
- GitHub 原生 branch protection/ruleset 与系统 App 权限的创建或变更。
- 历史分支迁移、真实环境部署、Prod rollout，以及 `quwoquan_data/**` 的任何代码、内容或发布工作。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分支角色与 scoped candidate

- 本地与远端只允许 `dev1.0`、`main` 与六条长期 `lane/*`。lane 是长期来源工作面，integration 是跨模块集成工作面；两者都可按不重叠整文件 scope 构造 candidate。lane 仍只推同名 lane；唯一 `integration/` 工作区可从匹配本地 `refs/heads/dev1.0` 以普通认证 Git push 更新远端同名分支，但只允许 non-force fast-forward。
- `dev1.0` 是唯一集成 ref，接受 `trusted_integration_publisher_cas`、`integration_worktree_fast_forward` 与 `system_fast_forward_backsync` 三条通道；publisher 保留为 exact candidate + Alpha/Beta 准入通道，但不再是唯一 writer。`main` 是最新 source-admitted 源码，只接受 `dev1.0 -> main` promotion PR，不是 Prod source selector。
- 每个 candidate 必须绑定 expected `origin/dev1.0` parent、exact commit/tree、scope、changed paths、owner、ImpactPlan、source facts 与私有 index identity；scope 外 tree 逐字继承 parent。parent 或 scope generation 漂移使 candidate 和全部环境事实失效。
- 同一 worktree 可有多个不重叠文件 writer；同文件、父子路径、rename/delete、生成物、Git index/HEAD/ref、环境、设备、package 与外部 mutation 竞争只能有一个 winner。未知 dirty、无 owner 或越界字节不得被隐式纳入 candidate。

<a id="req-002"></a>
### REQ-002 集成、promotion 与回同步准入

- trusted publisher 只在 source facts 与 required Alpha/Beta `EnvironmentAcceptanceFact` 均绑定同一 candidate、签名和 cleanup 闭合时，以 expected remote OID 执行一次非 force fast-forward CAS 并 exact readback。唯一 integration 工作区的普通认证 direct push 必须 head/base 均为 `dev1.0`、本地来源精确为 `refs/heads/dev1.0`，并使用 pre-push update line 的 before/after OID 调用 Git ancestry authority；相等可幂等通过，缺 OID、authority 不可用、非快进、force、删除、来源不匹配、lane→dev、任意 `main` direct push、未知 remote/ref 或 unknown result 盲重试全部拒绝。
- CAS loser必须从新parent重建candidate与环境事实；网络结果按remote=`before|after|other`回读收口，不得stash、reset、自动merge或吸收其他writer字节。
- `dev1.0 -> main` 是唯一 promotion PR 边，只接受 current dev head 的 `IntegrationQualificationFact`。promotion 成功后，`main -> dev1.0` 的回同步只能是无 force 的 fast-forward：当前由唯一 integration 工作区按自身 FF 通道执行（校验远端 main 头是恰好一次两父 merge 且第二父等于本地 `dev1.0` 头，`--ff-only` 后推送并读回 `after`），受管 system actor 通道保留同一 expected-before 语义但尚无 caller（见 OPEN-004）。两者都是 equal 幂等成功，分叉或漂移零写阻断，不得 reset、stash 或自动 merge。
- integration worktree direct fast-forward push 仅把源码提交到 `dev1.0`，不签发 `integrationEligibility`、Alpha/Beta/Gamma、`IntegrationQualificationFact`、promotion、release 或 Prod authority。需要 main promotion/发布时仍必须走 exact candidate + Alpha/Beta、current dev head Gamma 与既有后续资格链。main合入结果也仅为`source-admitted`；Prod source admission必须从不可移动正式SemVer标签的AdmissionFact解析可达main的peeled commit和exact OCI digests；dev-only、RC-only、main HEAD、裸SHA或缺唯一promotion绑定均不得进入Prod。
- integration 工作区通道同样可以携带资格，且与 publisher 通道共用同一事实形态：把 integration 本地 HEAD 或某个 lane head 作为 exact candidate（scope 即相对当前远端 `dev1.0` 的全部 changed paths，claim 仍走同一 append-only generation），在远端 ref 尚未移动前由 ImpactPlan 派生集成深度、完成本地 readiness source fact 与 Alpha（`abg_release_sensitive` 时含 Beta，否则 Beta 以 typed `not_required` 事实闭合）`EnvironmentAcceptanceFact`，形成 publish admission；随后以 expected-old lease 的 non-force fast-forward push 更新远端并按 `before|after|other` 精确读回，只有读回 `after` 才写入 publish result。该 publish result 与 publisher CAS 的结果同 schema，可作为 current dev head Gamma 与 `IntegrationQualificationFact` 的前驱；缺 admission 的裸直推、读回 `before`（零写）或 `other`（他方先行）都不产生任何事实。lane→`dev1.0` 的 Pull Request 是评审与可见性载体，并承载 hosted 静态/合同复算 required check（`required_integration_checks`，只复算治理、影响面与 ops 本地合同，不启动任何环境）；合入本身由 integration 工作区按该通道执行——远端 `dev1.0` 一旦包含 lane head，PR 即由 hosted 侧标记为 merged，环境证据只来自该通道的 Alpha/Beta 事实。
- `conditional_beta` 判定唯一由 `quwoquan_ops/ci/impact_planner_core.py` 的 `derive_integration_depth` 派生，不得人工降档：`data|topology` → `abg_release_sensitive`（Alpha 与 Beta 都真跑）；`app|service|portal` → `alpha_integration`（只真跑 Alpha，Beta 以 `not_required` + `IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED` 闭合）；五 scope 全空 → `no_live`（不启动环境）。`integrationEligibility` 是本地 readiness 正交维度（producer=`trusted_integration_publisher`，状态 `not_evaluated|eligible|blocked`），只在 exact candidate 的 publish admission 绑定 passed source fact 与 required Alpha/条件 Beta 事实之后由 publisher/integration FF 通道写成 `eligible`；裸直推、L0/L1/L2 source readiness 与 Environment Ops 的 `environmentReadiness` 都不得推导该维度。
- Alpha/Beta/Gamma `EnvironmentAcceptanceFact` 与 `IntegrationQualificationFact` 的签名只接受 Ed25519（`ed25519:<base64>`），signer identity 与其 active 公钥的唯一真相源是仓内 `quwoquan_ops/policies/evidence_signing_keyring.yaml`；私钥只在本地仓外由 `make evidence-signing-bootstrap` 生成，hosted Delivery Gate 只用 PR head exact bytes 中的 keyring 验签、不持有任何 secret。两个 identity 的 active 公钥不得相同；retired key 不参与验签（见 [L2 DEC-010](../design.md#dec-010)）。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- 机器合同：`quwoquan_ops/policies/branch_policy.yaml`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 scoped candidate与受信集成发布

- GIVEN 两个writer基于同一expected dev parent声明候选scope。
- WHEN 它们构造并请求发布candidate。
- THEN 不重叠整文件scope可分别形成只含本scope字节的exact commit；同路径、父子、rename/delete、共享生成物或Git ref竞争只有一个winner。
- AND source及required Alpha/Beta事实完全匹配的candidate可由trusted publisher CAS写入dev；匹配integration worktree的普通认证push仅在before/after OID可证明non-force fast-forward时写入源码。direct push不产生任何集成、晋级、发布或Prod资格；parent漂移、未知dirty、越界字节、签名或cleanup缺失仍不得冒充publisher准入。
- AND 以 integration 本地 HEAD 或 lane head 构造的 exact candidate，其 scope 等于相对远端 `dev1.0` 的全部 changed paths，parent 非祖先时拒绝；携带 passed source fact 与 Alpha/条件 Beta 事实的 admission 经 expected-old lease fast-forward push 后，读回 `after` 才写出 publish result，读回 `before` 为零写 STALE/不可用，读回 `other` 为 CAS 冲突且不得 stash、reset 或自动 merge。
- AND 该 publish result 与 publisher CAS 结果同 schema，可作为 current dev head Gamma 与 `IntegrationQualificationFact` 的前驱；没有 admission 的裸直推、失败的 source fact 或环境事实缺失都不能进入 admission。
- AND 每份 EAF/IQF 的 `signer.signature` 只能由仓内 keyring 中该 identity 的 active Ed25519 公钥验签通过；错误 key、retired key、非 canonical 编码、identity 未登记或两 identity 共用同一公钥均 fail closed，私钥不在仓内、`.qwq_output` 或 hosted secret 中出现。

<a id="gwt-002"></a>
### GWT-002 五分钟promotion与system backsync

- GIVEN current dev head已有匹配的IntegrationQualificationFact且main base稳定。
- WHEN 创建`dev1.0 -> main` promotion并完成merge。
- THEN 唯一required context只验branch/tree/evidence/approval/ruleset并生成MainSourceSeal，随后回同步（integration FF 通道或受管 system actor）以expected-before无force fast-forward更新dev；equal幂等，分叉或漂移零写阻断。
- AND `dev1.0 -> main` 与 `lane/* -> dev1.0` 各有独立的 required check：前者由 `required_promotion_checks` 唯一声明并展开为 main ruleset 期望值，后者由 `required_integration_checks` 唯一声明（`04. Lane Gate`，见 `local-continuous-integration#gwt-005`）；两者不共享 workflow 或名字。reusable `system-backsync.yml` 只引用 GitHub Actions 合法上下文，其 `QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF` 由 caller 的 `github.repository`/`github.ref` 拼装，静态门禁拒绝任何非 `container|services|status` 的 `job.*` 属性。

<a id="gwt-003"></a>
### GWT-003 main可用源码与Prod版本选择分离

- GIVEN main持续前移且历史上存在qualified RC与stable release。
- WHEN 查询或请求Prod source admission。
- THEN main head变化不创建tag、不构建、不改变Prod；只有stable tag AdmissionFact绑定的main-reachable commit和exact digests可进入Prod。
- AND dev-only、RC-only、main HEAD、裸SHA、mutable tag或“最新qualified”查询均不能取得Prod eligibility。

<a id="gwt-004"></a>
### GWT-004 RC 准入与资格工厂分离

- GIVEN `ProductVersionManifest` 已激活且 main 上存在 create-only RC `ReleaseTagAdmissionFact`。
- WHEN 产品选择该 RC 进入资格工厂。
- THEN 资格工厂必须绑定 package acceptance、provider、UAT 与 supply-chain 四类事实及 Android keystore，缺任一类不得签发 `QualificationFact`，也不得创建 stable tag。
- AND 晋级 ratchet 与 hosted CI 超时/缓存/soak 占用不得用假样本或放宽例外收紧；未达 `quwoquan_ops/policies/promotion_timing_ratchet.yaml` 声明的窗口与最低 eligible 次数前保持现行阈值。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 每日合并发布策略 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：仓内 decision-table 已覆盖普通 lane 同名 push、匹配 integration worktree 的 direct fast-forward push，以及可证明 system fast-forward backsync；尚缺真实 scoped candidate、trusted publisher CAS、`dev1.0 -> main` PR/check、promotion 后 system CAS backsync，以及 hosted 八条分支权威清单与干净 clone 复现回执。Hosted 仍需证明 non-fast-forward、delete/force 与 `main` direct push 保护，但 direct fast-forward dev push 不再定义为非法。此外 `promotion_verify` 调用 `integration_qualification.py` 时仍缺 `--qualification-verification-key-env`、`--environment-verification-key-env` 与 `--expected-{qualification,alpha,beta,gamma}-signer-identity`：workflow 只注入一把 `QWQ_INTEGRATION_QUALIFICATION_SIGNING_KEY`，而合同要求两把互异 verification key 与四个 SPIFFE signer identity，且仓内尚无这些 identity 与 key env 名的 canonical 真相源（生产侧 `environment_execution.py` / `integration_candidate.py` 同样只以 required 参数接收、无默认值）。该脚本含 f-string 命名的 required 选项，`verify_workflow_cli_arguments.py` 对它整体判为不可静态判定而非放行；在真相源建立并接线前，promotion 门禁在该 step 必以 argparse exit 2 结束。另外 `deploy-prod-auto.yml` 与 `release-qualification.yml` 三处以 `${{ github.run_started_at }}` 填充 `--admitted-at` / `--created-at` / `--qualified-at`，该上下文属性在 GitHub Actions 中不存在，运行期展开为空串，会让对应 fact 的时间戳字段为空或被 CLI 拒绝。
- 完成判定：`GWT-001.t1..t2` 与 `GWT-002.t1..t2` 具备 decision-table local contract；signer identity 与两把 verification key env 名进入版本化 policy 并由 `promotion_verify` 逐一传入，`integration_qualification.py` 的合同测试覆盖 workflow 调用形态；当前最终 SHA 的 hosted readback 证明 lane PR/check、promotion PR/check、system actor、八条 refs 闭集以及 dev non-FF/force/delete 与 main direct-push 保护，真实 system backsync 证明 CAS 与 ref before/after。

<a id="open-002"></a>
### OPEN-002 private-free GitHub 托管分支保护

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 阻断边界：仅阻断 `formalProd` 与“GitHub 原生保护已闭合”声明；不阻断已由 Hosted API 精确证明的 promotion source validation。
- 影响或价值：仓内 hook/Actions 不能冒充服务端保护。当前 source admission 必须逐次从 Hosted API 证明 exact merge SHA、最终 `dev1.0` head、绑定该 head 的 approval、canonical required workflow run/attempt/check identity、当前 main reachability、repository default branch 与当前 workflow attempt；历史 bootstrap create、普通 lane push与integration worktree direct fast-forward push都缺唯一promotion binding且不具备release eligibility。Hosted ruleset仍须证明`dev1.0` non-fast-forward、force/delete与`main` direct push被阻断；合法matching integration fast-forward不再被定义为绕过publisher或非法更新。托管ruleset的适用条件、bypass actor与required check readback未精确闭合前，不能签发正式Prod。
- 完成判定：`GWT-002.t1..t2` 与 `GWT-003.t1..t2` 的 GitHub refs、适用 ruleset/branch protection 与 system actor 权限均由托管 API readback 证明；在此之前 `hostedProtectionVerified=false / formalProd=false` 保持不变。

<a id="open-003"></a>
### OPEN-003 六 lane activation、canary 与 direct-push 收敛

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：六条固定 lane 已开放。尚缺 hosted readback、六条 lane canary、integration/abort 终态与 retained worktree mandatory fast-forward resync 证据；该观察证据不改变 lane→dev、main direct push、non-fast-forward、force/delete禁令，也不把integration direct fast-forward push升级为任何资格事实。
- 完成判定：`GWT-001.t3`、`GWT-001.t4` 持续由 local contract 绑定；hosted readback 证明 canonical active，六条 lane 各至少完成一次 canary，integration 或 abort 后均证明 worktree retained、lane fast-forward 到新的 `dev1.0`。
- 依赖：[`objective-execution` OPEN-002](../../development-workflow-governance/objective-execution/spec.md#open-002) 的六并发证据、[`local-worktree-lifecycle-governance`](../../system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md) 的 worktree 授权提醒、Delivery Gate exact candidate evidence。

<a id="open-004"></a>
### OPEN-004 受管 system backsync 与 hosted publisher broker 尚无执行面

- 类型：`external_blocker`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`dev1.0` 三条写入通道中，trusted publisher CAS 需要 hosted authenticated broker，受管 system backsync 需要专用 `SYSTEM_BACKSYNC_DEPLOY_KEY` 与 `system-backsync` Environment；两者当前都没有外部执行面。现行闭环全部由 integration 工作区 FF 通道承担（`make integrate` 发布、`make promotion-backsync` 回同步），reusable `system-backsync.yml` 保留合同但无 caller。
- 完成判定：`GWT-001.t2` 的 publisher CAS 与 `GWT-002.t2` 的 system actor 回同步各有一次真实 hosted 执行回执，且与 integration FF 通道产生的 publish result / 回同步读回同 schema、同终态。
- 依赖：hosted broker 凭据与 URL、dedicated deploy key、`system-backsync` Environment。

<a id="open-005"></a>
### OPEN-005 CI 效率、晋级 ratchet 与 RC factory 四类事实缺口

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`06. RC Qualification Factory` 尚缺 package acceptance、provider、UAT、supply-chain 四类事实生产者与 Android keystore，因此不得签发 `QualificationFact` 或 stable tag。`deploy-prod-auto.yml` 的 job timeout 小于内部 deadline；soak 占用自托管 runner；ARM 上 QEMU 编 amd64；`validate-deploy` 重复 verify；`app_pipeline` 五个 macOS job 无缓存且 nonprod 产物不进 CMM；多次 Environment 审批串行。`promotion_timing_ratchet.yaml` 的窗口与最低 eligible 次数尚未满足，不得收紧阈值。
- 完成判定：`GWT-004.t1` 的四类事实与 keystore 各有真实生产者与 hosted 回执；`GWT-004.t2` 的 ratchet 达到 `promotion_timing_ratchet.yaml` 声明的窗口与最低 eligible 次数后单调收紧一次，且 CI 超时/缓存/soak 占用不再用假样本或放宽例外。
- 依赖：[`OPEN-004`](#open-004)、GHCR `write:packages`。

<a id="open-006"></a>
### OPEN-006 本机没有满足当前 Data release 合同的 immutable release，模式二 Alpha 在 ship apply 处阻断

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 阻断边界：只阻断 Alpha/Beta `EnvironmentAcceptanceFact` 的真实签发与其后的 publish admission；不阻断 L1 readiness、exact candidate、打包（`sourceRevision == candidate` 已证明）、`up`/`down` 与 Ed25519 keyring 验签本身。
- 影响或价值：`make integrate` 已真实跑到 `alpha.data-release`：`qwq-data ship apply` 以 `release_header … source identity set requires a pool selection` 拒绝 `release-20260906-intersection-flywheel-001`；本机全部 30 份 immutable release（product-mainline 与 data-engineering 产出）的 `selectionScope` 仍是硬切前的 `all_publishable`，无一满足 dev1.0 当前 `content.release.canonical.release_header` 合同。health 的 `release_active` 层依赖该导入回执，因此 Alpha 不能在没有合同兼容 release 的情况下签发 passed 事实；不得放宽合同或伪造回执。
- 完成判定：`GWT-001.t3` 由 Data lane 以 `content-production` Skill 在当前合同下产出一对（candidate、rollback）immutable research release 并附 attestation 后，`make integrate PUBLISH=0` 对 exact candidate 完整产出 Alpha（及条件 Beta）`EnvironmentAcceptanceFact`，summary 各分段耗时齐全。
- 依赖：Data lane 的合同兼容 release 交付；`quwoquan_data/scripts/content/release/canonical/release_header.py` 的 `selectionScope ∈ {target_environment, explicit_cohort}`。
