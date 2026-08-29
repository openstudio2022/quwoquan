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
- homepage 正文在 `4.draft` 自检截面的派生度准入：段落相对底稿的逐字重合与正文内部的段落自我重复。
- 单对象结果互斥五态与非成功终态的结构化 `nextAction + reentryRef`。
- 同一冻结请求的 exact replay 零增量验证。

### Out of Scope

- 意图 preview 与 envelope 编译（归 [`work-request-compilation`](../work-request-compilation/spec.md)）。
- immutable release、环境导入与 App 消费（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）。
- invalid canonical identity 的修复裁决（归 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md)）。
- article 来源预筛的匹配置信度、最小正文字数与探测预算的具体数值（见 `OPEN-001`）。
- 绕过登录、付费墙、验证码、访问控制、DRM 或平台技术限制取得素材；直接生成图片或视频。
- 冻结期多样性准入的每实体累计上限与 Top-N 上限数值：阈值由多样性策略的既有 owner 单点拥有，本 Story 只消费其准入结论。
- article 载体的正文逐字重合口径与商用抄写边界（归 `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md`）。
- homepage 派生度两条判否线与段落最小字数的具体数值：数值由 vertical content supply policy 单点拥有，本 Story 只声明判据形态与判否要求（标定见 `OPEN-008`）。

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
- 池内每个对象只有「在可选集内」与「已留回执退役」两种终态，不存在既不可选又不可退役的第三态。退役对 receipt 协议之前入池、无入池事务回执因而无法 rollback 的历史对象同样可用，它逐对象写一份 create-once 退役回执，只声明该对象退出可选集，并冻结退役当时的 payloadDigest 与退役前由发现层给出的 typed 不可准入判据。
- 退役路径不接受也不写 manifest、`generator` 与审核回执，因此不能用来伪造溯源。退役请求必须先观测到发现层已给出所声明的那条 typed 判否，因此也不能把合格对象移出可选集。同参数重入 replay 出同一份回执，参数漂移返回 typed conflict 且零写入。
- 已退役与未准入是两个独立结论。退役对象不再产出 quality/eligibility 判否而计入报告的退役计数，且仍不进入可选集与任何供给计数。退役回执缺席、不可读、缺必需字段、reason 落在闭集外与 payloadDigest 漂移各自是独立 typed 结论，既不静默恢复成未准入，也不默认判为已退役。

<a id="req-003"></a>
### REQ-003 homepage 正文的派生度判否点名到段落

- 内容运营者在 `4.draft` 自检就能知道哪一段是复述原文、哪两段互为复读，而不是等独立评审读完整篇才收到驳回。判据只判正文最小字数与章节均衡时，「把底稿几行原样搬进来凑够字数」是通过成本最低的写法，自检本身在诱导复述原文。
- homepage 正文自检必须判定两条派生度事实，两者互不替代。单个正文段落相对底稿的逐字重合不能由整篇平均口径覆盖，因为一段照抄会被其余重写段落稀释到判否线以下。正文内部任意两段之间的相似度不能由精确相等去重覆盖，因为改掉两个词的复读在相等判定下不可见。
- 两条判否事实都必须点名到段落。逐字重合的判否事实携带正文段落序号与底稿 `source.clean.md` 的行号区间，自我重复的判否事实携带两个正文段落序号。只给一个总分不构成可执行的判否，作者无法据此定位要改哪一段。
- 段落序号取自面向读者的正文段落顺序，frontmatter、图文块、小标题与图片占位不占序号位。按 issue 给出的序号数到另一段等于判否不可执行。
- 判定必须确定且可复算：同一份正文与同一份底稿在任何时候得到同一组判否事实，不读运行时间、进程状态或环境。
- 两条判否线与参与判定的段落最小字数由 vertical content supply policy 单点声明，判据代码不持有默认值。逐字重合的度量粒度与整篇口径同源，同一份正文在段落口径与整篇口径下的数必须可比。
- 底稿正文文件不可定位时判否并点名该引用，不得跳过逐字重合判定。跳过等于「底稿来源单元不在场即免判复述原文」。
- 正文最小字数与章节均衡是必要条件而非充分条件。字数达标的复述原文与字数达标的复读都必须判否，不得因已满足字数门而放行。

<a id="req-004"></a>
### REQ-004 media workUnit 的对象身份保持与素材出处类别准入

