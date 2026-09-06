# L3 Story：本地优先持续集成与就绪判定 (`local-continuous-integration`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：本 Story 为横切工程能力，不直接承接用户 Journey。
>
> 设计归属：[L2 DEC-007](../design.md#dec-007)

## 1. 用户价值

作为在共享工作树中持续交付的开发者或 Agent，我希望编辑、空闲、提交范围与推送范围逐级获得绑定精确输入的本地反馈，从而在进入远端流水线前发现可本地判定的问题，并明确知道尚未满足的就绪条件。

## 2. 范围与非目标

### In Scope

- 显式 readiness 命令、持久 advisory 队列、可选择的 focused check，以及保留作未来/显式 producer 的 after-edit 脚本。
- 五个互不推导的事实维度：`sourceReadiness`、`environmentReadiness`、`deviceReadiness`、`integrationEligibility`、`promotionEligibility`；本 Story 只生产 `sourceReadiness`，其内部状态为 `fast_green`、`scope_ready`、`release_ready`。
- 基于 canonical EvidenceFingerprint 的精确输入缓存、回执新鲜度与资源互斥。
- Go、Python、Dart、Portal 与 spec/contract 的本地影响规划和执行。
- 仓库级 workflow lint 配置由本 Story 唯一拥有，作为 canonical workflow 静态检查的受版本控制输入。
- code-health delta 在 L0 快判、L1 完整检查、PR clean candidate 与 scheduled report-only 间的分层调度。

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
- source、lockfile、toolchain、command 或 owner manifest 任一变化都必须 cache miss；运行期间输入漂移必须使本次结果失效。
- PASS cache 只可按 exact-input 复用；同一资源的执行必须持有本地锁，不能以并发成功覆盖失败或漂移。
- deferred queue 必须持久化且可检查；在真实宿主 producer 与消费 SLO 闭合前，contract 将 `exact-pending` 与 `foreign-pending` 都标为 advisory，二者必须出现在 receipt/inspect 中但不得阻断显式 `scope`/`release`。显式 readiness 的 required checks 与 Review admission 仍 fail-closed。

<a id="req-003"></a>
### REQ-003 Git hook 只做边界检查，回执在准出消费

- 硬门只在准出（lane→`dev1.0` PR、交接、发布）。本地 git hooks 不消费 `scope_ready`/`release_ready` 回执，也不自动运行全面测试：pre-commit 只运行 staged boundary（secret/PII、generated/cache 边界，以及 `--local-commit` 当前 HEAD 分支检查），失败时只给出唯一恢复命令；pre-push 只运行 branch policy：普通 lane push 只校验同名远端，不要求同时推送全部 lane；匹配 `integration/dev1.0` 的普通认证 direct push 仅在 local/remote 均为 `dev1.0`、update line before/after OID 存在且 Git ancestry 证明 non-force fast-forward 时放行，相等幂等；缺 OID、authority 不可用、非快进、force/delete、来源不匹配、lane→dev、`main` direct push 或未知 ref 全部阻断。trusted publisher CAS 与可证明的受管 system fast-forward backsync 继续放行。
- `--local-commit` 必须只校验当前 HEAD 非 detached、Git authority 可读且分支属于 `allowed_local_branches`，不得枚举或治理其他 local/remote-tracking refs；无参数默认模式继续执行全 ref 治理，`--pre-push` 必须消费 canonical integration update contract。L0 `commit_gate.sh` 的提交前 branch 检查也必须使用 `--local-commit`。
- `sourceReadiness.status=scope_ready|release_ready` 仍由显式 CLI 产出并绑定精确输入 fingerprint，供 Skill 报告与交接消费；integration worktree direct fast-forward push 不生产 readiness 或资格事实，`integrationEligibility` 只能由 exact candidate + Alpha/Beta admission 建立，`promotionEligibility` 只能由 current dev head 的 IntegrationQualificationFact 建立，GitHub Delivery Gate 只验后者的不可变身份。
- L0 的 code-health 快判不得网络安装工具且以 p95 30 秒为目标；L1 执行完整 candidate delta；scheduled 全仓热点只 report-only。指标与阈值唯一引用系统架构能力的 `REQ-008` 与 `DEC-031`，本 Story 不复制。`lane/* -> dev1.0` 的 hosted 复算由 `.github/workflows/lane-gate.yml`（`04. Lane Gate`）承担：它在 exact PR head 上重建 ImpactPlan、校验 changed boundary、以 `verify_code_health_delivery.py` 绑定同一 `changed_paths_digest`/`impact_plan_digest` 复算 `code-health-delta`，并分片执行 `quwoquan_ops/tests/local_contract/**`；该 check 名称由 `branch_policy.yaml#required_integration_checks` 唯一声明，与 `required_promotion_checks` 互斥。本地 PASS 不替代该 hosted 复算。
- 影响分类的边界：`classify_impacts` 只把 changed paths 分类成"触及了哪些运行时 scope"的事实，未知根级路径的运行时触及为零；把它升到 `R3` 并要求全 scope 是 Delivery 的 fail-closed 决策，只在 `build_delivery_impact_plan` 施加。本地 L-1/L0 复用同一分类做秒级 focused 反馈，不得为陌生根文件扇出全部 scope。
- staged 中某个已修改文件继续改变内容时，即使 `git status` 文本不变，也必须判定旧回执失效。

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
- AND exact-input cache 对 source、lockfile、toolchain、command 与 owner manifest 的变化全部 miss。

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
- THEN pre-commit 只运行 staged boundary（secret/PII、generated/cache 边界，以及 `--local-commit` 当前 HEAD 分支检查），pre-push 只运行既有 `--pre-push` branch policy；普通 lane push 不要求 all lanes，匹配 integration worktree 的 `dev1.0 -> dev1.0` non-force fast-forward direct push 与可证明的 system fast-forward backsync 可通过，非快进/delete/force、lane→dev和main direct push被拒绝；两者都不读取 readiness 回执，秒级完成。
- AND 合法 current lane 即使存在非法陈旧 local/remote-tracking refs 也通过 `--local-commit`；非法当前分支、detached HEAD 或 Git authority 不可读必须失败；无参数默认模式仍拒绝额外 refs。
- AND 任一边界检查失败都阻断并只返回一个稳定 recovery。hook 不读取 readiness receipt、也不输出 readiness PASS，缺少 `scope_ready`/`release_ready` 不构成 lane 提交或推送的阻断理由。

<a id="gwt-004"></a>
### GWT-004 hosted 复算只对 exact dev1.0 快进范围发布 typed fact

- GIVEN `dev1.0` 收到一次 push，hosted `code-health-integration` workflow 以事件提供的 exact before/after OID 运行。
- WHEN 驱动对 before..after 复算 canonical code-health delta。
- THEN before 为零 SHA、与 after 相同或不是 after 的祖先时不复算，返回 typed `GATE_BLOCK` 并只发布携带 blocker code 的 typed fact。
- THEN 复算 terminal 为 `GATE_BLOCK` 时 run 失败且 fact terminal 为 `GATE_BLOCK`，不产生任何 PASS fact；terminal 为 `PASS`/`PR_WARN` 时 run 成功且 fact 绑定 exact before/after 与完整 candidate report。
- THEN fact 只是 report-only 事实（`blocksPush=false`），不拦截已发生的 push；是否进入 promotion `required_evidence_refs` 由交付链 owner 单独裁决，本 Story 不据此声称集成准出。

<a id="gwt-005"></a>
### GWT-005 lane PR 的 hosted 复算是 fail-closed 的 required check

- GIVEN 一个 `lane/* -> dev1.0` 的 Pull Request，其 exact head 与 merge-base 可从 Hosted 事件精确读回。
- WHEN `04. Lane Gate` 在该 PR 上执行。
- THEN 它只由 `pull_request: branches: [dev1.0]` 触发，在 exact PR head 的 clean checkout 上重跑 branch/supply-chain/workflow/artifact/脚本治理与 Feature Tree；ImpactPlan 由 `detect_ci_impacted_scopes.py` 以 `--execution-profile pr` 生成并经 `--validate-impact-plan` 与 `verify_ci_changed_boundary.py` 四个 required 参数校验；`code-health-delta` 以 `verify_code_health_delivery.py` 绑定同一 `changed_paths_digest` 与 `impact_plan_digest` 复算；`quwoquan_ops/tests/local_contract/**` 经 `delivery_gate_data_shard.py --scope ops` 取模分片执行。
- AND `lane_gate_summary` 以 `always()` 汇总且对全部三个 job 只接受 `success`；任一 job 失败、`code-health-delta` 返回 `GATE_BLOCK`、或分片为空时该 check 失败，PR 不可合入。GWT-004 的 push 后复算是 report-only 事实，不替代本 check。
- AND 该 check 名称与 `branch_policy.yaml#required_integration_checks` 唯一声明一致，与 `required_promotion_checks` 不共享 workflow 或名字；job 间不通过 Actions artifact 交换结果，digest 在需要处就地重算。
- AND workflow 对仓内 Python CLI 的每次直接调用都必须覆盖该脚本全部常量 required 选项；`verify_workflow_cli_arguments.py` 在 L0 只对本次 staged 的 workflow 判定、在 `gate_repo.sh` 全量判定，漏传即 `GATE_BLOCK`。

## 6. 依赖

- 前置要求：canonical EvidenceFingerprint 可用，Git 可读取 staged 与 push update identity。
- 上游事实：changed paths、owner manifest、命令与工具链版本。
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
- 影响或价值：`lane/* -> dev1.0` 的 PR 前阻断已由 `04. Lane Gate`（`GWT-005`）承担，`10. Code Health Integration Recompute` 对每次 `dev1.0` 快进复算 exact before/after 并发布 typed fact（`GWT-004`）；但两者之间仍缺一环：`integration/` 工作区的 direct fast-forward push 不经 PR，此时只有 push 后的 report-only fact，而 `03. Delivery Gate` 的 `required_evidence_refs` 尚未要求该 fact，于是经该通道进入 `dev1.0` 的新增或恶化代码健康债在 promotion 前仍不阻断。
- 完成判定：`GWT-005` 持续证明 lane PR 的 hosted required check fail-closed；`GWT-004.t3` 继续成立（fact report-only、不冒充准出）；交付链 owner 把 dev1.0 head 对应的 code-health fact 纳入 promotion `required_evidence_refs` 并由其自身规格证明 `GATE_BLOCK` fact 使 promotion admission 失败；不得以本地回执、warn-only 或降低阈值替代。
- 依赖：`deliver-deploy-prod-pipeline` 的 promotion admission 契约与 `quwoquan_ops/ci/verify_code_health_integration.py`。

<a id="open-004"></a>
### OPEN-004 lane 门禁的 ops 合同覆盖面缺 macOS 与完整工具链

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`04. Lane Gate` 在 `ubuntu-latest` 上执行 ops local_contract 四分片（首跑 5269 通过 / 23 失败）。23 个失败全部来自 10 个把开发机事实写成前提的合同：macOS `sandbox-exec`、APFS `cp -c`、Flutter/Go/Dart 二进制、本机受管根证书、设备矩阵 preflight。它们已在 `quwoquan_ops/policies/gates/lane_gate_ops_contract_exclusions.yaml` 逐条声明缺失的宿主能力并从 lane 分片排除，`gate_repo.sh` 全量执行不受影响；但这意味着 lane PR 对这 10 个合同缺少 hosted 复算，仍依赖开发机或 self-hosted macOS。
- 完成判定：`GWT-005` 持续证明剩余 593 个合同在 hosted 上 fail-closed；排除清单只减不增，每条被删除的前提是该合同改为按宿主能力 `skipif`（并让 skip 可见于回执）或 lane 门禁获得 hosted macOS runner；`test_lane_gate_exclusions_are_declared_real_ops_files_and_only_narrow_ops` 持续证明清单指向真实文件且不影响 data/全量。
- 依赖：hosted macOS runner 预算，或 10 个合同的 owner 为其补 `skipif` 与 skip 可见性。
