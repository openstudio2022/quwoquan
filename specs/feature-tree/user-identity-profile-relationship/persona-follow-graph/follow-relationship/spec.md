# L3 Story：关注关系 (`follow-relationship`)

> 所属能力：[`persona-follow-graph`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望owner 不能作为默认 follow 主体参与社交关系建立，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “关注关系”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 关注关系

- owner 不能作为默认 follow 主体参与社交关系建立。

<a id="req-002"></a>
### REQ-002 follow / unfollow 的命令主体必须是当前 active persona 或显式选择的 persona

- follow / unfollow 的命令主体必须是当前 active persona 或显式选择的 persona。
- owner 不能作为默认 follow 主体参与社交关系建立。
- follow 边的 `followerId / followeeId` 语义必须统一映射到 `ProfileSubject` 级别，而不是漂移在 owner/user 级别。
- 重复 follow 必须幂等，不得重复计数。
- 对合法主体，unfollow 不存在的边是受命令版本与幂等仲裁保护的安全 no-op，不破坏计数；权限、身份或前置版本不合法时返回 canonical failure。
- 如果 `BlockEdge` 表示任一方向的强屏蔽，follow 写入必须被拒绝或无效化，具体语义由 user 域统一定义。
- follow 写入侧不能绕过 `BlockEdge` 直接落边。
- follow 写入成功与否，不得泄露不应暴露的屏蔽细节。
- 平台审计可追踪 follow 命令与分身主体；普通读接口不得反推出 owner 映射。
- user 域之外不得复制 follow 写入契约。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-004"></a>
### REQ-004 联系人发现到关注写入必须保持对象边界与隐私单轨

- 通讯录发现只允许在端侧完成号码规范化与哈希；原始手机号不得进入联系人发现请求、日志、埋点或结果回执。
- 联系人发现、账号搜索与二维码解析只负责返回候选主体；是否允许关注必须重新读取 `persona_relationship` 的 canonical relationship capability，候选结果不得自行推导写权限。
- 关注写入只能由 active persona 经 user-service production Remote 或 Alpha 对象级本地演练 adapter 发起；在线环境不得走 Alpha adapter。失效二维码、无权限候选、被屏蔽主体或不可见主体不得产生 follow edge。
- 页面切换、权限拒绝、网络失败或 canonical failure 不得清空仍可恢复的搜索条件与候选结果，也不得显示伪成功关系态。

<a id="req-005"></a>
### REQ-005 屏蔽列表读取与解除屏蔽必须以云侧读回为准

- 屏蔽列表必须从 `persona_relationship` 的具名投影分页读取，不得由本地历史关注关系拼装。
- 解除屏蔽只在 typed command 成功且云侧读回不再包含该关系后更新最终 UI；失败时必须保留原列表项和可重试入口。
- 普通用户只能看到产品允许的屏蔽结果，不得从列表、错误或恢复动作推断 owner 映射、对方额外身份或内部治理原因。

<a id="req-006"></a>
### REQ-006 打招呼收发箱与正式会话升级必须保持 User 与 Chat 双 owner 单轨

- canonical `chat.greeting_inbox` 页面必须经 production Remote composition 分别读取收到和发出的 `GreetingRequest`；pending 请求在回复前不得进入普通会话列表，也不得由本地会话或通知记录拼装。
- 收到的请求只允许目标 persona 回复或忽略，发出的 pending 请求只允许发起 persona 撤回；动作成功前不得乐观删除条目，canonical failure 必须保留原状态与可重试动作。
- 回复必须由 `GreetingRequest` owner 先完成状态迁移并取得 `promotedConversationId`，再由 Chat owner 创建或复用唯一正式 1v1 conversation；重放不得创建第二个会话，且升级不得自动建立关注、互关或其它关系事实。
- 忽略与撤回不得创建 Chat conversation；页面不得泄露 owner 映射、对方额外身份、内部风控原因或未获授权的交集事实。

<a id="req-007"></a>
### REQ-007 人物关注只接纳已解析的不可变目标，Creator 只可被关注

- 普通 Persona 与已发布 Creator 均须由 User 的唯一目标解析能力确认公开身份、当前可见性与人物关注资格；昵称、用户号、路由别名和 owner 不能代替关系身份，未完成解析不得接纳本地待发关注。
- Creator 仅可作为被关注目标；不得为关注创建可登录账号或伪 Persona，也不因被关注获得回关、发消息或通话的主体资格。不改走 SubjectFollow 掩盖人物目标缺口。
- Creator 的公开映射必须唯一且绑定当前有效 release；旧发布依据、跨类型同字节冲突或缺少映射均明确受限，不任取一种身份继续。已具备资格的真实 Creator 必须可完成关注、读取和取关，不能通过隐藏全部 Creator 入口实现本要求。
- 改名、改头像与合法发布切换不改变既有关系身份。退出当前 release 不等于用户主动取关；永久撤销或删除按 owning lifecycle 收敛，不复活公开关系、统计或推荐贡献。

<a id="req-008"></a>
### REQ-008 每个新接纳的关系决定均有版本仲裁，摘要不能替代身份核验

- 同一对不可变公开身份保持唯一 Pair；交换查看方向不改变 Pair 身份。所有查询、锁定、写入、取消、回执恢复及投影消费均须核验实际二元组；摘要命中其他身份时拒绝串用，不改变任何方向，不产生成功回执或业务事件。
- 不存在关系也具有可比较的初始版本。每个权限和前置版本校验通过的新命令，包括目标值已满足的 no-op，都推进同一 Pair 版本并留下确定回执；同键重放返回首次结果且不推进版本。
- no-op 不重复占用关注名额、不改变公开计数、不发关系变化事件；“无业务变化”与“命中原回执”必须可区分。后续事件可跨越无事件的命令版本，消费方不得等待不存在的业务事件。
- Pair 的双向关注与屏蔽共享仲裁版本。反向关注导致旧依据失效属于可恢复的业务冲突，不能自动换版本重发旧决定；当前状态已满足只证明当前态，不证明原命令提交。
- 关系、实际名额变化、命令回执与需要发布的事件要么一起提交，要么一起不提交；任一方向屏蔽须清除双方实际关注且不重复释放，解除屏蔽不恢复旧关注。权威关系读取必须呈现同一快照的方向与版本。

<a id="req-009"></a>
### REQ-009 有限命令有效期内可恢复，结果未决不能靠当前关系态终结

- 同一用户意图固定已验证主体、canonical 目标、目标状态、前置依据与接收期限；传输重试复用原命令身份，不改变其中任何语义。关键输入缺失、非法或相互冲突必须在写前拒绝，不按默认值接纳。
- 写依据由服务端签发并受完整性保护，默认最大接收窗口为 72 小时；签发依据本身不改变业务状态，也不代替当前身份、目标权限与名额校验。有效依据可随正常页面读取批量取得，已有依据的点击不强制多一次预备请求。
- 命令回执保留至少 96 小时，并覆盖接收窗口与恢复余量；期限不能因重试、重新取依据或缓存回放而续长。同键已有回执可在接收期限后读取，新的用户决定才可取得新依据并使用新命令身份。
- 断连、超时、崩溃或后置查询失败仅能说明结果未决，不能推翻已经提交的事实。到期只停止新写发送；恢复方与仍在飞行的原写须争用同一回执裁决，只有确认已提交或已不可执行后才能移除未决状态。
- 历史回执已清理时，当前关系值不能被包装为历史成功或从未执行；过期依据不能重新变成新写。权威不可达时明确保留未决与恢复入口，不无限接纳待发意图，也不丢弃已有恢复凭据。
- 永久关闭或退役的内部关系清理由经验证的 owning lifecycle 事实授权，不依赖已失效用户凭据或终端写依据；终端用户不得伪造该内部补偿通道。

<a id="req-010"></a>
### REQ-010 主动关注人数由系统限额精确裁决

- 单 Persona 主动关注初始上限为 1000，可经受管系统配置提高到 10000；它不是每秒限流，不限制被关注人数，页面只能展示服务端有效限制，不能自行放宽。
- 同一 Persona 对不同目标并发新增关注时，成功数不得超过剩余名额；只有实际从未关注变为关注才占用名额，取关、屏蔽清边与生命周期清理只释放实际已占用名额。
- 超限为明确系统限制拒绝，原关系与名额不变，不产生关注成功事件，不进入持续后台重试。已有关系的同键重放不再次占用名额。
- 上调不重建关系；下调不强制删除既有关注，已超额者仍可取关但不能新增。配置激活完成才宣布新限制生效，在飞行旧策略命令与激活之间必须有可观察、无穿透的提交边界；激活失败继续使用已生效限制。
- 名额以写权威为准，不按异步公开计数或缓存裁决。千级、万级的功能边界均须成立；提高参数本身不证明对应查询和写入容量已达标。

<a id="req-011"></a>
### REQ-011 所有人物关注入口只显示待确认，不显示本地假成功

- 首页卡、作者主页、沉浸查看器、关注/粉丝列表、圈子成员/统计、账号搜索、联系人确认/二维码与通讯录发现使用同一人物关系事实和命令恢复语义，仍各自遵守入口资格。
- 点击立即显示处理中，已确认的关注状态只由对应主体、目标与命令的云端回执更新；断连保持待确认，确定拒绝保留原态并展示 canonical recovery。读失败且没有用户命令时不得制造“关注处理中”。
- 同一主体目标至多一个已发送而未裁决的意图；反转可合并尚未发送部分，但不能改写在飞行命令或绕过它发送后继意图。已持久接纳的意图须在重启后可恢复，存储失败不得宣称已可靠排队。
- 切账号或分身、页面重入、旧网络响应与旧缓存均不得串主体或覆盖更新的已确认状态；旧 capability 不能覆盖新关系，pending 不能扩大私信或通话权限。
- 视觉待确认反馈目标 P95 不超过 100 毫秒，云确认耗时另计；在线前台可见关系在声明负载下从提交到展示的端到端 P99 收敛目标为 5 秒，离线、后台与权威故障单列，不以 UI 改变冒充确认。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/object.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/storage.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/events.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/profile_projection/creator_runtime_profile/object.yaml`
- canonical：`quwoquan_service/services/user-service/config/schema.yaml`
- 目标证明、命令依据、回执终态、限额与恢复的确切 wire 只由以上 User contracts 拥有；本节点不新增字段、枚举或错误码。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 关注关系

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“关注关系”对应的公开行为。
- THEN owner 不能作为默认 follow 主体参与社交关系建立。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 联系人发现、搜索或二维码候选经关系能力确认后完成关注

- GIVEN 用户以 active persona 登录 production Remote composition，并从系统通讯录、账号搜索或可撤销资料二维码进入添加联系人旅程。
- WHEN App 对通讯录权限作出允许或拒绝处理；允许时仅提交端侧规范化后的哈希集合，并分别经 `contact_discovery_record`、`user_account` 或二维码解析公开能力取得候选。
- WHEN App 对选中候选读取 `persona_relationship` 的 relationship capability，并仅在 `canFollow` 成立时提交 follow 命令。
- THEN 原始手机号、ownerId、二维码 bearer 信息和内部屏蔽原因不进入请求、日志、埋点或结果回执。
- AND 成功后由 production Remote 或 Alpha 本地演练 adapter 读回 canonical 关系态；失效二维码、不可见或被屏蔽候选不得落 follow edge。
- AND 权限拒绝、网络失败或 canonical failure 保留可恢复的输入与候选状态并提供重试，不得清空页面或展示伪成功。
- AND 只有绑定同一 candidate、真实 Provider 与 production Remote 的 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 均通过时，本验收场景才计通过；Widget、模拟器、动态 skip 或 typed double 不计。

<a id="gwt-003"></a>
### GWT-003 屏蔽列表分页读取、解除屏蔽与失败恢复

- GIVEN 用户以 active persona 登录 production Remote composition，且云侧存在由该 persona 拥有的真实 block edge。
- WHEN App 经 `persona_relationship` 具名 reader 分页读取屏蔽列表并对目标提交解除屏蔽命令。
- THEN 分页使用稳定 cursor，结果不重复、不串页，且不得泄露 owner 映射或目标的额外身份。
- AND 只有 typed command 成功且 production Remote 读回已移除目标时，UI 才移除该列表项。
- AND canonical failure 或读回未收敛时保留原列表项、关系态与重试入口，不得显示解除成功。
- AND 只有绑定同一 candidate、真实 Provider 与 production Remote 的 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 均通过时，本验收场景才计通过；Widget、模拟器、动态 skip 或 typed double 不计。

<a id="gwt-004"></a>
### GWT-004 打招呼收发箱回复、忽略、撤回与正式会话升级

- GIVEN 两个非互关且未互相屏蔽的 persona 之间存在真实 pending `GreetingRequest`，用户从 canonical `chat.greeting_inbox` 进入 production Remote 收发箱。
- WHEN App 分别分页读取 inbox 与 outbox，并由合法 actor 对收到的请求执行回复或忽略、对发出的 pending 请求执行撤回。
- THEN 收到和发出的请求保持正确归属、状态与稳定分页，pending 请求在回复前不进入普通会话列表。
- AND 回复成功只创建或复用一个 Chat 正式 1v1 conversation，返回的 `promotedConversationId` 可打开该会话，重放保持同一会话且关注关系不变。
- AND 忽略或撤回只在 production Remote 确认状态迁移后更新条目，且不创建 conversation。
- AND canonical failure、超时或读回未收敛时保留原条目与可重试动作，不展示伪升级、伪忽略或伪撤回，也不泄露额外身份与内部治理事实。

<a id="gwt-005"></a>
### GWT-005 普通 Persona 与真实 Creator 使用唯一关系身份且摘要碰撞不串边

- GIVEN 当前主体已验证，目标分别为合法普通 Persona、具有当前发布资格的真实 Creator，以及未解析别名、冲突映射或失权候选。
- WHEN 用户从人物入口关注、读取再取关，并在目标改名或合法发布切换后读取同一关系；完整性专项让不同身份二元组命中相同摘要。
- THEN 合法普通 Persona 与 Creator 均能由真实关系命令形成、读取及取消同一 canonical 关系；Creator 只被关注，不创建登录身份或获得 actor 能力，公开属性变化不重建 Pair。
- AND 未解析、跨类型歧义、旧发布依据或失权目标不得入待发队列或落边，不将 Creator 改走其他关注对象，也不把全部 Creator 禁用当正向通过。
- AND 对摘要碰撞的查询、写入、取关、解除屏蔽、回执恢复与投影输入均安全拒绝，不改写任何一对真实身份的方向、计数或成功事件；数据库拒绝第三端点与不属于 Pair 的方向。
- AND 退出当前发布仅收缩公开资格，不伪造用户主动取关；永久撤销后旧缓存和迟到消费不能复活公开贡献。

<a id="gwt-006"></a>
### GWT-006 no-op、原键重放与到期恢复只有可证明的命令结果

- GIVEN 两设备持同一 Pair 的有效写依据，旧写尚未提交，且可控制响应丢失、原事务停顿、接收期限和回执保留期限。
- WHEN 新的无变化决定先接纳，随后旧版本写到达；另令原写与到期恢复竞争，并在物理清理历史回执后再次发送原过期请求。
- THEN 每个新接纳命令恰好推进一次 Pair 版本，包括原本无边的取关；原键重放保留首次版本和冻结结果，无变化不增加业务事件、公开贡献或名额，后续实际事件可跨版本收敛。
- AND 旧版本写和被反向关系变更淘汰的依据不能覆盖新决定；权威读返回同一快照，当前态已满足不归因为原命令成功。
- AND 服务端签发的 72 小时依据不能换主体、换目标、篡改版本或续期，也不越过最新权限与名额；关键输入缺失、错误或幂等来源冲突均在写前失败。
- AND 回执至少保留 96 小时；原写与到期终结在同一回执裁决中仅一个终态胜出，提交后丢响应可取回原结果，统计或后置读失败不改报未提交。
- AND 截止前已接纳的原事务可以晚于截止提交，但不能和“确定未执行”的终态同时成立；回执清理后只报告历史不可判定，过期请求不能再次执行，权威不可达不伪造终态。
- AND 经验证 lifecycle 事实可在用户凭据失效后继续内部清理，但伪造的终端请求不能借此绕过授权。

<a id="gwt-007"></a>
### GWT-007 并发限额、策略激活与全入口待确认保持同一真实关系

- GIVEN Persona 只剩一个关注名额，另有在飞行旧策略命令，用户从各人物入口操作，并可能切换分身、重启或遇到弱网。
- WHEN 多目标并发关注、受管上调或下调限制，随后取关或屏蔽并原键重试；本地尚未确认时反转意图或接收旧页面响应。
- THEN 新增成功数不超过剩余名额，超限明确拒绝且不写成功事件、不后台反复重试；实际取关与双向屏蔽只释放已占用名额，公开异步数字不能作为配额。
- AND 初始 1000 与升档 10000 的功能边界可验证；下调保留已有关系、禁止超额新增并允许取关和原键回放，旧策略在途写与激活有确定先后，激活失败不谎报新限制生效。
- AND 所有人物入口点击只展示待确认，按匹配主体与目标的云端回执更新已确认关系；无命令的读失败不生成 pending，超时不当失败，明确拒绝保留原态和恢复动作。
- AND 未裁决原写不被后继意图越过；存储失败不称可靠接纳，重启可恢复已接纳意图，切主体、旧响应和旧 capability 不覆盖新确认或扩大聊天权限。
- AND 同一候选的 Android 与 iPhone 物理设备证据包含真实普通 Persona、真实 Creator、全部人物入口以及关联回执和服务读回；待确认反馈与在线可见收敛分别按本 Story 目标测量，UI 自证、模拟器和 skip 不计通过。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[目标解析 DEC-002](../design.md#dec-002)、[Pair DEC-004](../design.md#dec-004)、[命令终结 DEC-005](../design.md#dec-005)、[系统限额 DEC-006](../design.md#dec-006)、[App 确认 DEC-010](../design.md#dec-010)。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 联系人、屏蔽与打招呼收发箱的双真机 user_acceptance 证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺能够同时证明 `GWT-002`、`GWT-003` 与 `GWT-004` 的 production Remote、隐私边界、User→Chat 升级、成功读回、失败恢复及同一 candidate 双物理设备行为的结果回执。
- 完成判定：`GWT-002`、`GWT-003` 与 `GWT-004` 均由职责匹配的 production journey 覆盖，并绑定同一 commit、ContractGraph、candidate、环境与真实 Provider；Android 物理设备和 iPhone 物理设备的 `ReadinessResultBundle` 均为 passed 后才可关闭。failed、blocked、skipped、模拟器或测试 double 结果均不计通过。

<a id="open-002"></a>
### OPEN-002 人物目标、命令终结与限额确认的单轨合同及真实证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Creator 目标与普通 Persona 的单轨解析、完整性拒绝、版本化新 no-op、服务端签发写依据、到期同回执仲裁、精确限额及所有关注入口的云确认尚缺配套合同与直接证据；现役目标声明、可缺省幂等输入及只描述服务内 CAS 的合同不能证明这些要求。
- 完成判定：`GWT-005`、`GWT-006`、`GWT-007` 的每条结果均有有效 `spec_ref` 和职责匹配的真实测试；local_contract 覆盖身份/状态机反例，api_integration 覆盖真实 PG、受管 Creator 发布、policy 激活与原写/终结竞争，user_acceptance 覆盖同候选双物理设备全部入口。合同验证、当前生成结果与对应证据一致后才可关闭，静态规格、旧 receipt、UI 自证与 skip 均不算实现完成。
- 依赖：canonical PersonaRelationship 的目标引用、请求/结果/恢复、事件完整后态、storage 与系统配置同步收敛；Creator release 与物理设备依现役受管入口准备。
