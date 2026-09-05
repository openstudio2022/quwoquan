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
- `fast_green`、`scope_ready`、`release_ready` 三种逐级就绪状态。
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
- L2 只有全部 release profile 成功且 `deferred=[]` 时生成 `release_ready`；本地回执不得声称环境或正式发布已就绪。

<a id="req-002"></a>
### REQ-002 精确输入身份、缓存和互斥

- 规划、运行、缓存与回执必须复用 canonical EvidenceFingerprint，覆盖 tracked、untracked、deleted、renamed 与 symlink 的实际内容身份。
- source、lockfile、toolchain、command 或 owner manifest 任一变化都必须 cache miss；运行期间输入漂移必须使本次结果失效。
- PASS cache 只可按 exact-input 复用；同一资源的执行必须持有本地锁，不能以并发成功覆盖失败或漂移。
- deferred queue 必须持久化且可检查；在真实宿主 producer 与消费 SLO 闭合前，contract 将 `exact-pending` 与 `foreign-pending` 都标为 advisory，二者必须出现在 receipt/inspect 中但不得阻断显式 `scope`/`release`。显式 readiness 的 required checks 与 Review admission 仍 fail-closed。

<a id="req-003"></a>
### REQ-003 Git hook 只做边界检查，回执在准出消费

- 硬门只在准出（lane→`dev1.0` PR、交接、发布）。本地 git hooks 不消费 `scope_ready`/`release_ready` 回执，也不自动运行全面测试：pre-commit 只运行 staged boundary（secret/PII、generated/cache 边界，以及 `--local-commit` 当前 HEAD 分支检查），失败时只给出唯一恢复命令；pre-push 只运行 branch policy：普通 lane push 只校验同名远端，不要求同时推送全部 lane；canonical activation 为 `active` 时阻断直推 `dev1.0`/`main`，并只放行可证明的受管 system fast-forward backsync。
- `--local-commit` 必须只校验当前 HEAD 非 detached、Git authority 可读且分支属于 `allowed_local_branches`，不得枚举或治理其他 local/remote-tracking refs；无参数默认模式继续执行全 ref 治理，`--pre-push` 必须消费 canonical activation state。L0 `commit_gate.sh` 的提交前 branch 检查也必须使用 `--local-commit`。
- `scope_ready`/`release_ready` 仍由显式 CLI 产出并绑定精确输入 fingerprint，供 Skill 报告、交接单与 lane→`dev1.0` PR 说明消费；PR 准出由 CI Delivery Gate 在独立并行 job 重新执行 required `code-health-delta`，不信任本地回执。
- L0 的 code-health 快判不得网络安装工具且以 p95 30 秒为目标；L1 执行完整 candidate delta；scheduled 全仓热点只 report-only。指标与阈值唯一引用系统架构能力的 `REQ-008` 与 `DEC-031`，本 Story 不复制。
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
- THEN 不生成 `scope_ready` 或 `release_ready` PASS 回执。
- AND queue backlog（包括 exact candidate pending）仅作为 receipt/inspect advisory 可见；显式 worker 失败不生成 PASS，但 backlog 本身不阻断 scope/release。
- AND Portal 范围必须真实执行 `npm test` 与 `npm run build` 后才能范围就绪。

<a id="gwt-003"></a>
### GWT-003 Git hooks 只做边界检查

- GIVEN 开发者在 lane worktree 上暂存改动并提交或推送。
- WHEN pre-commit 或 pre-push 运行。
- THEN pre-commit 只运行 staged boundary（secret/PII、generated/cache 边界，以及 `--local-commit` 当前 HEAD 分支检查），pre-push 只运行既有 `--pre-push` branch policy；普通 lane push 不要求 all lanes，active 集成分支的 direct push 被拒绝，可证明的 system fast-forward backsync 可通过；两者都不读取 readiness 回执，秒级完成。
- AND 合法 current lane 即使存在非法陈旧 local/remote-tracking refs 也通过 `--local-commit`；非法当前分支、detached HEAD 或 Git authority 不可读必须失败；无参数默认模式仍拒绝额外 refs。
- AND 任一边界检查失败都阻断并只返回一个稳定 recovery。hook 不读取 readiness receipt、也不输出 readiness PASS，缺少 `scope_ready`/`release_ready` 不构成 lane 提交或推送的阻断理由。

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
