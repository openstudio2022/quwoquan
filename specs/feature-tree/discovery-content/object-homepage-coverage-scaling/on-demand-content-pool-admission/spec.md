# L3 Story：按需内容生产与 canonical 池准入 (`on-demand-content-pool-admission`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-022](../design.md#dec-022)、[L2 DEC-026](../design.md#dec-026)

## 1. 用户价值

作为内容运营者，我希望同一份 confirmed 按需请求的所选载体经真实来源发现、生产与独立审核后，合格唯一对象经唯一 reviewed delivery 路径以单对象事务幂等增量进入 canonical 内容池，并在任何非成功终态得到可执行的恢复动作与重入引用，从而每次生产都能复核数量守恒与来源闭合，失败不丢已合格对象。

## 2. 范围与非目标

### In Scope

- article lane 在冻结 target set 之前完成实体级来源预筛，并把候选级拒绝原因聚合为实体级单一首要失败原因。
- image/video 的媒体来源准入、workUnit 冻结与 execution 后独立内容审核。
- 新内容唯一写路径：reviewed delivery intent → drain → canonical 单对象事务；历史 raw backfill 不进入正常生产装配。
- 单对象结果互斥五态与非成功终态的结构化 `nextAction + reentryRef`。
- 同一冻结请求的 exact replay 零增量验证。

### Out of Scope

- 意图 preview 与 envelope 编译（归 [`work-request-compilation`](../work-request-compilation/spec.md)）。
- immutable release、环境导入与 App 消费（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）。
- invalid canonical identity 的修复裁决（归 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md)）。
- article 来源预筛的匹配置信度、最小正文字数与探测预算的具体数值（见 `OPEN-001`）。
- 绕过登录、付费墙、验证码、访问控制、DRM 或平台技术限制取得素材；直接生成图片或视频。
- 冻结期多样性准入的每实体累计上限与 Top-N 上限数值：阈值由多样性策略的既有 owner 单点拥有，本 Story 只消费其准入结论。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 article 来源预筛准入与实体级首要失败原因

- 内容运营者在 article lane 冻结 target set 之前就能知道哪些实体存在可锚定的长文来源，因此工作单元不再被无来源实体占用；同一 quota 下 article 的累计下限达成得更快，而不是把 target set 砍小后更早收敛为 `partial`。
- article lane 必须在冻结 target set 之前完成实体级来源判定，不得只按主清单静态优先级排序、把来源可得性推迟到 auto_research 或 content_plan 才发现。homepage 与 video 的既有判定时点由各自路径拥有，本 REQ 不重复约束，也不要求 article 照搬 homepage 把整批拦下的处置。
- 每个候选实体的预筛结论必须是且只能是以下四态之一。四态互不塌陷，也不得塌陷为空值、空集合或零计数：
  - `在场可用`：允许来源闭集内至少有一个可合法取得、可读，且经实体锚定判定确属该实体的长文候选。
  - `在场不足`：判定已完成，候选可合法取得且可读，但未达门槛。必须再带唯一子原因区分「已锚定到本实体但正文篇幅不足」与「可读但未锚定到本实体」；前者的运营动作是换实体或按 calibration 调整篇幅门槛，后者是扩来源闭集或换实体。同一实体同时命中两个子原因时取前者，因为它已证明本实体的来源确实存在。
  - `缺席`：判定已完成，允许来源闭集内不存在可合法取得且可读的候选。必须再带唯一子原因区分「闭集内存在候选但不可合法取得或不可读」（含被 robots/服务条款、登录或验证墙、允许路径之外排除者）与「闭集内不存在候选」；前者的运营动作是修来源闭集，后者是换实体。
  - `探测失败`：判定未完成，包括网络不可达、超时、解析中断与探测预算在得出结论之前耗尽。
