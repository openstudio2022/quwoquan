# L3 Story：工作流同轨解析 (`workflow-resolution`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：本横切工程 Story 不直接承接用户 Journey。
>
> 设计归属：[L2 DEC-006](../design.md#dec-006)、[L2 DEC-007](../design.md#dec-007)、[L2 DEC-008](../design.md#dec-008)

## 1. 用户价值

作为开发工作流调用方，我希望自然语言意图和显式 Skill 命令经同一个可审计解析器选择 canonical workflow，从而在不猜测自由文本的前提下获得一致的 Skill 身份、准备度和后继阶段。

## 2. 范围与非目标

### In Scope

- 冻结 12 个 canonical workflow、canonical command、宿主显式入口可用性、自然语言高置信规则和结构化候选输入。
- 生成不保存敏感原文的版本化 `WorkflowResolveReceipt`，并由 resolver 安全打开 repo-relative owner manifest、校验 canonical owner chain/target/scope 并重算当前 canonical `EvidenceFingerprint`。
- 在歧义、低置信、未知候选、owner manifest 缺失/非法/过期时 fail closed，并给出唯一 typed code 与 recovery。
- 以中性 host adapter 承接 Cursor 命令薄壳；宿主无法同步拦截任意自然语言时，只记录 discovery unproven，不伪造集成能力。

### Out of Scope

- 不声称任意自由文本都能确定解析，也不以本地测试证明真实 Cursor/Codex 宿主发现。
- 不复制 Review role、Human Authority role 或动态 audience 正文；只引用各自 canonical owner。
- 不执行被选择的工作流，不创建 Human checkpoint，不修改父 L2 规格与设计接线。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 闭集、同轨与保守解析

- 解析器必须从 canonical contract 读取 12 个 workflow 闭集、显式命令与自然语言高置信规则；自然语言只接受 contract rule 命中或带证据的结构化 canonical candidate。
- 同一 canonical workflow 的两种 input mode 必须产生相同 `selected_workflow`、Skill digest、readiness profile 与 canonical next segment；receipt digest 保留 input mode，因此 receipt 可以不同，并由显式 semantic identity 比较语义。
- 无唯一高置信候选时不得猜测：真正重叠与低置信返回 `ask`，未知候选优先返回 `hold`；否定、引用或元讨论中的 mutation 只允许 `ask/hold`，不得选择 commit/environment/content 等 mutation workflow。
- 结构化候选证据只接受 contract 枚举的 kind/reference 与 `sha256` digest；receipt 只保留输入 digest/长度/类别和枚举或摘要化 confidence basis，不得保存自然文本、原始 evidence、secret、email 或 PII。

<a id="req-002"></a>
### REQ-002 可审计 receipt 与 PRE 阻断

- 版本化 receipt 必须只保存输入摘要/长度/类别，不保存敏感原文，并包含摘要化候选/拒绝、Skill identity、owner manifest ref/status、canonical typed code/recovery、ambiguity terminal、readiness profile、next segment、Human interaction binding ref、canonical EvidenceFingerprint 与 `host_audit`。
- owner manifest 输入只能是 repo-relative ref 加预期 target/scope；caller 不得声明 freshness。resolver 必须拒绝 absolute/traversal/symlink/非 canonical schema/owner chain/target/scope，并用 canonical validator 重算 fresh/stale/missing。缺失或 stale 仍可保留已选 workflow，但不得进入 READY/PRE。
- terminal matrix 固定为唯一合法高置信候选且 manifest fresh 才是 `selected/PRE`，真实歧义或低置信是 `ask/terminal`，未知候选、manifest/contract/security 失败是 `hold`。`verify_receipt` 必须重算 terminal matrix、Skill digest、receipt digest 与 manifest 当前 freshness，拒绝仅重哈希的非法组合。
- readiness profile 必须由 contract 集中拥有并覆盖全部 workflow；routine workflow 不制造 Human checkpoint，dynamic audience 只保持 Human interaction binding 引用。

<a id="req-003"></a>
### REQ-003 宿主中性与证据诚实性

- `host_audit` 的 claimed host、adapter、discovery evidence ref/status 只作为非语义审计输入；它进入 receipt digest，但不得改变 workflow、Skill digest、readiness profile、next segment 或 semantic identity。
- contract 区分 `canonical_command`、`host_explicit_entry_available` 与 `automatic_only`；四个无 Skill metadata command 的自动 workflow 不虚构宿主命令。八个 Cursor command shell 必须调用版本化中性 adapter，先创建并验证 receipt，再暴露 selected Skill ref/next segment。
- CLI 必须提供 resolve、receipt verify、contract inspect 三个只读命令；argparse 缺参/未知参数与 contract/receipt 错误必须返回一个 typed JSON，stdout/stderr 策略确定且不输出 usage/traceback。
- 真实 Cursor/Codex discovery 在完成双方宿主 smoke protocol 前保持 OPEN；本地 contract/gate PASS 只能证明 resolver 字节与 fixture，不得升级为真实宿主发现 PASS。

## 4. 契约引用

- object / projection：`quwoquan_ops/policies/workflow_resolution_contract.yaml#schemas.workflow_resolve_receipt`
- error / recovery：`quwoquan_ops/policies/workflow_resolution_contract.yaml#errors`
- interaction：`quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding`
- evidence：`quwoquan_ops/policies/agent_governance_contract.yaml#evidence_fingerprint`
- review route：`.agents/skills/review/references/registry.yaml#workflows`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 显式与自然语言同轨且宿主中性

- GIVEN 同一 canonical workflow 的显式命令和唯一高置信自然语言结构化输入，以及 fresh owner manifest。
- WHEN 分别以 Cursor/Codex host label 解析并验证 receipt。
- THEN 两种 input mode 的 selected workflow、Skill digest、readiness profile、next segment 与 semantic identity 相同。
- AND receipt digest 因 input mode/input digest/host audit 可不同，host label 不改变语义 identity。
- AND continue 只路由到 continue Skill 后由 Skill 自行选择恢复分支，review 不递归自动 Review，commit resolver 不授予 external write permission。

<a id="gwt-002"></a>
### GWT-002 歧义、低置信与过期 manifest fail closed

- GIVEN continue/review/commit/environment 等规则可能重叠、没有高置信命中或 owner manifest 缺失/过期。
- WHEN resolver 处理输入。
- THEN 重叠或低置信返回 typed `ask`，unknown+legal 候选仍以 unknown precedence 返回 typed `hold`，否定/引用/meta mutation 不得被选中。
- AND nonexistent/traversal/symlink/schema/target/owner/fingerprint drift manifest 均 typed `hold`，已选 workflow 仍不得进入 PRE。
- AND 重哈希后的非法 terminal matrix、包含 secret/PII 原文的 receipt 或 stale manifest receipt 验证失败。

<a id="gwt-003"></a>
### GWT-003 CLI、宿主接线与真实证据分层

- GIVEN resolver contract、CLI、gate 和真实宿主 smoke protocol。
- WHEN 执行 focused local contract 与 gate。
- THEN CLI 对 resolve/verify/inspect 及 argparse 错误输出单一 typed JSON 且无 usage/traceback，gate 校验 workflow/Skill/Human binding/Review registry、八个 Cursor adapter shell 和四个 automatic-only policy 闭包。
- AND Cursor shell adapter integration tests 证明 receipt 先于 Skill PRE；Codex repository adapter 仅证明本地 smoke，真实 native discovery 继续由 OPEN 阻断。
- AND 只有完成真实 Cursor 与 Codex discovery smoke 后才能关闭 OPEN；本地 PASS 不作该声明。

## 6. 依赖

- 前置要求：L2 `REQ-002` 的自然语言与显式 Skill 同生命周期约束。
- 上游事实：12 个 Workflow Skill metadata、Human interaction binding、Review registry、EvidenceFingerprint contract 和当前 owner manifest。
- 下游结果：主会话后续把本 Story 接入父 L2 Story 列表、设计适用工程根与全仓门禁入口。
- 父级设计：`DEC-006`、`DEC-007`、`DEC-008`。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实 Cursor/Codex discovery smoke

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：本地测试只能证明 resolver 与 fixture，无法证明真实 Cursor/Codex 宿主对显式命令与自然语言的发现行为；在两宿主 smoke 完成前不得声明 discovery PASS。
- 完成判定：`GWT-003.t2` 在真实 Cursor 与 Codex 宿主各自完成显式/自然语言输入对 smoke，并保存可核对的 resolver receipt 与宿主发现证据。
- 依赖：可访问的真实 Cursor 与 Codex 会话宿主。
