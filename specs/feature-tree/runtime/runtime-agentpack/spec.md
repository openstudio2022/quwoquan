# L2 Business Capability：Agent 特性上下文工具 (`runtime-agentpack`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

按目标路径扫描目录与 Markdown，生成只读的最小规格上下文、特性树总览和 Git 增量影响报告；产物只写入 `.qwq_output`。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-agentpack”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：按目标路径扫描目录与 Markdown，生成只读的最小规格上下文、特性树总览和 Git 增量影响报告；产物只写入 `.qwq_output`。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`feature-context-discovery`](./feature-context-discovery/spec.md)：同优先级多个 L1 认领路径时必须阻断；成功输出不得依赖 tracked index、registry 或状态文件。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime agentpack 能力 SIT

- 本能力必须直接扫描目录与 Markdown 生成上下文，不读取或写入 tracked tree/index/registry；无法唯一定位 owner 时必须 `GATE_BLOCK`。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime agentpack 能力 SIT

- GIVEN 执行“runtime agentpack 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime agentpack 能力”对应动作。
- THEN 输出包含唯一 owner、父链、REQ/验收/DEC/OPEN、metadata 与 `spec_ref`，且仓库中不存在 tracked TreeIndex。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime agentpack 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：目标路径无法稳定生成最小完整上下文时，Cursor/Codex 可能遗漏约束或误选领域 owner。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
