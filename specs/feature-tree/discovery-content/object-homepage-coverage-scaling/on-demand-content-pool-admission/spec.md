# L3 Story：按需内容生产与 canonical 池准入 (`on-demand-content-pool-admission`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-026](../design.md#dec-026)

## 1. 用户价值

作为内容运营者，我希望同一份 confirmed 按需请求先以 identity-only candidate 冻结目标对象，再在 execution 内依次完成来源选择、字节取得、质量判断、创作与独立审核；合格对象经唯一 reviewed delivery 路径以单对象事务幂等进入 canonical 内容池，从而数量、来源与权利可复核，失败不丢已合格对象。

## 2. 范围与非目标

### In Scope

- article lane 在冻结 target set 之前完成实体级来源预筛，并把候选级拒绝原因聚合为实体级单一首要失败原因。
- image/video 的 candidate 只冻结对象身份；媒体来源、bytes/CAS 与 hard facts 在 `1.download` 形成，execution 后由 sequence-007 单一 `content_review.json` 完成独立内容/rights 审核。
- 宿主 AI 按 producer 九阶段完成来源、创作与独立 review；publish AI 对 approved 对象逐个调用 canonical 单对象事务。
- homepage 正文在 `4.draft` 自检截面的派生度准入：段落相对 `1.download` 原始 source unit 的逐字重合与正文内部的段落自我重复；自检结论冻结在 sequence-006 receipt，不形成额外业务文件。
- 单对象 approved/rejected 与非成功终态的 typed issues；通用 stage receipt 只保持 `pass|blocked`，不新增 `partial` 或 recovery action。
- 同一冻结请求的 exact replay 零增量验证。

### Out of Scope

- 意图 preview 与 envelope 编译（归 [`work-request-compilation`](../work-request-compilation/spec.md)）。
- immutable release producer handoff（归 [`multi-carrier-release`](../multi-carrier-release/spec.md)）；环境导入与 App 消费由下游环境 owner 独立拥有。
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
- article lane 必须在冻结 identity-only target set 之前完成实体级来源可得性预筛，不得只按主清单静态优先级排序、把所有可得性判断推迟到 execution 的 `sources` 或 `1.download` 才发现。该预筛只帮助宿主选择 target identity，不绑定具体 source、bytes 或 admission；homepage 与 video 的既有判定时点由各自路径拥有，本 REQ 不重复约束。
- 每个候选实体的预筛结论必须是且只能是以下四态之一。四态互不塌陷，也不得塌陷为空值、空集合或零计数：
  - `在场可用`：允许来源闭集内至少有一个可合法取得、可读，且经实体锚定判定确属该实体的长文候选。
  - `在场不足`：判定已完成，候选可合法取得且可读，但未达门槛。必须再带唯一子原因区分「已锚定到本实体但正文篇幅不足」与「可读但未锚定到本实体」；前者的运营动作是换实体或按 calibration 调整篇幅门槛，后者是扩来源闭集或换实体。同一实体同时命中两个子原因时取前者，因为它已证明本实体的来源确实存在。
  - `缺席`：判定已完成，允许来源闭集内不存在可合法取得且可读的候选。必须再带唯一子原因区分「闭集内存在候选但不可合法取得或不可读」（含被 robots/服务条款、登录或验证墙、允许路径之外排除者）与「闭集内不存在候选」；前者的运营动作是修来源闭集，后者是换实体。
  - `探测失败`：判定未完成，包括网络不可达、超时、解析中断与探测预算在得出结论之前耗尽。
