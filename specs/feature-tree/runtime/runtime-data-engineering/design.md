# L2 Design：运行时数据工程 (`runtime-data-engineering`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入”需要 `article-commercial-scale-closure`、`geo-content-trinity`、`image-commercial-scale-closure`、`video-commercial-scale-closure` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

四个历史 carrier Story 退役其 execution/pool/milestone/release/UAT 业务 ownership，只保留仍具跨域唯一价值的 consumer contract：

- [`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)：文章 canonical closure 到 importer/query 的字段与 failure 语义。
- [`geo-content-trinity`](./geo-content-trinity/spec.md)：四载体共同引用闭包在 runtime consumer 的同 identity 对账。
- [`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)：图片 asset disposition/generator 在 consumer wire 的 fail-closed。
- [`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)：视频 attribution/media package 到 service/App 的无损投影。

execution、reviewed delivery、canonical pool、milestone 与 release build/handoff 业务规格归 [`discovery-content/object-homepage-coverage-scaling`](../../discovery-content/object-homepage-coverage-scaling/spec.md) 的 producer owner；promotion 与 UAT/acceptance 归下游环境 owner。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 runtime-data-engineering 只拥有 immutable release consumer 边界
- 决策：本节点不拥有数据任务 execution、pool、milestone、release build/handoff，也不拥有环境 promotion 或 UAT/acceptance；前者归 discovery producer owner，后者归下游环境 owner。runtime-data-engineering 只拥有 importer/outbox、Search/Recommendation/Homepage 与 App media projection 对公开 immutable release ref/digest 的消费边界。
- 理由：同一 release/UAT 事实存在两个 owner 会产生冲突 gate；runtime 的唯一跨域价值是确保消费者不改写、不猜测且同 identity readback。
- 被否决方案：在四个 carrier Story 重复环境晋级或 acceptance OPEN；由 runtime integration PASS 代替 discovery 的 fresh Gamma/device evidence。
- 失败恢复：上游 ref/digest 缺失或漂移时 consumer fail closed；恢复只在上游 owner 修复后重放 importer/query，不在本域补造 release/UAT。
- 可测试面：api_integration 绑定同一 immutable release 的 importer/outbox/query/readback；静态测试断言本节点无 execution/pool/milestone/release/UAT command owner。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 随体对象包与 pool/release 只作为上游只读事实
- 决策：canonical object package 持有随体最终媒体，content library 仅作采集复用；完整包与 immutable release 消费不依赖原库。包、pool record、library 与 release 均由各自上游 owner 单写，本域只消费 media binding、manifest digest、access mode 与 object refs，不拥有 holder、selection seal、materialization rebuild 或 pool repair command。
- 理由：consumer 取得写权会破坏包与 release 的单写边界；跨域层只需验证 exact binding 并 fail closed。
- 被否决方案：从 runtime cache、旧 release、fixture 或 App 本地字节回填 canonical；从 SourcePool/execution/campaign/provider/model 推导 eligibility。
- 一致性与恢复：binding 不可达或 digest 漂移时 importer/query 整体或逐对象按公开契约阻断，owner bytes 不变；恢复后 exact replay。
- 可测试面：local_contract 锁定 consumer schema 白名单，api_integration 覆盖 binding 漂移与 exact replay。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 Content active pointer 是跨域唯一可见性 fence
- 决策与 owner：active pointer 及 candidate 存储位于已验证 deployment target 的独立权威内，同 environment 的不同 target 不共享可变 pointer。activation 与 rollback operation 仍由下游环境 owner 发起（`REQ-002` 的 environment operation 语义不变）；Content 不选择 release，只在环境 owner 的 operation 内执行 owner-bound expected-current CAS 写 active pointer。immutable release tuple 固定为 `(environment, sourceOwner, releaseId, manifestDigest)`，是 Tag、Creator、Homepage、Content 四域 candidate 的唯一身份；pointer 在该 tuple 之上附带 CAS 成功时产生的单调 `revision`，`revision` 只标识 pointer 世代，不参与 candidate 身份，回滚到 previous release tuple 会产生新的更大 revision 而不复用旧值。上游 discovery owner 只交付 immutable release，Tag/Creator/Homepage 各自只 stage 与 release tuple 绑定的 immutable verified candidate，并返回 exact query receipt；stage、校验或 receipt 创建均不改变旧 live。Content 只在自身 Post/outbox candidate、其余三域 receipt、完整媒体闭包，以及首页/premium/必要详情所需 candidate-scoped Recommendation/Search 查询投影全部 exact ready 后 CAS pointer。查询准备通过 Content owner 的正式 lifecycle 准备边界驱动各域 owner，不直写派生库、不新增第二 active flag；尚无 typed 准备契约或完整 receipt 时阻断激活，而非把 CAS 后异步追平描述为无中断。四域及必要查询以一次读取的 active pointer pin 同一 candidate，CAS 一次暴露完整闭包。激活事件继续承担提交后通知/对账，但不作为首次可读的唯一准备触发。
- 跨服务传输：Content 通过自身 Post canonical contract 声明带最小 service scope 的只读 HTTP operation，将现有 `ActiveReleaseFenceQueryPort` 的完整 found/not-found typed 结果暴露给消费者；operation、wire、错误、超时与 scope 只在 Content contracts authoring。Tag 使用部署配置的 Content endpoint 与本服务签发的 scoped credential，每个非空查询只调用一次该 operation 并 pin 完整 tuple+revision，再 exact 读取并验证自己的 immutable verified candidate；Tag 不直读 Content Mongo、不导入 Content internal、不创建第二 pointer，也不回退 prior/latest。所有共享 active reader 的公共查询、内部查询、反馈校验与 projection health 采用同一组合 reader。空 pointer 是合法未激活状态；已存在 pointer 而 candidate 缺失、身份/闭包漂移、鉴权失败或 transport 超时均按调用方既有 typed storage failure fail closed。
- 传输恢复与观察：读取无副作用，不重试 activation；transport 的单次 deadline 小于调用方查询预算，取消透传，禁止缓存旧 fence 兜底。沿用 operation 级 outcome metric、request/trace identity 与脱敏错误，不记录 credential。修复连接或 candidate 后下一请求重新 pin 当前 revision；rollback 到旧 tuple 仍读取新的 revision，不把 revision 写进 candidate identity。可测试 seam：真实 HTTP service-auth 的未认证/错 scope、空 pointer、错误 tuple、missing/drift candidate；真实 bootstrap 组合加 owner command/provider state 验证 stage A→B 不变 live、Content CAS 后 B 可读、rollback 后新 revision 的 A 可读，并锁定全部共享 reader 一次 pin。服务本地证据不替代 Gamma readback 或 SLO 实测。
- 最小剩余 slice 的源/查询边界：Content `ReadVerifiedImportedPostReleaseCandidate` 与 Entity `QueryReleaseCandidate` 已有 exact verified 源闭包，但前者只返回摘要/计数、后者的 receipt 不等于 Search 文档或 Recommendation 可查询。由 Post/Homepage 各自在既有公开 owner contract 补受信 candidate 公开快照 query（Post 同域可直接 application port），读取候选而非 active/live，交付稳定公开 ID、完整预期身份及规范化快照摘要；保留 entityRef→homepageId 映射，不从标题或 Post 展示字段反推 owner 完整事实。Content lifecycle 只聚合这些 typed 值，不把源 receipt 改标 ready；首次无 active 也能读取和纯准备，纯准备不持有或调用 activation 权限。
- Search 有界扩展：复用现有 `SearchReleasePreparation` 的 command/query、执行 fence、checkpoint 与完成证明，正式扩展为 Creator、Post、Homepage 三种 typed 准备输入及各自证明；不另建通用任务框架或第二流程对象。准备身份只由完整release tuple、对象slice及受管Provider/schema generation确定，不引入协议版本选择。Creator/Post/Homepage共同消费一个typed输入与proof，一套prepare/query、一组checkpoint/receipt存储，删除Creator-only及额外typed-slice双份入口/存储；旧completed不进入当前reader，全部按当前契约重新prepare。源摘要仍是同identity不可变输入，不借变化摘要绕过冲突。源快照由 Content 从各公开 owner 取得后传递，Search 不跨库、不导入其他服务 internal。SearchIndexView 保持 projection `commands:none` 和同域投影 port；Provider 写入、source-version/tombstone、candidate 分区、查询前过滤复用 Creator 机制并按对象种类正式扩展。Data Post 激活后的原 outbox 仅对账同一 candidate，不覆写另一 release 分区；UGC 和普通账户继续原事件、资格和来源分区，不能用 Creator-only 判断让 Post/Homepage 漏过 fence。
- Recommendation 最小准备轨道：不把 `RecommendationCandidateIndexView` 改成 command owner，不把 `RankedRecommendationWindow` session 变成 release 状态机。选择 Content 已有 Post lifecycle owner 的 durable publication：显式纯准备命令在验证 immutable source 后发布契约化的候选准备事实（不是 PostPublished/activation），Recommendation 现役 projector 使用自己的 inbox/checkpoint 消费并在同一 Mongo 提交中保存 candidate 投影与已消费源依据；分块有界且完整预期集合/摘要由源冻结，缺块不 ready。中断按原 durable consumer 重放，Consumer 成功不要求 active，读取证明不推进任务；现有投影 checkpoint 已承担真实 durable 进度，故本 slice 不新增 Recommendation process_manager。Content 到 Search 仍沿现役 prepare command；两者服务不同 Provider 的唯一投影路径，不给同一候选增加可切换同步/异步双轨。Content 原 prepare 重放必须复用同一冻结 publication 身份，不能反复生产新意图来隐藏消费失败。
- Recommendation identity 与精品事实：现有 `(scenario, contentId)` 候选键、premium 的 contentId 唯一键以及 window 未带完整 Data tuple，必须在各自 authoring source 正式区分 Data candidate 与非 Data 来源，并使 Data 候选/附属索引/tombstone/checkpoint 绑定完整 tuple；revision 仅属于请求/window fence。新旧相同 contentId 可并存，不能靠 releaseId 或 manifestDigest 单字段猜 identity。premium 准入仍唯一来自 Product Ops `PremiumPoolEntry` 的真实 approved/eligible/global、有效期及下架事实；在其原 owner 增补 exact 候选源版本/身份绑定，使一份 admission 不能凭同 contentId 误准入另一版本，不由 Content、Search 或 Data 合成准入。Recommendation 只在本地投影中联合 exact Post candidate 与该 admission，沿现役 premium 资格谓词证明 required 的非空 playable `work + video` 集合；普通 video 非空、Post.Featured 或旧 active pool 不能代替。候选源齐备但精品审批缺失是明确 not-ready，不用恒真适配恢复 CAS。
- 共同 ready proof/evaluator：只共享真正跨服务消费的 release binding、源快照及只读证明值语义，wire 唯一落在现役 shared types；证明需 exact 绑定来源 closure/预期对象集合与投影摘要、查询类别、唯一当前契约及实际 Provider/schema generation，premium 另绑定准入事实版本/摘要与有效时间边界。各 owner 从自身真实候选资源和原 checkpoint 只读重验，Search 证明仍属于 Search 准备完成事实，Recommendation 证明是本地投影/准入事实的查询结果，不建立第二 receipt registry 或复制 ready 状态。Recommendation 经已有 `RankedRecommendationWindow` 公开 owner 增加受信、无 session 创建/曝光/反馈的 candidate readiness query，委托同域 candidate named reader 与排序/硬过滤的纯计算端口；真实用户 window 不充当准备任务。Content `RequiredReleaseQueries` 的正式 evaluator 只组合这些 owner 事实与四域/媒体/必要详情证明，并在每个 activation/rollback 入口以目标 tuple 重验；不接收调用方自述 passed，不写远端数据库、不选择 release。复用共同 evaluator 是复用判定代码与 typed 值，不是让多个服务保存一份聚合状态。
- 集合判据的最小裁决：S 是 Content verified candidate 的完整、稳定 canonical Post 身份及源版本/摘要集合；顶层 proof 与候选级 `home` 均证明同 S 全量安全供给实际可查询，不是某个用户 TopN、分页、频控或个性化过滤后的集合。任一源对象缺失、同数量换 ID、版本/摘要漂移或 home 不全都 not-ready；不放宽为摘要非空，不引入合法排除子集/exclusion 协议平台，也不让 Content 复制 Recommendation eligibility 算法。普通用户排序/偏好子集只属于运行查询，不能修改 S。`required_detail` 的 Rec 证据只覆盖同 S 的候选引用/媒体依据，Content 必须用自身 owner reader 完成同 candidate 的真实 hydration/引用/媒体安全核验，Rec 摘要不替代权威详情事实。各查询类别按各自规范化投影核验文档摘要，不因对象集合相同就混用源文档和查询文档摘要。
- 安全失效与精品子集：沿 canonical-search-contract REQ-007，权威删除、privacy/purge、审核拒绝、可见性收紧及账号关闭导致 Post 安全失效时，所有含该对象的 immutable candidate 整体不可 activation/rollback；不删减 S 沿用原 proof。账号关闭清理或安全事实不完整不能由“限制行缺失”推断恢复；suspension 可逆但当前 not-ready，只有 User 明确恢复事实后重新验证，不能放宽普通账户或 Creator 的身份边界。premium P 是 S 中 ProductOps 真实 exact 准入、质量/生命周期合格且可播放的非空子集，允许部分精品退出/到期后其余有效 P 仍满足准入；需依据当前 owner 事实重算完整 P 和 proof，不沿用已失效旧 proof，也不自动把精品资格退出升级为 S 的权威删除。若同时发生 Content 对象级安全撤回则整个候选失效；home 或 P 空均不能通过发布门，普通用户合法空结果不是准入凭据。
- 准入时间判据与 authority：Content lifecycle owner 从现役 operation deadline/取消链确定真正 commit deadline 与所需提交余量，不在读完各域后另起完整预算；每次源/查询耗时都从同一总预算扣减，提交前必须仍有足够余量且 Safety/GenerationProtection 持续有效。消费时核验 `verifiedAt` 格式、时区和相对当前受信时钟的获准误差，超界未来值拒绝；`validUntil` 必须晚于 `verifiedAt`，扣除获准 clock-skew 安全余量后仍严格晚于真正 commit deadline，恰好等于、过期或查询已耗尽预算均 not-ready。proof producer 只可在最后 required 资源观察完成后确定有效窗口，上限受最老仍被复用事实的新鲜度、当前 policy 保证、P 中最早审批 expiry、实际 Provider/schema/GC 保护期限共同约束；不得只把 query 开始时间盖成完成时间来刷新旧事实，不得延长审批 expiresAt、简单增大固定十秒或以顺序查询自然延迟产生的微小裕量过门。两次相等 generation 采样不能证明持续保护，安全撤回不得被保护租约延期；缺可验证 Safety/GenerationProtection 仍阻断。
- 现役时间复用证据与缺口：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml` 已声明 ReadRequiredReleaseQueries 的 8000ms、ActivateContentReleaseAtSearchBarrier 的 10000ms timeout 和 cancellation；Recommendation ranked_recommendation_window/operations.yaml 声明 readiness query 3000ms，Content recommendation_proof.go 的实际调用期限为 2 秒。这些只拥有调用预算，不授予 proof 寿命或时钟可信度。`quwoquan_service/runtime/auth/config.go` 的 `tokenClockSkew=30s` 只属于 access/device token 验证，不能挪用到候选 proof；当前未发现候选准入专属、经 owner 冻结的 clock-skew/时钟健康政策及 commit 余量权威。后续最小补位是 Content Post lifecycle operation/config 与 Recommendation proof operation 共同引用同一获准时间政策，具体数值与 typed 配置必须有权威来源后再 authoring；缺失先以现役 not-ready/OPEN-019 阻断，本设计不发明默认时长。当前 query 仅有 binding/snapshotDigest；下述供给裁决确认需要显式传递真正截止需求和policy identity，后续只能在canonical fields/operation单轨authoring `requiredUntil`/`policyDigest`，本设计不实现隐含字段；它们只表达需求及策略绑定，不授予有效期或扩大原deadline。
- 时间政策单写与供给决定：选择 Content Post release lifecycle 为唯一策略 owner，参数只在 `quwoquan_service/services/content-service/config/schema.yaml` 声明 `sys.content-service.release_query_time.max_proof_lifetime_ms`、`max_clock_uncertainty_ms`、`min_commit_budget_ms`、`max_clock_observation_age_ms`，实际环境值在本服务 `environments/<env>/config.yaml` 明确给出，无隐式默认、无在线独立编辑。前三项分别限制 proof 最大寿命、每个参与宿主相对 UTC 的最大保守误差界及 CAS 所需剩余单调时钟预算；第四项限制宿主时钟观测最大年龄，不把采集间隔隐式当 freshness。它们是工程准入策略，不是时钟健康事实。现役 `platform-ops/config_snapshot` 只读服务配置、`immutable_configuration_composition.py` 的配置 provenance/组合摘要可复用；Platform Ops 不成为第二策略 writer。沿 canonical 配置打包流水线从 Content 已验证包提取这四项，计算只覆盖规范化策略值与 Content owner ref 的 `policyDigest`，在同一封存输入中投影到 Content/Search/Recommendation 各自唯一运行配置的只读 `release_query_time` 消费段；附源 Content config digest 和自身 package provenance。Search/Rec schema 只声明派生消费段与校验义务，其环境 authoring 不另填策略值。运行组合校验三个服务的 policyDigest/来源 config digest 一致，任何 overlay/调用方数字覆盖或来源不完整均 not-ready；不以三个独立人工配置“恰好相等”替代单写来源。字段与共享值最终在各 owner contracts/config authoring，本段只冻结供给责任与语义，不在本设计新增 wire。
- 时钟外部事实与最小 adapter：现役 `quwoquan_ops/cli/commands/health.py`、`diagnostics_shared.py` 可承载具名宿主时钟探针和报告；现有 node-exporter 仅启用 CPU/内存/磁盘等 collector，`--collector.disable-defaults` 下未启用 timex，当前没有 NTP/chrony/内核时钟误差读回实现，不能将 host up 或 Prometheus scrape 成功视为同步。新增范围限定为既有宿主诊断的 `host_clock_health` probe，以及服务 runtime health/本地 adapter 的 typed `ClockHealthReader`：Linux 从运行服务真正所在宿主/VM 的受管 time-sync provider 只读取得同步状态、UTC 保守误差界、同步源身份和失同步/clock-step 依据；首个有界实现选Linux只读timex/adjtimex系统时钟状态adapter，检查未同步状态、maxerror/esterror及boot/单调时钟绑定，且必须以provider conformance证明采用的保守误差界和更新/holdover语义；无法提供该保证时返回unavailable，不自动切另一授时来源。chrony仅在目标已由部署owner明确使用且能给出对应上界证据时作为该target替代adapter，不形成请求级双读fallback。不能只把NTP enable=true、估算offset或采样往返时间当上界。容器必须验证映射到同一宿主 boot/clock identity；Mac上的Linux VM不能用Mac宿主结果代填，未支持的宿主返回 unavailable，不为开发期造健康常量。reuse node-exporter只作观测投影；准入消费同一adapter的本次只读事实，不仅依赖延迟/可陈旧的Prometheus历史样本。
- 时钟事实传输与失效：ClockHealthReader返回的 typed 当前事实至少绑定 host/boot/clock identity、所属service instance/target、observationId、UTC采样值、宿主单调采样点、同步状态及当前保守误差界；这些是部署/宿主 owner 的事实，不写入immutable config或业务candidate，不设第二registry。同宿主直接用只读本地adapter；宿主与容器隔离时只允许由现役host诊断agent/受管runtime输出通道提供带身份校验的只读观测，禁止业务容器获取改系统时钟权限。每次proof验证和CAS前重新读取；若只能复用短期观测，则用同boot单调时钟计算age，并按provider可证明的holdover误差增长上界扩张误差，不能仅检查wall-clock时间戳。超max_clock_observation_age、误差超政策、sync unknown/unsynchronized、boot/clock identity变化、时钟跳变或无法证明映射均not-ready。此probe与本地传输adapter尚缺实现，先于启用时间policy验收；不新增通用时间服务、业务HTTP时间查询对象或额外网络授时系统。
- 可执行的预算与证明算法：Content在原请求入口钉住单调deadline和当前ClockHealth，实际总deadline取原operation/context较早者；源与proof调用都消费该预算。进入CAS前要求单调剩余量不小于min_commit_budget_ms，并验证原deadline未到、policyDigest一致、Safety/GenerationProtection仍有效。跨主机只传UTC截止需求，不传不可比较的monotonic tick：在三域准备query的canonical envelope统一声明 `requiredUntil` 和 `policyDigest` 是本方案的最小必要跨域输入；Content从原deadline及自己当前保守误差界派生requiredUntil，不在重试或各次query重新起算。它只是需求，producer不能据此扩大policy或审批寿命。每个producer完成最后一项required资源观察后读取本机时钟事实形成verifiedAt，并保留仍复用事实的最早失效点；validUntil上限取verifiedAt加max_proof_lifetime、所有仍用事实/policy freshness期限、实际持续保护期限及Rec P最早premium expiry中最早者，再按producer误差界保守收紧。与调用者要求无法形成严格覆盖时返回not-ready，绝不改审批expiresAt。Content消费proof时根据双方获准clock uncertainty界检验verifiedAt不在可证未来、validUntil严格晚于verifiedAt且覆盖requiredUntil，再按剩余单调预算校验；proof须绑定policyDigest和producer ClockHealth观察引用，消费者通过现有受信owner结果验证该引用的provider/host/boot/freshness，调用方不能自报误差数字。以保守端点比较统一实现，不在多个检查中重复或漏扣同一误差；时间变更、策略/引用漂移和过期立即拒绝。Safety/持续保护与时钟事实各自必需，TTL/时钟同步不替代安全撤回保护。
- 参数取值与准入选择：现役8秒required-query、10秒activation、Search query预算及Rec3秒operation/2秒调用只能给总预算约束，不能唯一推出clock uncertainty或CAS提交余量。该最小流程只消费本次调用的新proof，不需要长期复用；max_proof_lifetime的上限不得超过所选Content activation总timeout（当前为10000ms），这只是可验证上限，不代表自动填10000ms即成立。min_commit_budget_ms须至少覆盖隔离真实CAS提交路径的具名保守执行预算，且小于入口总预算；每宿主允许误差与观测年龄须由受管time-sync provider的conformance/holdover证据支撑，在扣除跨宿主误差、查询耗时及提交余量后仍有严格正余量。p95/SLO、JWT30秒和现代码10秒都不是该保守界的证明。当前缺CAS保守预算与时钟provider实测，故不能填写任意数值或只扩大TTL；先交付probe/CAS延迟证据，工程owner在上述约束内冻结环境显式值即可，不需用户替工程选拍脑袋阈值。若实测无可行预算，则准确的Human裁决问题是：保持当前activation时限并接受该target not-ready，还是允许调整activation SLO及其operation合同；不得通过默许更大时钟风险/延长精品审批绕过。该选择尚未出现实测冲突，本设计不预设用户接受任何放宽。
- 关联测试与证据：environment-topology-and-packaging GWT-007 直接覆盖完整 S/home、同数量错身份、用户排序子集独立、premium 一条撤销另一条仍有效、对象撤回失效所有候选、账号关闭清理不足、future verifiedAt/恰 deadline/到期/查询超时/双向 clock skew 与 query 零写。采用 owner 命令/真实 relay 与可控时钟分别证明上述结果，不能只比较 hash 存在、只测试拒绝或用以往局部联合 PASS 冒充 Safety/持续保护、CAS/readback 完成；未实现项仍由 OPEN-019 阻断。
- 请求与保留：Search 在查询前一次 pin Content fence；Content Feed 请求一次 pin 并经受信 typed 请求传给 Recommendation，window 创建/续页与 Content cursor 校验同一完整 tuple+revision、主体、策略/模型及部署绑定；不因内部已有 releaseId/digest 就声称 fence 完整。首次无 pointer 的公开 Data 结果为空，但纯准备照常执行，UGC/普通账户资格不变。切换或 rollback 后旧 cursor/window 拒绝续页并要求重新首刷；已 pin 的单请求内候选、hydration、对象详情及媒体只读取同 tuple，不重新选 active 造成混合。保留 old candidate、源引用、Search proof/checkpoint 和媒体直至回滚窗口及活跃读引用结束；rollback 重验旧候选在当前查询契约/Provider 下仍 ready，并以新的 pointer revision 恢复，不能倒退 external version、切第二 alias 或重建旧 active flag。
- 真实 race 与证据边界：bulk acknowledged、Mongo 投影提交、源 counts 相等均不是 Search 可查询证明；必须在实际候选分区完成 refresh 可见性和完整身份/摘要查询，再签 owner proof。schema/mapping 与 read/write alias 所属受管 generation 是证明依赖。沿 Search DEC-002 与工程 DEC-032 的既有部署串行边界，在验证 proof 至 Content CAS 的短窗口禁止该 generation 切换及 candidate GC；所有受支持 activation/rollback 入口都须持有该现役保护，缺保护或 bypass 无法证明时 not-ready，不新增通用跨库锁平台。前后两次 generation 相等不能代替无竞态证据；pointer race 仍由 expected tuple+revision CAS 裁决。premium expiry 需覆盖该有界准入窗口，下架/撤权不能被准备锁阻止，读侧始终按现役安全规则 fail closed，CAS 后依赖变化/不可达用 ambiguous 与 exact readback/显式 rollback，不承诺跨库事务或永远不失效。
- contracts-first 落点与次序：先冻结 Post/Homepage typed source、Search 三 slice input/proof、Recommendation 候选准备事实/identity/premium admission/window fence，再 verify/codegen 后接实现。authoring 位为 `quwoquan_service/contracts/metadata/_shared/types.yaml` 的真正共享值；`services/content-service/contracts/content/post/{object,fields,operations,events,storage,errors}.yaml`；`services/entity-service/contracts/entity_homepage/homepage/{object,fields,operations,errors}.yaml`；`services/search-service/contracts/search/search_release_preparation/{object,fields,operations,storage,errors}.yaml` 与 `services/search-service/contracts/search/search_index_view/{object,fields,storage}.yaml`、`projections/search_index_document.yaml`；`services/recommendation-service/contracts/recommendation/recommendation_candidate_index_view/{object,fields,events,operations,storage,errors}.yaml` 及 `projections/premium_candidate_projection.yaml`；`ranked_recommendation_window/{fields,operations,storage,errors}.yaml`；`services/product-ops-service/contracts/product_ops/premium_pool_entry/{object,fields,events,operations}.yaml` 的源绑定（所有 services 路径均相对 `quwoquan_service/`）。Data Post 来源说明按 canonical-search-contract REQ-003 修正，Creator DEC-003 仍保留为其 slice 的先行决定；不复制 owner 注册或改 metadata schema/compiler。共享 types、跨服务 ContractGraph/security/client 及 App 生成由一个 writer 在各 owner authoring 稳定后串行执行，不与 Creator 联合测试任务并写。
- 单主线切换的可执行边界：先冻结共享ReleaseCandidateBinding、SearchReleaseCandidateSnapshot、ReleaseQueryPreparationBinding和ReleaseQueryReadinessProof；Search只保留PrepareSearchRelease/ReadSearchReleasePreparation及一组state/receipt。随后在同一增量将`runtime/search/creator_release.go`、`runtime/search/release_slice.go`和ES candidate读写合为当前typed主线，替换Search preparation domain/application/persistence/HTTP/bootstrap，删除被替代Creator-only与typed-slice reader/writer/handler，不保留deprecated路由。Content `creator_search_barrier.go`、`creatorsearch/http_client.go`、纯准备及activation API/CLI统一调用新operation；User候选读取、service scope配置、所有CLI/HTTP客户端和原联合测试/CAS/rollback测试同时更新。历史receipt/存储只离线审计，不删除业务数据，也不从旧completed迁入ready；通过当前owner源重新prepare后才允许激活。生成器共享类型保真修复仍必要，Graph/security/OpenAPI/App/client必须在运行替换完成后统一重建；仅authoring冻结时全部实现/索引/运行与迁移门禁保持OPEN，不称单轨代码已完成。
- 最小实施闭合顺序：先 Post/Homepage source + Search 同对象扩展及读侧 fence；再 Content candidate publication + Recommendation candidate/premium 源绑定与无副作用 proof query、window fence；最后装配 Content 正式 evaluator 至 API bootstrap、release-control CLI 和 rollback 的共同 activation 边界。阶段性 pure prepare 可以独立可用，但只有全部 required 证明真实齐备才能恢复 CAS。恢复 `cmd/api/active_release_fence__local_contract_test.go` 的 `TestActiveReleaseFenceBootstrapTransport` 和 `tests/api_integration/content/post/import/release_activation_cas__data_consistency__api_integration_test.go` 原有 stage/CAS、materialize failure rollback、并发唯一 winner、control replay/conflict 正向断言：通过真实 owner command/import 与 Provider state 准备四域、Search、Recommendation、premium 和媒体，然后从正式 bootstrap 装配触发 CAS；仅 typed port 单测可用替身隔离，不将替身结果提升为真实屏障证据。不删 barrier、不把正向改成 only-not-ready，也不直写 proof 文档或 CAS 后 live query 伪装 pre-CAS 证明。
- 测试 seam 与未完成：直接绑定 environment-topology-and-packaging GWT-007 的新增源/查询分离、首次 activation、A→B→A、UGC/账户隔离、cursor/session 和 race 子句；local_contract 覆盖 typed identity、source/proof 区分、缺项/漂移拒绝及零 projection command，真实 Mongo/ES/Redis api_integration 覆盖 refresh、mapping/alias generation 切换、Provider 写成功/checkpoint 丢失、中断重放、proof→CAS 竞争与过期 premium。沿既有 operation deadline/取消与脱敏 request/trace/outcome 指标，分别观测准备 lag、proof mismatch、generation skew、CAS conflict、窗口 fence 拒绝；CAS 后 60 秒 readback、显式 rollback 后 5 分钟恢复必须实测，未测不声称达成。以上为剩余 slice 的当前设计，不是现役实现/测试 PASS；缺失 contracts、premium 候选事实、受管代际保护或 required runtime 证据继续由 environment-topology-and-packaging OPEN-019 阻断。
- 理由：分域切换会混版本，CAS 后才准备推荐/精选又产生 fail-closed 空窗；将完整媒体、四域和必要查询预物化纳入同一准入屏障，在保留各 owner 单写与环境发起/Content CAS 分工的同时，让一次 pointer 切换暴露完整可读闭包。
- 被否决方案：Tag/Creator/Homepage 或推荐/精选各自 activation；stage 覆盖 live；CAS 后异步追平冒充无中断；直写索引/精选 seed；按 counts/latest/LKG 猜 active；revision 纳入 candidate 身份；Content 自选 release；下游 readback 回写 producer handoff；读取失败在线 fallback 到旧版本。
- 失败恢复与回滚：CAS 前任一 stage/校验/receipt 失败或 CAS conflict 均保持 previous pointer 与旧 live，candidate 可保留供诊断但不可见。Content CAS 已返回后，任一 fenced readback 超时、不可达或身份不一致都返回 typed `ambiguous`，不得自动重试 CAS、猜测成功或选择某域结果；环境 owner 必须先 query exact pointer（含当前 revision），再发起显式 rollback operation，由 Content 以 asserted current tuple+revision 作 expected-current CAS 回 previous fully verified release tuple 并生成新 revision，随后重做四域 fenced readback。rollback 冲突或 readback 失败继续 fail closed，不改 canonical、pool、content-library 或 producer bytes。
- 读会话与资源：页面、详情、分页及媒体会话固定同一内容版本；版本切换使旧 cursor 明确失效并重取第一页，不混旧 cursor/新对象/旧媒体。新旧不可变数据和媒体保留到活跃读引用与回滚窗口结束再 GC，不覆盖在播文件。
- 首次激活恢复：没有 previous 的准备失败保留无 active 状态；CAS 结果未知先 query exact pointer，不猜空或旧 release。确认新 pointer 已激活但 readback 失败时保持 ambiguous/阻断；仅在 canonical operation 支持并经授权时显式 CAS 到已验证 empty baseline，否则等待 owner 恢复，不伪造回滚成功。
- SLI/SLO 与告警：记录媒体闭包、四域及必要查询 ready、CAS conflict、fenced identity、ambiguous 与 rollback outcome；CAS 后 60 秒必须取得四域及 required 查询/媒体 exact fenced readback，否则告警并阻断；显式 rollback 后 5 分钟恢复 previous 完整闭包，否则持续阻断。这是目标，未测不称达成。
- 可测试 seam：Data 侧四域 receipt 的 exact-bytes evaluator 为 `quwoquan_data/scripts/content/release/environment/owner_local_staging_admission.py`，只消费显式 receipt ref+digest，不扫描 latest、不接受 import report 代替 candidate proof；local_contract 注入 stale/missing receipt、CAS race 与 readback timeout，证明 candidate immutable、stage 零 live mutation、CAS 只接受 release tuple 与 asserted revision 且 post-CAS failure 不会自动猜测或重试；api_integration 覆盖 previous→candidate→previous，断言 CAS 前旧 live 持续可读、CAS 后四域只见同 tuple、rollback 后 revision 单调递增，ambiguous 经显式 rollback 收敛且 owner bytes 不变。
- 关联要求：`REQ-002`、`REQ-004`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-001`、`SIT-002`，并由 [`environment-topology-and-packaging GWT-007`](../runtime-config/environment-topology-and-packaging/spec.md#gwt-007) 验证 candidate 查询屏障、缺媒体/精选、CAS race、首次无 previous 与恢复时限；未设计完成的 typed 准备面及未测闭环登记该 Story OPEN-019，不以现有异步实现宣称通过。

<a id="dec-004"></a>
### DEC-004 image generator 由 Post manifest schema 单轨拥有
- 决策：Post manifest materializer 是 `generator` 的唯一写 owner，并只写 schema 已声明的 `agent`。image evidence pack 继续作为 execution/source/review 的内部 evidence，不成为第二个 generator 值；pool validator 与 release selector 只读通过 canonical schema 的 manifest。
- 理由：`generator` 表达交付 copy 的 authoring 身份，而 evidence pack 表达素材与审核证据。把两者塞进同一 wire 字段会让 schema、materializer 与 release reader 对对象身份产生分叉。
- 被否决方案：schema 增加 `image_evidence_pack`、reader 双读、warn-only 放行、按 carrier 推导默认值，或原地修补旧 manifest/receipt。
- 失败恢复：非 canonical generator 使单对象 typed excluded，不阻断同池其它对象；仅允许基于原 terminal evidence 的 replay/adopt 创建新 manifest，不重跑已闭合上游。
- 可测试观察面：Post manifest schema validation、image materialize 输出、provenance/pool record 与 release selection；对象级 local_contract 证明所有交付 manifest 为 `agent` 且不存在 compatibility fallback。
- 关联要求：[`image-commercial-scale-closure/REQ-004`](./image-commercial-scale-closure/spec.md#req-004)
- 影响 Story：[`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)
- 关联验收：[`image-commercial-scale-closure/GWT-004`](./image-commercial-scale-closure/spec.md#gwt-004)

<a id="dec-005"></a>
### DEC-005 宿主 execution 只作为 discovery owner 的只读上游
- 决策：宿主 AI producer 九阶段、OPEN/CLOSE receipts、逐对象 publish 与显式 cohort release handoff 归 discovery producer owner；ship/environment facts 归下游环境 owner。本节点不定义 Skill、stage control、recovery 或执行状态投影，只允许 consumer diagnosis 通过公开 release/handoff/环境 operation ref 追溯。
- 理由：执行推进方式不是 runtime consumer 的业务事实；在本域再拥有一套会与 discovery 单轨分叉。
- 被否决方案：仓内 managed SDK/controller/campaign/runner/fleet/claim、stage-gate/semantic wrapper/reducer、runtime view 回写 execution，或由 importer/UAT 写业务 verdict。
- 失败恢复：execution 问题返回上游 typed ref；本域只能重跑自己的 importer/query，不创建 `retryOf` 内容 execution。
- 可测试面：静态 owner test 与 projection-only local_contract。
- 关联要求：`REQ-005`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-003`

<a id="dec-006"></a>
### DEC-006 runtime 运营对象仅投影 consumer facts
- 决策：本域 View 只投影 importer/outbox/query/active pointer 与公开上游 release refs；无 command、Repository、checkpoint、独立 lifecycle 或 owner-fact 修复能力。
- 理由：跨 owner 查询可重建，持久 checkpoint 会成为第二状态台账。
- 被否决方案：View 写下一环境、acceptance、release selection 或 execution terminal。
- 恢复：缺 fact/digest drift 返回 typed incomplete/conflict，修 source fact 后重建。
- 可测试面：删除重建 exact 相同且 owner bytes 不变。
- 关联要求：`REQ-005`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-003`

<a id="dec-007"></a>
### DEC-007 UAT runner 只消费 runtime readback，不拥有 acceptance
- 决策：sample plan、target binding、raw `ReadinessCaseResult` 与 `EnvironmentAcceptanceFact` 的 authority 继续由 discovery/metadata/Ops owner；runtime 只提供被 required runner 调用的 release-bound readback。
- 理由：readback producer 与 UAT result/acceptance writer 是不同 owner；本域 PASS 不能代替 registered physical device raw facts 或 Gamma acceptance。
- 被否决方案：把 verdict 写进 Data readiness、由 bundle/counts 推导 acceptance、从 runtime integration 触发上游内容生产。
- 失败恢复：readback 缺失或漂移只返回 typed blocker，不写 raw result/acceptance；由外层 runner 保留真实结果。
- 可测试面：local_contract 锁定 port 只读，api_integration 提供同 release/candidate readback。
- 关联要求：`REQ-006`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-004`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本/bytes 冲突、锁冲突、环境 baseline 未收敛、inventory/holder 漂移、target 前置缺失、required raw result 缺失或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写 ship succeeded 或追加伪 `EnvironmentAcceptanceFact`。
- execution 恢复：写前失败保持 canonical 不变，terminal 只以新 `executionId + retryOf` 恢复。reset 后只按 terminal evidence replay/adopt。
- 环境恢复：追加新的 operation/readback/Exit/raw result facts 并重新求值，不改旧 execution/acceptance。
- materialization 恢复：由原 owner 显式从完整随体包重建；包损坏时须从独立保护副本逐摘要验证恢复，不依赖原 content library，不由 consumer 隐式修复。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写、compatibility shim、View Repository/checkpoint 或页面本地写副本。

## 6. 质量与观测

- 成本影响保持同量级：reset 只处理 canonical publish/inventory 元数据，replay 成本与被选 terminal execution 数量线性相关；release materialization 从随体包重建，content library 只作采集复用，既有独立 golden media 保护副本保留，不由 consumer 新建长期 holder。
- reset 写阶段在取得锁后 60 秒内完成或 fail closed；环境从 empty baseline 恢复原 release 的目标为 5 分钟内完成。超时只产生失败 receipt，不放宽锁、holder protection 或 closure。
- SLI 直接读取 create-once reset/producer-stage receipt 与下游 ship receipt、empty/replay lifecycle、canonical identity state query、raw readiness result、target binding 与 acceptance fact 的完成状态和耗时；View 与 bundle 只做查询，不新增第二份状态台账。
- 内容生产启动不由 Runtime 决定；本域在正式 candidate 准备边界预物化 required 查询闭包，active pointer 改变后按 same digest 对账，不重新选择内容。既有消费缺口保留在本能力 OPEN-004/005/008；无中断准入的新设计与实证缺口由环境 Story OPEN-019 承接。
