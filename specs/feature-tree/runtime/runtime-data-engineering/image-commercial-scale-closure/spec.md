# L3 Story：图片商用规模闭环 (`image-commercial-scale-closure`)

> 所属能力：[`runtime-data-engineering`](../spec.md)
>
> 横切 runtime 工程能力；下游价值证据：[`AppRoot UAT-001`](../../../spec.md#uat-001)
>
> 设计归属：[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为开发、测试或运维角色，我希望通用图片 rights、去重、Agent 文案与 release 生命周期验收，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 资产级 rights/provenance、watermark、对象匹配与 generator 的 consumer contract
- canonical identity 去重结果到 environment consumer 的无损投影
- request-bound importer/rollback/replay readback

> 图片 execution、pool、milestone、release build/promotion 与 UAT/acceptance 业务 owner 已迁至 discovery `multi-carrier-release`；本 Story 保留既有 GWT 锚点作为 consumer 合同与测试绑定，不再拥有规模完成结论。

### Out of Scope

- 静态区域、目标对象、数量或阶段清单
- 绕过登录、DRM、robots 或反爬

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 each publishable image has an asset-level disposition

- 缺任一 required rights 字段的资产不能进入 release。

<a id="req-002"></a>
### REQ-002 image identity and visible copy are unique and attributable

- 同一视觉资产不能通过改 URL、尺寸或文件名成为第二对象。

<a id="req-003"></a>
### REQ-003 image release and capacity evidence are request-derived

- M100/M1000 的 image workload target 分别为 100/1000；quota/count 只表达请求负载与里程碑目标，不是发布门。
- 每个 hard-qualified 图片对象均须发布；shortfall 和带 typed issues 的 discard 不否决其余对象。
- active image workloads 按可用容量独立调度，可串行或重叠执行；固定并发、固定 worker、workspace smoke、capacity soak 与 resource samples 不作为 dispatch/promotion 前置。每个实际启动的 task 逐项记录 typed 终态，诊断 sample 不得冒充 task 结果。
- receipt 必须记录 target/selected/qualified/finalized/discarded/shortfall，以及 object pass、first-pass、discard 与 quota attainment 的清晰分子、分母和 rate。任何 dry-run、缺对象硬门或缺环境 receipt 的估算值都不能作为放量完成，target/rate 未命中仅形成统计。

<a id="req-004"></a>
### REQ-004 image Post 交付 generator 只有 `agent`

- 进入 canonical publish、pool record 或 immutable release 的 image Post manifest，其 `generator` 必须且只能为 `agent`，表示用户可见 copy 由冻结的 Agent authoring 产生。
- `image_evidence_pack` 只可作为 execution/source/review evidence 的内部类型，不得序列化为 Post manifest `generator`，也不得通过 schema 双读、兼容 fallback 或放宽校验形成第二条 wire 契约。
- 旧对象若仍携带非 canonical generator，必须 typed excluded；只有基于原 terminal evidence 的 replay/adopt 生成新 manifest 才可重新准入，禁止原地改写历史 receipt。

## 4. 契约引用

- canonical：`quwoquan_data/verticals/<vertical>/providers.yaml`
- canonical：`quwoquan_data/schema/release/asset_rights_closure.schema.json`
- canonical：`quwoquan_data/scripts/content/post/image`
- canonical：`quwoquan_data/scripts/content/release`
- canonical：`quwoquan_data/scripts/governance/coverage/benchmark.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 each publishable image has an asset-level disposition

- GIVEN family 和 provider policy 已声明来源分类和 rights 规则。
- WHEN 图片候选进入 source unit、review 和 canonical promotion。
- THEN 原始落地页、作者、rights、使用范围、watermark、对象匹配与处置结论完整可审计。

<a id="gwt-002"></a>
### GWT-002 image identity and visible copy are unique and attributable

- GIVEN 资产已通过 rights admission，模型绑定已冻结。
- WHEN 图片完成下载、安全检测、Agent 配文、独立 review 和对象事务。
- THEN hash、perceptual similarity 和 source identity 阻止重复发布。
- THEN 归因和用户可见 copy 与 canonical 对象一致。

<a id="gwt-003"></a>
### GWT-003 image release and capacity evidence are request-derived

- GIVEN request 冻结 target set、runtime policy、source digest 和模型绑定。
- WHEN execution 形成 immutable release 并进入 integration 环境。
- THEN import、API、consumer、rollback/replay 和成本吞吐 evidence 都绑定同一 release digest。
- THEN 每个 qualified 图片均 finalize；target shortfall 与 typed discard 只进入 receipt，不阻断其它合格图片。
- THEN 后续容量评估只读取真实 receipt，并按明确分子/分母报告 object pass、first-pass、discard 与 quota attainment；统计值不参与对象发布或结构性 promotion 判定。
- THEN soak/workspace/resource samples 的缺失或失败只影响容量结论，不影响 task dispatch；canonical publish 保持对象事务单写者，最终 release 仍对被选对象及引用做 exact closure。

<a id="gwt-004"></a>
### GWT-004 image Post generator 与 authoring evidence 单轨

- GIVEN image execution 已冻结 Agent authoring 与独立 review evidence。
- WHEN execution materialize Post manifest、交付 canonical pool 或构建 immutable release。
- THEN 所有对外交付的 Post manifest 都以 `generator=agent` 通过 schema，`image_evidence_pack` 只保留在内部 evidence，不进入 generator wire 字段。
- THEN 非 canonical generator fail closed 且对象 typed excluded，不触发双读、历史 receipt 改写或上游 author/review 重跑。
- THEN 即使 `generator=agent`，缺失或错配冻结的 authoring/review evidence 仍使对象 typed excluded，不能仅凭 generator 字面值进入 pool 或 release。

## 6. 依赖

- 前置要求：[`runtime-data-engineering`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-004](../design.md#dec-004)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 each publishable image has an asset-level disposition

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺任一 required rights 字段的资产不能进入 release。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 image identity and visible copy are unique and attributable

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：同一视觉资产不能通过改 URL、尺寸或文件名成为第二对象。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 image release and capacity evidence are request-derived

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：任何 dry-run、缺对象硬门、缺环境 receipt 或估算值都不能作为放量完成，同时 target/rate shortfall 只统计而不阻断合格对象。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 image Post generator 与 authoring evidence 单轨

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺 production materialize 与 schema 的单轨实现及直接验收；schema 仅接受 `generator=agent`，但 image execution 与测试仍写入 `image_evidence_pack`，导致 Post 无法通过 canonical publish schema。
- 完成判定：`GWT-004` 由 manifest schema、materialize、provenance 与 release selection 的对象级 `local_contract` 直接覆盖；非 canonical generator、authoring evidence 缺失/错配和 review evidence 缺失/错配均 typed excluded，且旧 generator 无 compatibility fallback。