- `缺席` 与 `探测失败` 的分界是「判定已完成且结论确定」与「判定未完成」，二者不得互相冒充：未完成的判定不得报告为确定缺席，确定缺席也不得表述为可续跑中断。`探测失败` 必须给出精确可续跑 refs，`在场不足` 与 `缺席` 必须给出不可续跑的判定依据。
- 同一实体的多个候选归并为实体终态时按 `在场可用` → `探测失败` → `在场不足` → `缺席` 取先者：只要存在一个合格候选即 `在场可用`；没有合格候选但仍有候选未得出结论时不得先行宣告 `在场不足` 或 `缺席`。
- 预筛的每个非成功结果必须以 typed 且运营者可直接读取的形式呈现；进程退出码、异常字符串与运行日志都不是合法呈现面。预筛在 target set 冻结之前终止时同样适用；存在部分可用 target 时 shortfall/探测失败写入 stage result artifact 与 receipt 引用，通用 receipt 仍为 `pass`，零可用或 stage-wide identity/integrity failure 才 `blocked`。
- 预筛是 target identity 选择，不是 source admission 或产量保证。`在场可用` 数少于 quota 时可由宿主在冻结 candidate bindings 前的同一真实会话继续补充候选并重新预筛，不得建立仓内补采 controller/queue、静默下调 quota 或用未通过预筛的实体 padding。探测预算耗尽后仍不足则冻结实际可用 identity 集合，并在 execution 的 stage result/typed issue 中保留 shortfall；至少一个对象可继续且无 stage-wide identity/integrity failure 时 receipt 可 `pass`，零对象或 stage-wide failure 才 `blocked`。
- 上一条的 `blocked` 有两种成因不同的零，必须分别携带对应证据，不得互相冒充。零 `在场可用` 的那种携带本 REQ 的实体级首要原因。`在场可用` 非空而经宿主 target identity selection 后为零的那种携带逐实体排除证据，并按 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的零合格原因闭集取「全部候选实体被 target identity selection 排除」；此时实体级首要原因聚合全部为 `在场可用`，用它冒充会把运营者指向一个没有问题的来源。
- 冻结期 target identity selection 是宿主 Agent 在 candidate binding 冻结前作出的显式决定，只作用于已判为 `在场可用` 的实体；它不绑定具体 source 或 admission，其出局不改变该实体的四态取值，也不计入本 REQ 的来源拒绝计量。本 REQ 的四态保持四个值，不因此新增第五态或平行状态位。
- 预筛与宿主候选补充发生在 candidate binding 冻结前，早于 execution 初始化与 `targetObjectCount` 冻结。预筛只改变 identity-only 候选集合，不改变对象下限、工作单元数与宿主并发能力的三值分离。
- 实体级预筛结果只描述本次 target 的来源事实；来源访问失败或网络不可达由宿主 AI 写 target-scoped typed issue。不得再派生 fleet 级原因或自动恢复动作；blocked 后只以新 execution 重试。
- 每个候选实体只有一个首要失败原因，实体不得同时挂多个并列首要原因，也不得只留下无法回到具体实体的计数。候选级与页面级的细粒度拒绝原因必须聚合到实体级，且聚合后能按下列四类分别量化：`缺席` 为「无可合法取得来源」，`在场不足` 的两个子原因分别为「抓到但正文篇幅不足」与「抓到但不是本实体」，`探测失败` 为「判定未完成」单独计量、不并入前三类。
- 候选级拒绝原因的闭集由其 owner 节点维护。owner 新增一类拒绝原因时必须同时归入本 REQ 的四态之一及其子原因；尚未归类的原因必须使该候选所属实体以 `探测失败` fail closed 并点名该未归类原因，不得静默归入 `缺席` 或 `在场不足` 而污染已完成判定的三类计量，也不得被丢弃。
- 同一实体在 target identity 预筛、`sources` 与 `1.download` 三个截面的结果必须可按实体逐一对齐。任一截面可继续对象数下降时，必须精确列出在该截面出局的实体及首要原因，不得只保留互不可对账的阶段计数。
- 站点与 provider 级抓取准入、候选级相关性判定的闭集及其不可变审计证据，以及 workload receipt 的 target/selected/qualified/finalized/discarded/shortfall 计数口径，由 `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md` 的 `REQ-003` 与 `REQ-004` 拥有。本 REQ 只消费其逐候选判定结果做实体级聚合与准入，不复制该闭集，也不建立第二套来源台账。

<a id="req-002"></a>
### REQ-002 唯一入池路径、typed 结果与新 execution 恢复面

