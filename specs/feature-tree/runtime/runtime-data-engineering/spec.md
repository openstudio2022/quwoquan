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
- tag/entity/post/media 的跨域消费 projection、importer/outbox 与 App/Service wire 一致性。
- 只读消费 discovery owner 交付的 immutable release、canonical identity、content-library binding 与环境 operation facts；不拥有 execution、pool、milestone、release build/promotion 或 UAT/acceptance。
- `content_library` sole-holder 与 raw UAT authority 作为上游不变量被本域消费者验证，不在本节点复制 owner、生命周期或完成结论。

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

- tagRef、canonicalEntityId、entityRef、内容语义 relationEdge、creator/avatar 与 post media 均来自 discovery owner 的 canonical object/release projection；本域只验证并导入，不创建这些业务事实。
- 作者池准入只保存 `processResult`、`qualityResult`、版本、证据引用与状态；只有 `completed + passed + active` 可进入新 release。头像只做格式、可读取、清晰度、安全和内容质量检查，不保存 Research/Commercial 范围，不参与作者或内容的 Prod 准入，也不产生内容 commercial variant。
- 内容池准入只保存 `processResult`、`qualityResult`、`usageScope=research|commercial`、版本、证据引用与状态；未知或缺商用证明一律是 `research`，`commercial` 必须由 receipt 中公开可审计的商用发布权证明支持。
- `contentId`/`authorId` 是稳定身份，有效变化只追加递增版本；同一追加键相同 digest 可幂等重放，不同 digest 返回 typed conflict，禁止覆盖旧版本。
- discovery owner 声明的 `content_library` 是 canonical media bytes sole-holder。本域 importer/service/App 只能消费 identity/digest/ref 或目标环境 materialization，不得取得 holder、recovery 或 release rebuild 写权；binding 不可达或摘要漂移时 fail closed。
- alpha/beta/gamma/prod 的 importer/query 只消费 immutable release identity；本域不得自建 release、重采样 cohort、推导 milestone、写 acceptance，且无 environment fixture/self-seed 旁路。Manifest 只决定召回资格，不直接提供首页列表或搜索结果。
- 对象主页网络可引用同一数据工程输入构建交集、推荐和小艺上下文。

<a id="req-002"></a>
### REQ-002 标签、对象与 release consumer contract 单轨

- 标签 authoring 真相源仍为数据工程 `control_plane/governance/taxonomy`；`publish/tags` 只保存上游 canonical 对象实际引用的 consumer snapshot。本域 importer 不恢复扁平枚举、不复制整棵 taxonomy。
- 实体归一产物必须映射到 runtime `canonicalEntityId`；Post/Creator/Entity/Tag/Media 引用以同一 immutable release identity 和 manifest digest 原子导入，缺引用或 digest 漂移整次 fail closed。
- pool selection、Research/Commercial、M100/M1000 profile、release build/promotion、`ReleaseUatSamplePlan`、`TargetUatBinding`、raw `ReadinessCaseResult` 与 `EnvironmentAcceptanceFact` 的业务 owner 均为 [`discovery-content/object-homepage-coverage-scaling/multi-carrier-release`](../../discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md) 及其声明 owner；本节点只读验证公开 ref/digest，不复制命令、枚举、状态或 OPEN。
- content importer 必须原子写 Post 与 durable outbox，并在 receipt 中绑定 `sourceOwner=qwq_data`、上游 immutable payload digest 与 exact object/author/media readback。Recommendation/Search 只消费 Content 所有的 lifecycle；禁止 Mongo 直写、Redis-only 推送或 seed 搜索/推荐表。
- consumer rollback/replay 只跟随上游 environment operation/active pointer，并以同 manifest digest 完成 importer/API/media readback；本节点不创建 release lifecycle 或 acceptance 事实。
- 逐对象 attribution、rights 与 media access mode 只从 canonical projection 读取，服务与 App 不维护第二套字段，不得从 provider、SourcePool、execution/campaign/model 或路径字面推断。


<a id="req-003"></a>
### REQ-003 标签发布物必须自带采集通道与在线消费方式声明

- taxonomy 每个节点必须声明采集通道与消费方式；采集通道取值限于拍摄元数据、地点选择、创作者勾选、点评勾选、行为事件与仅管线派生。
- 取值为仅管线派生的存量节点进入基线清单并只减不增，新增节点不得使用该取值。
- 消费方式必须至少包含召回过滤、排序因子、交集判定与搜索筛选之一，缺失声明的节点不得进入 canonical publish。
- 同一现实概念跨轴出现时由节点自身声明同义引用，跨轴权重传播只读取该声明，不按路径前缀推测轴间关系。
- 境外行政区必须覆盖声明的最小目的地集合，覆盖不足时视为发布物不完整并阻断发布。

<a id="req-004"></a>
### REQ-004 consumer 下线、rollback 与 sole-holder 边界

