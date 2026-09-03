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
- 从 canonical branch policy 动态推导 S4 准入：策略未声明完整长期 lane 生命周期时维持 `not_admitted` 单 writer，声明后返回 `admitted` 并允许最多六个不同 lane writer；同一 lane 与共享 mutation 始终保持单 writer 和竞争恢复。

### Out of Scope

- Human Authority 的身份、角色、DecisionUnit、授权派生与人类交互语义；这些属于 [`human-agent-delivery-interaction`](../human-agent-delivery-interaction/spec.md)。
- 用本地 JSON、授权卡投影、测试 provider 或状态 journal 冒充 authenticated human identity authority。
- 在未取得外部 provider 与真实 effect readback 证据前宣称 headless、商用或生产执行闭环。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 TransitionEvent 是 Objective 与 Increment 的唯一执行状态 authority

- Objective 与 Increment 的当前状态必须只由 append-only TransitionEvent journal 经版本化 deterministic reducer 重建；本地 journal 是 execution-state authority，不是 human identity authority。
- 每次 append 必须以 expected head 与 generation 执行 CAS，写入完整 hash chain，并在 atomic commit 后由 readback 返回 reduced state、head、generation、最后 authority reference 与最后 effect readback。
- 平台原语只允许 retained parent dirfd 下的同目录 descriptor-relative rename：Darwin event create-once 使用 `renameatx_np(RENAME_EXCL)`，Linux 使用 `renameat2(RENAME_NOREPLACE)`；snapshot/head 已存在时分别使用 Darwin `RENAME_SWAP` 或 Linux `RENAME_EXCHANGE` 交换后删除承载旧内容的 staging，不存在时使用对应 no-replace 原语。其他平台、缺失 libc symbol/syscall、未知 Linux 架构或不支持所需 flags 一律 typed fail-closed；不得回退到 `os.replace` 或任何可覆盖 authoritative event 的模糊 rename。
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
### REQ-003 S4 准入由 branch policy 动态推导并约束写并发

- S4 admission 必须直接消费 `quwoquan_ops/policies/branch_policy.yaml`；Objective contract 的 admission/readback contract 是 S4 wire、status/reason/terminal、写并发、长期 lane 许可、branch-policy digest 及 blocked 动态 detail 约束的唯一 owner，其他 contract 不得复制这些字段和值。
- branch policy 未声明 writer 分支前缀或未声明完整长期 lane 生命周期（`branch_per_writer` 隔离、只经声明 PR 边晋级、integration/abort 后 mandatory fast-forward resync、worktree retained、并发证据必需）时，S4 必须返回 canonical `not_admitted` readback、`write_concurrency=1` 与 `persistent_lane_allowed=false`；生命周期齐备（当前为六条固定 `lane/*`、`lane/* → dev1.0` 晋级边、retained worktree 与 mandatory resync）时，S4 返回 canonical `admitted` readback、`write_concurrency=6` 与 `persistent_lane_allowed=true`。六车道由用户裁决立即开放，不经过渐进扩容；启用后观察只补证据，不反向阻断已裁决准入。
- branch policy 读取或解析失败必须返回同一 owner contract 定义的 canonical `blocked` readback、`write_concurrency=0` 与 `persistent_lane_allowed=false`，并保留合法动态 detail。
- 无论 admission 处于何态，writer lease 与 CAS 必须保证同一 subject 的并发竞争恰好一个 winner；同一 lane 同一时刻最多一个 writer，不同 lane 的 Git branch mutation 可在准入上限内并行。只读 query 可并行；共享环境、设备、codegen、package、同一状态、同一 Git ref 与外部系统 mutation 维持单 writer。

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
- AND Darwin 与 Linux 分别以 `RENAME_EXCL` / `RENAME_NOREPLACE` 保证 event create-once；派生物替换以 `RENAME_SWAP` / `RENAME_EXCHANGE` 保留旧目标到 staging 后再 unlink，原语或架构不可用以及其他平台均 typed fail-closed，绝不允许覆盖式 fallback。
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
### GWT-003 S4 持久 lane 准入与 writer 竞争恢复

