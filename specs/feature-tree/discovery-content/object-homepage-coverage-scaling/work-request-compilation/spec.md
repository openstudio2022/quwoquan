# L3 Story：按需意图编译为载体请求信封 (`work-request-compilation`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-020](../design.md#dec-020)、[L2 DEC-024](../design.md#dec-024)、[L2 DEC-025](../design.md#dec-025)

## 1. 用户价值

作为内容运营者，我希望用一份可修改、可取消、可确认的按需请求声明范围、载体组合、逐载体数量与来源策略，得到无副作用的 typed preview，并在显式确认后确定性编译为现有载体 request envelope，从而不写任何执行事实就能复核意图，失败时零写入并可直接修复输入。

## 2. 范围与非目标

### In Scope

- confirmed pre-acquisition handoff 作为来源发现前按需 demand 的唯一 owner：lifecycle、严格 discriminated scope、canonical topic refs 与按载体 sourceSelection。
- WorkRequest 只从 confirmed handoff 与 SourcePool 的直接父引用/摘要派生，编译为每个 active carrier 恰好一个现有 request envelope。
- preview / needs_input / blocked / confirmed / canceled 五态互斥；确认前零 envelope 写入。
- `executionAuthority` 的编译期绑定：bounded explicit 请求精确绑定 handoff/SourcePool/workload，无效或越界 authority typed blocked。

### Out of Scope

- 来源发现执行、载体生产、review 与 canonical 池准入（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）。
- immutable release、环境导入与 App 消费（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）。
- 由自然语言静默猜测缺失数量、未知区域、载体、lifecycle、provider、来源策略或 retry 依据；resolver 可以在 preview 中提出显式默认建议，但确认前不得写 envelope 或执行。
- 新建第二套 Campaign、Execution、Reconciliation、SourcePool、发布台账或运行生命周期；意图请求只编译到现有 request envelope。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 用户意图只编译为现有四载体请求信封

- WorkRequest 只表达内容运营者确认的范围、active carrier、每载体对象数量、`research|commercial` lifecycle、`fresh|retry` 意图与显式依赖引用；它不拥有 Campaign、Execution、Reconciliation、SourcePool、release 或环境状态。
- preview 必须回显解析出的输入、每个 active carrier 的对象数量、提出的默认建议、依赖 identity/digest 与 typed outcome。缺数量、未知或冲突的范围/载体/lifecycle、无效 retry 引用返回 `needs_input`；SourcePool 或其它必需依赖缺失、依赖 digest 漂移返回 `blocked`。两类结果的新 envelope 写入数均为零。
- 内容运营者可以确认、修改或取消 preview。修改回到新的 preview。取消不写 WorkRequest 或 envelope。只有确认才进入编译。登录态不属于本地 Data CLI 的用户入口；provider credential、来源访问权限与素材 rights 分别在 preflight、source admission 与对象 admission 返回 typed 失败，不得塌陷为空结果。
- 同一已确认 WorkRequest、resolver policy/catalog digest 与全部依赖 ref/digest 必须生成相同 WorkRequest digest 与每 carrier envelope digest。每个 active carrier 恰好生成一个现有 request envelope；编译器不得直写 ExecutionSpec、Campaign plan/report、reconciliation receipt 或 SourcePool。
- 多 carrier 编译采用全有或全无语义：任一 carrier 无法形成合法 envelope 时，本次不发布任何新 envelope，已存在的 create-once artifact 保持不变并回到可修改 preview。同 ID 同 bytes 重放幂等；同 ID 不同 bytes、policy/receipt/source digest 漂移必须在写前失败。
- `fresh` 不得携带 `retryOf` 或 reconciliation。`retry` 必须绑定 exact `retryOf` 与兼容的 create-once receipt。网络或 provider 不可用、provider 未授权、rights 被拒、`DATA.POOL.EMPTY`、执行中断或批次截止分别保留自身 typed 终态和下一动作。修复输入后回到 preview；已经产生 execution 事实的恢复只能由新的 `retryOf` 请求进入现有恢复链。

<a id="req-002"></a>
### REQ-002 confirmed handoff 是按需 demand 的唯一 owner 且输入不静默默认

