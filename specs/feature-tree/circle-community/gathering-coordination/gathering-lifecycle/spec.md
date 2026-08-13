# L3 Story：Gathering 生命周期 (`gathering-lifecycle`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)、[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为具有真实 authority 的 Host，
我希望从内容、C 位、主页或会话发起同一个可发布、可变更、可取消或完成的 Gathering，
从而让 1:1、多人兴趣活动和多日行程都具有可信承诺、可区分终态与可验证 Outcome。

## 2. 范围与非目标

### In Scope

- Gathering 的 Host authority、草稿、room-ready 发布与公开来源引用。
- lifecycle 与派生时间阶段/准入状态、GatheringRevision、重大变更、取消/提前结束/安全终止、完成与 Outcome。
- 公开详情允许披露的核心承诺，以及完成后回顾内容所需 canonical activity reference。

### Out of Scope

- Participation 的邀请、申请、加入、容量与名单，由 [`gathering-participant-roster`](../gathering-participant-roster/spec.md) 负责。
- 群会话绑定，由 [`gathering-conversation-binding`](../gathering-conversation-binding/spec.md) 负责。
- Message、Announcement、Post、Media、Report、推荐排序与 Persona 关系。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 单一 Gathering 覆盖所有 Host、人数与行程

- Persona、Circle、创作者与具备 authority 的 Entity Host 发起的 1:1、多人和多日活动复用同一 Gathering。
- 来源可引用内容、主页、Circle、地点、路线、会话或模板，但必须可验证、可导航并遵循 owner 可见性；来源差异不得产生活动类型枚举或第二根。

<a id="req-002"></a>
### REQ-002 发布前验证 Host、承诺、风险与 room ready

- 草稿可以渐进补全；发布必须具有可验证 Host authority、确认日程、容量/准入/披露、必要风险 obligations 与唯一 room binding ready。
- 任一前置不成立时保持草稿，不得公开、接受响应或以普通群聊替代活动。

<a id="req-003"></a>
### REQ-003 lifecycle 与派生阶段分离

- lifecycle 只表达草稿、已发布、已取消与已完成；时间阶段和 admission 从日程、政策、容量、截止时间及暂停位派生。
- 满员、进行中、结束时间到达不得写成可漂移 lifecycle；时间到达关闭普通准入并触发 reconciliation，但不自动产生 occurred。

<a id="req-004"></a>
### REQ-004 GatheringRevision 保护重大承诺

- 有有效参与者后，时间、精确地点、Host、费用、难度、要求或人数承诺变化必须形成新 GatheringRevision，并触发每条受影响 Participation 分别确认。
- 进行中只允许 canonical policy 规定的现场/安全更新，不得静默改写核心承诺；Plan Revision 不得代替 GatheringRevision。

<a id="req-005"></a>
### REQ-005 取消、提前结束、安全终止、完成与 Outcome 可区分

- 普通取消只允许开场前；开场后使用个人提前离开、Host 提前结束或 Trust & Safety 安全终止，不得恢复招募或伪装成取消。
- completed 与真实发生分离；occurred 必须具有独立参与证据，时间到达、Host 单方声明或 reconciler 只能形成 canonical 未验证结果，不得计入有效参与指标。
- 被取消、提前结束或安全终止的参与者仍可读取裁剪通知、举报与申诉入口。

<a id="req-006"></a>
### REQ-006 生命周期不自动建立关系

- Gathering 完成、occurred、共同 Experience 或回顾发布均不得自动建立 Follow、mutual、CircleMembership 或普通 direct conversation；关系由 User owner 的独立动作决定。

<a id="req-007"></a>
### REQ-007 服务本地契约引用边界

- 字段、operation、route、surface、event、error、metric 与恢复语义只引用所属服务 contracts 或跨服务 metadata；本节点不得复制 wire 定义。

<a id="req-008"></a>
### REQ-008 旅行与校园仅以正交体验配置复用 Gathering

- 旅行多人多日计划与新生同校兴趣活动必须引用同一个 Gathering 行为合同、分发场景、Placement、官方 Skill、operation、route、surface 与 tool；不得新增校园服务、校园领域对象或复制 Gathering/Skill/Presentation。
- 场景差异只允许来自 canonical Topic/tag、来源对象、策略参数和 immutable ExperiencePackage 配置；观测只按 `topicRef` 归因，不建立垂类业务分支。
- 校园内容、Entity 与 tag 必须经 `quwoquan_data` canonical publish、immutable release 和环境 importer 激活；缺 release/import receipt 与 Remote readback 时 UAT 保持 OPEN，不得用 fixture 进入 production composition。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/errors.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/ui_config.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
- canonical taxonomy：`quwoquan_data/control_plane/governance/taxonomy/Topic/教育成长/校园生活/社团活动/_definition.json`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 旅行与校园复用同一 Gathering 行为合同

