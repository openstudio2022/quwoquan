# L3 Story：本地 worktree 生命周期治理 (`local-worktree-lifecycle-governance`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-026](../design.md#dec-026)

## 1. 用户价值

作为在本仓库并行使用多个 AI 执行面与人工终端的开发者，我希望新建 worktree 或 clone 前执行体会被提醒先取得我的显式授权，并且任何未合入 `dev1.0` 的滞留工作都会被持续提醒，从而不再出现「意外多出一个工作副本、很久之后才发现里面压着未合入改动」的结果；同时日常开发与 Skill 调用不被 hook 阻断，硬门只留在准出。

## 2. 范围与非目标

### In Scope

- 本地 linked worktree 与同源 clone 的创建授权提醒（observe-only 上下文注入），覆盖 Cursor、Codex 两条执行面。
- 未合入工作（本地领先提交、工作树脏改动、stash）的滞留识别与分级提醒。
- git hooks 安装状态（`core.hooksPath`）的自检与失效告知。
- 上述判定所需清单的实时派生方式，以及「不得留存台账」的约束。
- 六条长期 lane 的 worktree 身份与 clean/bootstrap 一致性，在准出门禁中验证。

### Out of Scope

- 分支角色、合法 PR 边与晋级准入，由 [`daily-merge-release-strategy`](../../deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md) 的 `REQ-001`、`REQ-002` 拥有，本 Story 只引用不重复。
- 远端 GitHub branch protection、ruleset 与托管侧强制，见该 Story 的 `OPEN-002`。
- hook 面的任何阻断（deny/ask）。执行面 hook 只注入上下文，判断权留给执行体；hook 运行在开发者本机且执行体有权改写环境变量与仓内文件，本就不构成安全边界。真正的硬门只在准出：lane→`dev1.0` 合入、交接、发布。
- 工作副本的自动删除、自动合并或自动 stash。提醒只产生可观察告知，处置由人决定。
- 同一 worktree 内多会话/多子代理的 writer 互斥。共享工作树的合作规则由根 `AGENTS.md` 的行为条款承担，不以 hook、claim 文件或锁实现。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 worktree 与 clone 创建的授权提醒

- 识别面为三类动作：新增 linked worktree、对本仓库同源 origin 的再次 clone、创建 branch policy `allowed_local_branches` 白名单之外的本地分支。分支白名单与禁令本身由 `daily-merge-release-strategy` `REQ-001` 拥有，本 Story 只补齐它在 worktree 与 clone 维度的缺口，不复制分支清单。
- 授权是根 `AGENTS.md` Git 不变量对执行体的行为要求：新建 linked worktree 或再次 clone 每次都须先取得用户明确授权。hook 只负责在识别面命中且该 segment 未以授权凭据留痕时，把该规则、留痕方式（`QWQ_WORKTREE_AUTHZ="<用户同意的理由>"` 前缀）与 canonical 创建形态注入执行体上下文；始终 `allow`，不 `deny`、不 `ask`，由 Cursor/Codex 依用户意图自行判断。
- canonical lane worktree 形态：显式 `-b <fixed lane>`、显式 path 与 start-point，start-point 解析为 `origin/dev1.0`（不存在时才回落本地 `dev1.0`），不使用 `--detach`、force 与 force-create；可从任意 worktree 发起，不要求当前 worktree 在 `dev1.0`。非 canonical 形态只附带模板提醒（`OPS.WORKTREE.INVALID_ADD`），不阻断；创建后的 lane clean/HEAD 一致性由准出门禁 `verify_local_worktree_lifecycle.py` 验证。
- 两个执行面共用同一判定实现，只在输出协议上适配：Cursor `beforeShellExecution` 以 `agent_message`/`user_message` 注入，Codex `PreToolUse` 以 `hookSpecificOutput.additionalContext` 注入。策略不可读时同样 `allow`，并注入 `OPS.WORKTREE.POLICY_INVALID` 与稳定 recovery，不以任何形式阻断。
- Codex 对每条 Bash 命令都会调用本 hook，因此未命中创建面正则的命令必须在加载策略与探测 git 之前返回，不得让每条命令背负策略加载开销。
- 授权凭据是随命令一次性传递的显式意图声明，不得沉淀为「已授权清单」。授权理由只作为可删除运行记录留痕，删除后不改变后续任何判定。
- 提醒身份为 `OPS.WORKTREE.NOT_AUTHORIZED`，策略不可读为 `OPS.WORKTREE.POLICY_INVALID`；路径、命令、授权理由与解析诊断只进入 string context。