- 新内容的唯一写路径固定为宿主 AI producer 九阶段在 sequence-007 receipt 中冻结每对象唯一 `content_review.json`，随后 publish AI 对每个 approved 对象直接调用 canonical 单对象事务。单对象事务是原子与幂等单位；不存在独立 review receipt、drain/process manager 或 execution 级 publish。
- 每个对象由 AI 显式提交 `published|blocked` 与 typed issues；原子事务另提供 `applied|replayed|conflict` 硬事实。汇总只读对象 receipts、review 与 transaction facts，不新增可写台账。
- 任一对象失败由 AI 在 stage CLOSE 中写 typed issue 与 evidence refs；代码不生成 nextAction/reentry 或 recovery stage。整个 execution blocked 后以新 execution 重新开始。
- 入池冻结证据必须绑定 batch 输入摘要、逐对象 record（`contentVersion/recordSequence/结果态`）与 post-apply 池 readback，不得只引用一次终端输出；追加过程中断（含尾部快照刷新失败窗口）必须可重入且不产生半可见对象。
- 同一冻结请求 exact replay 时全部已入池对象 `poolDelta=0`、record-set digest 与既有 record 字节不变；漂移返回 typed conflict 且零写入。
- lineage 不复制：producer 沿 execution manifest、sequence-006/007 receipts、唯一 draft/review artifacts、object transaction 与 pool record 回溯；release consumer 只读 canonical object package + append-only pool record 白名单。运行身份不进入 consumer identity 或 App DTO。
- 池内每个对象只有「在可选集内」与「已留回执退役」两种终态，不存在既不可选又不可退役的第三态。退役对 receipt 协议之前入池、无入池事务回执因而无法 rollback 的历史对象同样可用，它逐对象写一份 create-once 退役回执，只声明该对象退出可选集，并冻结退役当时的 payloadDigest 与退役前由发现层给出的 typed 不可准入判据。
- 退役路径不接受也不写 manifest、`generator` 与审核回执，因此不能用来伪造溯源。退役请求必须先观测到发现层已给出所声明的那条 typed 判否，因此也不能把合格对象移出可选集。同参数重入 replay 出同一份回执，参数漂移返回 typed conflict 且零写入。
- 已退役与未准入是两个独立结论。退役对象不再产出 quality/eligibility 判否而计入报告的退役计数，且仍不进入可选集与任何供给计数。退役回执缺席、不可读、缺必需字段、reason 落在闭集外与 payloadDigest 漂移各自是独立 typed 结论，既不静默恢复成未准入，也不默认判为已退役。

<a id="req-003"></a>
### REQ-003 homepage 正文的派生度判否点名到段落

- 内容运营者在 `4.draft` 自检就能知道哪一段是复述原文、哪两段互为复读，而不是等独立评审读完整篇才收到驳回。判据只判正文最小字数与章节均衡时，「把底稿几行原样搬进来凑够字数」是通过成本最低的写法，自检本身在诱导复述原文。
- homepage 正文自检必须判定两条派生度事实，两者互不替代。单个正文段落相对底稿的逐字重合不能由整篇平均口径覆盖，因为一段照抄会被其余重写段落稀释到判否线以下。正文内部任意两段之间的相似度不能由精确相等去重覆盖，因为改掉两个词的复读在相等判定下不可见。
- 两条判否事实都必须点名到段落。逐字重合的判否事实携带正文段落序号与 `1.download` 原始 source unit 的 ref/锚点区间，自我重复的判否事实携带两个正文段落序号。只给一个总分不构成可执行的判否，作者无法据此定位要改哪一段。
- 段落序号取自面向读者的正文段落顺序，frontmatter、图文块、小标题与图片占位不占序号位。按 issue 给出的序号数到另一段等于判否不可执行。
- 判定必须确定且可复算：同一份正文与同一份底稿在任何时候得到同一组判否事实，不读运行时间、进程状态或环境。
- 两条判否线与参与判定的段落最小字数由 vertical content supply policy 单点声明，判据代码不持有默认值。逐字重合的度量粒度与整篇口径同源，同一份正文在段落口径与整篇口径下的数必须可比。
- 原始 source unit 或可复核锚点不可定位时判否并点名该引用，不得要求 `source.clean.md|source.layout.json|source.quality.json`，也不得因缺少派生清洗文件而跳过逐字重合判定。
- 正文最小字数与章节均衡是必要条件而非充分条件。字数达标的复述原文与字数达标的复读都必须判否，不得因已满足字数门而放行。

<a id="req-004"></a>
### REQ-004 identity-only candidate 与 `1.download` 素材出处准入

