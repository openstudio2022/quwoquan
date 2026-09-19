# L3 Story：本地优先持续集成与就绪判定 (`local-continuous-integration`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：本 Story 为横切工程能力，不直接承接用户 Journey。
>
> 设计引用：[L2 DEC-007](../design.md#dec-007)

## 1. 用户价值

作为在共享工作树中持续交付的开发者或 Agent，我希望编辑、空闲、提交范围与推送范围逐级获得绑定精确输入的本地反馈，从而在进入远端流水线前发现可本地判定的问题，并明确知道尚未满足的就绪条件。

## 2. 范围与非目标

### In Scope

- 显式 readiness 命令、持久 advisory 队列、可选择的 focused check，以及保留作未来/显式 producer 的 after-edit 脚本。
- 五个互不推导的事实维度：`sourceReadiness`、`environmentReadiness`、`deviceReadiness`、`integrationEligibility`、`promotionEligibility`；本 Story 只生产 `sourceReadiness`，其内部状态为 `fast_green`、`scope_ready`、`release_ready`。
- 基于 canonical EvidenceFingerprint 的精确输入缓存、回执新鲜度与资源互斥。
- Go、Python、Dart、Portal 与 spec/contract 的本地影响规划和执行。
- 仓库级 workflow lint 配置由本 Story 唯一拥有，作为 canonical workflow 静态检查的受版本控制输入。
- code-health delta 在 L0 快判、L1 完整检查、accept exact candidate 与 scheduled report-only 间的分层调度。

### Out of Scope

- 常驻守护进程、替代远端 Delivery Gate 或自动发布。
- 用本地源码与测试结果冒充环境、设备、UAT 或生产 release 证据。
- 修改父 L2 的规格或设计接线。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分层反馈与 fail-closed 就绪

- L-1 编辑反馈必须短时完成入队，并可同步执行安全的 focused check；异常时不得生成 PASS。
- L0 空闲增量可生成允许带 deferred 的 `fast_green`，但不得升级为 `scope_ready`。
- L1 只有全部范围检查和 compile/build（含 required `code-health-delta`）成功且 `deferred=[]` 时生成 `scope_ready`。
- L2 只有全部 release profile 成功且 `deferred=[]` 时令 `sourceReadiness.status=release_ready`；本地回执必须同时把 `environmentReadiness`、`deviceReadiness`、`integrationEligibility` 与 `promotionEligibility` 明确记为 `not_evaluated`，不得声称其他维度已就绪。
- 五个维度均有独立 producer 与证据身份；任何 `sourceReadiness` PASS 都不得推导、填充或替代另四个事实。旧的顶层单轴 `readiness` 字段不再有 reader 或 writer。

<a id="req-002"></a>
### REQ-002 精确输入身份、缓存和互斥

- 规划、运行、缓存与回执必须复用 canonical EvidenceFingerprint，覆盖 tracked、untracked、deleted、renamed 与 symlink 的实际内容身份。
- source、lockfile、toolchain、command 或 context manifest 任一变化都必须 cache miss；运行期间输入漂移必须使本次结果失效。
- PASS cache 只可按 exact-input 复用；同一资源的执行必须持有本地锁，不能以并发成功覆盖失败或漂移。
- deferred queue 必须持久化且可检查；在真实宿主 producer 与消费 SLO 闭合前，contract 将 `exact-pending` 与 `foreign-pending` 都标为 advisory，二者必须出现在 receipt/inspect 中但不得阻断显式 `scope`/`release`。显式 readiness 的 required checks 与 Review admission 仍 fail-closed。

<a id="req-003"></a>
### REQ-003 Git hook 只做边界检查，回执在准出消费

- 硬门只在准出（lane `make accept` → integration bundle 发布、交接、发布），不再依赖 lane PR。本地 git hooks 不消费 `scope_ready`/`release_ready` 回执，也不自动运行全面测试：pre-commit 只运行 staged boundary（secret/PII、generated/cache 边界，以及 `--local-commit` 当前 HEAD 分支检查），失败时只给出唯一恢复命令；pre-push 只运行 branch policy，拒绝任何远端 lane 创建/更新。匹配 `integration/dev1.0` 只有持有已验真的 exact publish admission、本地/远端均为 `dev1.0`、update line before/after OID 存在且 ancestry 证明 non-force fast-forward 才放行，相等幂等；仅 env=1 不能证明 admission，最终 publisher 仍独立复验。缺 admission/OID、authority 不可用、非快进、force/delete、来源不匹配、lane→dev、`main` direct push 或未知 ref 全部阻断。受信 publisher 与消费 MainSourceSeal 的受管 system backsync 各按 canonical 资格边界执行，不存在 source-only 旁路。
- `--local-commit` 必须只校验当前 HEAD 非 detached、Git authority 可读且分支属于 `allowed_local_branches`，不得枚举或治理其他 local/remote-tracking refs；无参数默认模式继续执行全 ref 治理，`--pre-push` 必须消费 canonical integration update contract。L0 `commit_gate.sh` 的提交前 branch 检查也必须使用 `--local-commit`。
- `sourceReadiness.status=scope_ready|release_ready` 仍由显式 CLI 产出并绑定精确输入 fingerprint，供 Skill 报告与交接消费；integration worktree 的验真 admission publish 不重新生产 readiness 或环境事实，`integrationEligibility` 只能由 exact candidate + Alpha/Beta admission 建立，`promotionEligibility` 只能由 current dev head 的 IntegrationQualificationFact 建立，GitHub Delivery Gate 只验后者的不可变身份。
- L0 的 code-health 快判不得网络安装工具且以 p95 30 秒为目标；L1 执行完整 candidate delta；scheduled 全仓热点只 report-only。指标与阈值唯一引用系统架构能力的 `REQ-008` 与 `DEC-031`，本 Story 不复制。既有 `.github/workflows/lane-gate.yml`（`04. Lane Gate`）的静态治理、ImpactPlan/changed boundary、canonical full `code-health-delta` 与 ops local_contract 检查集合必须左移 lane `make accept`，绑定同一 exact candidate 与 `changed_paths_digest`/`impact_plan_digest`，复用 canonical planner/runner 去重执行，缺项或失败不得 accepted。日常 dev 由本地 accept/bundle/integrate/hook 验真 current exact source/EAF/admission，不重跑完整套件，不依赖远端 lane 或 lane PR。dev 旧 `04. Lane Gate` required check 按授权撤除，已可达 dev 且增量保全的远端 lane 可删除；专用 publisher/broker 和 hosted 资格强制保持 daily-merge OPEN-004 `track`，不阻塞该本地通道，也不是远端拓扑调整的先决条件。普通授权凭据仍可服务端 FF dev，不能保证 Alpha；dev 禁删/禁 non-FF 和 main promotion 强制继续权威读回，required 集合仍只读 canonical policy。
- 影响分类的边界：`classify_impacts` 只把 changed paths 分类成"触及了哪些运行时 scope"的事实，未知根级路径的运行时触及为零；把它升到 `R3` 并要求全 scope 是 Delivery 的 fail-closed 决策，只在 `build_delivery_impact_plan` 施加。本地 L-1/L0 复用同一分类做秒级 focused 反馈，不得为陌生根文件扇出全部 scope。
- staged 中某个已修改文件继续改变内容时，即使 `git status` 文本不变，也必须判定旧回执失效。
- push readiness（包括 `level=fast`）的 code-health 必须以 actual push before/after 精确 OID 执行 canonical `full` 报告；不可用 capsule 的 HEAD/index/dev1.0 自比较或 `auto` 代替。staged 仍以 HEAD→index 执行 `fast`。报告与 receipt 必须绑定同一 base/head/tree、完整 changed paths 与执行 mode；非空源码变化不得空扫描，纯非源码变化可以有零生产源码计量，但必须保留真实变化范围。
- 公共 source fact producer 必须读取真实 readiness receipt，核对自身终态、exact candidate base/head/tree/paths、全部 required check 与内嵌 code-health 子报告（含 digest、终态与 full 模式）；调用方传入 `status=passed` 不构成证据。失败回执、伪 passed wrapper、错 candidate、漏范围、缺健康子结果或空源码扫描均拒绝签发 passed fact。
- 已有 ops `local_contract` companion、仅依赖源码字节、无需网络/编译器/设备/环境、fail-closed 且不增长豁免、实测可容纳于现有 L0 预算的晚发现扫描，必须左移到显式 L0，并由同一 check id/命令进入 local readiness；不扩大 Git hook 职责，不把 code-health 快判的 30 秒目标解释成整套 L0 预算。`retired_terms_zero` 在`quwoquan_app/`、`quwoquan_service/`、`quwoquan_data/`、`quwoquan_ops/` 四棵工程树变更时选中，扫描范围与检测语义仍归现有扫描器；fast/scope/release 在编译前消费相同检查，失败不生成 PASS。`gate_repo.sh` 在合法 scope/phase 参数校验后、重型治理/测试和工具链检查前执行一次该扫描，不再放在 `run_app`；该 companion 随 Lane Gate 检查集合在 accept 执行，hosted 只验 exact 结果，不新增第二个 hosted 扫描入口。
- Feature Tree 只表达需求、设计与验收，不授予 mutation 权限，也不冻结实现文件清单或测试 scope。每次 current actual changed paths 增减都必须重算 exact-path claim 冲突与 ImpactPlan；测试与 gate 选择只由 canonical path normalization 后的 actual diff、普通代码影响和契约 dependency closure 派生。无 context 或多 context 均不阻断 mutation。
- Data schema、Data loader/dispatch、Service contract/importer、App contract/generated consumer、Ops typed reader 或统一闭包检查器自身发生变化时，L0 必须选择同一 `contract_closure` 静态检查。触发面只含真实 authority、显式 consumer binding、生成/验证入口及规则自身，任意 Service/App/Ops 文件或整棵 `cli/lib`、`ci`、`gate` 不得因物理归属被纳入。该检查只读源码字节、无网络/编译器/设备/环境依赖，现场派生 authority/consumer 双向边并复用现有 ContractGraph source freshness、App handoff lock 与 generated manifest 判据；不得等到 context 全套、merge、Delivery 或 Alpha 才首判。无生产消费者、无唯一 authority、悬空/循环引用、重复身份、跨树 binding 漂移或 stale generation 任一失败都阻断 `fast_green`；修复只能在同一变更接线或原子退役，不能以候选、deferred 或 OPEN 放行。


<a id="req-004"></a>
### REQ-004 App 可编译、可启动、内容可访问是 `app` scope 的基础准入事实

- 只要 `app` 进入 ImpactPlan scopes，每一级 readiness（含显式 `fast`；可发布 accept 默认 `scope`）都必须真实编译 App：darwin 主机执行 `scope_build:app-compile-ios-simulator`（`flutter build ios --simulator --debug --flavor nonprod --no-pub --no-codesign`），所有主机执行 `scope_build:app-package-smoke`（`flutter build apk --debug --flavor nonprod --no-pub`）。两者都以裸 SDK 直接构建：Debug-nonprod 的 trust 与 alpha 供给由 [`environment-topology-and-packaging` REQ-003](../../runtime-config/environment-topology-and-packaging/spec.md#req-003) 的构建期自供给在构建阶段现场签发，readiness 不注入 handoff、不依赖 PATH facade，也不得为此放宽 trust gate 或新增 skip 条件。`fast` 的超时上限为此抬到 900 秒；Android 构建仍要求 Gradle 依赖可解析（联网或 `app-dependency-sync` 快照），解析失败按 typed blocker 记账，不得静默跳过。
- lane 工作树 `make accept` 的 Alpha App 准入先按显式平台计划执行离线页面轴，默认 Android 与 iOS，也可仅选择其中一端；所选平台须显式指定设备，双端设备必须不同。所有结果绑定同一 exact candidate，经 canonical `stackctl app-content-uat` 以 bundled snapshot/rehearsal 真实启动并完成现役 case catalog 的全部必需用例，不在本层复制用例数量。每份 raw `ReadinessCaseResult` 必须有 exact artifact、device、launch、snapshot、native execution 与 screenshot 闭包，保持 `nonPromotable=true`；日志终态、planned/dry-run 或缺失/漂移闭包均不得替代所选矩阵。未选平台不执行、不阻断，也不记为通过；该选择不降低生产分发要求。服务环境变更前必须校验离线证据轴。
- 所需平台计划随 acceptance 的签名输入及 bundle 固定，package、依赖恢复、capsule、currentness 与 raw 消费保持一致。消费端不能从已有 receipt 集合推断或缩小要求；平台计划变化、单平台事实满足双平台请求、历史事实缺平台声明均拒绝复用。
- 双端计划的离线编排不得因首端失败而短路另一端；每个所选平台保留实际 phase、命令 result 与已有 receipt，缺报告不得覆盖命令 payload 的 `firstBlocker`。所选平台尝试后仍保留首个 typed blocker；另一端成功不使失败的平台计划通过，任一所选端失败都不得签发 Alpha fact 或 acceptance bundle。裸 `flutter run` 启动与页面 UAT 是独立证据，本编排不补造未执行的裸 SDK PASSED。
- Alpha API 轴独立执行：`health` 之后、同一 runtime 仍在线时，`alpha.content-readback` 经 Alpha 网关读取首页 feed（`GET /content/feed?sort=recommend&channelId=recommend`）与视频书（`GET /content/feed?identity=work&type=video`），要求 HTTP 200 且集合非空，并产生独立 `content-readback:home-feed+video-book` raw result。所选平台完整 raw 矩阵与独立 API 证据一起进入 Alpha `EnvironmentAcceptanceFact.caseResultRefs`，互不替代；设备不可用、离线闭包失败或任一 API readback 失败均为 typed blocker，不以服务 health、facade status 或旧 receipt 冒充通过。
- `make accept` / integrate 汇总中的 `wallClockSeconds` 以顶层单次执行的 monotonic 起止差计量，包含退出前的清理；嵌套 phase 只用于诊断，禁止累加其 duration 冒充总耗时或预算。
- smoke/integration 的环境巡检消费 [`config-and-reliability-governance` REQ-002](../../../platform-ops-governance/config-and-reliability-governance/spec.md#req-002) 的完整 runtime scope，不把正式分发材料作为日常准入前提；release profile 与显式 all/release/distribution 的严格判据不变。
- 数据工程 release 进入环境的 handoff 准出必须引用同一 candidate 的 App readback evidence ref；"服务健康"或"release-readiness PASS"都不能单独证明用户可见内容可访问。

<a id="req-005"></a>
### REQ-005 可发布验收默认完整 scope，预检与 admission 同一纯校验

- `make accept` 与 CLI 默认 `scope`，产生与最终 admission 一致的 `local_readiness_scope` source fact；仅 `fast_green`、改写 fact kind、required 缺项/失败、`deferred` 非空或缺有效 Review consolidation 都不得 accepted。完整 Lane Gate 与 canonical full Code Health 在同一 exact candidate 上去重执行，开始 Alpha 前拒绝已可判定的 source/Review 缺口。
- `--validate-bundle-only` 与正式 admission 复用同一纯验真逻辑，除 bundle 摘要、签名与 candidate/parent 外，检查完整 scope receipt、required checks、Review 及 Alpha/Beta 前驱；缺 scope 的 fast-only bundle 在任何本地 HEAD/index/WIP 变化前拒绝。预检不 import、不签 admission、不移动 ref；正式发布仍重新复核，不能由预检成功推导发布成功。
- `no_live` 仅是 ImpactPlan 的免环境诊断结果，不是可发布终态；无 passed Alpha 就不得 `accepted`、bundle 或 integration eligibility。显式 fast/历史 baseline 诊断与完整可发布验收分开报告，不用成功退出掩盖没有发布后继。
- 显式 candidate 与自动 reuse 使用同一 current caller owner/claim 检查；同 SHA 不等于同 owner。生产来源 provenance 与当前 consumer 身份分别验真，不放宽 `validate_current`，不把 dev consumer 加入源码 producer lane 闭集。

## 4. 契约引用

- local readiness contract：`quwoquan_ops/policies/local_readiness_contract.yaml`
- EvidenceFingerprint：`quwoquan_ops/policies/agent_governance_contract.yaml#evidence_fingerprint`
- branch policy：`quwoquan_ops/gate/verify_git_branch_policy.py`
- workflow lint config：`.github/actionlint.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 精确内容变化使回执失效

- GIVEN 当前 staged 范围已有 `scope_ready` 回执。
- WHEN 已标记为 M 的文件内容继续变化而 Git status 文本保持相同。
- THEN 回执校验判定旧回执 stale，任何消费者（Skill 报告、交接、PR 说明）都不得再引用它。
- AND exact-input cache 对 source、lockfile、toolchain、command 与 context manifest 的变化全部 miss。

<a id="gwt-002"></a>
### GWT-002 deferred 与执行失败不能升级就绪

- GIVEN planner 产生本地 focused、compile/build 或 release 工作。
- WHEN 任一 required check 或 Review admission 失败。
- THEN 不生成 `sourceReadiness.status=scope_ready|release_ready` 的 PASS 回执。
- AND queue backlog（包括 exact candidate pending）仅作为 receipt/inspect advisory 可见；显式 worker 失败不生成 PASS，但 backlog 本身不阻断 scope/release。
- AND Portal 范围必须真实执行 `npm test` 与 `npm run build` 后才能范围就绪。
- AND 即使 `sourceReadiness.status=release_ready`，另外四个事实仍为 `not_evaluated`，消费者若把它解释成环境、设备、集成或晋级资格必须失败。

<a id="gwt-003"></a>
### GWT-003 Git hooks 只做边界检查

- GIVEN 开发者在 lane worktree 上暂存改动并提交或推送。
- WHEN pre-commit 或 pre-push 运行。
- THEN pre-commit 只运行 staged boundary（secret/PII、generated/cache 边界，以及 `--local-commit` 当前 HEAD 分支检查），pre-push 只运行既有 `--pre-push` branch policy；远端 lane 创建/更新均拒绝，匹配 integration worktree 且持有验真 admission 的 `dev1.0 -> dev1.0` non-force fast-forward publish 与消费 MainSourceSeal 的受管 system backsync 可通过，而仅 env=1、裸 push、非快进/delete/force、lane→dev 和 main direct push 被拒绝；两者都不读取 readiness 回执，秒级完成。
- AND 合法 current lane 即使存在非法陈旧 local/remote-tracking refs 也通过 `--local-commit`；非法当前分支、detached HEAD 或 Git authority 不可读必须失败；无参数默认模式仍拒绝额外 refs。
- AND 任一边界检查失败都阻断并只返回一个稳定 recovery。hook 不读取 readiness receipt、也不输出 readiness PASS，缺少 `scope_ready`/`release_ready` 不构成 lane 本地提交的阻断理由，但不解除远端 lane 写入禁令或 admission 要求。

<a id="gwt-004"></a>
### GWT-004 hosted 复算只对 exact dev1.0 快进范围发布 typed fact

- GIVEN `dev1.0` 收到一次 push，hosted `code-health-integration` workflow 以事件提供的 exact before/after OID 运行。
- WHEN 驱动对 before..after 复算 canonical code-health delta。
- THEN before 为零 SHA、与 after 相同或不是 after 的祖先时不复算，返回 typed `GATE_BLOCK` 并只发布携带 blocker code 的 typed fact。
- THEN 复算 terminal 为 `GATE_BLOCK` 时 run 失败且 fact terminal 为 `GATE_BLOCK`，不产生任何 PASS fact；terminal 为 `PASS`/`PR_WARN` 时 run 成功且 fact 绑定 exact before/after 与完整 candidate report。
- THEN fact 只是 report-only 事实（`blocksPush=false`），不拦截已发生的 push；是否进入 promotion `required_evidence_refs` 由交付链 owner 单独裁决，本 Story 不据此声称集成准出。

<a id="gwt-005"></a>
### GWT-005 accept 完整执行 Lane Gate，hosted 保证范围如实读回

- GIVEN 本地 lane 的 exact candidate 与上次已发布 `origin/dev1.0` parent，且没有远端 lane 或 lane PR 作为前驱。
- WHEN lane 执行 `make accept`，随后 integration 消费其 bundle 请求发布。
- THEN accept 在同一 exact candidate 上执行 branch/supply-chain/workflow/artifact/脚本治理与 Feature Tree；canonical ImpactPlan 与 `verify_ci_changed_boundary.py` 校验同一 before/after 的完整 changed paths；`verify_code_health_delivery.py` 绑定同一 `changed_paths_digest`/`impact_plan_digest` 执行 full delta；ops local_contract 经 canonical 分片器执行。相同检查 id/command 与 exact 输入去重，不重复完整套件；宿主能力缺口仍保持 OPEN-004，不能以空分片或静默排除伪装完成。
- AND required 检查缺项、失败、`GATE_BLOCK` 或应非空的分片为空时拒绝 accepted/source PASS；本地 integrate/hook 验 current exact 证据闭包、签名/有效期、expected parent 与身份，缺失/失败/伪造/漂移事实拒绝受管发布，但不把它外推为普通授权凭据的服务端 FF 也会被拒绝。GWT-004 push 后 report-only fact 不替代本准入，开发机自报 success 也不能替代服务端保护。
- AND integration 与 promotion check 的名称/职责只读 `branch_policy.yaml` 各自 required 集合，不共享第二真相源；按授权撤除 dev 旧 `04. Lane Gate` required check，可达 dev 且增量已保全的远端 lane 可删除，不等待 hosted 替代门。专用 publisher/broker 未接线保持 daily-merge OPEN-004 `track`，不阻塞日常本地合入，不恢复 lane PR 依赖，也不保证服务端 Alpha 必经。
- AND workflow 对仓内 Python CLI 的每次直接调用都必须覆盖该脚本全部常量 required 选项（含 `for x in <字符串常量元组>` 内 f-string 声明的成组 required，静态展开后比对）；`verify_workflow_cli_arguments.py` 在 L0 只对本次 staged 的 workflow 判定、在 `gate_repo.sh` 全量判定，漏传即 `GATE_BLOCK`。任一 step 在自身 `run`/`env`/`with` 中引用 `steps.<自身 id>.outputs` 由 `verify_github_supply_chain.py` 静态阻断（表达式在 step 开始前求值，恒为空串）。
- AND 仓内 `required_integration_checks` 声明不能自证 hosted 强制：只读 governance 通过 `verify_hosted_integration_ruleset.py` 读回全部 ruleset（列表满一页即阻断，不静默截断）与 repository `default_branch`（读不到即阻断），按 GitHub ref_name 语义判定适用规则：`~ALL`、`~DEFAULT_BRANCH`、GitHub 方言 fnmatch（`File::FNM_PATHNAME`：`*`/`?` 不跨 `/`，`**/` 匹配任意层级，`[...]` 按字面），exclude 优先，拒绝未声明的影子规则。权威 readback 必须证明 dev 旧 `04. Lane Gate` required check 已撤、`deletion`/`non_fast_forward` 仍强制且无 lane PR 限制，并独立证明 main promotion 保护未被削弱。普通授权写凭据可 FF dev 的剩余能力须如实报告为不能保证 Alpha；专用 broker/hosted 资格强制归 OPEN-track，不作为上述迁移或有效本地合入的前置。仍 required 的保护不可证即 `GATE_BLOCK`，detail 唯一指向失败形状并带 observed 值。GitHub 只向具有 ruleset write 权限的调用者返回 `bypass_actors`：缺席/null 必须显式不可见，不能折成 `[]`；可见的未声明 actor 必须拒绝。只读 receipt 的 `ruleset.bypassActorsObservable` 如实标记并输出 stdout，`requiredIntegrationChecksEnforced` 只证明 required_status_checks 形状、不含 bypass 证明。admin 以 `--require-bypass-observable` 在每次规则变更后及 promotion 前读回（不可见即阻断，recovery 为换相应权限 token），由 `.qwq_output/env/repo/runs/lane-gate/hosted-integration-ruleset-admin.json` 的 current `evidenceDigest` 证明空集合或 canonical 专用 actor 集合；不得据此提升只读 job 权限。`hosted-integration-ruleset-receipt` 继续绑定 branch、required checks、integration fast-forward executor、可见性和 evidence digest，不签发 release authority；历史 receipt 不证明当前保护。

<a id="gwt-006"></a>
### GWT-006 退役标识在本地廉价检查阶段失败

- GIVEN 四棵工程树的变更触发退役标识扫描，检测器与零豁免语义保持不变。
- WHEN 执行显式 L0 或 fast/scope/release local readiness。
- THEN 选择器与 readiness plan 均包含同一 `retired_terms_zero` 检查；扫描器自身变更同时选中 companion，混合路径不重复调度。
- THEN 被扫描运行时源码含退役标识时，真实扫描命令返回非零，L0 保留失败且 readiness 不发 PASS；合法标识、纯注释与既有测试目录排除不误报。
- THEN 根级文档不选择此扫描，spec 变更仍保留 Feature Tree 检查，Git hooks 的 staged/branch boundary 不变。
- THEN `gate_repo.sh` 在合法 scope/phase 校验后、工具链检查与重型测试前恰调用一次扫描，`run_app` 不再重复；扫描失败时后续阶段不执行。


<a id="gwt-009"></a>
### GWT-009 跨树契约漂移在 L0 同一闭包首判

- GIVEN Data schema 与 Data/Service/App/Ops 的现役 producer、reader、dispatch、生成物形成可派生契约图。
- WHEN 任一相关侧单独变更，并执行显式 L0 或 fast/scope/release local readiness。
- THEN current actual changed paths 每次改变都重取 exact-path claim，并以 canonical impact planner 的 path normalization 与 dependency closure 重算；context manifest 只提供非授权验收上下文，不裁剪或扩张测试。
- THEN selector 与 readiness plan 对真实 contract surfaces 恰好包含一次同 id/同命令的 `contract_closure`，对普通 Service/App/Ops 文件不选择；检查在编译、context 全套、环境与合并前执行，失败不产生 source readiness PASS。
- THEN 新增无消费者 schema、删除仍被消费 schema、悬空或越界 `$ref`、重复 `$id`/逻辑身份、任意动态目标、Service/App/Ops binding 漂移及 stale ContractGraph/handoff/generated manifest 各有行为负例并稳定失败；合法 supporting `$ref`、同变更接线与原子退役通过。
- THEN 检查器不写 tracked inventory、不自动删除、不维护第二字段清单；测试/文档引用不能把无生产绑定 schema 判为现役，OPEN/deferred 不能抵消失败。


<a id="gwt-007"></a>
### GWT-007 干净 push capsule 与 source fact 不得空 delta 假绿

- GIVEN actual push parent→candidate 新增超过既有硬上限的手写源码，capsule 的 HEAD/index/工作树均为 candidate 且干净。
- WHEN 执行 push readiness（包括 fast 等级）并消费真实 receipt。
- THEN 现有 canonical full code-health 报告扫描真实范围并阻断，report base/head 与 receipt tree/paths 绑定实际 push；公共 source fact 即使收到 passed wrapper 也拒绝。
- AND 健康源码、合法纯非源码变化与 staged 快判各有真实执行正例；空扫描、错 base/head/tree/paths/mode、缺健康子报告或失败子结果均不可签发 passed source fact。

<a id="gwt-008"></a>
### GWT-008 默认 scope 与纯预检阻断不可发布证据

- GIVEN lane exact candidate 的默认 accept，或携带 fast-only/缺 scope/缺 required/Review/deferred 的 bundle。
- WHEN 执行 readiness、validate-only 与最终 admission。
- THEN 默认实际执行完整 scope/full required 并产生匹配 `local_readiness_scope`，不得仅改 fact kind；可判定 source/Review 缺口在 Alpha 前拒绝。上述无效 bundle 在本地 HEAD/index/WIP 移动前失败，预检不 import/admit/ref mutation，正式入口仍再次验证。
- AND no_live 或显式 fast 诊断即使源码检查成功，也不得 accepted、bundle 或 eligible；不存在无 Alpha 的发布成功终态。
- AND 显式 candidate 与自动 reuse 对 caller owner/claim 漂移给出一致拒绝；合法不可变 producer 内容与当前 consumer 分开验真，不因同 SHA 接受他方身份，不从 dev 环境消费权推导源码生产权。

## 6. 依赖

- 前置要求：canonical EvidenceFingerprint 可用，Git 可读取 staged 与 push update identity。
- 上游事实：changed paths、context manifest、命令与工具链版本。
- 下游结果：本地 readiness queue、exact-input cache 与 typed receipt。
- 父级设计：`DEC-007`。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 readiness 队列的空闲触发与积压可见性

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：Cursor 没有 after-edit hook，Codex PostToolUse 当前也未接线且本机无真实 Codex smoke；自动 edit enqueue 已停用，队列没有受管自动 consumer，历史或显式入队项可长期停留在 `PENDING`。因此队列在本能力阶段只作 advisory，不阻断普通 Skill、scope 或 release。
- 完成判定：真实 Cursor/Codex 宿主 smoke 证明 edit producer 的输入/输出协议受支持，并证明 idle 或等价受管 consumer 在声明 SLO 内幂等启动 bounded worker；随后才可通过新 contract 版本重新评估 queue enforcement。`GWT-002.t3..t4` 持续证明积压量、最老入队时间、`exact-pending`/`foreign-pending` 与失败 typed pending 可见且不伪造 PASS。
- 依赖：Cursor/Codex 可验证的 edit/idle 生命周期事件、真实 Codex smoke，以及现有 `local_readiness.py enqueue|worker --once|inspect` 显式入口。

<a id="open-002"></a>
### OPEN-002 local readiness impact planner 复杂度热点收敛

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 exact candidate-bound Code Health report 将 `quwoquan_ops/ci/local_readiness_planner.py` 的 `build_impact_plan` 标为 `CODE_HEALTH.COMPLEXITY_ADVISORY`；该 calibration `PR_WARN` 不阻断 candidate，但继续增长会降低 planner 分支与降级语义的可审计性。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为继续满足；在独立 owner increment 中保留现有 impact-plan 合同并收敛该函数；fresh clean-range Code Health 不再为该 symbol 产生复杂度 advisory，且不得新增 allowlist、baseline 或改变 fail-closed terminal。
- 依赖：current Code Health named evidence与 planner focused contracts。

<a id="open-003"></a>
### OPEN-003 hosted code-health fact 尚未成为 promotion required evidence

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`10. Code Health Integration Recompute` 的 push 后 exact before/after fact 仍是 report-only（GWT-004），不能代替 accept 的 full delta 或 main base→current dev head 的完整 promotion range。尚缺 Lane Gate 左移 accept 与 hosted 验真的 current 接线验收证据；REQ-005/GWT-008 的默认 scope、完整 required/Review、pure prevalidate、no_live 拒绝与双路径 owner 对账也须 current 执行证明，冻结规格不代表实现通过；交付链已有完整 promotion range 的 producer/reader 增量，但其 required evidence 与 PR_WARN 裁决闭包仍须由该 owner 独立证明，不能沿用历史 lane PR 通过作为完成依据。
- 完成判定：`GWT-008.t1..t6` 具备 current 默认 scope、纯预检零 mutation、no_live 拒绝与双路径 owner 验真证据，缺口未证前保持 OPEN；`GWT-005` 证明 accept 缺失/失败健康证据不得 accepted、本地 integrate 对漂移证据拒绝、hosted 剩余 FF 能力如实披露；`GWT-004.t3` 继续成立（fact report-only、不冒充准出）；交付链 owner 以自身 SIT 证明 promotion `required_evidence_refs` 消费 main base→current dev head 完整 full 报告与既有 Review disposition，缺失/错范围/`GATE_BLOCK` 或未裁决 `PR_WARN` 均拒绝。不得把最后一次 push fact、本地 wrapper passed、warn-only 或降阈值替代完整准入。
- 依赖：`deliver-deploy-prod-pipeline` 的 promotion admission 契约与 `quwoquan_ops/ci/verify_code_health_integration.py`。

<a id="open-004"></a>
### OPEN-004 lane 门禁的 ops 合同覆盖面缺 macOS 与完整工具链

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`04. Lane Gate` 在 `ubuntu-latest` 上执行 ops local_contract 四分片（首跑 5269 通过 / 23 失败）。23 个失败全部来自 10 个把开发机事实写成前提的合同：macOS `sandbox-exec`、APFS `cp -c`、Flutter/Go/Dart 二进制、本机受管根证书、设备矩阵 preflight。它们已在 `quwoquan_ops/policies/gates/lane_gate_ops_contract_exclusions.yaml` 逐条声明缺失的宿主能力并从 lane 分片排除。排除不等于别处会补跑：`gate_repo.sh` 没有 ops local_contract 的整目录 pytest，10 个合同中只有 `test_app_generated_manifest` 经 `make test-gate-companion-local-contract` 进入 gate 链，`test_app_dependency_capsule` 仅被手动 target `verify-app-dual-platform-usability-baseline` 点名，其余 8 个只在 L0 commit-gate 按影响面选中或开发机手动 pytest 时执行。这些是历史 hosted 覆盖缺口；取消 lane PR、把检查集合移到 accept 不能自动证明它们已有稳定执行点。
- 完成判定：`GWT-005` 在同一 exact candidate 的 accept receipt 中证明完整 ops 合同集合实际执行、应非空分片非空且失败拒绝 accepted；宿主能力排除只减不增，required 能力缺失必须 typed 阻断，非 required skip 必须按 canonical 合同可见，不把 skipped 写成 passed。hosted 仅验该 exact 闭包，不重复完整套件；现有排除清单合同持续证明声明指向真实文件且不影响 data/全量。未取得 current 本地接线与执行证据前保留本 OPEN，历史数量不当作当前通过数。
- 依赖：accept 宿主工具链/设备能力与各合同 owner 的接线、合法 skip 可见性；hosted 替代验真门见 daily-merge OPEN-004。

<a id="open-005"></a>
### OPEN-005 `gate_repo.sh` 全量对 `main` 基线的门禁自证仍有 13 个 unproven gate

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`verify_gate_local_contract_execution.py` 在 `gate_repo.sh` 全量（不传变更区间）时以 `origin/main` 为基线判定「改动过的门禁脚本必须有被 gate 链执行的 companion」。`main` 长期落后 `dev1.0`，于是 `dev1.0` 与本 lane 上同样有 13 个 unproven gate 尚未闭合：`quwoquan_data/scripts/verify/` 下 11 个 verify 脚本没有任何同名 companion；`quwoquan_ops/gate/verify_stackctl_args_contract.py` 挂在 `gate_repo.sh` 上但没有 companion；`quwoquan_ops/gate/verify_app_cloud_closure.py` 有 59 例 companion 却在全仓没有任何调用方（死门禁）。该判据不进入 `04. Lane Gate`、L0 或 L1 readiness，因此不阻断 lane→`dev1.0`，但让开发机 `gate_repo.sh` 全量持续红，掩盖真正新增的自证缺口。
- 完成判定：`GWT-002` 下 `gate_repo.sh` 全量对当前 `main` 基线的 `verify_gate_local_contract_execution.py` 退出 0：Data lane 为 11 个 verify 脚本补 companion 或把它们从 gate 链下线；`verify_stackctl_args_contract.py` 获得 companion 并进入 `test-gate-companion-local-contract`；`verify_app_cloud_closure.py` 要么接入 gate 链要么连同 companion 一并删除，不保留无 caller 的门禁。
- 依赖：Data lane 对 `quwoquan_data/scripts/verify/**` companion 的产出；`main` 经 promotion 前移后基线自然收窄。

<a id="open-006"></a>
### OPEN-006 L0 选择器 `commit_gate_select.classify` / `static_checks` 复杂度热点收敛

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：lane→`dev1.0` 增量 `22786e264..1f4e09aa2` 的 candidate Code Health（hosted `04. Lane Gate` 与 dev1.0 push 后 `10. Code Health Integration Recompute` 一致）把 `quwoquan_ops/gate/commit_gate_select.py` 的 `classify`（cyclomatic 37 / cognitive 68，基线 34 / 63）与 `static_checks`（24 / 27，基线 23 / 26）标为 `CODE_HEALTH.COMPLEXITY_ADVISORY`。两者在 dev1.0 基线已越过 15/20 阈值，本增量只为 `workflow_actionlint` 与 checker 自触发各加一两条分支；calibration 阶段 `PR_WARN` 不阻断，但 L0 选择器是每次提交都走的路径，分支继续堆积会让「哪些 staged 改动触发哪些检查」不可审计。同一增量新增的 `_verify_ruleset`、`_step_self_output_reference_failures`、`_constant_loop_required` 三处热点已在 candidate 内以纯函数抽取修复，不在本 OPEN。尚缺的实现：把 path→flag 分类与 flag→静态检查两张表数据化并让两个函数回到阈值内；尚缺的验收证据：一份对该收敛后 head 的 fresh clean-range Code Health report，其中这两个 symbol 不再出现在 `CODE_HEALTH.COMPLEXITY_ADVISORY`。
- 完成判定：`GWT-001`/`GWT-002` 对应行为与 `test_commit_gate_select` 合同继续满足；在独立 owner increment 中把 path→flag 分类与 flag→静态检查两张表数据化，fresh clean-range Code Health 不再为这两个 symbol 产生复杂度 advisory，且不得新增 allowlist、baseline 或改变 fail-closed terminal。
- 依赖：current Code Health named evidence；[`OPEN-002`](#open-002) 的同类收敛先例。

<a id="open-007"></a>
### OPEN-007 三处基线已存在的「失败折成空值」路径

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：落地后独立评审在 dev1.0 基线里指出三处把外部失败折成空集合而无 typed 留痕的路径，均在本增量相邻但未改动：`.github/workflows/code-health-weekly.yml` 拉取 workflow runs 失败时 `|| echo '[]'`（weekly 报告会把 API 失败当作「无运行」）；`quwoquan_ops/gate/commit_gate_select.py` 的 `git diff --cached` 非零退出返回 `[]`（L0 会把 git 失败当作「无 staged 改动」而空跑）；`quwoquan_ops/gate/verify_workflow_cli_arguments.py` 的 `_run_blocks` 对 `yaml.YAMLError` 返回 `[]`（workflow 解析失败时该门禁对该文件零判定；解析期失效本身由 `verify_workflow_actionlint.sh` 拦截，故为可见性缺口而非漏放）。同一增量新增的 `report_code_health_weekly.discover_local_previous` 同形态问题已在 candidate 内修复为与 `_load_previous` 同轨抛错。
- 完成判定：三处改为 typed 失败（非零退出或显式 `skipped`/`failed` 字段）并各补一条让其变红的负例：`GWT-002` 下 L0 对 `git diff --cached` 失败返回 typed 失败而非空跑（`test_commit_gate_select` 锁定）；`GWT-005` 下 `verify_workflow_cli_arguments.py` 对 YAML 解析失败给出 typed 判定而非零判定；weekly 报告在 runs 拉取失败时标注 `deliveryRunsStatus=unavailable` 而非空样本（`GWT-004.t3` 的 report-only 语义保持）。
- 依赖：无外部依赖；按最低 owner 拆入各自 focused contract。

<a id="open-008"></a>
### OPEN-008 其余晚发现静态扫描的有界左移

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`run_app` 在 analyzer 之后仍执行 `verify_concept_naming.py`、`verify_runtime_host_literals.py` 及 Dart 语义棘轮；这些检查的依赖、companion 和累计预算尚未逐一证实，不能因退役词扫描已左移而声称全部本地首判。
- 完成判定：按 `REQ-003` 对现有晚发现扫描逐条核对输入、依赖、companion、失败负例与实测预算；合格者经 `OPEN-006` 的数据化选择表进入最早可执行层，并由 `GWT-006` 同类执行证据证明首判与失败传播；需 analyzer、超预算或缺 companion 者留在原层，明确原因与最低 owner 的缺口，不增加 allowlist 或放宽预算。
- 依赖：`OPEN-006` 的选择表收敛与各检测器 owner 的 companion；不得为此新增中央 check registry、常驻 worker 或重复 hosted 扫描。
