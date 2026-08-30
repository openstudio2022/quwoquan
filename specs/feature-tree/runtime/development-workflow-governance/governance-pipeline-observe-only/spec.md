# L3 Story：治理流水线 Observe-only 准入 (`governance-pipeline-observe-only`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为治理流水线提供只读证据聚合、准入解释与运行观测契约
>
> 设计归属：父 L2 后续由主会话接线；当前实现只细化既有 Human/Objective/HOTL 单轨边界，不修改其 owner

## 1. 用户价值

作为工程交付、质量与发布运维责任人，我希望治理流水线只读聚合各层真实证据并给出保守、可解释的 observe-only 准入终态，从而能观察治理效率与等待瓶颈，同时不把本地测试、技术 Review、源码检查或调用方自报升级为 Human、生产、商用或 HOTL authority。

## 2. 范围与非目标

### In Scope

- 分层消费 workflow resolve、fingerprint-indexed owner manifest、本地 scope/release readiness、Review、Human-owned calibration readback、hosted authority、Objective、effect、Portal、hosted CI、环境/设备/UAT、Commercial/Prod/channel/outcome、handoff consumer 与 HOTL inspect 的 readback。
- 只读输出 `blocked / not_admitted / eligible_observe_only / observe_only`，按 schema、freshness、fingerprint 和独立证据 owner 进行 fail-closed 聚合。
- 定义治理运行指标的 schema 与安全维度；evaluator 只验证指标存在和 shape，不采集指标。

### Out of Scope

- 不创建 Human、hosted、activation、production、commercial、channel、outcome 或 HOTL authority；不实现 effect、发布、激活、grant、resume 或 mutation command。
- 不修改 Human、Objective、HOTL、workflow resolver、local readiness、hosted authority、Review、Makefile 或父特性节点。
- 不以本地 fixture 关闭 Human owner 定义的六类责任/四类 principal calibration、hosted live、环境/设备/UAT、商用、生产、渠道或 outcome 的外部 OPEN。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分层证据只聚合、不互相冒充

- evaluator 必须分别消费各层 exact readback；schema 无效、证据过期或 fingerprint mismatch 优先返回 `blocked`。代码存在、命名证据未执行、集成未证明与 live 外部依赖缺失必须使用不同终态和 blocker，不得统一写成 `absent`。
- 各层证据必须保持独立：machine baseline 不得替代 Human-owned calibration readback，Review `READY` 不得替代 `PASS`，且 consolidation 中出现任一 `GATE_BLOCK` finding 时必须拒绝 Review PASS；`scope_ready` 不得替代 `release_ready`。hosted code/integration 不得替代 hosted live，Portal test/build 不得替代 Portal UAT，released、published 与 outcome attained 不得互推。
- 每层由 contract 冻结唯一 producer/adapter 身份、允许的 provider kind、release eligibility、candidate/scope/fingerprint binding 与最大证据年龄。freshness 只能由 adapter 对 provider-owned timestamp 验证，不接受 `fresh=true`；bundle 保存显式 receipt ref 与 exact bytes，不保存调用方自报 truth boolean。
- canonical contract 只拥有 schema、required evidence、真实 hosted Story/service contract/adapter 实现引用与命名 evidence 身份，不拥有随运行变化的当前 PASS/absent 状态。当前状态只能从绑定 current EvidenceFingerprint 的 canonical receipt 读取。

<a id="req-002"></a>
### REQ-002 observe-only 激活独立且所有 mutation 恒为 false

- 无独立 authenticated activation provider 时，即使全部分层证据满足也最多返回 `eligible_observe_only`，并包含 `ACTIVATION_PROVIDER_UNAVAILABLE`；本地 `inspect`、调用方 receipt、精确摘要自报或本地 fixture 均不得自授 `observe_only`。
- `observe_only` 只能由注入的独立 verifier 对 authenticated、release-eligible、exact evaluation digest 与 exact evaluation bytes receipt 完成 readback 后返回；不满足时保持 `not_admitted`。
- 任一终态都必须保持 `production_ready=false`、`commercial_ready=false`、`hotl_admitted=false`、Prod/HOTL/global mutation false。S4 动态消费 Objective readback，但当前输出最大写并发不得大于 1。
- 外部 effect 只允许受控 allowlist 中的可逆非生产治理动作；`unknown` 只能 `pending` 且禁止 retry，evaluator 自身不执行 effect。

