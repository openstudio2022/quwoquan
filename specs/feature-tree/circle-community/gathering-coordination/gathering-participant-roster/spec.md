# L3 Story：Gathering 参与者名单 (`gathering-participant-roster`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为想加入一次相聚的用户，
我希望知道自己是不是真的加上了、还有多少位置、以及都有谁去，
从而不用一直追问发起人也能确定自己的行程。

## 2. 范围与非目标

### In Scope

- 加入申请、审批、退出与拒绝的状态流转。
- 容量上限与加入策略的判定。
- 参与者名单与计数的展示口径。

### Out of Scope

- Gathering 自身的状态流转，由 [`gathering-lifecycle`](../gathering-lifecycle/spec.md) 负责。
- 群会话成员同步，由 [`gathering-conversation-binding`](../gathering-conversation-binding/spec.md) 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 加入策略决定是否经过待审批

- 开放加入策略下申请直接成为已加入；需审批策略下申请先进入待审批，由发起方决定通过或拒绝。

<a id="req-002"></a>
### REQ-002 容量上限不得被并发越过

- 已加入人数不得超过容量上限；并发申请必须在名单写入的同一事务内完成容量判定。

<a id="req-003"></a>
### REQ-003 重复申请幂等

- 同一账号对同一 Gathering 的重复申请不得产生第二条名单记录。

<a id="req-004"></a>
### REQ-004 计数是名单的投影

- 参与者计数必须由名单派生，不得作为独立可写事实保存；名单与计数不得出现不一致。

<a id="req-005"></a>
### REQ-005 终态可区分且可恢复

- 容量已满、已取消、审批拒绝必须是可区分终态；被拒绝或已退出的账号可再次申请。
- 不得产生半加入状态。

<a id="req-006"></a>
### REQ-006 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/errors.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 并发申请不越过容量且重复申请幂等

- GIVEN 一个剩余名额有限的 Gathering。
- WHEN 多个账号并发申请加入，其中包含同一账号的重复申请。
- THEN 已加入人数不超过容量上限，重复申请不产生第二条名单记录。
- AND 超出容量的申请返回容量已满终态而不是通用失败。

<a id="gwt-002"></a>
### GWT-002 审批拒绝与已取消是不同终态

- GIVEN 一个需审批的 Gathering，其中一位申请者被拒绝，随后发起方取消该 Gathering。
- WHEN 被拒绝者与新申请者分别查看结果。
- THEN 被拒绝者得到审批拒绝终态，新申请者得到已取消终态。
- AND 被拒绝者在 Gathering 仍开放时可再次申请。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-004](../design.md#dec-004)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 参与者名单尚未进入真实会话同步链

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺真实 Chat durable membership projector、Circle API composition 与 App 名单页；参与者值对象、容量/幂等/审批/退出裁决和事务 Store 已落地，本地 saga 测试证明 Chat 写失败不会伪造 joined。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