- `缺席` 与 `探测失败` 的分界是「判定已完成且结论确定」与「判定未完成」，二者不得互相冒充：未完成的判定不得报告为确定缺席，确定缺席也不得表述为可续跑中断。`探测失败` 必须给出精确可续跑 refs，`在场不足` 与 `缺席` 必须给出不可续跑的判定依据。
- 同一实体的多个候选归并为实体终态时按 `在场可用` → `探测失败` → `在场不足` → `缺席` 取先者：只要存在一个合格候选即 `在场可用`；没有合格候选但仍有候选未得出结论时不得先行宣告 `在场不足` 或 `缺席`。
- 预筛的每个非成功终态必须以 typed 且运营者可直接读取的形式呈现，运营者只读该终态即可决定续跑、修来源闭集还是换实体；进程退出码、异常字符串与运行日志都不是合法呈现面。预筛在 execution spec 冻结之前终止时同样适用，lane 终态为 `published` 或 `partial` 时 `探测失败` 实体的可续跑 refs 也必须留在同一呈现面，不因该 lane 已发布而丢弃。
- 预筛是准入过滤，不是产量保证。`在场可用` 数少于 quota 时必须触发既有补采轮次补充候选并重新预筛，不得静默下调 quota，也不得用未通过预筛的实体 padding 工作单元。补采预算耗尽后仍不足时，lane 以 `在场可用` 经冻结期准入后的实际集合继续执行并按 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的 lane 终态契约进入 `partial`；只有该集合为零才 `blocked`。
- 上一条的 `blocked` 有两种成因不同的零，必须分别携带对应证据，不得互相冒充。零 `在场可用` 的那种携带本 REQ 的实体级首要原因。`在场可用` 非空而经冻结期准入后为零的那种携带准入侧的逐实体排除证据，并按 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的零合格原因闭集取「全部候选实体被选择器准入排除」；此时实体级首要原因聚合全部为 `在场可用`，用它冒充会把运营者指向一个没有问题的来源。
- 冻结期准入是选择器在冻结工作单元时的决定，只作用于已判为 `在场可用` 的实体，其出局不改变该实体的四态取值，也不计入本 REQ 的候选级或实体级拒绝计量。本 REQ 的四态保持四个值，不因此新增第五态，也不在四态旁挂表达是否被选中的状态位。
- 预筛与补采发生在 selection 阶段、早于执行策略冻结 `targetObjectCount`。预筛只改变进入冻结的候选集合，不改变对象下限、工作单元数与并行上限的三值分离。
- 实体级预筛终态是「该实体是否还能被重新探测」的唯一权威面，fleet 级零合格原因只归因「本批次是否还能续跑」。两者层级不同、不得互相推导或互相替代：fleet 级把来源访问被拒或网络不可达判为本批次不可续跑（需要新的 `retryOf`），并不表示实体级 `探测失败` 的实体不可再被探测；实体级的可续跑 refs 正是该 `retryOf` 的输入。
- 每个候选实体只有一个首要失败原因，实体不得同时挂多个并列首要原因，也不得只留下无法回到具体实体的计数。候选级与页面级的细粒度拒绝原因必须聚合到实体级，且聚合后能按下列四类分别量化：`缺席` 为「无可合法取得来源」，`在场不足` 的两个子原因分别为「抓到但正文篇幅不足」与「抓到但不是本实体」，`探测失败` 为「判定未完成」单独计量、不并入前三类。
- 候选级拒绝原因的闭集由其 owner 节点维护。owner 新增一类拒绝原因时必须同时归入本 REQ 的四态之一及其子原因；尚未归类的原因必须使该候选所属实体以 `探测失败` fail closed 并点名该未归类原因，不得静默归入 `缺席` 或 `在场不足` 而污染已完成判定的三类计量，也不得被丢弃。
- 同一实体在来源预筛、auto_research 与 content_plan 三个阶段的 ready 判定必须可按实体逐一对齐。任一阶段 ready 数下降时，必须能精确列出在该阶段出局的是哪些实体及其首要原因，不得只保留两个互不可对账的阶段计数。
- 站点与 provider 级抓取准入、候选级相关性判定的闭集及其不可变审计证据，以及 workload receipt 的 target/selected/qualified/finalized/discarded/shortfall 计数口径，由 `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md` 的 `REQ-003` 与 `REQ-004` 拥有。本 REQ 只消费其逐候选判定结果做实体级聚合与准入，不复制该闭集，也不建立第二套来源台账。