- GIVEN 旅行 profile 发起多人多日计划，校园 profile 从学校 Entity、校园 Post 或 Circle 发起新生同校兴趣活动。
- WHEN 两者完成 Gathering create/discovery/approval/chat/board/plan/outcome 流程。
- THEN 两者解析到同一 Gathering root、行为合同以及同一 operation/route/surface/tool ID 集合，只有 Topic/tag、来源和策略配置不同。
- AND 不存在 Activity/Meet/Trip 第二活动根、校园服务、校园领域对象、复制的 Skill/Presentation 或裸建群发布路径。

<a id="gwt-002"></a>
### GWT-002 开场后普通取消被拒绝且 Outcome 不自动 occurred

- GIVEN 一个已经开场且随后到达结束时间的已发布 Gathering。
- WHEN Host 尝试普通取消，reconciler 评估结束，且只有 Host 单方声明完成。
- THEN 普通取消被稳定拒绝、普通准入保持关闭，reconciler 只能形成 canonical 未验证结果。
- AND 只有满足独立参与证据后才能形成 occurred；参与不会自动产生 mutual。

<a id="gwt-003"></a>
### GWT-003 重大变更逐人确认并可安全退出

- GIVEN 一个已有有效参与者的 Gathering 修改时间、精确地点或 Host。
- WHEN Host 提交新 GatheringRevision，参与者分别接受、拒绝或逾期。
- THEN 每条 Participation 绑定同一 Revision 形成独立确认结果，拒绝/逾期者按 owner policy 退出并撤销访问。
- AND 多人和 capacity=2 都不要求群体 unanimous，也不静默视为同意。

<a id="gwt-004"></a>
### GWT-004 CreateGatheringDraft 只创建未发布草稿

- GIVEN actor 具有可验证 Host authority，来源、日程与披露输入可由 owner 校验。
- WHEN actor 以同一意图重复调用 `CreateGatheringDraft`，并以同一幂等身份提交冲突输入。
- THEN 首次调用只创建一个 unpublished Gathering draft，返回的 typed owner identity 与 version 可由后续 owner readback 读回。
- AND 完全重放返回同一结果，冲突输入返回 canonical idempotency failure 且不创建第二个 Gathering 或公开投影。

<a id="gwt-005"></a>
### GWT-005 GetGathering 只向有权 viewer 返回 private detail

- GIVEN 同一 Gathering 分别由当前 Organizer、有效参与者、已撤权参与者与无关 Persona 读取。
- WHEN viewer 调用 `GetGathering`。
- THEN 当前 Organizer 或有权参与者获得与 owner version 一致、按 viewer disclosure 裁剪的 typed private detail。
- AND 已撤权或无关 viewer 返回 canonical access failure，不泄露申请答案、名单、精确地点或其他 private 字段。

<a id="gwt-006"></a>
### GWT-006 ListGatheringsByHost 按 canonical Host identity 分页

- GIVEN 同一 Host 下存在 draft、published、cancelled 与不同 disclosure 的 Gathering，另有其他 Host 的公开活动。
- WHEN public viewer 以 canonical Host identity 调用 `ListGatheringsByHost` 并翻页。
- THEN typed page 只包含该 Host 已公开且当前仍可披露的 `published`、`cancelled` 或 `completed` Gathering，保留真实 lifecycle/Outcome，不包含 draft、private 或其他 Host 条目；cursor 重放保持稳定且不重复。
- AND 形状合法但没有匹配项的 Host identity 返回 typed empty page；Host kind/identity 形状无效或 owner store 失败时返回 canonical failure，不把依赖失败伪装成空页。

<a id="gwt-007"></a>
### GWT-007 ListGatheringsBySource 按 canonical source identity 分页

- GIVEN 多个 Gathering 已在 authoring/publish 边界把可导航、遵守 owner 可见性的 Post、Homepage、Circle 或地点冻结为 canonical source identity 与 source digest。
- WHEN public viewer 以 canonical source identity 调用 `ListGatheringsBySource` 并翻页。
- THEN typed page 只包含精确引用该冻结 source identity、已公开且当前为 `published`、`cancelled` 或 `completed` 的 Gathering；列表不在读路径重新解释 source 类型或复制 source 展示事实，cursor 重放保持稳定且不重复。
- AND 形状合法但没有匹配项的 source identity 返回 typed empty page；source identity 形状无效或 Gathering owner store 失败时返回 canonical failure，不回退到模糊类型匹配或其他来源结果。

<a id="gwt-008"></a>
### GWT-008 AssignGatheringCoHost 只授予独立管理权

- GIVEN primary Organizer 持有当前 Gathering version，目标 Persona 具有有效 Host authority 且可被任命。
- WHEN primary Organizer 调用 `AssignGatheringCoHost` 并重放同一意图。
- THEN 目标只获得该 Gathering 的 co-host 管理能力，独立 Participation、席位和关系事实保持不变。
- AND 重放返回同一结果，越权、无效 authority 或陈旧 version 返回 canonical failure 且不产生部分 Chat admin access。

