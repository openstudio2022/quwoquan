# L3 Story：来源发现由宿主 AI 原生执行 (`source-discovery-scale-reliability`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望来源发现由宿主 AI 直接按 target 执行并留下可复核计划、取得结果与 typed issue，从而失败只影响对应 target，且硬切后的仓库不再恢复 scheduler/worker/fleet 控制面。

## 2. 范围与非目标

### In Scope

- immutable candidate binding 只冻结 target identity；宿主 AI 在 `sources` 为每个冻结 target 选择来源并写计划，在 `1.download` 才按计划取得 source units/source refs 与媒体 bytes/CAS。
- 每份来源结果绑定唯一 target identity；多个 target 或 execution 的串并行由宿主原生能力承担。
- 跨会话只读 stage OPEN/CLOSE receipts 与业务 result refs。

### Out of Scope

- 仓内来源发现编排、进度控制面或运行能力标定。
- 由代码自动选择替代来源、解释业务终态、重试失败或推进后继 stage。
- 引入仓内调度、进度状态或兼容读写。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每个 target 的来源计划与取得结果保持单轨

- producer 九阶段 Skill是唯一业务工作说明；candidate binding 不承担来源 admission，`sources` 只写逐 target source plan，`1.download` 才创建 source unit、source ref 与取得字节/CAS。
- 宿主可串行或并发调研 target，但每个计划、source unit、typed issue 与 result ref 必须绑定对应 target exact identity，不得因并发丢失、合并或复制 target。
- OPEN 无 CLOSE 时新会话读取同一冻结输入并重做该 stage；CLOSE blocked 后只新建 execution，不由代码生成 recovery stage。

<a id="req-002"></a>
### REQ-002 来源失败由宿主 AI 显式裁定且旧控制面保持删除

- 来源访问失败、不可取得、无候选与证据不足由宿主 AI 写 typed issues；代码只执行窄 IO、schema 与 verifier，不得自动接管、重试、派生终态或选择替代来源。
- 仓库不保存来源发现编排、进度控制面或运行能力标定。
- 旧 schema、CLI、tests 与 references 物理删除后保持零 shim、零 dual-read、零兼容入口；删除事实不等于 fresh 业务 E2E 已完成。

## 4. 契约引用

- source plan：`quwoquan_data/schema/source/source_plan.schema.json`
- source unit：`quwoquan_data/schema/source/atomic_source_unit_meta.schema.json`
- source ref：`quwoquan_data/schema/source/object_source_refs.schema.json`
- stage receipt：`quwoquan_data/schema/execution/stage_receipt.schema.json`
- source plan verifier：`quwoquan_data/scripts/verify/verify_source_plan.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多 target 来源发现保持逐 target 单轨

- GIVEN 一个由 identity-only candidate bindings 冻结多个 target 的 execution，task-init 前没有 source/media admission。
- WHEN 宿主 AI 使用原生串行或并发能力完成 `sources` 与 `1.download`。
- THEN 每个 target 先有 source plan，下载阶段才有 source units/source refs/媒体 bytes 与 CAS，且每份结果只绑定一个 target；candidate binding 不被提升为 source evidence。
- THEN 单 target 失败产生该 target 的 typed issue，其它 target 的已完成结果不被撤销或覆盖。
- THEN 仓库中不存在来源发现编排或进度 authority，后继只由 Skill 固定。

## 6. 依赖

- 前置要求：[`work-request-compilation`](../work-request-compilation/spec.md) 提供 confirmed carrier demand 与只冻结目标对象身份的 immutable candidate bindings。
- 上游事实：冻结 target identity 与允许来源策略。
- 下游结果：逐 target source plan、source units/source refs 或 typed blocked evidence。
- 父级设计：`DEC-001`、`DEC-028`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 硬切后多 target 来源发现尚缺 fresh 直接证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：旧来源发现编排与进度控制面已物理删除，并由 post-delete architecture/public CLI live-import gates 持续锁定；但当前尚缺硬切后多 target 来源发现的行为证据，不能仅凭删除门宣称逐 target 计划、下载与局部失败隔离已经实现或闭合。
- 尚缺验收证据：同一 identity-only candidate-backed execution 至少包含一个成功 target 与一个 typed blocked target，直接证明计划先于下载、结果 identity 不串线、局部失败不覆盖其它 target。
- 完成判定：[`GWT-001.t1`](#gwt-001)、[`GWT-001.t2`](#gwt-001) 与 [`GWT-001.t3`](#gwt-001) 逐条由硬切后 current local_contract/api_integration 绑定并实际通过；fresh 四载体 producer release handoff 由 [`multi-carrier-release` OPEN-020](../multi-carrier-release/spec.md#open-020) 跟踪，下游环境消费不构成本 Story 验收。
- 依赖：当前 source plan、atomic acquisition 与 stage OPEN/CLOSE 边界；不得恢复旧编排来补证据。
