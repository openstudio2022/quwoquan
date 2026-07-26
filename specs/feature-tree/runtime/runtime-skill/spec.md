# L2 Business Capability：运行时 Skill (`runtime-skill`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

SkillRouter：根据 PageContext 场景 + 标签 → 匹配适用的 Skill。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-skill”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：SkillRouter：根据 PageContext 场景 + 标签 → 匹配适用的 Skill。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`skill-router-and-executor`](./skill-router-and-executor/spec.md)：Ecosystem Skill 必须在沙箱中执行，不得直接访问生产数据库。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime skill 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“SkillRouter：根据 PageContext 场景 + 标签 → 匹配适用的 Skill”所定义的业务结果；失败终态必须可区分且不得伪造成功。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime skill 能力 SIT

- GIVEN 执行“runtime skill 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime skill 能力”对应动作。
- THEN 直属 Story 共同交付“SkillRouter：根据 PageContext 场景 + 标签 → 匹配适用的 Skill”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime skill 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：SkillRouter：根据 PageContext 场景 + 标签 → 匹配适用的 Skill。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
