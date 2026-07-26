# L3 Story：治理侧建档并发布候选主页 (`homepage-candidate-intake-and-publish`)

> 所属能力：[`homepage-claim-maintain-and-offline`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望治理侧建档候选主页并发布为公开主页（IntakeHomepageCandidate / PublishHomepageCandidate），从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- 治理 operator 建档候选（数据工程 import 与用户 suggest 之外的人工通道）。
- candidate→published 状态迁移与发布后进入搜索投影。

### Out of Scope

- 数据工程批量导入（homepage-import 通道）。
- 用户侧建议提交（missing-homepage-suggestion-and-review）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 治理 operator 建档并发布候选主页

- 两个治理命令必须由真实 Ops Portal 调用，并遵守权限、审计与发布状态机约束。
- 治理消费面（Ops portal surface）落地并绑定 operation。

<a id="req-002"></a>
### REQ-002 候选主页不能绕过审核直接公开

- 候选主页不能绕过审核直接公开。
- 候选来源必须可追踪。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 治理 operator 建档并发布候选主页

- GIVEN 具备 entity_governance_operator 权限的 account 登录治理消费面。
- WHEN 建档候选并执行 publish。
- THEN 候选以幂等命令落库；publish 后 status=published、进入搜索投影并可被 App 消费。
- THEN 非治理 account 调用被结构化 403 拒绝。

## 6. 依赖

- 前置要求：[`homepage-claim-maintain-and-offline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
