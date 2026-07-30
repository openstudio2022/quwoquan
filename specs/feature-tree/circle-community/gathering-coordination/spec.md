# L2 Business Capability：结伴与线下相聚协调 (`gathering-coordination`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：`本层 design.md`

## 1. 能力目标

让「有人一起去吗」从一句话变成一个可加入、有名单、有时间、有绑定会话的真实对象，使交集行动阶梯的同行与线下两级有可承接的终点。结伴同行与线下相聚由同一个 Gathering 表达，两者只在时间确定性上不同，不构成两种对象。

## 2. 范围与非目标

### In Scope

- Gathering 的发起、状态流转与过期归档。
- 参与者的加入、审批、退出与容量边界。
- Gathering 与其群会话的绑定关系。

### Out of Scope

- 会话内的消息投递与实时通话，由 [`chat-conversation`](../../chat-conversation/spec.md) 负责；Gathering 只持有会话引用，不拥有消息。
- 交集的识别与行动提示登记，由 `object-homepage-network` 与 `recommendation-platform` 负责。
- 目标对象自身的主页与事实，由 `object-homepage-network` 负责。
- 实时位置与附近相遇：数据源未就绪，本能力不提供伪承接。

## 3. Journey / Scenario 贡献

- [`JNY-011 / SCN-027`](../../spec.md#scn-027)
  - 本能力接收：来自交集行动阶梯的发起或加入意图与目标对象引用。
  - 本能力处理：创建或加入 Gathering，维护参与者名单与状态，并绑定其群会话。
  - 本能力输出：一个可加入、有名单、有时间的 Gathering 及其可进入的群会话。
  - 失败时终态：容量已满、审批拒绝或已取消时给出可区分终态，不产生半加入状态。

## 4. Story

- [`gathering-lifecycle`](./gathering-lifecycle/spec.md)：发起一次结伴或线下相聚并管理其状态直至结束。
- [`gathering-participant-roster`](./gathering-participant-roster/spec.md)：加入、审批与退出，并看到真实的同行名单。
- [`gathering-conversation-binding`](./gathering-conversation-binding/spec.md)：加入后进入绑定群会话协调具体安排。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 结伴与线下相聚由同一聚合表达

- 结伴同行与线下相聚必须由同一个 Gathering 表达，二者的差别只体现在时间区间的确定性上。
- 不得引入形态枚举，也不得为线下相聚新建第二个聚合。

<a id="req-002"></a>
### REQ-002 时间区间同时表达时间窗与时间点

- Gathering 必须以起始时间与可空结束时间表达时间；结束时间为空表示一个尚未确定的时间窗，两者同时存在表示一个确定区间。
- 时间区间过期后状态必须自动流转为已结束，不得停留在开放态。

<a id="req-003"></a>
### REQ-003 Gathering 不拥有消息

- Gathering 只持有其群会话引用，不拥有消息、成员资格或通话事实；这些事实由消息域拥有。

<a id="req-004"></a>
### REQ-004 审批状态机复用既有圈子成员先例

- 参与者的待审批、已加入、已退出与已拒绝状态必须与圈子成员治理保持同一套语义，不得发明新的状态机。

<a id="req-005"></a>
### REQ-005 实时语音复用绑定会话内既有群通话

- 语音房必须复用绑定群会话内既有的群通话入口；不得新建语音房聚合，也不得为其新增独立行动键。

<a id="req-006"></a>
### REQ-006 服务本地契约引用边界

- 跨边界字段、operation、事件与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 6. 契约与依赖

- 上游能力：`recommendation-platform` 提供发起与加入的行动提示；`object-homepage-network` 提供目标对象事实。
- 下游能力：本目录直接 Story 及其公开结果；`chat-conversation` 承接绑定会话内的协调与通话。
- 读取事实：目标对象引用、发起方身份与关系门禁结果。
- 写入事实：Gathering 状态、参与者名单与会话绑定关系。
- operation / event / surface：`quwoquan_service/services/circle-service/contracts/circle_management/circle_membership/operations.yaml`、`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- 一致性要求：参与者计数是名单的投影而非独立事实；容量判定以名单为准。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 发起到实时的完整升级

- GIVEN 两个账号之间存在成立的交集，且发起方从交集行动入口发起 Gathering。
- WHEN 另一方加入该 Gathering 并进入其绑定群会话。
- THEN 双方在同一群会话中可协调安排并可发起群通话。
- AND 全程不产生独立的语音房对象，通话复用绑定会话内既有入口。

<a id="sit-002"></a>
### SIT-002 容量、重复加入、取消与审批的边界一致

- GIVEN 一个设有容量上限且需要审批的 Gathering。
- WHEN 多个账号并发申请加入，其中包含重复申请，且发起方在此期间取消该 Gathering。
- THEN 加入结果不超过容量上限，重复申请不产生第二条名单记录，取消后的申请返回可区分终态。
- AND 不产生半加入状态或名单与计数不一致的情形。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 Gathering 聚合尚不存在

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前交集行动阶梯的同行与线下两级没有任何承接对象，发起结伴只能落到裸建群，加入类行动全部处于不可承接状态。行动阶梯在这两级上断开。
- 完成判定：`SIT-001` 与 `SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 附近相遇缺少稳定实时位置数据源

- 类型：`capability_gap`
- 优先级：`P3`
- 准出影响：`track`
- 影响或价值：缺少稳定的实时模糊位置数据源，且该类功能的价值取决于同城活跃用户密度，密度不足时「附近同趣」对所有人都成立因而零信息量。持续位置上报同时带来最高等级的隐私成本。
- 完成判定：同城活跃用户密度达到可用门槛且实时模糊位置数据源具备稳定供给后，再评估是否将相关行动转为可承接
- 依赖：`recommendation-platform` 的交集类型登记保持其不可承接状态不变
