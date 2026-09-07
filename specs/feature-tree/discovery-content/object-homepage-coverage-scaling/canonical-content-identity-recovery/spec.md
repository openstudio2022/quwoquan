# L3 Story：canonical 内容身份的显式治理修复 (`canonical-content-identity-recovery`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-023](../design.md#dec-023)

## 1. 用户价值

作为内容运营者，我希望 invalid canonical identity（如 payload digest 漂移）被呈现为互斥、可裁决的对象治理状态，并通过显式人工命令修复或退役；该治理不得成为内容 producer 九阶段的自动 recovery 或 scheduler。

## 2. 范围与非目标

### In Scope

- invalid canonical identity 的互斥状态、最深层错误保留与唯一恢复 command。
- release/publish AI 对 invalid 状态的只读判定与显式治理交接。

### Out of Scope

- 正常合格对象的入池路径（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）。
- 自动 repair process manager、调度解饥饿、nextAction/reentry 状态机。
- immutable release producer handoff（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）与下游环境消费（由环境 owner 独立拥有）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 invalid canonical 状态互斥且恢复动作唯一

- 统一池 reader 只接受显式 create-once pool record。缺 admission、稳定 `contentId/contentVersion`、完整 `sourceAttribution` 或 source identity 的历史对象按对象排除，不得在读取时从 review、路径或当前 source identity 推导。
- 「已准入且已消费」「存在但可修复」「存在且不可修复」必须是互斥状态；最深层 typed error（如 `DATA.POOL.PAYLOAD_DIGEST_DRIFT`）必须保留到全部读取面，不得折叠为 generic not-admitted，也不得只因 manifest 存在就把 candidate binding静默过滤为已消费。
- payload drift 的恢复只有三种互斥 command，且旧 record、旧 payload evidence 与旧 task receipt 均不改写、不复用：
  - record repair：fresh evidence 证明当前 canonical bytes 仍是同一逻辑版本时执行，保持 `contentVersion`、只追加 `recordSequence + 1`。
  - payload rebuild：fresh immutable author/review/rights evidence 证明是新 payload 时执行，原子写入 `contentVersion + 1` 与 `recordSequence + 1`。
  - terminal：两类证据均不成立时追加 terminal record，保持 `contentVersion`、推进 `recordSequence` 并冻结 terminal reason/next action。
- invalid 状态不得触发自动 recovery。publish/release AI 遇到它时提交 blocked typed issue；治理者可在独立对象治理操作中显式 repair/rebuild/terminal。新内容尝试使用新 execution。

## 4. 契约引用

- canonical pool record：`quwoquan_data/schema/release/pool_object_record.schema.json`
- canonical object transaction：对象级 package/apply schema

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 invalid canonical identity 不得被误判为已消费或无动作空缺

- GIVEN 一个 Homepage stable objectRef 已存在 canonical manifest，但 latest pool record 的 payload digest 与当前 payload 不一致，现役 candidate binding 中含同 objectRef 的候选，且治理输入明确处于以下互斥情形之一：fresh evidence 证明当前 bytes 仍是同一逻辑版本、fresh immutable author/review/rights evidence 证明当前 bytes 是新 payload、两类证据均不成立。
- WHEN 运营者执行显式 canonical identity state query 与 release/publish readback。
- THEN 三个读取面均保留最深层 `DATA.POOL.PAYLOAD_DIGEST_DRIFT`，不折叠为 generic `DATA.POOL.OBJECT_NOT_ADMITTED`，也不只因 manifest 存在就把候选静默过滤为已消费。
- THEN 结果按上述谓词只给出一个受治理 command：record repair、payload rebuild 或 terminal；未裁决前不得覆盖旧 payload或让该对象进入新 release。
- THEN record repair 保持原 `contentVersion`，只追加 `recordSequence + 1` 并绑定 current payload/fresh evidence；payload rebuild 原子写入 `contentVersion + 1` 与 `recordSequence + 1`，旧 record/payload evidence 保持可读。摘要、evidence 或写入冲突时原状态不变。
- THEN terminal command 不创建新内容版本，保持 `contentVersion`、推进 `recordSequence` 并冻结 terminal reason；对象治理结果不派生 execution next 或自动重试。

## 6. 依赖

- 前置要求：canonical pool 的 create-once record 与对象事务单写者语义。
- 上游事实：payload/record digest 事实与治理侧 fresh evidence。
- 下游结果：可裁决的 invalid 状态与恢复动作，供 publish AI 与 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的显式 release cohort 选择消费。
- 父级设计：`DEC-023`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 invalid canonical identity 恢复链缺 fault-injection api_integration 证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺完成判定要求的 api_integration 证据。三态互斥（已准入且已消费、存在但可修复、存在且不可修复）、最深层 `DATA.POOL.PAYLOAD_DIGEST_DRIFT` 保留到读取面与恢复动作路由已实现并由 local_contract 锚定；识别现场（峨眉山 Homepage 的 payload digest 漂移致 `gap=1`、release selection 长期排除）已由受治理 record repair 收敛，release readback 为 `admitted_current` 且无深层错误、`recordSequence` 前进到 2。
- 尚缺验收证据：从真实 canonical application command 出发、经基础设施存储边界 fault-injection port 制造 drift、覆盖 record repair / payload rebuild / terminal 三互斥分支的 api_integration。
- 完成判定：`GWT-001.t1..t4` 由同一 api_integration 直接覆盖。测试先通过真实 canonical application command 创建有效状态，再只通过明确的基础设施存储边界 fault-injection port 制造 digest drift，禁止直接写 manifest、ledger 或 fixture seed，并分别构造 record repair、payload rebuild 与 terminal 的互斥证据谓词。首轮 inspection 精确保留 `DATA.POOL.PAYLOAD_DIGEST_DRIFT` 且只给出对应 command。record repair 保持 `contentVersion` 只推进 `recordSequence`，payload rebuild 同时推进两者并保留旧证据，terminal 不创建新内容版本且携带 terminal reason/next action。三个分支都不再出现 `gap>0 && backlog=0 && 无恢复动作`。
- 依赖：canonical repair authority、immutable evidence 来源、recordSequence/contentVersion 与 release consumer 的职责边界由 [L2 DEC-023](../design.md#dec-023) 冻结；实现不得通过放宽 payload digest 或恢复 manifest-only admission 完成。
