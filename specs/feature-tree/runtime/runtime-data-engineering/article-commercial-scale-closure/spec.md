# L3 Story：文章商用规模闭环 (`article-commercial-scale-closure`)

> 所属能力：[`runtime-data-engineering`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望通用文章 provider onboarding、单 execution 生产与基于真实回执的发布容量验收，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- provider policy 与文本、插图的 source/rights 闭包
- Agent authoring、独立 review、canonical promotion 与 immutable release
- request 驱动规模下的 import/API/consumer/rollback/replay 证据

### Out of Scope

- 静态区域、目标对象、数量或阶段清单
- 未经真实 receipt 支撑的生产容量结论

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 provider onboarding is reusable and source-role complete

- 缺来源或权利的对象保持 typed GATE_BLOCK，不能进入 canonical publish。

<a id="req-002"></a>
### REQ-002 each approved article closes one execution and release lifecycle

- 任何已进入 qualified/finalized 闭包的文章缺对象、来源、rights 或环境 receipt 均阻断该对象与 release；未达 quota 的 shortfall 和带 typed issues 的 discard 不阻止其余合格文章发布。
- `payload/release.json`、`payload/desired_state.json`、environment `run/result`、`applied_ref`、`rollback_ref` 与各 importer/API readback report 分别由对应 JSON Schema 唯一约束；`release_manifest` 不承担 canonical release 或环境激活真相源。
- empty baseline 是 release-bound、零 execution、零对象/creator/tag 的 immutable snapshot；Tag taxonomy 允许激活该零节点 snapshot，并允许 retired snapshot rollback/replay，历史 snapshot 不物理删除。
- Alpha/Beta/Gamma 必须分别以真实 importer receipt、`applied_ref` 和 post/homepage（或 baseline）API report 证明激活；Prod `prepared` / `dry-run` 只能证明准备或演练，不得生成或冒充激活证据。
- entity 的 `creatorProfileId` 必须进入 creator object closure；avatar 仅在 creator profile 绑定可校验 CAS bytes、摘要与 schema-bound commercial rights snapshot 时投影，禁止合成 URL。rights 必须明确 `depictsIdentifiablePerson`：可识别人物只能使用 `modelReleaseStatus=obtained`，非人物资产才可在权利审计通过时使用 `not_required`。

<a id="req-003"></a>
### REQ-003 capacity conclusions use only measured execution receipts

- M100/M1000 的 article workload target 分别为 100/1000；quota/count 只表达请求负载与里程碑目标，不是发布门。
- receipt 分别记录 target、selected、qualified、finalized、discarded、shortfall，以及 object pass、illustrated、first-pass、discard 与 quota attainment 的分子、分母和 rate；任何目标缺口或比率值都不阻断已闭合对象。
- active article workloads 按可用容量独立调度；固定并发、固定 worker、workspace smoke、capacity soak 与 resource samples 不作为 dispatch/promotion 前置。每个实际启动的 task 逐项记录 typed 终态，诊断 sample 不得冒充 task 结果。
- 容量评估可重算且不被当作生产完成；对象级 review、source/rights/provenance、同源图片闭包、去重与 canonical 引用仍是硬门。

<a id="req-004"></a>
### REQ-004 开放式旅行/摄影文章来源站点统一 onboarding 合同与 shared commercial pool

- 开放式旅行/摄影文章来源站点统一 onboarding 合同与 shared commercial pool
- article 必须从 campaign 冻结的 canonical entity catalog 独立选择 target；不得依赖 homepage execution 或已发布主页批次。
- 搜索补全供给使用独立 execution，不能和主线共享冻结目标、状态或准出口径。
- article source discovery 只允许进入 registry 已声明可抓取、允许 crawl、包含 article lane 且具备 commercial release admission 的站点；robots/terms、allowed path、速率/退避、深度/日页数、canonical 去重与实体/别名/主题相关性均须形成不可变审计证据。
- 登录墙、robots deny、网络不可达与不相关候选必须形成 typed blocked/discard；`factual_reference_only` 只保留事实引用身份，不得保存原文或伪造成功。
- content plan 只消费 target set 冻结的 canonical target 与 aliases 作为实体锚定；只偶然列举目标的城市总览或 figure caption 不能因行长、推断短别名或标题回填成为目标文章底稿。
- `factual_reference_only` 只可提取可核验事实、路线顺序、必要数字与专有名词；成稿必须使用独立句式、结构和叙事，不得保留来源连续长句、自然段、小标题或原文结构，也不得以 licensed adaptation 的底稿留存率为其设下限。
- independent review 已有 finished Grok journal，但 controller 中断后只剩唯一 schema-valid pending response 时，不得改写旧 execution 的 `reviewer_result`/attestation。
- 只有唯一 pending response 与唯一未绑定 finished reviewer work unit 能生成 create-once reconciliation receipt。
- 标准 campaign submission 必须从该 receipt 与其余 final review 自动派生 failed-only refs。
- plan 冻结该 scope，lane argv 透传该 scope，并在新 sequence 以 `retryOf` 消费 typed issues。
- 已通过对象不得重试。

## 4. 契约引用

- canonical：`quwoquan_data/verticals/<vertical>/providers.yaml`
- canonical：`quwoquan_data/verticals/<vertical>/content_policy.yaml`
- canonical：`quwoquan_data/scripts/content/source`
- canonical：`quwoquan_data/scripts/content/execution`
- canonical：`quwoquan_data/scripts/content/release`
- canonical：`quwoquan_data/scripts/governance/coverage/benchmark.py`
- interrupted review reconciliation：`quwoquan_data/schema/execution/campaign_review_interruption_reconciliation_receipt.schema.json`
- failed-only retry feedback：`quwoquan_data/schema/execution/retry_review_feedback.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 provider onboarding is reusable and source-role complete

- GIVEN 垂类 provider policy、content policy 与 family 已由仓内真相源声明。
- WHEN 任一文章 execution 以 request 选择 provider 和主题。
- THEN provider admission、文本事实来源和插图 rights/provenance 使用同一合同。
- THEN content plan 优先并准入严格锚定 canonical target/alias 的直接来源，排除只偶然列举目标的宽泛页面；`factual_reference_only` author prompt 只允许事实提取与独立表达。
- THEN review 中断证据不改写旧 execution；create-once receipt 、submission、plan 与 lane 只向新 `retryOf` 透传 exact failed refs 和 typed feedback，通过对象不进入新序列。
- THEN 静态 policy 不包含实体 URL、区域、数量或运行结论。
- THEN 真实 source discovery 主线可回读 provider policy、frontier 决策、canonical URL 与 typed blocked/discard evidence。

<a id="gwt-002"></a>
### GWT-002 each approved article closes one execution and release lifecycle

- GIVEN request 已冻结 target set、provider 选择、模型与 source digest。
- WHEN article 完成 source、compose、draft、review、canonical promotion 和 release aggregate。
- THEN 文章、canonical entity identity、creator、资产、tag 和 source digest 可闭包追溯；关联主页不是文章 execution 的前置条件。
- THEN 每个 qualified 对象均 finalize 并发布；quota shortfall 或带 typed issues 的 discard 只进入 receipt，不删除或阻断其它合格文章。
- THEN Beta/Gamma integration 证明 full-sync、API、幂等、rollback 与 replay。
- THEN rollback receipt 明确绑定 `rollbackFromReleaseId`；empty baseline 由 baseline API readback 证明隔离下线，历史内容由后续 replay 的 importer/API readback 证明恢复。
- THEN 生命周期 gate 不读取测试专用 activation smoke，也不把 Prod prepared/dry-run 报告计为 activated。

<a id="gwt-003"></a>
### GWT-003 capacity conclusions use only measured execution receipts

- GIVEN 至少一个完成闭包的文章 execution 已产生不可变 receipt。
- WHEN 运营评估后续规模与预算。
- THEN 吞吐、成本、object pass、illustrated、first-pass、discard、quota attainment、queue lag 与 source capacity 都来自 receipt，并为每个 rate 标明分子与分母。
- THEN 未命中 workload target 或统计 rate 只形成 shortfall/趋势结论，不否决至少一个 hard-qualified 对象的发布与结构性 promotion。
- THEN active workloads 可串行或重叠执行；每个实际 task 分别终态，soak/workspace/resource samples 的缺失或失败只影响容量结论，不影响 dispatch。canonical publish 保持对象事务单写者，最终 release 仍要求 exact closure。
- THEN 缺失对象级硬门或 receipt 身份证据时结论为 GATE_BLOCK，不能写入静态 policy 或 acceptance 数字。

## 6. 依赖

- 前置要求：[`runtime-data-engineering`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 provider onboarding is reusable and source-role complete

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺真实 M100 article workload execution 对 source/rights closure 与 target/qualified/shortfall 统计的完整 receipt；frontier 的本地合同与单站 probe 不能替代规模证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 each approved article closes one execution and release lifecycle

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现与验收证据，包括 article 对 canonical entity identity 的独立闭包、Alpha/Beta/Gamma 真实激活、baseline rollback 和历史 replay 环境 receipts；当前 immutable pilot-001 不得原地补写 creator closure。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 capacity conclusions use only measured execution receipts

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚无真实 M100 execution receipt；容量评估不得依据 frontier probe、fixture 或估算结论关闭，也不得把 target/rate 未命中提升为对象发布门。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
