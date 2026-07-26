# L2 Business Capability：圈子动态与成员治理 (`activity-member-governance`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“activity-member-governance”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-008 / SCN-014`](../../spec.md#scn-014)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-011 / SCN-027`](../../spec.md#scn-027)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`activity-stream-paging`](./activity-stream-paging/spec.md)：定义“动态流式分页”的可观察主路径、失败语义及父能力交接。
- [`circle-lifecycle`](./circle-lifecycle/spec.md)：定义“圈子生命周期”的可观察主路径、失败语义及父能力交接。
- [`member-role-permission`](./member-role-permission/spec.md)：加入与退出可先反馈进行中状态；失败时回滚展示，成功时以服务端成员事实收敛。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 activity member governance 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 跨边界字段、operation 与错误语义只引用所属服务 contracts

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 需审批圈子的入圈申请与成员计数一致

- `joinPolicy=approval` 的入圈动作必须先生成 pending 成员事实，只允许 owner 或 active admin 读取申请队列并执行通过/拒绝。
- 通过将 pending 原子收口为 active，拒绝将其收口为 rejected；非 pending 状态的审批必须失败，重放不得重复增加成员数。
- App 审批页必须展示 pending 队列、通过/拒绝动作、空态与可重试错误态，不得使用本地假审批。

## 6. 契约与依赖

- 上游能力：[`circle-community`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 activity member governance 能力 SIT

- GIVEN 执行“activity member governance 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“activity member governance 能力”对应动作。
- THEN 直属 Story 共同交付“让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态”，失败终态可区分且不产生伪成功事实。
- THEN approval 圈子的申请进入 pending，非管理员无法读取或审批，通过/拒绝状态迁移幂等且只有 active 成员计入 memberCount。
- THEN App 审批页在加载、空队列、错误与成功审批后都展示与服务端事实一致的可观察结果。
