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
- `dev1.0 -> main` 是唯一 promotion PR 边，只接受 current dev head 的 `IntegrationQualificationFact`。promotion成功后，受管system actor仅以expected-before做`main -> dev1.0`无force fast-forward backsync；equal幂等成功，分叉或漂移阻断。
- integration worktree direct fast-forward push 仅把源码提交到 `dev1.0`，不签发 `integrationEligibility`、Alpha/Beta/Gamma、`IntegrationQualificationFact`、promotion、release 或 Prod authority。需要 main promotion/发布时仍必须走 exact candidate + Alpha/Beta（可由 publisher 通道）、current dev head Gamma 与既有后续资格链。main合入结果也仅为`source-admitted`；Prod source admission必须从不可移动正式SemVer标签的AdmissionFact解析可达main的peeled commit和exact OCI digests；dev-only、RC-only、main HEAD、裸SHA或缺唯一promotion绑定均不得进入Prod。

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

<a id="gwt-002"></a>
### GWT-002 五分钟promotion与system backsync

- GIVEN current dev head已有匹配的IntegrationQualificationFact且main base稳定。
- WHEN 创建`dev1.0 -> main` promotion并完成merge。
- THEN 唯一required context只验branch/tree/evidence/approval/ruleset并生成MainSourceSeal，随后system actor以expected-before无forceCAS回同步dev；equal幂等，分叉或漂移零写阻断。
- AND `dev1.0 -> main` 与 `lane/* -> dev1.0` 各有独立的 required check：前者由 `required_promotion_checks` 唯一声明并展开为 main ruleset 期望值，后者由 `required_integration_checks` 唯一声明（`04. Lane Gate`，见 `local-continuous-integration#gwt-005`）；两者不共享 workflow 或名字。reusable `system-backsync.yml` 只引用 GitHub Actions 合法上下文，其 `QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF` 由 caller 的 `github.repository`/`github.ref` 拼装，静态门禁拒绝任何非 `container|services|status` 的 `job.*` 属性。

<a id="gwt-003"></a>
### GWT-003 main可用源码与Prod版本选择分离

- GIVEN main持续前移且历史上存在qualified RC与stable release。
- WHEN 查询或请求Prod source admission。
- THEN main head变化不创建tag、不构建、不改变Prod；只有stable tag AdmissionFact绑定的main-reachable commit和exact digests可进入Prod。
- AND dev-only、RC-only、main HEAD、裸SHA、mutable tag或“最新qualified”查询均不能取得Prod eligibility。

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
