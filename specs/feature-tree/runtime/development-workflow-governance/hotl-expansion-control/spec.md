# L3 Story：HOTL 扩展控制 (`hotl-expansion-control`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为全部交付阶段提供可审计的 Human-on-the-loop 扩展准入边界
>
> 设计归属：[L2 DEC-010](../design.md#dec-010)

## 1. 用户价值

作为工程交付、质量、风险与发布责任人，我希望系统只在真实人工等待瓶颈、职责与商业 authority、checkpoint 减量收益和紧急控制均已被独立证明后，才允许 Human-on-the-loop 扩大自动执行范围，从而在减少人工等待时仍保留不可代签决定、可立即止损和可审计恢复。

## 2. 范围与非目标

### In Scope

- S6 的 HOTL applicability、固定 cohort 人工等待瓶颈证明、checkpoint delta、控制 proof、capability admission 与 fallback。
- R0/R1 的只读可评估性，以及 R2-R4 的硬阻断；首版只读 inspect 只产生 `blocked / not_admitted / eligible_for_activation`，contract 保留 `admitted` 作为未来版本目标状态。
- checkpoint 减量、resume、human override、disconnect/audit/ACK timeout，以及 `pause / deny / abort / revoke` 的 exact command ACK 与独立 effect readback。

### Out of Scope

- Human role、DecisionUnit 与 authority 语义；其唯一 owner 是 [`human-agent-delivery-interaction`](../human-agent-delivery-interaction/spec.md)。
- Objective/Increment 状态、effect、S4 admission 与动态写并发；其唯一 owner 是 [`objective-execution`](../objective-execution/spec.md)。
- 生产、渠道、outcome 与具体业务事实；它们仍由所属 Story 拥有，本 Story 只消费 readback，不复制事实。
- `routine_execution` 自动准入、activation/grant/resume mutation command，或将 local test provider 当作 release evidence。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 风险、authority、cohort 与 checkpoint 准入 fail-closed

- R0/R1 只允许进入只读评估，R2-R4 必须保持 `blocked / not_admitted`；authority decision kind 必须属于 Human contract 闭集，首版 allowlist 仅接受 `delivery_authorization`，`routine_execution` 只能作为未来候选且不得充当 authority。
- problem acceptance、product scope、experience direction、solution risk、delivery authorization、quality/UAT、integration、artifact、nonproduction、commercial readiness、production campaign、channel publication、outcome acceptance 与 knowledge landing 决定不可由 checkpoint removal 移除。
- authority 必须来自 authenticated、非 projection/test、可发布的 provider；role responsibility 与职责分离必须闭合，真实 human calibration 必须为 observed。
- 固定 cohort 必须非零、stable id 不漂移。cohort member id 与控制 proof id 在重复检查、计数、排序和 digest 前必须先归一为 NFC，归一后冲突按 contract error fail-closed。人工等待只从 durable `decision_requested / decision_recorded` 计算，不接受 runner queue 或 job started 时间。选择 query、瓶颈规则、contract v1 的 9000 basis points coverage 门槛均须预冻结。
- checkpoint delta 必须已解析且 reduction 不含不可移除决定；resume 必须由 authenticated exact Human decision readback 证明新的决定。v1 尚无该 readback/provider，因此 `resume_requested=true` 无论是否携带 decision ID 都必须保持 `RESUME_REQUIRES_NEW_HUMAN_DECISION`，ID 只作为不受信审计字段。人类 override 永远优先。

<a id="req-002"></a>
### REQ-002 控制 proof 必须由 ACK 与独立 effect readback 共同成立

- `pause / deny / abort / revoke` 每个 action 都必须同时有 exact command ACK 与独立 effect readback，两者的 status、subject、scope 与 action identity 必须一致，只提供 ACK 不算生效。所有 closed readback 的 `failed` 必须返回专用 `*_READBACK_FAILED` blocker，不得折叠为只表示 `None/absent` 的 missing/unavailable。present ACK 非 exact、present effect 非 applied、present effect 非 independent 必须分别返回单义 blocker，组合问题必须同时报告且顺序稳定。
- disconnect、audit failure 或 ACK timeout 任一出现时 fail-closed；revoke 后必须证明零新动作，不能仅记录命令已发出。
- capability 请求的写并发不得超过动态调用 Objective execution `inspect_admission()` 得到的 S4 值。
- HOTL `contract` loader 只严格校验 Objective source reference 与本地 consumption constraints，不加载 Objective descriptor。单次 `inspect` 才动态加载并校验 Objective-owned admission/readback contract 的 exact wire 与 status/value 一致性。HOTL contract 不拥有或复制 S4 字段列表、reason、terminal、branch 列表或静态数值。
- 首次 S4 provider/descriptor/validation 失败必须单义返回 Objective emergency/owner-defined blocked S4 fallback，provider 只调用一次且不得以第二次结果掩盖首次失败。已规范校验的 `status=blocked` readback 必须保留该 readback，并立即返回 Objective admission 专用 typed blocked。

<a id="req-003"></a>
### REQ-003 evaluator 只读且 activation 独立绑定当前评估

- evaluator 永远只读，并稳定返回 deterministic JSON、canonical evaluation digest 与 EvidenceFingerprint ref；输入集合按 stable id 排序，调用方顺序不得改变 digest 或 blocker 优先级。
- 首版当前前提必须返回 `not_admitted`、`allowed_mode=manual`、`checkpoint_reduction_allowed=false`、`max_write_concurrency=1`、`grant_executable=false`、`mutation_allowed=false`，并显式给出 authority、cohort、control、commercial、checkpoint 与 write expansion 未闭合原因。
- 即使所有评估事实满足，首版也只能到 `eligible_for_activation`、`allowed_mode=observe_only`；首版没有 activation verifier/provider，任何调用方提交的 receipt 及其中 authenticated/exact/release 布尔值都只是未受信审计输入，必须以 `ACTIVATION_PROVIDER_UNAVAILABLE` 返回 `not_admitted/manual`，永远不能读回 `admitted` 或 executable。未来 authenticated consumer 必须引入新的 contract/version/implementation。
- 所有 `blocked / not_admitted` 结果只从 canonical `current_fallback` 取得 manual、禁止 checkpoint reduction、最大写并发 1、grant 不可执行和零 mutation。动态 S4 仅作为证据与 requested concurrency 门，不得抬高结果并发。Objective canonical contract 无法加载时，HOTL 只能调用 Objective owner 模块内不依赖 YAML 的 emergency blocked S4 helper，且 HOTL 不得复制 S4 字段或 wire/value。
- 首版 CLI 只提供 `contract` 和 `inspect --input <file|->`，不提供 activate、grant 或 resume mutation command。真正的 JSON、I/O 与 inspection input/schema 问题使用 `INPUT_CONTRACT_INVALID / HOTL.CONTRACT_INVALID` 并投影 canonical fallback；S4 provider/descriptor/validation 失败或规范 S4 直接返回 blocked，与 EvidenceFingerprint canonical serialization/digest/ref 依赖异常分别在公开 inspect 边界单义返回 `OBJECTIVE_ADMISSION_BLOCKED / HOTL.OBJECTIVE_ADMISSION_BLOCKED` 和 `EVALUATION_IDENTITY_FAILED / HOTL.EVALUATION_IDENTITY_FAILED` typed blocked，保留首次 detail、已取得或 owner-owned S4 readback，且 CLI 原样输出、退出 2、不抛 traceback。HOTL canonical contract 自身加载失败必须返回独立最小 contract terminal `CANONICAL_CONTRACT_INVALID / HOTL.CANONICAL_CONTRACT_INVALID`，不得伪造 status、mode、并发、grant、mutation 或 S4 admission facts。

## 4. 契约引用

- HOTL admission machine contract：`quwoquan_ops/policies/hotl_admission_contract.yaml`
- Human Authority：`quwoquan_ops/policies/human_agent_delivery_contract.yaml`
- Objective execution 与动态 S4：`quwoquan_ops/policies/objective_execution_contract.yaml#commands.inspect_admission`
- EvidenceFingerprint：`quwoquan_ops/policies/agent_governance_contract.yaml#evidence_fingerprint`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 当前 readback 保持 manual、单写者与零 mutation

- GIVEN R0/R1 请求缺真实 authority provider、固定 cohort human calibration、四类控制 readback、商用 authority 与已解析 checkpoint policy，且动态 S4 为 not admitted/write concurrency 1。
- WHEN 调用方以合法输入执行只读 inspect。
- THEN 结果确定性返回 not_admitted、manual、禁止 checkpoint reduction、最大写并发 1、grant 不可执行且零 mutation，并包含六类当前 blocker。
- AND R2-R4、projection/test/expired authority、SoD 失败、cohort/coverage/query/threshold/wait source 漂移、不可移除 checkpoint、控制 proof 缺失/identity 漂移、disconnect/audit/timeout、v1 resume 携带任意 decision ID 或请求并发超 S4 均 fail-closed；S4 readback schema/value 漂移与首次 provider 失败返回 Objective admission 专用 typed blocked，三个 EvidenceFingerprint 身份依赖任一失败返回 evaluation identity 专用 typed blocked，二者都不冒充输入无效，且 S4 provider 在一轮 inspect 中最多调用一次。

<a id="gwt-002"></a>
### GWT-002 控制 ACK、effect 与撤销终态可独立审计

- GIVEN pause、deny、abort、revoke 四个 action 都声明 command identity、subject、scope 与预期 effect。
- WHEN evaluator 分别核对 exact ACK、独立 effect readback、连接、审计、timeout、override、resume 与 revoke 后活动。
- THEN 任一 action 缺 ACK、ACK 无 effect、status/subject/scope/action identity 漂移都不算控制生效，且 failed、absent/missing 与 present-but-negative readback 返回各自单义 typed blocker。
- AND disconnect、audit failure、ACK timeout 或 revoke 后仍有新动作时 fail-closed，human override 优先且 resume 必须绑定新 Human decision。

<a id="gwt-003"></a>
### GWT-003 只读 eligibility 与独立 activation 不互相冒充

- GIVEN R0/R1 的 `delivery_authorization` authority、职责、固定 cohort、coverage、human calibration、checkpoint、四类控制、commercial readback 与动态 S4 全部满足。
- WHEN evaluator 分别在无 activation receipt 和调用方提交任意自称 authenticated/exact/release-eligible receipt 时 inspect。
- THEN 无 receipt 时只返回 eligible_for_activation/observe_only，且 grant 不可执行、禁止 checkpoint reduction、最大写并发 1、activation_required=true、零 mutation。
- AND 任意非空 receipt 都因首版 activation provider 不可用而返回 not_admitted/manual，精确伪造 digest 与全部真布尔值也不能 admitted；输入列表换序不改变 digest 与 blocker 顺序，未来 admitted 读取需要新的 contract/version/implementation。

## 6. 依赖

- Human authority 外部依赖：[`OPEN-001`](../human-agent-delivery-interaction/spec.md#open-001)、[`OPEN-002`](../human-agent-delivery-interaction/spec.md#open-002)、[`OPEN-003`](../human-agent-delivery-interaction/spec.md#open-003)。
- Objective execution 外部依赖：[`OPEN-001`](../objective-execution/spec.md#open-001)、[`OPEN-002`](../objective-execution/spec.md#open-002)。
- Production/gray release 外部依赖：[`gray-release-to-prod OPEN-003`](../../deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#open-003)、[`OPEN-004`](../../deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#open-004)、[`OPEN-005`](../../deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#open-005)。
- 父级设计：`DEC-010`。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实固定 cohort 与 human calibration 尚未观察

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：本地样本只能验证 schema、排序和阈值；尚无预冻结 query/阈值下的非零固定 cohort、durable 人工决定等待与真实角色 calibration，不得宣称瓶颈或 coverage 已闭合。
- 完成判定：`GWT-001.t1`、`GWT-001.t2` 与 `GWT-003.t1` 由真实 cohort 和去标识 human observation 证据直接绑定。
- 依赖：`human-agent-delivery-interaction/OPEN-002`、durable decision events 与真实角色参与者。

<a id="open-002"></a>
### OPEN-002 authenticated 控制 provider 与控制演练尚未闭合

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚无 production-grade pause/deny/abort/revoke command ACK、独立 effect readback、disconnect/audit/timeout 与 revoke 后零动作演练；local test provider 不可作为 release evidence。
- 完成判定：`GWT-002.t1`、`GWT-002.t2` 由 authenticated provider 的故障注入与 exact readback 直接绑定。
- 依赖：`human-agent-delivery-interaction/OPEN-001`、`objective-execution/OPEN-001` 与 hosted control authority。

<a id="open-003"></a>
### OPEN-003 checkpoint 实验与 authenticated activation provider 尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚无对不可移除决定保持零删除的真实 checkpoint delta 实验，也无 authenticated exact Human decision readback/provider 或独立 authenticated activation verifier/provider；当前 v1 的任意 resume decision ID 都不受信，inspect 只能产生 not_admitted 或 eligibility，调用方 receipt 永远不授予执行权。
- 完成判定：`GWT-003.t1`、`GWT-003.t2` 的 checkpoint 实验闭合，且 Human decision 与 activation authority 分别通过新的 contract/version/implementation 提供 authenticated exact-byte readback。
- 依赖：经批准的 checkpoint policy、外部 Human decision/activation authority、新版本 consumer 与 Objective execution 动态 readback。

<a id="open-004"></a>
### OPEN-004 S6 release impact 仍为 blocked

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Human/commercial authority、production control drill 与 gray release hosted facts 尚未闭合；源码和 local contract PASS 只证明 fail-closed evaluator，不证明 S6 admitted 或 release-ready。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 的外部 evidence 全部绑定当前 exact candidate，且 gray release `OPEN-003/004/005` 已满足各自完成判定。
- 依赖：本 Story `OPEN-001/002/003` 及 gray release `OPEN-003/004/005`。