<a id="req-003"></a>
### REQ-003 Human-owned 六责任四主体 calibration 与无敏观测契约

- governance 不拥有第二套 calibration 角色 schema；它只能动态消费 Human owner 的版本化 `human_calibration_readback`。该 readback 以 `product / engineering / quality / release_operations` 四类 principal class 覆盖 `business / product / experience / quality / engineering / release_operations` 六类责任，责任映射、观察维度、三态、24 小时 freshness、最小样本和 decision-specific distinct-principal 规则均由 Human owner 定义；governance 不得复制 desired role list、静默映射或自行扩为六类 principal。
- governance 必须区分责任覆盖与 distinct authenticated principal/quorum；只有 Human readback 声明的预冻结 `independent-principal-required` 决定才校验不同 principal，routine calibration、咨询/知会与 cross-role impact 不得被自动升级为六人 checkpoint。
- 本地 fixture 只能为 `not_observed` 或结构性的 `insufficient`，machine baseline 仅证明结构代理，不是人类可理解性证据；只有 authenticated/consented/deidentified source 基于 fresh exact session bytes 派生且兼容的 Human readback 才可能为 `calibrated`。缺版本/字段、unknown model、过期、摘要漂移、shadow schema 或 machine self-claim 必须 fail closed。
- 观测 contract 必须覆盖 edit/idle/scope/release latency、cache hit、deferred age、commit freshness、hosted mismatch、resolve latency、authority wait/transfer/timeout、review incomplete、handoff stale、objective pending/revoke；维度不得包含 prompt、message、raw payload、actor/user identity 或 PII。

## 4. 契约引用

- 本 Story canonical contract：`quwoquan_ops/policies/governance_pipeline_admission_contract.yaml`
- Workflow resolve：`quwoquan_ops/policies/workflow_resolution_contract.yaml`
- Local readiness：`quwoquan_ops/policies/local_readiness_contract.yaml`
- Human machine baseline 与 authority：`quwoquan_ops/policies/evals/human_agent_delivery_interaction_v1.yaml`、`quwoquan_ops/policies/human_agent_delivery_contract.yaml`
- Objective S4：`quwoquan_ops/policies/objective_execution_contract.yaml#admission.readback_contract`
- HOTL inspect：`quwoquan_ops/policies/hotl_admission_contract.yaml`
- Hosted authority：[`hosted-human-authority`](../../../platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md)、`quwoquan_service/control-plane/platform-ops/contracts/platform_ops/human_authority/operations.yaml`、`quwoquan_ops/cli/lib/hosted_authority/`；contract/adapter/service/Portal code 已存在，正式 hosted integration/live provider 仍须独立证据。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 证据冒充、过期与身份漂移 fail-closed

- GIVEN 每一层 evidence 都使用独立 status/result/provider/freshness/fingerprint readback。
- WHEN 任一 schema 无效、过期、fingerprint mismatch、required code 证据缺失，或以 READY 冒充 Review PASS、scope_ready 冒充 release_ready、machine baseline 冒充 calibration、hosted code 冒充 live、released 冒充 published/outcome。
- THEN 结果按 canonical precedence 确定性返回 blocked 或 not_admitted，并包含单义 typed blocker。
- AND 任一结果都不产生 authority、production/commercial/HOTL ready 声称或 mutation。

<a id="gwt-002"></a>
### GWT-002 Human calibration 与 activation 不能自我声明

- GIVEN Human owner 的六类责任/四类 principal readback 与所有分层证据分别可满足，且本地调用方可提交任意 activation receipt。
- WHEN 缺任一 principal class、责任或观察维度，样本/authentication/consent/deidentification/freshness/SoD 不足，使用 local fixture/machine baseline，readback 版本不兼容，或未注入独立 authenticated verifier 时 inspect。
- THEN calibration 保持 `not_observed`、`insufficient` 或 Human-owned typed incompatibility/blocker；governance 不建立 shadow role schema。全证据满足但 activation provider 缺失时最多 eligible_observe_only/observe_only mode，包含 `ACTIVATION_PROVIDER_UNAVAILABLE`。
- AND 只有独立 verifier exact readback 成功才返回 observe_only；本地 receipt 自报永不提升，所有 mutation 与 HOTL admitted 恒为 false。