<a id="req-002"></a>
### REQ-002 未合入工作的滞留识别与分级提醒

- 「未合入」由三类事实的并集判定：领先 `origin/dev1.0` 的本地提交、工作树脏改动、stash 条目。三类事实全部为空的工作副本不产生提醒。
- 滞留时长取三类事实中最早的发生时间：最早未合入提交的 committer date、最早脏文件 mtime、最早 stash 时间。
- 事实必须归属到真正持有它的工作副本。stash 存放在仓库 common dir，全部 linked worktree 与主 worktree 共享同一份，因此 stash 只归属独立 clone；未合入提交必须以主仓库的集成分支为基准判定，不得采用副本自身可能陈旧的远程引用。错误归因会让刚创建的干净副本立刻显示为已滞留，几次假报警之后整条提醒就不再被阅读。
- 提醒必须在两个时机触达：任何一次向 `dev1.0` 的提交完成后立即触达；每个执行面按最小间隔触达，使自然日内至少提醒一次。
- 投递事件按执行面各自声明的输出能力选择。执行面的会话开始事件不支持投递消息时，必须回落到该执行面确实支持输出的事件；挂在不支持输出的事件上会让 hook 正常退出却什么也不投递，而静默失效正是本 Story 要治理的那类问题。回落到高频事件时，未到时点的短路判断不得引入第二份间隔参数。
- 滞留时长超过策略阈值的工作副本升级为强提醒，并给出该副本路径、未合入事实计数与滞留天数。
- 提醒去重状态属于可删除运行输出，丢失后只退化为多提醒一次，不得因其缺失而漏报。
- 识别范围必须覆盖 linked worktree 与策略声明的发现根下的同源 clone。clone 目标不继承本仓库 hooks，只能由源侧识别。
- 失败身份为 `OPS.WORKTREE.UNMERGED_OVERDUE`。

<a id="req-003"></a>
### REQ-003 hooks 安装状态自检

- `core.hooksPath` 未指向仓内受版本控制的 hook 目录时，本仓库的提交与推送门禁全部失效，该状态本身必须可被发现。
- 因为 hooks 失效时 pre-commit 不会运行，自检不得只挂在 pre-commit；必须由聚合门禁与执行面会话开始两处交叉承担。
- 安装入口必须在仓库根被正确解析，并可幂等重复执行。
- 失败身份为 `OPS.WORKTREE.HOOKS_NOT_INSTALLED`。

<a id="req-004"></a>
### REQ-004 清单只实时派生，不得留存台账

- worktree 与 clone 清单只能由 `git worktree list` 与策略声明的发现根实时派生；禁止提交或维护工作副本 registry、inventory、已授权 allowlist 与滞留基线。
- `git worktree list --porcelain` 失败、linked worktree probe 失败、detached、非 fixed lane、重复 lane 绑定或路径重复均 fail-closed，不得把失败退化为空清单；默认门禁只验证已发现 linked worktree，不要求六条 lane 已全部存在。
- 全量身份门开启时必须精确存在六条 fixed lane，且每条 worktree clean、HEAD 与优先 `origin/dev1.0` 的 canonical integration ref（不存在时才回落本地 `dev1.0`）一致。
- 策略参数（数量上限、滞留阈值、提醒最小间隔、发现根、失败码）集中在唯一策略文件，实现不得内联第二份默认值。

## 4. 契约引用

