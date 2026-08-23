# L2 Business Capability：运行时数据工程 (`runtime-data-engineering`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。

## 2. 范围与非目标

### In Scope

- tagRef 发布物。
- canonical entity 与 entityRef。
- 内容语义 relationEdge 候选事实；不包含关注、圈成员或会话成员等在线交易关系。
- canonical publish、immutable release、环境 activation receipt 与数据隔离。
- Data 平台虚拟作者池、Data 内容池、准入结果、追加版本与环境 ReleaseManifest 选择。

### Out of Scope

- 在线推荐排序实现。
- 业务服务在线写路径。
- 真实用户 Persona 与 UGC 的创建、更新和删除；它们仍由 User/Content 公开 command/event 拥有。

## 3. Journey / Scenario 贡献

- 本节点是横切 runtime 工程能力，不拥有 App 用户 command 或 Scenario。
- 下游价值证据由 [`AppRoot UAT-001`](../../spec.md#uat-001) 承接：本能力只向发现、搜索与对象连接旅程提供 immutable release 绑定的 canonical projection。

## 4. Story



- [`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)：缺来源或权利的对象保持 typed GATE_BLOCK，不能进入 canonical publish。
- [`geo-content-trinity`](./geo-content-trinity/spec.md)：图片来源、下载字节、授权与发布引用均可回放。
- [`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)：缺任一 required rights 字段的资产不能进入 release。
- [`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)：不满足 admission 的候选以 typed issue 阻断。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 数据工程同源输入验收

- tagRef、canonicalEntityId、entityRef、内容语义 relationEdge、creator/avatar 与 post media 均有 canonical publish/release 来源。
- 作者池准入只保存 `processResult`、`qualityResult`、版本、证据引用与状态；只有 `completed + passed + active` 可进入新 release。头像只做格式、可读取、清晰度、安全和内容质量检查，不保存 Research/Commercial 范围，不参与作者或内容的 Prod 准入，也不产生内容 commercial variant。
- 内容池准入只保存 `processResult`、`qualityResult`、`usageScope=research|commercial`、版本、证据引用与状态；未知或缺商用证明一律是 `research`，`commercial` 必须由 receipt 中公开可审计的商用发布权证明支持。
- `contentId`/`authorId` 是稳定身份，有效变化只追加递增版本；同一追加键相同 digest 可幂等重放，不同 digest 返回 typed conflict，禁止覆盖旧版本。
- alpha/beta/gamma/prod 只激活 immutable ReleaseManifest，数据策略不漂移且无环境 fixture/self-seed 旁路；Manifest 只决定召回资格，不直接提供首页列表或搜索结果。
- 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

<a id="req-002"></a>
### REQ-002 标签真相源为数据工程 control_plane/governance/taxonomy；publish/tags 仅保存发布对象实际引用的 consumer snapshot，不得恢复扁平枚举或复制整棵 taxonomy

- 标签真相源为数据工程 `control_plane/governance/taxonomy`；`publish/tags` 仅保存发布对象实际引用的 consumer snapshot，不得恢复扁平枚举或复制整棵 taxonomy。
- 实体归一产物必须能映射到运行时 `canonicalEntityId`。
- 作者池与内容池是四环境的统一源头。环境定向 ReleaseManifest 可按稳定选择生成，Alpha 最多 2,100 个 Data Post，Beta 最多 10,000，Gamma 最多 100,000，Homepage 不计入 Post cap。M100/M1000 的环境无关 Research Manifest 分别精确冻结 `100/100/100/10` 与 `1000/1000/1000/100`，同一 manifest 可依次供 Alpha/Beta/Gamma/Prod 在 private Research isolation 下激活。Commercial 生产发布是另一个显式授权 release，不得由环境名或全局运行配置推导。
- ReleaseManifest 以 `releaseId + payload digest` 作为唯一发布身份，精确绑定内容版本、作者版本及 Entity/Tag/媒体闭包；环境 activation/import/rollback/replay receipt 不得建立第二套 snapshot/bundle 发布身份。
- Research 与 Commercial 必须从同一 frozen canonical pool snapshot 构建并绑定相同 `poolDigest`，但使用不同 `releaseId + payload digest`。Research 可选择 `research|commercial` 内容；Commercial 只选择逐对象 `usageScope=commercial` 且全部资产权利闭合的授权子集，不得修改 Research release 或复用其环境 receipt。
- 每个环境的 acceptance receipt 必须同时绑定 Data release 身份、runtime candidate 身份、实际 target-scoped App CaseResult、lifecycle Exit、Provider、观测与 cleanup。Beta、Gamma、Prod 的 receipt 还必须绑定前一环境 acceptance receipt 的 exact-byte digest；只绑定 `appUatEnvelopeDigest` 不构成环境晋级。
- Data CLI 只暴露易于理解的池入口。`release pool-inspect --milestone M100|M1000` 统一输出 `ready|partial|blocked`，并按 `quality|eligibility|delivery` 展示 Homepage、Article、Image、Video 的 observed、admitted、累计唯一 publishable、deliveryPending、target、gap 与确定性 next wave。
- 逐对象问题只影响该对象，成功部分可以继续构建 Release。inspect/build/select 只读取显式 create-once pool record；缺 admission、稳定 `contentId/contentVersion`、完整 `sourceAttribution` 或 source identity 的历史对象一律按对象排除，禁止从 review、路径或当前 source identity 只读推导默认 Research。
- governed repair 只能基于 canonical object bytes 与 fresh source evidence 追加更高 `recordSequence`，保持原 `contentVersion`，并冻结完整 attribution、Research admission 与 modern execution 或 typed legacy migration identity；旧 record、旧 release 与旧 task receipt 不改写、不复用。
- `release pool-build` 必须显式传入 `--release-class research|commercial`：两者读取同一 frozen canonical pool snapshot 并记录相同 `poolDigest`，Research 可选择 `research|commercial` 内容，Commercial 只选择 `usageScope=commercial` 且 entity/post 全资产商用权利闭合的授权子集；Commercial 仅携带该子集引用的 Creator，头像仍按作者既有 identity/CAS/quality/rights-evidence 闭包而不新增 usageScope。也可用 `--milestone M100|M1000 --release-class research` 构建环境无关精确 cohort。缺 admission、完整 `sourceAttribution`、引用或授权范围不匹配的对象只进入 typed excluded/deliveryPending，不阻断同池其它对象。Manifest 冻结后仍要求完整导入与验证，禁止部分激活。
- `release pool-inspect --by-task` 必须显式接收一个或多个 exact execution ref，只读取这些 execution 的 semantic journal、review 与 pool-delivery intent。不得遍历全部 task tree或读取旧 receipt。它按批输出 target、generated、quality、usageScope、admitted、publishable、deliveryPending、excluded、成功率与阶段耗时。这些运行统计只定位瓶颈，不改变对象准入。
- 定向改写只能由 `task execute --rewrite-content-id --expected-version --rewrite-reason` 创建新的 retry execution：保持 `contentId`、版本精确加一、重新验证作者/实体/标签/媒体闭包，旧版本与历史 release 只读；头像或作者资料变化不触发内容改写。
- `release supply-chain-drill` 只编排现有 Data/stackctl 正式入口，按 inspect/delivery/rehearsal 输出一个可重建 receipt，逐阶段记录耗时、输入/成功/失败/排除数和首个 typed blocker；不得直写数据库、容器、Search 或 Recommendation 投影。
- content importer receipt 必须携带 `sourceOwner=qwq_data` 与等于 release attestation `payloadSha256` 的 `manifestDigest`，并保留 exact post/author readback binding。
- Data Post 与 content durable outbox 必须同事务提交，Recommendation 与 Search 只消费 Content 所有的 Post lifecycle；禁止 Mongo 直写、仅 Redis 推送、直接 seed 搜索索引或推荐候选表。
- 每个环境的回滚准出必须写 create-once `environment_release_lifecycle_exit`，同时绑定 original apply/verify、rollback-to rollback/verify、replay apply/verify，并重新证明 replay `manifestDigest` 等于 original immutable payload digest；不得用三份互不关联的 run 目录代替 Exit receipt。
- `release discard` 除进程互斥外还必须保护长期验收引用；passed `release-readiness.json` 是永久保护证据，UAT 则由 Data-owned、append-only `release_acceptance_lease_event` acquire/revoke 显式包围。只有已绑定 acquire 的 revoke 才能关闭 lease，revoke 不得撤销 passed readiness 的保护。
- 同一 environment 同一时刻只允许一份未 revoke acceptance lease；该 lease 必须阻断该 environment 对任意 release 的 apply、rollback、verify 或另一份 lease acquire，环境级进程锁覆盖“检查 active lease → 写事件/执行 ship”的完整临界区，不同 environment 的锁相互独立。
- 新增数据发布物必须提供可执行 schema 校验或 canonical contract fixture，且失败时不得进入发布包。
- 内容、Creator、实体、标签与发布媒体禁止由 T3/UAT、领域 API、数据库脚本或环境 bootstrap 创建；用户账号、评论、圈子、会话与消息由各领域公开 command/event 拥有，不属于 Data release。基础设施灰度探针不得进入业务 query/projection。
- 单元/合约测试只写 tempfile 临时根，pytest 不得向仓内根或 `QWQ_OUTPUT_ROOT` 落盘（conftest 落盘隔离门）。

<a id="req-003"></a>
### REQ-003 标签发布物必须自带采集通道与在线消费方式声明

- taxonomy 每个节点必须声明采集通道与消费方式；采集通道取值限于拍摄元数据、地点选择、创作者勾选、点评勾选、行为事件与仅管线派生。
- 取值为仅管线派生的存量节点进入基线清单并只减不增，新增节点不得使用该取值。
- 消费方式必须至少包含召回过滤、排序因子、交集判定与搜索筛选之一，缺失声明的节点不得进入 canonical publish。
- 同一现实概念跨轴出现时由节点自身声明同义引用，跨轴权重传播只读取该声明，不按路径前缀推测轴间关系。
- 境外行政区必须覆盖声明的最小目的地集合，覆盖不足时视为发布物不完整并阻断发布。

<a id="req-004"></a>
### REQ-004 作废 canonical 内容必须经 empty release 与受治理 replay

- 需要清除作废对象时，操作者必须先对所有仍承载这些对象的环境 full-sync 同一已核验 empty immutable release，并以 release lifecycle 与 baseline API readback 证明环境已进入零对象状态。
- `release reset-canonical` 只能在无 active content task、全局 release operation lock 与 canonical publish lock 均可独占时原子清空 publish 与 inventory；禁止手工删除 inventory、提交脏中间态或为旧 execution 事后补 receipt。
- reset 后只允许从 terminal execution 通过同 execution ID resume，或以新 sequence `retryOf` 执行 typed recovery；已完成 acquisition、author、review 的 `retry_delivery` 只能恢复 exact pool delivery，不得重跑或改变上游身份。
- 本要求不冻结长期 `content_library + holdings` 的对象所有权或 durability。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 数据工程同源输入验收

- GIVEN 执行“数据工程同源输入验收”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“数据工程同源输入验收”对应动作。
- THEN tagRef、canonicalEntityId、entityRef、内容语义 relationEdge、creator/avatar 与 post media 均有 canonical publish/release 来源，在线交易关系不存在于 Data release。
- THEN 作者只按完成、质量和 active 准入；同一合格头像可进入 alpha/beta/gamma/prod，头像变化只增加作者版本，不改变内容 `usageScope` 或创建内容变体。
- THEN Research 与 Commercial Manifest 从同一 frozen canonical pool snapshot 构建并绑定相同 `poolDigest`；Research 接受 research/commercial 内容，Commercial 只接受逐对象授权闭合子集且只携带被该子集引用的 Creator，坏对象 typed excluded 不阻断其余合格对象。环境无关 M100/M1000 Research Manifest 可由 Alpha/Beta/Gamma/Prod 逐环境独立激活，Prod Research 必须保持白名单、签名媒体、禁止公开索引/分享/导出且不得升级为 Commercial。
- THEN 池报告只用 `quality`、`eligibility`、`delivery` 解释 `ready|partial|blocked`；单对象缺 admission 或引用时成功对象仍可发布，M100 gap 和所有过程统计不改变对象准入结果。
- THEN 历史对象缺显式 pool record、稳定身份、完整 `sourceAttribution` 或 source identity 时按对象排除；只有 governed repair 追加同 contentVersion 的新 record 后才可重新计数，reader 不运行 compatibility fallback。
- THEN 批次统计、定向改写和 supply-chain drill 均引用既有 task/object/release/environment receipt，不建立第二套内容或发布真相源。
- THEN 同一 milestone 的 `releaseId + manifestDigest + sourceIdentitySetDigest` 按 Alpha→Beta→Gamma→Prod 产生独立 activation/import/API/media/rollback receipt；后续环境必须冻结前一环境 passed acceptance receipt、实际 App CaseResult 和 lifecycle Exit 的 exact-byte digest，且无 fixture/self-seed 旁路。
- THEN importer、public feed/media 与 Ops/UAT readiness 均绑定同一 immutable payload digest。
- THEN Manifest Data Post 数、导入数、active 数、Search 可查询数与 Recommendation 可召回数相等；任一不等即 verify 失败。
- THEN 每个环境具备 original→rollback→same-digest replay Exit receipt。
- THEN 活跃任务、passed readiness 或未 revoke acceptance lease 任一存在时 cleanup 均 fail-closed。
- THEN release A 的未 revoke acceptance lease 阻断同一环境 release B 的 ship 与 lease acquire，且不同环境可独立推进。
- THEN 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

<a id="sit-002"></a>
### SIT-002 empty baseline、canonical reset 与 exact replay 保持同一证据链

- GIVEN 作废对象仍可能存在于环境或 canonical publish，且已选定 immutable empty baseline 与可恢复 terminal execution。
- WHEN 操作者依次完成 empty baseline full-sync/readback、`release reset-canonical` 和 terminal execution replay/adopt。
- THEN reset 只在环境零对象 lifecycle、无 active task、全局 release lock 与 canonical publish lock 同时可证时发生，publish 与 inventory 不留下未归属删除或部分清空。
- THEN replay 只消费原 terminal evidence 与 typed recovery，`retry_delivery` 不重新执行 acquisition、author 或 review，也不改写旧 execution receipt。
- THEN 重建后的 creator、entity、post、tag、media、rights、source identity、payload digest 与 release staging/CAS 引用形成 exact closure。
- THEN 任一环境不是零对象 readback、active task 仍存在、任一锁冲突、replay evidence/closure 错配或执行中断时产生 typed blocker/terminal receipt；publish、inventory 与旧 receipt 保持进入该步骤前的已确认状态，部分新 sequence 不得进入 release。

## 8. 开放事项

<a id="open-004"></a>
### OPEN-004 统一池发布的复合环境验收尚缺完整子句级真实证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前作者/内容最小准入、全池稳定选择、governed repair、Post 与 durable outbox、Search 查询校验及容量观测已有 local contract，但 canonical pool 的大量历史对象仍缺显式完整 record，且尚无同一新 milestone release 的四环境真实顺序 activation；目录数量、静态测试或旧环境回执不能声明为 Alpha/Beta/Gamma/Prod 的完整发布闭环。
- 完成判定：`SIT-001` 的全部结果子句 `sit-001.t1..t16` 分别具备直接 `spec_ref`；同一新 M100/M1000 Research `releaseId + releaseDigest` 在 Alpha/Beta/Gamma/Prod 分别完成 import、Search/Recommendation exact-count verify、private isolation、activate、rollback 与 same-digest replay，Commercial 另由显式授权 release 验证，且 Mongo/Provider/真实 App 证据均非 fixture 或旧回执。

<a id="open-002"></a>
### OPEN-002 标签发布物在创作侧没有采集通道，绝大多数标签处于孤儿状态

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前绝大多数标签没有任何用户侧写入通道，内容标签只能由数据侧 release import 产生，创作者发布的内容不携带标签。地理轴节点数量最多，但在地点选择结果被解析为标签引用之前同样不产生真实分布。由此召回过滤、排序因子、交集判定与搜索筛选都只能作用于数据侧内容，标签数量增长不转化为用户可感知的能力，在通道打通前继续扩充只会等比例增加孤儿。
- 完成判定：拍摄元数据、地点选择与创作者勾选三条通道均能把标签写入用户发布的内容。taxonomy 全部节点的采集通道与消费方式声明齐备，且不存在新增的仅管线派生取值。境外最小目的地集合校验通过，标签在召回、排序、交集与搜索中的真实分布可从发布物回读。

<a id="open-003"></a>
### OPEN-003 采集通道已在发布物声明，但排序侧读不到，所有标签同权

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前发布物虽已按 REQ-003 为每个节点声明采集通道，但该声明止步于 taxonomy，没有随标签进入在线特征。排序侧对一篇内容的全部标签施加同一个由停留深度与来源渠道推导的权重，因此拍摄元数据测量出的机身与焦段、地点选择解析出的行政区、创作者自行勾选的风格三者在召回与排序中完全等价。自填标签的噪声因此被当作实测证据参与分发，而实测证据也拿不到应有的置信优势。对象标签倒排只存扁平 tagRef 数组，不承载单条赋值的权重与置信度，所以该信息在存储层同样缺位。
- 完成判定：单条标签赋值的采集通道与置信度可从发布物经倒排索引到达排序侧，排序按该置信度区分实测标签与自填标签。置信度只有发布物声明这一个来源，Go 侧不得按 tagRef 路径前缀推测采集通道。倒排索引改造后，反查与子树前缀反查的命中集合与改造前等价，并有真实存储证据。

<a id="open-006"></a>
### OPEN-006 旧执行编排层退役中，删除需以 skill 驱动稳产证据为准入

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前旧编排层（`quwoquan_data/scripts/content/execution/` 的 `agent/`、`queue/`、`controller` 自动推进与 checkpoint 循环、`recovery/` rewind、campaign fleet 调度，约 4~5 万行）已按 [`DEC-005`](./design.md#dec-005) 判定为退役中存量，但尚缺 skill 驱动主线任何一次 M1 全链路 `succeeded` 的真实运行证据（stage receipt 链、immutable release 与环境导入回执均未产生），也缺删除编排层后治理门与测试全绿的证据（import 闭包影响面未验证）。保留原因是 verify/测试仍有 import 依赖且删除需与并发流协调；退役完成前它们不得作为新内容任务的执行入口，新任务一律走阶段契约 + 宿主 agent 主线。
- 完成判定：skill 驱动的 M1 全链路按 [`SIT-001`](#sit-001) 的同源输入与 release/导入证据连续 3 次以上 `succeeded`（恢复语义仍满足 [`SIT-002`](#sit-002) 的 terminal replay 约束）后，删除上述编排代码及其专属测试并原子更新受影响 import（无旧路径 shim）；删除后 `verify script-architecture`、`verify python-symbols`、`verify all` 与仓库 Python 治理门全绿。

<a id="open-005"></a>
### OPEN-005 作废 canonical 内容的受治理 reset 与 exact replay

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仍缺一次 current、digest-bound 的 empty baseline full-sync/readback、原子 `reset-canonical` 与 terminal execution exact replay/adopt 证据；手工删除、旧 receipt 补写或重新执行已闭合上游均会破坏 release 与来源身份。
- 完成判定：`SIT-002.t1/t2/t4` 由 reset 锁、active task、非零 readback、publish/inventory 原子性、旧 receipt 不变、replay evidence/closure 错配、执行中断与部分新 sequence 不得进入 release 的 `local_contract` 直接覆盖；`SIT-002.t3` 由 empty baseline lifecycle、重建 canonical release、importer 与 API readback 的 `api_integration` 覆盖。真实 App 消费继续由 `OPEN-004` 承接，不作为本 OPEN 的模糊第三层证据。
