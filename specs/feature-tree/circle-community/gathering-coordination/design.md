# L2 Design：结伴与线下相聚协调 (`gathering-coordination`)

> 对应规格：[L2 spec](./spec.md)
>
> 设计触发原因：新增聚合与状态所有权，且跨 circle-community、chat-conversation 与 recommendation-platform 三个领域交接行动承接关系。

## 1. 背景、目标与非目标

- 背景：旧 Gathering 已有五态与 Chat 绑定基础，但仍把活动理解为“结伴/线下”局部承接，缺 root-owned Participation、Host authority、Revision、Outcome、公开详情、Board、内容回流与安全撤权的统一模型；旅行又存在独立 Trip 根风险。
- 设计目标：以单一 Gathering 承接内容驱动的 1:1、多人和多日行动，让 lifecycle、Participation、room+board、Host、容量/准入、取消/完成与安全边界各有唯一 owner。
- 非目标：不拥有消息、公告、内容、推荐排序或 Persona 关系，不承担连续实时位置、票务支付，不建立 Workspace、第二文件存储或活动类型分支。

## 2. Story 协作与状态流

- 状态 owner：Circle 的 Gathering root 拥有 Host/Organizer binding、root-owned Participation、GatheringRevision、Outcome、容量/准入、lifecycle 与 room binding state；Chat 拥有 Conversation/Membership/Message/Announcement。
- 并发边界：Join、Approve、Accept、Leave、Remove、capacity 与 Participation 版本在 owner 事务/CAS 边界裁决；任何 interleaving 都不得超员或产生同人第二记录。
- 幂等边界：每个语义 operation 使用 actor/target/request digest 绑定的 idempotency；重复邀请、申请、加入、确认、完成和 room ensure 重放原 receipt。
- 一致性窗口：时间阶段、admission、full、Roster、PublicCard 与 Board 是投影；跨域 room access 通过 durable outbox/inbox 收敛，投影延迟不回滚 owner 成功事实，也不伪造可访问。

## 3. 端云与数据流

- App 责任：C 位首层并列发内容/发起活动/发起群聊；所有活动入口复用同一 composer、公开详情、动态主动作、活动群聊/Board 与 Host console。游客选择具体动作才登录并通过 continuation 续接。
- Metadata/contract：字段、operation、route、surface、event、error、metric 与 recovery 只在 owner contracts/metadata 定义；本设计不复制 DTO。
- Service/Data/Ops 责任：Circle 提交 owner 聚合与 outbox，Chat 幂等确保唯一 contextual room 并投影访问，Content 提供来源/回顾，Recommendation 只排序，User/Entity/Circle owner 提供 authority，Ops 提供风险处置和回滚。
- 缓存或投影：PublicCard、Detail、Roster、Board、Timeline/Map 与 AvailabilityWatch 通知均可从 owner 事实重建；snapshot 必须携带 source version/digest，不成为写真相源。
- 主流：`source ref -> draft -> ensure room -> binding ready -> publish -> public projection -> admission/Participation -> room access -> chat+board -> Outcome -> user-confirmed Content recap`。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 1:1、多人、旅行与各类来源合并为单一 Gathering

- 决策：创作者、Circle、Persona 与 Entity Host 发起的 1:1、多人和多日行动全部使用同一 Gathering；人数、日程、来源、要求和 Plan/Map/Calendar/Experience 能力表达差异，不引入 activity/travel/date 形态枚举。
- 理由：这些场景共享 Host、准入、容量、Participation、重大变更、room access、取消与 Outcome 不变量；按文案或垂类拆根只会复制状态机和安全边界。
- 被否决方案：约伴/线下局/旅行分别建聚合，以 capacity=2 建 Match 根，或先建普通群再补活动。
- 影响 Story：[`gathering-lifecycle`](./gathering-lifecycle/spec.md)
- 关联要求：`REQ-001`、`REQ-002`
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 Circle root 同时拥有 Participation、Revision 与 Outcome

- 决策：每个 Persona 在 Gathering root 下只有一条 Participation；邀请、申请、加入、退出、移除、重大变更确认与出席通过专用 operation 改变该实体。GatheringRevision 和 Outcome 与 root 同属 Circle 一致性边界，full/time phase/admission 从事实派生。
- 理由：席位、准入、重大变更和完成证据必须在一个 owner 事务中裁决；拆分 Application/Invitation/Membership/Reservation 或保存 full 会产生竞态与漂移。
- 被否决方案：通用 SetStatus、四套参与对象、ConversationMembership 充当参与事实、endAt 自动写 occurred。
- 影响 Story：[`gathering-lifecycle`](./gathering-lifecycle/spec.md) 与 [`gathering-participant-roster`](./gathering-participant-roster/spec.md)
- 关联要求：`REQ-002`、`REQ-003`、`REQ-005`、`REQ-006`、`REQ-008`
- 关联验收：`SIT-002`