- media candidate 的对象身份只在 immutable candidate binding 中物化一次。binding 只冻结 candidate identity、carrier 与 canonical coverage target，不携带或要求 source/media admission、acquisition、rights 或 semantic verdict。每个 candidate 的 brief 与 content object 共享同一 identity；两侧不得各自拼装身份。
- 对象 ref 由该绑定按 candidate id 派生，是 candidate id 的单向派生物，不得反向决定 candidate id。
- candidate binding 无法唯一映射为一个对象（缺 canonical coverage target、摘要漂移或同一 identity 重复）属于 stage-wide identity/integrity failure，`task init` 必须 fail closed 且零 execution 初始化；绝不只排除单个资产后继续，也不静默产出无身份对象。对象 identity 必须完全来自 immutable candidate binding。
- 数量三值分离：`targetObjectCount` 等于可映射 accepted assets 数，`targetEntityCount` 等于唯一 canonical coverage target 数，`approvedQuota` 保留请求的对象下限。实体维度不得改写对象下限，因此 workUnit 模式下 `approvedQuota` 允许大于 `targetEntityCount` 与 `targetObjectCount`，shortfall 仍按保留的 `approvedQuota` 计算。
- 素材水印高风险的排除判据是出处类别裁决，不是文件名或 URL 的字面匹配。裁决只读三个出处事实：上传者与权利人是否同一主体、是否经批量导入工具搬运、原始平台是否属水印高风险闭集。同一出处类别的素材必须得到同一结论，命名差异不得使结论反转。
- 三个出处事实各自是受版本控制的显式闭集（`quwoquan_data/scripts/core/media_source_provenance.py`）。闭集之外的入站取值落到各自的显式未知成员；未知成员不等价于任何放行态：它与任一其它风险事实组合时判否，也不能替代「已声明的低风险平台」。
- 排除条件有三条，命中任一即判否。第一条是原始平台落高风险闭集，且经批量导入搬运或权利人未第一手声明。第二条是经批量导入搬运且权利人未第一手声明。第三条是经批量导入搬运且原始平台落未知成员。只有权利人第一手直接上传且平台未落高风险闭集才放行。
- 采集侧与 homepage 准入读侧共用同一个裁决入口，不各持一套判据。两侧都把出处事实随素材行传入该裁决，因此同一条素材在采集与准入两个截面得到同一结论，读侧不再由 URL 或授权证明串的字面匹配决定。
- 出处事实只从素材行上与裁决入参一一对应的显式声明位解析（作者、出处、上传者、描述）。画面主题一类的描述位不算出处声明：它讲画面里有什么，不讲谁上传、谁持权、来自哪个平台。素材行一个声明位都没写时判否并给稳定 typed 理由，不静默放行也不由读侧补默认值——三个事实此时全落各自的未知成员，而未知成员不等价于任何放行态。
- CC 协议要求指明的衍生修改由 `sourceAttribution` 的必填字段承载，取值限于 `DerivedModification` 闭集（`video_frame_extraction|crop|format_conversion`）。该字段在场为空（空数组）表示发布字节相对原始素材逐字节原样，缺席不合法：两者是不同的事实，缺席时读不出发布物有没有被改过。
- 该字段只在写侧按本次交付真实发生的操作一次物化，读侧与测试替身都不得补默认值。视频交付侧从真实做过的操作派生——重编码为交付容器与编码写 `format_conversion`，取封面帧写 `video_frame_extraction`，只有来源长于交付上限而真的截断时间轴才写 `crop`；不做任何修改的采集与文本来源写空数组。
- `sources` 先选择来源；`1.download` 才取得 bytes/CAS、冻结 MIME/digest/probe/rights hard facts 并执行素材出处裁决。被排除素材保留 `policyExcluded` 处置与稳定 `reason`，不倒写 candidate；处置由该阶段 result refs 与 receipt 冻结。
- OCR 像素检测仍是主检测器。文件身份层的补充判据只关闭「角标低于 OCR 置信阈值但文件身份写明高风险托管源」这一漏检类，它与出处类别裁决共用同一高风险平台闭集，不构成第二套判据。

## 4. 契约引用

