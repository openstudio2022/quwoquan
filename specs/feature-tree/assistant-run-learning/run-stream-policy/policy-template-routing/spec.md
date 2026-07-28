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
- `assistant-default` 的非 alpha 发布必须来自镜像内不可变 artifact：artifact 必须声明 command identity、canonical digest、默认模板、路由规则、learning-context allowlist 与 cohort assignment。publisher 必须在写入前校验 digest 和完整 schema，不得补写默认值，也不得从环境 seed、`cmd/api` 启动路径或静态 fallback 隐式创建 release/rollout。
- alpha、beta、gamma、prod 必须经运行配置显式指向 release 与 rollout artifact，并由受控的 `assistant-policy-publish` Job 执行幂等 stage/activate；同一 publisher 还必须作为服务 init container 成功完成，API 才能接收真实 Run。Alpha 可在服务防腐层绑定登记的模型 sandbox/local substitute，但 App、策略发布链和第一方业务结果不得使用 contract mock。发布报告仅可包含 policy/version/cohort/revision/digest 等 metadata，不能输出 prompt 内容。

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
- AND 同一 publication command 的重试返回首次持久化结果；复用 command identity 但改变 digest、revision 或 assignment 必须失败关闭。

## 6. 依赖

- 前置要求：[`run-stream-policy`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
