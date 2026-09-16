# L2 Design：发布评论互动状态 (`publish-comment-reaction`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同”需要 `comment-thread`、`filter-catalog-release`、`image-editing`、`post-create-update`、`reaction-state-counter`、`text-post-commercial-publication` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`comment-thread`](./comment-thread/spec.md)：Gamma 真机完成打开、评论、返回和二次进入。
- [`filter-catalog-release`](./filter-catalog-release/spec.md)：Mongo 真实引擎 contract 覆盖 digest 幂等、状态机和单 active CAS。
- [`image-editing`](./image-editing/spec.md)：全仓无占位符号；工具确认路径全部经 ImageEditorExportEngine 烘焙。
- [`post-create-update`](./post-create-update/spec.md)：从拍摄得到的图片可进入图片选择器底部缩略条或创作编辑器图片列表，并参与排序、编辑和发布。
- [`reaction-state-counter`](./reaction-state-counter/spec.md)：定义“互动状态状态计数”的可观察主路径、失败语义及父能力交接。
- [`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)：micro 与 article 两种确认结果均有 widget 与 payload 合同证据。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 published 与 actor-aware 资格由目标 owner 裁决
- 决策：Reaction 只经 Post/Comment owner 公开 typed 资格 reader 接纳新互动。Post 必须 published、审核与可见性有效且当前 verified actor 可访问；Comment 还需自身可互动和父 Post 资格。缺失、受限与依赖失败按 owning contract 分型，读面不泄露私有目标。
- 理由：仅检查非 deleted 或 Active 无法证明 published、审核及 actor 权限；Feed 曾可见也不是之后命令的授权凭据。
- 被否决方案：页面缓存 bool、恒 active reader、直接读兄弟私有 store、把前置读取当作跨聚合事务或把 basis 签名当当前权限。
- 约束与影响：资格校验与 Reaction 提交之间仍可能发生跨 owner 失权；公开面由当前目标资格保护，内部迟到事实按 DEC-006 最终抑制/清理，不能承诺跨 owner 删除之后绝无存储写入。
- 恢复与回滚：临时 reader 失败保留可重试读取，明确受限停止新动作；已提交不改报失败。回滚停止受影响新写，保留不可逆生命周期事实，禁止恢复旧宽松资格判定。
- 观测与测试 seam：分别观测资格成功、拒绝、依赖失败与公开附着完整率，零越权为硬约束；固定 typed port local_contract 只证调用协议，真实 Post/Comment reader API 反例证明 draft/hidden/deleted/父 Post/actor 矩阵，关联 [Reaction GWT-004](./reaction-state-counter/spec.md#gwt-004)、[Comment GWT-022](./comment-thread/spec.md#gwt-022)。
- 关联要求：`REQ-001`
- 影响 Story：[`comment-thread`](./comment-thread/spec.md)、[`filter-catalog-release`](./filter-catalog-release/spec.md)、[`image-editing`](./image-editing/spec.md)、[`post-create-update`](./post-create-update/spec.md)、[`reaction-state-counter`](./reaction-state-counter/spec.md)、[`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 不恢复 Post 级收藏，实体意图统一由「想去」承载

- 决策：`favorited` 已从 reaction 契约退场，不恢复 Post 级收藏；内容表面的意图动作
  统一为实体级「想去」（`wishlist_add/remove` 行为事实 + `GetEntityWishlistState`），
  意图对象是内容锚定的 canonical 实体（`primaryHomepageId`），不是 Post 本身。
- 理由：交集飞轮的意图信号源是 `coWishlistedEntity`（都想去同一实体），Post 级收藏
  没有任何消费闭环（无收藏夹场景、无推荐消费、无交集派生），只会稀释「想去」这个
  唯一意图信号的语义；「稍后再看」类内容收藏在出现真实闭环场景（生产者→消费者→用户价值三点齐备）之前不立项。
- 被否决方案：恢复 `favorited` reaction（无消费方的第二意图轨道）；把想去实现为
  Post 级事实（意图锚点错位，无法聚合到实体供给）。
- 约束与影响：涉及「赞+收藏」的历史规格文案按本决策修正为「赞+想去（有实体锚点时）」；works 沉浸页的想去按钮只在内容锚定到 `wishlistHomepageTypes` 支持的实体时渲染，不做本地推断。首页内容 Post 卡不消费该动作，即使携带合法锚点也不渲染想去 UI、语义或登录续接；实体主页入口、实体 wishlist contracts 与 `coWishlistedEntity` 派生保持不变。
- 关联要求：`REQ-001`
- 影响 Story：[`reaction-state-counter`](./reaction-state-counter/spec.md)、[`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 合集独立聚合与权限内分页

- 决策：PostCollection 独占合集元信息和有序 Post 引用，所有者命令以预期版本作 Mongo 单文档 CAS；创建使用调用者提供的稳定合集身份，重试不得重建第二合集。删除采用墓碑状态，保留版本以拒绝旧命令。Post 内容与可见性不复制到合集存储。
- 理由：跨作品顺序、所有权与并发版本构成独立一致性边界；单 Post 媒体项不能表达合集，也不能承载跨作品权限。
- 被否决方案：PostMediaItem 分集、页面内存合集、跨对象直接读写私有 Mongo 集合、无版本覆盖保存与客户端过滤分页。
- 约束与影响：合集 named reader 经 Post 公开 reader 查询当前可见成员，在保留作者顺序后对可见结果分页、计数；游标绑定合集身份、调用者和版本及最后扫描位置，编排变更拒绝续页，权限收缩每次重新过滤，不让失权成员与数量泄露。依赖读取失败传播 typed failure，不能伪造成空集合。
- 命令与查询：公开 Facade 独占创建、修改与删除；成员增删和排序在同一次预期版本替换中原子生效。公共查询只输出调用者可见成员及计数，不能作为聚合写回。独立 owner 管理 reader 返回已拥有的完整编排引用，失权成员不附带标题、媒体、类型或下架原因；客户端只从该视图编辑。新增成员与封面由现役作者作品 typed 查询选择，不提供内部标识符文本输入。公开 HTTP、App page 与 route 必须来自对象 metadata；在正式接线与 conformance 完成前保留 Story block OPEN。
- 一致性与幂等：同版本同状态重复命令回读原结果；过期且内容不同的请求返回版本冲突，不自动覆盖；数据库不确定失败由调用者先回读，不伪造成功回执。读取无跨对象事务保证，每次查询基于当前 Post 权限，后续导航仍由 Post 再鉴权。
- 恢复与回滚：版本冲突刷新后由作者重新确认；缺失或失权合集同为不可访问；存储或上游失败可重试读取，删除不触碰成员 Post。回滚停用合集入口与新写操作，保留 Mongo 数据和墓碑，禁止回退到本地第二真相源。
- SLI/SLO：命令及查询成功率、依赖失败率、CAS 冲突率与 P95 延迟；查询沿用本能力 800ms、命令 500ms 预算，持续超预算或存储失败触发停止放量。trace/request identity 由边界继承，只记录 outcome 与计数，不记录标题、成员标识及 cursor 原文。
- 测试 seam：固定身份与时钟的 Facade local_contract、真实 Mongo CAS/重启回读 conformance、Post named reader 权限分页 contract；App 单独证明 generated Remote/typed port，真实环境证据缺失不得视为可发布。
- 关联要求：`ordered-post-collection` 的 `REQ-001`、`REQ-002`、`REQ-003`。
- 影响 Story：[`ordered-post-collection`](./ordered-post-collection/spec.md)。
- 关联验收：`ordered-post-collection` 的 `GWT-001`、`GWT-002`、`GWT-003`。

<a id="dec-004"></a>
### DEC-004 Post 关联摘要只解析 canonical 引用

- 决策：Post named projection reader 通过各 owner 的公开查询将已发布 semantic mention、真实 Homepage、具有 Participation 的 Gathering 和独立合集引用解析成闭集 typed summary；目标类型显式区分话题、新闻事件、地点、参与活动和合集。
- 理由：关联标签与活动参与、地点文本与真实主页具有不同事实来源，字符串相似不是关系证据。
- 被否决方案：根据标题或 URL 猜对象、把新闻标签当活动、从同地点推断参与以及复制其他对象完整状态。
- 约束与影响：所有目标在响应前验证可见与有效性；不存在或无权限的引用不产生成功入口，上游读取失败向调用者传播而不回退旧摘要。页面消费 typed summary，布局与导航接线不改变事实所有权。
- 恢复与回滚：上游故障按 read failure 重试；错误映射修复后重新读取，禁止旧 wire 双读或默认成功。停止投放关联入口不删除 canonical 来源事实。
- 质量与观测：摘要共享详情读取预算，记录依赖类别与 outcome，禁止输出引用标识或原文；P95 或失败率持续越过详情预算时停止放量。不同 owner reader 的 typed seam 用于检验失权、悬空与依赖失败，真实跨服务验收保持独立 OPEN。
- 关联要求：`typed-post-associations` 的 `REQ-001`、`REQ-002`。
- 影响 Story：[`typed-post-associations`](./typed-post-associations/spec.md)。
- 关联验收：`typed-post-associations` 的 `GWT-001`、`GWT-002`、`GWT-003`。

<a id="dec-005"></a>
### DEC-005 Reaction 以单 actor-target 命令版本、受签名依据与 receipt 终结结果

- 决策：保持 ContentReaction 独立聚合与现役 Mongo adapter；Post 对外 bool、Comment 三态独立。幂等身份由 verified actor namespace 加稳定 command key 确定，摘要冻结目标、desired、前置版本和发行期限；HTTP 的唯一 canonical 幂等来源须映射到 store，body/header 冲突或不完整输入在写前拒绝。
- 决策：actor-scoped query 只签发轻量 mutation basis，不写业务事实；依据绑定 actor/目标 namespace、允许 operation、expectedVersion、服务端发行/截止时间与完整性签名。默认接纳窗口 72 小时，receipt 至少保留 96 小时；签名采用受管独立用途 key/domain separation，验签旧 key 保留覆盖最大接纳窗，不复用原始 access-token 密钥。Feed/详情按 batch/总 bytes 预算附着，有合法依据的点击不强制额外“读→写→读”。具体字段与恢复 operation 只归 Reaction contracts。
- 决策：新命令通过权限/依据/expectedVersion 后，连同 no-op 在同一 Mongo transaction 真正 CAS 更新 Reaction version、写 receipt，业务变化才追加 outbox。不存在为 version0，新接纳 no-op 也推进至下一版本；同键命中原 receipt 不推进。no-op 不加计数/业务事件，业务事件允许版本跳号，不能把 changed=false 等价 replayed=true。receipt 关联当前状态最近一次实际业务事实供因果读取，no-op 不让消费者等待未发布的新版本；初始无关系且无事件返回已验证空态，不制造假 event ref。
- 决策：write 与恢复终结经同一 actor-scoped receipt 唯一记录的事务插入/条件迁移竞争；有效期限制新接纳，已存在 receipt 可按保留政策读回。截止前进入但提交晚于截止的在途写与终结由事务赢家裁决；客户端到期不证明没有提交。已清理 receipt 的过期依据永不能新执行，历史不可判定只返回当前态与恢复入口，不补造提交归因。
- 理由：单 actor-target 版本隔离热门内容成员的并发，true→false→true 保留用户意图先后；新 no-op 若不写版本栅栏，旧离线请求能覆盖较新“保持不变”的决定。仅延长 TTL 或回读 bool 都不能证明原命令结果。
- 被否决方案：迁移到 PG 只为统一协议、target 共享版本、snapshot CountDocuments 代替 CAS、客户端墙钟 LWW、同键修改 desired/期限、永久幂等假设、过期后换键自动重发、未确认先等待/重算统计，以及吞坏 JSON 成默认命令。
- 约束与影响：状态、receipt 与 outbox 原子提交不包括跨 owner 权限、统计或推荐；提交响应来自冻结结果，不做后置 Count 决定成功。时间戳只作观测，顺序以逻辑版本裁决，跨副本时钟偏差按 owning 合同处理，不让正常微小回拨长期拒绝合法动作。业务冲突需当前事实与用户恢复，不悄悄刷新版本强写；数据库技术冲突只在同 key/deadline 内有界重试。
- 恢复与回滚：提交后丢响应保持 unknown，以原 key 恢复；receipt 确认即终结命令，统计不可用只降级统计。签名/作用域/配置错误不可长期重试；authority 不可用保留有界日志与恢复入口。升级采取单一最低支持客户端/合同准入；旧缺 basis/稳定命令的客户端明确升级或拒绝，不旧协议 fallback。回滚停新写且保留 authority/receipt/outbox、验签材料和已接纳命令恢复面，不恢复旧快照丢新写。
- 观测与 SLO：命令 availability 沿用 99.9%，服务 P95 800ms、P99 目标 1200ms；另记 durable 确认、unknown 年龄、同键回放、no-op/冲突/过期终结与签名失败，统计失败不计为已提交写失败。包含所有 attempt/timeout/拒绝，basis bytes/签名成本及 receipt 容量纳入准出；RPO=0 只能由批准故障模型的 majority/journal/切主证据证明。
- 测试 seam：固定 clock/签名 key 与 typed Facade 覆盖篡改、换 actor/target、期限续长及 no-op；真实 replica set 屏障证明 CAS 与 expire-finalize 恰一赢家、commit 后丢响应、receipt 逻辑/物理清理后旧依据拒绝。必须走真实 Remote→HTTP→receipt，不以手工 body 或替身证明原子性。
- 关联要求：`reaction-state-counter` 的 `REQ-001`、`REQ-003`、`REQ-004`；影响 Story：该 Story 与 `comment-thread`。
- 关联验收：[GWT-004](./reaction-state-counter/spec.md#gwt-004)、[GWT-005](./reaction-state-counter/spec.md#gwt-005)、[GWT-006](./reaction-state-counter/spec.md#gwt-006)、[Comment GWT-022](./comment-thread/spec.md#gwt-022)。真实 proof/合同缺口归 Reaction `OPEN-003`，不因 authoring 完成签发实现 PASS。

<a id="dec-006"></a>
### DEC-006 Reaction-owned 全桶写栅栏封闭与有界生命周期补偿

- 决策：Reaction 拥有每个 target 内固定数量的 lifecycle fence buckets，按 reaction identity 稳定路由；真实 Like transaction 必须检查所属桶 open 并更新其内部 commit 标记，再提交 Reaction/receipt/outbox。没有成员时惰性创建，桶数量不得运行期热变；测试基线 B=16，发布数量经热点/封桶延迟证明后在 owning storage/config 冻结。
- 决策：Post 删除消费者在 Reaction 自有 scope 持久保存来源版本化不可逆抑制事实，并在同一封闭事务关闭该 target 全部固定桶，包含缺失桶；与并发 Like upsert/update 产生真实写冲突。不得跨写 Post 私有存储，也不得把所有 Like 又集中到一个 target 行热点。封闭完成后每次最多清理 500 成员且受 deadline/总工作预算约束，持久 cursor/checkpoint 与 worker fencing 允许中断续跑；全部桶封闭且活跃成员/贡献到安全水位后才宣告清理完成。
- 决策：Post 删除、账号关闭和 Persona 退役补偿仅消费已验证 owner lifecycle event，经显式内部 port 授权。补偿 identity 绑定 event、成员和被清理版本，不要求已失效用户凭据或 App basis，不盲套 72 小时窗口；只有该内部操作可跳过新互动的 active 资格，普通 HTTP 无此权限。actor 清理按 actor-side 索引有界推进，撤销凭据不再接纳新写。
- 理由：只在事务快照读 tombstone 不制造冲突，目标检查后→删除扫空→晚到 upsert 可复活。固定 target 内桶分散正常写热点，又允许在一次可证实的边界封完所有写路；仅 hash(target) 分区不拆 target 热点。
- 被否决方案：跨 owner 分布式事务承诺、只读墓碑/只关已存在桶、单 target 全局写锁、while 每批 500 直到空的无界 Drain、复用旧 cleanup receipt 而忽略被清理版本、全图周期扫描和用用户凭据伪装内部补偿。
- 约束与影响：Post owner 删除提交后公开访问立即服从其资格；Reaction 尚未观察事实时内部短暂提交属于声明的跨 owner eventual 边界，公开统计/推荐不得重新放行。永久抑制事实是 owner lifecycle 的受信执行投影，不成为第四条 Post 删除真相；周期反熵仅处理已登记 dirty/tombstone scope。
- 恢复与回滚：失败保留首个 typed blocker 与 durable 续跑位置，重启从未完成范围接续；旧 worker 不推进新租约水位。清理保留最小不可逆防复活依据，retention 依 source/required consumer 安全水位，不无条件 TTL。回滚停新写/清理 worker 升级，不解封永久关闭桶或恢复已失权公开数据；热点 proof 不达标则阻断接线并重审本 DEC，不忽略 race。
- 观测与 SLO：记录封桶 transaction 延迟/冲突率、未封桶数、dirty scope 年龄、批次处理量/耗时、剩余成员与贡献、安全水位和旧 worker 拒绝；单次超过 500 或 deadline、封闭后新增活跃成员为硬告警。大 target 清理耗时及恢复速率须在批准百万级热点画像实测，不承诺无资源条件下的固定排空时长。
- 测试 seam：local_contract 控制预算退出、成员版本与授权；真实 Mongo replica set 在资格后、写事务中、清理扫空后三个屏障放行 Like，涵盖缺失桶、crash/restart、旧租约/重复 event、actor 关闭与外部伪造补偿，比较公开 reader 和活跃贡献。仅内存替身不构成真实冲突证据。
- 关联要求：`reaction-state-counter REQ-005`、`comment-thread REQ-006`；影响 Story：`reaction-state-counter`、`comment-thread`。
- 关联验收：[Reaction GWT-007](./reaction-state-counter/spec.md#gwt-007)、[Comment GWT-022](./comment-thread/spec.md#gwt-022)，required 缺口分别留在 Story `OPEN-004`、`OPEN-016`。

<a id="dec-007"></a>
### DEC-007 成员贡献 inbox、分桶统计与来源代际修复

- 决策：ContentReaction 拥有 target 统计读面与消费账本，Post/Comment 仅组合；User 拥有 Persona 社交统计，不把 owner 账号总数当 Persona 数。每个事件在消费方以 event identity 去重，并将成员 lastAppliedVersion/currentContribution 与所属 bucket 的新后态减旧贡献原子提交；同版本异摘要拒绝，重复/旧版本无效果。
- 决策：低度数惰性建桶，周期 rollup 以固定频率上限产出 statsVersion、source checkpoint 与 generation。版本只在对应对象/代际内比较，数字可因取赞下降；不逐事件写热门 Post 正文或作者资料，不伪造 PostUpdated，也不逐事件/每次点查全目标 Count。
- 决策：业务事件携带完整后态并容许 no-op 版本跳号；实际 outbox 使用按 reaction identity 路由的固定分区运输序列，同事务分配并写事件，不维持全站 sequence 热点。消费者各自独立 checkpoint/lease，at-least-once + inbox 保证幂等效果而非端到端 exactly-once；毒事件停住所属分区连续 applied 水位，保存原事件/typed 原因/重试与告警，其他分区继续。fetched/quarantined/applied 不混用，旧 worker 的 token 必须约束 sink 与 checkpoint。
- 决策：repair 固定权威 snapshot、贡献 generation 与每分区 source checkpoint，重建后追平未包含增量，校验 oracle 后发布一个 reader generation；旧汇总/缓存不能覆盖新代际。shadow 仅旁路对账不服务业务，不在线 dual-read。retention 基于 required consumer 安全水位、离线恢复窗口和权威快照/归档来源，不能用 stream TTL 替代 outbox/receipt 恢复保证。
- 理由：纯 delta 重复或重建已含新边后再次应用 delta 都会漂移；成员完整后态允许乱序和版本跳跃，惰性桶/定频汇总限制热点写放大。
- 被否决方案：全量 Count 热路径、每事件更新单个总数热点、GREATEST(0) 掩错、以 aggregateVersion 当连续运输序列、取 MAX checkpoint 跳毒事件、重建覆盖并发新增量、未接 production composition 的孤立 projector，以及匿名 device 冒充 Persona 兴趣。
- 恢复与回滚：毒事件修复后从受阻分区原事件重放，若允许跨 gap 继续需另有 durable gap 设计，本期不默默跨越。来源已超 retention 时从可验证 snapshot/authority 重建，无恢复来源或未对账保持 not-ready；quota/计数维护预算独立，不能删除未消费记录解压。回滚保留新 authority 与 lifecycle 抑制，重建追平后单 reader 切换，不能回到旧快照丢写。
- 观测与 SLO：记录分区 backlog age/连续 applied 水位、租约拒绝/毒事件、重复/异摘要、贡献 oracle 差异、桶与 rollup 延迟、代际切换、磁盘和恢复来源余量；projection 正常 2 秒只是 5 秒端到端预算，不由无新事件的旧 occurredAt 推断积压，使用处理水位/健康进度。负数、异摘要或复活为硬告警，消费者落后不撤销命令成功。
- 测试 seam：local 可控版本/事件序列和 fixed snapshot 验证贡献函数、同版本异摘要和预算；真实 storage transaction 验证 inbox/member/bucket 原子性，多 worker/毒事件隔离、rollup 与 repair 并发、旧 generation 迟到。至少一条真实 Remote→自动 production worker→stats reader 链，不全用手动 drain。
- 关联要求：`reaction-state-counter REQ-006`、`REQ-007`；影响 Story：`reaction-state-counter`、`comment-thread`。
- 关联验收：[GWT-005](./reaction-state-counter/spec.md#gwt-005)、[GWT-008](./reaction-state-counter/spec.md#gwt-008)、[GWT-009](./reaction-state-counter/spec.md#gwt-009)、[Comment GWT-006](./comment-thread/spec.md#gwt-006)；统计/readiness 缺口归 Reaction `OPEN-005`。

<a id="dec-008"></a>
### DEC-008 统计缓存同任期原子防旧填充，跨 failover 只承诺源期限内陈旧

- 决策：统计提交之后由 durable consumer 失效或版本化更新该统计 cache；Reaction 已提交但统计尚未提交时不能先删 cache 然后重缓存旧总数。Redis 仅为短 TTL 公开统计/正文加速，actor 私有态不混入公共 value，安全、receipt 恢复与带最小版本的 RYW 走 authority。
- 决策：miss 先取非复用 generation，再读 source；generation 校验、版本约束与 SET/失效在同 hash slot 以 Lua 或等价原子操作完成，缺失/eviction 创建新 token 不重用固定零。值和填充凭据带保守 source readStartedAt、asOf、checkpoint/generation 及不可续期 absoluteExpiresAt；读/填充/L1 接收均复核期限，源副本 lag 与时钟偏差纳入预算。
- 决策：同任期已生效失效可拒绝迟到填充，但 DB→Redis 异步窗口或 Redis 异步复制 failover 可能回退到 g1+旧值；本期明确允许原 source 期限内陈旧，随机 token/Lua 不承诺跨切主 fencing。统计服务 TTL 目标 1 秒，抖动计入硬期限；App 继承来源，不能从落后投影新 SET 就重置鲜度。更强 failover 语义需 Redis 外 durable epoch，本期不新增。
- 理由：GET generation 后独立 SET 仍有 TOCTOU；只做 DEL 或给缓存续租会把短暂投影落后扩成长期陈旧。源绝对期限在失效遗漏/旧副本提升时仍给出可验证上限，同时不引入普通计数不需要的全局协调。
- 被否决方案：Redis/DB 原子双写承诺、Lua 等于跨主从线性一致、重新 SET 续鲜、TTL 从每层接收时起算、读失败负缓存成零/false、viewer 字段共用公开缓存，以及逐卡 timer 或全站推送重建。
- 恢复与回滚：metadata/连接故障或已知切换期有界 bypass，配 singleflight、bulkhead/回源令牌与 deadline，不能耗尽 authority pool；超过 source 硬期限或最小版本不满足返回 typed unavailable。回滚可 bypass cache，不换旧统计真相、不解禁失权内容，generation 迁移保持一个在线 reader。
- 观测与 SLO：cacheAge、projectionLag、invalidationLag 独立，记录真实 hit、拒绝 stale fill、failover/bypass、key/byte/eviction、DB 放大、源期限超限和完整统计附着率；命令 availability 与统计 availability 分开。以同一事实 commit→render P99≤5 秒的批准负载测量确认总预算，在线人数×可见批大小×刷新频率单列；缺容量证据继续 OPEN，不以分项 P99 相加。
- 测试 seam：真实 Redis 同 slot 失效/填充 race、generation eviction 与缓存 hit 的 DB 调用计数；必须额外模拟阻断复制→g1 更新 g2→提升仍持 g1 的副本→释放旧填充，断言原期限不能延长、RYW/security 仍读 authority。清库测试不代替落后副本反例；App fixed clock 证明 L1 不续期。
- 关联要求：`reaction-state-counter REQ-007` 与 `viewer-profile-state-sync-contract REQ-005/006`；影响 Story：Reaction 统计与跨页状态同步。
- 关联验收：[Reaction GWT-009](./reaction-state-counter/spec.md#gwt-009)、[状态同步 GWT-007](../content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-007)，真实缓存/容量缺口仍由最低 Story OPEN 承接。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：确定拒绝不写成功事实；超时/断连/提交结果未知走同键恢复，不能推断未提交。冻结 receipt 已确认后，统计、推荐或响应传输失败不能把命令改报业务失败。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- SLO：Comment 列表 P95 800ms、创建/回复命令 P95 500ms；Reaction 命令按 DEC-005 的 P95 800ms 独立计量，不把评论预算覆盖到 Reaction。hotScore/统计投影收敛滞后 SLI 与告警分别报告。
- 灰度：Canary → 1% → 50% → 100%，回滚条件绑定评论创建成功率与列表可用性 SLO。