<a id="gwt-009"></a>
### GWT-009 RevokeGatheringCoHost 只撤销 OrganizerAssignment

- GIVEN 一名 Persona 持有当前 co-host `OrganizerAssignment` 且可能同时拥有独立有效 Participation，primary Organizer 持有当前 Gathering aggregate version。
- WHEN primary Organizer 以 `coHostPersonaId` 与 `expectedGatheringVersion` 调用专用 `RevokeGatheringCoHost` command 并重放同一意图。
- THEN 该 Persona 的 co-host 管理能力被撤销，独立 Participation、席位和普通参与访问保持 owner 合同规定的状态。
- AND 该 command 不得复用 Participation command wire，也不得携带或校验 `participantPersonaId`、`expectedParticipationVersion`；重放返回同一结果，越权或陈旧 aggregate version 返回 canonical failure 且不撤销其他 Organizer 或参与者权限。

<a id="gwt-010"></a>
### GWT-010 TransferGatheringOrganizer 原子转移 primary authority

- GIVEN 尚未开场的 Gathering 具有当前 primary Organizer，目标 Persona 具有可验证 Host authority。
- WHEN current primary Organizer 以当前 version 调用 `TransferGatheringOrganizer`。
- THEN primary authority 原子转移到目标并形成 material GatheringRevision；不得创建、删除或改变双方及其他人的 Participation identity、state 或 seat，已有 active Participation 只安装该 material revision 的 `pending` acknowledgement 并推进自身 version。
- AND 越权、无效 authority、开场后请求或陈旧 version 返回 canonical failure，不留下双 primary 或部分 Chat admin projection。

<a id="gwt-011"></a>
### GWT-011 CancelGathering 只允许开场前取消

- GIVEN upcoming 与已经开场的 Gathering 各自持有当前 owner version。
- WHEN 有权 Organizer 调用 `CancelGathering` 并重放同一意图。
- THEN upcoming Gathering 进入 cancelled 终态并关闭准入，相关访问撤销意图与 owner command receipt 在同一一致性结果中可审计。
- AND 开场后、越权或陈旧 version 请求返回 canonical failure，不能伪装成提前结束或安全终止，重放不产生第二终态。

<a id="gwt-012"></a>
### GWT-012 CompleteGathering 只终结 ended 活动并独立计算 Outcome

- GIVEN ended Gathering 包含充分、缺失或互相冲突的独立参与证据，Organizer 或 reconciler 持有当前 version。
- WHEN actor 调用 `CompleteGathering` 并重放同一意图。
- THEN 合法请求把 lifecycle 收敛为 completed，Outcome 由 Circle 按参与证据计算且 completed 本身不等于 occurred。
- AND 证据不足或争议保持 canonical unverified/disputed 结果，越权、陈旧或重复请求不伪造 occurred、关系事实或第二完成记录。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)、[L2 DEC-004](../design.md#dec-004)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Gathering 生命周期、Revision 与 Outcome 目标合同未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 尚缺实现：完整 lifecycle/temporal/admission reconciliation、GatheringRevision 跨域确认、证据化 Outcome production UAT 及校园 canonical release/import readback 尚未闭环。
- 影响或价值：尚缺 lifecycle/temporal/admission 分离、room-ready publish、GatheringRevision、开场后取消边界、证据化 Outcome，以及校园 canonical 数据 release/import 与 production Remote UAT；metadata/local_contract 已证明旅行与校园 profile 复用同一行为合同。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003`、`GWT-004`、`GWT-005`、`GWT-006`、`GWT-007`、`GWT-008`、`GWT-009`、`GWT-010`、`GWT-011`、`GWT-012` 由 Circle local_contract、api_integration 与跨域 user_acceptance 直接覆盖；校园 Post/Entity/tag 绑定同一 immutable release、环境 import receipt 与 Remote readback，且 occurred 误计、第二活动根、自动 mutual、专用校园对象/服务与开场后普通取消均为零。
- 依赖：父 L2 `OPEN-001`、`OPEN-002`，`quwoquan_data` 校园 canonical release/import，以及后续真实账号 Remote UAT。

<a id="open-002"></a>
### OPEN-002 gathering_control_required 声明了发射点但实现无业务发射

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前 `CIRCLE.USER.gathering_control_required` 在 errors.yaml 声明由 PublishGathering/SafetyTerminateGathering 发射，但 `internal/**` 没有任何业务代码路径发射它——只有 `mapLifecycleError` 的映射分支存在。错误码断言测试已经映射合约锚定该分支（`gathering_error_code_mapping__local_contract_test.go`），但「控制权限不足时拒绝发布/安全终止」这条业务语义本身缺实现或缺契约收敛（删码）。
- 完成判定：`GWT-012` 相关的控制权限语义二选一收敛——PublishGathering/SafetyTerminateGathering 的授权路径真实发射该码并有真实测试 `spec_ref` 断言业务触发；或契约裁决该码冗余并从 errors.yaml 删除（同步删除映射分支与测试）。
