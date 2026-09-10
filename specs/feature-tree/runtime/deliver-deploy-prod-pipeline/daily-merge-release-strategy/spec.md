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
- 带资格的合入是「lane 验收 → integration 发布」两段式，与 publisher 通道共用同一事实形态。lane 工作树（当前分支为该 lane，head 即 exact candidate；scope 为相对 baseline 的全部 changed paths，claim 仍走同一 append-only generation）以 `make accept` 在远端 ref 尚未移动前完成：ImpactPlan 派生集成深度、本地 readiness source fact、Alpha `EnvironmentAcceptanceFact` 必跑、Beta 仅显式 `BETA=1` 才真跑（否则 typed `not_required`），终态 `accepted` 并把 candidate/claim/source fact/两份 EAF 及其全部 case/named 证据按 store 相对路径打成 portable acceptance bundle（`bundle.json` 记录 candidate 身份、expectedParent、lane 来源、每文件 exact digest 与 `bundleId`）。integration 工作区（分支 `dev1.0`，HEAD 已 fast-forward 到该 candidate）以 `make integrate ACCEPTANCE_BUNDLE=<dir>` 只做消费：逐字节按 manifest digest 导入本工作树 store（create-once，已存在且字节不同即 `INTEGRATION_RUN.BUNDLE_DRIFT`）、以仓内 keyring 验签并复核 EAF 全部引用与 candidate 绑定、要求 `commit/tree == HEAD` 且 `expectedParent == 当前远端 dev1.0`（否则 `BUNDLE_CANDIDATE_MISMATCH` / `BUNDLE_STALE`，后者须在合入新 `dev1.0` 的 head 上重新 `make accept`），然后形成 publish admission，以 expected-old lease 的 non-force fast-forward push 更新远端并按 `before|after|other` 精确读回，只有读回 `after` 才写入 publish result。integration 不启动任何环境、不接受 Data release 输入；缺 bundle 即 `INTEGRATION_RUN.ACCEPTANCE_REQUIRED`。该 publish result 与 publisher CAS 的结果同 schema，可作为 current dev head Gamma 与 `IntegrationQualificationFact` 的前驱；缺 admission 的裸直推、读回 `before`（零写）或 `other`（他方先行）都不产生任何事实。lane→`dev1.0` 的 Pull Request 是评审与可见性载体，并承载 hosted 静态/合同复算 required check（`required_integration_checks`，只复算治理、影响面与 ops 本地合同，不启动任何环境）；合入本身由 integration 工作区按该通道执行——远端 `dev1.0` 一旦包含 lane head，PR 即由 hosted 侧标记为 merged，环境证据只来自 lane bundle 中的 Alpha/Beta 事实。
- Alpha/Beta 的签发位置是产出 Data release handoff 的 lane 工作树（`--mode acceptance`，不 admit、不写 `dev1.0`、拒绝 `--publish`）；integration 工作区独占 admit/publish 及其后的集成验证——集成验证只有两级：`gamma-local` 对 current exact `dev1.0` head 的 Gamma，以及可选的 prod canary 放量。用户可显式把多个 lane head 合并为一个 candidate 后一次验收，`--merged-lanes lane/<name>` 逐一记录来源且每个都必须是 candidate 的祖先，bundle 的 `mergedLanes` 随之进入 integration summary。lane 已裸 fast-forward 落地后仍可对同一 head 验收，须显式 `--baseline <上一个已验收基线>`，否则 `INTEGRATION_RUN.NOTHING_TO_ACCEPT`；不得为在 `dev1.0` 分支上跑通 ship admission 而放宽 `validate_current` 或复制他方 lane 的证据字节（见 [L2 DEC-014](../design.md#dec-014)）。
- 集成深度仍唯一由 `quwoquan_ops/ci/impact_planner_core.py` 的 `derive_integration_depth` 派生（`data|topology` → `abg_release_sensitive`；`app|service|portal` → `alpha_integration`；五 scope 全空 → `no_live`，不启动环境），但不再决定 Beta 是否真跑或政策跳过的原因码：需要环境验收时 Alpha 必跑；Beta 只在显式 `--beta` 时真跑，否则无论集成深度为何都签 `status=not_required`、`reasonCode=ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`。事实合同保留 `IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED` 表达 ImpactPlan 本身的免环境结论，但不得代替本通道未 opt-in 的政策原因；签发（`environment_scheduler`）、schema（`environment_acceptance_fact.schema.json`）与 admission（`create_publish_admission`）消费同一原因码闭集，其余原因码 fail closed，Alpha/Gamma 不得 `not_required`。`integrationEligibility` 是本地 readiness 正交维度（producer=`trusted_integration_publisher`，状态 `not_evaluated|eligible|blocked`），只在 exact candidate 的 publish admission 绑定 passed source fact 与 Alpha/Beta 事实之后由 publisher/integration FF 通道写成 `eligible`；裸直推、L0/L1/L2 source readiness 与 Environment Ops 的 `environmentReadiness` 都不得推导该维度。
- Alpha/Beta/Gamma `EnvironmentAcceptanceFact` 与 `IntegrationQualificationFact` 的签名只接受 Ed25519（`ed25519:<base64>`），signer identity 与其 active 公钥的唯一真相源是仓内 `quwoquan_ops/policies/evidence_signing_keyring.yaml`；私钥只在本地仓外由 `make evidence-signing-bootstrap` 生成，hosted Delivery Gate 只用 PR head exact bytes 中的 keyring 验签、不持有任何 secret。两个 identity 的 active 公钥不得相同；retired key 不参与验签（见 [L2 DEC-010](../design.md#dec-010)）。
- lane 与 `dev1.0` 之间只有两条本地同步通道，均由 Workflow Skill 显式执行、不由 hook 或 commit 隐式触发：`sync-lane-from-dev` 在当前 lane 工作树把本地 `dev1.0` 同步进本 lane（lane 已是 `dev1.0` 祖先时 `--ff-only`，否则普通 merge 并只在本 lane 解决冲突；工作树存在与本次变更重叠的脏文件、或已有进行中 merge/rebase 时零写阻断，禁止 reset/stash/clean）；`integrate-lane-to-dev` 只在唯一 integration 工作区把 lane head fast-forward 进 `dev1.0`，按本 REQ 的 publish admission 或裸 fast-forward 通道推送后，再对其余 lane 执行回同步。回同步只对「无进行中 merge、工作树干净或脏文件与本次 ff 不重叠、且是新 `dev1.0` 祖先」的 lane 执行 `--ff-only` 并推送同名远端；分叉或重叠脏树的 lane 只产出 typed 结果（`skipped_diverged` / `skipped_dirty_overlap`），由该 lane 自己的会话运行 `sync-lane-from-dev` 解决，任何通道都不得在他人工作树里自动 merge、覆盖或清理字节。
- 同一 exact candidate 的 readiness receipt 与 Alpha/Beta `EnvironmentAcceptanceFact` 可被 lane 的后续 `make accept REUSE=1` 复用：复用只按 candidate commit/tree、ImpactPlan digest 与 receipt fingerprint 精确匹配，命中即跳过重跑并在 summary 标记 `reused`；任一输入漂移都必须重跑，不得按时间窗、分支名或「最近一次」复用。因 OPEN-006 类外部阻断未能签发 Alpha 事实时，integration 工作区仍可按裸 fast-forward 通道推送源码并保留首个 typed blocker，但不得写出 publish result 或任何资格事实。

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
- AND lane 工作树 `make accept` 以 lane head 为 exact candidate（scope 等于相对 baseline 的全部 changed paths，baseline 非祖先时拒绝），Alpha 真跑、Beta 只在 `--beta` 时真跑，否则无论集成深度为何都以 `ACCEPTANCE.BETA_OPTIONAL_BY_POLICY` 签 typed `not_required`；终态 `accepted` 产出 acceptance bundle，不 admit、不写 `dev1.0`；用户显式合并多 lane 时 `--merged-lanes` 中每个 lane 都必须是 candidate 祖先。
- AND integration 工作区 `make integrate ACCEPTANCE_BUNDLE=…` 只导入并复核 bundle：manifest `bundleId` 与每个 store 文件的 exact digest 一致、create-once 导入、EAF 以仓内 keyring 验签且引用/candidate 绑定成立、`commit/tree == HEAD`、`expectedParent == 远端 before`；任一漂移 typed 拒绝（`BUNDLE_DRIFT` / `BUNDLE_CANDIDATE_MISMATCH` / `BUNDLE_STALE`），缺 bundle 为 `ACCEPTANCE_REQUIRED`，acceptance 专用输入出现在 integrate 为 `INPUT_INVALID`；integration 相位只有 preflight → import-bundle → admit（→ publish），不出现任何环境相位。
- AND 携带 passed source fact 与 Alpha/Beta 事实的 admission 经 expected-old lease fast-forward push 后，读回 `after` 才写出 publish result，读回 `before` 为零写 STALE/不可用，读回 `other` 为 CAS 冲突且不得 stash、reset 或自动 merge。
- AND 该 publish result 与 publisher CAS 结果同 schema，可作为 current dev head Gamma 与 `IntegrationQualificationFact` 的前驱；没有 admission 的裸直推、失败的 source fact 或环境事实缺失都不能进入 admission。
- AND 每份 EAF/IQF 的 `signer.signature` 只能由仓内 keyring 中该 identity 的 active Ed25519 公钥验签通过；错误 key、retired key、非 canonical 编码、identity 未登记或两 identity 共用同一公钥均 fail closed，私钥不在仓内、`.qwq_output` 或 hosted secret 中出现。

<a id="gwt-002"></a>
### GWT-002 五分钟promotion与system backsync

- GIVEN current dev head已有匹配的IntegrationQualificationFact且main base稳定。
- WHEN 创建`dev1.0 -> main` promotion并完成merge。
- THEN 唯一required context只验branch/tree/evidence/approval/ruleset并生成MainSourceSeal，随后回同步（integration FF 通道或受管 system actor）以expected-before无force fast-forward更新dev；equal幂等，分叉或漂移零写阻断。
- AND `dev1.0 -> main` 与 `lane/* -> dev1.0` 各有独立的 required check：前者由 `required_promotion_checks` 唯一声明并展开为 main ruleset 期望值，后者由 `required_integration_checks` 唯一声明（`04. Lane Gate`，见 `local-continuous-integration#gwt-005`）；两者不共享 workflow 或名字。reusable `system-backsync.yml` 只引用 GitHub Actions 合法上下文，其 `QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF` 由 `github.repository`/`github.ref` 拼装（当前无 caller，见 OPEN-004），静态门禁拒绝任何非 `container|services|status` 的 `job.*` 属性，actionlint 拦截解析期即失效的其余上下文/属性/类型错误。

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

<a id="gwt-005"></a>
### GWT-005 lane 回同步三态零写与 candidate 事实复用

- GIVEN 新 `dev1.0` 头已就位，六条 lane 分别处于「干净且为祖先」「脏文件与 ff 不重叠且为祖先」「脏文件与 ff 重叠」「已分叉」四种状态。
- WHEN 在 integration 工作区执行回同步。
- THEN 前两种 lane 被 `--ff-only` 推进到新 `dev1.0` 并推送同名远端；后两种 lane 的 HEAD、index 与工作树字节零变化，结果分别为 `skipped_dirty_overlap` 与 `skipped_diverged`；渲染模式只输出命令不移动任何 ref。
- AND 同一 exact candidate 在 lane 的第二次 `make accept REUSE=1` 复用 readiness receipt 与已签发 Alpha 事实并标记 `reused`；candidate commit、ImpactPlan digest 或 fingerprint 任一漂移都重跑，不复用。

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
- 影响或价值：仓内 decision-table 已覆盖普通 lane 同名 push、匹配 integration worktree 的 direct fast-forward push，以及可证明 system fast-forward backsync；尚缺真实 scoped candidate、trusted publisher CAS、`dev1.0 -> main` PR/check、promotion 后 system CAS backsync，以及 hosted 八条分支权威清单与干净 clone 复现回执。Hosted 仍需证明 non-fast-forward、delete/force 与 `main` direct push 保护，但 direct fast-forward dev push 不再定义为非法。`promotion_verify` 对 `integration_qualification.py` 的接线已收口：signer identity 的 canonical 真相源是 `quwoquan_ops/policies/evidence_signing_keyring.yaml`（Ed25519 公钥，见 [L2 DEC-010](../design.md#dec-010)），workflow 以 `--signing-keyring` 与四个 `--expected-*-signer-identity` 逐一传入，不再需要 verification key env 或 repository secret；`verify_workflow_cli_arguments.py` 已能静态展开该脚本常量循环内的 required 并对该调用判绿；workflow 里的 `QUALIFICATION_SIGNER_IDENTITY` / `ENVIRONMENT_SIGNER_IDENTITY` 字面常量由 `test_delivery_gate_signer_identity` 锁定为 keyring 已登记且 purpose 匹配的 identity 并逐一透传；`deploy-prod-auto.yml` / `release-qualification.yml` 的 `${{ github.run_started_at }}` 已改为 shell 侧 `date -u`。仍缺：真实 `dev1.0 -> main` PR/check 回执与 hosted readback 证据。
- 完成判定：`GWT-001.t1..t2` 与 `GWT-002.t1..t2` 具备 decision-table local contract；`integration_qualification.py` 的合同测试覆盖 workflow 调用形态（keyring 验签）；当前最终 SHA 的 hosted readback 证明 lane PR/check、promotion PR/check、system actor、八条 refs 闭集以及 dev non-FF/force/delete 与 main direct-push 保护，真实 system backsync 证明 CAS 与 ref before/after。

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
- 影响或价值：六条固定 lane 已开放。retained worktree 的 mandatory fast-forward resync 已有执行面（`make lane-resync-execute` 与 `integrate-lane-to-dev` Skill，三态零写由 `GWT-005.t1` 绑定），但尚缺 hosted readback、六条 lane canary 与 integration/abort 终态证据；该观察证据不改变 lane→dev、main direct push、non-fast-forward、force/delete禁令，也不把integration direct fast-forward push升级为任何资格事实。
- 完成判定：`GWT-001.t3`、`GWT-001.t4`、`GWT-005.t1` 持续由 local contract 绑定；hosted readback 证明 canonical active，六条 lane 各至少完成一次 canary，integration 或 abort 后均证明 worktree retained、lane fast-forward 到新的 `dev1.0`。
- 依赖：[`objective-execution` OPEN-002](../../development-workflow-governance/objective-execution/spec.md#open-002) 的六并发证据、[`local-worktree-lifecycle-governance`](../../system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md) 的 worktree 授权提醒、Delivery Gate exact candidate evidence。

<a id="open-004"></a>
### OPEN-004 受管 system backsync 与 hosted publisher broker 尚无执行面

- 类型：`external_blocker`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`dev1.0` 三条写入通道中，trusted publisher CAS 需要 hosted authenticated broker，受管 system backsync 需要专用 `SYSTEM_BACKSYNC_DEPLOY_KEY` 与 `system-backsync` Environment；两者当前都没有外部执行面。现行闭环全部由 integration 工作区 FF 通道承担（`make integrate` 发布、`make promotion-backsync` 回同步），reusable `system-backsync.yml` 保留合同但无 caller。`DEC-011` 把 `dev1.0` ruleset 设为 `required_status_checks=[04. Lane Gate]` 后，promotion 产生的 main merge commit 不带该 check，`make promotion-backsync` 的直推会被 ruleset 拒绝：回同步只能由专用 system backsync actor 以其自身 bypass 语义执行。`dev1.0` ruleset 上那条无规格来源的 `DeployKey`/`always` bypass（既不是该 actor，也让 `release-controller` 可写 key 获得强推能力）已由 admin 移除并以 `--require-bypass-observable` 读回证明（`hosted-integration-ruleset-receipt` evidenceDigest `sha256:d4021fe5c652bf482a8f1827da220b2f18cd678d54480539c9da30aff2b92fa7`，`bypassActorsObservable=true`），同时把 `04. Lane Gate` 设为 strict required check；`04. Lane Gate` 只读 governance job 的 readback 首次于 run `34078890252` 通过。本 OPEN 余下的是 system backsync actor 与 publisher broker 的执行面。
- 完成判定：`GWT-001.t2` 的 publisher CAS 与 `GWT-002.t2` 的 system actor 回同步各有一次真实 hosted 执行回执，且与 integration FF 通道产生的 publish result / 回同步读回同 schema、同终态；system backsync actor 的 bypass 不得同时豁免 `non_fast_forward`/`deletion`（GitHub bypass 按 ruleset 整体生效，因此 `required_status_checks` 须放入独立 ruleset 并只给该 actor bypass），且 `04. Lane Gate` 的 ruleset readback 显式接受这一结构与该唯一 actor。
- 依赖：hosted broker 凭据与 URL、dedicated deploy key、`system-backsync` Environment、ruleset bypass actor 只登记该 deploy key。

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
- 影响或价值：现役 DEC-041 已删除 release 类别，DEC-042 使用独立内容仓。旧 research/commercial/production attestation 与源码内旧 publish 包均不能充当当前输入；尚缺新协议下真实 candidate/rollback release、lane Alpha 消费与恢复回执。不得改旧 header、receipt 或摘要冒充新契约，也不以仅源码快进推导环境资格。
- 完成判定：`GWT-001.t6..t7` 使用当前无类别、显式 cohort、完整 source/media/review/record 的两份 immutable release，绑定 `RELEASE_ATTESTATION`、`ROLLBACK_RELEASE_ATTESTATION` 与 candidate `RELEASE_HANDOFF_REF`，在 producer lane 完成真实 Alpha（Beta 仅 `BETA=1`）并形成 accepted bundle；`GWT-001.t9..t12` 再独立证明 integration 消费 bundle 发布并读回 after。普通源码通道不要求 bundle，但不关闭本环境资格缺口。
- 依赖：`quwoquan_data/scripts/content/release/canonical/release_header.py` 的 `selectionScope ∈ {target_environment, explicit_cohort}`；empty_baseline writer 的恢复由 Data lane 决定，不阻断本 OPEN。

<a id="open-008"></a>
### OPEN-008 lane acceptance bundle → integration admit/publish 尚缺一次真实 hosted 发布回执

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：[L2 DEC-014](../design.md#dec-014) 的两段式已落地：`make accept` 在 lane 工作树终态 `accepted` 并写出 portable acceptance bundle；`make integrate ACCEPTANCE_BUNDLE=…` 只导入 bundle（create-once、digest 复核、keyring 验签、`expectedParent == 远端 before`）后 admit → publish，不再自己跑环境，也不再需要 Data release 输入，因此不会在 `dev1.0` 分支上撞到 ship handoff admission 的 `CANDIDATE.OWNER_DRIFT`。local contract 已覆盖 bundle round-trip、digest/manifest/commit/parent 漂移、缺 bundle 与 acceptance 专用输入的 typed 拒绝、integrate 相位闭集。尚缺的是一次真实闭环：同一 candidate 在 lane 工作树 `make accept` 产出 bundle，再由 integration 工作区消费并 fast-forward 发布到远端 `dev1.0`、读回 `after`。
- 完成判定：`GWT-001.t6..t12`——真实 lane `make accept` 的 summary（终态 `accepted`、`acceptanceBundle` 路径）与 integration `make integrate ACCEPTANCE_BUNDLE=… PUBLISH=1` 的 summary（相位 preflight → import-bundle → admit → publish，publish result 读回 `after`，`acceptanceBundle.bundleId` 等于 lane bundle）各一份，且远端 `dev1.0` 读回等于该 candidate。
- 依赖：[L2 DEC-014](../design.md#dec-014)；[`OPEN-006`](#open-006) 的 Alpha 真实签发。

<a id="open-007"></a>
### OPEN-007 `promotion_hosted.ruleset_fact` 把只读 token 下不可见的 `bypass_actors` 折成空并判 `passed`

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：GitHub 只向对 ruleset 有 write 权限的调用者返回 `bypass_actors`；`03. Delivery Gate` 的 `promotion_verify` 以只读 `github.token` 运行 `promotion_hosted.py hosted-authority`，其 `ruleset_fact` 用 `list(ruleset.get("bypass_actors") or [])` 把缺席字段当作 `[]`，于是 `requiredCheckEnforced=true` 与 `bypassActors: []` 写出了并未观测到的值。`04. Lane Gate` 侧的 `verify_hosted_integration_ruleset.py` 已改为"可见且非空才阻断、不可见以 `bypassActorsObservable=false` 留痕、admin 侧以 `--require-bypass-observable` 承担为空的证明"；main ruleset 读回尚未对齐同一观测边界，`CI_CD_SECRETS.md` 对"无 bypass actor"的陈述也超出只读 token 能证明的范围。
- 完成判定：`GWT-002.t1` 的 ruleset 事实由 `ruleset_fact` 以 `bypassActorsObservable` 显式区分"观测为空"与"不可见"，不可见时不输出 `bypassActors: []`，`requiredCheckEnforced` 只声明 required_status_checks 形状；main ruleset 的 bypass 为空由 admin 侧 `--require-bypass-observable` 读回或等价 write 权限读回签发，并在 `test_promotion_hosted` 以缺席/null/非空三态锁定；`GWT-002` 的 required context 在只读 token 下不再写出未观测到的值，并以只读 token 比对 `dev1.0` ruleset 当前 `updated_at` 与最近一次 admin 侧 `hosted-integration-ruleset-receipt` 的 `ruleset.updatedAt`，不一致即 typed 阻断（让「每次 promotion 前重跑 admin 读回」成为可审计的执行面而非文档声明）；`CI_CD_SECRETS.md` 同步措辞。
- 依赖：`local-continuous-integration#gwt-005` 已定义的观测边界；`03. Delivery Gate` 下一次真实 hosted 执行用于回归。

<a id="open-009"></a>
### OPEN-009 exact candidate 的 readiness 范围随远端 `dev1.0` 落后线性膨胀

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：模式二把 candidate scope 定义为相对远端 `dev1.0` 的全部 changed paths，因此每当本地 `dev1.0` 领先远端而未发布，下一次 `make integrate` 的 `readiness-fast` 都要覆盖累计差异；连续多次 integrate 运行中 changed paths 从数十涨到数百、`readiness-fast` 墙钟从数分钟涨到十余分钟并以 `INTEGRATION_RUN.L1_FAILED` 终止，进一步阻止发布、形成恶性循环。readiness receipt 与 Alpha 事实按 candidate 复用只消除同一 candidate 的重跑，不缩小 scope 本身。尚缺：candidate scope 相对「上一次已发布或已签发事实的 exact parent」的增量派生实现，以及证明 `readiness-fast` 输入规模不随未发布提交数单调增长的 local contract 验收证据。
- 完成判定：`GWT-005.t2` 持续绑定；candidate scope 可以按「相对上一次已发布/已签发事实的 exact parent」增量派生且仍绑定 100% changed paths 的 workspace digests，或 integration 工作区在每次成功 admission 后即刻发布使远端不再落后；两者之一落地并由 local contract 证明 `readiness-fast` 输入规模不再随未发布提交数单调增长。
- 依赖：[`OPEN-006`](#open-006) 解除后的真实 Alpha 签发；`quwoquan_ops/ci/scoped_candidate/` 的 parent 语义。

<a id="open-010"></a>
### OPEN-010 验收调度入口的职责拆分与复杂度收敛

- 类型：`risk`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：双端离线页面与服务/API 独立证据轴接入后，`quwoquan_ops/cli/integration_run.py` 的环境执行、exact 输入复用和 CLI 分派仍集中在同一入口。增量 Code Health 报 `_run_environment`、`_find_reusable_candidate`、`main` 复杂度与超千行 advisory，尚未超过硬阻断阈值；职责拆分必须保留完整失败与资源清理语义，不为降低指标扩大成验收框架重写。
- 完成判定：在原 CLI 入口不变、无第二调度轨道的前提下按现有职责提取上述边界；`GWT-001.t6..t12` 与 `GWT-005.t2` 的 exact candidate、release/rollback/handoff、双端 raw、签名、复用和 cleanup 负向合同保持通过，增量复杂度不再恶化且入口回到文件 advisory 阈值以内。
- 依赖：`quwoquan_ops/cli/integration_run.py`、`quwoquan_ops/cli/lib/integration_app_launch.py` 及现役 acceptance bundle/reuse local contract；仅源码健康后续项，不代替 required Alpha 或发布证据。
