# L3 Story：目标与增量执行 (`objective-execution`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为全部交付 Objective 与 Increment 提供可恢复的状态执行协议
>
> 设计归属：[L2 DEC-009](../design.md#dec-009)

## 1. 用户价值

作为工程交付负责人或受授权的自动执行调用方，我希望 Objective 与 Increment 只由可审计、可重放的状态事件推进，并且副作用只有在真实授权和精确 readback 都成立后才提交状态，从而在并发、崩溃和外部结果未知时仍能恢复到可信终态而不重复执行。

## 2. 范围与非目标

### In Scope

- Objective 与 Increment 的闭集状态、append-only TransitionEvent、deterministic reducer、CAS 与 readback。
- authenticated Human Authority readback 的限界消费、effect 幂等执行、exact readback 与两事件提交顺序。
- 从 canonical branch policy 动态推导 S4 准入，并在当前策略下维持 `not_admitted`、单 writer 与竞争恢复。

### Out of Scope

- Human Authority 的身份、角色、DecisionUnit、授权派生与人类交互语义；这些属于 [`human-agent-delivery-interaction`](../human-agent-delivery-interaction/spec.md)。
- 用本地 JSON、授权卡投影、测试 provider 或状态 journal 冒充 authenticated human identity authority。
- 在未取得外部 provider 与真实 effect readback 证据前宣称 headless、商用或生产执行闭环。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 TransitionEvent 是 Objective 与 Increment 的唯一执行状态 authority

- Objective 与 Increment 的当前状态必须只由 append-only TransitionEvent journal 经版本化 deterministic reducer 重建；本地 journal 是 execution-state authority，不是 human identity authority。
- 每次 append 必须以 expected head 与 generation 执行 CAS，写入完整 hash chain，并在 atomic commit 后由 readback 返回 reduced state、head、generation、最后 authority reference 与最后 effect readback。
- 已完成私有 staging 写入与 file fsync、再以同目录 exclusive no-replace 原子发布并 fsync events directory 的完整、连续且摘要与 identity 可验证的 event chain 是 crash recovery authority；未发布 staging 永不构成 authority。snapshot/head 是可重建派生物。event 发布后 snapshot/head 缺席、落后或仅部分 materialize 属于合法 crash state，只能由显式 recovery 或下一次 append 在 exclusive writer lease 下确定性重建；只读 readback 不得无 lease 写入，并以 canonical recovery-required terminal 区分该状态。
- Journal 信任边界固定为当前 trusted effective UID：canonical root、kind、subject、events 全部是 `0700` 目录，authoritative event、writer lock、staging 与 derived artifact 全部是 `0600` regular single-link file；任一 ancestor/component symlink（含 broken symlink）、非可信 owner、group/world writable、错误 mode/type/link-count 或 inode identity 漂移均 fail closed，不能解释为 absent。首次创建的每一级目录必须显式设为 `0700`，并依次 fsync parent 与新目录。
- Writer lease 只能由 `writer_lease` 返回且绑定 canonical root 与 subject inode 的内部 capability 表示；公开 append/recover 自行竞争 lease，任何 caller boolean 均不能绕过。capability 在每次 under-lease read/mutation 前验证 retained dirfd/inode identity，subject rename/recreate 或 lock identity split 必须零写入失败。
- 只有 event 缺口、event digest/hash chain、subject identity、reducer version 或受信存储节点漂移才判为 journal tamper；event I/O/平台 exclusive-publish primitive 故障与合法派生物待恢复使用各自 canonical terminal，readback 继续区分 `present`、`absent` 与 `failed`，仅真实 `ENOENT` 可表示 absent。

<a id="req-002"></a>
### REQ-002 Executor 只消费 authenticated authority 并在 effect readback 后迁移状态

- Executor 必须通过注入 verifier 验证 authority provider 对 exact bytes 的 authenticated receipt readback，并检查 actor、Human Authority role、目标 scope、expiry、EvidenceFingerprint、decision kind 与 action；生产默认没有 provider 时返回 typed blocker 且零 mutation。
- Human `AuthorizationGrant` projection 保持 `authenticated=false`、`executable=false`，不得触发 journal 或 effect；`provider_kind=test` 只可用于 local contract，报告不得作为 release evidence。
- 在任何 effect invoke 之前，executor 必须按 canonical contract 的 Objective/Increment 版本化 transition graph 校验 `action / from_state / to_state`；terminal 只能通过图中显式 reopen/restart 边离开，非法跳跃返回 canonical typed blocker 且零 effect、零 transition。
- 有效决定先幂等追加 `human_decision_recorded`，并冻结完整 command envelope 的 canonical digest 与非空 `effect_id`；envelope 覆盖 subject/target/source/action/payload/authority scope/evidence/decision/provider/receipt/effect key 等完整 identity。恢复请求必须 exact match 已持久化 envelope，任一 mismatch 返回专用 typed conflict，零 effect、零 transition。
- effect 只能以已持久化的非空 `effect_id` 与 idempotency key 执行 exact readback；仅 `applied` 且 identity exact match 才追加状态 TransitionEvent。结果 unknown 或 effect identity 漂移时不得重试副作用，状态保持 pending readback。

<a id="req-003"></a>
### REQ-003 S4 准入由 branch policy 动态推导并保持单写者

- S4 admission 必须直接消费 `quwoquan_ops/policies/branch_policy.yaml`；Objective contract 的 admission/readback contract 是 S4 wire、status/reason/terminal、写并发、临时分支、branch-policy digest 及 blocked 动态 detail 约束的唯一 owner，其他 contract 不得复制这些字段和值。
- 当前只允许 `dev1.0` 与 `main`、无临时分支前缀且唯一 promotion 边为 `dev1.0 → main` 时，S4 必须返回 canonical `not_admitted` readback、`write_concurrency=1` 与 `temporary_branch_allowed=false`；branch policy 读取或解析失败必须返回同一 owner contract 定义的 canonical blocked readback，并保留合法动态 detail。
- writer lease 与 CAS 必须保证并发竞争恰好一个 winner；loser 在重新 readback 前不得执行 effect 或追加 event。只读 query 可并行，状态、Git、环境与外部系统 mutation 维持单轨。

## 4. 契约引用

- Objective execution machine contract：`quwoquan_ops/policies/objective_execution_contract.yaml`
- Human Authority machine contract：`quwoquan_ops/policies/human_agent_delivery_contract.yaml`
- branch policy：`quwoquan_ops/policies/branch_policy.yaml`
- command / readback：`append_transition`、`execute_authorized_effect`、`read_execution_state`、`inspect_admission`
- event：`human_decision_recorded`、`state_transition_committed`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Journal、CAS、replay 与 readback 保持单轨

- GIVEN 一个 Objective 或 Increment 已有可验证 head，或 journal 尚不存在。
- WHEN 调用方以 expected head/generation 追加事件并执行 replay/readback，或在 staging create/partial write/file fsync、exclusive publish、events-directory fsync、snapshot materialize、head materialize 后 crash 并重启，或遇并发 stale writer、路径替换、事件缺口与字节篡改。
- THEN 完整可验证且已 exclusive-publish 的 event chain 始终由 deterministic reducer 得到唯一 reduced state；派生物完整时返回 `present` 或 `absent`、当前 head/generation、最后 authority reference 与最后 effect readback，未发布 staging 永不进入 replay。
- AND event 已发布但 snapshot/head 缺席、落后或部分 materialize 时，只读 readback 零写并返回 canonical recovery-required terminal；显式 recovery 或下一 append 仅凭绑定 canonical root/subject inode 的内部 lease capability 从 event chain 重建并恢复可信 `present`，公开 API 不提供 caller-forgeable bypass。
- AND 每个创建目录均以 `0700` 完成 parent/new-directory fsync，全部文件以 `0600` 建立；staging 与派生物 failpoint 重启只呈现旧完整 chain 或新完整 chain/recovery-required，且同一 expected head 的竞争只有一个 CAS winner，stale writer 零新增 event。
- AND symlink/broken symlink、非 regular/hardlinked/错误权限或 owner 节点、subject rename/recreate、event 缺口、event digest/hash chain、identity/reducer version 漂移返回 canonical typed failure且零路径逃逸；I/O 或不支持 exclusive atomic publish 返回独立 failed terminal，均不得被解释为 `absent` 或可信状态。

<a id="gwt-002"></a>
### GWT-002 Authority 与 effect 使用两事件恢复协议

- GIVEN 一个待执行 command 带 Human Authority receipt reference、目标 scope、EvidenceFingerprint、decision kind、action 与 effect idempotency key。
- WHEN executor 验证 authority exact-byte readback，先记录决定，再执行 effect 并核对 exact effect readback。
- THEN absent、expired、scope/fingerprint/role/decision/action 无效、未认证或 projection-only authority，以及版本图不允许的 action/from/to，全部在 effect invoke 前阻断；生产无 provider 返回 typed blocker，以上路径均零 effect、零状态 transition。
- AND `human_decision_recorded` 冻结完整 command envelope digest 与非空 effect ID；pending 恢复只接受 exact identity，subject/target/action/payload/authority/evidence/provider/receipt/effect 任一漂移返回专用 conflict，零 effect、零 transition。
- AND exact effect readback 只使用已持久化 effect ID；test authority 仅在 `provider_kind=test`、验证通过且 readback identity exact `applied` 时追加状态 TransitionEvent，并标记证据不可用于 release。unknown/identity mismatch 保持 pending readback 且不重试，重复 idempotency key 不产生第二次 effect 或第二组事件。

<a id="gwt-003"></a>
### GWT-003 S4 not admitted 与单 writer 竞争恢复

- GIVEN canonical branch policy 只允许 `dev1.0` 与 `main`、无临时分支前缀且唯一 promotion edge 为 `dev1.0 → main`。
- WHEN 两个 writer 竞争同一 Objective/Increment，或调用方尝试以临时分支扩大并发。
- THEN admission 依据 Objective-owned canonical readback contract 动态返回 `not_admitted`、`write_concurrency=1`、`temporary_branch_allowed=false`，而只读 readback 仍可并行。
- AND writer lease/CAS 只允许一个 winner 执行 effect 和追加 event；loser 零 effect、零 event，并在 readback 后保持 queued/not admitted。
- AND branch policy 漂移或解析失败返回 typed blocker，不回退到 Human-Agent contract 中的静态副本。

## 6. 依赖

- 前置要求：[`human-agent-delivery-interaction`](../human-agent-delivery-interaction/spec.md) 的 Human Authority、DecisionUnit 与授权语义，以及本层 `DEC-009`。
- 上游事实：authenticated authority provider readback、EvidenceFingerprint、branch policy 与 effect adapter readback。
- 下游结果：Objective/Increment reduced state、typed command terminal、可恢复 journal 与 S4 admission inspect。
- 父级设计：`DEC-009`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实 authority/effect provider 与共享 durable lease 闭环尚未接入

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：本地 journal、reducer、test verifier、`fcntl` writer lease 与 effect adapter 只能证明单机 execution-state 协议，尚无真实 identity provider、authenticated actor/role authority、隔离的 durable provider、跨进程/跨主机共享 durable writer lease、headless executor 或外部 effect exact readback；不得把测试证据当作 release evidence。
- 完成判定：`GWT-002.t1`、`GWT-002.t2`、`GWT-002.t3` 与 `GWT-003.t2` 均由真实 authenticated provider、独立 authority readback、受限 executor、外部 effect readback及共享 durable lease 竞争/恢复的职责匹配集成证据直接绑定。
- 依赖：[`human-agent-delivery-interaction/OPEN-001`](../human-agent-delivery-interaction/spec.md#open-001)、真实身份/authority provider、外部 effect provider、共享 durable lease provider 与 release 证据通道。

<a id="open-002"></a>
### OPEN-002 S4 write concurrency 2 尚未获得准入策略

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺 S4 `write_concurrency=2` 的 branch lifecycle 实现与并发集成验收证据。canonical branch policy 当前不允许临时分支，S4 因而正确维持 `not_admitted` 与 `write_concurrency=1`；未来的双 writer 能力需要先冻结可清理分支生命周期、隔离边界与 promotion/回收规则，不能用本地配置绕过现行单写者策略。
- 完成判定：`GWT-003.t1`、`GWT-003.t2`、`GWT-003.t3`、`GWT-003.t4`、`GWT-003.t5` 在新的 canonical branch policy 与并发集成证据下证明两个合法 writer 隔离执行、竞争回收且无遗留分支；在此之前不阻断当前 concurrency1 实现。
- 依赖：经批准的 branch policy 变更、临时分支生命周期 owner、并发隔离与回收 gate。
