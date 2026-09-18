# L3 Story：每日合并发布策略 (`daily-merge-release-strategy`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与应用交付与发布验收。

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望六个物理工作树共享远端 `origin/dev1.0`，lane 以本地 `lane/*` 身份构造 exact candidate 并签发 typed Alpha/Beta，唯一 integration 工作区只消费 acceptance bundle 以 non-force fast-forward 更新 `origin/dev1.0`，再把具备完整资格链的已集成可用源码晋级到 `main`，
从而既不强迫跨模块修复返回原 worktree，也不让未验字节、裸源码直推或 main 最新状态直接进入 Prod。

## 2. 范围与非目标

### In Scope

- 远端闭集（仅 `origin/dev1.0` 与 `origin/main`）、本地六条 `lane/*` 检出/验收 identity、`dev1.0`/`main` 角色、唯一 promotion 边，以及白名单外任何分支的禁令。
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

- 执行与保证边界：日常 dev 合入由本地 `accept → bundle → integrate` 与 hook 强制验收和 admission；下述缺证据零写约束指受管本地入口，不是 GitHub 对任意凭据的保证。dev 的旧 `04. Lane Gate` required check 按授权撤除，远端 lane 在权威读回证明其 exact tip 已可达已发布 dev 且未发布增量已保全后可删除，不以专用 publisher/broker 或 hosted 替代门先到位为条件。服务端必须保留 dev 禁删/禁 non-FF 与 main promotion 强制；普通已授权写凭据仍可能绕过本地流程直接 FF dev，服务端不能保证每次 dev 更新均经过 Alpha。该缺口保持 OPEN-004 `track`，不阻塞本地有效验收后的日常 dev 合入，也不产生任何环境/生产资格。

- 本地允许 `dev1.0`、`main` 与六条长期 `lane/*`。远端闭集只允许 `origin/dev1.0` 与 `origin/main`；存量 `origin/lane/*` 只是 leftover，不得作为写入目标。lane 是长期来源工作面与本地检出/验收 identity（Git 禁止同分支多工作树），不是独立远端交付线；六条本地 lane 的 upstream 统一指向 `origin/dev1.0`。integration 是已验候选的集成消费工作面；源码 writer 必须在现有 lane 按不重叠整文件 scope 交付最终 candidate，不能因 integration/dev 是合法环境 consumer 就把它当 lane acceptance producer。lane 不推远端；唯一 `integration/` 工作区更新远端 `dev1.0` 必须消费验真的 acceptance bundle 与 publish admission，只允许 non-force fast-forward。`QWQ_ACCEPTANCE_PUBLISH=1` 等布尔环境变量不构成 admission 或授权，无 bundle 的裸 `git push` 零写。
- `dev1.0` 是唯一集成 ref，接受 `trusted_integration_publisher_cas`、`integration_worktree_fast_forward` 与 `system_fast_forward_backsync` 三条通道；后两条都必须绑定已验收 admission 或受管 system actor，裸源码直推不是 writer。`main` 是最新 source-admitted 源码，只接受 `dev1.0 -> main` promotion PR，不是 Prod source selector。
- 每个 candidate 必须绑定 expected `origin/dev1.0` parent、exact commit/tree、scope、changed paths、owner、ImpactPlan、source facts 与私有 index identity；scope 外 tree 逐字继承 parent。parent 或 scope generation 漂移使 candidate 和全部环境事实失效。
- 同一 worktree 可有多个不重叠文件 writer；同文件、父子路径、rename/delete、生成物、Git index/HEAD/ref、环境、设备、package 与外部 mutation 竞争只能有一个 winner。未知 dirty、无 owner 或越界字节不得被隐式纳入 candidate。

<a id="req-002"></a>
### REQ-002 集成、promotion 与回同步准入

