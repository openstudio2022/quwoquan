# L2 Design：对象主页与多载体供给 (`object-homepage-coverage-scaling`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“可复用实体主页与多载体内容供给、发布和环境消费闭环”需要 `multi-carrier-release` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：可复用实体主页与多载体内容供给、发布和环境消费闭环。
- 设计目标：调度容量以上限语义冻结进不可变 execution，运行回执可被运营者单独复核并据此决定续跑、修来源还是重新冻结时间预算。
- 设计目标：article lane 在冻结 target set 之前就把实体级来源可得性判成互不塌陷的四态，运营者只读终态即可决定续跑、修来源闭集还是换实体。
- 设计目标：内容运营者的 typed intent 在写入 execution 事实前经过 preview 与显式确认，并只编译到现有 carrier request envelope。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。
- 容量数值由 Story 的受治理 calibration 决定：`local-apple-silicon + cursor_grok` 绑定 `m100-wave-soak-20260818-v4` receipt，取值为来源发现并发 8、fleet 并发 3、单对象 wall-clock 660 秒、完成宽限 60 秒；设计不复制这些数值的 schema。
- 非目标：冻结实体锚定匹配置信度、最小正文字数与单实体探测预算的具体取值，这些数由 Story `OPEN-004` 的受治理 calibration 承接。
- 非目标：为 managed checkpoint 的 prompt 扇出建立第三个受治理容量上限。
- 非目标：定义候选级与页面级拒绝原因的闭集，或改变 homepage/image/video 既有的供给与来源判定机制。
- 非目标：收敛 download、content_plan 与 recovery 阶段既有的载体分支；本层只约束目标选择到 target set 冻结这一段。
- 非目标：裁决实体多样性策略本身的取值与适用载体（每实体累计上限、Top-N 集中度上限、hot entity allowance 及其证据要求），这些由 `governance/coverage` 的策略 owner 拥有；本层只裁决它的结论归属于哪一层、落在哪个面、以及如何进入跨阶段对账。
- 非目标：让 WorkRequest 拥有 Campaign、Execution、Reconciliation、SourcePool、release 或环境生命周期，或以新的 intent catalog 复制这些对象的状态。

## 2. Story 协作与状态流

- [`multi-carrier-release`](./multi-carrier-release/spec.md)：每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 四载体共享实体目录但保持独立 execution
- 决策：Source Adapter 隔离并校验不可信外部输入；homepage、article、image、video 从同一冻结 canonical entity catalog 独立选目标并形成可分别调度的 workload，各自保留 immutable execution，实际运行可串行或重叠，不要求固定四路并发。
- 理由：post 只需要稳定 entity identity，不需要等待 entity homepage 生成；独立 execution 才能按载体隔离来源、权利、容量与失败恢复。
- 被否决方案：把四载体塞入同一 execution、让 post 依赖 homepage publish，或由调用方、页面、脚本复制本层状态并绕过公开契约。
- 约束与影响：四载体必须共享 reviewed named main branch、commit、source digest 与 entity catalog digest。
- 约束与影响：controller 从受审核输入构建一份 content-addressed、只读 source/executor capsule；各 lane 只写独立 execution root、queue namespace 与 staging prefix，不复制完整仓库，也不直接写共享工作树，final release 统一验证引用闭包。
- 约束与影响：四复制会话以 plan-frozen campaign run/fence 为共同身份，但各自只持有 carrier-scoped 文件锁与 claim；active workload 按可用容量独立调度，soak、workspace smoke、effective concurrency 与 resource samples 只作诊断。共享 canonical publish 继续由对象事务锁保持单写者，review/author/download 和 execution evidence 不共享可写根，最终 Manifest/release 精确验证被选对象及引用闭包。
- 约束与影响：单一载体失败不得篡改其他工作包，也不得阻止其他载体已合格对象发布。
- 约束与影响：quota 是里程碑目标，`partial` lane 必须发布合格对象并记录 typed shortfall。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 对象下限、工作单元数与并行上限各自冻结，`requiredWorkers` 退役
- 决策：`autoResearchMaxConcurrentWorkers` 与 `fleetMaxConcurrentWorkers` 只由 execution spec 的 `executionPolicy` 冻结，分别约束来源发现阶段与 ReliableTask 交付阶段任一时刻可同时运行的进程数。
- 决策：`approvedQuota` 只承载对象下限，`targetObjectCount` 只承载工作单元数，`requiredWorkers` 从 `executionPolicy` 与容量派生函数中退役。
- 决策：`fleetPeakConcurrentWorkers`、`fleetWaveCount` 与 `fleetBatchDeadlineEpochSeconds` 落在 ReliableTask fleet 运行回执的顶层必填位，不进入逐 job 结果数组，也不进入允许缺席的诊断子对象。
- 理由：`requiredWorkers` 由工作单元数原样派生，名字断言 worker 语义而取值是工作单元数，既与 `targetObjectCount` 构成同一事实的两份记录，又让交付阶段把每个工作单元当成一个可同时运行的进程。
- 理由：wave 数只应由工作单元数与冻结上限相除得到，只有把上限从工作单元数里剥离，规模增长才会只增加 wave 数而不增加同时运行的进程数。
- 被否决方案：把 `requiredWorkers` 原地改写成并行上限——已冻结 execution 的该字段等于工作单元数，重解释会把远高于标定值的数字当成上限而 fail open。
- 被否决方案：保留 `requiredWorkers` 并另加两个上限字段——同一 execution 内出现两个自称 worker 数的字段，属于契约单轨禁止的双读。
- 被否决方案：把上限放进 `queuePolicy`、runtime profile 或命令行默认值——`queuePolicy` 只承载传输参数，后两者都不随 execution 冻结，规格已判定它们不是合法来源。
- 约束与影响：`capacityPlanDigest` 承诺的 workload plan 文档同批扩展到两个上限与 calibration 摘要，使上限在 submission、claim 与执行策略之间任一环漂移都能被摘要比对发现。
- 约束与影响：`partitionCount` 仍只由工作单元数派生，它表达持久 job 身份与 fencing 分片，不表达可同时运行的进程数。
- 约束与影响：现有读 `requiredWorkers` 的调用点按语义一分为二，job set 规模、分区与 wave 推导读 `targetObjectCount`，进程并行度与 worker 启动参数读 `fleetMaxConcurrentWorkers`。
- 约束与影响：三值任一缺失即 fail closed，不得由另一项默认补齐，也不得回落到「worker 数等于工作单元数」的派生。
- 可观察面：local_contract 用同一请求冻结三值并单独提高 `approvedQuota`，断言派生 job 数只随工作单元数变化、并行上限不变、wave 数随 job 数变化，并断言缺任一值即 fail closed。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的执行策略容量冻结面
- 关联验收：`GWT-009.t1`、`GWT-009.t2`、`GWT-009.t3`、`GWT-009.t4`、`GWT-008.t1`、`GWT-011.t1` 与 `SIT-001.t11`

<a id="dec-003"></a>
### DEC-003 批次绝对截止在 execution 冻结时定值，lease 截止降为派生量
- 决策：`fleetBatchDeadlineEpochSeconds` 在 execution 冻结那一刻算出并写入 `executionPolicy`，取值为冻结时刻加上 wave 数乘以单对象 wall-clock 上限再加完成宽限，三个时间项全部来自 calibration。
- 决策：该绝对截止是本 execution 的唯一时间权威，lease 级 `deadlineEpoch` 不再独立取「当前时间加单对象上限」，改为取它与绝对截止的更小者。
- 理由：首个 wave 的启动时刻不属于不可变计划，进程被杀后重新拉起会重新落在「首个 wave 启动」上，等于让恢复路径为批次续期。
- 理由：lease 每次续租都重算完整单对象窗口时，第二个时间权威可以把总时长推到绝对截止之外，两个权威并存就没有任何一方能真正约束总时长。
- 被否决方案：在首个 wave 启动时冻结截止——它需要第二份持久化记录才能跨进程可见，且重启发生在首个 wave 之前时截止会整体后移。
- 被否决方案：保留 lease 独立截止并额外加一道批次检查——两个时间权威仍并存，最终要在每个消费点重复裁决谁优先。
- 约束与影响：剩余时间由 `max(0, fleetBatchDeadlineEpochSeconds - 当前时间)` 单点投影，进程重启、子进程重建与 lease 续租都只能注入这个投影值。
- 约束与影响：剩余时间为 0 时租约申请被拒绝且不再有新 job 开始，已在运行的 job 按单对象上限收敛并写入 typed deadline 终态。
- 约束与影响：批次超时推导从「按 wave 重新算一个相对预算」改为读取剩余时间投影，wave 数的推导只服务于冻结时刻的一次截止计算与运行回执。
- 约束与影响：绝对截止在冻结后不接受任何恢复路径改写，需要更多时间只能由新的 `retryOf` 冻结新的绝对截止。
- 可观察面：api_integration 在真实 worker 被杀死并重启的场景断言注入时间等于剩余时间投影且过期后不再启动新 job，local_contract 断言 lease 截止取两者更小值。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的批次时间预算面
- 关联验收：`GWT-010.t1`、`GWT-010.t2`、`GWT-010.t3`、`GWT-010.t4`、`GWT-011.t2` 与 `SIT-001.t12`

