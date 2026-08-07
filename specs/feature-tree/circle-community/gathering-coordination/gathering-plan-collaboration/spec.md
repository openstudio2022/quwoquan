# L3 Story：Gathering 协作计划与不可变修订 (`gathering-plan-collaboration`)

> 所属能力：[`gathering-coordination`](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)、[`JNY-013 / SCN-031`](../../../spec.md#scn-031)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-006](../design.md#dec-006)

## 1. 用户价值

作为 Gathering 的 Host 或有效参与者，
我希望在同一活动下按需启用协作计划、提出结构化修改并回看不可变历史，
从而让议程、地点、路线、任务、清单与备注保持一致，又不复制活动身份、成员或会话事实。

## 2. 范围与非目标

### In Scope

- 每个 Gathering 最多一个可选 GatheringPlan，Plan 以 current Revision 指针与不可变历史表达当前协作计划。
- typed PlanItem、计划提案、Host commit、CAS、幂等重放、digest、历史读取与计划级受影响确认引用。
- 经 Gathering owner 委托端口校验 Host 与有效 Participation，并在 Gathering 不存在或关闭后 fail-closed。
- Assistant `gathering.propose_plan` 只绑定 canonical `ProposeGatheringPlan`，先产出 ApproveTool，审批后使用 single-use DelegatedCommandGrant 提交 proposal。

### Out of Scope

- Gathering 的 title、schedule、Host、Participation、capacity、lifecycle、Outcome 与 conversation。
- GatheringRevision 的重大活动承诺确认；Plan acknowledgement 不得冒充活动重大变更确认。
- Assistant 自动创建 Plan、接受/拒绝或 commit Proposal；Map/Calendar/Experience 投影、App Board 写入，以及任何已退役 Travel 协议、源快照或 crosswalk 的产品读取。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每个 Gathering 最多一个可选 Plan

- GatheringPlan 必须以 canonical Gathering reference 关联，且同一 gatheringId 最多存在一条当前 Plan。
- Plan 不得拥有或复制 Gathering 的标题、日程、Host、Participation、容量、生命周期、Outcome 或会话；可选 Plan 不可用不得改变 Gathering。

<a id="req-002"></a>
### REQ-002 current Revision 唯一且历史不可变

- Plan 只通过 currentRevisionRef 指向当前写真相源；已提交 PlanRevision 必须不可变、顺序连续并可按稳定游标回看。
- PlanItem 使用 agenda、place、route_segment、task、checklist、note 闭集 typed payload；assignee 与来源只保存 canonical reference，不复制成员或来源对象正文。

<a id="req-003"></a>
### REQ-003 写权限由 Gathering owner 委托裁决

- 创建与 commit 只允许未撤销 Host；proposal 允许 Host 或有效 Participation。所有写入都必须在提交前经 Gathering delegated owner port 重验，不信任客户端角色、成员列表或 Assistant 声明。
- Gathering 不存在、已取消、已完成或 authority/Participation 已变化时拒绝写入；不得因已存在 Plan 或旧授权继续成功。

<a id="req-004"></a>
### REQ-004 提案、commit 与冲突保持单轨

- Proposal 必须绑定当前 Plan version、base Revision number/digest、typed items 与 proposal digest；commit 再次校验同一基线与 expected Plan version。
- CAS 冲突必须返回刷新/重提语义，禁止 last-write-wins；相同幂等键和相同请求重放原结果，相同键不同 digest 必须拒绝且不得追加 Revision。

<a id="req-005"></a>
### REQ-005 受影响确认只属于 Plan

- Revision 可保存 plan-level acknowledgement policy、受影响 Participation canonical refs 与 acknowledgement refs，用于提醒或下游确认。
- 这些字段不得写入 GatheringParticipation 的 material-change acknowledgement，不得推进 GatheringRevision，也不得把计划调整伪装成活动核心承诺变更。

<a id="req-006"></a>
### REQ-006 owner state、receipt 与 typed transactional event log 原子

- 创建、proposal 与 commit 的 Plan/Proposal/Revision、command receipt 与 typed event log record 必须在同一 owner transaction 提交；event log 只证明 owner 事实已原子留存，不声明事件已经可投递或已有 consumer。
- 重放不得产生第二 Plan、第二 Proposal、重复 Revision 或重复 event log record；存储失败不得返回成功。
- 在 Assistant、Chat 或 App 至少一个真实 durable consumer 接线，并由 publication、retry 与 checkpoint 证据证明可恢复投递前，不得把该 event log 声明为 transactional outbox。

<a id="req-007"></a>
### REQ-007 服务本地契约引用边界

- 字段、operation、event、error、metric 与恢复语义只引用 Circle 服务本地 contracts；本节点不得复制 DTO/wire 定义。
- Assistant 只登记并执行 canonical `ProposeGatheringPlan`：确认前仅产生 typed proposal 与 ApproveTool，确认后才消费 single-use DelegatedCommandGrant；不得自行构造 Host authority，也不得自动 create/accept/reject/commit。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/object.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/events.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/errors.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 创建、提案、commit 与历史保持不可变

- GIVEN 一个已发布 Gathering 的 Host 创建可选 Plan，有效参与者基于 current Revision 提出 typed items。
- WHEN Host 以匹配的 expected version、revision digest 与 proposal digest commit。
- THEN 同一 gatheringId 只有一个 Plan，current pointer 原子推进到连续的新 Revision，旧 Revision 内容与 digest 保持不变且历史可读。
- AND Plan 不包含 Gathering title、schedule、Host、Participation、capacity、lifecycle 或 conversation 副本。

<a id="gwt-002"></a>
### GWT-002 CAS、幂等重放与越权 fail-closed

- GIVEN 两个基于同一 current Revision 的并发提案，以及非成员、已退出参与者和非 Host actor。
- WHEN 它们分别尝试 proposal 或 commit，并重放相同/不同 digest 的幂等键。
- THEN 只有匹配 CAS 且有权的命令成功；相同请求重放原 receipt，不同请求拒绝，越权或过期角色零写入。
- AND 冲突不得覆盖 current Revision，也不得创建重复 Revision 或 typed event log record。

<a id="gwt-003"></a>
### GWT-003 Gathering 关闭后写入拒绝且 Plan 确认不冒充重大变更

- GIVEN 一个已有 Plan history 的 Gathering 被删除、取消或完成，且最新 Revision 含受影响 Participation 与 acknowledgement refs。
- WHEN 原 Host 或参与者继续 proposal/commit，或下游读取确认语义。
- THEN delegated owner port fail-closed 拒绝新写，已提交 Revision history 保持不可变。
- AND acknowledgement 仍明确属于 Plan revision，不修改 GatheringRevision 或 GatheringParticipation 的 material-change acknowledgement。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的 owner、Participation、lifecycle 与 room/board 边界。
- 下游结果：Chat Board、Assistant 与旅行体验只消费本 Story 的 canonical Plan operation/event/reference。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-006](../design.md#dec-006)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 GatheringPlan 商用品质三层证据尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Chat Board、App production Remote、真实 durable consumer 与 user_acceptance 接线。对象 contracts/runtime、generated Go、Assistant proposal dispatcher/local_contract、真实 Mongo API 与 owner-transaction typed event log 可先落地，但当前 event log 不得冒充 transactional outbox，canonical operation 也不能标记为 commercial ready。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 由对象 local_contract、真实 api_integration 与跨域 user_acceptance 直接覆盖。Circle/Assistant/Chat/App 使用同一 Plan revision/digest，且无越权、last-write-wins、第二活动根或 travel fallback。至少一个真实 consumer 完成 publication、retry 与 checkpoint 的可恢复投递验证后，才可声明 transactional outbox。
- 依赖：Gathering owner delegated port、Chat Board 与 production Remote App。
