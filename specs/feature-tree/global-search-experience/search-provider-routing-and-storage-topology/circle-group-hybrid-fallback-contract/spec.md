# L3 Story：Circle 讨论本地回退契约 (`circle-group-hybrid-fallback-contract`)

> 所属能力：[`search-provider-routing-and-storage-topology`](../spec.md)

> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为搜索圈子或讨论的用户，
我希望在云侧搜索不可用时获得明确标记的本地回退结果，
从而继续找到可用对象且不会把降级结果误认为完整云结果。

## 2. 范围与非目标

### In Scope

- Circle 讨论本地回退的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Circle 讨论本地回退契约

- fallback 必须返回 typed `resolvedFrom=local_fallback`。

<a id="req-002"></a>
### REQ-002 fallback 必须返回 typed resolvedFrom=local_fallback

- fallback 必须返回 typed `resolvedFrom=local_fallback`。
- 页面不得直接决定 fallback。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Circle 讨论本地回退契约

- GIVEN 执行搜索的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行 Circle 讨论本地回退对应的公开行为。
- THEN fallback 必须返回 typed `resolvedFrom=local_fallback`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`search-provider-routing-and-storage-topology`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