<a id="dec-003"></a>
### DEC-003 每个 Gathering 固定唯一活动群聊，Board 为组合投影

- 决策：Publish 前由 Chat 幂等确保唯一 contextual Conversation；有效 Participation 与 Organizer authority 分别投影 participant/admin membership。加入后默认消息，Board 组合 Circle、Chat 与可选能力投影，通话复用会话能力。
- 理由：Chat 已拥有消息、Announcement、已读、附件和通话可靠性，Circle 必须继续拥有准入、容量、取消和 Outcome。Board 只需聚合读，不需要 Workspace 生命周期。
- 被否决方案：活动内嵌消息、普通 direct/裸群代替 activity room、WorkspaceManifest、第二文件存储、按 recto/board 缓存回写活动事实。
- 影响 Story：[`gathering-conversation-binding`](./gathering-conversation-binding/spec.md)
- 关联要求：`REQ-007`
- 关联验收：`SIT-001`、`SIT-003`

<a id="dec-004"></a>
### DEC-004 Host authority、风险 obligations 与参与者权利 fail-closed

- 决策：Host/Organizer authority 由 Persona/Circle/Entity owner 证明；发布义务由风险决策返回，不按活动类型白名单。普通管理依赖未撤销 OrganizerAssignment，新增/转移 authority 与安全事件 fail-closed，Participation 不赋予 mutual。
- owner evaluation 是三条 internal typed query：Persona 只认可 active 本人，EntityHomepage 只认可 published+claimed 的 owner/manager，Circle 只认可 active Circle 的 owner 或 active admin membership。请求与证据必须逐项携带 `hostSubjectKind/Id/Ref`、`actorPersonaId`、`organizerPersonaId`、`authorityEvidenceRef/version` 与 action；响应追加 owner digest、短时 expiry、valid/revoked。`create_draft/publish` 要求 actor=organizer，`assign_organizer/transfer_organizer` 由当前 owner authority 验证 actor 并明确目标 organizer。
- canonical reference 固定为 `<hostSubjectKind>:<hostSubjectId>`。
- Persona evidence ref 为 `persona:<id>:self`，EntityHomepage/Circle 为 `<kind>:<id>:authority:<actorPersonaId>`。
- authority version 分别绑定 Persona aggregate、Homepage aggregate、Circle owner aggregate 或 admin CircleMembership aggregate。owner 当前版本、角色、状态、撤销或 expiry 任一不匹配都返回无效/撤销证据，Circle 不做角色推断且不得降级。
- 理由：陌生人活动安全来自披露、资质、装备、天气、商业与应急义务，以及 Block/Report/撤权/申诉，而不是实名徽章、垂类名或默认关系。
- 被否决方案：信任客户端 ownerId、按 activity type denylist、加入后自动 mutual、移除后立即抹去通知与申诉。
- 影响 Story：三个直接 Story。
- 关联要求：`REQ-004`、`REQ-009`
- 关联验收：`SIT-003`

<a id="dec-005"></a>
### DEC-005 公开发现与内容回流只传 canonical reference

- 决策：Circle 签发 Gathering 公开投影；Recommendation 只排序，Surface wrapper 只保存 reference/placement/reason。完成后 Circle 输出 Outcome/Experience reference，用户确认后 Content owner 创建 Post/Media，Report 仍归 Content Trust Safety。
- 理由：发现和回流需要连接活动与内容，但 Feed 或 Content 若保存可写活动状态会与 Circle 漂移，Circle 若复制 Post/Report 又会破坏内容与安全治理。
- 被否决方案：Gathering 作为第五种 Post、Recommendation 直接创建 Participation、Board 或 Feed 回写活动、Circle 新建 GatheringReport。
- 影响 Story：[`gathering-lifecycle`](./gathering-lifecycle/spec.md) 与 [`gathering-conversation-binding`](./gathering-conversation-binding/spec.md)
- 关联要求：`REQ-010`
- 关联验收：`SIT-001`

<a id="dec-006"></a>
### DEC-006 GatheringPlan 独立可选对象经 Gathering owner 委托授权

