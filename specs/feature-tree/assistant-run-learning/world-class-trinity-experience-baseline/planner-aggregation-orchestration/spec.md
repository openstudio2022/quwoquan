# L3 Story：编排决策与答案边界裁决 (`planner-aggregation-orchestration`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为向小趣提问的用户，我希望关键信息不足时它先反问确认而不是硬答，跨多个领域的问题被分头处理后合并成一个结论，并且证据不足时明确告诉我边界而不是编造。

## 2. 范围与非目标

### In Scope

- 每一步的下一步动作决策，含向用户反问
- 单技能与多技能统一编排面
- 聚合状态裁决最终答案模式与信息边界

### Out of Scope

- 用户可见的编排配置界面
- 技能内部的检索实现
- 跨会话的长期计划持久化

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 关键信息不足时反问而不是硬答

- 回答所需的关键信息缺失且无法从上下文推断时，该次运行必须以向用户反问收尾。
- 反问必须是可直接回答的具体问题，不得把内部推理或提示内容暴露给用户。
- 用户补充信息后必须在同一会话延续原目标，不得要求用户重述整个问题。

<a id="req-002"></a>
### REQ-002 单技能与多技能使用同一编排面

- 单技能与多技能问题必须通过同一编排面表达，每个技能执行产生独立的执行记录与停止原因。
- 多技能并行执行必须各自受独立的时限与工具预算约束，单个分支失败不得使整轮失败。
- 分支之间的依赖顺序必须显式声明，不得依赖执行顺序的隐含约定。

<a id="req-003"></a>
### REQ-003 聚合状态裁决答案模式与边界

- 最终答案模式必须由统一的聚合状态裁决，可区分完整回答、有边界回答、需要反问、需要重规划与拒答。
- 拒答与有边界回答必须说明缺失的信息范围，不得以完整回答的形式呈现未验证内容。
- 过程叙述必须表达当前编排阶段与原因，且不得携带内部推理、提示原文或凭据。

<a id="req-004"></a>
### REQ-004 用户意图先形成冻结的检索计划再调用研究工具

- 需要站内或公开网事实时，编排必须先把目标、分维度检索词、对象范围、证据充分条件和最大查询数收敛为 `RetrievalPlan`，再显式选择 canonical Tool。
- 计划必须绑定 Run、Turn、冻结 Tool metadata、对象访问策略、工具调用预算、候选与 ContractGraph，并以 digest 防止执行后静默改写。
- 证据不足时只能在剩余预算内形成新计划；预算耗尽时必须基于已有证据给出有边界终态或反问，不得隐式增加查询。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/_shared/aggregation_state/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/skill_run/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/subagent_plan/schema.yaml`
- event：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_stream_event/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 关键信息缺失时先反问

- GIVEN 用户提出的问题缺少回答所必需的关键信息且无法从上下文推断
- WHEN 该次运行执行编排决策
- THEN 该次运行以向用户反问收尾，且反问是可直接回答的具体问题
- THEN 过程叙述不包含内部推理或提示原文
- THEN 用户补充信息后在同一会话延续原目标

<a id="gwt-002"></a>
### GWT-002 多领域问题分头处理后合并

- GIVEN 用户提出同时涉及两个领域的问题
- WHEN 该次运行按编排面分派多个技能执行
- THEN 每个技能执行产生独立执行记录与停止原因，并各自受独立时限与工具预算约束
- THEN 单个分支失败时其余分支结果仍被合并为一个结论
- THEN 合并结论由聚合状态裁决为完整回答或有边界回答

<a id="gwt-003"></a>
### GWT-003 证据不足时给出边界而不是编造

- GIVEN 该次运行检索到的证据不足以支撑完整回答
- WHEN 聚合状态裁决最终答案模式
- THEN 回答以有边界回答或拒答呈现并说明缺失的信息范围
- THEN 未验证内容不以完整回答的形式呈现

<a id="gwt-004"></a>
### GWT-004 检索调用可追溯到冻结计划

- GIVEN 用户问题需要一个或多个站内或公开网检索维度
- WHEN 编排选择研究工具并执行检索
- THEN 每个实际检索均绑定同一份含 Run、Turn、Tool metadata、访问策略、预算、候选与 ContractGraph 身份的 `RetrievalPlan` digest，执行后不得静默改写或隐藏额外查询

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：技能路由结果、工具执行观察与上下文装配结果。
- 下游结果：本 Story 声明的 GWT 可观察结果，决定用户可见的回答模式与过程叙述。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