- GIVEN canonical branch policy 处于两态之一：未声明 writer 前缀或完整持久 lane 生命周期，或已声明六条固定 lane、`lane/* → dev1.0` 晋级边、retained worktree、integration/abort 后 mandatory fast-forward resync 与并发证据。
- WHEN 最多六个不同 lane writer 并发执行，同一 lane 出现第二个 writer，或调用方尝试以策略外分支扩大并发。
- THEN admission 依据 Objective-owned canonical readback contract 动态返回：前态 `not_admitted`、`write_concurrency=1`、`persistent_lane_allowed=false`；后态 `admitted`、`write_concurrency=6`、`persistent_lane_allowed=true`；解析失败返回 `blocked`、`write_concurrency=0`、`persistent_lane_allowed=false`，各态只读 readback 均可并行。
- AND writer lease/CAS 对同一 subject 只允许一个 winner 执行 effect 和追加 event；同一 lane 的第二个 writer 不被准入，不同 lane 可在六车道上并行，loser 零 effect、零 event并在 readback 后保持 queued/not admitted。
- AND branch policy 漂移或解析失败返回 typed blocker，不回退到 Human-Agent contract 中的静态副本；共享环境、设备、codegen、package 与同一 Git ref mutation 不因 lane 准入获得并发写权限。

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
### OPEN-002 S4 write concurrency 6 的真实并发证据尚缺

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：canonical contract 与 branch policy 已按用户裁决立即准入六条持久 lane，并返回 `admitted`、`write_concurrency=6`、`persistent_lane_allowed=true`；尚缺六个不同 lane writer 同时执行的真实集成证据，以及同 subject 竞争恰好一个 winner、integration/abort 后 retained worktree mandatory fast-forward resync 的联合 readback。同 lane 内并行会话不再由 hook/claim 互斥，冲突在 lane→`dev1.0` 准出时暴露。启用后观察用于补齐证据，不阻断已裁决的六车道准入，也不得把未实现的准出 gate 报告为已完成。
- 完成判定：`GWT-003.t1`、`GWT-003.t2`、`GWT-003.t3`、`GWT-003.t4`、`GWT-003.t5` 由六条 lane 的真实并发 execution/PR/readback 证明并发上限、准出时冲突暴露、竞争恢复和 integration/abort 后 fast-forward resync，且 worktree 全程 retained。
- 依赖：六条 lane 的授权 worktree、真实六并发执行窗口、lane PR ready / exact merge candidate 准出 gate 与 integration/abort resync 执行 gate。

<a id="open-003"></a>
### OPEN-003 Journal 信任边界末两条子句尚未形成当前通过证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前缺少 [`GWT-001.t10`](#gwt-001) 受信节点/identity 漂移与 [`GWT-001.t11`](#gwt-001) I/O/unsupported primitive 独立失败终态的可通过测试证据；[`GWT-001.t1`](#gwt-001) 至 [`GWT-001.t9`](#gwt-001) 的既有索引不能代替这两条，因此整个复合验收保持 pending。
- 尚缺验收证据：修复当前 Objective command envelope 与测试输入的 contract drift 后，由现有 journal security/authority local_contract 直接证明受信节点篡改为 `OEX.JOURNAL_TAMPERED`、存储 I/O/不支持原语为 `OEX.JOURNAL_FAILED`，且两者都不解释为 `absent` 或可信状态。
- 完成判定：[`GWT-001.t10`](#gwt-001) 与 [`GWT-001.t11`](#gwt-001) 分别由职责匹配且在当前 revision 实际通过的 local_contract 绑定；届时复跑全部 [`GWT-001`](#gwt-001) journal 测试无失败后再关闭本 OPEN。
- 依赖：Objective execution command-envelope contract 与 journal test fixture 对齐；不得仅添加 `spec_ref` 掩盖当前测试失败。