<a id="dec-004"></a>
### DEC-004 prompt 级观测与进程并行度按词元分家，`effectiveWorkerCount` 退役
- 决策：execution state 的 `managedAgentScheduler` 只保留 `promptCount` 作为单个 managed checkpoint 的 prompt 级调度观测，`effectiveWorkerCount` 退役。
- 决策：容量词元按角色固定，`fleetMaxConcurrentWorkers` 只表示冻结上限，`fleetPeakConcurrentWorkers` 只表示实测峰值，两个名字不得互换或复用到另一维度。
- 理由：`effectiveWorkerCount` 由 prompt 数原样赋值，与同一对象内的 `promptCount` 是同一事实的两份记录，同时又用 worker 词元指向一个不是进程并行度的量。
- 理由：退役之后 execution state 里不再存在任何 worker 命名的字段，「不得互相读取或推导」由字段缺席强制，而不是靠人工约定维持。
- 被否决方案：保留 `effectiveWorkerCount` 只补文档口径——同名字段仍在，跨维度误读只被劝阻而没有被阻断。
- 被否决方案：把 `effectiveWorkerCount` 改名成另一个 worker 派生名——它与 `promptCount` 的重复仍在，改名只换标签不减真相源。
- 约束与影响：三个维度分属三个 schema，冻结上限只在 execution spec，交付实测只在 fleet 运行回执，prompt 级观测只在 execution state，三者之间不建立引用也不互相复制取值。
- 约束与影响：managed checkpoint 的 prompt 并发扇出仍等于该 checkpoint 的 prompt 数，它不是受治理容量上限，为它设上限属于新的能力要求。
- 约束与影响：实测峰值只能被读来与冻结上限比对，回执写入时执行策略早已不可变，因此不存在把观测回写成新上限的路径。
- 可观察面：local_contract 断言 fleet 回执实测峰值不超过冻结上限、执行策略在回执写入后字节不变，并断言 execution state 契约中不存在 worker 命名字段。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的运行观测面
- 关联验收：`GWT-011.t2`、`GWT-011.t5`、`GWT-008.t4`、`GWT-008.t5` 与 `SIT-001.t8`

<a id="dec-005"></a>
### DEC-005 零合格原因是一个共享值对象，由观测者写一次再向上引用
- 决策：`REQ-006` 声明的 typed 零合格原因闭集连同其证据字段定义为 `quwoquan_data/schema/_common/` 下的单个共享值对象，lane 回执、campaign 报告与 fleet 运行回执都引用同一定义，三层不各自声明枚举。
- 决策：该值对象要求可续跑中断携带精确可续跑 refs，其余原因一律携带不可续跑的判定依据，两者由同一条件约束互斥。
- 理由：同一闭集在三层各写一份枚举，等于三个可以分别漂移的真相源，运营者读到的原因会随读取层不同而不同。
- 理由：原因是终结该终态的那一层观测到的事实，来源为空与访问被拒发生在交付启动之前，截止耗尽只有交付阶段能观测，所以写者按观测者定而不是按层级定。
- 被否决方案：只在 fleet 回执定义原因、其余两层做字符串透传——lane 在交付启动前就已 blocked 的路径没有回执可透传。
- 被否决方案：为 campaign 增加一个聚合级原因——它会成为闭集之外的又一个值，并与逐 lane 原因产生不一致的可能。
- 约束与影响：lane 回执是 lane 零合格原因的唯一写者，`qualified == 0` 的 lane 必须携带唯一原因，`blocked` 不再是没有原因的汇总值。
- 约束与影响：在交付阶段终结的 lane 直接绑定 fleet 回执中的同一个原因值，不做任何转换映射，转换表本身就是隐藏的第二套枚举。
- 约束与影响：campaign 报告只投影各 active lane 的原因集合而自己不写原因，campaign 的 `blocked` 表示全部 active lane 均为 blocked。
- 可观察面：local_contract 对闭集内每个原因逐个构造终态，断言三层读到同一个值对象、campaign 不产生闭集之外的值、可续跑原因必须带非空 refs 而其余原因必须带判定依据。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的零合格终态面
- 关联验收：`GWT-011.t3`、`GWT-011.t4`、`GWT-001.t7` 与 `GWT-004.t3`

<a id="dec-006"></a>
### DEC-006 容量数值只能从 create-once calibration receipt 冻结进 execution
- 决策：两个并行上限、单对象 wall-clock 上限与完成宽限只能取自一份 create-once calibration receipt，execution 冻结时把取值与该 receipt 的摘要一并写进 `executionPolicy`。
- 决策：冻结时没有当前有效 receipt，或 receipt 字节与所绑摘要不一致时，execution 创建即 `GATE_BLOCK`，不落默认常量也不回落 runtime profile。
- 理由：执行期必须自包含且不可变，而数值的产出方是一次受治理 soak；冻结加摘要绑定让任一时刻只有一个生效值，同时保留可复核的产出来源。
- 被否决方案：运行期按路径实时读取 receipt——receipt 被替换会改变已在运行批次的上限与截止，绝对截止不可改写的结论随之失效。
- 被否决方案：让 receipt 只做建议值而允许请求方覆写——覆写值没有实测依据，等于把探针观测与手填数字重新变成合法来源。
- 约束与影响：receipt 不可原地修改，改数值只能产出新的 create-once receipt，并由新的 `retryOf` execution 绑定新摘要。
- 约束与影响：新 receipt 取代旧 receipt 只影响此后冻结的 execution，已冻结 execution 继续使用自己绑定的数值，回滚即让新 execution 重新绑定上一份仍有效的 receipt。
- 约束与影响：receipt 按运行主机类别与 Provider 档位声明适用范围，超出该范围的 execution 不得复用它的数值。
- 可观察面：local_contract 断言缺 receipt、摘要漂移与超范围复用三种情况均 fail closed，并断言冻结后的执行策略数值与 receipt 内容逐字段相等。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的容量来源绑定面
- 关联验收：`GWT-009.t4`、`GWT-010.t4` 与 `GWT-011.t2`

<a id="dec-007"></a>
### DEC-007 实体级预筛四态落在独立聚合，既有两态判定与权利分级都不扩展
- 决策：article 预筛结论定义为一个独立聚合，与 `execution_spec` 和 lane 回执同层落在 `quwoquan_data/schema/execution/`；聚合边界是一次预筛（含其全部补采轮次），候选实体是它的 owned entity，写 owner 唯一为预筛执行者。
- 决策：四态是一个闭集字段，子原因是第二个闭集字段并按状态条件必填，可续跑 refs 与不可续跑判定依据由同一条件约束互斥——与 `DEC-005` 的零合格原因同一范式。
- 决策：`quwoquan_data/schema/execution/source_qualification_result.schema.json` 与 `content/execution/planning/source_ready_precheck.py` 的权利闭包分级都不承载本四态，两者的值域、粒度与判定时点保持原样。
- 理由：四态之间的区别是可判定的事实差异，只有让它成为一个字段的四个值，「判定未完成」才不会靠「没有结论」来表达；子原因单列则让运营动作（换实体、调阈值、扩来源闭集、修来源闭集）能从终态直接读出来。
- 理由：verdict 不能内嵌进 execution spec 的 `coverageTargets`——出局实体根本不在冻结集合里，而它们的首要原因正是要被量化的那一部分；spec 冻结后也不可再写。
- 被否决方案：把四态并进 `source_qualification_result`——它是 publish 前对 execution root 内已生成 source catalog 的事后闭包校验，`policyRevision` 与 issue lane 都是 const，运行时点远在预筛之后。放宽这两个 const 会让同一契约同时承载「百科闭集事后校验」和「article 冻结前可得性预筛」两个判定时点，homepage 也随之失去 const 带来的 fail-closed。
- 被否决方案：复用权利闭包分级的四个等级——它按来源集合分组回答「权利决策是否闭合」，不是按实体回答「来源是否可得」；复用会让既有测试补一个 `spec_ref` 就冒充本节点新验收，`OPEN-004` 已点名禁止。
- 约束与影响：四态、子原因与计量都不得以缺席、空数组或零计数表达；`探测失败` 单独计量，不并入其余三类的分子分母。
- 可观察面：local_contract 对六类实体逐个构造终态，断言四态与子原因逐一成立且任一态都不是空值、空集合或零计数，并断言 `探测失败` 必带非空可续跑 refs、`在场不足` 与 `缺席` 必带不可续跑依据；`缺席` 与 `探测失败` 在真实探测下的区分由 api_integration 以受治理 provider-state 注入取得拒绝、超时与预算耗尽证明。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 来源预筛终态面
- 关联验收：`GWT-012.t1`、`GWT-012.t2`、`GWT-012.t6` 与 `GWT-012.t7`

<a id="dec-008"></a>
### DEC-008 预筛终态是先于 spec 的 create-once receipt，退出码不再承载原因
- 决策：预筛聚合以 create-once receipt 写入该 execution 的工作包，写入时点严格早于 execution spec；进程只允许在 receipt 落盘之后退出，退出码与异常字符串不再是 article 预筛失败的呈现面。
- 决策：该 receipt 是运营者的唯一呈现面。lane 回执与 campaign report 只以 `ref + digest` 指向它并投影四类计数，不复制 verdict 行，也不新建第二个查询入口。
- 理由：预筛失败的定义就是 spec 不会被冻结，所以任何「冻结之后再补写」的落点在需要它的时候都不存在；只有把受体放在 spec 之前，`GWT-012.t9` 才有东西可读。
- 理由：receipt 与 spec 绑定同一个 execution 身份，lane 终态为 `published` 或 `partial` 时它仍在原路径可读，`探测失败` 实体的可续跑 refs 不因该 lane 已发布而被丢弃。
- 被否决方案：把 campaign report 的自由文本 `error` 升级成 typed 对象——report 是运行回执而不是新的真相源，且 campaign 层只投影 lane 事实；把唯一权威面放进去会让复制会话的 finalize 聚合写者与预筛写者争抢同一字段。
- 被否决方案：复用 lane 回执——它的 phase 闭集是 `review` 与 `publish`，最早也要到 review 才成立；预筛终止时 review 从未发生，为它加第三个 phase 等于把「从未进入生产」伪装成一次 review 结果。
- 约束与影响：工作包根的存在不再等价于 spec 已冻结，`executionRootRef` 与 cleanup 终态可以在 spec 缺席时已创建。
- 约束与影响：该 receipt 是 execution 证据，因此止于预筛的 attempt 不再是「无 plan/report/runtime/execution 证据」的 submission-only attempt，其收口走既有 terminal execution 证据路径；receipt 受 GC protection，不得被清理或改写。
- 可观察面：local_contract 让预筛在 spec 冻结之前终止，断言 receipt 已存在且四态可读、执行 spec 不存在、进程退出码不携带任何原因；并断言 lane 终态为 `published` 或 `partial` 时同一 receipt 仍可读、可续跑 refs 未被删除。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的预筛呈现面
- 关联验收：`GWT-012.t8`、`GWT-012.t9` 与 `GWT-013.t7`