- media workload 的对象身份只在 projection 导出面物化一次。每个冻结 workUnit 导出一个对象身份绑定，brief 与 content object 逐一共享同一 `workUnitId`；两侧不得各自拼装身份，因此不存在「brief 有身份而 content object 没有」或两侧身份不同的中间态。
- 对象 ref 由该绑定按 `workUnitId` 派生，是 `workUnitId` 的单向派生物，不得反向决定 `workUnitId`。
- 声明了 `workUnitId` 但无法唯一映射为一个对象（缺 canonical coverage target、摘要漂移或同一 identity 重复）时判否，只排除该资产并写 typed exclusion，同批其它资产照常绑定；绝不静默产出无身份对象。quota-only 模式没有 workUnit 声明，其对象身份不使用 `workUnitId`，两种模式由 execution spec 的 `content.workUnits` 是否声明来分叉，不靠字段是否在场推断。
- 数量三值分离：`targetObjectCount` 等于可映射 accepted assets 数，`targetEntityCount` 等于唯一 canonical coverage target 数，`approvedQuota` 保留请求的对象下限。实体维度不得改写对象下限，因此 workUnit 模式下 `approvedQuota` 允许大于 `targetEntityCount` 与 `targetObjectCount`，shortfall 仍按保留的 `approvedQuota` 计算。
- 素材水印高风险的排除判据是出处类别裁决，不是文件名或 URL 的字面匹配。裁决只读三个出处事实：上传者与权利人是否同一主体、是否经批量导入工具搬运、原始平台是否属水印高风险闭集。同一出处类别的素材必须得到同一结论，命名差异不得使结论反转。
- 三个出处事实各自是受版本控制的显式闭集（`quwoquan_data/scripts/core/media_source_provenance.py`）。闭集之外的入站取值落到各自的显式未知成员；未知成员不等价于任何放行态：它与任一其它风险事实组合时判否，也不能替代「已声明的低风险平台」。
- 排除条件有三条，命中任一即判否。第一条是原始平台落高风险闭集，且经批量导入搬运或权利人未第一手声明。第二条是经批量导入搬运且权利人未第一手声明。第三条是经批量导入搬运且原始平台落未知成员。只有权利人第一手直接上传且平台未落高风险闭集才放行。
- 采集侧与 homepage 准入读侧共用同一个裁决入口，不各持一套判据。两侧都把出处事实随素材行传入该裁决，因此同一条素材在采集与准入两个截面得到同一结论，读侧不再由 URL 或授权证明串的字面匹配决定。
- 出处事实只从素材行上与裁决入参一一对应的显式声明位解析（作者、出处、上传者、描述）。画面主题一类的描述位不算出处声明：它讲画面里有什么，不讲谁上传、谁持权、来自哪个平台。素材行一个声明位都没写时判否并给稳定 typed 理由，不静默放行也不由读侧补默认值——三个事实此时全落各自的未知成员，而未知成员不等价于任何放行态。
- CC 协议要求指明的衍生修改由 `sourceAttribution` 的必填字段承载，取值限于 `DerivedModification` 闭集（`video_frame_extraction|crop|format_conversion`）。该字段在场为空（空数组）表示发布字节相对原始素材逐字节原样，缺席不合法：两者是不同的事实，缺席时读不出发布物有没有被改过。
- 该字段只在写侧按本次交付真实发生的操作一次物化，读侧与测试替身都不得补默认值。视频交付侧从真实做过的操作派生——重编码为交付容器与编码写 `format_conversion`，取封面帧写 `video_frame_extraction`，只有来源长于交付上限而真的截断时间轴才写 `crop`；不做任何修改的采集与文本来源写空数组。
- 被排除素材保留 `policyExcluded` 处置与稳定 `reason`，不删字节；处置在 `1.download` 截面一次冻结（[L2 DEC-029](../design.md#dec-029)）。
- OCR 像素检测仍是主检测器。文件身份层的补充判据只关闭「角标低于 OCR 置信阈值但文件身份写明高风险托管源」这一漏检类，它与出处类别裁决共用同一高风险平台闭集，不构成第二套判据。

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
- THEN 池内存在 receipt 协议之前入池、无事务回执因而无法 rollback 的历史对象时该子句仍可判定：这些对象经逐对象退役写出 create-once 回执后，`pool-inspect` 的 `quality` 与 `eligibility` 转 `passed`，累计供给计数逐项不变，对象目录除该回执外字节不变且 `generator` 原样保留。
- THEN 合格可选对象的退役请求、观测到另一条 typed 判否的退役请求与闭集外 reason 各自判否且零写入，同参数重入 replay 出同一份回执，参数漂移返回 typed conflict。
- THEN 必填出处字段落地前入池的历史对象经受治理迁移补齐字段后仍满足本锚点：迁移按 append-only 追加新 record 并写入重算后的 `canonicalObjectDigest` 而不就地改写既有 record，迁移后 publish 树下全部 post manifest 与 entity 与 pool 记录按各自 schema 通过且每个对象最新 record 的 digest 与对象当前字节相符，两侧同一 `sourceAttribution` 一侧有字段一侧没有的中间态判否。

<a id="gwt-006"></a>
### GWT-006 homepage 正文的复述原文与自我重复在 4.draft 自检即判否

- GIVEN 三份字数与章节均已达标的 homepage `4.draft/page.md`：第一份有一段与底稿 `source.clean.md` 连续若干行逐字同构，第二份有两段互相几乎逐字重复（仅个别词不同），第三份全部段落各自独立改写。
- WHEN 运营者对这三个对象分别执行 `4.draft` 的正文自检。
- THEN 第一份的逐字同构段落判否，判否事实点名该正文段落序号与底稿的行号区间。
- THEN 第二份的两个复读段落判否，判否事实点名这两个正文段落序号。
- THEN 第三份不被这两条判据判否，独立改写不因与底稿共享专有名词或主题而误判。
- THEN 两条判否线与参与判定的段落最小字数取自 vertical content supply policy 的显式声明，判据代码内不存在等价数值也不接受省略阈值的调用。
- THEN 同一份正文与同一份底稿重复自检得到同一组判否事实，段落序号与行号区间逐字一致。

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
- 影响或价值：缺 article target set 冻结前预筛的受治理阈值 receipt，四态判定也未接入 target selection。`matchConfidence`、成稿最小字数与首轮 `oversampleFactor` 都不是合法预筛阈值来源。
- 已达成的部分：四态闭集、六个子原因、归并优先级、恢复方向与实体级四类计量已是单一真相源，判定未完成单独计量而不并入前三类；qualifier 现有的四个拒绝原因各自归入一态一子原因，归类表之外的取值以 `探测失败` fail closed 并点名，不被替它选成缺席或在场不足。阈值面在受治理标定值对象里与容量、存活并列声明且不提供默认常量，整段缺席即判否。
- 尚缺实现：实体锚定判定、最小正文门槛与单实体探测预算的取值尚未标定，四态判定因此尚未接入 article target selection；补采重筛与三阶段逐实体对账未接入。
- 尚缺验收证据：缺少受治理 provider-state 下拒绝、超时与探测预算耗尽的 api_integration，以及一次真实 execution 的 selection、auto_research、content_plan receipt 对账。
- 完成判定：`GWT-001` 与 `GWT-002` 的全部结果子句成立，且预筛阈值与探测预算来自 calibration receipt，而不是默认常量或从成稿质量门挪用的数值。M1 的单实体 article 实例通过不关闭本 OPEN；只有对初始支持 provider/source strategy 矩阵完成预筛 calibration 与直接证据后才关闭或收窄。
- 依赖：Data owner 先在可代表主清单冷门实体占比的样本上完成受治理预筛 calibration，再实现四态准入与补采。local_contract 覆盖四态、子原因、归并优先级、补采和两种零合格终态。api_integration 覆盖真实探测状态与三阶段对账。环境消费证据由 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的 `OPEN-001` 承接。

<a id="open-002"></a>
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
- 影响或价值：仍未有一次 confirmed WorkRequest → compile → drain → pool-append 的完整走通。入池冻结证据只引用终端输出，且从未有一份 confirmed 请求身份的对象沿该链通过 exact replay 零增量验证。对象可经 receipt 协议 publish 路径（`release publish-execution`）真实进入 canonical 池并构建 immutable release，故本缺口只阻断 WorkRequest 驱动的按需入池，不阻断 publish 驱动的入池与发布。
- 已达成的部分：两条写路径判据已单轨。compile 的五态与 drain 的逐对象终态共用同一恢复动作闭集（schema 真相源 `quwoquan_data/schema/execution/recovery_next_action.schema.json`，Python 侧 `core.control_types.RecoveryNextAction`），非成功终态各自携带 `nextAction` 与绑定 request/handoff 摘要的 `reentryRef`，成功终态则显式为 `none` 与缺席。`pool-append` 在结构校验后、任何写入前判定该批对象是否被某份已编译 WorkRequest 声明驱动，命中即整批判否为 `DATA.POOL.DELIVERY_INTENT_REQUIRED` 并点名 execution 与 WorkRequest 身份；判据只读编译包里的显式声明，不看执行工作区是否还在磁盘上。
- 完成判定：`GWT-005` 全部结果子句由 local_contract（五态守恒、nextAction/reentry、重入窗口、backfill 拒绝、replay 单义）与真实 typed 请求的 api_integration（首次 Article M1 入池 `appended=1/poolDelta=1`、exact replay `poolDelta=0`）直接 `spec_ref`。前者已达成，后者仍缺。
- 依赖：入池原子性与唯一写路径由 [L2 DEC-026](../design.md#dec-026) 冻结；编译面阻断由 [`work-request-compilation`](../work-request-compilation/spec.md) 的 `OPEN-003` 先行关闭。

<a id="open-006"></a>
### OPEN-006 homepage 目标集冻结前不预筛图片供给

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺口在于 homepage 目标集只按正文来源可得性冻结，图片供给要到 `5.review` 物化才判定，落空即 `HOMEPAGE_ASSET_SHORTFALL`，而此时该实体的调研、抽事实、组包、创作与自查成本已全部发生。实测一次 10 目标的 homepage execution：`sources` 与 `1.download` 全部判 pass 且 `candidateCount=0` 未被拦下，正文一路做到 `4.draft` 两条判据 exit 0，`5.review` 才报十个实体 `sources/*/assets` 全空；补采一轮后仍有 5 个实体 `gate_block`，逐个原因为 wiki 无 bitmap、头条百科无图、开放许可缺 audited `sourceAttribution`、以及唯一候选图低于 640×426。按该样本，长尾实体的图片供给命中率约五成，等于一半创作成本被投在注定无法物化的对象上。
- 已达成的部分：失败面是可归因的而不是笼统的——`HOMEPAGE_ASSET_SHORTFALL` 带逐实体子原因，`media_dispositions.json` 的缺席也逐实体点名，补采轮次会区分「无 bitmap」「无许可」「分辨率不足」「实体忠实度不足」四类，因此预筛所需的判据集合已经存在，只是被放在了太晚的截面。
- 尚缺实现：把图片供给探测提前到目标集冻结之前，与正文来源预筛同一截面执行；选择器需按「正文可得且图片可得」联合判定而不是只看正文，`source-ready-priority` 一类选择器要显式消费该判据。四态契约与探测预算已与 [`OPEN-001`](#open-001) 共用同一声明，图片侧的最小候选数阈值与该预算的取值仍待实测标定，未标定即判否。
- 尚缺验收证据：一个 api_integration 以真实 provider 状态证明图片供给不足的实体在目标集冻结前即被排除并给出四态子原因，且同一目标集冻结后不再出现物化期 `HOMEPAGE_ASSET_SHORTFALL`；一个 local_contract 证明「正文可得但图片不可得」的实体不会进入冻结目标集。
- 完成判定：[`GWT-001`](#gwt-001) 的预筛四态不塌陷子句同时覆盖正文与图片两条供给，即冻结目标集内每个实体都已有可物化的图片候选。
- 依赖：与 [`OPEN-001`](#open-001) 的 article 正文预筛共用探测预算与四态契约，两者应在同一截面收敛而不是各建一套。

<a id="open-007"></a>
### OPEN-007 `1.download` 截面的出处排除证据未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺 `1.download` 截面的端到端证据。截面级排除目前只有对象级证据，因此「搬运素材在下载截面即被排除」这条只由单元判据支撑，不由真实 provider 状态支撑。判据与落盘字段本身已按 [`REQ-004`](#req-004) 落地——三个出处事实的显式闭集与裁决在 `quwoquan_data/scripts/core/media_source_provenance.py`，采集侧与 homepage 准入读侧共用同一裁决入口，出处同类但文件名与 URL 不同的两条素材结论一致、素材行缺声明位时判否，衍生修改字段在 `sourceAttribution` 必填且由写侧一次物化，均由 local_contract 覆盖。
- 尚缺验收证据：一个 api_integration 证明经批量导入工具搬运且权利人未第一手声明的素材在 `1.download` 截面即被排除。用可控的本地 provider state 表达受控 provider 状态，不得用 fixture 假造通过。
- 完成判定：[`GWT-004.t4`](#gwt-004) 与 [`GWT-004.t6`](#gwt-004) 在 `1.download` 截面的素材出处排除上由 api_integration 直接绑定。
- 依赖：与 [`OPEN-006`](#open-006) 的图片供给预筛共用同一出处类别闭集；存量发布物的字段迁移见 [`OPEN-009`](#open-009)。

<a id="open-008"></a>
### OPEN-008 homepage 派生度判否线尚未经真实语料标定

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺口在于两条判否线的取值来自单批实测的两个反例而不是可代表主清单的语料标定，因此既可能漏放、也可能误伤。实测一次 10 目标 homepage execution 的独立评审：首过 1/4，驳回的 3 个里 2 个是正文质量——一个对象正文 539 字符与底稿 `source.clean.md` 第 11–13 行逐字同构，另一个 8069 字符的对象第 69 行与第 71 行几乎逐字重复。两者都通过了当时只判字数与章节均衡的 `4.draft` 自检，正文质量因此成为首过率的第一损耗源。
- 已达成的部分：判据形态与呈现面已经健全而不是缺失——两条判据已在 `4.draft` 自检截面执行，判否事实点名到正文段落序号与底稿行号区间，判否线与段落最小字数由 vertical content supply policy 单点声明且代码不持有默认值，同输入同结论已由 local_contract 覆盖。所以缺的是取值标定，不是判据机制。
- 尚缺实现：判否线与段落最小字数需按可代表主清单冷门实体占比的语料标定，标定 receipt 必须落在受版本控制真相源里并能指回逐对象判定结果。当前三个 vertical 的取值相同，标定后应允许按 vertical 分化而不是继续共用一个数。
- 尚缺验收证据：缺少一次真实 execution 的 api_integration，证明标定后的取值在该批全部对象上与独立评审的正文质量结论一致——既不放过复述原文与复读，也不把独立改写误判为逐字重合；还缺误判率与漏判率的逐对象对账。
- 完成判定：`GWT-006.t1`、`GWT-006.t2`、`GWT-006.t3`、`GWT-006.t4`、`GWT-006.t5` 均由 local_contract 直接绑定（已达成），且两条判否线与段落最小字数来自语料标定 receipt 而不是单批反例推出的初始值。标定完成前本 OPEN 不因判据已上线而关闭，因为「判据存在」不等于「判否线正确」。
- 依赖：Data owner 先在可代表主清单的样本上完成正文派生度标定；与 [`OPEN-001`](#open-001) 的预筛阈值同属受治理阈值来源问题，两者应共用同一 calibration receipt 形态而不是各建一套。

<a id="open-009"></a>
### OPEN-009 存量发布物的衍生修改字段迁移需可重新封印 digest

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：缺口在于新契约与存量实例之间存在一段未迁移的历史。`derivedModifications` 在 [`REQ-004`](#req-004) 已是 `sourceAttribution` 的必填字段，但该字段落地前入池的发布物没有这个字段。实测：`quwoquan_data/publish` 下 11 份 post manifest、6 份 entity 记录与 30 份 pool 记录缺该字段，按各自 schema 校验全部判否。当前无门禁读取这些实例，`verify all` 因此仍 OK，所以这是 track 而不是 block；但任何开始校验发布树的消费方都会在这段历史上判否。
- 尚缺实现：迁移不能靠手改字节。`manifest.json` 与 `_entity.json` 属对象根下的 canonical document，逐字节参与 `pool_payload_digest`；实测 17 个已发布对象的最新 pool 记录 `canonicalObjectDigest` 当前与对象字节逐一相符，手改这两类文件会让这 17 个封印全部漂移，而改写 pool 记录里的既有 digest 等于重写 append-only 历史。`_pool/` 被排除在 digest 之外，因此只改 pool 记录不会动 digest，但那样两侧的同一 `sourceAttribution` 会一侧有字段一侧没有，把一段历史换成一段自相矛盾的历史。
- 尚缺实现：迁移需走受治理的历史迁移路径，在补齐字段后按 append-only 重新封印——追加新 record 并写入重算后的 `canonicalObjectDigest`，而不是就地改既有 record。现有 `pool_attribution_repair` 不能直接用：它要求一份带 evidence root 的真实 source pool，且在 `payload_digest` 与绑定值不符时先判 `DATA.POOL.REPAIR_OBJECT_DIGEST_DRIFT`，正是手改字节后必然命中的那一条。
- 尚缺实现：迁移写的取值必须是真实事实而不是统一填空数组。视频对象的交付副本经过重编码与取封面帧，图片对象里存在从 JPG 转 WebP 的对象，这些都不是逐字节原样；取值应从各对象自己的 media policy 与交付记录派生。
- 完成判定：`quwoquan_data/publish` 下全部 post manifest、entity 与 pool 记录按各自 schema 校验通过，迁移后每个对象最新 pool 记录的 `canonicalObjectDigest` 与对象当前字节重新相符，且 [`GWT-005.t6`](#gwt-005) 的「协议之前入池的历史对象经迁移后字节除新增记录外不变」与 [`GWT-005.t5`](#gwt-005) 的「既有 record 字节不变」在该批对象上同时成立。
- 依赖：字段契约本身已闭合，见 [`REQ-004`](#req-004)；迁移路径与 `runtime/runtime-data-engineering` 的 canonical 入池事务共用同一 append-only 记录形态。