<a id="req-002"></a>
### REQ-002 唯一入池路径、结果五态与可重入恢复面

- 新内容的唯一写路径固定为 reviewed delivery intent → drain → canonical 单对象事务。drain 是可 partial 的 process manager，单对象事务是原子与幂等单位。current WorkRequest execution 不得经历史 raw backfill/pool-append 直写路径绕过 reviewed delivery intent，backfill 只保留历史迁移能力。
- 单对象结果互斥为 `appended|replayed|pending|excluded|blocked`，满足 `total = appended + replayed + pending + excluded + blocked`、`poolDelta = appended`。用户汇总只从既有 handoff、SourcePool、review 与 drain facts 的只读投影派生，不新增可写台账。
- compile 与 drain 的所有非成功终态必须提供结构化 `nextAction + reentryRef`；action 取值来自最小闭集（补输入、重试来源发现、扩范围、换来源策略、采集或重试、修证据、修 identity、选新 identity、恢复交付、无动作），`reentryRef` 必须绑定原 handoff/request/intent 摘要。
- 入池冻结证据必须绑定 batch 输入摘要、逐对象 record（`contentVersion/recordSequence/结果态`）与 post-apply 池 readback，不得只引用一次终端输出；追加过程中断（含尾部快照刷新失败窗口）必须可重入且不产生半可见对象。
- 同一冻结请求 exact replay 时全部已入池对象 `poolDelta=0`、record-set digest 与既有 record 字节不变；漂移返回 typed conflict 且零写入。
- lineage 不复制：submission/envelope 不新增请求摘要冗余字段，回溯沿既有 execution 身份 join（compile receipt ↔ envelope ↔ delivery intent ↔ pool record）。

## 4. 契约引用