<a id="dec-009"></a>
### DEC-009 article 预筛是独立对象，选择器只消费它的单向投影
- 决策：article 预筛是自己的对象，既不做 `TargetSourceQualification` 的第三个实现，也不把 homepage/video/article 三个 qualifier 收敛成按载体分派的统一抽象。
- 决策：`source-ready-priority` 对 qualifier 非空的硬性要求由一个 adapter 满足，它从已完成的四态 verdict 单向投影：`在场可用` 投影为接受，其余三态投影为不接受。投影有损且只喂选择器，任何消费者都不得从选择器的拒绝码反推四态。
- 决策：article lane 与 homepage 同样强制 `source-ready-priority`，预筛不是调用方可选项。
- 理由：`TargetSourceQualification` 是二值接受加单个拒绝码，且以不变量绑定「接受当且仅当有合格来源」；三个非成功态只能压进同一个不接受再靠拒绝码反推，正是 REQ-007 禁止的塌陷。拒绝码闭集的 owner 也不是本节点，借它当四态载体意味着别处新增一个码就改变本节点的态。
- 理由：homepage 判的是百科三闭集加字数门，video 判的是冻结 acquisition receipt 的 exact pair 查表且完全不探测网络，article 判的是站点 frontier 探测加实体锚定；输入、失败模式、探测预算与判定时点都不同，统一抽象只会退化成一个按载体分支的 dispatcher，把三份互不相关的判定绑到一个 owner，还会迫使 homepage 与 video 承担它们规格已判为 Out of Scope 的四态。
- 理由：不强制选择器时，「必须在冻结之前完成判定」会退化成调用方选项，等于给整条准入留一个 warn-only 逃逸。
- 被否决方案：让 article 沿用 homepage qualifier 的形状新增一个同构实现——形状同构掩盖的是值域不同，四态一进去就塌成两态。
- 被否决方案：让 adapter 的投影结果被持久化成 article 的来源证据——那会在 verdict 之外再留一份可漂移的来源结论；article 的来源证据由 frontier evidence 与 verdict receipt 拥有。
- 约束与影响：materialization 中「其余载体一律 fail closed」的分支收敛为「article 走预筛、其余仍 fail closed」，homepage 与 video 两个 qualifier 的形状和语义不变。
- 可观察面：local_contract 断言只有 `在场可用` 实体进入冻结工作单元、其余三态实体不出现在 auto_research/download/content_plan 的输入里，并断言 article 在非 `source-ready-priority` 选择器下 fail closed。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 目标冻结面
- 关联验收：`GWT-012.t5` 与 `GWT-012.t1`

