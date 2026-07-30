# L3 Story：Gathering 生命周期 (`gathering-lifecycle`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为想约人一起去某个地方的用户，
我希望能发起一次有目标、有时间、可被别人看到并加入的相聚，
从而不必在群里反复喊话也知道到底谁要去。

## 2. 范围与非目标

### In Scope

- Gathering 的发起与其目标对象引用。
- 起始时间与可空结束时间构成的时间区间。
- 开放、已关闭、已取消与已结束之间的状态流转。

### Out of Scope

- 参与者的加入与审批，由 [`gathering-participant-roster`](../gathering-participant-roster/spec.md) 负责。
- 群会话绑定，由 [`gathering-conversation-binding`](../gathering-conversation-binding/spec.md) 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 发起必须绑定目标对象与时间

- 发起 Gathering 必须提供目标对象引用与起始时间；结束时间可空。
- 目标对象引用必须指向真实且可导航的对象。

<a id="req-002"></a>
### REQ-002 时间区间表达确定性差异

- 结束时间为空表示尚未确定的时间窗，起止同时存在表示确定区间；不得引入形态枚举区分两者。

<a id="req-003"></a>
### REQ-003 过期自动结束

- 时间区间过期后状态必须自动流转为已结束，不得停留在开放态，也不得继续接受加入。

<a id="req-004"></a>
### REQ-004 状态终态可区分

- 已关闭、已取消与已结束必须是可区分终态，分别对应发起方主动停止招募、发起方撤销与时间过期。

<a id="req-005"></a>
### REQ-005 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_membership/operations.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 时间窗与时间点由同一聚合表达

- GIVEN 发起方分别发起一次仅有起始时间的相聚与一次有确定起止区间的相聚。
- WHEN 两者被创建。
- THEN 两者是同一类对象，只有时间区间不同。
- AND 不存在区分二者的形态字段。

<a id="gwt-002"></a>
### GWT-002 过期后自动结束且不再接受加入

- GIVEN 一个时间区间已经过去的开放中 Gathering。
- WHEN 状态被重新判定。
- THEN 状态流转为已结束。
- AND 此后的加入请求返回可区分终态而不是成功。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 聚合与其承接页尚不存在

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前没有 Gathering 聚合，也没有对应的详情承接页，发起类行动只能落到裸建群，用户看不到目标、时间与参与者。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