<a id="gwt-003"></a>
### GWT-003 CLI、指标 shape 与当前仓终态诚实

- GIVEN canonical contract、只读 CLI、当前仓真实 code、明确命名的 owner/workflow/readiness/Review/code/integration/Portal receipt 与尚未完成的外部依赖。
- WHEN gate 不带 bundle 仅执行 evaluator safety self-check，或显式从受限 `.qwq_output/env/repo/runs/governance-pipeline/**` evidence bundle 读取 owner receipt refs、冻结 exact bytes 并验证 current canonical EvidenceFingerprint；receipt 缺失、伪造、过期、跨 fingerprint、仅文件存在或自报 boolean。
- THEN typed JSON 不输出 traceback，只有 exact current receipt 能投影对应层 PASS；Review `READY`、Portal pass、代码存在和 activation self-assert 均不得冒充下游事实。输出包含首个优先 blocker 与完整 blocker 集。
- AND gate 对当前仓输出 `not_admitted/manual` 的预期终态；成功退出只表示 expected fail-closed evaluator 有效，不是 admission PASS，production/commercial/HOTL claims 恒为 false。

## 6. 依赖

- Human 与真实 calibration：`human-agent-delivery-interaction` 的 Human provider/calibration OPEN。
- Hosted authority：`hosted-human-authority` 的 contract/provider/consumer、identity/infrastructure/live UAT OPEN。
- Objective/HOTL：只动态消费现有 owner readback，不复制其 wire 或升级其 authority。
- 父节点与 Makefile/gate_repo 接线由主会话后续完成，不在本 Story 当前授权范围内。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Human 六责任四主体真实 calibration 尚未观察

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：角色模型冲突已由 Human owner 裁定为四类 principal class 覆盖六类责任，不再等待 governance 选择或扩为六主体；当前仍缺 Human contract/readback 对该版本、映射、观察维度、三态与 fail-closed 语义的实现，也缺真实 participant observation，因此不得宣称 calibrated。
- 完成判定：Human owner 的 contract/local_contract 先实现兼容 readback 并绑定 `GWT-002.t1`、`GWT-002.t2` 的 schema/mapping/不兼容负例；随后 external `user_acceptance` 以四类 principal class 的真实参与者样本、至少四个 qualifying role-session 覆盖六类责任及全部观察维度。governance 只消费该版本的 authenticated/consented/deidentified fresh readback，不持有 desired role list 或映射事实。
- 依赖：Human owner contract/version follow-up、真实参与者与代表任务、Human provider、合规观测与去标识流程。

<a id="open-002"></a>
### OPEN-002 Hosted authority 与 activation provider 尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 hosted authority service contract、adapter、Go service 与 Portal code 绑定同一 candidate 的 canonical integration/live evidence，独立 authenticated activation verifier/provider 也未闭合；本地 inspect 只能 not_admitted 或 eligibility。
- 完成判定：`GWT-001.t1`、`GWT-002.t1`、`GWT-002.t2` 由 current-fingerprint hosted integration evidence、authenticated exact-byte live readback 与独立 activation receipt consumer 绑定。
- 依赖：`hosted-human-authority/OPEN-002` 与新版本 activation provider/consumer。

<a id="open-003"></a>
### OPEN-003 环境、商用、生产、渠道与 outcome 外部证据未闭合

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前源码/local contract/gate 不证明 Portal live UAT、hosted clean-SHA、环境/设备/UAT、Commercial、Prod、channel 或 outcome；这些层不能由上游状态推导。
- 完成判定：`GWT-003.t1`、`GWT-003.t2` 由各自 owner 的同一 immutable candidate exact readback 独立绑定，且 released/published/outcome 保持分层事实。
- 依赖：Portal/hosted CI、环境与真实设备、Human Commercial/Prod/channel/outcome authority。
