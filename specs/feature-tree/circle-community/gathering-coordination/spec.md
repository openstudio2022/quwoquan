# L2 Business Capability：结伴与线下相聚协调 (`gathering-coordination`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：`本层 design.md`

## 1. 能力目标

让任何可信 Host 把内容、地点或兴趣变成可公开发现或定向邀请、可准入、可在活动群聊与看板协作、可形成 Outcome 并回流内容的 Gathering。创作者行动、Circle 活动、普通 Persona 发起、可选 Entity Host、1:1、多人和多日行程只通过来源、政策、要求与可选能力形成体验差异，不建立第二活动根。

## 2. 范围与非目标

### In Scope

- Gathering 的 Host authority、草稿/发布、Revision、生命周期、时间阶段、准入状态、取消/提前结束/安全终止与 Outcome。
- root-owned GatheringParticipation 的邀请、申请、公开加入、审批、退出、移除、重大变更确认、出席与容量不变量。
- 唯一 contextual activity room 的 binding state、有效参与者访问投影，以及由 Circle/Chat/可选能力组合的 Board 读模型。
- 公开详情、发现投影、名额提醒、Host 管理、安全披露、Report/Block 级联与完成后 Content 回流引用。

### Out of Scope

- Conversation、ConversationMembership、Message、Announcement、已读、通话和附件索引，由 [`chat-conversation`](../../chat-conversation/spec.md) 负责。
- Post、MediaAsset、LocalPostDraft 与 Report，由 Content owner 负责；Gathering 不是第五种 Post。
- 候选召回与排序由 `recommendation-platform` 负责，但 Recommendation 不拥有候选资格、Participation、准入、容量或 Outcome。
- Persona Follow/mutual/Block、Entity Homepage authority 与 CircleMembership 由各 owner 负责；Participation 不自动建立关系或 Circle membership。
- 连续实时位置、票务支付、退款分账、Workspace 产品和活动类型白名单。

## 3. Journey / Scenario 贡献