- canonical：`quwoquan_ops/policies/worktree_policy.yaml`
- canonical：`quwoquan_ops/cli/lib/local_worktree_inventory.py`
- canonical：`quwoquan_ops/hooks/worktree_authz_guard.py`
- canonical：`quwoquan_ops/hooks/worktree_merge_reminder.py`
- canonical：`quwoquan_ops/hooks/worktree_session_reminder_gate.sh`
- canonical：`quwoquan_ops/hooks/run_install_hooks.sh`
- canonical：`quwoquan_ops/gate/verify_local_worktree_lifecycle.py`
- canonical：`.cursor/hooks.json`
- canonical：`.codex/hooks.json`
- 分支角色与合法 PR 边：[`daily-merge-release-strategy` REQ-001](../../deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#req-001)
- 分支机器合同：`quwoquan_ops/policies/branch_policy.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 创建授权提醒在两个执行面注入且不阻断

- GIVEN 策略声明了授权凭据名称与三类识别面，且当前命令未携带该凭据。
- WHEN Cursor 或 Codex 执行面即将执行新增 linked worktree、再次 clone 本仓库或创建非白名单分支的命令。
- THEN 两个执行面都返回 `allow`，并按各自协议注入 `OPS.WORKTREE.NOT_AUTHORIZED`、根 `AGENTS.md` 授权要求与 `QWQ_WORKTREE_AUTHZ` 留痕方式；策略不可读时同样 `allow` 并注入 `OPS.WORKTREE.POLICY_INVALID` 及稳定 recovery。
- AND 白名单分支、只读 worktree 子命令、第三方仓库 clone 与任何未命中创建面的命令不产生消息，且后者在加载策略前返回；误伤与每条命令的秒级开销都会让这道提醒很快被整体关闭。
- AND 同一 command 中每个创建 segment 分别留痕；已留痕且 canonical 的 segment 静默放行并写入可删除运行记录，未留痕或非 canonical 的 segment 只附带对应提醒/模板，不产生任何受版本控制的授权清单。

<a id="gwt-002"></a>
### GWT-002 滞留工作在提交与会话开始时被提醒

- GIVEN 存在至少一个含未合入提交、脏改动或 stash 的工作副本，且其最早未合入事实早于策略阈值。
- WHEN 向 `dev1.0` 完成一次提交，或任一执行面开始新会话且距上次提醒已超过最小间隔。
- THEN 提醒列出该副本路径、未合入事实计数与滞留天数，并以 `OPS.WORKTREE.UNMERGED_OVERDUE` 标识超阈值项。
- AND 三类未合入事实全部为空的工作副本不出现在提醒中；删除提醒去重状态后重新触发只会多提醒一次，不会漏报。
- AND 刚创建且自身干净的 linked worktree 不因共享 stash 或副本自身的陈旧远程引用被判为滞留。
- AND 回落到高频事件的投递通道在未到时点时只返回放行、不携带消息，且其短路判断不内联提醒间隔。

<a id="gwt-003"></a>
### GWT-003 hooks 失效可被发现且安装入口可正确解析

- GIVEN `core.hooksPath` 未设置，或未指向仓内受版本控制的 hook 目录。
- WHEN 执行聚合门禁，或任一执行面开始新会话。
- THEN 返回 `OPS.WORKTREE.HOOKS_NOT_INSTALLED` 并给出安装命令，且该判定不依赖 pre-commit 自身运行。
- AND 安装入口在仓库根正确解析并可幂等重复执行；执行后 `core.hooksPath` 指向仓内 hook 目录，提交与推送门禁恢复生效。

<a id="gwt-004"></a>
### GWT-004 lane 身份在准出门禁中 fail-closed

- GIVEN 实时 worktree authority 与六条 fixed lane policy。
- WHEN 准出门禁 `verify_local_worktree_lifecycle.py` 验证已发现 linked worktree，或以全量模式要求六条 lane 全部存在。
- THEN inventory authority 失败、detached/非 lane/重复身份、probe error、全量 lane 缺失/dirty/HEAD 漂移均返回 typed blocker；默认模式不要求六条 lane 已全部创建。
- AND 该判定只在显式运行门禁（本地 `make verify-local-worktree-lifecycle`、lane→`dev1.0` PR 的 CI）时生效，不挂在任何执行面 hook 或普通 commit gate 的无条件 static checks 上；改动 worktree 治理实现/策略时，commit gate 只选择 lifecycle focused local_contract；门禁 recovery 要求长期 lane fast-forward resync 并保留 worktree，clone 或额外废弃副本才由人工决定是否删除。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的范围、要求与 SIT。
- 上游语义：[`daily-merge-release-strategy`](../../deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md) 的分支角色与集成准入。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-026](../design.md#dec-026)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 lane recovery 处置尚无直接行为测试

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：[`GWT-004.t1`](#gwt-004) 至 [`GWT-004.t3`](#gwt-004) 已由 lifecycle gate local_contract 绑定，[`GWT-004.t4`](#gwt-004) 由 commit-gate focused test selection 绑定；但当前只有 recovery 文案与策略声明，没有测试直接执行并验证长期 lane fast-forward resync 后 worktree retained，以及 clone/额外副本只由人工决定删除。
- 完成判定：[`GWT-004.t5`](#gwt-004) 由职责匹配的 local_contract 直接绑定并实际通过，证明 resync 后同一路径 worktree 仍在场且未自动删除 clone/额外副本。
- 依赖：worktree lifecycle gate 与 branch policy owner；不得把提示文案存在当成处置已执行。
