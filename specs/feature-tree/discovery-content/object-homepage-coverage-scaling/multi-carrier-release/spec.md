# L3 Story：多载体内容与主页发布 (`multi-carrier-release`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望文章、图片、视频和主页对象以独立 execution 并行生产，同时共享冻结实体目录与 release 边界，从而能分别恢复失败并复核来源、媒体、实体与环境消费是否闭合。

## 2. 范围与非目标

### In Scope

- 四个 carrier execution 共享不含运行身份的 canonical entity catalog digest，各自冻结 target set、quota 与终态。
- 各载体复用同一创建、审核、promotion 和 ship 生命周期。
- 批次级/跨载体聚合门只作目标与统计；对象级质量与权利门保持 fail-closed。

### Out of Scope

- 为不同地区或载体维护第二套发布目录与运行台账。
- 为「能发布」而放松对象级质量、权利、去重或真实媒体门。

## 3. 行为要求

### REQ-001 多载体统一发布边界

- 每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。
- homepage、article、image、video 不以彼此的 execution 或 publish 结果作为运行前置；post 只依赖可解析的 canonical entity identity。
- 四个 execution 必须从同一 reviewed named main branch、commit、source digest 与 entity catalog digest 并行运行，单一载体失败不得覆盖其他载体工作包，也不得阻止其他载体已合格对象发布。
- `task execute --stage submit-only|campaign-run|review-only` 是唯一 campaign 门面；controller 等齐四份 immutable submission 后才冻结唯一 plan 与 `planDigest`，collision、branch/commit/source/catalog mismatch、主工作树漂移或超时均 fail closed。
- controller 为四个 lane 建立同一 frozen commit 的 detached disposable clone，四 lane 并发 review；每条 lane 按自身 review 结果独立进入 publish，不得因任一 lane 失败而整批 abort。
- lane 终态独立记录为 `published`（`qualified >= quota`）、`partial`（`0 < qualified < quota` 且已合格对象已发布）或 `blocked`（`qualified == 0` 或 review/publish 失败）；campaign 终态为聚合视图：`succeeded`（四路均达标）、`succeeded_partial`（至少一路发布了合格对象）、`blocked`（无任何可发布合格对象）。
- `quota` 是里程碑累计目标，不是发布许可条件；`partial` lane 必须发布全部已合格对象，并将 shortfall 写入 typed evidence，不得因未达 quota 丢弃合格对象。
- 若存在 discard，每个 discard 必须具备非空 `objectRef` 与 typed `issues`，且 `selected == qualified + discarded`；不得要求真实批次必须存在 discard 才准出。
- article/image/video 的 canonical Post manifest 必须显式声明 `contentIdentity=work`；schema、promotion 与 importer 任一层发现缺失或非 `work` 均阻断该对象，禁止由消费者默认补值。
- campaign report 必须保留 named main branch、status、phase、review/publish return code、clone ref、qualified/finalized count 与 cleanup 终态；报告是运行回执，不得成为新的内容或 release 真相源。
- 复制会话准出（COPY_READY）可要求每路达到约定 quota/count 证明，但不得阻止未达复制门的合格内容发布。

## 4. 契约引用

- release：`quwoquan_data/schema/release/release_manifest.schema.json`
- ship：`quwoquan_data/schema/release/ship_report.schema.json`
- campaign report：`quwoquan_data/schema/execution/content_campaign_report.schema.json`
- lane receipt：`quwoquan_data/schema/execution/content_campaign_lane_receipt.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 独立载体并行且引用闭包后才允许 promotion

- GIVEN homepage、article、image、video 各有一个 immutable execution，并共享同一 named main branch、commit、source digest 与 entity catalog digest。
- WHEN 四个 execution 并行生产且操作者请求聚合并 promotion release。
- THEN post 不等待 homepage execution 或 publish，任一载体失败只保留在自身 evidence，其他载体已合格对象仍可 publish。
- THEN 仅当全部 approved 对象的 entity identity、creator、tag、source 与媒体处置闭合时生成 immutable release；任一悬挂引用使整次 promotion 失败。
- THEN 四个 review 子进程存在真实时间重叠；任一 lane 的 publish 不得早于该 lane 自身 review 终态，但不得等待其他 lane 的 review/publish 终态。
- THEN 某 lane `0 < qualified < quota` 时终态为 `partial`，已合格对象已 finalize，shortfall 有 typed evidence；`qualified == 0` 时该 lane 为 `blocked`。
- THEN 全批次零 discard 仍允许成功终态；若存在 discard，则每个 discard 必须有非空 `objectRef` 与 typed `issues`。
- THEN mismatch、submission collision、主工作树 drift 或等待 timeout 留下 blocked report。
- THEN lane 级 review/publish 失败只阻塞该 lane。
- THEN 所有已创建 detached clone 均被清理。

## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 多载体环境消费证据

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：发布合同完成不等于四类载体已在目标环境被真实消费。
- 完成判定：`GWT-001` 与目标环境四载体消费 UAT 均有直接 `spec_ref`。
