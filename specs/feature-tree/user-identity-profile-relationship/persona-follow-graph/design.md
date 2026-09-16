# L2 Design：Persona 与关系图谱 (`persona-follow-graph`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“本能力统一分身生命周期、公开身份、关系隔离与跨域透传”需要 `follow-relationship`、`persona-context-propagation`、`persona-management`、`persona-profile-subject-and-visibility`、`social-graph-read` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：本能力统一分身生命周期、公开身份、关系隔离与跨域透传。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`follow-relationship`](./follow-relationship/spec.md)：owner 不能作为默认 follow 主体参与社交关系建立。
- [`persona-context-propagation`](./persona-context-propagation/spec.md)：若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`。
- [`persona-management`](./persona-management/spec.md)：读取、更新、同步与激活 Persona，并在切换失败时保持原主体。
- [`persona-profile-subject-and-visibility`](./persona-profile-subject-and-visibility/spec.md)：外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段。
- [`social-graph-read`](./social-graph-read/spec.md)：分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。

## 3. 端云与数据流

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

以下决定约束 authoring 与实现，不是实现完成或运行准出证据；具体字段、operation、错误码、metric ID 与存储 schema 仍由各 owning User contracts 声明。尚缺的合同和真实证据见三个最低 Story 的 OPEN，不以本设计替代 contract gate。

<a id="dec-001"></a>
### DEC-001 账号认证与 Persona 公开身份、关系网络分离

- 决策：账号认证与 Persona 公开身份、关系网络分离。UserAccount 拥有凭据绑定及创建恢复入口，Persona 拥有自身资料/生命周期，PersonaRelationship 拥有 Pair 命令与关系事实；公开读取不展示 owner 映射。
- 理由：允许一个账号管理多分身而不让下游动作、公开关系或计数串号。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约；以 owner 代替未就绪 Persona；把 Creator release 投影当可登录用户。
- 约束与影响：跨对象只经 typed public port、named reader 或事件协作；账号、Persona、关系的事务边界不因处于同一部署进程而合并成跨私有 store 写入。
- 失败恢复与回滚：主体未就绪或当前身份核验不可用时拒绝新动作，恢复原主体上下文；回滚不重绑历史归因、不复活已退役身份。已提交结果按 DEC-003/005 读取，不由响应异常反推未提交。
- 观测与 SLO：跨 owner/Persona 误归属、未授权主体接纳的容忍量为零；操作可用性与失败类别按第 6 节分别观测，不以拒绝动作伪造成功率。
- 测试 seam：真实 Persona 管理 command/summary 与 relationship actor reader 组合，双 owner 同请求和切分身反例检验 owner 不泄露、旧主体不接纳；本地策略不替代真实端云归属证据。
- 关联要求：[L2 REQ-001](./spec.md#req-001)、[L2 REQ-005](./spec.md#req-005)。
- 影响 Story：[`follow-relationship`](./follow-relationship/spec.md)、[`persona-context-propagation`](./persona-context-propagation/spec.md)、[`persona-management`](./persona-management/spec.md)、[`persona-profile-subject-and-visibility`](./persona-profile-subject-and-visibility/spec.md)、[`social-graph-read`](./social-graph-read/spec.md)。
- 关联验收：[SIT-001](./spec.md#sit-001)、[关注 GWT-001](./follow-relationship/spec.md#gwt-001)、[管理 GWT-006](./persona-management/spec.md#gwt-006)、[图读取 GWT-004](./social-graph-read/spec.md#gwt-004)。

<a id="dec-002"></a>
### DEC-002 User 唯一 typed 目标解析保留 Creator 身份且仅授予 target 资格

- 决策：PersonaRelationship 经 User owning `RelationshipTargetResolver` 公共 port 获取唯一 typed 目标证明。普通 Persona 走不可变身份 reader，Creator 经 `creator_runtime_profile` named reader 验证 canonical author/persona 映射和 Content 当前 active tuple 的 exact release fence；service composition 组合端口，不跨读其他 owner 私有库。
- 决策：Pair 输入保留已发布身份原字节；目标种类/namespace 来自 resolver 证明，不新增前缀重算 Pair。跨类型同字节映射冲突即拒绝准入。Creator 只作 target，不能拿来构造 active actor、登录 Persona、回关、Greeting 或 Chat 权限。
- 理由：普通 Persona 格式校验不能代表 Creator 资格，而字段名或可展示昵称也不能证明可写身份；统一资格解析才能让主页、列表和关注命令一致。
- 被否决方案：路由 handle fallback、昵称 hash、创建伪登录 Persona、转用 SubjectFollow、普通 Persona/Creator 随机择一、关闭全部 Creator 关注入口。
- 约束与影响：目标引用与公开 proof 的 exact shape 归 PersonaRelationship/Creator contracts。查询和 unset 仍校验身份与二元组，但合法已有关系的清理不要求目标重新获得新增关注资格。当前 release 移除只改变展示资格，永久撤销由 owning lifecycle 驱动抑制及有界清理。
- 失败恢复与回滚：过期 fence、缺失映射或依赖故障明确拒绝新关注；由当前 owner 重新解析后才建立新意图，不能刷新原命令期限。回滚保留 canonical 身份与已提交关系，不从旧 release 回填可见性，不宣称跨 owner 撤权具有全局原子事务。
- 观测与 SLO：错误 target/actor 接纳及跨 namespace 串边容忍量为零；resolver 延迟纳入关系命令 P95 500ms/P99 1000ms 目标，统计缺映射、旧 fence 与依赖失败的脱敏分类，不记录 bearer 或 owner 映射。
- 测试 seam：扩展 `quwoquan_service/services/user-service/tests/local_contract/account/user_account/creator_release_public_identity__contract__local_contract_test.go` 的普通/Creator/歧义矩阵；以真实 User resolver、受管 Creator release 和 PG 在 `tests/api_integration/relationship/persona_relationship/` 证明 Follow→Get→Unfollow 正向及旧 fence 拒绝，nil reader 的存储专项不能证明目标资格。
- 关联要求：[关注 REQ-007](./follow-relationship/spec.md#req-007)；影响 Story：[关注关系](./follow-relationship/spec.md)、[社交图谱读取](./social-graph-read/spec.md)；关联验收：[关注 GWT-005](./follow-relationship/spec.md#gwt-005)、[图读取 GWT-003](./social-graph-read/spec.md#gwt-003)。

<a id="dec-003"></a>
### DEC-003 安全分配、owner 回执与持久创建步骤共同保证真实身份返回

- 决策：保留现役共享 ULID generator 与 User identity 封装；ULID 为 48-bit 毫秒时间加 80-bit `crypto/rand.Reader` 熵，生成要求 `0 ≤ UnixMilli ≤ 2^48−1`，26 字符 body 首字符只能 0～7。共享大写编码与 User 小写封装分别验证，不拿共享校验器验证完整 Persona ID；origin/shard 不计入随机熵，时间位不代表业务提交顺序。
- 决策：保留生产合法身份中的固定 `_01_` 字节，不按存在漂移的格式描述删除它。收紧前审计存量，以独立解码向量验证编码边界；不重算已发布 ID。路由必须让相同候选进入同一唯一性裁决边界，多库迁移不得双主接纳相同身份。
- 决策：新 ID/系统用户号仅在尚未提交且精确命中自身唯一约束时回滚该失败事务，使用新安全熵最多再生成 3 次（不含首次候选）；耗尽即停止。随机源异常直接失败，凭据/手机号、quota、receipt 或其他唯一冲突保持各自失败，不以模糊数据库错误重试。保留原创建意图，不因换候选换幂等键。
- 决策：Persona 创建回执以 verified owner、operation 与命令键隔离并校验摘要及对象归属；先读原回执，再分配候选。重放返回回执对应真实 Persona/冻结结果，不返回本次临时候选。Persona 状态、实际名额、receipt 与 outbox 遵守现役 command packet 原子边界。
- 决策：UserAccount 在现役创建/恢复边界持久保存稳定流程身份、credential/owner 绑定、已选 Account/Persona 身份及步骤结果；优先复用已有流程记录。Account 与 Persona 各守自身事务，通过公开创建 port 续跑，恢复记录不复制 profile/credential，不建设通用 saga 平台。
- 理由：随机低碰撞概率不证明正确归属；已提交回放和部分提交需要持久命令身份才能避免返回错误候选或重建账号。
- 被否决方案：弱随机/昵称 hash fallback、对重复 ID 再做 SHA、整链重新注册、未知提交时重选候选、全局未分 owner 的 receipt、升级 UUID/Snowflake 与存量并轨。
- 失败恢复与回滚：Account 已提交则只恢复 Persona 步骤；commit unknown 先查流程/receipt，不补偿删除 Account，不重用已发布 ID。回滚继续识别已建立流程与回执，新约束先审计再新增迁移，不改已执行迁移或回退数据库快照丢新身份。
- 观测与 SLO：跨 owner 回执和返回未落库身份容忍量为零；碰撞次数、精确约束类别、熵故障、恢复步骤年龄、未决恢复次数可观测，熵故障/耗尽触发告警。创建正常请求沿用 canonical P95 1500ms/可用性 99.9% 目标，重试受该请求预算约束；中断恢复在重新可用后的下一次受信请求中继续，后台/离线不计为已恢复。
- 测试 seam：`quwoquan_service/runtime/id/generator__local_contract_test.go` 注入 clock/entropy 并与独立解码交叉验证；User 分配 port 精确注入约束故障；扩展 `tests/api_integration/account/user_account/persona_command_packet__api_integration_test.go` 比较两次响应 ID、owner、receipt、真实行和 outbox，并在 Account 提交后/Persona 提交后丢响应处设屏障证明持久续跑。真实管理旅程重启验证同一 Persona，不拿 UAT happy path 证明编码。
- 关联要求：[管理 REQ-006](./persona-management/spec.md#req-006) 至 [REQ-008](./persona-management/spec.md#req-008)；影响 Story：[Persona 管理](./persona-management/spec.md)；关联验收：[GWT-001](./persona-management/spec.md#gwt-001)、[GWT-004](./persona-management/spec.md#gwt-004)、[GWT-005](./persona-management/spec.md#gwt-005)、[GWT-006](./persona-management/spec.md#gwt-006)。

<a id="dec-004"></a>
### DEC-004 SHA-256 Pair 身份不变，所有新命令含 no-op 参与同一版本仲裁

- 决策：业务身份是规范不可变二元组，技术身份继续为 `hex(SHA256(lower + NUL + upper))`。排序采用 canonical ID 原字节的确定性比较；Go 字节顺序与 PostgreSQL 明确 collation 的比较等价，不依赖默认 locale，不转小写重解释既有身份。
- 决策：保留 Pair 主键和二元组唯一性，数据库约束下界小于上界、摘要格式/长度以及 Direction 两端正好属于该 Pair、每方向唯一且至多两行；方向的状态与时间约束一致。任何按摘要命中的查询、锁、unset、receipt 或投影入口核验原二元组，摘要不是授权凭证，完整性失败不变更状态或产生成功 receipt/event。
- 决策：不存在态为 version 0；首次无边 Unfollow 可惰性建立规范 Pair 以保留现役 receipt 引用约束。通过权限/前置版本的新命令在 Pair 行锁内推进 version 一次，即使业务值未变；原 key 重放不推进。no-op 写 receipt 但不发业务变化事件、不动 quota/贡献，业务事件版本允许跳号。
- 决策：一次 PG 事务提交 Pair、Direction、需要变更的 quota、receipt 和实际 outbox 事件。响应直接来自冻结回执，不后置查询拼结果。向下游传递因果要求时，receipt 引用当前状态最近的实际业务事件；首次空态无事件则返回可证明空态，不让 consumer 等待未发布的 no-op 版本。双向共享一个 Pair version，反向关注引起保守冲突；不新增 directionRevision。读取优先单 SQL 一致快照，多 SQL 必须用 `REPEATABLE READ READ ONLY` 或等价方案，单独 READ ONLY 不足。
- 理由：只在创建时相信 hash 主键无法防其他入口串边，no-op 没有真实写栅栏会允许旧离线写越过新决定；同一版本避免平行真相。
- 被否决方案：缩短/更换 SHA、全量预创建 Pair、只在值变化时推进版本、读旧快照后不写的伪 CAS、客户端墙钟 LWW、冲突自动换版本重发、以 missing version 推断丢业务事件。
- 失败恢复与回滚：业务前置冲突只读当前事实并给用户恢复入口；DB 瞬态事务失败可在同 key/deadline 内有界重试，完整性异常隔离并告警。回滚不得重置 Pair version 或清除防旧写状态；旧 consumer 必须先承接完整后态/版本跳号才接入新 writer。
- 观测与 SLO：串边、第三端点、重复 effect、混合快照容忍量为零；no-op/重放/冲突、Pair 锁等待与事务回滚分别观测，关系命令 P95 500ms/P99 1000ms、点查 P95 300ms/P99 600ms 为目标。
- 测试 seam：现役 Pair domain 摘要 seam 注入碰撞；`tests/local_contract/account/user_account/persona_relationship_pair__canonical_identity__contract__local_contract_test.go` 固定字节向量；`tests/api_integration/relationship/persona_relationship/postgres_relationship__api_integration_test.go` 在真实 PG 测约束、旧写→新 no-op→旧写及双向竞争、同快照读取，私有 corruption fixture 仅用于完整性专项。
- 关联要求：[关注 REQ-008](./follow-relationship/spec.md#req-008)；影响 Story：[关注关系](./follow-relationship/spec.md)、[社交图谱读取](./social-graph-read/spec.md)；关联验收：[关注 GWT-005](./follow-relationship/spec.md#gwt-005)、[GWT-006](./follow-relationship/spec.md#gwt-006)、[图读取 GWT-004](./social-graph-read/spec.md#gwt-004)。

<a id="dec-005"></a>
### DEC-005 签名写依据只证明来源与期限，原写和到期终结竞争同一 receipt

- 决策：actor-scoped query 签发轻量 mutation basis，语义绑定 canonical 目标及 namespace、verified 主体、允许操作范围、前置版本和服务端发行/接收期限，默认最长 72 小时；GET 不落业务状态。已有依据按页面总 bytes 与批量预算附着，点击不必每次预读；具体字段名与签名封装只归 PersonaRelationship contracts，User 主体词汇不照搬 Content actor 字段。
- 决策：采用受管独立用途签名 key 与 domain separation，不复用原始 access-token 密钥；验签 key 覆盖最大合法写窗口及规定验证余量。basis 不是一次性业务令牌，同一依据可用于不同新意图但仍按 Pair CAS 裁决；完整性签名不能代替最新授权、可见性、lifecycle 和 quota。
- 决策：verified Persona 与 command key 构成 receipt 仲裁身份；摘要绑定操作、目标、desired、依据及不可变期限。传输幂等来源由 canonical 边界唯一映射，header/body 不一致、坏 JSON/未知字段/关键值缺失在写前失败，不允许空 key 跳过 receipt。
- 决策：PG 原写和恢复终结取得同一命令 advisory/row lock 并竞争唯一 receipt。先核验身份/请求完整性并查原回执；无回执时，原写在锁内判定新接纳期限，终结在同一裁决中读取已提交结果或保存不可再执行的到期结果。正常写还遵守 DEC-006 锁序；终结不得持 receipt 锁后反向获取 policy/Pair 锁。
- 决策：回执默认保留至少 96 小时，且不早于接收窗口结束加恢复余量及自身保存下限；物理清理后，旧 basis 仍不能接纳。截止前取得仲裁并接纳的事务可晚提交，终结必须等待其提交/回滚；先过期终结则原写不能执行。响应终态、历史不可判定与查询当前状态由 canonical contracts 分开，不靠 bool 造历史结论。
- 理由：有限 TTL 不是永久幂等，客户端计时器不能证明服务事务没提交；同一 receipt 争用提供可验的线性化点。
- 被否决方案：重试换 key/延长期限、客户端自报有效期、只用 JWT 是否有效判断原命令、查询 bool 后伪终结、另建独立终结账本、仅延长 TTL 代替事务仲裁。
- 失败恢复与回滚：超时/连接中断保留 unknown；权威恢复后原 key 查回执，期限内才允许原写重试。旧回执已不可得则显示历史未可判定并读取当前事实，新决定用新 key；无网不伪终态。内部生命周期清理由 verified event 和成员/被清理版本绑定授权，不开放普通 HTTP 跳过鉴权，也不受 App 72 小时窗口截断。
- 观测与 SLO：重复终态、过期请求执行和由 bool 伪造 committed 容忍量为零；统计签发/验签延迟及 bytes、unknown 年龄、到期竞争、receipt 丢失/保留余量、密钥轮换拒绝。在线恢复请求沿用关系 deadline，锁等待有界且超时仍是未决，不以高可用目标强行返回终态。
- 测试 seam：真实 Remote/header factory→HTTP→PG receipt 贯通；本地注入 clock/signature verifier 测篡改与续期拒绝，真实 PG 在接纳前、已持命令锁、commit 后断响应三处屏障并发 expire-finalize；实际删除过期 receipt 后重放旧 basis，核验同一命令仅一个终态。该真实引擎 proof 未通过不得接入新发送协议。
- 关联要求：[关注 REQ-009](./follow-relationship/spec.md#req-009)；影响 Story：[关注关系](./follow-relationship/spec.md)；关联验收：[GWT-006](./follow-relationship/spec.md#gwt-006)、[GWT-007](./follow-relationship/spec.md#gwt-007)。

<a id="dec-006"></a>
### DEC-006 系统 policy 激活共享锁与 source 精确 quota 同事务裁决

- 决策：主动关注上限是 User 系统配置，初始 1000、升档 10000；配置发布物化为 User owning policy activation 的生效 revision/limit/digest 提交快照，不形成第二 authoring。关系命令只用激活快照，不能由各副本内存旧配置或 Redis 覆盖。
- 决策：锁序固定为 policy activation 共享锁→幂等键→单 Pair→所有需要变更的 source quota 按 canonical ID 排序。配置激活持 policy 排他锁，等待旧共享锁事务结束后原子切换；激活失败保留旧策略，不提前宣称生效。事务不得反向取得另一 Pair；policy 共享锁不逐命令更新全局热点。
- 决策：source 精确已占用人数与边在同一 PG 事务中条件变更，名额只在 false→true 占用、true→false 释放；Block 清双向时按排序同时释放真实 source 名额。被动接收关注不锁 target 的 quota 或 profile。quota 惰性创建，存量初始化/回填受同一锁边界协调，不每命令 COUNT 全出边。
- 理由：单 Pair 串行不能保证同 source 跨 Pair 限额；异步公开数字不适合写授权。激活锁把“策略已生效”与在途旧事务的提交顺序绑定。
- 被否决方案：App 串行当并发保证、静态 DDL 限额、公开计数当 quota、内存多副本最终一致配置裁决、缓存失败无限制、预占名额 saga、无共置证明的分布式配额。
- 失败恢复与回滚：quota 拒绝不重试为新意图、不写成功事件；瞬态死锁/回滚仅同 key 有界重试。上调不重建身份，下调保留超额已有边并禁止新增；回滚配置也必须走激活排他边界，不回滚业务表。跨数据库分片需另行共置/协调证明，本设计不授权。
- 观测与 SLO：超额接纳、负 quota、authority 与 quota 不一致容忍量为零；观测激活等待/失败、生效摘要、Pair/source 锁等待、死锁、拒绝原因及对账差异，命令遵循 P95 500ms/P99 1000ms 目标。激活只有事务完成后计成功，超请求预算返回未完成而非新策略生效。
- 测试 seam：local 参数化 N=3/1000/10000；真实 PG 在 N−1 时并发 20 个不同目标仅一个新增成功，屏障挂起旧策略共享锁事务与降额激活，断言排他激活等待、完成后不得旧政策新接纳；Block/回放/事务失败核对 quota、边与 outbox，另测多 source 关注同 target 不触达其 profile/quota 锁。
- 关联要求：[关注 REQ-010](./follow-relationship/spec.md#req-010)；影响 Story：[关注关系](./follow-relationship/spec.md)；关联验收：[GWT-007](./follow-relationship/spec.md#gwt-007)。

<a id="dec-007"></a>
### DEC-007 单份 Direction 双向具名读取，批量组合与受保护图内搜索

- 决策：保留一份 PG 权威 Direction，source/target 两个 named reader 使用有效关注条件的 partial covering indexes，seek 按对应端点、`followedAt DESC`、`pairId DESC`；block 用独立索引。先以真实 explain 决定是否需要可重建物化边投影，不复制两份全关系写真相。
- 决策：资料与边分离，每页最多一次边读取，加三类批量依赖：公开资料（普通 Persona/Creator 各一个 reader，最多两次）、viewer 关系/安全快照一次、需要完整能力时 Greeting/Conversation 批量组合一次。故现役两种资料来源上界为一次边查询加四次批量依赖，20/100 项不增加调用次数；下游组合自身也不得逐 item N+1。Feed 轻量按钮不调用完整会话能力。
- 决策：opaque cursor 绑定 owner 公开主体、方向、query 摘要、viewer 安全 scope 与最后扫描位置并作完整性保护；扫描预算耗尽可返回短/空页及 next cursor，不把依赖失败吞为过滤。动态列表保证稳定 seek 与未变化遍历去重，不承诺任意并发取关/再关注的全局快照。
- 决策：仅在已获授权图范围提供现役昵称/公开句柄子串搜索，以规范公开资料的专用搜索索引与边 membership 做数据库索引交集/半连接。搜索与空查询分别有扫描预算和 deadline；无匹配不等于预算耗尽。现役 `object.yaml.search_policy` 的仅本地声明须先按此授权范围收敛，不能仅增加请求参数就绕过。
- 理由：千万入边不能逐条读头像、检查 block 或循环补页；索引与批量边界才能让成本受页/预算控制而不是随度数增长。
- 被否决方案：头像/昵称复制到每条粉丝边、B-tree 声称子串检索、高度数全部读入内存、limit 冒充 scan bound、坏 reader 当 not-found 跳过、匿名远端枚举全部关系。
- 失败恢复与回滚：安全 reader 失败拒绝相关结果，不泄露 block 原因；合法部分失败不清其他成功区块。索引或投影更换先一致快照对账、接续安全水位，再切唯一 reader；旧 cursor 失配明确重新刷新，不能续旧 cursor 偷换语义。
- 观测与 SLO：普通分页 P95 500ms/P99 1000ms，点查 P95 300ms/P99 600ms；搜索目标 deadline 不超过现役请求 1500ms，具体扫描上限由 owning 配置与容量画像冻结。观测 keys/rows examined、各 batch 次数、权限拒绝、空页续接、搜索无结果/预算失败及总耗时；未批准峰值和千万级 explain 前不声称容量满足。
- 测试 seam：`tests/api_integration/relationship/persona_relationship/postgres_relationship__api_integration_test.go` 的真实索引/seek 与 production batch ports 计数，20/100 行相同调用上界；用完整 viewer/方向/query 游标矩阵、同时间戳边及安全依赖故障验证拒绝/短页，授权私有容量库证明千级/万级/千万图无结果搜索成本。
- 关联要求：[图读取 REQ-005](./social-graph-read/spec.md#req-005)；影响 Story：[社交图谱读取](./social-graph-read/spec.md)；关联验收：[GWT-002](./social-graph-read/spec.md#gwt-002)、[GWT-003](./social-graph-read/spec.md#gwt-003)。

<a id="dec-008"></a>
### DEC-008 User 拥有 Persona 贡献统计，投影与公开资料写入分离

- 决策：关系公开计数按 Persona 而非 owner 归集；本人点赞作品与作品获赞分开消费 Content owning 事实，不让 User 冒充 ContentReaction writer。公开资料不再读取 owner 合计作为单 Persona 计数；typed 统计读面及公开披露口径只由 User owning contracts 声明。
- 决策：每成员保存已应用版本及当前贡献，与固定 bucket 的新旧贡献差额同事务提交；重复/旧事件不再累加，同版本不同摘要拒绝。Pair 事件须有两个方向完整后态，允许 no-op 造成版本跳号；运输 sequence/checkpoint 与聚合版本分开。固定惰性分桶及频率受限 rollup 避免每事件写热门 Persona 资料单行，不在事件或读请求中全量 COUNT。
- 决策：User outbox 发布、计数与其他投影以独立消费者/checkpoint 隔离故障；固定分区毒事件停住该分区连续 applied 水位并保留原事件，其他分区继续。lease/fencing 约束 sink effect 与 checkpoint，不只在 worker 启动校验；重算固定源快照/generation 和安全分区水位，接续增量追平后切换单一统计 reader。
- 理由：owner 计数会串分身，纯 delta 重放和重算不对齐会漂移；逐事件更新热门资料造成热点和资料版本污染。
- 被否决方案：以公开统计作为 quota、`GREATEST(0,...)` 掩盖错误、重算 COUNT 后再次叠加已含增量、跳过毒事件取最大水位、投影失败让已提交关系返回未提交、每次统计变化更新公开资料编辑时间。
- 失败恢复与回滚：统计不可用只降级统计区块，命令由 receipt 确认；撤销/关闭先保留不可逆来源事实，再有界清理，旧事件不能复活。重建从 authority/安全快照与增量恢复，来源缺失或对账未过保持未就绪，不返回零。回滚保留贡献、墓碑与已提交增量，不能恢复旧快照丢新事实。
- 观测与 SLO：重复 effect、跨 Persona 计数、负贡献和同版本异摘要容忍量为零；观测投影 lag、连续 checkpoint、最老积压、重算差异、rollup 频率及恢复排空率。前台可见 commit→render P99 5 秒为端到端目标，投影 2 秒只是预算；无新事件以处理水位/健康进度判 lag，不只看旧 occurredAt。
- 测试 seam：现役 counter projector/reconciler public seam 注入乱序、合法跳号、双向 Block 与重算屏障；真实 PG 和 production 后台 worker 自动投递，按两个同 owner Persona 的边/贡献/bucket/rollup oracle 比较，失租约旧 worker 和毒分区不能推进应用水位，手动 drain 仅证明局部算法。
- 关联要求：[图读取 REQ-006](./social-graph-read/spec.md#req-006)；影响 Story：[社交图谱读取](./social-graph-read/spec.md)；关联验收：[GWT-004](./social-graph-read/spec.md#gwt-004)。

<a id="dec-009"></a>
### DEC-009 普通 Redis 缓存同任期 CAS，failover 只承诺源期限内有界陈旧

- 决策：公开 Persona/Creator 资料、统计与有限候选热页分别缓存，私有 viewer 关系不进入共享值。namespace 绑定环境、owner/object 及必要 exact release；公开资料仍按当前安全策略过滤。现役 owner-private ProfileCache 不等于已接通公开 Persona 读缓存。
- 决策：cache miss 先取不复用 generation，再读源；同 Redis hash slot 内用 Lua/等价原子操作比较 generation 与源版本并 SET。失效与填充竞争同一权威代际；缺失/eviction 重建新 token，不重用固定 0，禁止 GET 比较后独立 SET 的 TOCTOU。资料版本与统计版本不跨族比较。
- 决策：同任期防迟到填充不延伸为跨 failover 全局 fencing。填充和 value 保留源 readStartedAt、source asOf 与不可续长的 absoluteExpiresAt；读和写均复核硬期限，App 继承源期限。旧副本提升即使带回旧 generation/value，也最多在原期限内陈旧，重新 SET 不续鲜；新读取同时受源投影/副本 lag 与受管时钟偏差预算限制。
- 决策：权限、quota、结果恢复、minVersion/读己之写绕过普通缓存。元数据/连接故障和已知切主期间 bypass 并限制 DB 回源，超过源期限或不能证明安全即不可用；不为普通缓存增建外部 durable 全局 epoch。需跨 failover 绝不接受旧代际的消费方须另作 authority fencing 决策，不能偷用本合同。
- 决策：DB state/receipt/outbox 提交后返回 frozen result，关系事件使候选页失效，统计投影真正提交后才失效统计缓存。初始配置目标：统计驻留 1 秒、候选页 2 秒、资料软期 60 秒/硬期 5 分钟、仅权威证明的负缓存不超过 1 秒；抖动计入总预算，不从缓存写入时间重置源寿命。
- 理由：异步失效不能消灭 DB→Redis 窗口，Lua 不能抵抗复制回退；不可续期源期限为普通读提供可测陈旧上限，安全与确认靠 authority。
- 被否决方案：无条件 SET、随机 generation 当跨切主证明、清库测试代替落后副本提升、TTL 用于 block 放行、网络失败缓存为 false/0/空页、重复填充刷新陈旧寿命、缓存持有唯一恢复凭据。
- 失败恢复与回滚：singleflight、批量上限、hot-page/key/bytes/LRU、回源 bulkhead 与 deadline 限制雪崩；缓存全失效可从 authority 重建，失败不改报已确认命令。回滚不复用旧 generation 覆盖新水位，不复活墓碑，只有追齐当前来源的单一 reader 可接回。
- 观测与 SLO：观测真实命中/DB 放大、旧填充拒绝、失效 lag、projection lag、bypass/eviction/bytes 与源绝对年龄；公开可见统计 P99 5 秒需同事实端到端实测，2 秒投影+1 秒服务 cache+2 秒 App 仅为预算。硬期限后成功提供旧值、安全读消费普通陈旧值容忍量为零。
- 测试 seam：真实 Redis Cluster 同 slot 失效/SET 屏障及 DB 调用计数；阻断复制、g1→g2 后提升仍持 g1 的副本，再释放旧填充并推进时钟，断言原期限不被续长、权威读仍新。App 可控 hydrate/epoch 测旧响应隔离；redis clear 或 fake cache 不能代替真实 failover。
- 关联要求：[图读取 REQ-007](./social-graph-read/spec.md#req-007)；影响 Story：[社交图谱读取](./social-graph-read/spec.md)；关联验收：[GWT-005](./social-graph-read/spec.md#gwt-005)。

<a id="dec-010"></a>
### DEC-010 App 关注待确认与领域事实分离，复用持久意图而非第二 writer

- 决策：沿用现役 actor partition/outbox engine，关系 coordinator 拥有 confirmed、未决发送与最终尚未发送 desired；所有人物入口复用它，runtime 只调度。分区含环境及实际 account/persona/device 上下文，verified Persona 才能写人物关系；Creator 无 actor 分区。
- 决策：同 actor+target 单飞，跨 target 有界并发；已发送 envelope 的 key/basis/desired 不可改，反转只合并未发送部分。持久接纳等待串行存储成功，hydrate 按对象 revision/tombstone 合并，切分身冻结旧发送且迟到回调只回原分区；未决意图不因 LRU 或正文缓存淘汰丢失。
- 决策：点击只改变待确认视觉，不改变 confirmed bool；真实对应 receipt 结束命令 pending，统计是否追齐独立。mutation epoch 同时防旧网络读与磁盘 hydrate 回填，query/receipt 校验主体、目标、请求 generation 与同族版本。capability 保留单一 canonical 动作矩阵，关系、可见性、Greeting/Conversation 各自版本/有效性不能用一个 Pair version 伪装；pending 永不扩大权限。
- 理由：本地成功旁路、Future<void> 丢回执与跨页旧布尔回填会让用户把未决当成功；复用现役持久队列可保留恢复而不造万能 Repository。
- 被否决方案：乐观改关注最终态、每页面直接 writer、超时立即回滚并重发新 key、一处 hydrate 变化丢整个磁盘快照、切账号搬移旧意图、以 capability 旧 bool 覆盖新 receipt。
- 失败恢复与回滚：scope/权限/quota 失败按 canonical 终态停止，网络 unknown 按 DEC-005 恢复；队列条数/bytes/最大年龄有界，满时拒绝新接纳而非丢旧意图。网络/前台恢复由唯一生命周期协调器唤醒且不绕退避；旧无稳定 key/basis 的 outbox 在协议迁移时不能臆造身份自动重写。
- 观测与 SLO：pending 反馈 P95 100ms、云确认总耗时、unknown 年龄/队列容量、迟到响应拒绝和各入口 source 分开记录；前台可见关系 commit→render P99 5 秒目标，进入/恢复/动作后一次合并 batch，持续驻留刷新仅在总 QPS 预算证明后开放，禁止逐控件 timer。
- 测试 seam：`quwoquan_app/test/local_contract/runtime/transport/state_sync/client_state_sync_outbox__local_contract_test.dart` 的 Completer/存储故障，`test/local_contract/service/user_service/relationship/persona_relationship/` 的真实 provider/descriptor/header factory 与 coordinator；production Remote 提交后丢响应，`test/user_acceptance/journeys/profile/profile_journey__user_acceptance_test.dart` 扩双设备全入口和真实 Creator，关联 receipt/读回，不能只断言控件文本。
- 关联要求：[关注 REQ-011](./follow-relationship/spec.md#req-011)、[图读取 REQ-007](./social-graph-read/spec.md#req-007)；影响 Story：[关注关系](./follow-relationship/spec.md)、[社交图谱读取](./social-graph-read/spec.md)；关联验收：[关注 GWT-007](./follow-relationship/spec.md#gwt-007)、[图读取 GWT-005](./social-graph-read/spec.md#gwt-005)。

## 5. 失败与恢复

- 未接纳的身份/权限/配额/前置冲突返回各 owner 的 canonical failure，不写成功事实；已经提交而响应、统计或网络失败属于传递/读取问题，不能改报业务未提交。unknown 的唯一历史裁决见 DEC-005，当前态查询不替代 receipt。
- Pair 内权威原子性与跨 owner 最终一致性分列：隐私/撤权由当前 owning authority 立即拒绝公开访问，可能交错提交的内部关系由版本化撤权事实及有界清理收敛。已发送客户端内容不可追溯撤回，不承诺跨服务全局线性撤销。
- PG durable ACK 和故障切换需批准同步复制/刷盘及旧主 fencing 证据才能声称单节点故障 confirmed RPO=0；可用性不优先于“不串身份、不超额、不重复、不伪确认”。权威故障拒绝新确认，可选缓存/统计故障只降级其读面。
- 迁移先审计合法身份、tuple/Direction 和 receipt，新增迁移而不重写已执行迁移。quota/贡献回填绑定一致快照与连续安全水位；shadow generation 只作离线对账，追齐后切换唯一 reader，不形成线上双写/双读。
- 端云协议按同候选统一升级；不支持新依据/版本合同的旧客户端由 canonical 最低版本准入明确升级或拒绝受影响命令，不缺字段时 fallback 旧语义。回滚版本组合必须识别已提交 receipt、单调版本、未决意图与 tombstone，不能回退数据库快照丢新写。
- 失败门禁、未冻结合同、恢复 proof 或资源缺失均指回最低 Story OPEN，保持对应能力准出阻断；不得以 Mock、旧 wire、测试旁路或 warn-only 隐藏。

## 6. 质量与观测

- 以上时延、新鲜度与容量均为 target，不是 measured。operation 可用性沿用 owning contract 的 99.9% 目标，同时单列用户意图获得 durable 确认率、完整读取率、合理拒绝、全部 attempt（含超时/过载/重试）与最终收敛率。
- 容量画像需 owning 配置/SLO authoring 冻结业务峰值、资源、引擎版本、总边数、热点比例、批量/扫描预算与压测时长；验证 1000/10000 出边、千万入边和冷缓存/切主/恢复，不把可配置上限当性能证据。无批准画像只可报告安全容量曲线，不宣称满足未知峰值。
- 单节点故障恢复 RTO 目标不超过 60 秒，需真实批准拓扑与负载校准；缓存冷恢复、消费者追赶与备份灾备分别测量。正确性 history oracle 按 Pair/receipt/source quota 的声明串行历史判定，跨 owner 只验版本化收敛，不造全局事务历史。
- 命令、receipt、事实和 readback 的脱敏关联可追踪，metric/trace 名称与告警规则归 owning operations/observability；不记录签名密钥、原始 basis、凭据、手机号或可推导 owner 多分身映射。完整性/越权/超额/重复 effect 告警不可被重试成功覆盖。
- local_contract 只证明算法和调用纪律；真实 PG/Redis、自动 worker、迁移/回滚与容量属于 api_integration/环境证据；user_acceptance 必须同候选 Android+iPhone 物理设备并有 receipt/readback。规格和 codegen 通过不替代后续层，未运行或 skipped 不计通过。