- 媒体来源准入：`quwoquan_data/schema/execution/source_qualification_result.schema.json`
- media workload object：`quwoquan_data/schema/execution/media_work_unit.schema.json`
- compile result：`quwoquan_data/schema/execution/work_request_compile_result.schema.json`
- drain result：`quwoquan_data/schema/execution/pool_delivery_drain_result.schema.json`
- lane receipt：`quwoquan_data/schema/execution/content_campaign_lane_receipt.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 article 在冻结 target set 前完成来源预筛且四态不塌陷

- GIVEN 一个 article execution 的候选实体中分别存在六类实体：允许闭集内有可锚定长文来源、已锚定到本实体但正文篇幅不足、可读但未锚定到本实体、允许闭集内存在候选但不可合法取得或不可读（被 robots/服务条款、登录或验证墙、允许路径之外排除）、允许闭集内不存在候选、以及探测在得出结论之前被中断；另有一个实体同时含未达门槛候选与判定未完成候选，还有一个实体的候选携带闭集之外的未归类拒绝原因。
- WHEN 该 execution 进入 target set 冻结之前的来源预筛。
- THEN 前六类实体分别得到 `在场可用`、带「篇幅不足」子原因的 `在场不足`、带「不是本实体」子原因的 `在场不足`、带「不可取得」子原因的 `缺席`、带「无候选」子原因的 `缺席`、以及 `探测失败`；任一态都不表述为空值、空集合或零计数，未完成的判定也不被报告为确定缺席。
- THEN 混合候选的那个实体按归并优先级得到 `探测失败` 而不是 `在场不足`。
- THEN 携带未归类拒绝原因的那个实体以 `探测失败` fail closed 并点名该未归类原因，不被归入 `缺席` 或 `在场不足`。
- THEN 只有 `在场可用` 的实体进入冻结的工作单元，其余三态的实体不进入 auto_research、download 与 content_plan。
- THEN `探测失败` 携带精确可续跑 refs，`在场不足` 与 `缺席` 携带不可续跑的判定依据；`缺席` 的两个子原因分别指向修来源闭集与换实体，`在场不足` 的两个子原因分别指向调整篇幅门槛或换实体与扩来源闭集。
- THEN 每个非成功终态都能被运营者直接读取并据此决定续跑、修来源闭集或换实体；预筛在 execution spec 冻结之前终止时同样留下该终态，而不是只留下进程退出码或异常字符串。

<a id="gwt-002"></a>
### GWT-002 预筛不承诺规模且实体级首要原因可跨阶段对账

- GIVEN 一个 quota 为 N 的 article lane，其首轮候选经预筛后 `在场可用` 数小于 N，且补采轮次预算尚未耗尽。
- WHEN 该 lane 执行预筛与补采直到补采预算耗尽，并继续走到 auto_research 与 content_plan。
- THEN 补采按既有轮次机制补充候选并重新预筛；quota 不被静默下调，未通过预筛的实体不被 padding 进工作单元。
- THEN 补采耗尽后仍不足时，lane 以 `在场可用` 经冻结期准入后的实际集合继续执行并进入 `partial`；只有该集合为零才 `blocked`，且该 `blocked` 按两种零分别携带证据。
  零 `在场可用` 的那种携带实体级首要原因。`在场可用` 非空而经冻结期准入后为零的那种携带准入侧的逐实体排除证据与「全部候选实体被选择器准入排除」这一批次级原因，不以实体级首要原因冒充。
- THEN 每个出局实体只有一个首要失败原因，「无可合法取得来源」「抓到但正文篇幅不足」「抓到但不是本实体」「判定未完成」四类的分子、分母与占比可直接由实体级聚合算出，第四类单独计量而不并入前三类。
- THEN lane 终态为 `published` 或 `partial` 时，`探测失败` 实体的可续跑 refs 仍留在同一呈现面；实体级可续跑判定不被 fleet 级「本批次不可续跑」的归因覆盖。
- THEN 来源预筛、auto_research 与 content_plan 三个阶段的 ready 判定可按实体逐一对齐；任一阶段 ready 数下降时可精确列出出局实体及其首要原因，而不是只留下两个互不可对账的阶段计数。

<a id="gwt-003"></a>
### GWT-003 media quota 按内容对象执行并隔离逐资产失败

- GIVEN 一个 image/video workload 的 `quota` 大于唯一实体数，且 immutable acquisition receipts 接受了同一实体下的多个不同资产。
- WHEN materialization 从 capsule 已验证的 manifest/receipt exact pair 投影 source selection 与 content plan。
- THEN `targetObjectCount` 等于可映射 accepted assets 数，`targetEntityCount` 等于唯一 canonical coverage target 数；`approvedQuota` 保留请求对象下限，不得按实体数静默降低。
- THEN 每个 workUnit 精确绑定一个 receipt/asset/content digest 与一个 canonical coverage target，并只生成一个具有相同 `workUnitId` 的 brief/content object；同一实体允许多个 workUnit。
- THEN 无关实体不得 padding；无法映射或歧义的单资产写 typed exclusion，局部 source/safety 失败只形成该 workUnit shortfall。仍有至少一个真实对象时继续 partial，零对象才 blocked。

<a id="gwt-004"></a>
### GWT-004 全新媒体先完成来源准入再于 execution 后完成独立内容审核

- GIVEN 干净输出根中没有可复用的 Image/Video independent review receipt，运营者为同一目标实体取得全新媒体，并分别冻结 acquisition、像素或运动媒体探测、rights attribution 与 source-scoped semantic review。
- WHEN 系统从这些证据构建首个 media SourcePool、编译 WorkRequest 并执行 author/reviewer。
- THEN catalog、acquisition、source review 与其 path evidence 均可从一个 portable evidence root 逐字节解析；绝对路径、`..`、symlink、缺失 ref 或 digest drift 返回 typed blocked，且零 SourcePool candidate 可见。
- THEN SourcePool 只确认物理来源可供 execution 使用，不把 source-scoped review 表述为内容级 independent review；execution manifest、author evidence 或 reviewer evidence 尚未形成时，SourcePool 可调度但 canonical publish 仍为零。
- THEN execution 后 acquisition、author、reviewer 使用三个互异且可回读的 runId，accepted `independent_asset_review_receipt` 精确绑定同一 asset bytes、对象、模型身份与判断；该 receipt 缺失、blocked 或 identity drift 时 publish/release fail closed。
- THEN Image 与 Video 各自独立满足上述链路；任一 Video `entityMatch=mismatch` 即保持 `DATA.SOURCE.SAFETY_REVIEW_BLOCKED`，不得因 playable、4K、premium eligible 或已有下载字节进入 SourcePool。
- THEN accepted receipt 形成后，同一对象只被 canonical append 一次；重放得到相同摘要，异字节或重复身份在写前失败。

<a id="gwt-005"></a>
### GWT-005 唯一入池路径的结果五态、恢复重入与 exact replay 零增量

- GIVEN 一份 confirmed 按需请求的载体生产已产出若干 reviewed delivery intent，其中部分对象合格、部分因证据或身份问题不可入池，且随后同一冻结请求被 exact replay。
- WHEN drain 消费这些 intent 并执行 canonical 单对象事务，随后运营者读取汇总并执行 replay。
- THEN 每个对象恰好落入 `appended|replayed|pending|excluded|blocked` 之一，`total = appended + replayed + pending + excluded + blocked` 且 `poolDelta = appended`；任一失败对象不撤销同批其他已合格对象。
- THEN 每个非成功终态携带最小闭集内的结构化 `nextAction` 与绑定原 handoff/request/intent 摘要的 `reentryRef`；运营者只读终态即可执行恢复，不需要读运行日志。
- THEN 入池证据绑定 batch 输入摘要、逐对象 record 与 post-apply 池 readback；追加过程在尾部快照刷新窗口被中断后重入，不产生半可见对象或重复 record。
- THEN current WorkRequest execution 尝试经 raw backfill 直写路径入池被拒绝为 typed blocked；唯一合法路径仍是 reviewed delivery intent → drain → 单对象事务。
- THEN exact replay 得到 `appended=0`、全部既有对象 `replayed`、`poolDelta=0`，record-set digest 与既有 record 字节不变；任一输入漂移返回 typed conflict 且零写入。

## 6. 依赖

- 前置要求：[`work-request-compilation`](../work-request-compilation/spec.md) 交付的 confirmed WorkRequest 与逐载体 envelope。
- 上游事实：来源发现产出的 source-ready SourcePool、独立审核结果与权利证据。
- 下游结果：canonical 内容池的合格唯一对象 record，供 [`multi-carrier-release`](../multi-carrier-release/spec.md) 构建 immutable release。
- 父级设计：`DEC-022`、`DEC-026`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 article 来源预筛的判定阈值与探测预算 calibration

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺少 article target set 冻结前的来源预筛实现、四态契约与受治理阈值 receipt。现有 `confirmed|blocked` homepage 契约会把 `在场不足`、`缺席`、`探测失败` 塌陷成同一状态；现有 `matchConfidence`、成稿最小字数与首轮 `oversampleFactor` 也不是合法预筛阈值来源。
- 尚缺实现：实体锚定判定、最小正文门槛、单实体探测预算、补采重筛、四态聚合和三阶段逐实体对账尚未接入 article target selection。
- 尚缺验收证据：缺少受治理 provider-state 下拒绝、超时与探测预算耗尽的 api_integration，以及一次真实 execution 的 selection、auto_research、content_plan receipt 对账。
- 完成判定：`GWT-001` 与 `GWT-002` 的全部结果子句成立，且预筛阈值与探测预算来自 calibration receipt，而不是默认常量或从成稿质量门挪用的数值。M1 的单实体 article 实例通过不关闭本 OPEN；只有对初始支持 provider/source strategy 矩阵完成预筛 calibration 与直接证据后才关闭或收窄。
- 依赖：Data owner 先在可代表主清单冷门实体占比的样本上完成受治理预筛 calibration，再实现四态准入与补采。local_contract 覆盖四态、子原因、归并优先级、补采和两种零合格终态。api_integration 覆盖真实探测状态与三阶段对账。环境消费证据由 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的 `OPEN-001` 承接。

<a id="open-002"></a>
### OPEN-002 media workUnit 复合验收的直接证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 media workUnit 的完整实现与验收证据。已有多资产 projection 与逐资产 typed exclusion 测试，但未以子句级证据证明数量三值、manifest/receipt exact pair 与 brief/content object 的同一 `workUnitId` 全部闭合，不能把文件存在或父锚点引用冒充完成。
- 尚缺实现：projection 导出面必须让 brief 与 content object 逐一保留输入 workUnit 的同一稳定 identity，并在无法唯一映射时只排除该资产。
- 尚缺验收证据：缺少对数量三值、exact pair、同一 `workUnitId` 与 partial/blocked 分界的逐子句直接断言。
- 完成判定：`GWT-003.t1`、`GWT-003.t2`、`GWT-003.t3` 均由 local_contract 直接绑定，其中 `t2` 必须断言 brief 与 content object 保持同一 `workUnitId`。
- 依赖：Data media owner 补齐直接断言；不得放宽验收或以 OPEN 本身冒充通过。

<a id="open-003"></a>
### OPEN-003 首个 Image/Video SourcePool 的审核身份与 evidence-root 无法自举

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前全新媒体即使已经完成 acquisition 与 source-scoped semantic review，`project-candidates` 仍强制要求 `independent_asset_review_receipt`；该 receipt 又要求 content execution manifest、author 与 reviewer execution 身份，而 WorkRequest 在 execution 前必须先消费完整 SourcePool，形成 `SourcePool -> execution -> independent review -> SourcePool` 启动环。当前 Image catalog 的 `pathEvidence.ref` 还相对另一个 `image-input` 根，严格单 evidence-root 投影首先返回 `DATA.SOURCE.POOL_INVALID`，不能靠复制 JSON、`..` 或绝对路径绕过。
- 尚缺实现：冻结 media source admission 与 post-author independent review 的单向阶段边界；首波 SourcePool 必须能消费同一 portable evidence root 下的 acquisition/source-review 事实，但不得提前宣称内容级 rights/quality review 已完成。execution 后仍必须由不同 runId 的 author/reviewer 生成 accepted independent receipt，且 publish/release 在该 receipt 缺失时 fail closed。catalog、acquisition 与所有 path evidence 必须由 CLI 从同一可解析根重新冻结。
- 尚缺验收证据：缺少从“仓内无既有 media review receipt”的干净输出根开始，依次完成 Image/Video acquisition、source-pool projection、WorkRequest、author/reviewer、independent review、publish 的 api_integration；还缺 catalog ref-root 漂移、reviewer local-root 漂移和 execution 身份缺失的 typed blocker 断言。
- 完成判定：`GWT-004.t1..t5` 由同一 M1 intent 的 api_integration 直接覆盖：Image/Video 各有一个全新 asset，从 portable acquisition/source review 进入 SourcePool，执行后生成三个互异 runId 的独立 review closure，并在 accepted receipt 前零 canonical 可见、accepted receipt 后各精确一个对象可发布；任一 root/digest/identity 漂移均输出稳定 typed blocker。
- 依赖：对象边界与时序由 [L2 DEC-022](../design.md#dec-022) 冻结；Video 仍需一个与目标实体语义匹配且权利链可治理的真实候选，当前铁路视频的 `DATA.SOURCE.SAFETY_REVIEW_BLOCKED` 不得重包装为通过。

<a id="open-004"></a>
### OPEN-004 恢复面、唯一入池路径与首次真实入池证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 compile/drain 的非成功终态缺统一 `nextAction + reentryRef`，`pool-append --apply` 仍可绕过 reviewed delivery intent，入池冻结证据只引用终端输出，且从未有一份 confirmed 请求的对象真实进入 canonical 池并通过 exact replay 零增量验证——引擎不可复用的直接表现正是这条路径从未一次走通。
- 完成判定：`GWT-005` 全部结果子句由 local_contract（五态守恒、nextAction/reentry、重入窗口、backfill 拒绝、replay 单义）与真实 typed 请求的 api_integration（首次 Article M1 入池 `appended=1/poolDelta=1`、exact replay `poolDelta=0`）直接 `spec_ref`。
- 依赖：入池原子性与唯一写路径由 [L2 DEC-026](../design.md#dec-026) 冻结；编译面阻断由 [`work-request-compilation`](../work-request-compilation/spec.md) 的 `OPEN-003` 先行关闭。
