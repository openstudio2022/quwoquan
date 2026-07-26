# L2 Business Capability：开发流程治理 (`development-workflow-governance`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。

## 2. 范围与非目标

### In Scope

- AppRoot/L1/L2/L3 的目录、规格、设计与验收规则。
- `explore/prd/design/dev/verify` 等命令的统一上下文链。
- 动态特性上下文、总览、变更影响报告和机器门禁。

### Out of Scope

- 业务领域自身的产品决定和 wire schema。
- 将当前会话计划、执行日志或派生报告提交为长期真相源。

## 3. Journey / Scenario 贡献

- 本能力是横切工程能力，不直接承接用户 Journey；它为所有 Journey 提供一致的实施和审核约束。

## 4. Story



- [`directory-native-sdd`](./directory-native-sdd/spec.md)：工具必须直接扫描目录与 Markdown；删除 `.qwq_output` 后仍可从受版本控制真相源重建上下文。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 目录原生单轨治理

- 目录结构必须直接表达 `AppRoot / L1 / L2 / L3`，不得维护人工索引或状态镜像。
- 规格、设计、metadata、代码与测试必须各自承担唯一职责，不得生成第二真相源。
- 长期未完成事项必须进入最低 owner 节点 `OPEN`；已解决事项转为当前要求或直接删除。

<a id="req-002"></a>
### REQ-002 命令与自然语言一致执行

- 命令和自然语言执行必须使用同一 Spec Entry、Pre-work Reflection 与 Exit Review。
- 动态上下文、总览和变更报告只写入 `.qwq_output`。
- 目录、链接、章节、验收证据和禁止文件必须由可执行门禁校验。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 的仓库执行约束。
- 下游能力：仓库内所有业务节点、metadata、代码和测试。
- 读取事实：目录、Markdown、metadata、测试 `spec_ref` 与 Git diff。
- 写入事实：只修改正式规格、设计、metadata、代码和测试；派生结果写入 `.qwq_output`。
- 一致性要求：README 模板、命令和 gate 必须同步更新。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 目标节点可生成最小完整上下文

- GIVEN 仓库中存在符合层级规范的目标 spec 或被 L1 工程归属覆盖的代码路径。
- WHEN 开发者生成 feature context 并执行特性树门禁。
- THEN 输出包含唯一 owner、父链、要求、验收、设计决定、metadata、测试证据、OPEN 与 Git 影响。
- AND 任何人工索引、节点级 acceptance、changelog 或中央 backlog 回潮都会阻断。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 全树证据引用收口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：部分节点仍以同节点 OPEN 声明尚缺直接测试 `spec_ref`，影响自动验收覆盖率。
- 完成判定：`SIT-001` 及全部节点验收锚点均有真实测试 `spec_ref`，且不再依赖 OPEN 代替证据。
