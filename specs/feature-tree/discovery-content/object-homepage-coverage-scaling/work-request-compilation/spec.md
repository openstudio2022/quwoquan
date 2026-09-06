# L3 Story：按需意图编译为载体 demand (`work-request-compilation`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望用一份可修改、可取消、可确认的按需请求声明范围、载体组合、逐载体数量与来源策略，得到无副作用的 typed preview，并在显式确认后确定性编译为 confirmed carrier demand，从而不写任何执行事实就能复核意图，失败时零写入并可直接修复输入。

## 2. 范围与非目标

### In Scope

- confirmed demand 的上游产品语义包含 lifecycle、严格 discriminated scope、canonical topic refs 与按载体 sourceSelection；已删除的 pre-acquisition handoff schema 不再是仓内 owner。
- 现役仓内入口只接收 confirmed carrier demand 与 immutable candidate bindings；旧 WorkRequest/SourcePool schema 已删除，相关 preview/confirm 仅作为上游待收敛产品语义。
- preview / needs_input / blocked / confirmed / canceled 五态互斥；确认前零 carrier demand 与零工作包写入。
- candidate-backed work package 的中性初始化边界已实现：`task init` 只原子物化三份 `0.plan` 输入，不推进 stage；它是唯一正式初始化命令。

### Out of Scope

- 来源发现执行、载体生产、review 与 canonical 池准入（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）。
- immutable release producer handoff（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）；环境导入与 App 消费由下游环境 owner 独立拥有。
- 由自然语言静默猜测缺失数量、未知区域、载体、lifecycle、provider、来源策略或 retry 依据；resolver 可以在 preview 中提出显式默认建议，但确认前不得写 carrier demand 或执行。
- 新建或调用 Campaign、仓内 Agent/controller/queue/runner/fleet/recovery、managed SDK/provider 路径、第二套 Execution/发布台账或运行生命周期；意图请求只编译 confirmed carrier demand，执行由宿主 Agent 进入 producer 九阶段。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 用户意图只编译为现役四载体 demand

- 上游 preview/confirm 只表达内容运营者确认的范围、active carrier、每载体对象数量、`research|commercial` lifecycle、`fresh|retry` 意图与显式依赖引用；仓内落点只形成现役 carrier demand，不恢复 Campaign、Reconciliation、SourcePool 或 WorkRequest schema。
- preview 必须回显解析出的输入、每个 active carrier 的对象数量、提出的默认建议、依赖 identity/digest 与 typed outcome。缺数量、未知或冲突的范围/载体/lifecycle、无效 retry 引用返回 `needs_input`；confirmed demand 或其它必需依赖缺失、依赖 digest 漂移返回 `blocked`。两类结果的新 carrier demand 与工作包写入数均为零。
- 内容运营者可以确认、修改或取消 preview。修改回到新的 preview。取消不写 carrier demand。只有确认才进入编译。宿主 Agent 不运行仓内 Cursor key/model/SDK semantic preflight；来源访问与素材 rights 分别在 source admission 与对象 admission 返回 typed 失败，不得塌陷为空结果。
- 同一已确认输入、resolver policy/catalog digest 与全部依赖 ref/digest 必须生成相同 confirmed-demand digest 与每 carrier demand digest。每个 active carrier 恰好生成一个 demand record；编译器不得直写 execution work package、Campaign plan/report、reconciliation receipt、SourcePool 或 pool record。
- 多 carrier 编译采用全有或全无语义：任一 carrier 无法形成合法 carrier demand 时，本次不发布任何新 carrier demand，已存在的 create-once artifact 保持不变并回到可修改 preview。同 ID 同 bytes 重放幂等；同 ID 不同 bytes、policy/receipt/source digest 漂移必须在写前失败。
- `fresh` 不得携带 `retryOf`。`retry` 必须绑定 exact predecessor terminal receipt。网络、来源访问、rights、候选为空、执行中断或批次截止分别保留自身 typed 终态和下一动作。修复输入后回到 preview；已经产生 execution 事实的恢复只能创建新的 `executionId + retryOf` 并由宿主 Agent 进入同一 producer 九阶段。

<a id="req-002"></a>
### REQ-002 confirmed demand 输入不静默默认

- 来源发现之前的按需 demand 事实（lifecycle、scope、canonical topic refs、按载体 sourceSelection、逐载体数量意图）必须在仓外上游完成确认；仓内 carrier demand 只持初始化必需的确定性投影。下游 release consumer 只能读 canonical object package + append-only pool record 的白名单 projection，不得读取生产输入字段。
- scope 是严格 discriminated 值，四类条件必填互斥：`vertical` 不携带 region/topic，`region` 只需 region，`topic` 只需 primary topic，`region_topic` 两者都需。`relatedTopicRefs` 只允许 canonical taxonomy 引用、不含 primary、不由同义展开自动生成。未知或歧义映射返回 `needs_input`，不得合成自由文本主题身份。
- vertical 是显式输入：缺失时只允许 preview 给出显式建议并要求确认，任何路径不得静默默认到固定垂类。
- `sourceSelection` 只引用现有 content source registry 的闭集标识，闭集按 `(lane, vertical)` 取。声明的 provider 在上游确认与 preview/confirm 阶段点名 fail closed，不得推迟到执行阶段才校验；执行阶段不得携带针对另一份闭集的第二次 provider 判定。
- carrier demand 的 source intent 只是已确认 `sourceSelection` 的逐载体确定性投影；编译输入不接受额外 provider 列表。旧 SourcePool、execution/campaign/provider/model 生产身份均不得进入 consumer identity、eligibility、release handoff 或 App DTO。

<a id="req-003"></a>
### REQ-003 candidate-backed `task init` 原子初始化

