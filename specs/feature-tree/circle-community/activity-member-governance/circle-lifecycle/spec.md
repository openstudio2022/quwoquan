# L3 Story：圈子生命周期 (`circle-lifecycle`)

> 所属能力：[`activity-member-governance`](../spec.md)

> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为圈子成员或圈子运营者，
我希望圈子创建、更新、归档和恢复都遵循 owner 权限与明确状态机，
从而完成可治理的社区协作。

## 2. 范围与非目标

### In Scope

- “圈子生命周期”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 圈子生命周期

- “圈子生命周期”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 圈子生命周期

- GIVEN 圈子成员或圈子运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“圈子生命周期”对应的公开行为。
- THEN 通过父能力公开契约交付“圈子生命周期”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 圈子生命周期 Remote API 状态与幂等收敛

- GIVEN 已认证 owner 通过 generated client 与 production Remote 调用 Circle 公开 operation，且服务依赖可用。
- WHEN 同一幂等身份依次创建并重放创建、更新、读取、归档，再重放无状态变化的命令。
- THEN 每次响应与最终读取均收敛到服务端 canonical Circle 状态，重放不产生第二个 Circle、额外版本推进或重复领域事实。
- AND 缺少环境配置、身份或依赖时 fail closed，不以本地 fixture、缓存对象或空成功替代 Remote 结果。

## 6. 依赖

- 前置要求：[`activity-member-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

- 无。
