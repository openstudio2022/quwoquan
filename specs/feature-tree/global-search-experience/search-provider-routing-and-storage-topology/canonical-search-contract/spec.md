# L3 Story：标准搜索契约 (`canonical-search-contract`)

> 所属能力：[`search-provider-routing-and-storage-topology`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望 App 与小趣通过同一 search request/response 契约获得可分类、可分页且错误明确的结果，从而找到可理解并可继续操作的对象。

## 2. 范围与非目标

### In Scope

- 单一 search(request) contract，suggest/result 仅以 mode 区分。
- 请求过滤词汇单轨：`objectTypes` 只使用 canonical 对象词汇（`content.post` / `user.profile` / `entity.homepage` / `circle.circle` / `circle.group` / `location.place`），`contentTypes` 只使用 `article` / `image` / `video`；App、api-edge GraphQL 读接口与 assistant retrieval 共用同一词汇。
- 商用 response 字段 requestId/experimentBucket/relatedTerms/rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason。
- 搜索实验 assignment unit 只使用可信登录主体或匿名稳定 `X-Session-Id`；禁止空主体默认为 control，也禁止用逐请求 requestId 重分桶。
- 未投影或未激活实验策略时，搜索可按显式 control 语义降级；该 control 语义必须拥有稳定策略摘要并与候选、查询、筛选和主体共同绑定分页 cursor，不得因命中超过首屏而退化为 `SEARCH.USER.invalid_argument`。
- Search runtime 必须从受管部署入口接收当前 immutable candidate digest；不得以空候选身份签发分页 cursor，也不得仅在单页查询中形成假绿。
- App result 唯一消费 `SearchPage` persisted GraphQL；`POST /search` 与 RetrieveRequest 只服务 assistant retrieval 与 api-edge owner projection。
- 错误响应经 CloudException/runtimeFailure 结构化。

### Out of Scope

- 具体排序算法与 provider 实现。
- 复杂布尔 DSL / 脚本排序 / 图查询表达式。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 唯一 canonical contract + 商用 response 字段（metadata/codegen 对齐）

- 页面与业务层只看到一个 contract，商用字段以 metadata 为唯一真相源。

<a id="req-002"></a>
### REQ-002 App result 只消费 SearchPage persisted GraphQL 响应

- App result 阶段唯一消费 `SearchPage` persisted query 的 typed slice；`POST /search` 不得再作为结果页生产读入口。

<a id="req-003"></a>
### REQ-003 统一 search(request) 作为页面与业务层唯一入口

- 统一 `search(request)` 作为页面与业务层唯一入口。
- 统一 `search(request)` 作为页面与 AI agent 检索 tool 的共用入口。
- 统一 `SearchRequest / SearchResponse / SearchSection / SearchHit` envelope。
- AI 模型可生成 typed 查询条件，但必须落在 schema 允许范围内。
- contract 必须保持 web-search-like 的 query-first 结构，支持 `web.document` 与趣我圈对象统一召回。
- 商用字段（`rankReasons / rankPosition / relatedTerms` 等）只在服务端产出，端侧只读消费，不得客户端合成形成第二真相源。
- Data Post 的源事实只能来自 Content verified candidate 及其 canonical Post lifecycle；激活前按跨域 [DEC-003](../../../runtime/runtime-data-engineering/design.md#dec-003) 从 owner typed candidate query 准备不可见搜索分区，激活后 durable outbox 只通知/对账同一候选，不能成为首次可读触发。公开查询必须匹配 Content active fence；公开 UGC 仍经原 lifecycle 进入，更新后重建文档、删除后移除。禁止 Data 或环境部署直接 seed 搜索索引，禁止把未激活准备伪装为 PostPublished。
- release verify 必须经 canonical `POST /search` 精确证明 Manifest 中每个 Data Post 和平台虚拟 Persona 可查询；仅证明 importer 成功不能作为 Search 就绪证据。
- 普通账户及其 Persona 公共资料只通过 `UserProfileSearchProjectionRequested` durable event 进入 Search；事件必须自包含公开快照，SearchIndexView 以 eventId inbox 与 profileVersion watermark 幂等消费、独占 Provider upsert/delete，失败不得前移 checkpoint，禁止 User 直写搜索 Provider 或 Search 回读 User 数据库。immutable release Creator 不属于该账户事件来源，其公开资料按 `REQ-005`、`REQ-006` 准备与查询；不得因复用 `user.profile` 而伪造普通账户事实。

<a id="req-004"></a>
### REQ-004 请求过滤词汇单轨（objectTypes + contentTypes）

- `search(request)` 的 `objectTypes` 取值域是 canonical 对象词汇：`content.post` / `user.profile` / `entity.homepage` / `circle.circle` / `circle.group` / `location.place`；`contentTypes` 取值域是 `article` / `image` / `video`，仅当过滤范围含 `content.post` 时生效。
- 内部召回 target（`article/photo/video/user/entity/circle/group/location`）是 search-service 的实现细节，由 `objectTypes × contentTypes` 在服务端单点压平推导；target 词汇不得出现在任何对外 wire、GraphQL schema、App enum 或 assistant tool 参数中。
- App `RemoteSearchPageRepository`、api-edge `SearchPage` executor、search-service 请求校验与 assistant retrieval 四处的词汇必须同源，任一处偏离即门禁 BLOCK；禁止在链路中间做第二套词汇翻译表。
- 携带合法 `objectTypes`/`contentTypes` 的请求不得被 `SEARCH.USER.invalid_argument` 拒绝；携带 target 词汇或未登记词汇的请求必须结构化拒绝，不得静默回退默认召回域。

<a id="req-005"></a>
### REQ-005 普通账户与 release Creator 复用公开结果身份但不混淆事实来源

- release 引用的平台 Creator 必须可作为 `user.profile` 精确搜索，保留 canonical Creator 与 Persona 的公开身份映射；搜索结果、公开资料、作品和导航目标身份一致，不创建新的搜索结果类型，也不把 Creator 改成可登录账号。
- Creator 公开资料只能来自 User owner 验证的 immutable release candidate 的 typed 公开快照；Search 独占该来源的 Provider 投影写入。禁止跨库读取、从 Post 作者展示快照补造完整资料、伪造普通账户事件、写 Persona 或 PostgreSQL 账户 outbox。
- Creator 内部投影不构成独立结果类型，不等于其公开资料不可搜索。普通账户的资格、封禁、关闭、隐私与调用方鉴权继续适用原契约，不因 Creator 来源增加而放宽；两类来源的公开身份冲突必须阻断，不按到达顺序覆盖或以 ID 前缀猜来源。

<a id="req-006"></a>
### REQ-006 Creator 搜索准备纳入唯一 Content 可见性屏障

- Creator与Post/Homepage必须统一升级为一个typed准备输入、一个proof协议、一套prepare/query和流程存储；不保留Creator-only可调用协议、兼容版本、默认补字段或旧completed转当前ready。slice只区分对象种类；旧事实仅离线审计，新运行重新prepare，客户端/配置/测试同时切换，未切完保持OPEN。
- Creator candidate 搜索闭包必须在激活前经 owner 正式准备并实际可查询；准备与重放不得改变当前 live 搜索结果，部分成功或请求已接收不能作为完整查询就绪。Search 可持久化其派生准备进度与证明，调用方必须回读可验证终态；该准备过程不得拥有 release activation/rollback 决策或独立 active pointer，不能把准备受理当成 release 激活成功。
- Content 执行 activation CAS 前必须消费 Search 对目标 release 与完整预期 Creator 集合的 exact 查询就绪证明；证明缺失、来源或摘要漂移、Provider 代际不匹配、部分准备均不得 CAS。仅有四域 import/readback 或其他用户文档数量不构成 Creator Search 就绪，CAS 后等待异步补齐不能替代准入。
- Creator 搜索可见性只服从 Content 的权威 active fence；所有相关搜索入口在 Provider 查询前限定同一内容版本，结果、数量、筛选聚合与分页均不泄露未激活或旧 candidate。部署候选身份不能替代内容版本 fence，公开调用方不得指定候选绕过它。
- 切换及显式 rollback 后，新请求只读取对应的已验证 Creator candidate；旧 cursor 必须失效并要求重新取首屏。准备失败、CAS 冲突保留旧 live；首次无 previous 保持无 active；CAS 结果未知必须先查权威 pointer，不能猜成功或自动重做 CAS。恢复沿用跨域 [Content fence 决策](../../../runtime/runtime-data-engineering/design.md#dec-003)。
- 本要求只关闭 Creator 搜索 slice，不宣称 Post、Entity、Recommendation 的必要查询屏障已实现；完整闭包仍由 [无中断查询准入 OPEN-019](../../../runtime/runtime-config/environment-topology-and-packaging/spec.md#open-019) 阻断。

<a id="req-007"></a>
### REQ-007 release 退出不等于权威删除，安全撤回优先于 rollback

- Content release 从 A 切换 B（包括显式 rollback）只改变唯一 active fence；A 独有 Post 退出当前 live 不等于作者删除、隐私撤回或最终清除。不得向对象删除消费者发送伪造的删除事实，不得修改 A 搜索/推荐 candidate 或触发评论、互动、媒体的权威删除级联；B 的不可见准备不能成为新的发布事实。
- 作者删除、隐私撤回、清除、审核拒绝及可见性收紧仍由 Content 对象 owner 的现役命令/安全事实唯一决定。已失去公开资格的 canonical Post 在所有保留候选、重放、重建及未来 prepare 中均不得复活；release rollback 不拥有恢复安全资格的权限。安全拒绝优先于候选保留窗口，媒体与个人字段清理由现役 privacy 契约约束，离线审计保留不得成为继续服务被撤回字节的理由。
- 最小恢复裁决：含失效 Post 的 immutable candidate 整体不再具备 activation/rollback 资格；不得静默过滤其对象后沿用原 objectSet/proof，也不得改写其源摘要伪装成原候选。需由 owner 产生当前安全合法的新候选并重新 prepare；其他未受影响且仍通过全部证明的保留候选才允许显式 rollback。不可逆删除/清除不因更大的 release revision 或迟到 upsert 被解除。
- 普通 lifecycle 更新和 candidate 准备必须从 Content 同一 canonical 公开投影派生。对象 sourceVersion、candidate 源版本、activation/outbox 顺序及 Content revision 各有命名空间，不能互相抬升或代替。无公开事实改变的 activation 对账只比较 exact candidate 的原版本/摘要，不借新 activation 序号覆盖原文档；公开内容变化须经合法 owner 版本及新候选准备，不原位修改冻结输入。
- 退出/对账必须绑定已提交的前后完整 fence，权威删除/撤权必须绑定显式来源和 canonical 对象身份，不从缺失字段、ID 前缀、当前 active 或不存在的 candidate 猜目标。源审计 releaseDigest 与可见性 manifestDigest 分离；同意图重放幂等、同身份不同摘要拒绝、乱序不改新状态；未知/缺失 payload 不得成功确认或前移 checkpoint。
- proof 到 CAS 必须有真实、持续且被部署切代/GC及 owner 安全变更路径共同执行的保护。首尾读到相同 generation、证明有效期、Content 单库事务或本地 ship 锁均不等于该保护；缺失时阻断激活，不得让安全撤回等待 rollback 保留或被保护租约压住。范围与依赖见 [DEC-003](../design.md#dec-003) 及 `OPEN-003`。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/search_contract.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_objects.yaml`
- 普通账户来源：`quwoquan_service/services/user-service/contracts/account/user_account/events.yaml`
- Creator 来源：`quwoquan_service/services/user-service/contracts/profile_projection/creator_runtime_profile/object.yaml`
- Search 投影与查询：`quwoquan_service/services/search-service/contracts/search/search_index_view/operations.yaml`；准备进度与证明由独立 Search-owned 流程对象承接，按 [L2 DEC-003](../design.md#dec-003) 补齐所属对象契约，不能在只读 projection 上声明 command。
- User 公开投影边界：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`；跨服务公开快照值唯一声明位：`quwoquan_service/contracts/metadata/_shared/types.yaml`。
- Content 可见性与准入：`quwoquan_service/services/content-service/contracts/content/post/storage.yaml`
- 上述 Creator typed 准备与查询证明尚需所属对象 contracts 补齐，缺口由 `OPEN-002` 承接；本规格不新增 wire 字段、事件、endpoint 或 schema。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 唯一 canonical contract + 商用 response 字段（metadata/codegen 对齐）

- GIVEN _shared/search_contract.yaml 已登记商用字段且 make verify-metadata 绿。
- GIVEN codegen 产物 search_registry.g.dart 与 metadata 一致且幂等。
- WHEN 调用 search(request) 以 mode=suggest|result 区分，返回统一 envelope。
- THEN response 含 requestId/experimentBucket/relatedTerms；hit 含 rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason。
- THEN 登录态从可信 principal 派生 experiment subject；匿名态必须按 SearchRequestFact contract 携带稳定 `X-Session-Id`，缺失时返回 `SEARCH.USER.invalid_argument`。
  实验策略缺失或未激活时返回 `experimentBucket=control`，多页中文查询仍生成绑定 canonical control 摘要的 opaque cursor；策略身份变化后旧 cursor 必须 fail-closed。
- THEN suggest 与 result 共用同一接口，无第二套建议专用接口。
- AND 普通账户 UserProfile/Persona 更新与删除由同一 Search-owned durable consumer 投影；相同 eventId 重放幂等，旧版本不覆盖新版本，Provider 失败保留 pending stream checkpoint。

<a id="gwt-002"></a>
### GWT-002 App result 只消费 SearchPage persisted GraphQL 响应

- GIVEN alpha/beta/gamma/prod composition 中 result 远程仓库只返回 `RemoteSearchPageRepository`（经 `HybridSearchRepository` 包装）；搜索 typed double 仅存在测试树。
- GIVEN assistant retrieval 仍经 RetrieveRequest 映射 targets 并剔除 chat 本地命名空间对象；api-edge owner 仍调用 search-service `POST /search`。
- WHEN result 阶段 POST `/graphql` 执行 `SearchPage` persisted query，解析 typed `SearchPageSlice`。
- THEN App 只读消费 slice 级 `searchRequestId`/`matchedTerms`/`degradeSignals`/`suggestions` 与 item 级 `objectRef`/`rankPosition`/`rankReason`/`contentType`/`action`，不再消费分域搜索接口，也不得把 opaque `objectRef` 合成旧 hit envelope。
- THEN 错误经 CloudException/runtimeFailure 结构化，不吞异常、不暴露原始异常字符串。
- AND `POST /search` 仅作为 owner/assistant 内部口保持 typed 契约，不得回到 App 结果页生产装配。

<a id="gwt-003"></a>
### GWT-003 请求过滤词汇单轨端到端生效（objectTypes + contentTypes）

- GIVEN App 结果页任一 Tab 携带 canonical `objectTypes`（如 `content.post`）与可选 `contentTypes`（如 `video`）发起搜索。
- WHEN 请求经 api-edge GraphQL `SearchPage` persisted query 转发到 search-service `POST /search`。
- THEN search-service 接受该词汇并返回 200，结果集只含所选 objectTypes，`contentTypes` 过滤同时在 `content.post` 命中上生效。
- THEN 携带内部 target 词汇（如 `photo`）或未登记词汇的请求被结构化拒绝：search-service 返回 `SEARCH.USER.invalid_argument`，GraphQL 层由 `SearchPageObjectType`/`SearchPageContentType` 枚举校验拒绝内部词汇上 wire。
- THEN App enum、GraphQL schema 枚举、api-edge 映射与 search-service 校验四处词汇由静态门禁证明同源，api-edge 集成测试的 owner 替身与真实 `POST /search` 校验语义同源，不得再出现替身接受、真实拒绝的分裂。
- THEN 结果投影字段在 wire 上完整：slice 级 `searchRequestId`、`matchedTerms`、`degradeSignals` 与 item 级 `rankPosition`、`contentType`、`rankReason` 全部可见。
- THEN 同 viewer/query/filter 的重复执行 TopN `objectRef` 序列一致、翻页 cursor 序列连续无重复，全栈装配链（网关 `/graphql` → api-edge persisted query → search-service 真进程 → CJK ES）的上述行为由环境冒烟 CaseResult 证明。

- GIVEN 普通账户资料和同一 Creator 的 previous、candidate 两份 immutable release，candidate 同时包含作者改名、新增与移除，且引用闭包及媒体 authority 均由 owning service 验证。
- WHEN 经正式 owner 准备入口执行完整准备、部分失败和中断重放，再经 Content activation、canonical Search、公开作者页及显式 rollback 读取。
- THEN Creator 命中保持 `user.profile` 与原 Persona 公开 ID，作者页、作品、导航和头像绑定与同一 release 一致；准备过程不写账户、Persona 或 PostgreSQL 账户 outbox，不接受伪造账户事件或私有字段，普通账户封禁、关闭、隐私与鉴权不变，来源身份冲突阻断而非覆盖。
- THEN stage、重复准备、Provider 成功后回执持久化失败及重放期间 previous 的命中、计数与筛选聚合不变；缺失、漂移或部分查询证明使 Content CAS 不发生，只有完整 exact candidate 实际可查询后才可准入，新旧版本的同一作者不得互相覆盖。准备受理与完成分开回读，进程中断后按持久 checkpoint 显式恢复；同候选并发推进只有一个有效 writer，过期执行者不能提交完成证明，失败准备没有 release 切换权。
- THEN CAS 后 result、suggest、retrieval 及分页仅暴露权威 fence 所选 Creator，旧 cursor 明确失效；显式 rollback 以新 revision 恢复保留的 previous candidate 而不降低 Provider external version 覆盖，CAS 冲突不改变 live、首次准备失败保持无 active、结果未知先 exact readback。CAS 后 readback 与显式 rollback 的恢复预算按跨域 Content fence 决策实测，失败保持 typed 阻断，不用其他用户计数或旧 receipt 代替。

<a id="gwt-004"></a>
### GWT-004 release 退出、权威撤回及准备保护单轨闭合

- GIVEN A 含独有 Post X、B 不含 X，两候选公开投影与证明合法且普通 UGC/账户同时存在。
- WHEN A→B→A。
- THEN 每次仅以新 revision 切换 fence，X 随 fence 隐藏/恢复，A candidate 源字节和 Provider sourceVersion 不被退出通知改写，评论/Reaction/媒体不因 release 退出被权威删除，普通来源不变。
- GIVEN A/B 保留候选引用同一 canonical Post X。
- WHEN Content owner 删除、privacy redaction、purge 或收紧 X 公开资格，且迟到准备/upsert、rebuild 与 rollback 并发。
- THEN 所有读面及安全清理按 owner 契约拒绝 X，旧 candidate 不可再准入，旧 proof 作废，不能靠更大 activationRevision/source sequence 复活；合法新候选重新准备，未改原件及其摘要。安全消费者部分失败不返回成功终态，读与CAS在无法证明安全时 fail closed。
- GIVEN 已提交 transition 的 exact 前后 fence 与 candidate 集合。
- WHEN 同事件重放、同revision不同摘要、逆序投递、未来revision、缺tuple、未知字段、跨环境或错误来源到达。
- THEN 仅可核实的同事实重放/已过期顺序被记录为明确幂等结果，未核实的事实阻断且checkpoint不成功前移；不猜旧candidate、不发共享键墓碑，响应丢失先查Content权威事实而非重做CAS。
- GIVEN 同一 Content 公开源及其正版本。
- WHEN prepare 与正式lifecycle mapper分别映射。
- THEN 可公开字段、空值、媒体、对象映射及规范摘要完全一致，同version不同digest必拒绝；activationRevision变化不改变源版本，source审计摘要不能替代visibility摘要；普通来源字段按契约显式声明而非消费者推断。
- GIVEN proof验证与CAS之间设置确定性测试栅栏。
- WHEN 在栅栏内尝试alias/schema切代、候选GC、owner撤权、保护超时/进程死亡。
- THEN 切代/GC在有效保护内不能破坏被验资源，撤权优先使不合法CAS失败，过期持有者不能提交；前后两次采样相同也不放行未受保护CAS。保护必须由全部参与写路径共同执行；缺失则阻断，不能用恒真端口、自述回执或延长proof有效期通过。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)；Creator 查询屏障受跨域 [Content fence 决策](../../../runtime/runtime-data-engineering/design.md#dec-003) 约束。

## 7. 开放事项

<a id="open-003"></a>
### OPEN-003 Data lifecycle目标与安全防复活、proof→CAS持续保护未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Content importer把旧live退出编码为新tuple的PostDeleted，而现役Search/Recommendation、评论和Reaction按权威删除消费；candidate准备与lifecycle公开mapper/sourceVersion不同轨。已存在的DeletePost事务墓碑仅支持当前对象删除窗口，不证明跨候选/未来prepare的安全防复活；PostPrivacyRedacted/PostPurged已有契约但尚未定位生产发布者。现役RequiredQueryEvaluator的ReleaseBindings、OwnerClosureReader和GenerationProtection尚无完整生产装配，VerifyHeld签名或前后采样不构成有效保护。
- 完成判定：`REQ-007`、`GWT-004`全部结果由Content源契约单写、Search/Recommendation同轨消费者、真实发布/安全事务/受管部署与GC路径、local_contract及隔离Mongo/ES api_integration共同证明；A→B→A不产生伪删除，安全撤回不可复活，原Content CAS正例经真实evaluator与保护通过，负例持续拒绝。不得以规格结构验证或既有ES PASS关闭本项。
- 依赖：后续串行修正Content Post fields/events/storage/operations、对应消费契约及生成物，再实现canonical公开投影、transition对账、安全失效与完整evaluator。保护authority尚缺，须由运行拓扑/部署owner交付所有参与者共同执行的资源保护及CAS fencing，不另建Search activation状态机；完整环境准出继续依赖environment-topology-and-packaging `OPEN-019`。


<a id="open-001"></a>
### OPEN-001 全栈搜索真实投影与语料闭环

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺全部 owner 生产投影的 canonical `Document.DeepLink`，缺失时 owner hit 的 `action` 为空且 api-edge 必须按 `fields.yaml` 的 `action NOT_NULL` fail-closed。`user.profile` 投影还缺 contracts-first 的 `userHandle`。canonical release 的 source identity 与 pool admission 未闭合时，ES 也缺少 article、image、video 的真实语料。测试 fixture 自带 DeepLink 或非 canonical URL 不得替代真实 owner 投影与 release 导入。
- 完成判定：`GWT-003.t5` 的全栈冒烟 CaseResult 半区满足——各 owner 投影补齐 canonical DeepLink（user 侧 contracts-first 加 `userHandle`）并 backfill 重放、api-edge 集成测试 owner 替身与真实 search-service handler 同源化、数据迁移收口后 canonical release 导入使 ES `content.post`（article/image/video）、`entity.homepage`、`user.profile` doc count > 0，执行冒烟 runner（覆盖 `GWT-003.t1`、`GWT-003.t2`、`GWT-003.t4`、`GWT-003.t5`），`status=passed` 且非空命中，归档 `.qwq_output/env/repo/runs/search-fullstack-smoke/`。

<a id="open-002"></a>
### OPEN-002 release Creator 搜索来源与 candidate 查询屏障尚未实现

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Creator 已有 immutable candidate 与公开资料读取，但 searchable owner 注册和普通账户事件不能表达 release Creator 来源，尚缺 owner typed 公开快照、Search candidate 准备及真实查询证明、Content CAS receipt 屏障与 fence-aware Provider 查询。新增规格不代表实现完成；不能删除 Data 作者精确搜索检查或伪造普通账户事件使之通过。
- 完成判定：[`GWT-003.t6`、`GWT-003.t7`、`GWT-003.t8`](#gwt-003) 的 Creator 来源隔离、候选准入及切换恢复结果分别由直接 `spec_ref` 绑定的 local_contract、真实 Mongo/Elasticsearch api_integration 与 Android/iOS 搜索到作者页 user_acceptance 共同证明；故障注入覆盖部分准备、幂等重放、CAS 冲突、首次无 previous、结果未知、显式 rollback 与恢复预算。取得同一 immutable release 中每个 Creator 的 canonical Search 精确命中及公开资料/作品/媒体 readback，而非只有非零文档数。
- 依赖：User 唯一公开投影 owner 对 Creator candidate 的 typed query、共享公开快照值、Search-owned 候选准备流程、SearchIndexView 与 Content Post 对象 contracts-first 交付。既有 process_manager 规约可表达准备状态与命令，但新对象契约尚未 authoring/编译，不能把设计可表达性当成 contract 或 runtime PASS；不得为本能力放宽 projection command、HTTP/runtime 互斥或扩展跨域类型解析器。Content `ActiveReleaseFenceQueryPort` 的正式受信 transport 仍待独立任务交付，本 Story 只消费其单一 authority，不猜 endpoint 或字段，不跨库替代。完整 Post/Entity/Recommendation barrier 仍由 environment-topology-and-packaging 的 `OPEN-019` 承接，本 OPEN 关闭不替代全局准出。