- 来源发现之前的按需 demand 事实（lifecycle、scope、canonical topic refs、按载体 sourceSelection、逐载体数量意图）只由 confirmed pre-acquisition handoff 拥有；WorkRequest 与下游任何对象不得独立接受这些字段的调用方输入，只能持有 handoff 的 ref+digest 与确定性投影。
- scope 是严格 discriminated 值，四类条件必填互斥：`vertical` 不携带 region/topic，`region` 只需 region，`topic` 只需 primary topic，`region_topic` 两者都需。`relatedTopicRefs` 只允许 canonical taxonomy 引用、不含 primary、不由同义展开自动生成。未知或歧义映射返回 `needs_input`，不得合成自由文本主题身份。
- vertical 是显式输入：缺失时只允许 preview 给出显式建议并要求确认，任何路径不得静默默认到固定垂类。
- `sourceSelection` 只引用现有 content source registry 的闭集标识；声明的 provider 必须在 preview/confirm 阶段按所选垂类 provider 闭集 fail closed，不得推迟到执行阶段才校验。

<a id="req-003"></a>
### REQ-003 数量三轴单义与 execution authority 互斥

- 三个数量各自单义且不得互相派生或反推：用户 `workload/quota` 是不可下调的对象下限，SourcePool `candidateCount` 是 oversampling policy 派生的候选数，execution `workUnitCount` 只由实际 accepted candidates 派生。编译与 SourcePool 绑定必须传递各自正确的量，不得以 quota 冒充候选数。
- `executionAuthority` 是互斥选择：`bounded_explicit` 仅允许小规模 explicit 请求（M1–M10）、单 worker、不可续期绝对截止，且必须精确绑定当前 handoff/SourcePool/workload，永不产生 capacity qualification；`governed_calibration` 保留给 M100 及以上，仍要求受治理 calibration receipt。两者不得同时在场，任一无效或越界即 typed blocked。
- bounded explicit 的限制取值只来自受版本控制 policy，不来自调用方覆写、默认常量或探针观测。

## 4. 契约引用

