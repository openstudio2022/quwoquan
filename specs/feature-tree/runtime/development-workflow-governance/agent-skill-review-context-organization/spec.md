# L3 Story：Agent 技能与评审上下文组织 (`agent-skill-review-context-organization`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；支撑全部 Scenario 的一致实施与审核约束
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-004](../design.md#dec-004)、[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为使用 Cursor 或 Codex 的编程 Agent、审核者和仓库维护者，我希望每次任务只加载当前路径、
工作流和风险真正需要的约束，并让 Review 在固定角色预算内消费同一份 owner 与证据事实，
从而减少上下文追链、重复 gate、模型额度放大和卡顿，同时保持失败可见、证据可复查。

## 2. 范围与非目标

### In Scope

- 根与子树 `AGENTS.md`、`.agents/skills` 唯一 Workflow Skill authoring/discovery surface、Feature spec/design/contracts、Review role/checklist 和 Cursor/Codex Reviewer projection 的单轨职责与渐进加载顺序。
- 只读控制 Skill 对 `feature-context` 的 best-effort 解析，以及 mutation workflow 与显式/准出 Review 对内容寻址 compact manifest immutable exact ref 的强制消费和复用。
- Review 的主审、唯一专审、命名 evidence、脏工作树指纹、定向复审和角色调用预算。
- Cursor/Codex 两个真实宿主对显式入口与自然语言 metadata discovery 的 smoke，以及 Reviewer 生成物一致性。

### Out of Scope

- 各业务领域自身的产品决定、wire schema 和 gate 实现细节。
- 自动清理 Cursor 本地数据库、改写历史 immutable receipt 或保留评审历史台账。
- 把 feature owner、执行状态或上下文正文复制进新的 tracked registry。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 规则按唯一职责分层并渐进加载

- 根 `AGENTS.md` 只拥有全仓安全、真相源顺序、工作流选择、证据诚实性、共享工作树与 Git 不变量。
- 最近子树 `AGENTS.md` 只拥有该子树每次变更都成立的不变量和工程入口；功能、页面、算法或错误事实不得进入全局规则，子树也不得参与自然语言工作流路由。
- `.agents/skills/*/SKILL.md` metadata 是唯一宿主发现面，body 是唯一 Workflow Skill 正文，只拥有触发与输入、执行、完成证据、失败停止、条件性交接五段；完成判据就地声明，不再经共享 completion/interaction 文档二次跳转。
- Feature spec/design/contracts 拥有功能行为、设计约束与验收；Review role 只拥有职责和盲区，checklist 只拥有分级判定并引用命名 evidence。
- `.cursor/commands` 只是一行式显式入口；`.cursor/agents` 与 `.codex/agents` 只允许 Reviewer projection。宿主专属目录不得承载 Workflow Skill stub、发现副本或规范正文。

<a id="req-002"></a>
### REQ-002 开发与 Review 共用精确 owner manifest

- Skill PRE 确定 exact target 后，`feature-context` 默认只输出内容寻址、不可变的紧凑 manifest exact ref；展开父链正文必须显式请求 expanded 格式。
- manifest 必须遵守 canonical agent governance contract 的 `feature_context_manifest` schema，指向唯一 owner 与直接 canonical 锚点并绑定自身内容摘要；不得把整条父链正文拼入默认输出。
- 路径先由 L1 最长工程根确定领域 owner，再由该 L1 下 L2 DEC 的适用工程根与唯一影响 Story
  精确下钻；同优先级多 owner、无 owner或解析失败必须产生 typed owner 解析结果。
- `explore`、`plan-next` 及 `continue` 的只读恢复 best-effort 调用 `feature-context`：唯一 owner 成功时保存并消费 immutable exact ref；无 owner、多 owner或解析失败时记录 typed 结果，基于当前 Git 快照继续只读，不 `GATE_BLOCK` 整个控制流程，也不得据此进入 mutation。
- prd、design、dev 等 mutation workflow 进入写入前必须持有唯一且 current 的 immutable exact ref；用户显式或准出 Review 必须原样复用该 ref。ref 缺失、旧 schema、内容摘要漂移、owner 多义、锚点冲突或 fingerprint stale 必须 fail-closed。控制型零 Reviewer workflow 不得包装送审交付件旁路 owner manifest。
- manifest 不包含 profiles。Review profile 只在显式或准出 Review 中按 current `changed_paths + deliverable` 派生 specialist 与 evidence，不复制 feature owner 或 design 内容。
- 上下文装配顺序固定为根 AGENTS → 宿主基于 `.agents/skills` metadata 选择 Skill → 唯一 Skill body → Skill PRE 确定 exact target → 最近子树 AGENTS + compact manifest immutable exact ref → exact contexts/tests。已知目标路径时可先读取最近子树 AGENTS，但子树不参与自然语言路由；禁止 manifest-before-skill。自然语言与显式入口必须由真实宿主加载同一 Skill body 并进入同一生命周期。

<a id="req-003"></a>
### REQ-003 Review 固定为主审加最多一名专审

- 显式或准出 Review 的 PRE 只由主会话完成 owner、范围、验收和 evidence 预检；其 POST 按 registry 先执行命名 evidence，再装配唯一 primary 与最高优先级 specialist。计划形态和预算必须遵守 canonical contract 与 registry limits。
- `explore`、`plan-next`、`continue`、`review` 与 `commit` 是零 Reviewer 的控制型 workflow：前两者不产生送审交付件，`continue` 复用被恢复 workflow，`review` 禁止递归自审，`commit` lane 提交不要求 Review evidence。其他 workflow 在 registry 保留 primary/specialist 角色配置供显式或准出派发，开发期 POST 默认零 Reviewer；显式 Review 仍受同一两角色上限。
- 修复后只允许 finding owner 定向复审；禁止第二次自动复审、超时自动重试或绕过 registry limits。

<a id="req-004"></a>
### REQ-004 Evidence 与复用身份单轨

- evidence 的定义只由 registry 拥有；checklist 的 MUST 只能绑定 `evidence: <id>` 或客观
  `check:`，不得保存命令。
- board 每个 evidence ID 只执行一次并把结果共享给 Reviewer。Reviewer 缺 evidence 时报告 incomplete，禁止自行补跑命令。Evidence runner 在首条命令前按 plan changed paths、canonical contexts 与 review assets 重算 current EvidenceFingerprint；tracked/untracked/deleted/renamed/symlink/context/registry command 任一变化必须零命令返回 `REVIEW.FINGERPRINT_CHANGED`。
- 每条命令后与最终收口都必须复核同一输入 identity；运行中受管内容变化使 result stale/GATE_BLOCK。execution/result receipt 必须携带真实 workspace digests，不能以空摘要代替当前工作树。
- 复用指纹必须消费 canonical contract 声明的全部输入；tracked、untracked、删除、symlink、
  context 或 evidence 定义的变化都不得复用旧结论。
- re-review 必须引用 initial plan，finding owner 必须来自首次 Reviewer；scope、profile 或路径集合变化时
  返回 `NEW_REVIEW_REQUIRED`，不得把旧结论迁移到新范围。
- 复用指纹的 digest 只覆盖 canonical contract 声明的 digestPayload；capturedAt 等 receipt
  字段不得进入摘要，同一输入不同采集时间必须产生相同 digest。
- digestPayload 的 serialization version、字段闭集、排序、缺席/空集合与 symlink 语义只由
  canonical agent governance contract 拥有；消费者不得另行定义影子 freshness 字段。

<a id="req-005"></a>
### REQ-005 Cursor 与 Codex 使用一个中性真相源

- `.agents/skills/` 同时是 Workflow Skill 唯一 authoring source 与两个宿主的 metadata 发现面；显式入口与自然语言 discovery 都加载同一 Skill body。Reviewer executor 以中性文件存在于 Review Skill 内。
- 生成器按 canonical contract 从中性 executor 单向生成 tracked Cursor/Codex projection，并对缺失、漂移、孤儿和手改判否；这些随仓库分发的 projection 不属于 `.qwq_output` 运行产物。
- 仓库不支持 Claude Code：不得存在 `CLAUDE.md`、`.claude/**` 或以 Claude Code 为当前 harness 的规格、门禁和命令示例。
- 真实 Cursor 与 Codex smoke 必须分别证明显式入口和自然语言 discovery 命中同一 `.agents/skills` body 与生命周期；本地 fixture、宿主标签或生成物存在不构成该证据。
- 历史 receipt 的字符串值与模型族 `claude` 不属于 harness 支持，不得因本要求改写。

<a id="req-006"></a>
### REQ-006 Review 中断给出 typed 终态与唯一恢复动作

- evidence 失败、evidence 超时、required/optional Reviewer 未完成、用户取消、owner manifest/指纹/scope 漂移必须分别落到 canonical contract 已声明的 terminal；每条 registry evidence 必须声明 `timeout_seconds`（正整数且不超过 3600），到期终止该 evidence 的独立进程组并记录 typed timeout/exit 语义，不得无限等待。实现可发射的 `REVIEW.*` code 与 contract 必须静态闭集一致，每个 code 只有一个 recovery，未知失败 fail-closed。
- Named evidence receipt 只有在文件/ref 真实存在、schema 合法、terminal=PASS、plan identity 匹配且 current fingerprint fresh 时才能进入 handoff；handoff evidence 行必须投影真实 command/exit/start-finish/source HEAD，禁止硬编码成功。
- Handoff producer、consumer/verifier 必须从 digest payload、artifact 与 named evidence receipt 重算 current freshness；同 HEAD 脏树漂移也拒绝旧 handoff，且 downstream 必须属于 canonical workflow registry。
- Review consolidator 只消费 current plan、fresh named evidence 与结构化 reviewer results：required incomplete=`GATE_BLOCK`、optional incomplete=`PR_WARN`，finding 确定性去重，旧 fingerprint result 拒绝。Board 必须按 terminal 等级与唯一恢复动作收敛，禁止把 READY、incomplete、cancelled 或 stale 包装为 PASS。

## 4. 契约引用

- canonical manifest schema：`quwoquan_ops/policies/agent_governance_contract.yaml#feature_context_manifest`
- canonical Review plan schema：`quwoquan_ops/policies/agent_governance_contract.yaml#review_plan`
- canonical typed terminal：`quwoquan_ops/policies/agent_governance_contract.yaml#terminal_codes`
- canonical tracked projection：`quwoquan_ops/policies/agent_governance_contract.yaml#tracked_projections`
- workflow/profile/evidence 路由：`.agents/skills/review/references/registry.yaml`
- 实现消费者：`quwoquan_ops/cli/feature_tree.py`、`quwoquan_ops/cli/review_dispatch.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 规则分层与上下文预算

- GIVEN 根/子树 AGENTS、Workflow Skill、角色/checklist、Feature 设计和 harness adapter 处于当前态。
- WHEN 运行 Agent 上下文治理门禁。
- THEN 根加最近子树 AGENTS 不超过 16KiB，单 Reviewer 规则上下文不超过 24KiB，默认 manifest 不超过 8KiB。
- AND 角色 reference、规范性 Cursor rule、共享 completion/interaction 跳转或 harness 规范副本出现时门禁判否并指出唯一迁移层。

<a id="gwt-002"></a>
### GWT-002 Owner manifest 精确且开发与 Review 同源

- GIVEN 一个被稳定 L1 根认领、并被 L2 DEC 适用工程根精确声明的代码路径，以及无 owner、多 owner或解析失败的路径。
- WHEN 只读控制 Skill、mutation workflow 与显式/准出 Review 分别以默认格式请求 feature context。
- THEN 唯一 owner 成功时，Skill PRE 产出的 manifest exact ref 与显式/准出 Review 复用的 ref 完全相同，均指向相同的 AppRoot/L1/L2/L3、DEC/REQ/GWT 锚点和适用 AGENTS，不含父链全文或 profiles。
- AND 无 owner、多 owner或解析失败时，只读控制 Skill 记录 typed 结果并基于当前 Git 快照继续只读，不产生 mutation 授权；mutation workflow 与显式/准出 Review 返回 typed `GATE_BLOCK`。
- AND ref 摘要漂移、内容寻址 writer 最终读取期间目录项被替换，或 Review profile 未按 `changed_paths + deliverable` 派生时 fail-closed，其中 writer 只有在已验证 fd 与返回 ref 的当前目录项仍指向同一单链接 regular inode 时才可返回。

<a id="gwt-003"></a>
### GWT-003 PRE 零 Reviewer 且 POST 至多两名

- GIVEN pageflip、纯 Python gate、无 profile 的普通实现和上述五个零 Reviewer 控制型 workflow。
- WHEN 分别生成显式 Review 的 PRE 与 POST plan。
- THEN 全部 PRE 的 reviewers/evidence 为空；pageflip POST 只有 Developer 与 UX，纯 Python gate 只有 Developer 与 Ops，无 profile 的普通实现 POST 只有 primary。
- AND 上述五个控制型 workflow 为零 Reviewer，任一仅由显式或准出入口生成的 initial Review plan 的 Reviewer 不超过两名。

<a id="gwt-004"></a>
### GWT-004 命名 Evidence、指纹与定向复审

- GIVEN 一个 initial POST plan 含重复覆盖 evidence、tracked/untracked/删除文件及两个 Reviewer。
- WHEN 生成计划、修改任一受管字节并按 finding owner 请求 re-review。
- THEN evidence 按 ID 去重且覆盖项不重复执行，任一受管字节变化都会改变指纹。
- AND re-review 只包含 finding owner，累计调用不超过 4；非法 owner、第三轮复审或 scope/profile/path 变化被明确拒绝。

<a id="gwt-005"></a>
### GWT-005 Cursor 与 Codex 发现同源且 Claude 不回潮

- GIVEN `.agents/skills` 唯一 Workflow Skill body、中性 Reviewer executor、Cursor Reviewer projection 与 Codex Reviewer projection。
- WHEN 在真实 Cursor/Codex 宿主分别执行显式入口与自然语言 discovery smoke，并运行 Reviewer projection 生成器的 `--check` 与根布局门禁。
- THEN 每个宿主的两种入口都加载同一 Skill body 和生命周期；两个 Reviewer projection 的正文与权限语义来自同一中性源，缺失、漂移、孤儿或宿主专属 Workflow Skill stub 都会判否。
- AND `CLAUDE.md`、`.claude/**` 或当前文档中的 Claude Code 支持入口回潮时门禁判否。

<a id="gwt-006"></a>
### GWT-006 Review 中断不被包装为成功

- GIVEN evidence 失败、required Reviewer 模型/额度/连接不可用、optional specialist 不可用、用户取消或指纹漂移。
- WHEN board 汇总该次评审状态。
- THEN 每种输入分别得到 canonical terminal contract 声明的 typed 等级、用户可读原因、是否允许重试与唯一恢复动作；实现发射闭集与 contract 精确相等。
- AND 任何 READY、incomplete、cancelled、owner manifest stale、evidence result stale 或 handoff stale 都不得产生整体通过结论，也不得自动无限重试。

<a id="gwt-007"></a>
### GWT-007 Evidence、Review 结果与 Handoff 只消费当前真实回执

- GIVEN 一个 POST plan、canonical named evidence receipt、结构化 reviewer results 与 handoff artifact/ref。
- WHEN plan 后任一受管工作树字节、context、registry command、review asset 或 artifact 在执行前、命令间或下游消费前变化。
- THEN 变化在首条命令前导致零命令 `REVIEW.FINGERPRINT_CHANGED`，运行中变化导致 stale/GATE_BLOCK；handoff 拒绝不存在、非 PASS、plan identity 不匹配或 freshness stale 的 evidence ref，并投影真实执行字段。
- AND 仅 current fresh 输入可被确定性 consolidation；required incomplete 为 `GATE_BLOCK`、optional incomplete 为 `PR_WARN`、finding 去重稳定，downstream 只能来自 canonical workflow registry。

## 6. 依赖

- 前置要求：[`development-workflow-governance`](../spec.md) 的目录原生与共享脏树约束。
- 上游事实：Feature Tree 目录、当前 Git 字节、`.agents/skills` metadata/body、Review registry 与中性 executor。
- 下游结果：紧凑 context manifest、Review plan、Cursor/Codex adapters 与 typed Review 终态。
- 父级设计：`DEC-002`、`DEC-003`、`DEC-004`、`DEC-005`。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 渐进上下文与轻量 Review 尚未全部绑定真实证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺绑定当前工作树字节的完整治理门、聚合 pageflip evidence，以及 Cursor/Codex 各自对显式入口与自然语言 metadata discovery 的真实宿主 smoke；在这些证据齐备前不得把规格完成当作实现完成。
- 完成判定：`GWT-001` 至 `GWT-007` 均具备职责匹配的真实 gate/local_contract；`GWT-005` 另具 Cursor 与 Codex 各自的显式/自然语言 discovery smoke，证明命中同一 Skill body 和生命周期，且上述证据绑定当前工作树字节。