- 用户 quota 与 immutable candidate 数量分别来自 confirmed demand 与 candidate bindings；二者不互相推导。
- 新任务初始化的目标契约为中性 `task init`：输入 confirmed carrier demand 与 immutable candidate bindings，只原子物化 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`，不运行 semantic preflight、不推进 `0.plan` 或任何后继 stage，也不创建 pool/release/environment 事实。
- 当前 `task init --carrier-demand <path> --candidate-bindings <path>` 是唯一合法初始化入口；真实宿主消费证据由 `OPEN-001` 追踪。
- 同 identity 同 bytes 初始化幂等；candidate ref/digest 缺失、accepted count 与 target set 不一致、同 identity 异 bytes 或任一 schema 失败时零工作包可见。

## 4. 契约引用

- 历史 demand handoff、WorkRequest 与 compile-result execution schema 已删除；本 Story 对 preview/confirm 的描述是待收敛的上游产品语义，不代表这些旧 schema 仍受支持。
- carrier demand / candidate bindings / init request：`quwoquan_data/schema/execution/carrier_demand.schema.json`、`immutable_candidate_bindings.schema.json`、`task_init_request.schema.json`
- execution manifest / target set：`quwoquan_data/schema/execution/content_execution_manifest.schema.json`、`quwoquan_data/schema/execution/target_set.schema.json`
- source registry：`quwoquan_data/control_plane/_shared/catalogs/content_source_registry.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 意图 preview 经确认后确定性编译且失败零写入

- GIVEN 内容运营者输入范围、homepage/article/image/video 中的 active carrier、每载体正整数对象数量、lifecycle、fresh/retry 与显式依赖引用。
- WHEN resolver 生成 preview，运营者依次选择修改、取消或确认。
- THEN 修改只生成反映新输入的新 preview，取消不写 carrier demand。
- THEN 缺数量、未知或冲突输入、无效 retry 返回 typed `needs_input`；confirmed demand 或其它必需依赖缺失、依赖 digest 漂移返回 typed `blocked`。两类结果的新 carrier demand 数均为零。
- THEN 只有确认生成稳定 confirmed-demand digest，并为每个 active carrier 恰好生成一个 carrier demand；相同输入、policy/catalog digest 与依赖 ref/digest 重放得到相同摘要，同 ID 异字节在写前失败。
- THEN 编译结果可读出 resolver policy/catalog、全部 dependency 与 carrier demand ref/digest；execution work package、Campaign plan/report、reconciliation receipt、SourcePool 与 pool record 均未由编译器写入。
- THEN 任一 carrier 编译失败时全批零发布，已存在的 create-once artifact 不变；修复输入后回到 preview。
- THEN 已实现的 candidate-backed `task init` 之后，confirmed demand 只由宿主 Agent 按 producer 九阶段消费；source access、rights、空候选、中断或截止失败保留真实 stage 终态。恢复只能由新 `executionId + retryOf` 消费精确 receipt，且其它 carrier 的既有合格对象不被撤销。

<a id="gwt-002"></a>
### GWT-002 confirmed demand 承载四类 scope 且输入缺口不静默

- GIVEN 内容运营者分别以 `vertical`、`region`、`topic`、`region_topic` 四类 scope 提交按需请求，其中一份缺 vertical、一份携带无法映射 canonical taxonomy 的相关主题、一份声明了垂类 provider 闭集之外的来源。
- WHEN preview 解析输入并等待显式确认。
- THEN 四类 scope 分别按各自的条件必填校验通过或返回 `needs_input`，不存在同时携带互斥维度仍通过的路径。
- THEN 缺 vertical 的请求得到显式建议并要求确认，任何阶段不出现静默默认垂类；未确认前 carrier demand 数为零。
- THEN 无法映射 canonical taxonomy 的相关主题返回 `needs_input` 并点名该主题，不合成自由文本主题身份。
- THEN 闭集之外的来源在上游确认与 preview/confirm 即 fail closed 并点名该 provider，不推迟到执行阶段；跨 lane 借用另一 lane 的闭集同样判否。
- THEN confirmed-demand ref+digest 是 carrier demand 派生的唯一输入；对同一字段的独立调用方输入路径为零。旧 SourcePool/execution/campaign/provider/model 不出现在 consumer projection 或 App DTO。

## 6. 依赖

- 前置要求：confirmed-demand input 与 create-once carrier demand 语义。
- 上游事实：content source registry 闭集、垂类 provider 闭集、canonical taxonomy 与（retry 时的）predecessor stage receipt。
- 下游结果：逐载体 confirmed demand 与 immutable candidate bindings；已实现的 candidate-backed `task init` 由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 的宿主 execution 消费。
- 父级设计：`DEC-020`、`DEC-024`、`DEC-025`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 confirmed 请求到宿主 execution 的真实消费证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：旧 canonical WorkRequest/`compile-intent` 实现与 schema 已删除；当前只保留上游产品语义与现役 carrier demand/task-init 边界。真实 confirmed demand 尚未通过中性 `task init` 形成 candidate-backed 工作包并由宿主 Agent 走到真实 stage terminal，因此不能证明一份意图沿目标单轨推进。
- 完成判定：[`GWT-001`](#gwt-001) 的 confirmed demand 原子性与 [`GWT-002`](#gwt-002) 的只读输入边界保持成立；api_integration 以真实 confirmed demand 调用已实现的 `task init`，由宿主 Agent 产生真实 stage terminal，并证明新 `retryOf` 精确消费 predecessor receipt、其它 carrier 既有合格对象不被撤销。性能观测不构成 execution authority。
- 依赖：deterministic `task init` 已实现；尚缺真实宿主消费。入池与环境后缀分别由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 与 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的 OPEN 承接。
