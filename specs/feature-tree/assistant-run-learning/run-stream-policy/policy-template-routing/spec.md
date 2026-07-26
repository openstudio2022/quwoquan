# L3 Story：策略模板路由 (`policy-template-routing`)

> 所属能力：[`run-stream-policy`](../spec.md)

> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望策略变更必须版本化；域路由规则必须可灰度发布，
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “策略模板路由”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 策略模板路由

- “策略模板路由”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 策略变更必须版本化；域路由规则必须可灰度发布

- 策略变更必须版本化；域路由规则必须可灰度发布。

<a id="req-003"></a>
### REQ-003 未命中策略时必须走可解释的默认模板

- 未命中策略时必须走可解释的默认模板。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 策略模板路由

- GIVEN 当前域存在已激活的 immutable policy release、默认模板与稳定 actor cohort。
- WHEN 创建新的 AssistantRun 并解析策略模板。
- THEN Run 冻结唯一 `policyId/version/cohort`，同一 actor 与 rollout 配置稳定命中；未命中规则时使用该 release 声明的可解释默认模板。
- AND release activation 或 rollback 只影响后续 Run；配置无效或 resolver 失败时返回 canonical failure，不在 Run 生命周期内切换版本或写入伪成功选择。

## 6. 依赖

- 前置要求：[`run-stream-policy`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 版本化策略路由与灰度回滚

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前仅按静态 Skill manifest 做粗粒度匹配和 fallback，未拥有可审计的 policy release、稳定 cohort、选中版本快照或 rollback 语义；因此不能证明版本化和灰度发布。
- 完成判定：metadata-owned immutable policy release 声明 template/version/规则和默认模板。resolver 用稳定 actor bucket 选择 release 并将 `policyId/version/cohort` 写入 Run。一次 release activation 或 rollback 只改变后续 Run。local/API/App 证明命中、默认回退、cohort 稳定、回滚和失败不写成功事实。`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
