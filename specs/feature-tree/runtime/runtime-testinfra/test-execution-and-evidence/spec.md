# L3 Story：测试执行与证据 (`test-execution-and-evidence`)

> 所属能力：[`runtime-testinfra`](../spec.md)

> Journey / Scenario：横切工程能力，不直接拥有 AppRoot Scenario。

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望 Runner 从 canonical 目录发现真实用例并记录可追溯执行结果，从而区分“存在测试入口”“实际执行”和“候选环境通过”。

## 2. 范围与非目标

### In Scope

- canonical 测试发现、执行、CaseResult、环境与制品摘要。

### Out of Scope

- 业务断言内容与测试数据领域实现。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 测试执行与证据单轨

- Runner 只从 canonical 三层目录发现测试，以直接 `spec_ref` 关联稳定验收锚点，并从真实执行结果生成 CaseResult。
- 结构入口、执行状态、环境和候选制品摘要分字段表达，文件存在不得冒充执行通过。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 测试执行与证据可追溯

- GIVEN canonical 测试入口和稳定验收锚点有效。
- WHEN Runner 发现并执行选中测试。
- THEN CaseResult 绑定真实测试、验收锚点、环境与候选摘要，并保持通过、失败、跳过和未执行可区分。
- AND 任一执行失败均不写入伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-testinfra`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 测试执行与证据验收闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `make verify-test-directory-layout` 全量通过，以及 Alpha/Beta/Gamma 对当前候选执行后生成的可比较 CaseResult；在两类证据齐备前不能声明执行与证据闭环。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