- demand handoff：`quwoquan_data/schema/execution/content_pre_acquisition_handoff.schema.json`
- WorkRequest：`quwoquan_data/schema/execution/work_request.schema.json`
- compile result：`quwoquan_data/schema/execution/work_request_compile_result.schema.json`
- carrier envelope：`quwoquan_data/schema/execution/content_campaign_request_envelope.schema.json`
- source registry：`quwoquan_data/control_plane/_shared/catalogs/content_source_registry.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 意图 preview 经确认后确定性编译且失败零写入

- GIVEN 内容运营者输入范围、homepage/article/image/video 中的 active carrier、每载体正整数对象数量、lifecycle、fresh/retry 与显式依赖引用。
- WHEN resolver 生成 preview，运营者依次选择修改、取消或确认。
- THEN 修改只生成反映新输入的新 preview，取消不写 WorkRequest/envelope。
- THEN 缺数量、未知或冲突输入、无效 retry 返回 typed `needs_input`；SourcePool 或其它必需依赖缺失、依赖 digest 漂移返回 typed `blocked`。两类结果的新 envelope 数均为零。
- THEN 只有确认生成稳定 WorkRequest digest，并为每个 active carrier 恰好生成一个现有 request envelope；相同输入、policy/catalog digest 与依赖 ref/digest 重放得到相同摘要，同 ID 异字节在写前失败。
- THEN 编译结果可读出 WorkRequest、resolver policy/catalog、全部 dependency 与 envelope 的 ref/digest；ExecutionSpec、Campaign plan/report、reconciliation receipt 与 SourcePool 均未由编译器写入。
- THEN 任一 carrier 编译失败时全批零发布，已存在的 create-once artifact 不变；修复输入后回到 preview。
- THEN envelope 已被现有 submit/freeze 链消费后，provider/network/permission、rights、空源、中断或截止失败保留真实阶段终态。恢复只能由新 `retryOf` 消费精确 receipt，且其它 carrier 的既有合格对象不被撤销。
- THEN 同一 immutable candidate 对 1-carrier 与 4-carrier 的 success、blocked、collision 各形成可重放 benchmark；成功场景满足 preview/confirm p95 预算，blocked/collision 新 envelope 数为零，样本不足或超预算不得形成性能达标结论。

<a id="gwt-002"></a>
### GWT-002 confirmed handoff 承载四类 scope 且输入缺口不静默

- GIVEN 内容运营者分别以 `vertical`、`region`、`topic`、`region_topic` 四类 scope 提交按需请求，其中一份缺 vertical、一份携带无法映射 canonical taxonomy 的相关主题、一份声明了垂类 provider 闭集之外的来源。
- WHEN preview 解析输入并等待显式确认。
- THEN 四类 scope 分别按各自的条件必填校验通过或返回 `needs_input`，不存在同时携带互斥维度仍通过的路径。
- THEN 缺 vertical 的请求得到显式建议并要求确认，任何阶段不出现静默默认垂类；未确认前 handoff revision 数为零。
- THEN 无法映射 canonical taxonomy 的相关主题返回 `needs_input` 并点名该主题，不合成自由文本主题身份。
- THEN 闭集之外的来源在 preview/confirm 即 fail closed 并点名该 provider，不推迟到执行阶段。
- THEN confirmed handoff 的 ref+digest 是 WorkRequest 派生的唯一 demand 输入；对同一字段的独立调用方输入路径为零。

## 6. 依赖

- 前置要求：现有 request envelope、submit/freeze 单轨与 create-once artifact 语义。
- 上游事实：content source registry 闭集、垂类 provider 闭集、canonical taxonomy 与（retry 时的）reconciliation receipt。
- 下游结果：confirmed WorkRequest、compile receipt 与逐载体 envelope，由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 消费。
- 父级设计：`DEC-020`、`DEC-024`、`DEC-025`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 confirmed 请求沿现有 submit/freeze 链的真实编译证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前真实 CLI 产出的 envelope 尚未以同一 WorkRequest/compile receipt 身份贯穿现有 submit/freeze/retry 链，仍不能证明一份意图沿现有单轨真实推进。canonical WorkRequest、carrier execution policy、`compile-intent` typed port/CLI 与整批原子 writer 已实现，local_contract 已覆盖 preview、修改、取消、needs-input/blocked、confirm、同摘要重放和持久化失败零可见。
- 完成判定：`GWT-001.t1..t5` 由 local_contract 覆盖 preview、四态结果、确定性摘要、owner 禁写边界与 all-or-nothing；`GWT-001.t6` 由真实 CLI api_integration 覆盖现有 submit/freeze/retry 链。
- 依赖：Data owner 以真实 source-ready 输入完成 confirm 后的 submit/freeze；入池与环境后缀分别由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 与 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的 OPEN 承接。

<a id="open-002"></a>
### OPEN-002 WorkRequest 专项性能与成本实测缺失

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 2 秒 preview、5 秒 confirm 的 p95 仍是设计 SLO，通用性能门禁没有覆盖 WorkRequest；每日 1,000 次确认、平均每份 artifact 16 KiB 与 180 天保留也是容量基线而非实测，不能据此宣称编译面已稳定或成本已闭合。
- 完成判定：`GWT-001.t7` 由同一 immutable candidate 的专项 benchmark 直接覆盖。1-carrier 与 4-carrier 每个成功场景至少 20 个样本并证明 preview/confirm p95 分别不超过 2,000/5,000 ms，blocked/collision 全部零 envelope 发布。报告同时给出 WorkRequest/compile receipt 的 p50/p95 bytes、每日 1,000 请求的 30/180 天未压缩投影，并验证 schema 256 KiB 单 artifact 上限与引用保护归档。
- 依赖：Data owner 在编译面契约收敛后补 benchmark runner 与 canonical report；缺样本、候选 SHA/源摘要漂移或任一场景失败均保持本 OPEN，不得用通用 App/feed 性能门禁替代。

<a id="open-003"></a>
### OPEN-003 handoff 扩展、派生 WorkRequest 与 authority 互斥尚未实现

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 handoff CLI 硬编码固定垂类、compiler 存在静默垂类回退、`topic` 是无 taxonomy 约束的自由字符串、`sourceProviders` 校验推迟到执行阶段、envelope 必填 capacity calibration 使 M1 无法启动、SourcePool 绑定误传 quota；这些输入合同缺口使按需请求无法在不改引擎的情况下表达与执行。
- 完成判定：`GWT-002` 全部结果子句由 local_contract 直接 `spec_ref`，且 `REQ-002`/`REQ-003` 声明的派生单轨、三轴单义与 authority 互斥在 schema 与编译器上以 fail-closed 证据成立。
- 依赖：先冻结 [L2 DEC-024](../design.md#dec-024)、[DEC-025](../design.md#dec-025)；实现为原子替换，不留双字段、fallback 或 shim。