- 对象从 active immutable release 退出后，runtime consumer 只按上游 active pointer/full-sync 结果删除自身 projection；不得直接删除 canonical object、pool record、release 或 content-library bytes。
- rollback/replay 必须原子恢复 Post/outbox/Search/Recommendation/media projection 到同一 previous release identity；任一 surface 混合新旧 identity 或仅 counts 相等都 fail closed。
- materialization 不可达时本域只返回 typed blocker；恢复由上游 content library/release owner完成，本域不得从缓存、旧 release、fixture 或 App 本地字节反向补 canonical。

<a id="req-005"></a>
### REQ-005 宿主 execution 与运营视图只作为上游只读事实

- 宿主 AI 十阶段、OPEN/CLOSE receipts、逐对象 publish、显式 cohort release 与 ship facts 全部归 discovery owner；runtime-data-engineering 不拥有执行命令、状态机、recovery、milestone 或完成结论。
- 本域的消费状态查询只能读取 immutable release、importer/outbox 与 active pointer facts；不得从 execution/campaign/provider/model 推导消费资格，也不得回写上游 terminal。
- 任何跨域运营 projection 均无 command、Repository、checkpoint 或独立 lifecycle，删除后可从公开 owner facts exact rebuild。

<a id="req-006"></a>
### REQ-006 UAT 与 environment acceptance 只读边界

- Data-owned sample plan、Ops target binding、metadata raw `ReadinessCaseResult` 与 Ops `EnvironmentAcceptanceFact` 的分层 authority 保持不变，但业务规格与完成证据只在 discovery owner 声明。
- runtime importer/query 可为 required case 提供真实 readback，并以公开 ref/digest 供 runner 消费；不得生成 raw UAT verdict、acceptance、promotion、predecessor 或 M1000 start gate。
- 任一上游 UAT/acceptance 缺失、失败或 digest 漂移只形成 typed read blocker，不得以本域 integration PASS、bundle、counts 或缓存代填。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。
- owner 边界：discovery `multi-carrier-release` 拥有 execution/pool/milestone/release 与其 UAT 业务闭环；content library、metadata raw result、Ops target/acceptance 仍由各自 canonical owner 单写。本节点只拥有 importer/outbox/query/App wire 的跨域消费边界。
- fresh 环境/物理设备 evidence 由 discovery OPEN 跟踪；本节点不得复制证据 OPEN 或据本域测试关闭上游缺口。
- 证据执行隔离：验证执行产生的临时字节只进入 tempfile 临时根，不得写入仓库根或 `QWQ_OUTPUT_ROOT`；runner 与落盘隔离门属于 evidence contract。
- 验收证据层：`SIT-001` 的对象、pool、holder、promotion 与 receipt 约束由 `local_contract` 承接，真实 import/readback/Search/Recommendation/lifecycle 由 `api_integration` 承接，App 消费结果由 `user_acceptance` raw `ReadinessCaseResult` 承接。
- 验收证据层：`SIT-003` 的 OPEN/CLOSE create-once 与 projection query 由 `local_contract` 承接，真实 ship 与 owner receipt ref/digest 串联由 `api_integration` 承接。
- 验收证据层：`SIT-004` 的 wire schema、append-only 与 fail-closed evaluator 由 `local_contract` 承接，真实 activation/readback/package/device 与 predecessor 串联由 `api_integration` 承接，真实 App consumer case 由 `user_acceptance` 承接。
- 「可发布」判定单轨：在数据工程内，环境 readiness 收据是否可发布只由 `quwoquan_data/scripts/verify/release_publishability.py` 的 typed 谓词裁定，CLI 入口为 `verify release-publishability`；phase 闭集与 phase↔lifecycle 对齐规则不得在数据工程脚本中重复定义。对象池准入、素材可发布与 execution 准出是各自独立的谓词，不共用该措辞。跨仓消费方（如 `quwoquan_ops/ci/generate_release_bound_environment_identity.py` 的 release-bound 身份校验）以 wire schema `environment_release_readiness.schema.json` 为锚做收据身份验证，属已登记消费，不构成第二份可发布谓词。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 canonical release 跨域消费保持同 identity

- GIVEN discovery owner 已交付一个 immutable release、manifest digest 与 content-library bindings。
- WHEN runtime importer、Content outbox、Search、Recommendation、Homepage 与 App media projection 消费它。
- THEN tag/entity/creator/post/media exact closure，Post 与 durable outbox 原子提交，各 consumer readback 同一 release identity；不创建 pool/milestone/UAT/acceptance 事实。
- THEN content-library binding 不可达或任何 digest/ref 漂移时 fail closed，不从缓存、旧 release、fixture、SourcePool、execution/campaign/provider/model 补值。
- THEN Research/Commercial、milestone cohort 与 UAT sample 只从上游 immutable release facts读取，本域不重采样或晋级。
- THEN consumer rollback/replay 全部回到同一 previous release identity。
- THEN raw UAT 与 acceptance 只由 canonical owner 写，本域 integration PASS 不代填。
- THEN runtime query 不暴露 SourcePool、execution/campaign/provider/model 生产身份。

