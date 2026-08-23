# L3 Story：canonical 内容身份的修复与调度解饥饿 (`canonical-content-identity-recovery`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-023](../design.md#dec-023)

## 1. 用户价值

作为内容运营者，我希望池中 invalid canonical identity（如 payload digest 漂移）被呈现为互斥、可裁决的状态并给出唯一恢复 command，从而按需生产不再被「已存在但不可修复也不可跳过」的对象永久饥饿，精确命名目标命中问题身份时得到 repair/select 动作而不是静默换对象。

## 2. 范围与非目标

### In Scope

- invalid canonical identity 的互斥状态、最深层错误保留与唯一恢复 command。
- source-ready 调度对 invalid 状态的解饥饿裁决。

### Out of Scope

- 正常合格对象的入池路径（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）。
- repair process manager 的完整实现规模：在 `OPEN-001` 关闭之前，只要求深层错误呈现与 `repair_identity|select_new_identity` 路由可用。
- immutable release 与环境消费（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 invalid canonical 状态互斥且恢复动作唯一

- 统一池 reader 只接受显式 create-once pool record。缺 admission、稳定 `contentId/contentVersion`、完整 `sourceAttribution` 或 source identity 的历史对象按对象排除，不得在读取时从 review、路径或当前 source identity 推导。
- 「已准入且已消费」「存在但可修复」「存在且不可修复」必须是互斥状态；最深层 typed error（如 `DATA.POOL.PAYLOAD_DIGEST_DRIFT`）必须保留到全部读取面，不得折叠为 generic not-admitted，也不得只因 manifest 存在就把 source-ready 候选静默过滤为已消费。
- payload drift 的恢复只有三种互斥 command，且旧 record、旧 payload evidence 与旧 task receipt 均不改写、不复用：
  - record repair：fresh evidence 证明当前 canonical bytes 仍是同一逻辑版本时执行，保持 `contentVersion`、只追加 `recordSequence + 1`。
  - payload rebuild：fresh immutable author/review/rights evidence 证明是新 payload 时执行，原子写入 `contentVersion + 1` 与 `recordSequence + 1`。
  - terminal：两类证据均不成立时追加 terminal record，保持 `contentVersion`、推进 `recordSequence` 并冻结 terminal reason/next action。
- 调度不得出现永久饥饿不变量破坏：`gap > 0` 且 `sourceReadyBacklog = 0` 且无恢复动作是立即阻断的状态；三个 invalid 状态必须返回 recovery action，`terminated` 以可读终态退出 backlog，后续供给必须选择新 stable identity。

## 4. 契约引用

- lane receipt：`quwoquan_data/schema/execution/content_campaign_lane_receipt.schema.json`
- drain result：`quwoquan_data/schema/execution/pool_delivery_drain_result.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 invalid canonical identity 不得被误判为已消费或无动作空缺

- GIVEN 一个 Homepage stable objectRef 已存在 canonical manifest，但 latest pool record 的 payload digest 与当前 payload 不一致，source-ready pool 含同 objectRef 的候选，且治理输入明确处于以下互斥情形之一：fresh evidence 证明当前 bytes 仍是同一逻辑版本、fresh immutable author/review/rights evidence 证明当前 bytes 是新 payload、两类证据均不成立。
- WHEN 运营者执行 pool inspection、backfill planning 与 source-ready scheduling。
- THEN 三个读取面均保留最深层 `DATA.POOL.PAYLOAD_DIGEST_DRIFT`，不折叠为 generic `DATA.POOL.OBJECT_NOT_ADMITTED`，也不只因 manifest 存在就把候选静默过滤为已消费。
- THEN 结果按上述谓词只给出一个受治理 command：record repair、payload rebuild 或 terminal；未裁决前不得创建新对象、覆盖旧 payload 或继续 semantic dispatch。
- THEN record repair 保持原 `contentVersion`，只追加 `recordSequence + 1` 并绑定 current payload/fresh evidence；payload rebuild 原子写入 `contentVersion + 1` 与 `recordSequence + 1`，旧 record/payload evidence 保持可读。摘要、evidence 或写入冲突时原状态不变。
- THEN terminal command 不创建新内容版本，保持 `contentVersion`、推进 `recordSequence` 并冻结 terminal reason 与“选择新 identity 或关闭本意图”的 next action；三个分支都禁止出现 `gap > 0`、`sourceReadyBacklog = 0` 且没有恢复动作的永久饥饿状态。

## 6. 依赖

- 前置要求：canonical pool 的 create-once record 与对象事务单写者语义。
- 上游事实：payload/record digest 事实与治理侧 fresh evidence。
- 下游结果：可裁决的 invalid 状态与恢复动作，供 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 的调度与 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的 release 选择消费。
- 父级设计：`DEC-023`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 invalid canonical identity 导致 Homepage 永久饥饿

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前峨眉山 Homepage 已有 canonical manifest，但 latest pool record 与 payload digest 漂移，底层事实为 `DATA.POOL.PAYLOAD_DIGEST_DRIFT`。`pool-inspect` 把它折叠为 generic `DATA.POOL.OBJECT_NOT_ADMITTED`，source-ready loader 又只因 manifest 存在就把同 stable objectRef 视为已消费，现场结果为 `gap=1`、`sourceReadyBacklog=0`、`dispatchCandidateCount=0`；backfill 同时返回 drift 且不给 repair requirement，因此继续补采 source 或重试都不会前进。
- 尚缺实现：把“已准入且已消费”“存在但可修复”“存在且不可修复的 canonical collision”分为互斥状态；保留最深层 `DATA.POOL.PAYLOAD_DIGEST_DRIFT`，由受治理 repair/rebuild 或显式终止 stable identity 收敛。不得把 invalid canonical 当作新对象覆盖，也不得无声过滤 source-ready candidate。
- 尚缺验收证据：缺少 payload drift 的 pool-inspect typed readback、source-ready 调度裁决、从 immutable evidence 修复后 contentVersion/recordSequence 前进、不可修复时显式终止且不再计入可调度 backlog 的 api_integration。
- 完成判定：`GWT-001.t1..t4` 由同一 api_integration 直接覆盖。测试先通过真实 canonical application command 创建有效状态，再只通过明确的基础设施存储边界 fault-injection port 制造 digest drift，禁止直接写 manifest、ledger 或 fixture seed，并分别构造 record repair、payload rebuild 与 terminal 的互斥证据谓词。首轮 inspection 精确保留 `DATA.POOL.PAYLOAD_DIGEST_DRIFT` 且只给出对应 command。record repair 保持 `contentVersion` 只推进 `recordSequence`，payload rebuild 同时推进两者并保留旧证据，terminal 不创建新内容版本且携带 terminal reason/next action。三个分支都不再出现 `gap>0 && backlog=0 && 无恢复动作`。
- 依赖：canonical repair authority、immutable evidence 来源、recordSequence/contentVersion 与 source-ready consumer 的职责边界由 [L2 DEC-023](../design.md#dec-023) 冻结；实现不得通过放宽 payload digest 或恢复 manifest-only admission 完成。
