# L3 Story：反馈上下文注入 (`feedback-context-injection`)

> 所属能力：[`learning-event-feedback-injection`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-015`](../../../spec.md#scn-015)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望注入数据必须经过字段白名单和策略过滤，
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “反馈上下文注入”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 反馈上下文注入

- “反馈上下文注入”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 注入数据必须经过字段白名单和策略过滤

- 注入数据必须经过字段白名单和策略过滤。

<a id="req-003"></a>
### REQ-003 注入内容必须经过白名单与策略过滤，不得泄露敏感原始字段

- 注入内容必须经过白名单与策略过滤，不得泄露敏感原始字段。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 反馈上下文注入

- GIVEN 当前 owner 已同意学习上下文、反馈投影达到策略最小样本，且 Run 尚未冻结模型请求。
- WHEN typed feedback context reader 为该 Run 构建上下文。
- THEN 模型仅收到 policy allowlist 允许的聚合摘要，不收到内部 definition digest、原始 query、answer、correction 或跨 owner 事实。
- AND 低样本、撤销、opt-out、owner 不匹配或 reader 失败时均 fail-closed，不注入旧值或本地合成结果。

## 6. 依赖

- 前置要求：[`learning-event-feedback-injection`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 经同意与策略过滤的反馈上下文注入

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺可用 Gamma 与获批 Prod Provider conformance 后对授权、撤权与真实模型请求的当前只读端到端回执。Run 已通过 account + persona scoped typed projection reader 构造 context，consent、最小样本与 policy allowlist 均 fail-closed。唯一 canonical projection definition 阻断跨 persona 聚合，模型 bridge 只接收脱敏 aggregate snapshot。gamma-local health gate 当前为 0/28，不能沿用历史 Run 回执准出。
- 完成判定：Run 只读取 owner-scoped typed feedback context reader。policy 显式决定允许字段、最小样本阈值和用户撤销/opt-out。模型 bridge 仅接收 allowlisted summary，不接收原始 query/answer/correction，且 local/API/App 证明命中、低样本不注入、撤销后立即排除和跨 owner fail-closed。`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
