# L2 Design：设置、设备与账号安全 (`settings-and-device-token`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证，”需要 `account-lifecycle-self-service-account-closure`、`account-suspension-and-appeal-lifecycle`、`appearance-accessibility-settings`、`device-token-register`、`notification-privacy-settings`、`settings-audit` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`account-lifecycle-self-service-account-closure`](./account-lifecycle-self-service-account-closure/spec.md)：真实事务存储证明状态、receipt 与 outbox 同提交，并发提交只产生一个终态事实。
- [`account-suspension-and-appeal-lifecycle`](./account-suspension-and-appeal-lifecycle/spec.md)：真实存储事务证明状态、epoch、session revoke 与 outbox 同提交，且没有 PII/审核证据进入事件。
- [`appearance-accessibility-settings`](./appearance-accessibility-settings/spec.md)：必须挂在 `settings-and-device-token` 下，以 metadata / API / audit 为真相源，禁止做成仅本地存储能力。
- [`device-token-register`](./device-token-register/spec.md)：定义“设备 Token 登记”的可观察主路径、失败语义及父能力交接。
- [`notification-privacy-settings`](./notification-privacy-settings/spec.md)：定义“通知隐私设置”的可观察主路径、失败语义及父能力交接。
- [`settings-audit`](./settings-audit/spec.md)：定义“设置审计”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 设置命令与设备令牌写入各自 owner 并返回结构化终态
- 决策：设置命令与设备令牌写入各自 owner 并返回结构化终态。
- 理由：为已登录账号提供可真实读写的通知、隐私、通话、外观设置，管理设备推送端点与登录凭证。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`account-lifecycle-self-service-account-closure`](./account-lifecycle-self-service-account-closure/spec.md)、[`account-suspension-and-appeal-lifecycle`](./account-suspension-and-appeal-lifecycle/spec.md)、[`appearance-accessibility-settings`](./appearance-accessibility-settings/spec.md)、[`device-token-register`](./device-token-register/spec.md)、[`notification-privacy-settings`](./notification-privacy-settings/spec.md)、[`settings-audit`](./settings-audit/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 UserAccount 是所有终端用户请求的同步安全权威
- 决策：资源服务只在 `JWT` 验签成功后调用 `UserAccount` service-principal internal operation。
- 权威返回：该 operation 只返回 `accountState` 与 `authEpoch`，响应 `Cache-Control: no-store`，不返回或记录 persona、资料、凭证、设备、case 或原始事件。
- 同步拒绝：资源中间件仅在 active/anonymous 且 token epoch 精确匹配时注入 principal；closed、suspended、not found 和 stale 以 canonical `USER.AUTH.*` 拒绝，任何 authority 依赖失败一律 fail-closed。
- 理由：签名验证只能证明 token 曾被签发，不能证明注销、封禁或 epoch 变更后的当前终态。把用户安全终态放在每个服务的本地 cache、JWT TTL 或异步 consumer 会制造可访问窗口和第二真相源。
- 新动作校验：HTTP 同步校验负责新动作；realtime gateway 的 ticket/upgrade/connection 和 RTC 的 join/renewal 同样调用 authority。
- 既有连接回收：`UserAccountClosed`/`UserSuspended` durable event 负责主动踢除已建立连接、presence、lease、ticket、CallSession 与 media access；事件是回收机制而不是新请求鉴权的替代。
- 可靠性与隐私：authority、outbox relay 和各 consumer 均采用 bounded retry、无 PII terminal DLQ、可恢复 replay 与 readiness。DLQ 只保存不可逆 event/reference/error digest，原 payload 从未 ACK 的 durable source 恢复。Content 对媒体使用引用安全的 revoke/GC work 和 residual probe，不能因为 metadata 已删除就假定 CAS/public slice 已清除。
- 被否决方案：仅缩短 JWT/ticket TTL。
- 被否决方案：仅依赖 UserAccountClosed 异步事件。
- 被否决方案：资源服务缓存 active 快照。
- 被否决方案：authority 不可用时沿用上次成功结果。
- 被否决方案：让 DLQ 保存 account/persona/raw payload。
- 被否决方案：由页面或 App 决定旧 token 是否失效。
- 约束与影响：authority client 必须用受限服务身份、显式 internal origin、短超时、no-store 和无 PII telemetry；生产装配缺少 URL、凭据、timeout 或 health 时 fail-fast。唯一 closed 放行是 canonical CloseAccount 的幂等重放，且由 UserAccount 自身在已确认终态后处理。所有新服务调用只能通过公开 internal contract，不得 import UserAccount infrastructure。
- 关联要求：`REQ-003`、`REQ-004`
- 关联验收：`SIT-003`

<a id="dec-003"></a>
### DEC-003 Content 主体关闭 runtime 证据只由本地工作流 owner 声明
- 决策：`ContentAccountClosureWorkflow` 的 `quwoquan_service/services/content-service/contracts/content/content_account_closure_workflow/fields.yaml` 唯一声明本地 owner 空间创建/闭包证据；Post 的 `account_closure.ownerEvidence` 只引用其 exact 文件摘要，不复制 schema，也不以 Post 安全集合 creation receipt 代证主体闭包。该证据证明当前 Content 物理空间与精确 User 源事件空间、订阅和投影初始化的绑定，不证明全世界 User 没有已关闭主体，不替代 DEC-002 的同步账号权威。
- 创建与恢复：环境 owner 在受管 target 执行锁和停写窗口内，从批准的 candidate/data-plane 资源输入独占创建全部 owner collections 和隔离源事件空间，逐集合读回 Mongo UUID、逐源分区读回初始边界及订阅位置。只有源创建凭证同时证明该源生产者的持久化/outbox 空间属于本次新空间且旧写路已隔离，才允许 `new_source` 的真实初始零水位；新建 Redis stream 本身不证明旧 User outbox 不会回放。复用已有源必须走 `replayed_source`，取得源 owner 完整历史/备份边界并真实重放至冻结边界，所有分区与本地投影逐项追齐且无 PEL/待处理工作；无法证明的 restored 或 Prod 暂时硬拒绝，不能改名为 new。
- 源分配信任：PG/Redis不提供永久不可复用的存储UUID。源证据使用managed allocation binding，可信性来自环境owner在现役target排他锁内独占创建受保护材料、PG专属角色/数据库与Redis专属ACL，并实际读回权限及producer→source配置，验证旧凭据拒绝连接/写入。随机ID、配置摘要、空态、PG system identifier/OID、container ID及mount信息均不能单独授信；这些provider信息只辅助定位。admin/root绕行及由其制造的不可区分拷贝不在本地非生产威胁模型；可观察的权限、凭据、挂载、candidate或current漂移必须拒绝。没有第二回执协议，不双读旧physicalAllocationId字段；Prod/restored未实现时保持拒绝。
- 一致性与拒绝：创建 attempt、资源 namespace、collection UUID、独立主体 HMAC key identity、源生产者创建凭证和订阅边界共同绑定一份 create-once evidence。已有资源、部分创建、未初始化、源恢复未知、错环境/candidate、旧证据复制到新物理空间均不产成功事实；失败保留本 attempt 诊断，不删除或补发 new 证据，不回滚到旧 key/旧源。初始闭包只在首次开放或停写恢复时比对；普通提交后的重启验证当前绑定和物理身份，不拿初始空摘要误判合法增长。
- 理由与被否决方案：空目标集合、最大分区水位、caller 时间/布尔授权、同一个 Post receipt 的两份 hash 都不能证明主体安全完整性。不新增 authority 服务、HTTP command 或业务 collection；受管创建 producer 调用 owner 的创建/readback 端口，Content bootstrap 只消费严格解析及实际身份验证的证据，再绑定现有 PostSafetyAuthority/Manager。
- 质量与测试 seam：沿用账号 consumer lag/DLQ/readiness 与 Post `query_barrier_not_ready`，仅输出脱敏 outcome/attempt 摘要，缺证据立即拒绝开放；不新增无实测 SLO。隔离 Mongo/Redis/源 producer 测试以同一创建函数验证成功和上述负例，另验普通写后重启；只读材料/类型测试不计 HTTP 闭环。
- 关联要求：`REQ-003`、`REQ-004`；关联验收：`SIT-003` 及 `account-lifecycle-self-service-account-closure` 的 `GWT-003`、`GWT-004`；影响 Story：账号关闭、账号封禁恢复与普通 Post 发布。字段及 covered collection 闭集仅归工作流 contracts。
<a id="dec-004"></a>
### DEC-004 Authority 查询委托短期、逐请求重验且不承诺单会话即时撤销

- 决策：细化 [身份 L1 DEC-002](../design.md#dec-002)，两条合集 query 的 grant TTL 为 60 秒且不得超过源 access credential 剩余有效期；不延长现役 query grant 的硬上限。有效期、clock skew 与源 credential 校验只由 canonical authority 合同表达，不由环境猜测或调用方覆写。
- 决策：authority 在签发及每次在线验证时都核对当前 account-persona 归属/存续、账号状态与 authEpoch；closed、suspended、账号或 persona 不存在、归属变化、旧 epoch、过期及权威不可用均 fail-closed。不得缓存 active verdict、复用旧成功快照或只靠 TTL/异步事件表达撤权；owner 每次仍重验资源当前权限。
- 决策：query grant 只允许有效期内同一精确请求的有界重试，不新增 query 单次消费存储，不允许换 operation/resource/body/hash/surface 或转换为 command。每次重试重新验权并受总 deadline 约束；既有 command approval、JTI 单次消费与 Assistant 专属验证不变。
- 决策：当前 logout 撤销 refresh/session 不等于立即撤销全部 access/grant；本能力不承诺单会话 logout 后立即取消在途 grant。若增加该要求，必须另行冻结 session 绑定与在线会话验证的产品/权限范围，不偷偷以账号级全量撤销替代。
- 决策：委托专用 signing secret/reference 仅由 user-service authority 持有，API Edge/content 只申请或调用在线验证；服务间凭据与委托 signing secret 分离。配置合同须声明 key identity、轮换、旧验证材料保留至最长有效期加 clock skew、紧急撤销与加载失败拒绝，密钥值不进源码、测试 fixture、日志或响应。设计决定不构成生成、读取、注入、轮换实际密钥或部署的授权，实际操作必须单独取得明确授权。
- 恢复与回滚：依赖失败返回 canonical 可恢复错误并限制重试，不切匿名、不用旧 grant 成功结果；新链未准出前保持关闭。后续只能回滚受审计签名包/配置并保留受支持 App operation 闭集，不恢复新增 REST、旧 persona scope、双协议或通用 POST 放行。
- SLO/观测：签发、在线验证、owner 调用全部消耗同一请求预算，进入 canonical 成本/owner-call 计划；身份实现前由 contracts 冻结具体 timeout/SLO、typed 错误与低基数 outcome。观测区分签发拒绝、绑定错误、撤权、过期、authority unavailable 与延迟，不把 account/persona、token、原始 payload 或资源标识作为日志/metric label；超时、错误率及 authority readiness 绑定告警与拒绝路径。
- 关联要求/验收：`REQ-004`、`SIT-003`；正向 api_integration 覆盖同请求有界重试，负向 local_contract/api_integration 覆盖 TTL 超限/超源有效期、跨身份、撤权/epoch、改目标重放、authority 故障及零私有读取；必须证明 POST 仅在 exact persisted query 解析与 expectation 完整验证后执行，普通 POST/Mutation 始终拒绝。
- 被否决方案：向 API Edge 授予委托 signing authority、扩展最小 account-security snapshot、依赖缓存 active 结果、把所有 POST 视为 safe-read、伪造 Assistant run/tool tuple，以及把 logout 语义扩大当作无授权实现细节。
- 实施状态：canonical grant source 与身份 owner 的细化验收/OPEN 由后续身份任务先行补齐；本决定不表示签发、撤权、轮换、真实链路或环境证据已经通过，不关闭现有账号安全与合集准出缺口。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 并观测 outbox/consumer/DLQ 指标；封禁旅程额外验证旧 token 拒绝、受限主页不可见、申诉。
- Suspend/Restore 各一次、验证 epoch 拒绝与下游 lag/DLQ 告警。
- authority 观测至少包含固定 outcome 的 allow/closed/suspended/stale/unavailable、延迟和 readiness；不允许用 account、persona、token、request payload 作为 metric label 或日志字段。
