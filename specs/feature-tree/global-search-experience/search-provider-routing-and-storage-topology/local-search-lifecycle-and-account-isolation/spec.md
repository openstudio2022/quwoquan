# L3 Story：本地搜索生命周期与账号隔离 (`local-search-lifecycle-and-account-isolation`)

> 所属能力：[`search-provider-routing-and-storage-topology`](../spec.md)

> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，
我希望本地索引必须按账号命名空间隔离，
从而找到可理解并可继续操作的结果。

## 2. 范围与非目标

### In Scope

- “本地搜索生命周期与账号隔离”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 本地搜索生命周期与账号隔离

- “本地搜索生命周期与账号隔离”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 本地索引必须按账号命名空间隔离

- 本地索引必须按账号命名空间隔离。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 本地搜索生命周期与账号隔离

- GIVEN 执行搜索的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“本地搜索生命周期与账号隔离”对应的公开行为。
- THEN 通过父能力公开契约交付“本地搜索生命周期与账号隔离”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