- 历史 source-qualification、media-work-unit、source capsule/admission pre-init 轨与 work-request compile-result execution schema 不构成现役依赖；candidate binding 只承载对象身份，现役来源事实由 `sources` plan、`1.download` source units/source refs/CAS 与后续 stage receipts 承载。
- canonical pool record：`quwoquan_data/schema/release/pool_object_record.schema.json`
- stage receipt：`quwoquan_data/schema/execution/stage_receipt.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 article 在冻结 target set 前完成来源预筛且四态不塌陷

- GIVEN 一个 article execution 的候选实体中分别存在六类实体：允许闭集内有可锚定长文来源、已锚定到本实体但正文篇幅不足、可读但未锚定到本实体、允许闭集内存在候选但不可合法取得或不可读（被 robots/服务条款、登录或验证墙、允许路径之外排除）、允许闭集内不存在候选、以及探测在得出结论之前被中断；另有一个实体同时含未达门槛候选与判定未完成候选，还有一个实体的候选携带闭集之外的未归类拒绝原因。
- WHEN 该 execution 进入 target set 冻结之前的来源预筛。
- THEN 前六类实体分别得到 `在场可用`、带「篇幅不足」子原因的 `在场不足`、带「不是本实体」子原因的 `在场不足`、带「不可取得」子原因的 `缺席`、带「无候选」子原因的 `缺席`、以及 `探测失败`；任一态都不表述为空值、空集合或零计数，未完成的判定也不被报告为确定缺席。
- THEN 混合候选的那个实体按归并优先级得到 `探测失败` 而不是 `在场不足`。
- THEN 携带未归类拒绝原因的那个实体以 `探测失败` fail closed 并点名该未归类原因，不被归入 `缺席` 或 `在场不足`。
- THEN 只有 `在场可用` 的实体进入 identity-only candidate bindings，其余三态不进入 execution；具体来源仍到 `sources` 选择，bytes/CAS 到 `1.download` 取得。
- THEN `探测失败` 携带精确可续跑 refs，`在场不足` 与 `缺席` 携带不可续跑的判定依据；`缺席` 的两个子原因分别指向修来源闭集与换实体，`在场不足` 的两个子原因分别指向调整篇幅门槛或换实体与扩来源闭集。
- THEN 每个非成功终态都能被运营者直接读取并据此决定续跑、修来源闭集或换实体；预筛在 target set 冻结之前终止时同样留下 stage receipt 引用的 typed 结果，而不是只留下进程退出码或异常字符串。

<a id="gwt-002"></a>
### GWT-002 预筛不承诺规模且实体级首要原因可跨阶段对账

- GIVEN 一个 quota 为 N 的 article lane，其首轮候选经预筛后 `在场可用` 数小于 N，且预先声明的 target 探测预算尚未耗尽。
- WHEN 宿主在同一真实会话内补充候选并重新预筛，直到 target 探测预算耗尽，再冻结 identity-only candidate bindings 并进入 `sources` 与 `1.download`。
- THEN 补采按既有轮次机制补充候选并重新预筛；quota 不被静默下调，未通过预筛的实体不被 padding 进工作单元。
- THEN 宿主在当前 OPEN stage 内结束补充后仍不足时，lane 以 `在场可用` 的实际集合继续，shortfall 写 stage result artifact/typed issue且通用 receipt 为 `pass`；只有该集合为零或 stage-wide identity/integrity failure 才 `blocked`，且零可用按两种成因分别携带证据。
  零 `在场可用` 的那种携带实体级首要原因。`在场可用` 非空而经宿主 target identity selection 后为零的那种携带逐实体排除证据与「全部候选实体被 target identity selection 排除」这一批次级原因，不以实体级来源原因为 selection 结果冒充。
- THEN 每个出局实体只有一个首要失败原因，「无可合法取得来源」「抓到但正文篇幅不足」「抓到但不是本实体」「判定未完成」四类的分子、分母与占比可直接由实体级聚合算出，第四类单独计量而不并入前三类。
- THEN stage receipt 保留每个探测失败 target 的 typed issue/evidence refs，不生成 fleet 级原因或自动恢复结论。
- THEN target identity 预筛、`sources` 与 `1.download` 三个截面的结果可按实体逐一对齐；任一截面可继续对象数下降时可精确列出出局实体及其首要原因，而不是只留下互不可对账的阶段计数。

<a id="gwt-003"></a>
### GWT-003 media quota 按内容对象执行并隔离逐资产失败

- GIVEN 一个 image/video workload 的 `quota` 大于唯一实体数，且 identity-only candidate bindings 为同一实体冻结了多个不同目标对象。
- WHEN `task init` 只按这些 binding 创建 execution，随后 `sources` 选择来源、`1.download` 取得实际 assets/bytes/CAS。
- THEN `targetObjectCount` 等于可唯一映射的 candidate identities 数，`targetEntityCount` 等于唯一 canonical coverage target 数；`approvedQuota` 保留请求对象下限，不得按实体数静默降低。
- THEN 每个 candidate 精确绑定一个 canonical coverage target，并只生成一组共享相同 candidate identity 的 brief/content object；source/asset/content digest 到 `1.download` 才形成，同一实体允许多个 candidate。
- THEN 无关实体不得 padding；candidate identity 无法映射、重复、歧义或 binding digest 漂移属于 stage-wide identity/integrity failure，task init typed blocked 且零 execution 初始化；仅局部 source/safety/bytes 失败在 `sources|1.download` 形成对应对象 shortfall。仍有至少一个对象可继续且无 stage-wide failure 时 receipt 可 pass 并带 typed shortfall，零对象或 stage-wide failure 才 blocked。

<a id="gwt-004"></a>
### GWT-004 identity-only 媒体 candidate 在 execution 内下载并由单一 review 裁决

- GIVEN 干净输出根中只有 Image/Video identity-only candidate bindings，task-init 前没有 acquisition、source/media admission 或 review receipt。
- WHEN `task init` 创建 execution，宿主依次在 `sources` 选择来源、`1.download` 取得 bytes/CAS 与机械 probe/rights hard facts、`2.quality` 判断语义/保留、`3.compose` 组织结构、`4.draft` 创作并在 `5.review` 独立裁决。
- THEN candidate binding 只冻结 target/candidate identity；实际 source refs、asset digest、MIME、probe 与 rights hard facts 均到 `1.download` 才形成并可从 portable root 逐字节解析，绝对路径、`..`、symlink、缺失 ref 或 digest drift 使当前 stage typed blocked，不倒写 candidate。
- THEN `4.draft` 每对象只留下 `image_work.json|video_script.json`，sequence-006 receipt 冻结整个 execution 的一个真实 author actor/invocation、自检与 input/output exact refs；不生成 draft meta、self-check 或 agent envelope 镜像文件。
- THEN `5.review` 由另一个真实 reviewer actor 会话执行，每对象只写 `content_review.json`，统一给出 `approved|rejected`、简短 dimensions/blockingIssues 与逐资产 rights 结论；sequence-007 receipt 冻结 reviewer actor/invocation 与 exact ref/digest，不存在独立 review receipt 第二 authority。author/reviewer 必须不同 session/runId，可为同一 model family。
- THEN Image 与 Video 各自独立满足上述链路；任一 Video `entityMatch=mismatch` 在 quality/review 保持 typed rejected，不得因 playable、4K、premium eligible 或已有下载字节被 approved。
- THEN approved/rejected 可混合且 shortfall 进入 stage result/typed issues，至少一个 approved 时 receipt 可 pass；零 approved 或 stage-wide identity/integrity failure 才 blocked。approved 对象只被 canonical append 一次，重放得到相同摘要，异字节或重复身份在写前失败。

<a id="gwt-005"></a>
### GWT-005 AI 逐 approved 对象执行唯一单对象事务

- GIVEN 一份 confirmed 请求已完成独立 review，包含多个 approved/rejected 对象。
- WHEN publish AI 只对 approved 对象逐个调用 canonical single-object transaction，并 exact replay 已成功对象。
- THEN 每对象 transaction 原子且幂等；一个对象 blocked/conflict 不撤销其它已成功对象，replay 不增加 pool record。
- THEN stage CLOSE 由 AI 显式提交每对象 verdict、typed issues、result refs 与 verifier facts；transaction 代码不生成业务 verdict、nextAction 或 recovery stage。
- THEN consumer projection 不暴露运行身份，canonical 写入单位始终是单对象事务。

<a id="gwt-006"></a>
### GWT-006 homepage 正文的复述原文与自我重复在 4.draft 自检即判否

- GIVEN 三份字数与章节均已达标的 homepage `4.draft/page.md`：第一份有一段与 `1.download` 原始 source unit 的某个锚点区间逐字同构，第二份有两段互相几乎逐字重复（仅个别词不同），第三份全部段落各自独立改写。
- WHEN 运营者对这三个对象分别执行 `4.draft` 的正文自检。
- THEN 第一份的逐字同构段落判否，判否事实点名该正文段落序号与底稿的行号区间。
- THEN 第二份的两个复读段落判否，判否事实点名这两个正文段落序号。
- THEN 第三份不被这两条判据判否，独立改写不因与底稿共享专有名词或主题而误判。
- THEN 两条判否线与参与判定的段落最小字数取自 vertical content supply policy 的显式声明，判据代码内不存在等价数值也不接受省略阈值的调用。
- THEN 同一份正文与同一份底稿重复自检得到同一组判否事实，段落序号与行号区间逐字一致。

## 6. 依赖

- 前置要求：[`work-request-compilation`](../work-request-compilation/spec.md) 交付的 confirmed carrier demand 与只冻结目标对象身份的 immutable candidate bindings。
- 上游事实：candidate identity；`sources`/`1.download` 形成的来源、bytes/CAS 与 rights hard facts；sequence-006/007 receipts 绑定的单一 draft/review artifacts。
- 下游结果：canonical object package + append-only pool record，并通过无写权限、字段白名单 handoff query 供 [`multi-carrier-release`](../multi-carrier-release/spec.md) 构建 immutable release。
- 父级设计：`DEC-022`、`DEC-026`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 article 来源预筛的判定阈值与探测预算 calibration

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺 article target set 冻结前预筛的受治理阈值 receipt，四态判定也未接入 target selection。`matchConfidence`、成稿最小字数与首轮 `oversampleFactor` 都不是合法预筛阈值来源。
- 已达成的部分：四态闭集、六个子原因、归并优先级、恢复方向与实体级四类计量已是单一真相源，判定未完成单独计量而不并入前三类；qualifier 现有的四个拒绝原因各自归入一态一子原因，归类表之外的取值以 `探测失败` fail closed 并点名，不被替它选成缺席或在场不足。阈值面在受治理标定值对象里与存活判据并列声明且不提供默认常量，整段缺席即判否。
- 尚缺实现：实体锚定判定、最小正文门槛与单实体探测预算的取值尚未标定，四态判定因此尚未接入 article target identity selection；宿主候选补充、重筛及 selection/`sources`/`1.download` 逐实体对账未接入。
- 尚缺验收证据：缺少受治理 provider-state 下拒绝、超时与探测预算耗尽的 api_integration，以及一次真实 execution 从 target selection 到 `sources`/`1.download` 的逐实体对账。
- 完成判定：`GWT-001` 与 `GWT-002` 的全部结果子句成立，且预筛阈值与探测预算来自 calibration receipt，而不是默认常量或从成稿质量门挪用的数值。M1 的单实体 article 实例通过不关闭本 OPEN；只有对初始支持 provider/source strategy 矩阵完成预筛 calibration，并取得 target selection → `sources` → `1.download` 的直接证据后才关闭或收窄。
- 依赖：Data owner 先在可代表主清单冷门实体占比的样本上完成受治理预筛 calibration，再实现四态准入与宿主在当前 OPEN stage 内的候选补充。local_contract 覆盖四态、子原因、归并优先级、shortfall 和两种零合格终态；api_integration 覆盖真实探测状态及 target selection、`sources`、`1.download` 对账。producer 真实链路由 [`multi-carrier-release` OPEN-020](../multi-carrier-release/spec.md#open-020) 跟踪，下游消费不参与关闭。

<a id="open-002"></a>
<a id="open-003"></a>
### OPEN-003 identity-only Image/Video candidate 到单一 review 的真实证据待闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：candidate 只冻结对象身份、source/media evidence 在 `1.download` 形成、post-author review 由 sequence-007 receipt 绑定的唯一 `content_review.json` 单写，但对应 Python/schema/tests 尚未实现该边界，因此真实 Image/Video execution 仍会被旧 pre-init admission 与镜像产物契约阻断。
- 尚缺实现：Python/schema/tests 尚缺 identity-only candidate、execution 内 source/media evidence、sequence-006/007 单 actor 和单一 draft/review artifact 的硬切；实现不得恢复 source-scoped review、media admission receipt、独立 review receipt 或镜像产物。
- 尚缺验收证据：缺少从 identity-only Image/Video candidates 开始，依次完成 `task init`、sources/download、quality/compose、单一 draft artifact、单一 `content_review.json`、publish 的 api_integration；还缺 portable root、actor/session、asset/draft/review digest 漂移的 typed blocker 断言。
- 完成判定：`GWT-004` 全部结果子句由同一 M1 intent 的 api_integration 直接覆盖：每个 execution 一个 author session、另一个 reviewer session，二者 runId 不同；approved 前零 canonical 可见，approved 后对象精确发布一次；任一 root/digest/identity 漂移均稳定 fail closed。
- 依赖：对象边界与时序由 [L2 DEC-022](../design.md#dec-022) 冻结；Video 仍需一个与目标实体语义匹配且权利链可治理的真实候选，当前铁路视频的 typed rejected 不得重包装为通过。

<a id="open-004"></a>
### OPEN-004 宿主 reviewed delivery 的首次真实入池证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：唯一入池判据和 receipt 协议 publish 已实现，但仍未有一次 confirmed carrier demand → identity-only candidate-backed `task init` → 宿主 producer 九阶段 → sequence-007 `content_review.json` approved → canonical append 的完整走通，也未以同一请求做 exact replay 零增量。缺口是目标单轨的真实 evidence，不是原子事务机制本身。
- contract-reset 要求删除 drain/recovery action 闭集及其 processor；新轨只保留 AI typed issues、单对象 transaction 硬事实与 pool record。规格不声称对应实现已完成。
- 完成判定：[`GWT-005`](#gwt-005) 由新 `task init` 和宿主 AI 完成 Article M1 的逐对象首次 apply 与 exact replay，并断言无 drain/process manager/recovery action 与 legacy publish 入口。
- 依赖：入池原子性与唯一写路径由 [L2 DEC-026](../design.md#dec-026) 冻结；中性初始化由 [`work-request-compilation`](../work-request-compilation/spec.md) 的 `OPEN-003` 先行关闭。

<a id="open-006"></a>
### OPEN-006 homepage 目标集冻结前不预筛图片供给

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺口在于 homepage 目标集只按正文来源可得性冻结，图片供给可能到后续 stage 才判定，落空即 `HOMEPAGE_ASSET_SHORTFALL`，而此时调研与创作成本已发生。预筛只可冻结候选 target identity 与“值得进入 execution”的来源可得性判断，不得要求 task-init 前下载 bytes、形成 source/media admission 或完成 review。
- 已达成的部分：失败面是可归因的而不是笼统的——`HOMEPAGE_ASSET_SHORTFALL` 带逐实体子原因，`media_dispositions.json` 的缺席也逐实体点名，宿主补充候选时可区分「无 bitmap」「无许可」「分辨率不足」「实体忠实度不足」四类，因此预筛所需的判据集合已经存在，只是被放在了太晚的截面。
- 尚缺实现：如保留 target selection 的轻量图片可得性探测，只能用于选择 target identity；实际来源选择、bytes/CAS、MIME/digest/probe/rights hard facts仍必须在 `sources`/`1.download` 完成。四态契约与探测预算已与 [`OPEN-001`](#open-001) 共用同一声明，图片侧阈值仍待实测标定。
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
- 影响或价值：缺口在于两条判否线的取值来自单批实测反例而不是可代表主清单的语料标定，因此既可能漏放、也可能误伤。既有反例包括正文段落与原始来源锚点逐字同构，以及正文内部段落复读；判据必须直接绑定 `1.download` 原始 source unit，不再依赖 `source.clean.md` 派生产物。
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

<a id="open-010"></a>
### OPEN-010 硬切后 media candidate 对象数量投影尚未重建直接证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前阶段为 `post_delete_projection_pending`。旧 materialization/ScaleSourcePool 编排与 workUnit schema 已删除，当前树尚无测试直接证明 media quota、对象/实体数量与 candidate identity 按 [`GWT-003`](#gwt-003) 的七条结果子句完整投影，因此数量、身份与局部失败语义尚无可执行验收保障。
- 尚缺实现：需要由当前宿主单轨从 identity-only image/video candidate bindings 创建 execution，并直接证明 `targetObjectCount`、`targetEntityCount`、`approvedQuota` 三值分离，brief/content object 共用同一 candidate identity，以及 `sources|1.download` 的来源/字节失败只影响对应对象。尚缺验收证据为上述行为的逐子句 local_contract/api_integration；不得以 pre-init admission、平行运行身份或批量写入器满足验收。
- 完成判定：[`GWT-003.t1`](#gwt-003) 至 [`GWT-003.t7`](#gwt-003) 逐条由硬切后当前实现的 local_contract/api_integration 绑定并实际通过，至少覆盖同一实体多对象、candidate identity/integrity 整体 blocked，以及局部 source/bytes shortfall 下 receipt pass。
- 依赖：identity-only candidate-backed task init 与 execution 内 media acquisition 的当前边界；fresh 四载体 producer 链路另由 [`multi-carrier-release` OPEN-020](../multi-carrier-release/spec.md#open-020) 跟踪。
