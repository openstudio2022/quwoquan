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

- 编辑后的短时反馈、持久待办队列和可选择的 focused check。
- `fast_green`、`scope_ready`、`release_ready` 三种逐级就绪状态。
- 基于 canonical EvidenceFingerprint 的精确输入缓存、回执新鲜度与资源互斥。
- Go、Python、Dart、Portal 与 spec/contract 的本地影响规划和执行。

### Out of Scope

- 常驻守护进程、替代远端 Delivery Gate 或自动发布。
- 用本地源码与测试结果冒充环境、设备、UAT 或生产 release 证据。
- 修改父 L2 的规格或设计接线。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分层反馈与 fail-closed 就绪

- L-1 编辑反馈必须短时完成入队，并可同步执行安全的 focused check；异常时不得生成 PASS。
- L0 空闲增量可生成允许带 deferred 的 `fast_green`，但不得升级为 `scope_ready`。
- L1 只有全部范围检查和 compile/build 成功且 `deferred=[]` 时生成 `scope_ready`。
- L2 只有全部 release profile 成功且 `deferred=[]` 时生成 `release_ready`；本地回执不得声称环境或正式发布已就绪。

<a id="req-002"></a>
### REQ-002 精确输入身份、缓存和互斥

- 规划、运行、缓存与回执必须复用 canonical EvidenceFingerprint，覆盖 tracked、untracked、deleted、renamed 与 symlink 的实际内容身份。
- source、lockfile、toolchain、command 或 owner manifest 任一变化都必须 cache miss；运行期间输入漂移必须使本次结果失效。
- PASS cache 只可按 exact-input 复用；同一资源的执行必须持有本地锁，不能以并发成功覆盖失败或漂移。
- deferred queue 必须持久化且可检查，不能把本地可执行工作留给 GitHub 后继续声称范围就绪。

<a id="req-003"></a>
### REQ-003 Git hook 消费新鲜回执

- pre-commit 不得自动运行全面测试，只接受绑定当前 staged fingerprint 的 fresh `scope_ready` 回执；缺失或过期时只能给出唯一恢复命令。
- pre-push 必须继续执行 branch policy，并在 push updates 可精确绑定时只接受 fresh `release_ready` 回执。
- staged 中某个已修改文件继续改变内容时，即使 `git status` 文本不变，也必须判定旧回执失效。

## 4. 契约引用

- local readiness contract：`quwoquan_ops/policies/local_readiness_contract.yaml`
- EvidenceFingerprint：`quwoquan_ops/policies/agent_governance_contract.yaml#evidence_fingerprint`
- branch policy：`quwoquan_ops/gate/verify_git_branch_policy.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 精确内容变化使回执失效

- GIVEN 当前 staged 范围已有 `scope_ready` 回执。
- WHEN 已标记为 M 的文件内容继续变化而 Git status 文本保持相同。
- THEN pre-commit 拒绝旧回执并只输出当前 staged producer 恢复命令。
- AND exact-input cache 对 source、lockfile、toolchain、command 与 owner manifest 的变化全部 miss。

<a id="gwt-002"></a>
### GWT-002 deferred 与执行失败不能升级就绪

- GIVEN planner 产生本地 focused、compile/build 或 release 工作。
- WHEN 任一 required check 失败、worker/hook 异常或队列仍有 deferred。
- THEN 不生成 `scope_ready` 或 `release_ready` PASS 回执。
- AND Portal 范围必须真实执行 `npm test` 与 `npm run build` 后才能范围就绪。

<a id="gwt-003"></a>
### GWT-003 Git hooks 只消费精确范围证据

- GIVEN 开发者显式执行 staged scope producer 或绑定 push updates 的 release producer。
- WHEN pre-commit 或 pre-push 运行。
- THEN hook 同时校验 readiness 等级、PASS、新鲜度、输入 fingerprint 与对应 Git 范围。
- AND pre-push 仍执行 branch policy，任一校验异常都不会伪造 PASS。

## 6. 依赖

- 前置要求：canonical EvidenceFingerprint 可用，Git 可读取 staged 与 push update identity。
- 上游事实：changed paths、owner manifest、命令与工具链版本。
- 下游结果：本地 readiness queue、exact-input cache 与 typed receipt。
- 父级设计：`DEC-007`。

## 7. 开放事项

当前无本 Story 内开放事项。