<a id="dec-010"></a>
### DEC-010 补采资格与不足处置各自显式声明，不再由来源证据是否持久化派生
- 决策：「本 lane 是否可跨轮补采」与「候选不足是否 fail closed」是两件独立的事，不再由「是否持久化 qualified source」这一个布尔同时决定；两者各自的真相源、单写者与组合方式由 [`DEC-014`](#dec-014) 与 [`DEC-015`](#dec-015) 裁定。
- 决策：article 为可补采且不足不 fail closed，补采预算耗尽后以实际 `在场可用` 集合继续执行并进入 `partial`，只有零 `在场可用` 才 `blocked`；homepage 保持可补采且不足 fail closed，video 保持不补采且只有零供给才阻断。
- 理由：现有补采驱动把补采资格绑在持久化标志上，而该标志同时开启了 homepage 的交付承诺 fail-closed 语义。article 要的组合是「可补采且不足降级为 partial」，在当前耦合下无法表达：走持久化分支会把 partial 变成 blocked，走非持久化分支则根本不进补采。
- 被否决方案：article 复用 homepage 的 fail-closed——直接违反「以实际 `在场可用` 集合继续执行并进入 partial」。
- 被否决方案：article 走非持久化分支——那条分支不进补采轮次，违反「补采按既有轮次机制补充候选并重新预筛」。
- 被否决方案：在 article 侧捕获补采驱动抛出的不足失败再继续——把失败态转写成成功态属于禁止的 fallback，还会丢掉驱动给出的 typed stop reason。
- 约束与影响：补采仍复用既有轮次与停滞检测机制，不新建第二套补采；每一轮新补进的候选必须重新走预筛，全部轮次的结论汇入同一个 create-once receipt，同一实体只保留一条终态。
- 约束与影响：quota 不得因预筛结果被静默下调，未通过预筛的实体不得 padding 进工作单元；预筛只改变进入冻结的候选集合，不改变 `DEC-002` 的三值分离。
- 可观察面：local_contract 用对象级 typed double 让首轮 `在场可用` 少于 quota，断言补采被触发且新候选重新预筛、quota 值不变、工作单元不含未通过预筛的实体；再让补采预算耗尽，断言 lane 为 `partial` 而不是 `blocked`，并单独断言零 `在场可用` 时 `blocked` 携带实体级首要原因。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 补采与不足处置面
- 关联验收：`GWT-013.t1`、`GWT-013.t2`、`GWT-013.t3`、`GWT-013.t4` 与 `GWT-013.t5`

<a id="dec-011"></a>
### DEC-011 实体级与 fleet 级各自单写者，衔接只有 refs 一个方向
- 决策：实体级 verdict receipt 是「该实体是否还能被重新探测」的唯一权威，写者是预筛，粒度是候选实体；`DEC-005` 的零合格原因值对象是「本批次是否还能续跑」的唯一权威，写者是终结该终态的那一层观测者，粒度是 lane。两个面各自单写者，互不推导也互不替代。
- 决策：衔接只有一个方向——实体级 `探测失败` 的可续跑 refs 是新 `retryOf` 的输入。fleet 级不得读 verdict 去改写实体态，实体级也不得因为 fleet 判定本批次不可续跑就把实体改成不可再探测。
- 决策：零 `在场可用` 的 article lane 在其零合格原因旁引用本 receipt 的实体级首要原因聚合，引用而不复制，不为这一种零另立 fleet 级原因值。
- 理由：同一次网络不可达在两层得出不同结论不是矛盾，而是两层在回答不同问题：fleet 级说「本批次到此为止，需要新的 `retryOf`」，实体级说「这些实体的判定未完成，下一次仍应探测」。把两者强行对齐会逼出一个既不能回答续跑、也不能回答重探的折中值。
- 理由：观测口径因此按分母固定——fleet 级原因的分母是批次，实体级四类的分母是候选实体数；两者不做加总，也不互相校验相等。
- 被否决方案：由 fleet 级原因派生实体级终态——批次级原因没有实体维度，派生只能给全部实体盖同一个章，`GWT-013.t6` 的四类构成随之失真。
- 被否决方案：由实体级聚合反推 fleet 级原因——`REQ-006` 闭集中除来源为空之外的原因都在预筛得出结论之后才被观测到，预筛看不到它们。
- 约束与影响：article lane 引用实体级聚合的前提是 `DEC-005` 的共享值对象已落地；在它落地之前不得在 article 侧先自建一份原因枚举。
- 可观察面：local_contract 构造一次网络不可达，断言 fleet 级判本批次不可续跑的同时实体级仍为 `探测失败` 且保留可续跑 refs，两个结论并存且互不覆盖；并断言零 `在场可用` 的 `blocked` 通过引用而不是复制携带实体级首要原因。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的续跑判定面
- 关联验收：`GWT-013.t8`、`GWT-013.t4`、`GWT-013.t5` 与 `GWT-012.t6`

<a id="dec-012"></a>
### DEC-012 归并在实体边界执行一次，跨阶段对账靠同一实体键做差集
- 决策：候选级与页面级细粒度拒绝原因到实体级首要原因的归并，由预筛在实体边界上执行且只执行一次，结果只写进 verdict receipt；候选级不做归并，也不新建第二套来源台账。
- 决策：归并按已冻结的优先级在实体内对全部候选取先者；候选携带未归入四态的原因时，该实体以 `探测失败` fail closed 并在证据里点名该原因，不得静默归入 `缺席` 或 `在场不足`，也不得被丢弃。
- 决策：来源预筛、auto_research 与 content_plan 三个阶段各自以同一实体键持久化自己的 ready 集合，跨阶段对账是对三个集合做差集，而不是比较三个计数；不新建第三个对账台账。
- 理由：归并是有损的，只有在实体边界做一次才能保证每个实体恰有一个首要原因；在候选级做归并会让同一实体在不同来源站点得出多个并列首要原因。
- 理由：候选级原因闭集的 owner 是另一个节点，预筛只消费其逐候选判定结果做聚合与准入。未归类原因 fail closed 是这条 owner 边界的执行方式——它保证 owner 新增一类原因而未归类时，污染的是可续跑的第四类，而不是已完成判定的前三类计量。
- 理由：只有计数没有实体键时，两个阶段的 ready 数一旦不同就无法回答「出局的是哪些实体」；差集把这个问题变成可直接列举的集合运算。
- 被否决方案：把归并下沉到 frontier——frontier 只看得见单个站点的单个页面，看不见同一实体的其它候选，归并优先级里的「只要存在一个合格候选即在场可用」在那里无法判定。
- 被否决方案：为跨阶段对账建一个独立台账——三个阶段各自的 ready 集合已经是既有产物，第三份记录只会成为可漂移的第二真相源；缺实体键的阶段应当补实体键，而不是补一个新文件。
- 约束与影响：本节点只消费候选级判定结果做实体级聚合与准入，不复制候选级闭集，站点与 provider 级抓取准入及其审计证据仍归 owner 节点。
- 可观察面：local_contract 构造同时含未达门槛候选与判定未完成候选的实体，断言归并得到 `探测失败`。构造携带未归类原因的实体，断言以 `探测失败` fail closed 并点名该原因。四类的分子、分母与占比可直接由实体级聚合算出且第四类单独计量。三阶段逐实体对账由 api_integration 经一次真实 execution 的 selection、auto_research 与 content_plan receipt 完成，断言 ready 数下降时能精确列出出局实体及其首要原因。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的实体级原因聚合与跨阶段对账面
- 关联验收：`GWT-012.t3`、`GWT-012.t4`、`GWT-013.t6`、`GWT-013.t9` 与 `GWT-013.t10`

<a id="dec-013"></a>
### DEC-013 零合格原因按观测阶段分家，publish 阶段的体量准入不并入 review 阶段的质量被拒
- 决策：`quwoquan_data/schema/_common/zero_qualified_reason.schema.json` 的原因值按观测阶段划分，同一原因值只属于一个观测阶段；publish 阶段的准入结论不得并入 review 阶段的质量被拒。
- 决策：原因值、观测阶段与运营动作三个闭集互相约束，任一新原因进入时三者一起扩容，新原因不得借用语义不符的既有阶段或既有动作。
- 决策：媒体侧只产出对象级排除码，批次级零合格原因的唯一写者仍是本 Story 的 lane 回执，两层以引用衔接而不复制。
- 理由：质量被拒与体量超预算是两次不同的判定。前者由 review 观测且运营动作指向内容本身，后者由 publish 准入观测且运营动作指向换素材、减少引用或拆对象。把后者读成前者会让运营者去查一本全部通过的 review 账本。
- 理由：三个闭集必须一起扩。只加原因值会迫使它借用一个语义不符的观测阶段与运营动作，同一个值随之出现两种读法，而 `DEC-005` 的立论正是原因由观测者写一次。
- 被否决方案：放宽 `ALL_OBJECTS_QUALITY_REJECTED` 的阶段约束让它同时表达 review 与 publish——该码在两个阶段指向两个运营动作，观测阶段从常量放宽成枚举后它自己也不再能回答谁观测到了这件事。
- 被否决方案：让媒体侧自行发明一个批次级原因码——同一闭集出现第二个写者，运营者读到的原因会随读取层不同而不同。
- 被否决方案：把体量超预算映射到既有的修来源动作——拆对象与减少引用资产数都不是修来源，按该提示去改来源闭集解决不了问题。
- 约束与影响：闭集基数由本 Story 的 `REQ-006` 与 `GWT-011` 声明，扩容必须先在规格上改写枚举，设计不越过规格自行扩容。
- 约束与影响：批次级原因只在一个批次的全部对象都被拦下时成立，存在任一合格对象时批次仍按合格对象数进入 `partial`。
- 可观察面：local_contract 对每个原因值断言其观测阶段唯一且与运营动作条件绑定，并断言 `ALL_OBJECTS_QUALITY_REJECTED` 只能出现在 review 阶段、publish 阶段的准入结论不能取到它。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的零合格原因归属面
- 关联验收：`GWT-011.t3`、`GWT-011.t4`

<a id="dec-014"></a>
### DEC-014 补采资格由候选池 provenance 派生，持久化标志收回字面语义
- 决策：「是否持久化 qualified source」只表达一件事——本载体的 coverage target 是否必须逐行携带该证据；取值由该载体的对象契约派生，即 coverage target 契约是否把该证据声明为该载体的逐行必填、spec 级校验是否据此 fail closed。它不再兼任路径选择器、处置开关或补采资格判据。
- 决策：补采资格不是策略而是可判定的结构事实——本次候选集未被本 execution 之外的任何一方冻结即可补采。冻结者是一个三元闭集：显式请求名单、外部 acquisition receipt 的候选身份集、`retryOf` 继承的前驱集，三者取或。持久化标志从该判据中删除，`retryOf` 继承同时由隐式变为显式合取项。
- 决策：补采资格与不足处置都是 execution 冻结期的策略输入，不是运营者终态权威面；`DEC-011` 的两个权威面及其单写者不变，本决策不新增第三个。
- 理由：三件事今天挤在同一个布尔上，而它们的真相源各不相同——持久化的真相源是对象契约，补采资格的真相源是候选集被谁冻结，不足处置的真相源是 lane 的交付承诺。一个布尔只能表达两种组合，任一载体需要的组合落在这两种之外就无法表达，article 正是这一种。
- 理由：删掉这个合取项后，homepage 与 article 都由本 execution 从有序参考集自取而可补采，image/video 的候选身份集由外部 receipt 冻结而不可补采，`retryOf` 由前驱集冻结而不可补采——三个既有载体的资格逐一不变，只有 article 新获得资格，说明该布尔从来不是这个判据的组成部分，只是恰好与之同向。
- 理由：`retryOf` 继承今天靠把持久化标志置 false 来阻止重新抽取。该置位在请求名单非空的 retry 上是死值，只有请求名单为空时才真正生效。把补采资格从该布尔摘下时若不同时把继承补成显式合取项，这类 retry 会从「不重新抽取」变成「可补采」，前驱候选池被静默改写。
- 被否决方案：为判据新增一个「允许本 lane 补采」的第二布尔——它与候选池 provenance 表达同一事实，两者一旦不一致就要在每个消费点重新裁决谁优先，属于契约单轨禁止的双读。
- 被否决方案：让 article 也取持久化以换取补采资格——`DEC-009` 已判定 adapter 的投影结果不得被持久化成 article 的来源证据，逐行写入会在 verdict receipt 之外再留一份可漂移的来源结论，且该行的键名与值域都是 homepage 百科闭集的形状。
- 约束与影响：持久化标志的取值此后只能从对象契约读出，请求方与装配点不得为换取其他行为而反向选择它。
- 约束与影响：oversample 填充继续与持久化同源——coverage target 不要求逐行证据时才允许用未合格行填满候选池，因为该池准入由下游 download admission 重新验证；它不拆成第四个入参。
- 约束与影响：`retryOf` 继承在请求名单为空时同样不可补采，前驱候选池在任何 retry 形态下都不被重新抽取改写。
- 可观察面：local_contract 对四种候选池 provenance 逐一断言补采资格取值，并在每种 provenance 下翻转持久化标志断言资格不变；单独构造请求名单为空的 `retryOf` 继承，断言它仍不可补采且选中集合与前驱逐行相同。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 补采资格面
- 关联验收：`GWT-013.t1` 与 `GWT-012.t5`

<a id="dec-015"></a>
### DEC-015 不足处置收敛为一处显式裁决，两条抽取路径只返回 typed 终态
- 决策：「候选不足是 fail closed 还是以实际合格集合继续」是 lane 交付契约事实，作为 selection 请求的显式二值入参在 execution 冻结时声明。闭集为「不足即阻断」与「不足即部分准入、零合格仍阻断」，无默认值，缺失即 fail closed。homepage 取前者，article 与 video 取后者。
- 决策：单轮分级与补采循环都不再自行把未达 quota 抛成失败，两者各自返回带 typed stop reason 的完整终态；是否阻断由目标选择的单一收口按上述入参裁决一次。今天分散在单轮分级的供给不足判据、选择器出口的候选池耗尽判据与补采循环终态这三处的 fail-closed 合并到这一处。
- 决策：抽取循环的 stop reason 是过程事实，只作为处置裁决的输入与 lane 回执的诊断，不得被投影成运营者可读的原因枚举。实体级终态权威面仍只有 `DEC-008` 的 verdict receipt，lane 级仍只有 `DEC-005` 的零合格原因值对象。
- 理由：补采循环今天把「循环已跑完、停止原因已证明、产出低于 quota」抛成异常。那是一个判定已完成、结论确定的事实，抛异常把它编码成「没做成」，正是结果状态单义禁止的跨态代偿；`REQ-007` 要求 article 的「在场不足」与「探测失败」分属判定已完成与判定未完成，沿用异常编码会让前者在这一层就塌进后者。
- 理由：选择抽取路径与选择不足处置本是两次独立决定，今天却由同一次二选一同时做出——走补采路径等于选了无条件阻断，走单轮路径等于选了按持久化标志分叉的阻断。只要处置还留在路径内部，任何只解开补采资格的做法都是把同一个阻断换个位置保留下来，article 仍拿不到 partial。
- 理由：处置只在一处执行时，「不足」与「零合格」的分界只需要写一次。分散在三处时每处都要重新判定一次零合格例外，而「持久化或零合格」与「非持久化且有选中」已经是同一条规则的两份互为镜像的记录。
- 被否决方案：保留补采循环抛错、由 article 侧捕获后继续——`DEC-010` 已否决，把失败态转写成成功态属于禁止的 fallback，并会丢掉循环给出的 typed stop reason。
- 被否决方案：只给补采循环加一个「允许不足返回」的开关而保留其余两处判据——三处判据仍在，处置权仍是三个写者，homepage 与 article 的差异要在三处分别维护一遍且可以分别漂移。
- 被否决方案：让处置入参可缺省并回落到持久化标志——那正是本次要拆掉的隐式派生；缺省值会让新接入的载体在没有声明交付契约的情况下静默继承别的载体的承诺。
- 约束与影响：处置为「部分准入」时 quota 不被下调，未通过分级的候选不得 padding；`DEC-002` 的三值分离与 `DEC-010` 的补采轮次机制均不变。
- 约束与影响：处置为「部分准入」且合格数为零时仍然阻断，该阻断按 `DEC-011` 引用实体级首要原因聚合，不新增 fleet 级原因值。
- 约束与影响：两条抽取路径的公开返回形状统一为「选中集合 + 分级报告 + typed stop reason」；调用方不得从是否抛出异常推断供给结论。
- 可观察面：local_contract 让两条抽取路径分别停在未达 quota 的终态，断言各自返回 typed stop reason 而不抛错。对同一终态分别注入两种处置取值，断言前者阻断、后者以实际合格集合继续，并断言合格数为零时两种取值都阻断。处置入参缺失即 fail closed。stop reason 不出现在 verdict receipt 与零合格原因值对象中。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 不足处置面
- 关联验收：`GWT-013.t3`、`GWT-013.t4`、`GWT-013.t1`、`GWT-013.t2` 与 `GWT-001.t6`

<a id="dec-016"></a>
### DEC-016 共享选择路径不读载体身份，载体差异只在装配点冻结为取值
- 决策：目标选择、来源分级与补采循环这条共享路径内不得出现载体名条件分支。载体差异只允许在 execution 装配点表达为三个策略取值（持久化、补采资格、不足处置）与一个 qualifier 实现的绑定，之后沿调用链只以取值流动。
- 决策：判据是「同一段代码是否会被一个以上载体执行」——是则不得读载体身份。装配点按载体绑定 qualifier 与声明取值不属于本禁令，它是组合而不是分支。
- 决策：持久化证据的键名带载体词属于命名而不是分支；共享路径只把它当键名使用，不得对其做值比较来反推载体。
- 理由：在共享路径里按载体分支等于在一个函数里维持多套语义，接入下一个载体时要在每个分支点重新裁决一次。本次拆解要解决的正是「一个判据同时决定多件事」，用载体名把它重新聚合回去只是把耦合换了个触发条件。
- 理由：三个取值在 execution 冻结时全部可知，因此不存在必须在运行期回读载体身份才能决定行为的路径；判断不出取值就说明该载体的交付契约尚未声明，应当先补契约而不是加分支。
- 被否决方案：在共享路径里保留一处载体分支作为过渡——过渡分支没有可判定的移除条件，会与三个显式取值并存成为第二套语义来源，并立刻成为下一个载体照抄的样板。
- 被否决方案：把三个取值合并成一个「载体档位」枚举——枚举值仍是载体名的别名，消费点仍要展开成同样的分支，且三个取值之间本来正交的组合会被枚举收窄成已列举的几种。
- 约束与影响：`DEC-009` 判定的「article 走预筛、其余仍 fail closed」发生在装配点，与本禁令不冲突。
- 约束与影响：本禁令只覆盖目标选择到 target set 冻结这一段；download、content_plan 与 recovery 阶段既有的载体分支不在范围内。
- 可观察面：local_contract 用同一组候选行、同一 qualifier 行为与同一组策略取值，分别以两个载体身份运行选择路径，断言选中集合与分级报告逐行相同；再单独改变其中一个取值，断言全部差异都能由该取值解释。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 共享选择装配面
- 关联验收：`GWT-012.t5`、`GWT-013.t3` 与 `GWT-013.t4`

<a id="dec-017"></a>
### DEC-017 冻结期准入是选择器的决定，不进预筛四态，且严格后置于判定
- 决策：一个 `在场可用` 实体因跨 execution 累计分布约束而未被选入本批工作单元，是**选择器在冻结工作单元时的准入决定**，不是来源预筛的结论。`REQ-007` 的四态保持四个值，不新增第五态，也不在四态旁挂一个表达是否被选中的状态位。
- 决策：冻结期准入严格在实体级预筛判定完成之后执行，只作用于已判为 `在场可用` 的行；判定与准入的先后不可对调。多样性是这类准入今天的唯一成员，本决策约束的是这一类而不是这一个实现。
- 决策：冻结期准入的出局不得计入预筛的候选级或实体级拒绝计量。`GWT-013.t6` 四类的分子与分母只由 verdict receipt 的实体终态算出，被准入挡下的实体在这四类里始终计为 `在场可用` 之外的零。
- 理由：四态的分界是「该实体的来源判定是否完成、结论是什么」，输入是实体、允许来源闭集与 calibration 阈值。准入的输入是 canonical publish 树的跨 execution 累计分布、本批已准入投影与治理策略，与该实体的来源可得性无关。同一实体、同一探测证据换一个批次就换结论，这样的取值不能充当 `DEC-011` 所说「该实体是否还能被重新探测」的权威。
- 理由：第五态会让一个来源完全可用的实体被记成来源预筛的一种态。四态的每个子原因都绑定一个运营动作——修来源闭集、扩来源闭集、调篇幅门槛、换实体、续跑——而被准入挡下的实体的正确动作是扩大候选范围或等累计分布变化，它绑不到其中任何一个；运营者按四态提示去改来源，改的是一个没有问题的来源。
- 理由：结果状态单义要求「来源可用但未被选中」与「来源不可用」保持两种状态。第五态把两个不同问题的答案挤进同一个枚举，读到该值的消费者无法判断它在回答哪一个问题，正是禁止的跨态代偿。
- 理由：顺序不可对调。先准入后判定会让被挡下的实体根本不产生 verdict 行，它既不在候选全集里、也没有出局原因，`DEC-012` 的逐实体差集会少掉一整块被减数，`GWT-013.t6` 的四类分母随之失真——省下的探测预算是用对账证据换来的。
- 被否决方案：在四态上加第五个值「可用但未选中」——这让预筛成为一个它没有做出、也无法复现的决定的写者（准入读 publish 树累计计数，预筛不读也不该读），直接违反 `DEC-011` 的单写者边界。
- 被否决方案：保留四态但给 `在场可用` 旁挂一个是否入选的布尔——同一实体的终态从此要两个字段合读才有意义，`DEC-007` 的「四态是一个字段的四个值」被拆成两个可分别漂移的位，而该布尔的写者仍然只能是选择器，写者问题原样保留。
- 被否决方案：把准入提前到预筛之前以省下探测预算——被挡下的实体不再产生 verdict 行，候选全集缩小到与 `在场可用` 集同形，跨阶段差集形式上恒为空，看似闭合实则把出局证据整体删除。
- 约束与影响：`GWT-012.t5` 的「只有 `在场可用` 的实体进入冻结的工作单元」是必要条件而不是充分条件，本决策与该结果子句不冲突，不需要改写它。
- 约束与影响：准入出局不是失败。补采循环把它计为当前抽取轮次未产出并在后续补采轮次补齐，因此它改变的是补采轮次数，不改变 quota，也不改变 `DEC-002` 的三值分离与 `DEC-010` 的补采轮次机制。
- 约束与影响：`在场可用` 非空但准入后为零时 lane 仍然阻断。该阻断的批次级归因不在四态内，而是 `DEC-005` 共享值对象中「全部候选实体被选择器准入排除」这一原因值，由 lane 回执按 `DEC-005` 的单写者规则写入。批次级原因与实体级证据是引用关系而不是二选一：该原因在不可续跑依据之外必须携带逐实体准入排除 refs，指向 [`DEC-018`](#dec-018) 排除面上已声明的条目，缺该 refs 时原因不成立；只留逐实体证据而不写批次级原因同样不成立。
- 可观察面：local_contract 构造两个来源证据逐字段相同的 `在场可用` 实体，只改变累计分布使其一被挡下，断言两者的 verdict 终态与子原因逐字段相同且都是 `在场可用`。verdict 契约中不存在任何多样性或入选字段。实体级四类的分子、分母与占比在该实体被挡下前后不变。准入只接收已判 `在场可用` 的行，未判定的行不进入准入。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 冻结期准入归属面
- 关联验收：`GWT-012.t1`、`GWT-012.t5` 与 `GWT-013.t6`

<a id="dec-018"></a>
### DEC-018 准入结论落在既有冻结选择证据上，写者是选择器，与 verdict 只有 refs 一个方向
- 决策：冻结期准入结论的呈现面是执行工作包既有的冻结选择证据 `_shared/target_selection.json`，写者是选择器本身。它回答「本批冻结了哪些实体、某个已合格候选为何未进入这一批」，与 `DEC-011` 两个权威面回答的两个问题都不同，因此不构成第三个权威面，也不需要新建文件或新增写者。
- 决策：衔接只有一个方向——选择证据以 `ref + digest` 指向 verdict receipt，并对每个出局实体给出与 verdict receipt 同一实体键；verdict receipt 不得出现任何准入字段，也不得回读选择证据。
- 决策：该证据的写入时点与 execution spec 冻结解耦。选择器跑完准入即写，spec 是否冻结不改变它是否存在；`在场可用` 非空而准入后为零、spec 不会被冻结时，它同样在原路径可读。
- 决策：闸门缺席与零出局不塌陷。准入闸门未运行时省略该键，闸门运行且无人被挡下时该键在场且出局集合为空数组；两者不得表述为同一种结果。
- 理由：写进 verdict receipt 会让预筛成为它没有做出的决定的写者。预筛既不读 publish 树累计分布，也在准入发生之前就已结论落定；`DEC-008` 的「唯一呈现面」辖域是预筛四态，不覆盖选择器的准入结论。
- 理由：选择证据不是新增面。它已是执行工作包登记在册的执行级权威证据，已经承载本批 targets、target refs 与 selection shortfall，也已经承载带实体 ref 的多样性报告；本决策只是把「谁是这个结论的权威写者、运营者该读哪个文件」写定。
- 理由：写入时点必须与 spec 解耦，理由与 `DEC-008` 同构——零准入正是最需要这份证据的时刻，而那一刻 spec 不会被冻结。把受体绑在成功路径上，等于让唯一需要它的场景读不到它。
- 理由：缺席与在场为空必须可分。读到一个空对象时无法判断是「闸门没跑」还是「闸门跑了没挡下任何人」，而 [`DEC-019`](#dec-019) 的残差判定在前一种情况下会把未闭合误判为已闭合。
- 被否决方案：写进 verdict receipt（无论作为第五态还是旁挂字段）——写者错位如上；且该 receipt 在 spec 之前 create-once，准入结论产生于其后，写入需要改写 create-once 证据。
- 被否决方案：新建一个独立的准入 receipt——这才是真正的第三个权威面。它与选择证据表达同一次选择的两半，两者一旦不一致就要在每个消费点重新裁决谁优先，属于契约单轨禁止的双读。
- 被否决方案：写进 lane 回执——`DEC-008` 已就同一形状否决：lane 回执的 phase 闭集是 review 与 publish，选择发生在 review 之前，为它加 phase 等于把「从未进入生产」伪装成一次 review 结果。
- 被否决方案：写进 campaign report——report 是运行回执而不是新的真相源，且复制会话的 finalize 聚合写者会与选择器争抢同一字段，`DEC-008` 已就同一形状否决。
- 约束与影响：运营者的读法固定为两跳——「这个实体还能不能重新探测」读 verdict receipt，「这个明明有来源的实体为什么没进这一批」读选择证据的准入排除面；后者带 verdict ref，可一跳回到前者。
- 约束与影响：选择器此后新增的任何冻结期准入排除（例如候选池容量截断）必须落在同一个排除面上并声明自己的约束取值，不得新开一个面；未声明即由 [`DEC-019`](#dec-019) 的残差判定 fail closed。
- 约束与影响：该证据与 `DEC-008` 的 verdict receipt 同级受 GC protection，不得被清理或改写。
- 可观察面：local_contract 让准入挡下若干 `在场可用` 实体，断言选择证据可逐实体列举出局实体、约束与原因，实体键与 verdict receipt 逐字相同，且 verdict receipt 无任何准入字段。构造零准入使 spec 不被冻结，断言选择证据仍存在且出局集合可读。分别构造闸门未运行与闸门零出局，断言前者省略该键、后者该键在场且集合为空，两者不被读成同一结果。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 冻结期准入呈现面
- 关联验收：`GWT-013.t9`、`GWT-013.t10` 与 `GWT-012.t5`

<a id="dec-019"></a>
### DEC-019 冻结边界进入逐实体差集，未归属的出局残差 fail closed
- 决策：article 的跨阶段对账把 selection 阶段显式区分为两个集合——预筛 `在场可用` 集与冻结工作单元集，对账因此在四个集合之间做三条边界的逐实体差集。四个集合分别来自 verdict receipt、冻结选择证据与 execution spec、auto_research receipt、content_plan receipt，全部是既有产物，不新建第三个台账，与 `DEC-012` 同一范式。
- 决策：四个集合使用同一实体键 `<domain>/<entityType>/<name>`；对账只做集合差，不比较计数。记候选全集为 `C`、预筛 `在场可用` 集为 `V`、冻结工作单元集为 `F`、选择器已声明的准入排除集之并为 `X`、两个下游 ready 集为 `R_auto` 与 `R_plan`。
- 决策：闭合式为 `F ⊆ V` 且 `V \ F = X`。其中 `X ⊆ V` 由 `DEC-017` 的顺序不变量结构成立，`V \ F ⊆ X` 是必须被断言的一侧；残差 `(V \ F) \ X` 非空即 fail closed，不得记为统计项或警告。
- 决策：每条边界的出局原因只从拥有该边界的那个面读——`C \ V` 读 verdict receipt 的四态与子原因，`V \ F` 读选择证据的准入排除面，`F \ R_auto` 与 `R_auto \ R_plan` 读各自阶段的 receipt。四态不被要求解释它不拥有的边界。
- 理由：只有把 `V` 与 `F` 分成两个集合，被准入挡下的实体才有一条属于自己的边界可落；把预筛阶段的 ready 集直接定义为 `F` 会让 `V \ F` 恒为空，对账形式上闭合而出局实体从对账中整体消失。
- 理由：闭合必须是充要而不是单向包含。只断言 `X ⊆ V \ F` 时，任何新的、未声明的选择器侧丢弃都会静默通过；把残差判定写成 fail closed，才让「差额必有出处」由结构保证，而不是靠今天恰好只有一个排除来源。
- 理由：原因按边界归属而不是按枚举归属，是这条闭合式能与 `REQ-007` 并存的前提。auto_research 与 content_plan 的出局原因本来就不在四态内，跨阶段子句要求的一直是「该实体在该阶段出局的首要原因」，准入排除只是又一条同形的边界。
- 被否决方案：为准入出局建一个独立对账台账——`DEC-012` 已就同形方案否决：三阶段各自的 ready 集已经是既有产物，第三份记录只会成为可漂移的第二真相源。
- 被否决方案：以计数相减判定闭合（`|V| - |F|` 等于出局计数）——计数相等不证明是同一批实体，两个方向的错配可以互相抵消；`DEC-012` 已判定对账是差集而不是比较计数。
- 被否决方案：把残差降级为诊断统计并继续执行——残差的含义正是「有实体在无人认领的地方出局」，容忍它等于让 `GWT-013.t10` 的「精确列出出局实体」退化为 warn-only。
- 约束与影响：本闭合式只覆盖 article lane 的预筛对账，homepage 与 video 既有路径不变。
- 约束与影响：`X` 的载体键缺席时（准入闸门未运行）`V \ F` 必须为空集，否则 fail closed；这条依赖 [`DEC-018`](#dec-018) 的缺席与在场为空可分。
- 约束与影响：一次性抽取路径按候选池容量截断已合格集合时，被截断实体落在 `V \ F` 且今天没有声明面，按本条 fail closed。补法是在 `DEC-018` 的同一排除面上声明该约束取值，而不是放宽本闭合式。
- 可观察面：local_contract 构造一批实体使 `在场可用` 集大于冻结集，断言 `V \ F` 与准入排除集逐实体相等、`F ⊆ V` 成立，并单独注入一个既不在冻结集也不在排除集中的 `在场可用` 实体，断言残差判定 fail closed 而不是记为统计项；再断言仅计数相等而实体不同时同样 fail closed。三阶段逐实体对账仍由 `OPEN-004` 已分派的 api_integration 经一次真实 execution 的 selection、auto_research 与 content_plan receipt 完成，本次在其上追加 `V \ F` 这条边界的断言。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 article 跨阶段对账闭合面
- 关联验收：`GWT-013.t9`、`GWT-013.t10` 与 `GWT-013.t6`

<a id="dec-020"></a>
### DEC-020 WorkRequest 是确认后才存在的独立聚合，编译只进入现有 envelope 单轨

- 对象边界：WorkRequest 是 `separate_aggregate`，只拥有一份已确认的规范化意图、内容寻址 identity、resolver policy/catalog digest、fresh/retry 模式、显式 dependency ref/digest 与编译结果引用。preview 是无持久化副作用的 query result，不是聚合。Campaign、单 carrier Execution、各类 Reconciliation 与 SourcePool 继续各自作为独立聚合，WorkRequest 不内嵌其成员、不改写其状态，也不把无界运行结果收进自身。
- 生命周期：WorkRequest 与整批 envelope 只允许在一次原子发布成功后以 `compiled` 终态出现。preview、needs-input、blocked、cancel 或编译失败均不创建 WorkRequest。`compiled` 只通过 compile receipt 引用下游，不跟随 Campaign/Execution 改写状态。当全部下游引用已终态、相关 immutable release 已退役且连续 180 天无 GC 保护引用时才可进入归档候选。归档必须先写 create-once archive receipt，删除必须由引用图证明零可达并保留 digest/ref tombstone。法律保留或任一 compile/retry/release/rollback 引用存在时不得归档或删除。规范化意图不保存自由文本、凭据或个人资料，合规删除只处理外部 actor 引用，不能改写内容寻址 payload 或伪造零引用。
- 身份决定：preview 完成全部字段与 dependency 校验后，confirm command 才按 canonical confirmed payload 计算 `workRequestDigest` 并创建 WorkRequest。run date、sequence 与 execution identity 不由用户输入，也不由 WorkRequest 另行分配；它们由既有 envelope identity 组件一次性分配并冻结进同一 compile receipt。相同 WorkRequest 重放只读取该 receipt，因此不会因时钟变化产生新 identity。校验失败、needs-input、blocked 与 cancel 均不得消耗 execution identity。
- fresh/retry 决定：一份 WorkRequest 只能全量 fresh 或全量 retry，不混合两种模式。retry 只包含需要恢复的 active carrier，并为每个 carrier 精确绑定 predecessor execution 与所属 reconciliation receipt。任一绑定缺失、字节漂移或 carrier 集不闭合时在创建 WorkRequest 前失败。
- SourcePool 决定：preview 可以在 SourcePool 缺失时返回 typed blocked 与取得物理 source-ready evidence 的恢复动作。confirm command 把每个 active carrier 的 exact SourcePool/evidence ref/digest 作为写前前置，缺失时不创建 WorkRequest 或 envelope。milestone preset 绑定同名 M100/M1000/M10000 pool，任意显式数量包括 M1 则绑定既有 `targetScale=WORKLOAD` pool，并要求其 active carrier 与 workload target 和意图逐项相等。compiler 不发现、不采集、不修复 SourcePool。
- command/query 分流：`WorkRequestPreviewQuery` 只解析与验证输入并返回 preview、needs-input 或 blocked。`WorkRequestCommandWriter` 只接受 preview digest 的 confirm/cancel command，其中 cancel 零写入。`WorkRequestCompilationQuery` 只按 `workRequestDigest` 读取 compile receipt 与 envelope refs。三者不暴露通用 Repository、动态 filter 或运行时数据源选择。
- 唯一映射 owner：carrier、operation、default selector 与 operator prompt ref 的对应关系由一个受 schema 校验并绑定 digest 的 carrier execution policy 单点拥有。envelope builder、WorkRequest compiler 与 submission validator 都消费同一 policy。`request_envelope.py` 与 `campaign/submission.py` 的手写映射在迁移后删除；compiler 禁止复制第四份映射。`write_campaign_envelopes` 没有生产调用，直接退役，不把死分支扶正为第二批量入口。
- 唯一写者：现有 `write_scale_envelopes` 收口为 envelope batch 的唯一内部 writer，并先在隔离 staging root 构建、校验全部 active carrier payload，再以同文件系统原子发布整个 sequence 目录。任一 carrier 构建、schema、dependency、collision 或持久化失败时新 envelope 可见数为零。已经存在的同 digest batch 只读返回；同 identity 异 digest 写前失败。
- 结果单义：preview、needs-input、blocked、confirmed 与 canceled 是互斥结果。needs-input 只表示用户输入可补充，blocked 只表示外部 canonical dependency 当前不能满足。confirmed 必须同时给出 WorkRequest digest、policy/catalog digest、dependency set digest、compile receipt 与每 carrier envelope ref/digest。失败不得编码为空集合或上一份成功结果。
- 可测试观察面：local_contract 经三个 typed port 观察修改、取消、确认、四态结果、同 digest replay、collision、全有或全无和 owner 禁写边界。api_integration 经真实 CLI 观察 confirm 后现有 submit/freeze、provider/source/rights failure 与新 `retryOf` 恢复。user_acceptance 只消费 immutable release，在 entity homepage、article、image、video 四个 surface 分别绑定同一 release digest 的 CaseResult。
- 失败恢复：confirm 前失败回到 preview，不留下 WorkRequest、execution identity 或 envelope。confirm 后而 submit 前失败重放同一 WorkRequest 与 compile receipt。submit 后失败只能创建新 retry WorkRequest 并精确消费旧 terminal/reconciliation receipt。App UAT 失败沿已有 release rollback receipt 恢复 previous active，不重建 release。
- 质量、容量与成本：preview 与 confirm 不调用 semantic Provider 或环境服务，单请求最多四个 carrier，CPU、内存与持久化成本相对 envelope 大小线性。成本方向为增加但有界：startup 基线按每日最多 1,000 次 confirmed request、每份 WorkRequest 与 compile receipt 平均各 16 KiB 估算，日增约 31.25 MiB、30 天约 0.92 GiB、180 天热保留约 5.49 GiB；schema 分别以 256 KiB 为硬上限，因此 180 天未压缩最坏上界约 87.9 GiB。既有最多四份 envelope 不计作 WorkRequest 新增成本，实测超过任一基线必须先更新容量设计而不是静默放宽上限。
- 性能与观测：preview/confirm 本地 p95 SLO 分别不超过 2,000/5,000 ms。在 1-carrier 与 4-carrier 的 success、blocked、collision 场景各形成专项 benchmark，缺样本或未达标保持 `OPEN-010`。WorkRequest 与 compile receipt 必须记录同一 `correlationId/workRequestDigest`、typed outcome、`durationMs`、active carrier 数、发布 artifact 数与总字节数。preview 全量记录不含用户原文的结果与时延，confirm/compile receipt 全量保留 180 天并按前述引用保护归档。按 outcome 分组计算 5 分钟窗口计数和 30 天 p95：任一 all-or-nothing violation 或 identity collision 立即 `GATE_BLOCK` 并产生高优先级告警。至少 20 个成功样本后 p95 连续两个窗口超 SLO 产生告警，少于 20 个样本只报 `insufficient_samples`、不得冒充达标。观测由 receipt 与结构化结果派生，不新增可写运行台账。
- rollout 与 rollback：先以 `scale=M1`、`workloadMode=explicit`、`targetScale=WORKLOAD` 的 homepage=1 非环境 source-ready 输入验证 preview/confirm 与 batch 原子性，再扩到四 carrier，随后只以 milestone preset 进入 M100/M1000/M10000。未形成 immutable release 前不触达环境。回滚只停止消费未提交的 WorkRequest 并保留现有手工 `prepare-campaign -> task execute` 单轨；已激活 release 使用原 immutable release 与 rollback receipt 在 5 分钟目标内恢复，不重新构建。
- 受影响契约：新增 WorkRequest、compile result 与 carrier execution policy 三个 Data execution schema，并新增一份受治理 carrier execution policy 实例。现有 request envelope 只扩展条件约束，使 `workloadMode=explicit` 的任意 M1 及以上请求可携带既有 `targetScale=WORKLOAD` SourcePool binding；不增加字段、版本信封或双读。execution spec、reconciliation receipt、SourcePool 与 release schema 不复制字段。
- 关联要求：`REQ-009`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的意图 preview、确认编译与四载体数量闭环
- 关联验收：`GWT-015`、`GWT-016`

<a id="dec-021"></a>
### DEC-021 容量自举是 measurement-only process manager，日常 execution 仍只认受治理 receipt

- 对象边界：`CapacityCalibrationBootstrapRun` 是独立 process manager，只拥有一次 `hostClass + providerTier + semanticSelectionId + M100 measurement workload digest + bootstrap policy digest` 的测量生命周期与 append-only evidence refs。`GovernedCapacityCalibrationReceipt` 继续是独立 create-once fact。WorkRequest、Campaign、Content Execution、SourcePool、canonical publish、release 与环境均不归 bootstrap 所有。
- 单向数据流：唯一顺序为 `bootstrap measurement -> frozen fleet/object timing -> calibrate-capacity Provider/resource probes -> Git-tracked receipt -> daily execution policy`。日常 execution 不得在 receipt 缺失时自动回退 bootstrap，bootstrap 也不得读取或回写日常 policy。
- 安全装配：bootstrap 使用专用 composition，物理上不装配 author/reviewer、canonical append、release、ship/import writer。首份 receipt 缺失时只允许版本控制的 measurement safety policy 固定单 worker，该上限只限制 M100 measurement，不得投影成日常容量或默认值。
- Command/Query：`CapacityBootstrapCommandWriter` 只接受显式 `prepare/run/finalize/cancel`，`CapacityBootstrapStatusQuery` 只返回 `prepared|running|measured|failed|canceled` 与 evidence closure。`CapacityCalibrationCommandWriter` 只消费 `measured` closure。日常 `CapacityPolicyQuery` 只返回有效 receipt 或 typed blocked，不能读取 bootstrap state。
- 失败恢复与回滚：bootstrap 中断保留已确认样本，以新 bootstrap identity 与 `retryOf` 续测，不原地补写。证据不闭合时零 receipt 可见。新 receipt 被证明无效时，新 execution 只能显式重新绑定上一份仍有效且 applicability 匹配的 receipt，已冻结 execution 不改写。
- 可观察面与 SLO：bootstrap 引起的 canonical/release/environment 新成功事实恒为 0。每个 measurement 对象必须有 typed timing 终态，fleet peak、wall clock、Provider probe 与资源样本逐字节闭合。未同时满足 M100 与每候选 100 probes 时终态只能是 failed，measurement elapsed 不表述为生产吞吐。
- 可测试面：local_contract 证明 authority/composition/状态机边界，包括普通 execute 缺 receipt typed blocked、bootstrap composition 无 publish writer、measurement evidence 不能被日常 policy 读取。api_integration 从空 output/无 receipt 启动真实 bootstrap 进程，以受控 Provider state 完成 measurement-only 流程，并证明 canonical/release/environment 成功事实增量均为 0；它不承担真实 Provider 容量结论。live reliability soak 才在 `local-apple-silicon + cursor_grok` 完成真实 M100 measurement 与每个候选并发档 100 次 probe。repository gate 删除动态 skip，在干净检出直接校验 tracked closure 摘要与 applicability。
- 被否决方案：默认容量常量、runtime profile、旧规格数值、事故记录或 preflight probe 观测回填。普通 execute 自动降级 bootstrap。手写或合成 receipt。让 bootstrap 直接发布内容或与日常 policy 双读同一可变路径。
- 关联要求：`REQ-006`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的容量自举与执行策略冻结
- 关联验收：`GWT-019`、`GWT-009.t4`、`GWT-010.t4` 与 `GWT-011.t2`

<a id="dec-022"></a>
### DEC-022 media source admission 与 post-author independent review 是两个顺序固定的 append-only fact

- 对象边界：`MediaSourceAdmissionReceipt` 由 source owner create-once 写入，绑定 asset bytes、目标实体、acquisition、媒体探测、rights attribution、source-scoped semantic review 与 portable source evidence root。`ScaleSourcePool` 只引用 accepted source admission，不拥有或推导内容级审核。`IndependentAssetReviewReceipt` 由 execution 后的 review owner另行写入，绑定同一 asset/object、execution manifest、author/reviewer identity 与三个互异 runId。canonical publish 只消费 accepted independent receipt。
- 固定时序：唯一顺序为 `acquire/probe/rights/source review -> source admission -> SourcePool -> WorkRequest/execution -> author/reviewer -> independent review -> canonical publish/release`。SourcePool 可调度只说明物理来源已准入，不表示内容可发布。
- Evidence root：source-admission root 内 catalog、acquisition、probe、rights 与 source review 全部使用 root-relative safe ref，并绑定逐文件摘要和 root digest。execution 后由 closure builder 形成独立 review root，以内容摘要引用 source admission 与 execution/author/reviewer evidence。两个 root 都是不可变 capsule，禁止绝对路径、`..`、symlink、调用者本地路径和人工复制 JSON。
- Command/Query：`MediaSourceAdmissionCommandWriter` 验证并冻结 source receipt，`MediaSourceAdmissionQuery` 向 SourcePool 返回 accepted/blocked typed result。`IndependentAssetReviewCommandWriter` 只在 execution evidence 齐全后冻结 receipt。`MediaPublishAdmissionQuery` 是 publish/release 唯一闸门，要求 accepted independent receipt 与 exact identity closure。
- 失败恢复与回滚：source root/ref/digest 漂移时零 SourcePool candidate，只能从原 acquisition bytes 以新 admission identity 重建。post-author review 缺失或 blocked 时保留 SourcePool 可调度事实但 canonical 为零，恢复必须产生新 author/reviewer run 与新 review receipt。已发布后发现审核错误时走既有 release rollback，再由新 content version 更正，不改写旧 receipt。
- 可观察面与 SLO：accepted independent receipt 前 canonical 可见数恒为 0，receipt 后同 stable identity canonical append 恰为 1。Image/Video 分开计量。Video `entityMatch=mismatch` 的 source admission 恒为 blocked，playable、4K 或 premium eligible 均不能覆盖该结论。
- 可测试面：local_contract 证明 SourcePool 只绑定 source admission、publish 只绑定 independent receipt且二者不可互换。api_integration 从干净 root 对 Image/Video 各跑一条完整链，断言三个 runId 互异、publish 前零可见、receipt 后精确一和 replay 同摘要。negative integration 覆盖 root drift、reviewer local-root drift、execution identity 缺失及 Video mismatch。
- 被否决方案：SourcePool 强制 pre-execution independent review。把 source-scoped review 冒充内容 independent review。publish 仅凭 SourcePool 放行。跨 root 相对路径或绝对路径。旧 independent receipt 与新 source admission 双读 fallback。
- 关联要求：`REQ-001`、`REQ-002` 与 `REQ-009`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的首波 media SourcePool 与发布准入
- 关联验收：`GWT-017`

<a id="dec-023"></a>
### DEC-023 invalid canonical 由唯一 repair process manager 按三个证据谓词收敛

- 对象边界：canonical Homepage/Content 与 append-only pool ledger 继续拥有 payload 和版本。`CanonicalIdentityRepair` 是独立 process manager，只拥有 invalid identity 的诊断快照、immutable evidence binding、resolution 与进度，不复制 canonical payload。terminal 是 append-only identity fact，不伪造新 content version。
- 唯一 Query：`CanonicalIdentityStateQuery` 返回互斥的 `absent|admitted_current|invalid_record_repairable|invalid_payload_rebuildable|invalid_unrepairable|terminated`，并携带最深层 error、唯一 recovery action 与 optimistic snapshot token。pool-inspect、backfill planning、source-ready scheduling 必须读取同一 query，不得把 `DATA.POOL.PAYLOAD_DIGEST_DRIFT` 改写为 generic not-admitted。
- 三个确定谓词：fresh evidence 证明 current bytes 仍是同一逻辑版本时只能进入 `invalid_record_repairable`。fresh immutable author/review/rights evidence 证明 current bytes 是新 payload 时只能进入 `invalid_payload_rebuildable`。两类 evidence 均不成立时只能进入 `invalid_unrepairable`。缺 evidence 或两类同时成立均 typed blocked，不由调用方猜测。
- 唯一 Command：`ResolveInvalidCanonicalIdentityCommand` 按 query token 只接受对应的 `record_repair|payload_rebuild|terminate`。inspection、backfill 与 scheduler 均无 canonical 写权限。`record_repair` 保持 `contentVersion`、追加 `recordSequence + 1`。`payload_rebuild` 原子写入 `contentVersion + 1` 与 `recordSequence + 1`。`terminate` 保持 `contentVersion`、推进 `recordSequence` 并冻结 terminal reason/next action。
- Scheduler 语义：只有 `admitted_current` 可判已消费。三个 invalid 状态不得因 manifest 存在而静默过滤，也不得 semantic dispatch，必须返回 recovery action。`terminated` 以可读终态退出 backlog。`gap > 0 && backlog = 0 && recoveryAction 缺失` 是立即 GATE_BLOCK 的不变量破坏。
- 失败恢复与回滚：resolution 只在隔离 staging 构建，payload、ledger append 与 effective-current 切换全有或全无。任一摘要、identity、sequence、query token 或写入冲突保持原 invalid 状态且零半可见版本。完成后的 record/payload/terminal fact 都不倒写，后续纠正只能以新 evidence 启动新 case；terminated identity 不复活，后续供给必须选择新 stable identity。
- 可观察面与 SLO：`actionless_invalid_identity_total` 与 `invalid_identity_semantic_dispatch_total` 必须恒为 0，同 identity effective-current 数只能是 0 或 1，三个读取面的 state/error/action 逐项相等。每个 repair case 全量记录 resolution、duration、evidence digest 与 terminal reason，保留期跟随 canonical 引用保护。
- 可测试面：local_contract 覆盖完整状态转移、三谓词互斥、optimistic conflict、两个版本号规则、terminal 零新版本与三 reader 同源。api_integration 必须先通过真实 canonical application command 创建有效状态，再经 canonical storage adapter 暴露的 test-only fault-injection port 在存储边界制造 payload digest drift；禁止直接写 manifest、ledger 或 fixture seed。随后注入三种互斥 evidence，断言首轮保留原 error 与唯一 command，repair/rebuild 后只有一个 current，terminal 分支零新内容版本且退出 backlog。reliability 在 staging、ledger append、current switch 三个故障点注入失败并断言旧状态不变。
- 被否决方案：manifest-only 判已消费。折叠深层错误。放宽 payload digest。原地覆盖 payload/record。让 backfill 同时承担 inspection 与 repair。repair/terminate 两套 CLI。用空 backlog或删除文件表达 termination。
- 关联要求：`REQ-001` 与 `REQ-009`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 canonical 修复与 source-ready 调度
- 关联验收：`GWT-018`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。
- 截止耗尽：剩余时间归零只取消未启动 job 的启动资格，运行中的 job 收敛为 typed deadline 终态，已合格对象不受影响。
- 续跑路径：可续跑中断在运行回执里给出精确 refs，新的 `retryOf` 只纳入这些 refs 并冻结新的绝对截止与新的容量来源绑定。
- 容量来源缺失：calibration receipt 缺席、摘要漂移或超出适用范围时在 execution 冻结处 fail closed，不进入运行期再补救。
- 预筛未完成：`探测失败` 是判定未完成的显式终态，运营者按 receipt 中的可续跑 refs 起新的 `retryOf` 重新探测这些实体；`在场不足` 与 `缺席` 携带不可续跑依据，运营动作是换实体、按 calibration 调阈值或修来源闭集。
- 候选不足：处置取值为「不足即阻断」时在目标选择收口一次性阻断；取值为「部分准入」时以实际合格集合继续并写入 typed shortfall，合格数为零时同样阻断。处置取值缺席在 execution 冻结处 fail closed，不进入运行期再补齐。
- 冻结期准入零通过：`在场可用` 非空而准入后为零时 lane 仍然阻断。批次级归因取 `DEC-005` 共享值对象的「全部候选实体被选择器准入排除」，由 lane 回执写入并携带指向 `DEC-018` 排除面的逐实体准入排除 refs，缺该 refs 时该原因不成立。恢复动作是扩大候选范围——扩大候选区域 frontier 取得尚未触及累计上限的实体，或按治理流程调整多样性策略，而不是修来源；也不得用实体级首要原因聚合冒充该原因，那份聚合此时全为 `在场可用`，会把运营者指向一个没有问题的来源。
- 对账残差：`V \ F` 出现未归属出局时按 `DEC-019` fail closed；恢复动作是在准入排除面上补齐该出局的约束取值，而不是放宽闭合式或把残差降级为统计。
- 预筛能力回滚：article 预筛不设 lane 级 bypass 开关，关闭它等于让「冻结之前完成判定」退化为 warn-only；阈值层面的回滚沿用 `DEC-006` 范式，由新的 `retryOf` 重新绑定上一份仍有效的 calibration receipt。
- 灰度范围：预筛只改变 article lane 进入冻结的候选集合，按 lane 逐 execution 生效，不改变 App 用户可见终态，因此不需要环境级灰度。

## 6. 质量与观测

- 记录 operation、终态、延迟与 canonical error；特有阈值由 spec 和运行配置约束。
- 交付阶段回执记录实测并行峰值、wave 数与绝对截止，三者是运行事实，不参与对象准入、publish、finalize 与 milestone 判定。
- 来源发现阶段报告记录实测峰值并行数与冻结上限，elapsed 与每分钟实体数只表述为当次运行事实，不表述为已测得的稳态吞吐。
- 上限饱和度与截止耗尽次数按 execution 观测并作为下一次 calibration 的输入；观测值本身不得回写为上限。
- 预筛按 execution 观测四类首要原因的分子、分母与占比，以及探测预算耗尽次数与补采轮次数；`探测失败` 占比是预筛健康度信号，与其余三类分开计量。
- 预筛观测值只作为下一次阈值 calibration 的输入，不得回写为匹配置信度、正文字数或探测预算的取值。
- 抽取循环的 typed stop reason 按 execution 观测并进入 lane 回执的诊断统计，只作为下一次阈值与轮次预算 calibration 的输入；它不进入运营者终态呈现面，也不改变对象准入、publish、finalize 与 milestone 结果。
- 冻结期准入按 execution 观测出局实体数与按约束分类的构成，并与预筛四类分开计量、不合并分母。观测值只作为下一次多样性策略 calibration 的输入，不得回写为每实体累计上限或 Top-N 上限。
- `V \ F` 的未归属残差数是门禁结果而不是统计项：它必须恒为 0，非 0 即 `GATE_BLOCK`，不得以趋势或占比的形式呈现。
