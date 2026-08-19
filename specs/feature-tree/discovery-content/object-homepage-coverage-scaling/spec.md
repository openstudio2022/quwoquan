# L2 Business Capability：对象主页与多载体供给 (`object-homepage-coverage-scaling`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

可复用实体主页与多载体内容供给、发布和环境消费闭环。

## 2. 范围与非目标

### In Scope

- family、provider policy、reference 与 execution request 的职责隔离。
- entity homepage、article、image、video 的五阶段生产、review、canonical publish 与 release。
- immutable release 的环境导入、API 验证、App 消费、rollback 与 replay 证据。

### Out of Scope

- 任何特定区域、实体、目标数量或活动阶段的运行计划。
- content library 耐久性等级、独立持有方形态、校验周期与恢复目标的具体取值（见 `OPEN-002`）。

## 3. Journey / Scenario 贡献

- [`JNY-008 / SCN-014`](../../spec.md#scn-014)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：可复用实体主页与多载体内容供给、发布和环境消费闭环。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`multi-carrier-release`](./multi-carrier-release/spec.md)：每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 可复用内容 execution 与发布 SIT

- 静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- execution packet 的 request 与 target set 均固化在 `0.plan`，且 output 删除后仍可从受版本控制的静态输入重建。
- 四类载体均能由同一 CLI 门面创建、review、promote 与聚合 release。
- homepage/article/image/video 的 quota/count 同时表达日常请求负载与累计 milestone target；日常 publish 允许 partial 并发布全部合格对象，M100 的唯一目标为 `100/100/100/10`，后继规模按当前池中唯一合格对象计算差额。
- milestone 只表示池中已达到的累计规模，不是日常 Research 发布的前驱门；历史批次、不同 source identity 与既有 release 中的合格对象可以按稳定对象身份累计，未达到目标时如实报告 gap 并继续增量发布。
- 文章配图率、素材来源分布、视频热度、automatic recovery、workspace/soak/resource samples、实际并发、重试与吞吐只记录诊断过程和统计，不改变 task dispatch、单对象的质量、授权范围或 Research 发布资格；完全重复作品不重复计数，但不阻断同批其它对象。
- homepage/article/image/video active workloads 彼此独立调度，可按可用容量串行或重叠运行，不要求固定四路并发、固定 worker 数或四个同时 workspace。每个实际启动的 task 逐项形成 typed 终态；共享 canonical publish 保持对象事务单写者，最终 Manifest/release 仍精确闭合全部被选对象与引用。
- 调度容量是上限语义而不是下限承诺：execution 冻结的并行 worker 上限与批次绝对截止只约束同时运行的进程数与总时长，与「不要求固定四路并发」并不冲突。对象下限、工作单元数与并行上限三者各自独立冻结，不得互相派生。
- release 只绑定 execution/source digest 与 desired state；环境 receipt、rollback/replay 通过 ship 写入输出。

<a id="req-002"></a>
### REQ-002 `reference/<vertical>/entities`：稳定实体、别名、分类与行政归属

- `reference/<vertical>/entities`：稳定实体、别名、分类与行政归属；不得写来源 URL 或运行结论。
- 静态资产不得包含区域、实体、日期、数量、运行路径或活动阶段；这些值只在 `0.plan` 冻结。
- 每个发布对象必须有 source、媒体处置、creator/tag 引用、review 与 execution source digest。
- 运行 profile、schema、provider policy 或 target set 改变时，必须创建新 sequence，并以 `retryOf` 关联重试。
- 环境导入、API 与 App 消费未完成时保留对应 `GATE_BLOCK`；静态目录与本地 gate 不得冒充环境交付。

<a id="req-003"></a>
### REQ-003 媒体字节唯一持有方的耐久性与引用不可兑现的 typed 呈现

- canonical publish 与 immutable release 只按内容摘要记录媒体引用，不随对象复制媒体字节；字节由单一 content library 持有。该库位于版本控制与可重建输出边界之外，因此 `REQ-001` 的「output 删除后仍可从受版本控制的静态输入重建」只覆盖 execution request、target set 与由它们派生的结构，不覆盖媒体字节——媒体字节没有任何受版本控制的真相源可供重建。
- 该库因此是这些字节的唯一持有方。「不易被例行清理误删」不是耐久性：把库迁出仓库工作树与可重建输出根只降低一次误操作的概率，不改变「丢失即永久丢失」这一事实。原始采集素材在对象产出后被回收，重新采集也不再是可依赖的退路，因此不得被计为恢复手段。
- 每一份被 canonical publish 或 immutable release 引用的媒体字节必须有显式声明的耐久性承诺：至少存在一份独立于该库主副本、且可被验证确实可恢复的持有方。该承诺未冻结或未被验证时，相关 release 的耐久性必须如实呈现为未确立；字节当前可读只证明此刻可兑现，不构成已耐久的判定。
- 引用不可兑现必须是 typed 失败，不得静默：被记录的媒体引用在库中缺席，或字节与记录的摘要、大小不一致时，读取方必须 fail closed 并给出可定位到具体引用的 typed 结果，不得返回空路径、空字节或零大小，也不得跳过该对象继续。
- 「整个持有方缺席」与「持有方在场但这一条引用缺席」必须是两个可区分的 typed 状态。库根不存在、跨卷不可引用与权限拒绝属于前者；把前者展开成逐对象的引用缺席，会把一次全局故障伪装成大量对象级质量问题，让运营者去逐个对象修一个根本不在对象上的故障。
- 耐久性等级、独立持有方形态、校验周期与恢复目标的具体取值不在本层冻结，见 `OPEN-002`。`specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md` 的备份恢复与 RPO/RTO 口径以生产数据库与远端加密副本为恢复目标，content library 不在其恢复目标内；本 REQ 只声明本持有方自身的耐久性要求，既不复制也不替代那套口径。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 可复用内容 execution 与发布 SIT

- GIVEN 执行“可复用内容 execution 与发布”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“可复用内容 execution 与发布”对应动作。
- THEN 静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- THEN execution packet 的 request 与 target set 均固化在 `0.plan`，且 output 删除后仍可从受版本控制的静态输入重建。
- THEN 四类载体均能由同一 CLI 门面创建、review、promote 与聚合 release。
- THEN 池按稳定对象身份累计四类唯一合格对象，M100 只以 `100/100/100/10` 判断目标是否达到；未达到时返回 gap，已合格对象仍可形成 partial Research release。
- THEN 文章配图、来源分布、视频热度、automatic recovery、workspace/soak/resource samples、实际调度重叠、重试与吞吐保留为诊断统计，且其缺失、失败或变化不改变 task dispatch、质量合格并具有目标环境使用范围的对象准入或规模 promotion 结果。
- THEN 每个实际启动的 task 分别形成 typed 终态；排队、未启动或诊断 sample 不算 task 结果。canonical publish 以单写对象事务接收已合格对象，最终 Manifest/release 对被选对象及引用做 exact closure。
- THEN 对象下限、工作单元数与并行 worker 上限在 execution 中各自独立冻结，任一项都不由另一项派生；批次绝对截止跨进程重启不续期，运行回执可复核实际并行峰值、wave 数与该截止。
- THEN release 只绑定 execution/source digest 与 desired state；环境 receipt、rollback/replay 通过 ship 写入输出。

<a id="sit-002"></a>
### SIT-002 媒体字节持有方可兑现、故障可区分且耐久性不被默认宣称

- GIVEN 一个 immutable release 的全部媒体引用都按内容摘要记录，字节只由 content library 持有，且该库位于版本控制与可重建输出边界之外。
- WHEN 分别构造四种情形：全部引用可兑现、单条引用的字节在库中缺席、单条引用的字节与记录的摘要或大小不一致，以及整个库不可达。
- THEN 全部引用可兑现时该 release 的媒体闭包成立，且该结论不依赖 release 目录内是否另存一份媒体字节副本。
- THEN 单条引用缺席或与记录不一致时读取方 fail closed，并给出可定位到该条引用的 typed 结果；不返回空路径或零大小，也不跳过该对象继续。
- THEN 整个库不可达与单条引用不可兑现产生两个可区分的 typed 状态，前者不被展开成逐对象的引用缺席。
- THEN 独立于库主副本的持有方被冻结并在隔离恢复目标上验证可恢复之前，该 release 的耐久性如实呈现为未确立；配置存在或字节当前可读都不足以呈现为已耐久。
- THEN 「可重新采集原始素材」不被计入任何恢复路径，原始采集素材已被回收后该结论不变。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 可复用内容 execution 与发布 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 content library 是媒体字节的唯一持有方，耐久性承诺尚未冻结

- 类型：`risk`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：媒体字节的落点已从受 Git 版本控制的 publish 树切换到 content library CAS，库也已迁出仓库工作树、落到用户数据目录（XDG 数据目录约定），以避免被 `git clean -xdf` 或可重建输出根的清理误删。这解决的是误删概率，没有解决持有唯一性：库现在是这些字节的唯一持有方，而它们不可从任何受版本控制的真相源重建。原始采集素材在对象产出后被回收、字节进 CAS 去重之后，连重新下载的退路也在收缩。当前既没有备份、没有第二份副本，也没有周期性可兑现校验，因此一次卷损坏、一次误删或一次目录迁移就会让已发布 release 的媒体闭包永久不可兑现。这一风险在 release 侧目前还不可见——`REQ-001` 的可重建承诺覆盖不到媒体字节，读者却容易据此认为已经覆盖。
- 完成判定：`SIT-002` 的全部结果子句成立，且独立持有方形态、校验周期与恢复目标来自显式冻结的耐久性承诺，而不是「库当前可读」这一观测。
- 依赖：Data owner 与 Ops owner 共同裁决独立持有方的形态与恢复目标，并冻结校验周期；具体取值属于 calibration 与运维裁决，不在本层规格冻结。证据层分派为：`SIT-002.t1`、`SIT-002.t2`、`SIT-002.t3` 与 `SIT-002.t5` 由 local_contract 在隔离库根上构造可兑现、引用缺席、摘要或大小漂移与库整体不可达四种情形，断言媒体闭包成立与三类互不塌陷的 typed 结果，fixture 只证明控制逻辑，不得当作耐久性结论；`SIT-002.t4` 必须由 api_integration 在真实独立持有方与隔离恢复目标上证明确实可恢复，配置存在或字节当前可读都不构成证据。本能力不改变 App 用户可见终态，因此不追加 user_acceptance；四环境的 release 消费证据继续由 `multi-carrier-release` 的 `OPEN-001` 承接。