- [`JNY-011 / SCN-027`](../../spec.md#scn-027)
  - 本能力接收：来自内容、C 位、主页、会话或推荐公开卡的发起/响应意图，以及 owner 可验证的来源、Host authority、viewer 与风险/披露结果。
  - 本能力处理：创建 room-ready Gathering，维护单一 Participation、Revision、容量/准入、生命周期、Outcome 与 room binding state，并向 Chat 投影访问、向 Content 输出回顾引用。
  - 本能力输出：可公开消费或受邀查看的 Gathering、一个状态驱动主动作、有效参与后的活动群聊与 Board、证据化 Outcome 和内容回流入口。
  - 失败时终态：登录取消、满员、待审批、邀请失效、重大变更待确认、room access 未就绪、取消、提前结束或安全终止均可区分；不产生半加入、自动 mutual、裸建群或本地合成成功。

- [`JNY-013 / SCN-030`](../../spec.md#scn-030)
  - 本能力接收：一个已存在的多人多日 Gathering 与用户确认的计划提案。
  - 本能力处理：保持 Gathering 的 Host、Participation、会话、生命周期与 Outcome 为唯一活动事实，并挂接可选 Plan/Map/Calendar/Experience。
  - 本能力输出：活动群聊 Board 可消费的旅行体验组合。
  - 失败时终态：可选能力不可用不复制 Trip 根，也不改变当前 Gathering 或 Plan Revision。

## 4. Story

- [`gathering-lifecycle`](./gathering-lifecycle/spec.md)：以同一 Gathering 管理 Host、发布、Revision、取消/提前结束/安全终止、完成与 Outcome。
- [`gathering-participant-roster`](./gathering-participant-roster/spec.md)：以单一 root-owned Participation 管理邀请、申请、公开加入、容量、名单、重大变更确认与退出/移除。
- [`gathering-conversation-binding`](./gathering-conversation-binding/spec.md)：在 Publish 前绑定唯一活动群聊，并让有效参与者默认进入消息与活动看板。
- [`gathering-plan-collaboration`](./gathering-plan-collaboration/spec.md)：以每个 Gathering 至多一个可选 Plan、typed proposal/commit 与不可变 Revision history 管理协作计划。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 所有活动形态由单一 Gathering 表达

- 创作者、Circle、Persona 与具备 authority 的 Entity Host 发起的 1:1、多人和多日活动必须由同一个 Gathering 表达。
- `Activity`、`Meet`、`Trip` 只可作为产品文案或 Gathering + optional capabilities 的体验组合；不得按人数、天数、来源或垂类引入活动形态枚举、第二状态机或第二聚合。

<a id="req-002"></a>
### REQ-002 Gathering、Participation、Revision 与 Outcome 同属 Circle owner

- Circle 拥有 Gathering root、root-owned GatheringParticipation、GatheringRevision、Outcome 和 room binding state；PublicCard、Detail、Board、Roster 与 AvailabilityWatch 是投影或外围记录，不是活动聚合。
- 每位 Persona 在同一 Gathering 下只有一条当前 Participation；邀请、申请与公开加入通过专用 operation 改变它，禁止通用状态写。
- GatheringRevision 只冻结活动核心承诺；可选 Plan Revision 独立演进，不得复制 Host、Participation、会话、生命周期或 Outcome。

<a id="req-003"></a>
### REQ-003 生命周期、时间阶段与准入状态分离

- lifecycle 只表达草稿、已发布、已取消与已完成；时间阶段从已确认日程派生，准入状态从政策、容量、截止时间、暂停位和时间阶段派生。
- 满员和进行中不得写成可与容量或时间漂移的第二生命周期；时间到达只可触发 reconciler 评估，不得自动宣称活动 occurred。
- 发布必须满足 Host authority、日程、准入/披露、容量、风险义务与 room binding ready；任一前置不成立时保持草稿且不可公开。

<a id="req-004"></a>
### REQ-004 Host 与 Organizer authority 独立于 Participation

- Persona、Circle 与 Entity Host 必须由 owner authority 证明；新建/发布、增加 organizer 与 Host 转移在 owner 不可用或证据无效时 fail-closed，客户端 subject 或角色声明不能赋权。
- Organizer 管理权不自动占参与席位；实际参加时必须另有有效 Participation。Host 转移、co-host 撤销与 owner governance 事件必须可审计并收敛 Chat admin access。

<a id="req-005"></a>
### REQ-005 准入与容量在 Participation owner 边界内裁决

- audience、admission、capacity 与 disclosure 是正交政策；公开加入、申请审批与邀请接受是三条明确语义，不建立 mandatory match proposal。
- 占用席位只由有效 Participation 与未过期邀请保留派生；申请待审批不占席。Join、Approve 与 Accept 的并发裁决必须永不超员，同一 Persona 的重复意图不产生第二 Participation。
- 满员后拒绝新响应；开场前退出/移除释放席位并可恢复准入，开场后关闭普通准入且不补招。名额提醒不占座、不授予 room access，也不是自动候补。

<a id="req-006"></a>
### REQ-006 重大变更逐 Participation 确认

- 有有效参与者后，时间、精确地点、Host、费用、难度、要求或人数承诺的重大变化必须形成新 GatheringRevision，并让每条受影响 Participation 分别确认。
- 未确认者继续占席但不得被视为已同意；明确拒绝或到期未确认按 owner policy 退出并撤销访问。多人场景不要求全员一致，capacity=2 也不建立独立 unanimous 协议。

<a id="req-007"></a>
### REQ-007 活动群聊是加入后默认主场，Board 不是 Workspace

- 每个可发布 Gathering 恰有一个 Chat contextual Conversation；Chat 拥有 Conversation、ConversationMembership、Message、Announcement、已读、通话与附件索引，Circle 只拥有 binding state。
- 有效 Participation 投影 participant membership，Organizer authority 投影 admin membership；待审批与邀请待响应者不得进入。访问投影未收敛时显示可恢复等待态，不回退普通建群。
- 加入后默认进入消息；顶部 Board 组合 Circle 的 Gathering/Participation/Plan、Chat 的 Announcement/AssetIndex 与可选能力状态。Board 是 typed 可重建读模型，不拥有写状态，不建立 WorkspaceManifest、第二消息流或第二文件存储。

<a id="req-008"></a>
### REQ-008 取消、完成与 Outcome 可区分

- 普通取消只在开场前允许；开场后必须使用个人提前离开、Host 提前结束或 Trust & Safety 安全终止，不得伪装为取消，也不得恢复招募。
- completed 不等于真实发生；occurred、未发生、提前结束、安全终止、争议中与未验证必须按 owner 合同可区分。时间到达或单方声明不能产生 occurred，北极星只消费具有独立参与证据的 occurred。
- lifecycle/outcome、准入关闭、room access 投影意图、command receipt 与 outbox 必须在 Circle owner 一致性边界提交。

<a id="req-009"></a>
### REQ-009 参与者权利、安全披露与关系独立

- 加入前只披露 canonical policy 允许的 Host、时间地点范围、容量、费用/要求、风险、取消规则与重大变更记录；精确地点、名单、附件和活动群聊按 Participation 与 disclosure 开放。
- Host 移除必须提供稳定原因类别、通知与申诉入口；Block、Report、安全退出或移除应收敛 room、文件、计划和精确地点访问，历史证据按审计策略裁剪只读。
- 风险控制依赖 obligations 与 owner authority，不依赖活动类型白名单/denylist；能力或处置条件不足时 fail-closed。
- Participation、ConversationMembership、CircleMembership、Follow 与 mutual 相互独立；加入、到场、完成和共同发布都不自动改变关系。

<a id="req-010"></a>
### REQ-010 公开发现与内容回流不转移 owner

- Circle 签发 Gathering 公开投影；首页、内容、Persona/Circle 主页、Search 与 Chat wrapper 只持 canonical reference/placement/rank reason，Recommendation 只排序，不保存可写活动事实。
- 未加入者进入公开详情，有效参与者再次打开活动默认进入群聊。完成后用户可创建回顾草稿，只有确认发布后 Content owner 才创建 Post/Media 并关联原 Gathering、Host 与来源内容。
- Report 继续由 Content Trust Safety owner 接收和治理；Circle 只保存安全退出、即时撤权与必要证据 reference，不复制 Report 生命周期。

<a id="req-011"></a>
### REQ-011 服务本地契约引用边界

- 字段、operation、route、surface、event、error、metric、恢复动作与 retention 只引用所属服务 contracts 或跨服务 metadata；本节点不得复制 DTO/wire 定义或发明兼容别名。

## 6. 契约与依赖

- 上游能力：Content 提供 Post/Media 来源引用，User/Entity/Circle 提供 Persona、Block 与 Host authority，Recommendation 提供排序结果，Runtime 提供登录 continuation 与 capability。
- 下游能力：本目录直接 Story 及其公开结果；`chat-conversation` 承接 Conversation/Membership/Message/Announcement，Content 承接确认后的回顾发布，Assistant 只消费 typed Reader/Command。
- 读取事实：canonical 来源引用、actor/Host authority、viewer 可见性、Block/Report 与风险 obligation 决策。
- 写入事实：Gathering、root-owned Participation、Revision、Outcome、AvailabilityWatch、room binding state，以及独立的 optional GatheringPlan/PlanRevision/PlanProposal 与 plan-level acknowledgement refs。
- operation / event / surface：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/operations.yaml`、`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/operations.yaml`、`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- 一致性要求：容量、准入、时间阶段、公开卡、名单摘要和 Board 都从 owner 事实派生；跨域投影经 durable outbox/inbox 和幂等 receipt 收敛，不双写 owner 状态。

### 质量、观测与发布契约

- SLI：公开详情成功率、准入 command 成功率、响应成功到 room access 延迟、room/board projection freshness、并发超员、撤权延迟、Outcome 证据完整率与 Content 回流引用完整率。
- SLO：30 天公开详情与准入成功率不低于 99.9%，响应到 room access、退出/移除到撤权 P95 不超过 10 秒。
- SLO：Board freshness P95 不超过 60 秒，超员和未授权 room access 为零；Outcome 与回流引用完整率不低于 99.99%。
- 采样与保留：生命周期、安全、准入写、Host authority、撤权与 Outcome 100% 审计；普通读取 trace 依受治理采样，默认在线 trace 保留 30 天、聚合漏斗保留 13 个月，申请答案和安全证据按 owner retention contract 执行。
- 告警：10 分钟窗口公开详情或准入成功率低于 99%、projection 或撤权 P95 超过 60 秒、任何超员/未授权访问、room binding 不可恢复或 Outcome 证据缺失立即通知 Circle/Chat 值班。
- feature flag：创建、公开发现、准入、room/board、Outcome/回流分别独立控制；关闭新能力时既有 Gathering 仍可读取、退出、安全处置和完成。
- rollback owner：Circle 值班负责人拥有总回滚，Chat 值班负责人负责 room/board 投影，Content 值班负责人负责回流入口；回滚不得删除既有对象、恢复裸建群、启用双读双写或 Mock。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 内容或 C 位发起到 room+board

- GIVEN Host 具有可验证 authority，来源内容或 C 位上下文有效，room provision 与风险义务可用。
- WHEN Host 发布 Gathering，参与者从首页/内容/主页公开详情通过开放加入、申请审批或邀请接受成为有效参与者。
- THEN Publish 前已有唯一 contextual room，有效参与后默认进入同一活动群聊并可打开 Board；待审批或邀请待响应者不能进入。
- AND Recommendation、Chat、Content 与 App 都不保存第二份 Gathering/Participation 状态，参与不会自动建立 mutual。

<a id="sit-002"></a>
### SIT-002 Participation、容量、重大变更与生命周期一致

- GIVEN 一个需要审批且席位有限的已发布 Gathering，存在有效参与者、未过期邀请与待审批申请。
- WHEN 并发 Join/Approve/Accept、重复响应、退出释放席位、重大变更确认，以及开场前取消或开场后提前结束发生。
- THEN 永不超员且每人只有一条 Participation；满员/重开、确认/退出、取消/提前结束的结果可区分，room access 与 owner 结果最终收敛。
- AND 时间到达或单方完成声明不产生 occurred，开场后不补招、不允许普通取消。

<a id="sit-003"></a>
### SIT-003 Host、安全撤权、Outcome 与内容回流

- GIVEN Persona、Circle 与 Entity Host 各有正负 authority 证据，参与者拥有不同 disclosure 与 Block/Report 状态。
- WHEN Host 管理准入与成员、Trust & Safety 执行终止、参与者完成活动并确认回顾发布。
- THEN 越权 Host/审批/移除/读取被拒绝，Block/移除/安全退出收敛群聊、文件、计划和精确地点权限，安全终止与普通完成可区分。
- AND 只有证据满足的 occurred 进入有效参与指标；回顾由 Content owner 发布并保留 Gathering/Host/来源引用，不泄露未授权参与事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 Gathering 核心 contracts 尚未收敛到目标模型

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺从旧 Gathering 五态、名单和绑定语义收敛到 root-owned Participation、Host/Organizer authority、Revision、正交准入/容量、Outcome、material change acknowledgement、AvailabilityWatch 和安全操作单轨的 contracts/runtime。
- 完成判定：contracts verify/codegen 与对象 local_contract 直接覆盖 `SIT-002`、`SIT-003`，并证明无第二聚合、通用状态写、可写 full/in_progress、并发超员或自动 mutual。
- 依赖：Circle/User/Entity/Chat/Content 所属 canonical contracts 与 authority/risk 决策。

<a id="open-002"></a>
### OPEN-002 公开详情、发起与准入 App 闭环未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 C 位三动作、内容/主页发起、公开详情、动态主动作、Host console、登录 continuation 与公开发现的同一 production Remote composer 和真实 UAT；缺 route/surface/operation contract 时不得下发可行动 CTA。
- 完成判定：`SIT-001` 由 local_contract、api_integration、user_acceptance 直接覆盖，游客关闭登录不循环、成功续接原发起/响应动作。
- 依赖：[`creation-mode-and-surface-ia-unification`](../../discovery-content/content-type-framework/creation-mode-and-surface-ia-unification/spec.md) 及后续 contracts/metadata 准入。

<a id="open-003"></a>
### OPEN-003 活动群聊、Board 与撤权可靠性未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺唯一 contextual room 的 Publish 前置、Participation/Organizer membership 投影、Board typed projection、Announcement/AssetIndex、取消/完成 access mode 与退出/Block/移除撤权的同一候选证据；消息离线可靠性仍是上层准出前置。
- 完成判定：`SIT-001`、`SIT-003` 与 [`gathering-conversation-binding`](./gathering-conversation-binding/spec.md) 的 GWT 在杀进程、重连、重复事件和依赖恢复下通过。
- 依赖：Chat message reliability、Circle outbox/reconciler、Calendar/Plan capability。

<a id="open-004"></a>
### OPEN-004 风险运营、SLO 与四环境回滚证据未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺风险 obligations、Host authority fail-closed、Block/Report、申诉、指标读回、告警、feature flag、kill switch、retention 与 rollback owner 在 alpha/beta/gamma/prod 的可执行证据。
- 完成判定：`SIT-003` 的安全正负例、上述 SLI/SLO 与告警 readback、独立 feature flag 关闭和 owner 回滚演练均通过；Prod 仅使用正式行为与正式 Provider。
- 依赖：Trust & Safety Ops、平台观测、Circle/Chat/Content 值班与四环境受治理配置。