- 决策：`GatheringPlan` 与现有 Gathering runtime 并行，使用独立 contracts/internal/storage 路径；`gatheringId` 是唯一关联键，同一 Gathering 最多一个 Plan。
- 状态边界：Plan 只拥有 typed items、proposal、current Revision pointer、immutable Revision history、version/digest 与 plan-level acknowledgement refs，不拥有 title、schedule、Host、Participation、capacity、lifecycle、Outcome 或 conversation。
- 授权边界：Plan mutation 通过对象级 delegated owner port 实时读取 Gathering Host/active Participation/lifecycle；不复制成员，不把旧授权缓存为长期写凭据，Gathering 删除或关闭后 fail-closed。
- 并发边界：proposal/commit 必须绑定 expected version 与 base Revision digest，冲突拒绝并刷新/重提，禁止 last-write-wins。Plan/Proposal/Revision、receipt 与 typed event log record 在同一 owner transaction 提交。当前无真实 Assistant/Chat/App consumer，event log 不冒充 transactional outbox。只有 durable consumer 接线并通过 publication、retry 与 checkpoint 验证后才升级为 outbox。
- 确认边界：受影响确认只保存 typed plan-level policy/ref，不写入 Gathering material revision acknowledgement。
- 理由：计划有独立演进频率和协作冲突语义，但参与资格、Host 与生命周期完全依赖活动根；该边界保持 Gathering 稳定并阻止第二活动根。
- 被否决方案：内嵌 GatheringRevision、复制 Host/成员/生命周期的 Plan root、last-write-wins 文档、travel dual-read/compat shim。
- 影响 Story：[`gathering-plan-collaboration`](./gathering-plan-collaboration/spec.md)
- 关联要求：`REQ-001`、`REQ-002`、`REQ-004`、`REQ-006`、`REQ-007`
- 关联验收：`SIT-001`、`SIT-002`、`SIT-003`

## 5. 失败与恢复

- 失败：Host authority/风险义务无效、room provision 未就绪、容量已满、邀请失效、审批拒绝、重大变更未确认、开场后普通取消、Outcome 证据不足、跨域投影或 Content 回流失败。
- 检测：Circle 在 owner transaction/CAS 内判定 Participation、capacity、lifecycle 与 Outcome；Chat/Content 只返回 owner receipt，reconciler 依据 outbox checkpoint 检测投影滞后。
- 可见结果：草稿未发布、待审批、已满、room access 等待、已取消、提前结束、安全终止、未验证与争议结果均可区分，不合并为通用失败。
- 恢复：room/board projection 可按同一 source version 幂等重放；可恢复准入遵循 owner policy，回顾发布失败保留 LocalPostDraft，安全撤权优先于便利性。
- 禁止 fallback：不得裸建群、静默超员、把 Chat membership 当 Participation、把时间到达当 occurred、自动 mutual、双读旧 Trip 或用 Mock/本地状态合成成功。

## 6. 质量与观测

- 隐私：未加入只读取 disclosure 允许的 Host、时间地点范围、容量与要求；名单、精确地点、申请答案、附件和参与事实按最小权限开放，不记录连续轨迹。
- 风控：发起/邀请频控、Host authority、risk obligations、Block/Report、移除审计与申诉必须可用；能力不足时拒绝发布，不按活动名硬编码禁令。
- SLI/SLO：与 L2 spec 的公开详情、准入、room access、Board freshness、超员、撤权、Outcome 和回流目标同源；生命周期/安全/写操作 100% 审计，普通读取按受治理策略采样。
- 告警：任何超员或未授权访问立即告警；10 分钟窗口成功率低于 99% 或投影/撤权 P95 超过 60 秒通知 Circle/Chat 值班。
- flags/rollback：创建、发现、准入、room/board、Outcome/回流独立开关；Circle 为总 rollback owner，Chat/Content 为子链 owner。回滚关闭新写与曝光但保留既有对象的读取、退出、安全处置和完成。

## 7. 迁移与回滚

- 切换顺序：先 contracts/codegen 与 owner runtime，再唯一 room+membership projection，再公开详情/发现与 App composer，最后 Outcome/内容回流和可选能力；前一门未通过不得打开后一 flag。
- 数据处理：旧 Gathering 按 target contract 一次性升级；已退役 travel-service 的历史对象逐对象导入 Gathering/Plan/Experience 目标，环境内一次 target-only 切流，不保留旧值别名、双读或双写，也不为导入恢复源服务。
- 删除的实现：发起结伴落到裸建群、Workspace/第二消息流、自动 mutual 与 Trip 公共根路径在目标能力落地时删除，不作为降级。
- 回滚条件：出现超员、半加入、未授权 room access、Outcome 误计或隐私泄露时立即关闭新创建/发现/准入；回滚到上一验证 artifact/config，但不把切流后增量写回旧源。