<a id="sit-002"></a>
### SIT-002 consumer rollback/replay 保持 exact release identity

- GIVEN 上游 environment owner 已将 active pointer rollback 到 previous immutable release。
- WHEN runtime consumer full-sync 并 readback。
- THEN Post/outbox/Search/Recommendation/Homepage/media projection 全部恢复同一 previous identity；任一混合 identity、悬挂引用或 counts-only 相等均 typed blocked，canonical/pool/library bytes 不被本域修改。


<a id="sit-003"></a>
### SIT-003 跨域 query projection 不反向拥有业务状态

- GIVEN 上游 execution/release/environment facts 与本域 importer/readback facts均可查询。
- WHEN 重建 runtime consumption view。
- THEN view 只读公开 refs/digests，无 command、Repository、checkpoint、execution terminal、release promotion 或 acceptance writer；删除后重建 exact 相同。


<a id="sit-004"></a>
### SIT-004 UAT runner 只消费 runtime readback

- GIVEN discovery/Ops 已创建 sample plan 与 target binding。
- WHEN required runner 调用 runtime/App consumer 并写 raw `ReadinessCaseResult`。
- THEN runtime 只提供绑定同 release/candidate 的真实 readback，不生成或修改 raw result、acceptance、predecessor、promotion 或 M1000 start gate；缺失事实 fail closed。


## 8. 开放事项

<a id="open-004"></a>
### OPEN-004 release consumer 的同 identity 真实 readback 尚缺

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺同一 current immutable release 在 Content importer/outbox、Search、Recommendation、Homepage 与 App media projection 的 exact identity/readback；这不表示本节点拥有 M100/M1000、release build/promotion 或 UAT acceptance。
- 完成判定：`SIT-001` 由真实 importer/storage/query api_integration 直接绑定，同 release identity 的对象、数量与 media binding 全部一致，负例证明 SourcePool/execution/campaign/provider/model 与 fixture 均不能代填。


<a id="open-002"></a>
### OPEN-002 标签发布物在创作侧没有采集通道，绝大多数标签处于孤儿状态

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺实现：绝大多数标签没有用户侧写入通道，内容标签只能由数据侧 release import 产生，创作者发布的内容不携带标签。地理轴节点数量最多，但在地点选择结果被解析为标签引用之前同样不产生真实分布。由此召回过滤、排序因子、交集判定与搜索筛选都只能作用于数据侧内容，标签数量增长不转化为用户可感知的能力，在通道打通前继续扩充只会等比例增加孤儿。
- 完成判定：拍摄元数据、地点选择与创作者勾选三条通道均能把标签写入用户发布的内容。taxonomy 全部节点的采集通道与消费方式声明齐备，且不存在新增的仅管线派生取值。境外最小目的地集合校验通过，标签在召回、排序、交集与搜索中的真实分布可从发布物回读。

<a id="open-003"></a>
### OPEN-003 采集通道已在发布物声明，但排序侧读不到，所有标签同权

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现：发布物的采集通道声明止步于 taxonomy，没有随标签进入在线特征。排序侧对一篇内容的全部标签施加同一个由停留深度与来源渠道推导的权重，因此拍摄元数据测量出的机身与焦段、地点选择解析出的行政区、创作者自行勾选的风格三者在召回与排序中完全等价。自填标签的噪声因此被当作实测证据参与分发，而实测证据也拿不到应有的置信优势。对象标签倒排只存扁平 tagRef 数组，不承载单条赋值的权重与置信度，所以该信息在存储层同样缺位。
- 完成判定：单条标签赋值的采集通道与置信度可从发布物经倒排索引到达排序侧，排序按该置信度区分实测标签与自填标签。置信度只有发布物声明这一个来源，Go 侧不得按 tagRef 路径前缀推测采集通道。倒排索引改造后，反查与子树前缀反查的命中集合与改造前等价，并有真实存储证据。

<a id="open-008"></a>
### OPEN-008 runtime consumption projection 尚缺实现闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：本域只保留的唯一未闭合能力是 importer/outbox/query/App wire 的 projection-only 硬切；仍需证明无 command/Repository/checkpoint、无 SourcePool/execution/campaign/provider/model 字段，且 content-library binding 漂移 fail closed。
- 完成判定：`SIT-003` 与 `SIT-004` 的 query/readback 边界具 local_contract/api_integration，projection 删除重建 exact 相同且 owner bytes 不变；fresh UAT/acceptance 仍由 discovery OPEN 关闭。


<a id="open-005"></a>
### OPEN-005 consumer rollback/replay 的同 identity 证据尚缺

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺一次上游 previous active release 经 runtime importer/outbox/Search/Recommendation/Homepage/media 全面恢复的 exact identity 证据；本缺口不拥有 canonical reset 或 release rollback command。
- 完成判定：`SIT-002` 的 api_integration 证明全部 consumer 恢复同一 previous release identity，混合 identity 与 counts-only 相等均 fail closed，且 canonical/pool/content-library owner bytes 不变。
