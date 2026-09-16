# L2 Design：内容展示一致性 (`content-display-consistency`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接”需要 `article-display-journey`、`circle-feed-viewer-handoff-contract`、`content-action-intent-contract`、`feed-item-dto-contract`、`moment-display-journey`、`photo-display-journey`、`video-display-journey`、`viewer-profile-state-sync-contract` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-display-journey`](./article-display-journey/spec.md)：整个卡片为统一热区，点击直接进入文章沉浸式阅读器。
- [`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)：圈子 post 进入 viewer 时必须传入。
- [`content-action-intent-contract`](./content-action-intent-contract/spec.md)：更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
- [`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)：`generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。
- [`moment-display-journey`](./moment-display-journey/spec.md)：**行为基线**：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器。
- [`photo-display-journey`](./photo-display-journey/spec.md)：让图片频道、沉浸式浏览器与作者主页使用同一内容身份和互动状态，并在返回时保持上下文。
- [`video-display-journey`](./video-display-journey/spec.md)：首页/视频频道/作品浏览器的同一视频 post 未播放态封面一致，点击后能进入同一 `videoUrl` 的播放态。
- [`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)：viewer、profile 与 feed 消费同一 canonical `RelationshipCapabilityView` 关系矩阵。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 列表、沉浸浏览器与作者主页共享对象身份和互动状态
- 决策：列表、沉浸浏览器与作者主页共享对象身份和互动状态。
- 理由：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 图片/视频及图片静态页/翻页纹理复用 [双轨发现 DEC-003](../dual-rail-discovery-redesign/design.md#dec-003) 的单一整栏几何；比例与显示窗口只消费 [works-immersive-viewer REQ-024](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#req-024)，不另建连续侵入栏内、无条件 cover 或图片专用 contain 主线。竖屏视频拖动控制与 chrome 共享同一 `VideoPlaybackSnapshot.isScrubbing`：caption、居中全屏入口及 association slot 同步退出绘制、命中和 semantics，保留测量空间，档位、对称裁剪和媒体矩形不跳动；不存在独立 current-time 行或时间锚点。timeline 仅持有手势热区和虚拟 target，视觉轨保持贴底基准并在增厚时向上展开；释放只提交一次 seek，取消不提交，两者保留 session intent。播放中的 scrub 不暂停或额外续播，取消保留自然推进的最新实际位置，paused 仍取原稳定位置；清除虚拟 target 后继续有效播放计时，不由可视层发第二套 play/pause/seek。竖屏 30 秒边界及 inlineFeed 的独立规则仅引用 [video-display-journey REQ-004](./video-display-journey/spec.md#req-004)。
- 横向几何以 `safeViewportRect -> fixed left/right control slots + mediaStageRect -> contained visibleMediaRect` 单向派生；外槽只随视口/安全区变化，标题、时间轴、作者/关注、赞转评只消费实际媒体像素左右边界，中央按钮只消费实际媒体中心。时间轴视觉端点按 thumb 半径内缩，横向任何 chrome 不再从整视口或固定 inset 平行推导。显隐使用始终挂载的 interaction plane，pointer-down 固定起始显隐意图；普通 hold 与 require-visible blocker 分型，session position tick 不得因 held pointer 强制 reveal 或销毁 gesture arena 参与者；隐藏短点只 reveal，横向播放 intent 仅由显示后的中央按钮改变。
- 横向展示与恢复复用 [双轨发现 DEC-004](../dual-rail-discovery-redesign/design.md#dec-004) 的 viewer 局部旋转和单一控件显隐状态机，不请求/捕获/恢复系统方向、不复制播放器或进入时旧播放位置。标题在顶部，作者/关注与赞转评保留底部分组；视频所有已知有效时长的时间轴位于整组上方，时间只在 scrub 显示，图片无播放/时间轴。播放、暂停和图片统一五秒隐藏全部普通控件（含退出），slot 与短视频 timeline 不另设竞争 timer；viewer 画布层以幂等 reveal/hide、pointer identity、blocker 集合及绑定 post/media/session 的独立 chrome epoch 协调拖动、按住、弹层、路由、buffering/loading/failure 等挂起条件，轻点只显隐，迟到回调不可改写新交互。横向禁切作品/翻图/切集，作者/评论往返与收起消费同一媒体最新位置/intent 和互动状态；主壳导航在整个沉浸周期保持隐藏。功能验收直接绑定 [GWT-021](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-021)、[GWT-023](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-023)、[GWT-024](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-024) 与 [GWT-025](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-025)，本层不维护第二套模式/失败恢复合同。
- 关联要求：`REQ-001`
- 影响 Story：[`article-display-journey`](./article-display-journey/spec.md)、[`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)、[`content-action-intent-contract`](./content-action-intent-contract/spec.md)、[`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)、[`moment-display-journey`](./moment-display-journey/spec.md)、[`photo-display-journey`](./photo-display-journey/spec.md)、[`video-display-journey`](./video-display-journey/spec.md)、[`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 复用同 actor 分区内核，领域意图与可信确认各归其主

- 决策：复用 ActorQueuePartition、现役 client_state_sync outbox engine 与持久 store；runtime 仅提供调度/持久化/版本合并能力，User 关系与 ContentReaction 各自拥有 typed coordinator/状态。Post bool 与 Comment 三态不合成万能 Repository 或 bool 队列。
- 决策：outbox、shared relation/reaction、receipt 与私有缓存同 environment/account/persona/device scope，实际 actorDimension/actorId 由 verified principal 派生；可信匿名 Persona 不因 isGuest 改写成 device。envelope 校验完整 actor，切区停止旧发送，迟到读/ACK 先校验 actor、目标、request generation 和本对象版本，A→B→A 不串用；匿名转登录不搬移。
- 决策：已发送 envelope 冻结 key、signed basis、目标值、expectedVersion/期限；同 actor-target 一 flight，跨 target 有界并发与公平。未发送反转可合并为最后 desired，但前驱 unknown 不得越过。持久写串行有序且成功才 durable acceptance；hydrate 以每对象 revision/tombstone 合并，既保护加载中的新增/删除也恢复其他未变磁盘项。未决/版本栅栏不随普通 LRU 淘汰，日志条数/bytes/年龄有上限与 backpressure。
- 决策：关注只 pending，云确认才改 confirmed；点赞按钮可乐观且仅覆盖本 intent，数字不加减。receipt 确认即移出命令重试，统计新鲜度独立。缺字段旧记录/损坏记录禁止补造新命令；超过本地最大年龄只停发，authority 同 key 终结与历史不可判定按 User/Reaction owning protocol 恢复，不凭当前 bool 或墙钟作历史裁决。
- 理由：页面局部 bool、全快照回滚或全快照 hydrate 会抹掉其他动作/串 actor；两个 bool 无法表达已发送身份、unknown 与后继意图。确认不等统计避免已成功命令重发或永久 pending。
- 被否决方案：新万能 sync Repository、按 guest 选 device、切号搬队列、任一对象变化就丢整包磁盘快照、吞 persist 错误宣称排队、同 target 并发写、ACK 回滚整页/整树、到期直接删 unknown、新 key 偷偷重试和由 viewer 返回值写第二真相。
- 恢复与回滚：瞬时传输故障同 key/依据有限退避；scope/配置/身份错误明确终态，不后台排 72 小时。确定拒绝仅撤当前 overlay，业务版本冲突读当前事实后交用户决定。持久化失败/满队列拒绝新 durable acceptance、保留现有记录与恢复入口。回滚停止新发送并保留可由 authority 恢复的 envelope/receipt，不还原旧双 bool 协议或旧账号数据。
- 观测与 SLO：点击到 pending/按钮反馈 P95 目标≤100ms，durable acceptance 与云确认时间分别记录；监测每分区队列数量/bytes、unknown 最大年龄、persist 失败、单飞冲突、迟到拒收、recovery outcome。跨 actor 污染、同 key 多 flight 或假确认零容忍，超容量执行 backpressure；字段只记脱敏身份/分类，不输出 basis/token 原文。
- 测试 seam：sealed production provider 配 typed port、Completer、固定 clock 与真实本地持久 store 控制 hydrate/写失败/A-B-A/反转/旧 ACK；真实 Remote 掉响应、重启和到期仲裁证明回执而非 bool；Android/iPhone 同候选跨页和切身份另证，测试替身不代替 service transaction proof。
- 关联要求：`viewer-profile-state-sync-contract REQ-001`～`REQ-004`；影响 Story：状态同步、动作意图、视频旅程及相邻 Comment。
- 关联验收：[GWT-001](./viewer-profile-state-sync-contract/spec.md#gwt-001)～[GWT-004](./viewer-profile-state-sync-contract/spec.md#gwt-004)、[Comment GWT-022](../publish-comment-reaction/comment-thread/spec.md#gwt-022)。内核、协议、设备缺口由最低 Story OPEN 承接。

<a id="dec-003"></a>
### DEC-003 公共内容、本人互动、命令与统计四条读语义分离

- 决策：页面组合公共内容、actor-scoped Reaction/Relationship、命令状态与 typed statistics slice，而非用一个 bool/null 或一个全局 version 表示全部。viewer attachment 的成功、明确不适用与暂不可用由 owning contract 明示；available 数字必填且合法，stale 只携带有来源旧数字，unavailable 不伪造零。旧 required 字段缺失仍是协议失败，必须先 authoring/codegen 单轨替换后才能消费 partial，不能从坏 DTO 自行救正文/数字。
- 决策：无命令且本人态完全未知保留稳定布局/loading/恢复入口，点击先有界权威读取再继续，不盲 toggle；同 actor 旧已知值仅按来源标 stale。统计单独失败只降级数字，不隐藏合法内容/互动栏；本人 reader 正常仍可操作。已有 pending 不因缺席消失，receipt 确认不等统计，10→按钮乐观/数字10→receipt→stats11 只显示11。
- 决策：REST Feed/detail/点查/批量 hydrate 调同一 verified actor reader。公开 persisted GraphQL 的 service-principal 内容切片保持公共，viewer 缺席属于明确不适用，不等同未赞；个性化必须经独立受信 actor slice 或正式委托组合，不伪造 Persona header、不把 service 身份当 viewer，不强制 App 迁移 GraphQL。公开 value 不保存 viewer bool/pending。
- 决策：复合 capability 的关系、资料/可见性、Greeting/Conversation 保留各自版本/有效性，不用 relationshipVersion 冒充整个视图版本；旧 capability 不覆盖新 confirmed，pending 不乐观扩大私信/通话权限，命令仍在 owner 重鉴权。
- 理由：本人是否赞、历史命令是否提交和总赞数新鲜度是三件不同事实；公共读取身份与真实用户身份也不同。把 read failure 填 null/false/0 会伪造未赞、零赞或假 pending。
- 被否决方案：数字本地 +1/个人贡献 witness、每点击全量 Count、failure→null/零、坏 DTO 任意容错、public GraphQL 缺席视为所有 App 路径失败、同公共 cache 混入 viewer，以及为消除表象强迫全部读取迁移 transport。
- 恢复与回滚：仅可选子读失败用 typed partial，主内容协议/权限失败仍按自身合同处理；可见目标有界 batch 补读，不用无界逐卡重试。回滚关停不支持的新操作/合同客户端，保留已确认与来源期限，不恢复旧数字 overlay 或宽松 decoder；authority unknown 与统计 unavailable 不互相转换。
- 观测与 SLO：记录完整互动附着率、不适用/暂不可用原因、decoder failure、统计 available/stale/unavailable 与用户命令确认分别计量；内容 HTTP200 不等于互动完整成功。统计期限/5 秒端到端预算遵循 [发布互动 DEC-008](../publish-comment-reaction/design.md#dec-008)，未测量不填达标。
- 测试 seam：generated decoder 直接喂 required 缺失/坏类型、合法零与各 typed 分支；production provider + sealed transport 验证真实 principal/descriptor。真实 REST/公开 GraphQL+私有组合覆盖登录 Persona、可信匿名 Persona、device-only、无/非法凭据，同 public cache 跨 viewer 无泄漏；双真机验证数字/按钮/恢复，不以 UI 文本可见证明 server ACK。
- 关联要求：`viewer-profile-state-sync-contract REQ-002`、`REQ-005`；影响 Story：状态同步、视频与全部显示载体。
- 关联验收：[GWT-005](./viewer-profile-state-sync-contract/spec.md#gwt-005)、[GWT-006](./viewer-profile-state-sync-contract/spec.md#gwt-006)、[Reaction GWT-002](../publish-comment-reaction/reaction-state-counter/spec.md#gwt-002)、[GWT-003](../publish-comment-reaction/reaction-state-counter/spec.md#gwt-003)。新 slice/组合缺口归状态同步 `OPEN-002` 与 Reaction `OPEN-002`。

<a id="dec-004"></a>
### DEC-004 所有入口由 metadata surface 接入协调器，以 epoch 保护精确刷新

- 决策：人物关注、Post like、Comment reaction 的现役入口分别进入所属领域 coordinator；保留 SubjectFollow 独立目标/版本/writer。页面只提供 canonical target 与真实宿主 surface，generated descriptor/header factory 继承 operation/trace/referral；首页、viewer 各方向、评论内 Post、作者作品、搜索直达、圈子统计及联系人系列均不直调 writer。只修真实 source 和 circleStats 绑定，不放宽无关 surface、不建中央手工 registry。
- 决策：enqueue、ACK、明确拒绝推进同 actor/target mutation epoch，身份切换推进分区 epoch；网络响应和磁盘 hydrate 同时核验后才允许缓存/共享状态写入。objectVersion、Reaction/Pair version、statsVersion/generation 与能力来源各比各；正文按 environment/release/object 身份及真实 replay policy 回放，私有状态独立，不让旧 DTO bool 覆盖 receipt。
- 决策：点赞确认只更新本人态、标记统计待刷新，正文无需重新下载；旧混合 DTO 尚未退役时精确失效目标及引用页并推进 query epoch，拆分完即退役该过渡形态，不长期双真相。Follow 确认只精确失效相关 following/followers 热页与顶部栏，公开统计等统计事实；点赞不重排不可变 RankedFeedWindow。
- 决策：页面进入、前台/网络恢复与动作后通过唯一生命周期协调器合并一次可见 batch，保留 singleflight/退避/公平和总并发预算；驻留页若继续提供 5 秒新鲜度，使用唯一可见区调度器并测在线人数×频率×batch 成本，无各 Widget timer。L1 继承源 asOf/硬期限，不延长服务缓存生命；服务端缓存机制只引用发布互动 DEC-008。
- 理由：只 DEL 已存 entry 会漏掉在途旧读；只测手工 Remote 会漏 production provider 的错误 source。精准失效和有界 batch 既保护读己之写也避免点赞触发全量正文/全 Feed 放大。
- 被否决方案：createWorkspace 作为任意点赞默认、页面自建 success bool、相同名字推断 Creator 资格、按路由 handle 入队、全 Feed 清空、永久数字覆盖值、媒体返回包第二写轨、`()=>true` production replay policy、每卡两秒 timer 和为未实现的 Post 收藏恢复入口；实体想去只遵循 [发布互动 DEC-002](../publish-comment-reaction/design.md#dec-002)，不新增能力。
- 恢复与回滚：scope/配置/身份失败明确停止，不排长期重试；可选统计/缓存故障按 typed stale/unavailable 和限额回源，权限收缩立即复核，不以 TTL 放行。回滚先禁受影响新入口/缓存回放，保留合法 envelope/receipt 与版本栅栏，不能切 Mock、回旧协议或丢已提交事实；只在全部服务/App/consumer 同候选契约与最低客户端准入验证后开放。
- 观测与 SLO：每入口 operation/surface/typed outcome、旧 epoch 拒收、batch 去重/大小/QPS、cache hit/源年龄、前后台恢复时延和 UI 反馈分别记录；圈子/Creator/直达不能用其它入口成功率代证。当前 approved 峰值与刷新成本不足时不声称驻留页 5 秒达标，后台/断网单列。
- 测试 seam：真实 provider/descriptor/header factory 连接 sealed transport 逐入口断言，静态源码/descriptor 扫描仅补旁路检查；Completer 固定旧 read→ACK→迟到 read/hydrate/capability，验证缓存和 state 双方均不被覆盖。真实 Remote/cache 与双真机完成竖横屏、作者/评论往返、搜索直达、A-B-A/前台恢复，播放会话不因互动 partial 重建；低层 engine race 引用其 owning API proof。
- 关联要求：`content-action-intent-contract REQ-002/003`、`viewer-profile-state-sync-contract REQ-006`、`video-display-journey REQ-006`；影响 Story：动作意图、状态同步与视频旅程。
- 关联验收：[动作 GWT-002](./content-action-intent-contract/spec.md#gwt-002)、[GWT-003](./content-action-intent-contract/spec.md#gwt-003)、[状态同步 GWT-007](./viewer-profile-state-sync-contract/spec.md#gwt-007)、[视频 GWT-005](./video-display-journey/spec.md#gwt-005)。缺证据分别保持各最低 Story block OPEN，不用旧播放测试或单 Remote 测试代签全入口。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；确定拒绝不写成功事实，响应丢失保留 outcome unknown，已提交命令的后置读/统计失败不反转提交。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 同步并发/队列/期限/刷新预算来自现役系统配置 authoring 与 App Config；业务页面不另立默认值或 feature flag 复制协议，scope 配置不完整时 typed 拒绝。
- 点击反馈、持久接纳、云 durable 确认、统计新鲜度和完整附着率分别记录；source/actor/命令只留脱敏关联，不记录凭据、basis 或私有 payload。
- local_contract、真实 Remote/引擎、编译安装、双真机、容量与 HA 证据分别绑定当前 source/ContractGraph/候选；本轮设计不替代其中任一证据。
- 单轨迁移与回滚遵循 DEC-002/004；source/合同先 verify/codegen，缺新字段客户端走明确升级/拒绝，不保留长期旧 decoder、双写或旧快照反向覆盖。
