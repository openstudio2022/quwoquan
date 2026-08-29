# L3 Story：来源发现阶段的调度与存活可判定 (`source-discovery-scale-reliability`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-014 / SCN-035`](../../../spec.md#scn-035)
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-011](../design.md#dec-011)

## 1. 用户价值

作为内容运营者，我希望来源发现阶段在任何规模下都以冻结的并发上限调度、单实体失败即释放额度并由下一实体接管，且阶段运行期间的存活与进度只读统一进度面即可判定，从而长时间来源发现不再表现为与「进程已死」无法区分的静默，规模增长也不会丢失任何实体的终态。

## 2. 范围与非目标

### In Scope

- 来源发现阶段的有界并发、slot 释放与接管、全部实体逐一终态。
- 来源发现阶段运行中的心跳、进度面与 typed 过期判定。

### Out of Scope

- ReliableTask 交付阶段的并发与截止（由 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的执行策略拥有）。
- 心跳间隔与过期阈值的标定过程本身（标定与冻结归 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的 governed capacity calibration；本节点只消费冻结后的取值）。
- 单实体来源判定的四态语义（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 来源发现有界并发且不丢实体

- 来源发现阶段任一时刻同时运行的 worker 数不得超过执行策略冻结的 `autoResearchMaxConcurrentWorkers`，该峰值不随实体数增长；上限的合法来源只有 immutable execution policy。
- 并发上限不得导致任何已冻结候选实体被丢弃、跳过或与其他实体合并；每个实体必须获得独立 typed 终态。
- 本阶段只有一层排程。待处理实体一次性交给同一个有界调度器，不得在调度器之外再按上限切批：额外的批次边界会形成栅栏，让先完成的额度空等本批最慢的实体，失败或超时释放的额度也无法被下一个实体接管。实体数不改变调度语义，小规模不得走另一套终态与报告口径。
- 单个实体超时或失败只终结该实体，其占用的并发额度必须立即释放并由下一个待处理实体接管，其余实体继续跑到各自终态。逐实体终态是闭集，成功、失败与超时各自独立，失败与超时不携带实体报告，成功终态必须携带。
- 一次排程为什么停下来是显式闭集：全部实体已得出终态、阶段级无进展、冻结批次准入截止到点。后两者下未得出终态的实体必须按身份原样交回续跑，既不被记成任何终态，也不与已得出终态的实体混在同一集合里。
- 阶段报告如实记录实测峰值并行数与冻结上限，两者是两个词元，不得互换或合并成一个 worker 数；elapsed 与每分钟实体数自带「本次运行事实」声明位，读者不需要从数值形态去猜它是不是稳态吞吐或容量结论。

<a id="req-002"></a>
### REQ-002 来源发现阶段运行中的存活与进度可判定

- 来源发现阶段在尚未终止时必须可判定存活与进度：阶段进程必须按执行策略冻结的心跳间隔持续写入运行中进度面，写入时机独立于任何单个实体是否得出终态。只在实体终态时写一次不满足本要求——单个实体的来源发现耗时可以远大于任何可接受的存活判定间隔，此时运营者读到的是一段与「进程已死」无法区分的静默。
- 该判定不得依赖进程外旁证。连接数、CPU 占用、进程是否仍在进程表内、进度文件 mtime 猜测与日志尾部都不是合法判定面；运营者只读该进度面即可区分「仍在推进」「已停止推进」「已终止」，不需要另行取证。
- 进度面必须携带足以定位当前工作的阶段身份与进度事实：本次冻结的候选实体总数、已得出终态的实体数、仍在运行的实体身份，以及最近一次心跳的时刻。「尚未有任何实体得出终态」是在场为空——总数已知、完成数为 0 且阶段状态为运行中；它不得与「阶段已死」或「进度面缺席」表述为同一种结果。
- 超出冻结阈值仍未推进必须是 typed 过期状态，并区分「阶段仍在运行但未按间隔心跳」与「阶段已终止且不会再心跳」两个结论。进度面缺席、不可读、缺必需字段或阶段状态落在契约声明的闭集之外，同样各自是独立的 typed 失败，不得塌陷为进度为零、不得默认判为存活，也不得静默沿用上一份快照冒充当前事实；读取面每次都重新读盘。阶段终止时最后一次心跳的事实必须保留，不得被清零或覆盖为空。
- 心跳只表达存活与进度，不表达吞吐承诺。心跳中的 elapsed、已完成实体数与每分钟实体数只是当次运行事实，不得被表述为已测得的稳态吞吐或容量结论，也不得改变 dispatch、对象准入、publish、finalize 与 milestone 结果。
- 本 REQ 与执行策略容量语义的分工：批次并行上限、绝对截止与终止后运行回执的可复核性由 [`multi-carrier-release`](../multi-carrier-release/spec.md) 的执行策略拥有；本 REQ 只约束阶段仍在运行期间的存活与进度可判定性。两者不得互相推导——心跳仍在推进不表示批次剩余时间未耗尽，剩余时间未耗尽也不表示阶段仍存活。心跳也不得被写回运行回执充当第二套容量或截止结论。
- ReliableTask 交付阶段不在本 REQ 范围内：它的静默窗口已由单对象 wall-clock 上限与逐工作单元 typed 终态限定，不重复约束。
- 心跳间隔与过期阈值是受治理取值，合法来源只有两处显式声明：governed 模式取 capacity calibration receipt 的 `frozenLiveness`，bounded 模式取 bounded execution authority policy 里同名的显式声明。两处都缺席即装配期判否，不得回落默认常量，也不得从 `autoResearchMaxConcurrentWorkers`、`objectWallClockSeconds` 或 `completionGraceSeconds` 挪用数值——容量结论与存活阈值是两组取值，字段集不重叠。过期阈值必须严格大于心跳间隔，否则一次正常间隔就会被读成失联。
- `frozenLiveness` 的取值必须能指回本次标定的实测证据：下界不低于实测的一次心跳写入开销，上界不高于实测单实体耗时所允许的检测粒度，过期阈值由显式声明的漏跳容忍次数从间隔推出。以「文件最近被写过」推断存活始终不成立。

## 4. 契约引用

- execution capacity policy：`quwoquan_data/schema/execution/execution_spec.schema.json`
- managed agent scheduler 观测：`quwoquan_data/schema/execution/execution_state.schema.json`
- 来源发现阶段统一进度面：`quwoquan_data/schema/source/source_discovery_stage_progress.schema.json`
- 受治理存活阈值：`quwoquan_data/schema/execution/governed_capacity_calibration_receipt.schema.json` 的 `frozenLiveness`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 来源发现并发有上限且不丢实体

- GIVEN 一个已冻结 execution 的执行策略把 `autoResearchMaxConcurrentWorkers` 冻结为 8，其 frozen target set 含 180 个实体，且单个实体的来源发现可被外部信号挂起与放行。
- WHEN 该 execution 进入来源发现阶段，一次性对全部 180 个实体排程。
- THEN 任一时刻处于运行中的来源发现 worker 数不超过 8，该峰值不随实体数增长。
- THEN 180 个实体全部得到逐实体终态，没有实体因为并发上限被丢弃、跳过或与其他实体合并。
- THEN 单个实体超时或失败只终结该实体，释放的额度立即被下一个待处理实体占用，其余实体继续跑到各自终态。
- THEN 阶段报告如实记录实测峰值并行数与冻结上限；elapsed 与每分钟实体数只是本次运行事实，不得被表述为已测得的稳态吞吐或容量结论。

<a id="gwt-002"></a>
### GWT-002 来源发现阶段运行中可判定存活且心跳不塌陷

- GIVEN 一个已冻结 execution 进入来源发现阶段，其冻结的候选实体中至少有一个实体的来源发现耗时远大于冻结的心跳间隔，且该实体何时得出终态可由外部信号控制。
- WHEN 该阶段启动后运行到首个实体终态之前，运营者读取运行中进度面。
- THEN 首个心跳之后、首个实体终态之前，进度面仍按冻结间隔持续推进且最近心跳时刻随之前移；该判定不读取连接数、CPU 占用、进程表或文件 mtime 猜测。
- THEN 该时刻的进度面表述为「候选实体总数已知、已得出终态的实体数为 0、阶段状态为运行中」，并可读出仍在运行的实体身份；它不表述为进度缺席、阶段已终止或零计数失败。
- THEN 承载该阶段的进程被强制杀死后，进度面停止推进，超出冻结阈值时得到 typed 过期状态，且该状态区分「运行中未按间隔心跳」与「已终止不会再心跳」；最后一次心跳的事实仍可读，不被清零或覆盖为空。
- THEN 进度面缺席、不可读或缺必需字段时得到 typed 失败结果，不被读成进度为零，不被默认判为存活，也不被上一份快照冒充为当前事实。
- THEN 心跳中的 elapsed、已完成实体数与每分钟实体数只作为当次运行事实呈现，不表述为稳态吞吐或容量结论，也不改变 dispatch、对象准入、publish、finalize 与 milestone 结果。

## 6. 依赖

- 前置要求：[`multi-carrier-release`](../multi-carrier-release/spec.md) 的 immutable execution policy 与容量来源绑定。
- 上游事实：冻结的候选实体集合，以及同一份 calibration receipt 冻结的 `frozenLiveness` 心跳间隔与过期阈值。
- 下游结果：可判定的来源发现进度与逐实体终态，供 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 的预筛与生产消费。
- 父级设计：`DEC-002`、`DEC-011`

## 7. 开放事项

无。
