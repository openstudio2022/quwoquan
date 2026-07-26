# L3 Story：搜索无结果时补充主页提交进入候选态 (`missing-homepage-suggestion-and-review`)

> 所属能力：[`homepage-discovery-and-attach`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望搜索无结果时补充主页提交进入候选态，并返回原上下文，从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- suggestHomepage 页最小必要信息提交（SuggestHomepageCandidate）。
- 提交进入 candidate 态，不直接公开。
- 提交后返回搜索/发布上下文。

### Out of Scope

- 候选发布审核后台（homepage-candidate-intake-and-publish 的治理消费面）。
- 认领申请。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 用户补充缺失主页并进入候选待审

- `SuggestHomepageCandidate` 必须幂等接收用户建议；候选在审核发布前不得被普通浏览用户发现。

<a id="req-002"></a>
### REQ-002 补充主页不能直接生成可公开浏览的正式主页

- 补充主页不能直接生成可公开浏览的正式主页。
- 提交失败不能丢失当前已填写内容。
- 如候选审核链路不稳定，可暂时隐藏补充主页入口，但不能用自由文本替代。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户补充缺失主页并进入候选待审

- GIVEN 已登录 persona 在搜索无结果或地点落地页点击「补充主页/提升为主页」。
- WHEN 填写类型、名称等最小信息并提交。
- THEN 服务端以可信 persona 落库 candidate（sourceType=user_suggested），不进入公开搜索。
- THEN 提交失败不丢失已填内容；成功后返回原上下文并有明确反馈。

## 6. 依赖

- 前置要求：[`homepage-discovery-and-attach`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 用户补充缺失主页并进入候选待审

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少直接绑定本节点的候选提交、不可公开浏览与审核状态机真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