- trusted publisher 只在 source facts 与 typed Alpha/Beta `EnvironmentAcceptanceFact` 均绑定同一 candidate、签名和 cleanup 闭合时，以 expected remote OID 执行一次非 force fast-forward CAS 并 exact readback。写入 `origin/dev1.0` 是 source-admitted：Alpha 可为 `passed`，或 `not_required` 且 `reasonCode=ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV`；Beta 仍可为 `passed` 或政策 `not_required`。该写入不证明 Alpha live、Data 激活、Gamma、UAT 或生产资格。唯一 integration 工作区写入 `origin/dev1.0` 必须先持有同一 candidate 的 publish admission；最终 publisher 独立重算 admission 自摘要并验证 exact 前驱引用、签名/有效期、candidate commit/tree 与 before/after、规范 integration 路径、本地 `refs/heads/dev1.0` 来源和目标 remote/ref，不能只依赖 bundle 导入或 pre-push。`make integrate … PUBLISH=1` 只表达发布意图，`QWQ_ACCEPTANCE_PUBLISH=1` 不替代上述验证。pre-push 使用 update line 的 before/after OID 调用 Git ancestry authority，publisher 自身也必须证明 non-force fast-forward；expected-old 约束不能替代 ancestry。相等可幂等通过；缺失/伪造/过期/漂移 admission、仅 env=1、缺 OID、authority 不可用、非快进、force、删除、来源不匹配、lane 同名推送、lane→dev、任意 `main` direct push、未知 remote/ref 或 unknown result 盲重试全部拒绝，远端 OID 不变。
- CAS loser必须从新parent重建candidate与环境事实；网络结果按remote=`before|after|other`回读收口，不得stash、reset、自动merge或吸收其他writer字节。
- `dev1.0 -> main` 是唯一 promotion PR 边，只接受 current dev head 的 `IntegrationQualificationFact`。promotion 成功后，`main -> dev1.0` 的回同步只能由受管 system backsync 消费已验真的 `MainSourceSeal`，以专用身份和 expected-before 执行无 force 的 fast-forward 并读回 `after`；不得由 integration 的普通 acceptance 通道、裸 `make promotion-backsync` push 或 env=1 代替。equal 幂等成功，分叉或漂移零写阻断，不得 reset、stash 或自动 merge。其 caller、凭据隔离与真实执行证据未闭合时保持 OPEN-004，不宣称 main→dev 闭环完成；确认 dev 发布读回后再同步 integration 与本地 lane。
- integration worktree 的 admission publish 仅消费已验收事实并把源码提交到 `origin/dev1.0`；`integrationEligibility` 只能由同一 exact admission 建立，不由 push 成功推导，publish 不重新签发 Alpha/Beta/Gamma、`IntegrationQualificationFact`、promotion、release 或 Prod authority。需要 main promotion/发布时仍必须走 exact candidate + Alpha/Beta、current dev head Gamma 与既有后续资格链。main合入结果也仅为`source-admitted`；Prod source admission必须从不可移动正式SemVer标签的AdmissionFact解析可达main的peeled commit和exact OCI digests；dev-only、RC-only、main HEAD、裸SHA或缺唯一promotion绑定均不得进入Prod。生产金丝雀仍在 `main` + stable tag 之后的现行正式链上，内部用户与其他用户一视同仁，本 Story 不新增生产前驱。
- 写入 `origin/dev1.0` 的唯一带资格通道是「lane 验收 → integration 发布」两段式，与 publisher 通道共用同一事实形态。lane 工作树（当前分支为该 lane，head 即 exact candidate；scope 为相对**上次已发布** `origin/dev1.0` head 的全部 changed paths，claim 仍走同一 append-only generation）以 `make accept` 在远端 ref 尚未移动前完成：ImpactPlan 派生集成深度、本地 readiness source fact、默认签发 typed Alpha/Beta `EnvironmentAcceptanceFact`（Alpha=`ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV`，Beta=`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`；仅 `ALPHA=1`/`BETA=1` 才真跑 live），`04. Lane Gate` 的静态治理、ImpactPlan/changed boundary、canonical full Code Health Delta 与 ops 合同检查集合左移到 accept，在同一 exact candidate 上去重执行；required 源码缺项或失败不得 accepted。Data attestation、设备与 24 格 UAT 不是默认 source-admitted 的必填项。本地验真器检查 current exact 证据与 admission，不重跑完整套件；dev 旧 `04. Lane Gate` required check 按授权撤除，专用 publisher/broker 与 hosted 资格强制缺口保持 OPEN-004 `track`，不阻塞本地合入或已可达 dev 的远端 lane 删除，终态 `accepted` 并把 candidate/claim/source fact/两份 EAF 及其全部 case/named 证据按 store 相对路径打成 portable acceptance bundle（`bundle.json` 记录 candidate 身份、expectedParent、lane 来源、每文件 exact digest 与 `bundleId`）。integration 工作区（分支 `dev1.0`）以 `make integrate ACCEPTANCE_BUNDLE=<dir>` 只做消费：在移动本地 HEAD 前先校验 bundle、candidate 与当前远端 parent，验证通过才允许本地 FF 到 candidate；逐字节按 manifest digest 导入本工作树 store（create-once，已存在且字节不同即 `INTEGRATION_RUN.BUNDLE_DRIFT`）、以仓内 keyring 验签并复核 EAF 全部引用与 candidate 绑定、要求 `commit/tree == HEAD` 且 `expectedParent == 当前远端 dev1.0`（否则 `BUNDLE_CANDIDATE_MISMATCH` / `BUNDLE_STALE`，后者须在合入新 `dev1.0` 的 head 上重新 `make accept`），然后形成 publish admission，以 expected-old lease 的 non-force fast-forward push 更新远端并按 `before|after|other` 精确读回，只有读回 `after` 才写入 publish result。integration 不启动任何环境、不接受 Data release 输入；缺 bundle 即 `INTEGRATION_RUN.ACCEPTANCE_REQUIRED`，无 bundle 不得以任何方式移动 `origin/dev1.0`。该 publish result 与 publisher CAS 的结果同 schema，可作为 current dev head Gamma 与 `IntegrationQualificationFact` 的前驱；缺 admission 的裸直推、读回 `before`（零写）或 `other`（他方先行）都不产生任何事实。`lane/* -> dev1.0` 不再是合法 PR 写入边；唯一 promotion 边是 `dev1.0 -> main`。
- 本地 Alpha App 验收只在显式 live Alpha（`ALPHA=1`/`--alpha`）时执行。缺省源码合入不要求 Android/iOS 设备，也不把未跑的 24 格记为通过。live 时调用方可显式选择仅 iOS 或仅 Android，未选平台不执行、不阻塞本次 dev 集成，也不得被记为通过。所选平台仍须完成完整必需页面矩阵、启动及制品身份验真；服务/API、Data 与 cleanup 等独立必需证据不因单平台选择省略。平台计划必须随 acceptance 的签名覆盖输入、bundle 与复用身份固定，消费者按该声明验真而不是从收到的 receipt 推断要求；单平台事实不得满足双平台要求或被提升为正式生产分发资格。
- Alpha/Beta 的签发位置是产出最终源码 candidate 的 lane 工作树（`--mode acceptance`，不 admit、不写 `dev1.0`、拒绝 `--publish`）。默认 source-admitted 不消费 Data release handoff；live Alpha/Beta 才要求合法消费 Data release handoff（不要求等于内容 producer 工作树）。integration 工作区独占 admit/publish 及其后的集成验证——集成验证只有两级：`gamma-local` 对 current exact 已发布 `dev1.0` head 的 Gamma（沿用现有 integration/release 剖面，不升级 nightly/全设备），以及 main + stable tag 之后现行正式链上的 prod canary。Gamma / UAT / Data 激活不得反向挡住本次 source-admitted 写入。用户可显式把多个 lane head 合并为一个 candidate 后一次验收，`--merged-lanes lane/<name>` 逐一记录来源且每个都必须是 candidate 的祖先，bundle 的 `mergedLanes` 随之进入 integration summary。可发布 candidate 的 parent 固定当前远端 head；candidate 已等于该 head 时，显式历史 `--baseline` 只作诊断（否则 `INTEGRATION_RUN.NOTHING_TO_ACCEPT`），仅祖先关系不证明成功验收/发布基线，不得重绑旧事实作为发布前驱；不得为在 `dev1.0` 分支上跑通 ship admission 而放宽 `validate_current` 或复制他方 lane 的证据字节（见 [L2 DEC-014](../design.md#dec-014)）。
- 集成深度仍唯一由 `quwoquan_ops/ci/impact_planner_core.py` 的 `derive_integration_depth` 派生（`data|topology` → `abg_release_sensitive`；`app|service|portal` → `alpha_integration`；五 scope 全空 → `no_live`，不启动环境），但不再决定 Alpha/Beta 是否真跑或政策跳过的原因码：默认无论集成深度为何都签 typed `not_required`（Alpha=`ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV`，Beta=`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`）；仅显式 `--alpha`/`--beta` 才真跑。事实合同保留 `IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED` 表达 ImpactPlan 本身的免环境结论，但不得代替本通道未 opt-in 的政策原因；签发（`environment_scheduler`）、schema（`environment_acceptance_fact.schema.json`）与 admission（`create_publish_admission`）消费同一原因码闭集，其余原因码 fail closed。Gamma 不得用 `not_required` 冒充环境通过，也不得借用 Alpha 延后原因码。`integrationEligibility` 是本地 readiness 正交维度（producer=`trusted_integration_publisher`，状态 `not_evaluated|eligible|blocked`），只在 exact candidate 的 publish admission 绑定 passed source fact 与 typed Alpha/Beta 事实之后由 publisher/integration FF 通道写成 `eligible`；裸直推、L0/L1/L2 source readiness 与 Environment Ops 的 `environmentReadiness` 都不得推导该维度。该 `eligible` 只证明 source-admitted，不证明 Alpha live / Gamma / 生产资格。
- Alpha/Beta/Gamma `EnvironmentAcceptanceFact` 与 `IntegrationQualificationFact` 的签名只接受 Ed25519（`ed25519:<base64>`），signer identity 与其 active 公钥的唯一真相源是仓内 `quwoquan_ops/policies/evidence_signing_keyring.yaml`；私钥只在本地仓外由 `make evidence-signing-bootstrap` 生成，hosted Delivery Gate 只用 PR head exact bytes 中的 keyring 验签、不持有任何 secret。两个 identity 的 active 公钥不得相同；retired key 不参与验签（见 [L2 DEC-010](../design.md#dec-010)）。
- lane 与 `dev1.0` 的同步只由 Workflow Skill 显式执行，不由 hook 或 commit 隐式触发。`sync-lane-from-dev` fetch 后冻结已发布 `origin/dev1.0` exact SHA，常规只把该 SHA 以 `--ff-only` 同步进当前 lane；不得回落到本地未发布 `dev1.0`。分叉时须获显式授权，由当前 lane 合并同一已发布 SHA、仅在自身工作树解决冲突并重新验收。重叠脏文件或进行中 merge/rebase 零写阻断，禁止 reset/stash/clean。`integrate-lane-to-dev` 只在唯一 integration 工作区先验真 bundle 与远端 parent，再本地 FF、admit/publish；远端读回 `after` 即完成本次 source-admitted 写入。回同步不是 publish 成功条件：`skipped_*` 退出 0，仅 `ff_failed` 失败；各 lane 在自己提交前按 `sync-lane-from-dev` 对齐已发布 SHA。回同步执行与渲染共用该 SHA，只对「无进行中 merge/rebase、工作树干净或脏文件与本次 ff 不重叠、且是该 SHA 祖先」的 lane 本地 `--ff-only`，**不推**远端 `lane/*`；不提供先移动本地 ref 后报 push 失败的废弃 push 接口。分叉或重叠脏树只产出 `skipped_diverged` / `skipped_dirty_overlap`，由该 lane 自己的会话处理，任何通道都不得在他人工作树里自动 merge、覆盖或清理字节。
- 同一 exact candidate 的 readiness receipt 与 Alpha/Beta `EnvironmentAcceptanceFact` 可被 lane 的后续 `make accept REUSE=1` 复用：复用只按 candidate commit/tree、ImpactPlan digest 与 receipt fingerprint 精确匹配，命中即跳过重跑并在 summary 标记 `reused`；任一输入漂移都必须重跑，不得按时间窗、分支名或「最近一次」复用。因 OPEN-006 类外部阻断未能签发 live Alpha 时，默认通道仍可签发 typed deferred Alpha 并产出 bundle；**不得**因此放宽裸推或在无 bundle 时移动 `origin/dev1.0`。OPEN-006 只挡 L3 环境/内容激活，不挡本次 source-admitted publish。

<a id="req-003"></a>
### REQ-003 最终组合候选、完整输入重验与消费边界

- 单 lane 已验候选由 integration 原样 FF，只有 commit/tree/expected parent、scope/owner、内容及投影、config、测试/工具链、恢复基线、签名有效期均匹配时复用原 Alpha/Beta，不重新运行环境。多 lane 批量交付先显式授权一条现有汇总 lane，冻结参与本地 identity 的 exact SHA 并合并成最终 C，再执行 C 的 Alpha；来源均须为 C 祖先，冻结后 lane 前移不改变本批次来源，不读 `refs/remotes/<remote>/lane/*` fallback，不新增工作树或改变 scope owner。
- A/B 的旧 bundle 不能合成 C 的通过结论；merge、冲突解决、rebase、squash、新修复或 parent/commit 改变，即使 tree 相同仍重验 Alpha。CAS loser 收到 `BUNDLE_STALE` 后须同步新 published parent、形成新候选并重验，不能改旧 bundle parent。integration 发现冲突回汇总 lane，不在发布时 merge/修改/重建源码；未参与的 lane 不因本批组合而重测。
- Beta 在包含 Data milestone 的整条链均显式 opt-in：未选时只以绑定同 candidate/release 的既有政策 `not_required` 与 Alpha/内容前驱进入 Gamma，Gamma 自身完整内容、UAT、恢复/cleanup 检查不省略；不得冒充 Beta passed。选中失败阻断本次 accepted，不能自动降为未选；opt-out 是留存历史的新显式请求。由未选改选 Beta 时，只在完整 exact runtime 前驱仍可恢复时复用 Alpha 并补跑 Beta，否则重新验收，不把复用不可用当成功。
- 默认可发布 source 检查、full required 与 admission 前纯预检遵循 [`local-continuous-integration` REQ-005](../../development-workflow-governance/local-continuous-integration/spec.md#req-005)；`no_live` 不产生 accepted/bundle。任何完整输入漂移拒绝旧事实，旧签名事实字节保持不变；自动 reuse 与显式 candidate 对 caller owner/claim 漂移作相同拒绝。
- producer source provenance 与当前 consumer candidate/environment 身份独立验真；沿用 Data sealed reader 与 Ops handoff 原入口，不将 producer baseline/当前源码 HEAD 相等作为跨工作树内容消费前提，也不关闭 currentness。Data 独占来源原件、审核成品与版本化渲染投影，本 Story 不改来源 schema 或新增映射；所选 release、投影 schema/构建输入、API/Alpha/App 版本与媒体摘要是验收输入，任一变化使受影响事实失效。
- Gamma 启动、签 IQF 与 promotion 前均对账已发布远端 dev exact head，不以本地未发布 dev 为基线。dev 前移后旧运行仅留诊断，不为新 head 签资格；仅重跑新 head 的 Gamma，不重复其已有效的 Alpha/可选 Beta。晋级窗口只串行共享 publish ref/环境/设备，不暂停六工作树编辑；MainSourceSeal 受管 backsync 不伪造 lane Alpha。
- 服务端正式发布与 App 正式分发解耦、单机正式生产与首发恢复由集成/release owner 在现有合同同轨实现；服务闭包完整时不以无关 App 商店物料阻塞，模拟器仅提供真实 AUT 业务证据、不授予 App 分发资格。保留 main/stable、签名、selected Provider、法务、账号/数据隔离、容量、健康、备份恢复与灰度技术门；不要求额外第二主机、不声称 HA。内容首次无恢复基线与服务首次无 `ProdReleasedFact` 分别验真，不以封装 ID 不同证明不同内容恢复，不伪造 previous released；合同与真实证据未闭合前保持对应 OPEN。

- integration 显式提供 `--merged-lanes` 表示本树多工作树合并验收：先验证每个来源head是候选祖先，再真实执行Alpha与Beta，不复用旧环境结果、不受Beta opt-in默认跳过影响；Gamma和生产由后继阶段真实执行。没有显式合并来源时不自动扫描上游；单树未变输入复用仍必须有可验签、未过期且覆盖输入一致的事实，跨candidate适用性由同一事实合同验证，不改写历史candidateId。相关跨候选复用与四环境完整后继仍由OPEN-011承接，不把入口放行当作全部闭环。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- 机器合同：`quwoquan_ops/policies/branch_policy.yaml`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 scoped candidate与受信集成发布

- GIVEN 两个writer基于同一expected dev parent声明候选scope。
- WHEN 它们构造并请求发布candidate。
- THEN 不重叠整文件scope可分别形成只含本scope字节的exact commit；同路径、父子、rename/delete、共享生成物或Git ref竞争只有一个winner。
- AND source及typed Alpha/Beta事实完全匹配的candidate可由trusted publisher CAS写入dev；integration worktree 仅在 publisher 独立验真 publish admission 的自摘要、exact 前驱/签名/有效期、candidate/tree、before/after、规范路径与 remote 后，且 before/after OID 可证明 non-force fast-forward 时写入 `origin/dev1.0`。无 admission 的裸 `git push`、仅设置 `QWQ_ACCEPTANCE_PUBLISH=1`、伪造/过期/漂移 admission 的远端 OID 均不变。push 成功不自行产生集成、晋级、发布或 Prod 资格；parent漂移、未知dirty、越界字节、签名或cleanup缺失仍不得冒充publisher准入。
- AND lane 工作树 `make accept` 以 lane head 为 exact candidate（scope 等于相对 baseline 的全部 changed paths，baseline 非祖先时拒绝），默认无论集成深度为何都签 typed `not_required`（Alpha=`ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV`，Beta=`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`）；仅 `--alpha`/`--beta` 才真跑。终态 `accepted` 产出 acceptance bundle，不 admit、不写 `dev1.0`；用户显式合并多 lane 时 `--merged-lanes` 中每个 lane 都必须是 candidate 祖先。
- AND 显式 iOS-only Alpha 验收不要求 Android 设备、不调用 Android 同步或构建；默认双平台不能消费该单平台事实。改变平台计划、缺所选平台页面、平台声明与 raw 证据不一致均拒绝复用或发布，不能按 receipt 的子集降低原要求；正式生产分发的双平台门保持不变。
- AND integration 工作区 `make integrate ACCEPTANCE_BUNDLE=…` 只导入并复核 bundle：manifest `bundleId` 与每个 store 文件的 exact digest 一致、create-once 导入、EAF 以仓内 keyring 验签且引用/candidate 绑定成立、`commit/tree == HEAD`、`expectedParent == 远端 before`；任一漂移 typed 拒绝（`BUNDLE_DRIFT` / `BUNDLE_CANDIDATE_MISMATCH` / `BUNDLE_STALE`），缺 bundle 为 `ACCEPTANCE_REQUIRED`，acceptance 专用输入出现在 integrate 为 `INPUT_INVALID`；integration 相位只有 preflight → import-bundle → admit（→ publish），不出现任何环境相位。
- AND 携带 passed source fact 与 Alpha/Beta 事实的 admission 经 expected-old lease fast-forward push 后，读回 `after` 才写出 publish result，读回 `before` 为零写 STALE/不可用，读回 `other` 为 CAS 冲突且不得 stash、reset 或自动 merge。
- AND 该 publish result 与 publisher CAS 结果同 schema，可作为 current dev head Gamma 与 `IntegrationQualificationFact` 的前驱；没有 admission 的裸直推、失败的 source fact 或环境事实缺失都不能进入 admission。
- AND 每份 EAF/IQF 的 `signer.signature` 只能由仓内 keyring 中该 identity 的 active Ed25519 公钥验签通过；错误 key、retired key、非 canonical 编码、identity 未登记或两 identity 共用同一公钥均 fail closed，私钥不在仓内、`.qwq_output` 或 hosted secret 中出现。

<a id="gwt-002"></a>
### GWT-002 五分钟promotion与system backsync

- GIVEN current dev head已有匹配的IntegrationQualificationFact且main base稳定。
- WHEN 创建`dev1.0 -> main` promotion并完成merge。
- THEN 唯一 required context 只验 branch/tree/evidence/approval/ruleset 并生成 MainSourceSeal，随后受管 system actor 消费该 exact seal，以 expected-before 无 force fast-forward 更新 dev；equal 幂等，分叉或漂移零写阻断。读回 dev 的 `after` 后，integration 与本地 lane 才能同步同一已发布 SHA。
- AND 唯一 promotion required check 由 `required_promotion_checks` 声明并展开为 main ruleset 期望值。`04. Lane Gate`（`required_integration_checks`）的检查集合左移到 lane `make accept`，不再依赖 `lane/* -> dev1.0` PR；本地 accept/bundle/integrate/hook 拒绝缺项或失败，完整套件不重复执行。dev 旧 `04. Lane Gate` required check 可按授权撤除，已可达 dev 的远端 lane 可在保全增量后删除，无需等待 hosted 替代门。hosted 资格强制缺口保持 OPEN-004 `track`，普通授权凭据仍可 FF dev，不能声称服务端保证 Alpha；dev 禁删/禁 non-FF 与 main promotion 强制须独立权威读回。reusable `system-backsync.yml` 只引用 GitHub Actions 合法上下文，其 `QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF` 由 `github.repository`/`github.ref` 拼装；caller 与真实回执缺口见 OPEN-004，静态门禁拒绝任何非 `container|services|status` 的 `job.*` 属性，actionlint 拦截解析期即失效的其余上下文/属性/类型错误。

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
- THEN 资格工厂按 release owner 冻结的发布 scope 绑定 package acceptance、provider、UAT 与 supply-chain 事实；服务闭包完整时不以无关 App 商店物料/Android keystore 阻塞服务发布，App 分发仍须自身平台签名与真机/渠道资格。scope 合同未同轨完成前保持 OPEN-005，不能自行跳过旧校验；缺范围内任一 required 事实不得签发 `QualificationFact` 或 stable tag。
- AND 晋级 ratchet 与 hosted CI 超时/缓存/soak 占用不得用假样本或放宽例外收紧；未达 `quwoquan_ops/policies/promotion_timing_ratchet.yaml` 声明的窗口与最低 eligible 次数前保持现行阈值。

<a id="gwt-005"></a>
### GWT-005 lane 回同步三态零写与 candidate 事实复用

- GIVEN `origin/dev1.0` 的已发布头已精确读回并冻结，六条 lane 分别处于「干净且为祖先」「脏文件与 ff 不重叠且为祖先」「脏文件与 ff 重叠」「已分叉」四种状态，本地 `dev1.0` 还可能含未发布提交。
- WHEN 在 integration 工作区执行回同步。
- THEN 前两种 lane 被本地 `--ff-only` 推进到同一已发布 exact SHA，绝不传播本地未发布 `dev1.0`，**不推**远端 `lane/*`；后两种 lane 的 HEAD、index 与工作树字节零变化，分别为 `skipped_dirty_overlap` 与 `skipped_diverged`；进行中 merge/rebase 也零写阻断。渲染模式只输出绑定同一 SHA 的命令，不移动任何 ref；废弃 `--push` 输入在任何本地 ref 写入前拒绝，不出现先 ff 后 `push_failed`。
- AND 同一 exact candidate 在 lane 的第二次 `make accept REUSE=1` 复用 readiness receipt 与已签发 Alpha 事实并标记 `reused`；candidate commit、ImpactPlan digest 或 fingerprint 任一漂移都重跑，不复用。
- AND `make accept` 默认 parent 是 `git ls-remote origin refs/heads/dev1.0` 的上次已发布 head；一次成功 publish 读回 `after` 后，下一次 readiness delta 排除已发布变化，integrate 不重跑 readiness。尚未发布的差异增长时 readiness 输入可以增长，不承诺常量范围或常量耗时；同 parent 的另一候选在他方发布后 stale，必须同步新 parent 并重新验收。

<a id="gwt-006"></a>
### GWT-006 最终组合重验、政策 Beta 与远端漂移

- GIVEN A/B 基于同一已发布 parent，用户选定现有汇总 lane 并冻结参与本地 SHA。
- WHEN 真实 Git 合并生成 C，再执行 C 的 accept 并由 integration 原样 FF。
- THEN A/B bundle 均不能代表 C；C Alpha 执行一次，未选 Beta 执行零次且只产生匹配政策事实，选中则真跑一次、失败不 accepted；integration 环境调用零次。冻结后来源 lane 前移不改变本批 SHA，远端 lane fallback 不可达。
- AND merge/rebase/squash 即使 tree 相同仍使旧 Alpha 不可复用；同候选完整输入匹配可复用，内容/投影/config/测试/工具链/恢复基线或有效期漂移拒绝旧事实，旧字节不变。Beta 从未选改选不把旧 not_required 当 passed，完整 runtime 前驱不可恢复时明确重验。
- AND 两个不同 candidate/admission 竞争同 parent 的真实 CAS 只有一个成功，另一方 stale/parent 漂移拒绝且远端不被覆盖；重验只针对同步后的新候选。Gamma 期间 dev 前移使旧 IQF 不可签发或用于新 head；新 head 有效 Alpha/Beta 不重复。

<a id="gwt-007"></a>
### GWT-007 内容 provenance 与当前消费身份独立成立

- GIVEN Data sealed 内容及其 exact Ops authority 与当前源码 candidate，二者可来自不同合法工作树。
- WHEN 汇总 lane 验收或 integration/dev 进行 Gamma 环境消费。
- THEN 分别校验 producer immutable provenance 与 current consumer owner/claim/candidate/config；同 SHA 他方 owner、直接 producer JSON、歧义 artifact、摘要/currentness 漂移均拒绝，不关闭 validate_current 或复制输出装身份。dev consumer 不能成为新增源码的 lane acceptance producer。
- AND 单 exact handoff 唯一解析同 release attestation；内容 unchanged 不制造新 release，正常更新恢复到真实成功的不同内容基线；仅封装 ID/digest 不同而 cohort/对象相同不证明恢复版本不同，首次无基线须独立权威证明与合法恢复输入。
- AND milestone 未选 Beta 的同 release Alpha→Gamma 有真实政策跳过与内容前驱并执行 Gamma 全部检查，不伪造 Beta passed；新 source/投影输入进入当前验收，Data 来源 schema 不在工程侧复制。服务 scope、App 分发与单机首发各由原 owner 以自身技术证据验收，不从本 GWT 源码通过推导下游完成。

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
- 影响或价值：仓内 decision-table 已覆盖拒绝 lane 同名远端推送、无 admission 的 integration 裸 push 零写，以及可证明 system fast-forward backsync；尚缺真实 scoped candidate、trusted publisher CAS、`dev1.0 -> main` PR/check、promotion 后 system CAS backsync，以及 hosted 两条远端分支权威清单与干净 clone 复现回执。Hosted 仍需证明 non-fast-forward、delete/force 与 `main` direct push 保护；存量 `origin/lane/*` 的删除属另授权 hosted 操作。`promotion_verify` 对 `integration_qualification.py` 的接线已收口：signer identity 的 canonical 真相源是 `quwoquan_ops/policies/evidence_signing_keyring.yaml`（Ed25519 公钥，见 [L2 DEC-010](../design.md#dec-010)），workflow 以 `--signing-keyring` 与四个 `--expected-*-signer-identity` 逐一传入，不再需要 verification key env 或 repository secret；`verify_workflow_cli_arguments.py` 已能静态展开该脚本常量循环内的 required 并对该调用判绿；workflow 里的 `QUALIFICATION_SIGNER_IDENTITY` / `ENVIRONMENT_SIGNER_IDENTITY` 字面常量由 `test_delivery_gate_signer_identity` 锁定为 keyring 已登记且 purpose 匹配的 identity 并逐一透传；`deploy-prod-auto.yml` / `release-qualification.yml` 的 `${{ github.run_started_at }}` 已改为 shell 侧 `date -u`。仍缺：真实 `dev1.0 -> main` PR/check 回执与 hosted readback 证据。
- 完成判定：`GWT-001.t1..t2` 与 `GWT-002.t1..t2` 具备 decision-table local contract；`integration_qualification.py` 的合同测试覆盖 workflow 调用形态（keyring 验签）；当前最终 SHA 的 hosted readback 证明 promotion PR/check、system actor、远端两条 refs 闭集以及 dev non-FF/force/delete 与 main direct-push 保护，真实 system backsync 证明 CAS 与 ref before/after。

<a id="open-002"></a>
### OPEN-002 private-free GitHub 托管分支保护

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 阻断边界：未证明 dev 禁删/禁 non-FF、main promotion 强制与正式 source/tag authority 时，仍阻断对应 `formalProd` 准出和“GitHub 原生保护已闭合”声明；专用 publisher/broker 尚未实现的 dev 资格强制仅归 OPEN-004 `track`，不额外阻断有效本地验收后的 dev 日常合入，也不替代任何真实生产技术前驱。
- 影响或价值：仓内 hook/Actions 不能冒充服务端保护。当前 source admission 必须逐次从 Hosted API 证明 exact merge SHA、最终 `dev1.0` head、绑定该 head 的 approval、canonical required workflow run/attempt/check identity、当前 main reachability、repository default branch 与当前 workflow attempt；历史 bootstrap create、普通 lane push与integration worktree direct fast-forward push都缺唯一promotion binding且不具备release eligibility。Hosted ruleset仍须证明`dev1.0` non-fast-forward、force/delete与`main` direct push被阻断；合法matching integration fast-forward不再被定义为绕过publisher或非法更新。托管ruleset的适用条件、bypass actor与required check readback未精确闭合前，不能签发正式Prod。
- 完成判定：`GWT-002.t1..t2` 与 `GWT-003.t1..t2` 的 GitHub refs、适用 ruleset/branch protection 与 system actor 权限均由托管 API readback 证明；在此之前 `hostedProtectionVerified=false / formalProd=false` 保持不变。

<a id="open-003"></a>
### OPEN-003 六 lane activation、canary 与 direct-push 收敛

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：六条固定 lane 工作树与本地 identity 已开放；远端 `lane/*` 已退役为 leftover，回同步只 ff 本地、不推远端。尚缺 hosted 删除存量 `origin/lane/*` 的 readback、六条 lane canary 与 integration/abort 终态证据；该观察证据不改变 main direct push、non-fast-forward、force/delete 禁令，也不把 admission publish 升级为任何资格事实。
- 完成判定：`GWT-001.t3`、`GWT-001.t4`、`GWT-005.t1` 持续由 local contract 绑定；hosted readback 证明远端闭集仅 `dev1.0`/`main`，六条 lane 工作树 retained 且本地 fast-forward 到新的 `origin/dev1.0`。
- 依赖：[`objective-execution` OPEN-002](../../development-workflow-governance/objective-execution/spec.md#open-002) 的六并发证据、[`local-worktree-lifecycle-governance`](../../system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md) 的 worktree 授权提醒、Delivery Gate exact candidate evidence。

<a id="open-004"></a>
### OPEN-004 hosted 资格强制与受管 system backsync 执行证据缺口

- 类型：`external_blocker`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺隔离的专用 publisher/broker、hosted exact evidence 准入的外部执行面与负向拒绝回执；普通已授权写凭据仍可直接 FF dev，服务端不能证明 Alpha 必经。本地 accept/bundle/integrate/hook 仍强制完整验收和 admission，dev 旧 `04. Lane Gate` required check 按授权撤除，已可达已发布 dev 且增量已保全的远端 lane 可删除；这两类动作与日常有效本地合入均不等待 hosted 替代门。本项为显式接受的 `track` 风险，不把本地 PASS 或历史 strict-check receipt 冒充服务端资格强制。受管 system backsync 的专用身份、合法 caller 与真实 MainSourceSeal→dev 回执另须取证，缺失时只阻断该回同步动作/闭环声明，不连带阻断 dev 日常合入。
- 完成判定：`GWT-001.t2` 有隔离 publisher/broker 的真实 hosted 准入与缺失/失败/伪造/漂移证据拒绝回执，证明普通写凭据不能绕过资格强制后才可关闭该风险；同一 candidate 完整套件仍只在 accept 执行一次。`GWT-002.t2` 另证明 system backsync 消费验真 MainSourceSeal、expected-before FF 与 before/after 读回；所有受管身份都不得绕过 dev `non_fast_forward`/`deletion` 或 main promotion 保护。生产仍保留 main/stable、签名物料、health、Provider 与回滚技术门，administrative 简化不能关闭这些未实测项。
- 依赖：hosted broker 凭据与 URL、dedicated deploy key、`system-backsync` Environment、ruleset bypass actor 只登记该 deploy key。

<a id="open-005"></a>
### OPEN-005 CI 效率、晋级 ratchet 与 RC factory 四类事实缺口

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`06. RC Qualification Factory` 尚缺按发布 scope 绑定的 package acceptance、provider、UAT、supply-chain 真实事实与 service/App 解耦接线；Android keystore 缺口只归需要它的 App 分发范围。由集成/release owner 完成既有 request/material/qualification/stable/activation 合同同轨调整，服务 RC 先封存构建再验收，不形成构建前要求该构建验收事实的循环；未接线前不能自行跳过旧门或签发 `QualificationFact`/stable tag。单机正式生产与首发恢复另由原 owner 证明，不从 scope 调整推导生产通过。`deploy-prod-auto.yml` 的 job timeout 小于内部 deadline；soak 占用自托管 runner；ARM 上 QEMU 编 amd64；`validate-deploy` 重复 verify；`app_pipeline` 五个 macOS job 无缓存且 nonprod 产物不进 CMM；多次 Environment 审批串行。`promotion_timing_ratchet.yaml` 的窗口与最低 eligible 次数尚未满足，不得收紧阈值。
- 完成判定：`GWT-004.t1` 的范围内四类事实各有真实生产者与 hosted 回执，service-only 无 App 商店物料可合法通过，未知 scope/缺服务物料/模拟器冒充分发资格均拒绝，App 分发所需 keystore 另有真实证明；`GWT-004.t2` 的 ratchet 达到 `promotion_timing_ratchet.yaml` 声明的窗口与最低 eligible 次数后单调收紧一次，且 CI 超时/缓存/soak 占用不再用假样本或放宽例外。
- 依赖：[`OPEN-004`](#open-004)、GHCR `write:packages`。

<a id="open-006"></a>
### OPEN-006 exact 内容交接、恢复基线解析与真实 Alpha 验收未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 阻断边界：缺有效内容输入、恢复基线或 live 验收结果时，只阻断 live Alpha/Beta 签发与 L3 环境/内容激活（Gamma / Data apply / UAT / prod-sim / IQF / `dev1.0 → main`）；不阻断默认 source-admitted 的 typed Alpha/Beta bundle 与本地 publish admission。不据此否定独立 source、构建或 runtime health 结果，也不以它们代替 UAT/部署完成。
- 影响或价值：Data producer handoff 已有 sealed 内容验真，但不是 Ops `handoff-ref-v1` authority；`release_runtime` 仍先验该 authority 且 `validate_current=True`，accept 仍分别要求 candidate/rollback attestation。尚缺 [DEC-014](../design.md#dec-014) 的单 exact handoff→同 release attestation 解析、从已验证成功发布/activation 记录冻结 rollback、producer source 与 consumer environment identity 分别验真的正式接线，以及真实 Alpha/UAT/恢复报告。不能把 producer finalize 当自动环境交接，不能关闭 current 校验或复制别的工作树输出来装身份；若跨工作树合同不兼容，由原 owner 在同一验真入口正式修正后再消费。
- 完成判定：`GWT-001.t6..t7` 的 consumer 只需一个 exact Ops handoff，能唯一解析完整 source/media/review/record 对应的内容 release 与同 release attestation；正常内容更新恢复到 distinct 的已成功基线，首次权威证明无基线时才要求显式合法恢复输入。源码热修且内容未变时引用当前已发布 immutable 内容，解释为 `unchanged/no_data_change` 而不是新 release 或内容回滚完成，不强制造两份不同 Data release；不得扫描 latest 或将待验 candidate 当伪 rollback。直接 producer JSON、摘要/签名/currentness 漂移、恢复记录损坏、healthy 但 UAT 失败及 cleanup 失败均有拒绝证据，合法输入有真实 Alpha（Beta 仅 `BETA=1`）与既有 accepted bundle；`GWT-001.t9..t12` 再独立证明 integration publish/readback。新增设计未实现前保持本 OPEN，不自动产生语义 review/cohort，不放宽发布 scope 内的生产技术门。Beta 全链可选前驱、合法跨工作树消费、最终组合与 source/投影绑定仍须按 GWT-006/GWT-007 取得 current 合同及真实报告；设计冻结不关闭本 OPEN。
- 依赖：Data producer handoff/release attestation owner、Ops handoff authority/current consumer owner、目标环境成功 activation/发布记录与原恢复入口；仅首次无基线的合法 empty-baseline 输入仍由现有 owner 提供，不新增总控或 receipt。

<a id="open-008"></a>
### OPEN-008 lane acceptance bundle → integration admit/publish 尚缺一次真实 hosted 发布回执

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：[L2 DEC-014](../design.md#dec-014) 的两段式已有部分源码与历史 local contract 证据，不能据此宣称 current admission 加固、Lane Gate 左移或真实发布已完成：`make accept` 在 lane 工作树终态 `accepted` 并写出 portable acceptance bundle；`make integrate ACCEPTANCE_BUNDLE=…` 只导入 bundle（create-once、digest 复核、keyring 验签、`expectedParent == 远端 before`）后 admit → publish，不再自己跑环境，也不再需要 Data release 输入，因此不会在 `dev1.0` 分支上撞到 ship handoff admission 的 `CANDIDATE.OWNER_DRIFT`。local contract 已覆盖 bundle round-trip、digest/manifest/commit/parent 漂移、缺 bundle 与 acceptance 专用输入的 typed 拒绝、integrate 相位闭集。当前新增的默认 scope/pure prevalidate、no_live 非发布终态、真实多 lane 合并/双候选 CAS、Beta 全链可选与远端 Gamma fencing 仍需 current 证据，GWT-006/GWT-007 与 local CI GWT-008 未取证不称完成；尚缺的是一次真实闭环：同一 candidate 在 lane 工作树 `make accept` 产出 bundle，再由 integration 工作区消费并 fast-forward 发布到远端 `dev1.0`、读回 `after`。
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
- 影响或价值：accept 默认 parent 取上次已发布 `origin/dev1.0` head 是既有合同，不能把 parent 选取自身当成效率改进，也不能保证未发布差异增长时输入为常量。尚缺成功 publish 前后的 paths/墙钟对照，以及 [DEC-014](../design.md#dec-014) 的同 exact 构建产品 build-once、既有原始报告/bundle refs 去重消费与三层 summary 展示的实现和验收证据；不以新增 fact/receipt 包装代替执行成本下降。
- 完成判定：`GWT-005.t2` 的 local contract 绑定默认远端 parent 与裸推零写，真实两次 accept 的 baseline/candidate/changed paths/墙钟报告和中间 publish `after` 证明排除已发布变化；构建日志/调用计数证明同 exact 产品只构建一次，平台/架构、环境相关编译输入或签名不同不假复用。源码热修且内容未变不生产伪新 Data release；单候选 summary 只用现有 readiness/sourceFact、environments/reports、publish/readback 展示 source/environment/deploy，保留原始报告与 bundle refs 的 schema/digest/signature/currentness/cleanup 校验，不增同义状态事实。healthy 而 UAT 失败不显示整体成功；未发布差异增长允许成本增长，未取得真实执行证据不关闭本 OPEN。
- 依赖：[`OPEN-006`](#open-006) 解除后的真实 Alpha 签发；`quwoquan_ops/ci/scoped_candidate/` 的 parent 语义。

<a id="open-011"></a>
### OPEN-011 integration 自验收的跨候选复用与四环境后继未闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺单树未变受验输入的Alpha/Beta跨候选适用性合同与真实执行证据，以及多树合并在本树完成Gamma/生产的完整后继。来源分支允许integration只解除入口限制，不能将旧事实改写成新candidate或把equal-remote补验收伪造为历史publish。显式多树合并须真跑Alpha/Beta，全部问题在本树修复；单树缺失或失败事实仍需如实补验。
- 完成判定：`GWT-001` 与 `GWT-005.t2` 分别以本树实际来源、真实签名/时效/输入覆盖和前驱适用性验证，输入漂移拒绝复用，多树显式来源验证后真跑Alpha/Beta，最终current dev Gamma与生产证据闭合；原始事实不改写，发布before/after/readback不伪造。

<a id="open-010"></a>
### OPEN-010 验收调度入口的职责拆分与复杂度收敛

- 类型：`risk`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：双端离线页面与服务/API 独立证据轴接入后，`quwoquan_ops/cli/integration_run.py` 的环境执行、exact 输入复用和 CLI 分派仍集中在同一入口。增量 Code Health 报 `_run_environment`、`_find_reusable_candidate`、`main` 复杂度与超千行 advisory，尚未超过硬阻断阈值；职责拆分必须保留完整失败与资源清理语义，不为降低指标扩大成验收框架重写。
- 完成判定：在原 CLI 入口不变、无第二调度轨道的前提下按现有职责提取上述边界；`GWT-001.t6..t12` 与 `GWT-005.t2` 的 exact candidate、release/rollback/handoff、双端 raw、签名、复用和 cleanup 负向合同保持通过，增量复杂度不再恶化且入口回到文件 advisory 阈值以内。
- 依赖：`quwoquan_ops/cli/integration_run.py`、`quwoquan_ops/cli/lib/integration_app_launch.py` 及现役 acceptance bundle/reuse local contract；仅源码健康后续项，不代替 required Alpha 或发布证据。
